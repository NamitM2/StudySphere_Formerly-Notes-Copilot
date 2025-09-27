from io import BytesIO
from typing import List
from pypdf import PdfReader

def extract_text_from_pdf(pdf_bytes: bytes) -> List[str]:
    """Return a list of page texts from a PDF byte stream."""
    reader = PdfReader(BytesIO(pdf_bytes))
    pages = []
    for page in reader.pages:
        txt = page.extract_text() or ""
        # Normalize whitespace a bit
        pages.append("\n".join(line.strip() for line in txt.splitlines()))
    return pages
