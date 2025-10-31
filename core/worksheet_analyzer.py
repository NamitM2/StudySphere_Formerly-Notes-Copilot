"""
Worksheet Analyzer - Uses Gemini Vision to detect fillable fields in PDF worksheets
"""

import fitz  # PyMuPDF
import google.generativeai as genai
import os
import json
from typing import List, Dict, Any
from PIL import Image
import io

class WorksheetAnalyzer:
    """Analyzes PDF worksheets using Gemini Vision to detect fillable fields."""

    def __init__(self):
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise ValueError("GOOGLE_API_KEY environment variable not set")

        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel("gemini-2.0-flash-exp")
        print("[WORKSHEET_ANALYZER] Initialized with Gemini 2.0 Flash")

    def detect_fields(self, pdf_bytes: bytes) -> List[Dict[str, Any]]:
        """
        Detect fillable fields in a PDF worksheet using Gemini Vision.

        Args:
            pdf_bytes: PDF file as bytes

        Returns:
            List of detected fields with positions and metadata
        """
        print("[WORKSHEET_ANALYZER] Starting field detection...")

        # Convert PDF pages to images
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        all_fields = []

        for page_num in range(len(doc)):
            print(f"[WORKSHEET_ANALYZER] Analyzing page {page_num + 1}/{len(doc)}")
            page = doc[page_num]

            # Render at 2x scale for better OCR
            pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
            img_bytes = pix.tobytes("png")

            # Analyze with Gemini Vision
            fields = self._analyze_page_image(img_bytes, page_num + 1)
            all_fields.extend(fields)

        doc.close()
        print(f"[WORKSHEET_ANALYZER] Detected {len(all_fields)} fields total")
        return all_fields

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

            response = self.model.generate_content(
                [prompt, image],
                generation_config={
                    "temperature": 0.2,  # Low temperature for consistent detection
                    "response_mime_type": "application/json"
                }
            )

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
