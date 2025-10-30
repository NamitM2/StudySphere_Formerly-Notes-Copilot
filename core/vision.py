# core/vision.py
"""
Vision model integration using Google Gemini for image understanding.
Analyzes images from PDFs to generate descriptions, identify content type,
and extract educational value.
"""
from __future__ import annotations

import os
import io
from typing import Dict, Any, List
from PIL import Image

import google.generativeai as genai

# Configuration
API_KEYS = []
primary_key = os.getenv("GOOGLE_API_KEY")
if primary_key:
    API_KEYS.append(primary_key)

for i in range(1, 6):
    backup_key = os.getenv(f"GOOGLE_API_KEY_{i}")
    if backup_key and backup_key not in API_KEYS:
        API_KEYS.append(backup_key)

VISION_MODEL = os.getenv("GEMINI_VISION_MODEL", "gemini-2.5-flash")
_current_key_index = 0


def _configure_api():
    """Configure the API with current key."""
    if not API_KEYS:
        raise RuntimeError("No Google API keys configured")
    genai.configure(api_key=API_KEYS[_current_key_index])


def analyze_image(
    image_bytes: bytes,
    page_context: str = "",
    nearby_text: str = "",
    filename: str = "",
    page_num: int = 0,
) -> Dict[str, Any]:
    """
    Analyze an image using Gemini Vision to extract educational content.

    Args:
        image_bytes: Raw image data
        page_context: Text from the page containing this image
        nearby_text: Text directly above/below the image (captions)
        filename: Source filename for context
        page_num: Page number for context

    Returns:
        Dict with:
        - description: Detailed description of the image
        - image_type: Category (diagram, chart, graph, equation, photo, etc.)
        - educational_value: Brief note on why this image is educationally relevant
        - key_concepts: List of key concepts shown
        - searchable_text: Text optimized for semantic search
    """
    global _current_key_index

    try:
        # Load image
        image = Image.open(io.BytesIO(image_bytes))

        # Build a detailed prompt for educational context
        prompt = f"""You are analyzing an image from a student's study material (page {page_num} of {filename}).

Your task is to provide a comprehensive analysis to help students search for and understand this visual content.

Context from nearby text: {nearby_text if nearby_text else "None"}

CRITICAL: Look carefully for ANY text in this image, including:
- Text rendered as part of the image (like PowerPoint/Google Slides text)
- Labels, titles, headings
- Captions or annotations
- Any words visible anywhere in the image
Extract ALL visible text word-for-word, exactly as shown.

Please analyze this image and provide:

1. TEXT_IN_IMAGE: Extract ANY text visible in the image word-for-word. If no text, write "None".

2. DESCRIPTION (2-3 sentences): What does this image show? Be specific and detailed. Include what any objects are (e.g., "a yellow banana").

3. IMAGE_TYPE: Classify as one of: diagram, flowchart, chart, graph, table, equation, formula, photo, screenshot, map, illustration, text_slide, other

4. EDUCATIONAL_VALUE (1 sentence): Why would a student care about this image? What does it teach or illustrate?

5. KEY_CONCEPTS (comma-separated): List 3-5 key concepts, terms, or topics shown in this image. Include specific objects shown.

6. SEARCHABLE_TEXT (2-3 sentences): Create search-optimized text. If there's text in the image, explicitly connect it with what's shown (e.g., "The slide says 'X' and shows [object]"). Include: the text from the image, what objects are shown, technical terms, and concepts that a student might search for.

Format your response as:
TEXT_IN_IMAGE: [extracted text or "None"]
DESCRIPTION: [your description]
IMAGE_TYPE: [type]
EDUCATIONAL_VALUE: [value]
KEY_CONCEPTS: [concept1, concept2, concept3]
SEARCHABLE_TEXT: [searchable version with all relevant terms]
"""

        _configure_api()
        model = genai.GenerativeModel(VISION_MODEL)

        # Generate analysis
        response = model.generate_content([prompt, image])

        if not response or not response.text:
            return _fallback_analysis(nearby_text)

        # Parse the structured response
        result = _parse_vision_response(response.text)

        # Note: Removed redundant OCR call for performance optimization
        # The vision analysis prompt already asks for text extraction
        # If it didn't find text, a second attempt is unlikely to succeed and adds latency

        # Add metadata
        result["raw_response"] = response.text
        result["model"] = VISION_MODEL

        return result

    except Exception as e:
        # Try next API key if quota exceeded
        error_str = str(e).lower()
        if "quota" in error_str or "429" in error_str or "resource exhausted" in error_str:
            print(f"Vision API key {_current_key_index + 1} quota exceeded, trying next key...")
            _current_key_index = (_current_key_index + 1) % len(API_KEYS)
            if _current_key_index != 0:  # Haven't cycled through all keys yet
                return analyze_image(image_bytes, page_context, nearby_text, filename, page_num)

        print(f"Warning: Vision analysis failed: {e}")
        return _fallback_analysis(nearby_text)


