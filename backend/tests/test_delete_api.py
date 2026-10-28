from app.main import app
from app.search_index import MemoryIndex, SearchIndexError, get_search_index
from app.storage import LocalStorage, get_storage

try:
    from tests.helpers import make_docx
except ImportError:  # tests/ is not a package here
    from helpers import make_docx

DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def make_searchable(client, filename, paragraphs):
    upload = client.post(
        "/documents/upload", files={"file": (filename, make_docx(paragraphs), DOCX)}
    )
    assert upload.status_code == 201, upload.text
    document_id = upload.json()["id"]
    assert client.post(f"/documents/{document_id}/process").status_code == 200
    assert client.post(f"/documents/{document_id}/index").status_code == 200
    return document_id


def search(client, query):
    return client.post("/search", json={"query": query, "top_k": 5}).json()


class BrokenStorage(LocalStorage):
    def delete(self, name):
        raise OSError("disk unavailable")


class BrokenIndex(MemoryIndex):
    def delete_document(self, document_id):
        raise SearchIndexError("search service unavailable")


def test_delete_removes_the_document_its_text_its_file_and_its_search_entries(client, storage):
    document_id = make_searchable(client, "audit.docx", ["Personal USB drives are allowed."])
    assert storage.list_files()
    assert search(client, "personal USB drives")

    response = client.delete(f"/documents/{document_id}")

    assert response.status_code == 204
    assert response.content == b""
    assert client.get(f"/documents/{document_id}").status_code == 404
    assert client.get(f"/documents/{document_id}/text").status_code == 404
    assert client.get("/documents").json() == []
    assert storage.list_files() == []
    assert search(client, "personal USB drives") == []


def test_delete_leaves_other_documents_alone(client, storage):
    first = make_searchable(client, "a.docx", ["Backups run weekly in the server room."])
    second = make_searchable(client, "b.docx", ["Visitors must be escorted at all times."])

    assert client.delete(f"/documents/{first}").status_code == 204

    remaining = client.get("/documents").json()
    assert [d["id"] for d in remaining] == [second]
    assert [f["name"].split("/")[0] for f in storage.list_files()] == [second]
    hits = search(client, "visitors escorted")
    assert hits and {h["filename"] for h in hits} == {"b.docx"}
    assert search(client, "backups weekly server room")[0]["filename"] == "b.docx"


def test_deleting_an_unknown_or_already_deleted_document_is_a_404(client):
    assert client.delete("0" * 32).status_code == 404
    document_id = make_searchable(client, "a.docx", ["Some text to keep."])
    assert client.delete(f"/documents/{document_id}").status_code == 204
    assert client.delete(f"/documents/{document_id}").status_code == 404


def test_a_document_that_was_never_processed_can_be_deleted(client, storage):
    upload = client.post(
        "/documents/upload", files={"file": ("raw.docx", make_docx(["Unread."]), DOCX)}
    )
    document_id = upload.json()["id"]
    assert client.delete(f"/documents/{document_id}").status_code == 204
    assert storage.list_files() == []


def test_a_storage_failure_keeps_the_document_so_it_can_be_retried(client, storage):
    document_id = make_searchable(client, "audit.docx", ["Personal USB drives are allowed."])
    app.dependency_overrides[get_storage] = lambda: BrokenStorage(storage.base)

    response = client.delete(f"/documents/{document_id}")

    assert response.status_code == 502
    assert "stored file" in response.json()["detail"]
    assert [d["id"] for d in client.get("/documents").json()] == [document_id]


def test_a_search_service_failure_keeps_the_file_and_the_document(client, storage):
    document_id = make_searchable(client, "audit.docx", ["Personal USB drives are allowed."])
    app.dependency_overrides[get_search_index] = lambda: BrokenIndex()

    response = client.delete(f"/documents/{document_id}")

    assert response.status_code == 502
    assert "search service unavailable" in response.json()["detail"]
    assert storage.list_files()
    assert [d["id"] for d in client.get("/documents").json()] == [document_id]
