from app.config import settings
from app.embeddings import Embedder, EmbeddingError
from app.main import app
from app.embeddings import get_embedder
from tests import helpers as h

DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
REFUNDS = ["Refunds are allowed within thirty days of purchase.", "Receipts are required for all returns."]
CAFETERIA = ["The cafeteria opens at eight and serves breakfast until ten."]


def ingest(client, name, paragraphs, index=True):
    data = h.make_docx(paragraphs)
    doc_id = client.post("/documents/upload", files={"file": (name, data, DOCX)}).json()["id"]
    client.post(f"/documents/{doc_id}/process")
    if index:
        assert client.post(f"/documents/{doc_id}/index").status_code == 200
    return doc_id


def search(client, query, **extra):
    response = client.post("/search", json={"query": query, **extra})
    assert response.status_code == 200
    return response.json()


def test_index_requires_extracted_text_first(client):
    data = h.make_docx(REFUNDS)
    doc_id = client.post("/documents/upload", files={"file": ("a.docx", data, DOCX)}).json()["id"]
    assert client.post(f"/documents/{doc_id}/index").status_code == 409


def test_index_unknown_document_is_404(client):
    assert client.post("/documents/nope/index").status_code == 404


def test_indexing_sets_status_and_reports_the_chunk_count(client):
    doc_id = ingest(client, "policy.docx", REFUNDS, index=False)
    result = client.post(f"/documents/{doc_id}/index").json()
    assert result["status"] == "indexed" and result["chunk_count"] == 1
    assert client.get(f"/documents/{doc_id}").json()["status"] == "indexed"


def test_a_long_document_becomes_several_chunks(client, monkeypatch):
    monkeypatch.setattr(settings, "chunk_chars", 300)
    monkeypatch.setattr(settings, "chunk_overlap_chars", 50)
    doc_id = ingest(client, "long.docx", [f"Paragraph {i} about refunds and returns." for i in range(60)], index=False)
    assert client.post(f"/documents/{doc_id}/index").json()["chunk_count"] > 3


def test_search_finds_the_right_document_with_citation_details(client):
    ingest(client, "refunds.docx", REFUNDS)
    ingest(client, "cafeteria.docx", CAFETERIA)
    hits = search(client, "refund within thirty days")
    assert hits[0]["filename"] == "refunds.docx"
    assert hits[0]["label"] == "Document" and hits[0]["page_number"] == 1
    assert "thirty days" in hits[0]["content"]


def test_search_can_be_limited_to_one_document(client):
    first = ingest(client, "refunds.docx", REFUNDS)
    ingest(client, "other.docx", REFUNDS)
    hits = search(client, "refunds", document_id=first)
    assert {hit["document_id"] for hit in hits} == {first}


def test_indexing_twice_does_not_duplicate(client, search_index):
    doc_id = ingest(client, "refunds.docx", REFUNDS)
    client.post(f"/documents/{doc_id}/index")
    assert len(search_index._chunks) == 1


def test_processing_again_removes_the_stale_search_entries(client):
    doc_id = ingest(client, "refunds.docx", REFUNDS)
    assert search(client, "refunds")
    client.post(f"/documents/{doc_id}/process")  # new text is coming; old entries must go
    assert search(client, "refunds") == []
    assert client.get(f"/documents/{doc_id}").json()["status"] == "extracted"


def test_embedding_failure_returns_502_and_records_why(client):
    class Broken(Embedder):
        dimensions = 3

        def embed(self, texts):
            raise EmbeddingError("Embedding rate limit reached.")

    doc_id = ingest(client, "refunds.docx", REFUNDS, index=False)
    app.dependency_overrides[get_embedder] = lambda: Broken()
    response = client.post(f"/documents/{doc_id}/index")
    assert response.status_code == 502
    detail = client.get(f"/documents/{doc_id}").json()
    assert detail["status"] == "extracted"
    assert "Indexing failed" in detail["status_detail"]


def test_search_with_nothing_indexed_returns_an_empty_list(client):
    assert search(client, "anything") == []


def test_search_rejects_bad_requests(client):
    assert client.post("/search", json={"query": ""}).status_code == 422
    assert client.post("/search", json={"query": "x", "top_k": 0}).status_code == 422
    assert client.post("/search", json={"query": "x", "top_k": 99}).status_code == 422

