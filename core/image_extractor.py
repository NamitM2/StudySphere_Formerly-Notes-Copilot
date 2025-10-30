# core/image_extractor.py
"""
Extract images from PDF documents using PyMuPDF (fitz).
Filters out small/irrelevant images and prepares them for vision model analysis.
"""
from __future__ import annotations

import io
from typing import List, Dict, Any, Tuple
import fitz  # PyMuPDF


# Minimum dimensions to consider an image worth analyzing
MIN_IMAGE_WIDTH = 100  # pixels
MIN_IMAGE_HEIGHT = 100  # pixels
MIN_IMAGE_AREA = 10000  # pixels (100x100)

# Maximum image size to avoid processing huge images
MAX_IMAGE_DIMENSION = 4096  # pixels


def _is_valid_image(width: int, height: int) -> bool:
    """Check if image dimensions are worth processing."""
    if width < MIN_IMAGE_WIDTH or height < MIN_IMAGE_HEIGHT:
        return False
    if width * height < MIN_IMAGE_AREA:
        return False
    return True


def _detect_image_type(xref: int, page: fitz.Page) -> str:
    """
    Attempt to detect what type of image this is based on context.
    Returns: 'diagram', 'chart', 'photo', 'equation', 'unknown'
    """
    # This is a basic heuristic - the vision model will do better classification
    # For now, we just return 'unknown' and let the AI figure it out
    return "unknown"


def extract_images_from_pdf(pdf_bytes: bytes, render_slides=True) -> List[Dict[str, Any]]:
    """
    Extract all meaningful images from a PDF.

    Args:
        pdf_bytes: PDF file bytes
        render_slides: If True, render entire pages as images for slide decks (captures text).
                      If False, extract only embedded images (default behavior).

    Returns a list of dicts with:
    - page: int (1-based page number)
    - image_index: int (0-based index on the page)
    - width: int
    - height: int
    - format: str ('png', 'jpeg', etc.)
    - image_bytes: bytes (the actual image data in PNG format)
    - bbox: tuple (x0, y0, x1, y1) - bounding box on page
    - xref: int (PyMuPDF reference number, or -1 for rendered pages)
    - is_rendered_page: bool (True if this is a full page render)
    """
    images: List[Dict[str, Any]] = []

    with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
        for page_num in range(len(doc)):
            page = doc[page_num]

            # Check if this looks like a slide/presentation page
            text_length = len(page.get_text().strip())
            image_list = page.get_images(full=True)

            # Detect slides: pages with few embedded images AND little/no extractable text
            # These are likely Google Slides, PowerPoint exports where text is rendered as images
            # Key indicators:
            # - 0-2 embedded images (slides usually have 0-2 photos/graphics)
            # - Little/no extractable text (< 100 chars means text is rendered as image)
            is_likely_slide = len(image_list) <= 2 and text_length < 100

            # If render_slides enabled and this looks like a slide, render the whole page
            if render_slides and is_likely_slide:
                # Render entire page as image (this captures both text and images together)
                try:
                    # Render at 2x resolution for better OCR
                    mat = fitz.Matrix(2, 2)
                    pix = page.get_pixmap(matrix=mat, alpha=False)
                    img_bytes = pix.tobytes("png")

                    images.append({
                        "page": page_num + 1,
                        "image_index": 0,
                        "width": pix.width,
                        "height": pix.height,
                        "format": "png",
                        "image_bytes": img_bytes,
                        "bbox": page.rect,
                        "xref": -1,  # No xref for rendered pages
                        "is_rendered_page": True,
                    })
                    print(f"[IMAGE_EXTRACT] Rendered full page {page_num + 1} as image ({pix.width}x{pix.height}) - detected as slide")
                    continue  # Skip extracting individual images from this page
                except Exception as e:
                    print(f"[IMAGE_EXTRACT] Warning: Failed to render page {page_num + 1}: {e}")
                    # Fall through to extract embedded images instead

            for img_index, img_info in enumerate(image_list):
                try:
                    xref = img_info[0]  # XREF number

                    # Get the image
                    base_image = doc.extract_image(xref)
                    if not base_image:
                        continue

                    image_bytes = base_image["image"]
                    image_ext = base_image["ext"]  # png, jpeg, etc.
                    width = base_image.get("width", 0)
                    height = base_image.get("height", 0)

                    # Filter out small/invalid images
                    if not _is_valid_image(width, height):
                        continue

                    # Get bounding box of image on page (for context)
                    # Note: An image might appear multiple times on a page
                    # We'll use the first occurrence
                    bbox = None
                    try:
                        img_rects = page.get_image_rects(xref)
                        if img_rects:
                            bbox = img_rects[0]  # First occurrence
                    except Exception:
                        bbox = None

                    images.append({
                        "page": page_num + 1,  # 1-based
                        "image_index": img_index,
                        "width": width,
                        "height": height,
                        "format": image_ext,
                        "image_bytes": image_bytes,
                        "bbox": tuple(bbox) if bbox else None,
                        "xref": xref,
                        "is_rendered_page": False,
                    })

                except Exception as e:
                    # Skip problematic images
                    print(f"Warning: Failed to extract image {img_index} from page {page_num + 1}: {e}")
                    continue

    return images


def extract_text_near_image(pdf_bytes: bytes, page_num: int, bbox: Tuple[float, float, float, float] | None) -> str:
    """
    Extract text near an image's bounding box to get context (captions, labels, etc.).

    Args:
        pdf_bytes: The PDF file bytes
        page_num: 1-based page number
        bbox: Bounding box (x0, y0, x1, y1) or None

    Returns:
        Extracted text around the image
    """
    if bbox is None:
        return ""

    try:
        with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
            page = doc[page_num - 1]  # Convert to 0-based

            # Expand bbox to capture nearby text (captions above/below)
            x0, y0, x1, y1 = bbox
            search_margin = 50  # pixels

            # Search area: above and below the image
            search_rect_above = fitz.Rect(
                max(0, x0 - search_margin),
                max(0, y0 - search_margin * 2),
                x1 + search_margin,
                y0
            )
            search_rect_below = fitz.Rect(
                max(0, x0 - search_margin),
                y1,
                x1 + search_margin,
                min(page.rect.height, y1 + search_margin * 2)
            )

            # Extract text from these regions
            text_above = page.get_text("text", clip=search_rect_above).strip()
            text_below = page.get_text("text", clip=search_rect_below).strip()

            # Combine and clean
            combined = []
            if text_above:
                combined.append(text_above)
            if text_below:
                combined.append(text_below)

            return " ".join(combined)

    except Exception as e:
        print(f"Warning: Failed to extract text near image on page {page_num}: {e}")
        return ""


def get_image_summary(images: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Get summary statistics about extracted images."""
    if not images:
        return {
            "total_images": 0,
            "pages_with_images": 0,
            "avg_images_per_page": 0,
        }

    pages_with_images = len(set(img["page"] for img in images))

    return {
        "total_images": len(images),
        "pages_with_images": pages_with_images,
        "avg_images_per_page": round(len(images) / pages_with_images, 1) if pages_with_images > 0 else 0,
        "formats": list(set(img["format"] for img in images)),
    }
