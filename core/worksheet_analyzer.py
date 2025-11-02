"""
Worksheet Analyzer - Uses Gemini Vision to detect fillable fields in PDF worksheets
"""

import fitz  # PyMuPDF
import google.generativeai as genai
import os
import json
from typing import List, Dict, Any, Optional, Tuple
from PIL import Image
import io
import time
from pathlib import Path

BOUNDS_VERSION = 3

DEBUG_BOUNDS_PATH = Path("logs/gemini_bounds.jsonl")
DEBUG_BOUNDS_PATH.parent.mkdir(parents=True, exist_ok=True)


def _debug_log_bounds(record: dict) -> None:
    """Persist raw Gemini bounds to disk for offline inspection."""
    timestamp = time.strftime("%Y-%m-%dT%H:%M:%S")
    with DEBUG_BOUNDS_PATH.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"timestamp": timestamp, **record}, ensure_ascii=False) + "\n")


class WorksheetAnalyzer:
    """Analyzes PDF worksheets using Gemini Vision to detect fillable fields."""

    def __init__(self):
        self.api_key = os.getenv("GOOGLE_API_KEY")
        self.model: Optional[genai.GenerativeModel] = None
        self._configured = False

    def _ensure_configured(self):
        """Lazy initialization - configure Gemini only when needed."""
        if self._configured:
            return

        if not self.api_key:
            raise ValueError(
                "GOOGLE_API_KEY environment variable not set. "
                "Worksheet field detection requires Gemini API access."
            )

        genai.configure(api_key=self.api_key)
        self.model = genai.GenerativeModel("gemini-2.0-flash-exp")
        self._configured = True
        print("[WORKSHEET_ANALYZER] Initialized with Gemini 2.0 Flash")

    @staticmethod
    def is_available() -> bool:
        """Check if Gemini API is configured and available."""
        return bool(os.getenv("GOOGLE_API_KEY"))

    def detect_fields(self, pdf_bytes: bytes) -> Tuple[List[Dict[str, Any]], Dict[int, Dict[str, float]]]:
        """
        Detect fillable fields in a PDF worksheet using Gemini Vision.

        Args:
            pdf_bytes: PDF file as bytes

        Returns:
            Tuple[List[Dict[str, Any]], Dict[int, Dict[str, float]]]: detected fields and per-page dimensions

        Raises:
            ValueError: If GOOGLE_API_KEY is not configured
        """
        self._ensure_configured()
        print("[WORKSHEET_ANALYZER] Starting field detection...")

        # Convert PDF pages to images
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        all_fields = []
        page_dimensions: Dict[int, Dict[str, float]] = {}

        for page_num in range(len(doc)):
            print(f"[WORKSHEET_ANALYZER] Analyzing page {page_num + 1}/{len(doc)}")
            page = doc[page_num]

            # Check page rotation and correct if upside down
            rotation = page.rotation
            print(f"[WORKSHEET_ANALYZER] Page {page_num + 1} rotation: {rotation}°")

            # Render at 2x scale for better OCR
            # If page is upside down (180°), apply rotation during rendering
            # This ensures Gemini sees the correct orientation
            if rotation == 180:
                print(f"[WORKSHEET_ANALYZER] Correcting upside-down page to upright")
                # Create matrix with 2x scale AND 180° rotation correction
                # rotate parameter takes degrees counter-clockwise, so -180 corrects a 180° rotation
                pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), rotate=-rotation)
            else:
                pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))

            img_bytes = pix.tobytes("png")

            # Analyze with Gemini Vision
            fields = self._analyze_page_image(img_bytes, page_num + 1)
            if fields:
                page_width = float(page.rect.width or 1.0)
                page_height = float(page.rect.height or 1.0)
                page_dimensions[page_num + 1] = {
                    "width": page_width,
                    "height": page_height
                }

                img_width = float(pix.width or 1.0)
                img_height = float(pix.height or 1.0)

                print(f"[WORKSHEET_ANALYZER] Page {page_num + 1} - PDF: {page_width}x{page_height}, Image: {img_width}x{img_height}")

                for idx, field in enumerate(fields):
                    bounds = field.get("bounds")
                    if not isinstance(bounds, dict):
                        continue
                    try:
                        raw_x = float(bounds.get("x", 0.0))
                        raw_y = float(bounds.get("y", 0.0))
                        raw_w = float(bounds.get("width", 0.0))
                        raw_h = float(bounds.get("height", 0.0))
                    except (TypeError, ValueError):
                        continue

                    is_fractional = all(0.0 <= val <= 1.0 for val in (raw_x, raw_y, raw_w, raw_h))

                    if idx < 5:  # Debug log the first few raw detections so we can inspect Gemini output
                        record = {
                            "page": page_num + 1,
                            "field_id": field.get("id"),
                            "raw_bounds": {
                                "x": raw_x,
                                "y": raw_y,
                                "width": raw_w,
                                "height": raw_h
                            },
                            "assumed_fractional": is_fractional,
                            "image_size": {"width": img_width, "height": img_height},
                            "pdf_size": {"width": page_width, "height": page_height}
                        }
                        print("[WORKSHEET_ANALYZER] Raw Gemini bounds", record)
                        try:
                            _debug_log_bounds(record)
                        except Exception as log_error:
                            print(f"[WORKSHEET_ANALYZER] Failed to write raw bounds debug log: {log_error}")
                    if is_fractional:
                        pdf_width = raw_w * page_width
                        pdf_height = raw_h * page_height
                        pdf_x = raw_x * page_width
                        pdf_y = raw_y * page_height
                    else:
                        scale_x = page_width / img_width
                        scale_y = page_height / img_height
                        pdf_width = raw_w * scale_x
                        pdf_height = raw_h * scale_y
                        pdf_x = raw_x * scale_x
                        pdf_y = raw_y * scale_y

                    # Keep top-left origin (don't flip Y-axis) since frontend uses top-left origin too
                    # Normalize coordinates to 0-1 range by dividing by PDF page dimensions
                    normalized_x = pdf_x / page_width
                    normalized_y = pdf_y / page_height
                    normalized_width = pdf_width / page_width
                    normalized_height = pdf_height / page_height

                    if idx == 0:
                        print(f"[WORKSHEET_ANALYZER] First field - raw: ({raw_x}, {raw_y}, {raw_w}, {raw_h}) -> pdf: ({pdf_x:.2f}, {pdf_y:.2f}, {pdf_width:.2f}, {pdf_height:.2f}) -> normalized: ({normalized_x:.4f}, {normalized_y:.4f}, {normalized_width:.4f}, {normalized_height:.4f})")

                    field["bounds"] = {
                        "x": round(normalized_x, 4),
                        "y": round(normalized_y, 4),
                        "width": round(normalized_width, 4),
                        "height": round(normalized_height, 4)
                    }
                    field["bounds_version"] = BOUNDS_VERSION

            all_fields.extend(fields)

        doc.close()
        print(f"[WORKSHEET_ANALYZER] Detected {len(all_fields)} fields total")
        return all_fields, page_dimensions

    def _analyze_page_image(self, img_bytes: bytes, page_num: int) -> List[Dict]:
        """
        Analyze a single page image to detect fillable fields.

        Args:
            img_bytes: PNG image bytes of the PDF page
            page_num: Page number (1-indexed)

        Returns:
            List of detected fields
        """
        # Convert to PIL Image for Gemini
        image = Image.open(io.BytesIO(img_bytes))

        prompt = """Analyze this worksheet page and identify ALL fillable areas where a student would write answers.

IMPORTANT: Look for these types of fillable fields:

1. **Text Lines**: Blank lines like "Name: _____________" or "97 + 65 = _____"
2. **Text Boxes**: Larger areas with "Show your work" or multi-line answer spaces
3. **Multiple Choice**: Options with circles or checkboxes like (A) (B) (C) (D)
4. **Math Work Areas**: Grid paper or boxed areas for calculations

For EACH fillable area you find, provide:
- **type**: "text_line", "text_box", "multiple_choice", or "math_work"
- **bounds**: Pixel coordinates {x, y, width, height} of the fillable area
- **question_number**: The question number/label if visible (e.g., "1", "Q3", "Problem 5")
- **context**: The full question or instruction text near this field
- **placeholder**: Suggested placeholder text for the input

CRITICAL: The bounds must be accurate pixel coordinates where the student should type.
- For "Name: _______", bounds should be over the underline
- For "97 + 65 = ___", bounds should be over the blank line after =
- For work areas, bounds should cover the entire space provided

Return ONLY valid JSON (no markdown formatting):
[
  {
    "type": "text_line",
    "bounds": {"x": 150, "y": 200, "width": 300, "height": 25},
    "question_number": "1",
    "context": "97 + 65 =",
    "placeholder": "Answer"
  },
  {
    "type": "math_work",
    "bounds": {"x": 100, "y": 300, "width": 400, "height": 150},
    "question_number": "2",
    "context": "Show your work for: 24 × 13",
    "placeholder": "Show your work here"
  }
]

If you don't find any fillable fields, return an empty array: []"""

        try:
            print(f"[WORKSHEET_ANALYZER] Sending page {page_num} to Gemini Vision...")

            # Retry logic for rate limiting (429 errors)
            max_retries = 3
            retry_delay = 2  # Start with 2 seconds

            for attempt in range(max_retries):
                try:
                    response = self.model.generate_content(
                        [prompt, image],
                        generation_config={
                            "temperature": 0.2,  # Low temperature for consistent detection
                            "response_mime_type": "application/json"
                        }
                    )
                    break  # Success, exit retry loop
                except Exception as api_error:
                    error_msg = str(api_error)
                    if "429" in error_msg or "Resource exhausted" in error_msg:
                        if attempt < max_retries - 1:
                            wait_time = retry_delay * (2 ** attempt)  # Exponential backoff
                            print(f"[WORKSHEET_ANALYZER] Rate limited (429). Retrying in {wait_time}s... (attempt {attempt + 1}/{max_retries})")
                            import time
                            time.sleep(wait_time)
                        else:
                            print(f"[WORKSHEET_ANALYZER] Rate limit exceeded after {max_retries} attempts")
                            raise
                    else:
                        raise  # Re-raise non-429 errors immediately

            # Parse JSON response
            fields_data = json.loads(response.text)

            if not isinstance(fields_data, list):
                print(f"[WORKSHEET_ANALYZER] Warning: Expected list, got {type(fields_data)}")
                return []

            # Add page number and generate IDs
            fields = []
            for i, field in enumerate(fields_data):
                field["id"] = f"page{page_num}_field{i}"
                field["page"] = page_num
                fields.append(field)

            print(f"[WORKSHEET_ANALYZER] Found {len(fields)} fields on page {page_num}")
            return fields

        except json.JSONDecodeError as e:
            print(f"[WORKSHEET_ANALYZER] JSON decode error on page {page_num}: {e}")
            print(f"[WORKSHEET_ANALYZER] Raw response: {response.text[:500]}")
            return []
        except Exception as e:
            print(f"[WORKSHEET_ANALYZER] Error analyzing page {page_num}: {e}")
            return []

    def validate_fields(self, fields: List[Dict]) -> List[Dict]:
        """
        Validate and clean detected fields.

        Args:
            fields: List of detected fields

        Returns:
            Cleaned and validated fields
        """
        valid_fields = []

        for field in fields:
            # Check required keys
            required_keys = ["id", "type", "bounds", "page"]
            if not all(key in field for key in required_keys):
                print(f"[WORKSHEET_ANALYZER] Skipping invalid field (missing keys): {field.get('id', 'unknown')}")
                continue

            # Validate bounds
            bounds = field["bounds"]
            if not all(key in bounds for key in ["x", "y", "width", "height"]):
                print(f"[WORKSHEET_ANALYZER] Skipping field with invalid bounds: {field['id']}")
                continue

            # Ensure bounds are positive
            if any(bounds[key] <= 0 for key in ["width", "height"]):
                print(f"[WORKSHEET_ANALYZER] Skipping field with non-positive dimensions: {field['id']}")
                continue

            # Validate type
            valid_types = ["text_line", "text_box", "multiple_choice", "math_work"]
            if field["type"] not in valid_types:
                print(f"[WORKSHEET_ANALYZER] Unknown field type '{field['type']}', defaulting to 'text_line'")
                field["type"] = "text_line"

            valid_fields.append(field)

        print(f"[WORKSHEET_ANALYZER] Validated {len(valid_fields)}/{len(fields)} fields")
        return valid_fields
