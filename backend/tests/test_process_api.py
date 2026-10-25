from app.main import app
from app.ocr import get_ocr
from tests import helpers as h

DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def upload(client, name, data, content_type):
    response = client.post("/documents/upload", files={"file": (name, data, content_type)})
    assert response.status_code == 201
    return response.json()["id"]


def test_process_docx_stores_segments(client):
    doc_id = upload(client, "policy.docx", h.make_docx(["Refund policy text"]), DOCX)
    result = client.post(f"/documents/{doc_id}/process").json()
    assert result["status"] == "extracted"
    assert result["segment_count"] == 1

    assert client.get(f"/documents/{doc_id}").json()["status"] == "extracted"
    (segment,) = client.get(f"/documents/{doc_id}/text").json()
    assert "Refund policy text" in segment["text"]


def test_processing_twice_does_not_duplicate_segments(client):
    doc_id = upload(client, "deck.pptx", h.make_pptx(["One", "Two"]), "application/vnd.ms-powerpoint")
    client.post(f"/documents/{doc_id}/process")
    client.post(f"/documents/{doc_id}/process")
    assert len(client.get(f"/documents/{doc_id}/text").json()) == 2


def test_scan_without_ocr_is_marked_needs_ocr(client):
    doc_id = upload(client, "scan.pdf", h.make_blank_pdf(), "application/pdf")
    result = client.post(f"/documents/{doc_id}/process").json()
    assert result["status"] == "needs_ocr"
    assert result["segment_count"] == 0
    assert "OCR" in result["status_detail"]


def test_scan_with_ocr_is_extracted(client):
    app.dependency_overrides[get_ocr] = lambda: h.FakeOcr()
    doc_id = upload(client, "scan.pdf", h.make_blank_pdf(2), "application/pdf")
    result = client.post(f"/documents/{doc_id}/process").json()
    assert result["status"] == "extracted"
    segments = client.get(f"/documents/{doc_id}/text").json()
    assert [(s["number"], s["source"]) for s in segments] == [(1, "ocr"), (2, "ocr")]


def test_damaged_file_is_marked_failed_with_reason(client):
    doc_id = upload(client, "broken.pdf", b"not a pdf at all", "application/pdf")
    result = client.post(f"/documents/{doc_id}/process").json()
    assert result["status"] == "failed"
    assert "Could not read" in result["status_detail"]


def test_process_unknown_document_returns_404(client):
    assert client.post("/documents/nope/process").status_code == 404
    assert client.get("/documents/nope/text").status_code == 404
