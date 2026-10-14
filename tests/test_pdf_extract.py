import pymupdf
import pytest

from mizan.data.pdf_extract import extract_text


def make_pdf(path, pages):
    doc = pymupdf.open()
    for text in pages:
        page = doc.new_page()
        if text:
            page.insert_text((72, 72), text)
    doc.save(path)
    doc.close()


def test_text_pdf_is_extracted(tmp_path):
    make_pdf(tmp_path / "a.pdf", ["Board approved an interim dividend of 3.00 per share.", "Second page of results."])
    result = extract_text(tmp_path / "a.pdf")
    assert result.pages == 2 and not result.needs_ocr
    assert "interim dividend" in result.text and "Second page" in result.text


def test_pdf_without_text_layer_is_flagged_not_returned_empty(tmp_path):
    make_pdf(tmp_path / "scan.pdf", ["", ""])           # pages with no text, like a scan
    result = extract_text(tmp_path / "scan.pdf")
    assert result.needs_ocr and result.text == "" and result.pages == 2


def test_mostly_blank_pdf_is_flagged(tmp_path):
    make_pdf(tmp_path / "mixed.pdf", ["x", "", "", ""])
    assert extract_text(tmp_path / "mixed.pdf").needs_ocr


def test_non_pdf_file_raises(tmp_path):
    (tmp_path / "bad.pdf").write_bytes(b"not a pdf")
    with pytest.raises(Exception):
        extract_text(tmp_path / "bad.pdf")
