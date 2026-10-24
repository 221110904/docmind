from sqlalchemy import select

from app.config import settings
from app.models import Document, Role, Workspace

PDF = ("report.pdf", b"%PDF-1.4 sample content", "application/pdf")


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_seed_data_exists(session_factory):
    with session_factory() as db:
        roles = {r.name for r in db.scalars(select(Role))}
        assert roles == {"admin", "viewer"}
        assert db.scalars(select(Workspace)).first().name == "Default"


def test_upload_stores_file_and_database_row(client, storage, session_factory):
    response = client.post("/documents/upload", files={"file": PDF})
    assert response.status_code == 201
    body = response.json()
    assert body["filename"] == "report.pdf"
    assert body["status"] == "uploaded"
    assert body["size_bytes"] == len(PDF[1])

    assert [f["name"] for f in storage.list_files()] == [body["blob_name"]]
    with session_factory() as db:
        assert db.get(Document, body["id"]) is not None


def test_upload_rejects_unsupported_type(client, storage):
    response = client.post(
        "/documents/upload", files={"file": ("notes.txt", b"hello", "text/plain")}
    )
    assert response.status_code == 400
    assert storage.list_files() == []


def test_upload_rejects_empty_file(client):
    response = client.post(
        "/documents/upload", files={"file": ("empty.pdf", b"", "application/pdf")}
    )
    assert response.status_code == 400


def test_upload_rejects_oversize_file(client, monkeypatch):
    monkeypatch.setattr(settings, "max_upload_mb", 1)
    big = b"0" * (1024 * 1024 + 1)
    response = client.post(
        "/documents/upload", files={"file": ("big.pdf", big, "application/pdf")}
    )
    assert response.status_code == 413


def test_upload_strips_folder_parts_from_filename(client, storage):
    for hostile in ("../../evil.pdf", "..\\..\\evil.pdf"):
        response = client.post(
            "/documents/upload", files={"file": (hostile, b"data", "application/pdf")}
        )
        assert response.status_code == 201
        assert response.json()["filename"] == "evil.pdf"
    for f in storage.list_files():
        assert f["name"].count("/") == 1  # always <document id>/<file name>


def test_two_uploads_with_same_name_do_not_overwrite(client, storage):
    client.post("/documents/upload", files={"file": PDF})
    client.post("/documents/upload", files={"file": PDF})
    assert len(storage.list_files()) == 2


def test_list_and_get_documents(client):
    created = client.post("/documents/upload", files={"file": PDF}).json()
    listing = client.get("/documents").json()
    assert [d["id"] for d in listing] == [created["id"]]
    assert client.get(f"/documents/{created['id']}").json()["filename"] == "report.pdf"


def test_get_unknown_document_returns_404(client):
    assert client.get("/documents/doesnotexist").status_code == 404


def test_timestamps_are_always_utc(client):
    created = client.post("/documents/upload", files={"file": PDF}).json()
    listed = client.get("/documents").json()[0]
    for value in (created["created_at"], listed["created_at"]):
        assert value.endswith("Z") or value.endswith("+00:00")
