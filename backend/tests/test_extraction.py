import pytest

from app.extraction import ExtractionError, extract
from app.ocr import NoOcr, OcrUnavailable
from tests import helpers as h


def texts(segments):
    return [s.text for s in segments]


def test_docx_paragraphs_and_tables():
    data = h.make_docx(["First paragraph", "Second paragraph"], [["Name", "Role"], ["Ana", "Admin"]])
    (segment,) = extract(data, "policy.docx", NoOcr())
    assert segment.label == "Document" and segment.source == "text"
    assert "First paragraph" in segment.text
    assert "Ana | Admin" in segment.text


def test_pptx_one_segment_per_slide_with_notes():
    data = h.make_pptx(["Intro slide", "Results slide"], notes={1: "speaker note"})
    segments = extract(data, "deck.pptx", NoOcr())
    assert [s.label for s in segments] == ["Slide 1", "Slide 2"]
    assert "Intro slide" in segments[0].text
    assert "speaker note" in segments[1].text


def test_xlsx_one_segment_per_sheet_and_skips_empty_rows():
    data = h.make_xlsx({"Budget": [["Item", "Cost"], ["Laptop", 900], [None, None]], "Empty": []})
    (segment,) = extract(data, "budget.xlsx", NoOcr())
    assert segment.label == "Sheet: Budget"
    assert "Laptop\t900" in segment.text


def test_pdf_text_layer_is_read_without_ocr():
    data = h.make_text_pdf(["First page has plenty of text", "Second page also has text"])
    segments = extract(data, "a.pdf", NoOcr())
    assert [s.number for s in segments] == [1, 2]
    assert all(s.source == "text" for s in segments)


def test_scanned_pdf_without_ocr_reports_unavailable():
    with pytest.raises(OcrUnavailable):
        extract(h.make_blank_pdf(2), "scan.pdf", NoOcr())


def test_scanned_pdf_pages_go_to_ocr():
    ocr = h.FakeOcr()
    segments = extract(h.make_blank_pdf(2), "scan.pdf", ocr)
    assert ocr.calls == [("application/pdf", [1, 2])]
    assert [s.source for s in segments] == ["ocr", "ocr"]


def test_mixed_pdf_only_sends_scanned_pages_to_ocr_and_keeps_order():
    ocr = h.FakeOcr()
    segments = extract(h.make_mixed_pdf(), "mixed.pdf", ocr)
    assert ocr.calls == [("application/pdf", [2])]
    assert [(s.number, s.source) for s in segments] == [(1, "text"), (2, "ocr")]


def test_image_is_read_with_ocr():
    ocr = h.FakeOcr()
    (segment,) = extract(h.make_png(), "photo.png", ocr)
    assert ocr.calls == [("image/png", None)]
    assert segment.source == "ocr"


def test_image_without_ocr_reports_unavailable():
    with pytest.raises(OcrUnavailable):
        extract(h.make_png(), "photo.png", NoOcr())


def test_document_with_no_text_is_an_error():
    with pytest.raises(ExtractionError):
        extract(h.make_docx([]), "empty.docx", NoOcr())


@pytest.mark.parametrize("name", ["bad.pdf", "bad.docx", "bad.pptx", "bad.xlsx"])
def test_damaged_files_become_extraction_errors(name):
    with pytest.raises(ExtractionError):
        extract(b"this is not a real file", name, NoOcr())


def test_unsupported_extension():
    with pytest.raises(ExtractionError):
        extract(b"x", "notes.txt", NoOcr())