def _parse_vision_response(response_text: str) -> Dict[str, Any]:
    """Parse structured response from vision model."""
    lines = response_text.strip().split("\n")

    result = {
        "text_in_image": "",
        "description": "",
        "image_type": "unknown",
        "educational_value": "",
        "key_concepts": [],
        "searchable_text": "",
    }

    current_field = None
    current_value = []

    for line in lines:
        line = line.strip()
        if not line:
            continue

        # Check for field markers
        if line.startswith("TEXT_IN_IMAGE:"):
            # Finalize previous field before starting new one
            if current_field == "description" and current_value:
                result["description"] = " ".join(current_value)
            elif current_field == "educational_value" and current_value:
                result["educational_value"] = " ".join(current_value)
            elif current_field == "searchable_text" and current_value:
                result["searchable_text"] = " ".join(current_value)

            current_field = "text_in_image"
            current_value = []
            text_val = line.replace("TEXT_IN_IMAGE:", "").strip()
            result["text_in_image"] = text_val if text_val.lower() != "none" else ""
        elif line.startswith("DESCRIPTION:"):
            # Finalize previous field
            if current_field == "description" and current_value:
                result["description"] = " ".join(current_value)
            elif current_field == "educational_value" and current_value:
                result["educational_value"] = " ".join(current_value)
            elif current_field == "searchable_text" and current_value:
                result["searchable_text"] = " ".join(current_value)

            current_field = "description"
            current_value = [line.replace("DESCRIPTION:", "").strip()]
        elif line.startswith("IMAGE_TYPE:"):
            # Finalize previous field
            if current_field == "description" and current_value:
                result["description"] = " ".join(current_value)
            elif current_field == "educational_value" and current_value:
                result["educational_value"] = " ".join(current_value)
            elif current_field == "searchable_text" and current_value:
                result["searchable_text"] = " ".join(current_value)

            current_field = "image_type"
            current_value = []
            result["image_type"] = line.replace("IMAGE_TYPE:", "").strip().lower()
        elif line.startswith("EDUCATIONAL_VALUE:"):
            # Finalize previous field
            if current_field == "description" and current_value:
                result["description"] = " ".join(current_value)
            elif current_field == "educational_value" and current_value:
                result["educational_value"] = " ".join(current_value)
            elif current_field == "searchable_text" and current_value:
                result["searchable_text"] = " ".join(current_value)

            current_field = "educational_value"
            current_value = [line.replace("EDUCATIONAL_VALUE:", "").strip()]
        elif line.startswith("KEY_CONCEPTS:"):
            # Finalize previous field
            if current_field == "description" and current_value:
                result["description"] = " ".join(current_value)
            elif current_field == "educational_value" and current_value:
                result["educational_value"] = " ".join(current_value)
            elif current_field == "searchable_text" and current_value:
                result["searchable_text"] = " ".join(current_value)

            current_field = "key_concepts"
            current_value = []
            concepts_str = line.replace("KEY_CONCEPTS:", "").strip()
            result["key_concepts"] = [c.strip() for c in concepts_str.split(",") if c.strip()]
        elif line.startswith("SEARCHABLE_TEXT:"):
            # Finalize previous field
            if current_field == "description" and current_value:
                result["description"] = " ".join(current_value)
            elif current_field == "educational_value" and current_value:
                result["educational_value"] = " ".join(current_value)
            elif current_field == "searchable_text" and current_value:
                result["searchable_text"] = " ".join(current_value)

            current_field = "searchable_text"
            current_value = [line.replace("SEARCHABLE_TEXT:", "").strip()]
        elif current_field in ["description", "educational_value", "searchable_text"]:
            # Continuation of multi-line field
            current_value.append(line)

    # Finalize multi-line fields
    if current_field == "description" and current_value:
        result["description"] = " ".join(current_value)
    if current_field == "educational_value" and current_value:
        result["educational_value"] = " ".join(current_value)
    if current_field == "searchable_text" and current_value:
        result["searchable_text"] = " ".join(current_value)

    # Fallback to description if searchable_text is empty
    if not result["searchable_text"]:
        result["searchable_text"] = result["description"]

    return result


