"""PDF -> plain text with PyMuPDF.

Some PSX announcements are scanned images with no text layer. Those come back
with needs_ocr=True instead of silently producing an empty evidence item.
OCR itself is not implemented yet.
"""

from dataclasses import dataclass
from pathlib import Path

import pymupdf

# A page with fewer extractable characters than this is treated as an image.
MIN_CHARS_PER_PAGE = 20


@dataclass
class ExtractedText:
    text: str
    pages: int
    needs_ocr: bool


def extract_text(path: str | Path) -> ExtractedText:
    with pymupdf.open(path) as doc:
        page_texts = [page.get_text().strip() for page in doc]
    text = "\n\n".join(t for t in page_texts if t)
    needs_ocr = len(text) < MIN_CHARS_PER_PAGE * max(len(page_texts), 1)
    return ExtractedText(text=text, pages=len(page_texts), needs_ocr=needs_ocr)