def _fallback_analysis(nearby_text: str) -> Dict[str, Any]:
    """Fallback when vision analysis fails."""
    description = f"Image from document. {nearby_text}" if nearby_text else "Image from document"

    return {
        "description": description,
        "image_type": "unknown",
        "educational_value": "Visual content from study material",
        "key_concepts": [],
        "searchable_text": description,
        "raw_response": "",
        "model": "fallback",
    }


def extract_text_from_image(image_bytes: bytes) -> str:
    """
    Use vision model to extract text from an image (OCR).
    Useful for scanned PDFs or images with text.
    """
    try:
        from PIL import Image

        image = Image.open(io.BytesIO(image_bytes))

        prompt = """Extract all text from this image.

Return ONLY the text content, preserving layout and structure as much as possible.
Do not add any commentary, descriptions, or explanations.
If there is no text, return "NO_TEXT_FOUND".

TEXT:"""

        _configure_api()
        model = genai.GenerativeModel(VISION_MODEL)
        response = model.generate_content([prompt, image])

        if response and response.text:
            text = response.text.strip()
            if text != "NO_TEXT_FOUND":
                return text

        return ""

    except Exception as e:
        print(f"Warning: Text extraction from image failed: {e}")
        return ""


def batch_analyze_images(
    images: List[Dict[str, Any]],
    pdf_bytes: bytes = None,
    filename: str = "",
    parallel: bool = True,
) -> List[Dict[str, Any]]:
    """
    Analyze multiple images in batch.

    Args:
        images: List of image dicts from image_extractor
        pdf_bytes: Original PDF bytes (for extracting nearby text)
        filename: Source filename
        parallel: If True, analyze images in parallel (much faster)

    Returns:
        List of analysis results corresponding to input images
    """
    from core.image_extractor import extract_text_near_image

    if parallel and len(images) > 1:
        # Use parallel processing for significant speedup
        import concurrent.futures
        import time

        print(f"[VISION] Analyzing {len(images)} images in parallel...")
        start_time = time.time()

        def analyze_single_image(img_tuple):
            i, img = img_tuple
            try:
                # Extract nearby text for context
                nearby_text = ""
                if pdf_bytes and img.get("bbox"):
                    nearby_text = extract_text_near_image(pdf_bytes, img["page"], img["bbox"])

                # Analyze
                analysis = analyze_image(
                    image_bytes=img["image_bytes"],
                    nearby_text=nearby_text,
                    filename=filename,
                    page_num=img["page"],
                )

                # Merge analysis with image metadata
                return {**img, **analysis}
            except Exception as e:
                print(f"[VISION] ERROR analyzing image {i+1}: {e}")
                return {**img, **_fallback_analysis("")}

        # Use ThreadPoolExecutor for parallel API calls
        # Gemini API supports 15 requests/minute, so limit to 5 concurrent
        max_workers = min(5, len(images))
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            results = list(executor.map(analyze_single_image, enumerate(images)))

        elapsed = time.time() - start_time
        print(f"[VISION] Completed {len(images)} image analyses in {elapsed:.1f}s ({elapsed/len(images):.1f}s per image)")
        return results

    else:
        # Sequential processing (original behavior)
        results = []

        for i, img in enumerate(images):
            print(f"Analyzing image {i+1}/{len(images)} on page {img['page']}...")

            # Extract nearby text for context
            nearby_text = ""
            if pdf_bytes and img.get("bbox"):
                nearby_text = extract_text_near_image(pdf_bytes, img["page"], img["bbox"])

            # Analyze
            analysis = analyze_image(
                image_bytes=img["image_bytes"],
                nearby_text=nearby_text,
                filename=filename,
                page_num=img["page"],
            )

            # Merge analysis with image metadata
            result = {**img, **analysis}
            results.append(result)

        return results
