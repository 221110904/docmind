import base64

import pytest

from app.storage import AzureBlobStorage, LocalStorage

try:
    from tests.helpers import intercept_azure_http
except ImportError:  # tests/ is not a package here
    from helpers import intercept_azure_http


def test_local_delete_removes_the_file_and_its_empty_folder(tmp_path):
    storage = LocalStorage(tmp_path)
    storage.save("doc1/a.docx", b"x", "text/plain")
    storage.delete("doc1/a.docx")
    assert storage.list_files() == []
    assert not (tmp_path / "doc1").exists()


def test_local_delete_leaves_other_files_alone(tmp_path):
    storage = LocalStorage(tmp_path)
    storage.save("doc1/a.docx", b"x", "text/plain")
    storage.save("doc1/b.docx", b"y", "text/plain")
    storage.save("doc2/c.docx", b"z", "text/plain")
    storage.delete("doc1/a.docx")
    assert [f["name"] for f in storage.list_files()] == ["doc1/b.docx", "doc2/c.docx"]


def test_deleting_a_missing_file_is_not_an_error(tmp_path):
    storage = LocalStorage(tmp_path)
    storage.delete("doc1/never-existed.docx")
    storage.save("doc1/a.docx", b"x", "text/plain")
    storage.delete("doc1/a.docx")
    storage.delete("doc1/a.docx")  # second time


def test_delete_refuses_paths_outside_the_storage_folder(tmp_path):
    outside = tmp_path / "outside.txt"
    outside.write_text("keep me")
    storage = LocalStorage(tmp_path / "uploads")
    with pytest.raises(ValueError):
        storage.delete("../outside.txt")
    assert outside.exists()


def azure_storage() -> AzureBlobStorage:
    key = base64.b64encode(b"test-key").decode()
    connection = (
        "DefaultEndpointsProtocol=https;AccountName=acct;"
        f"AccountKey={key};EndpointSuffix=core.windows.net"
    )
    return AzureBlobStorage(connection, "documents")


def test_azure_delete_sends_a_delete_for_that_blob():
    with intercept_azure_http(lambda method, url, body: (202, None)) as seen:
        azure_storage().delete("doc1/a.docx")
    assert [method for method, _, _ in seen] == ["DELETE"]
    assert seen[0][1].split("?")[0].endswith("/documents/doc1/a.docx")


def test_azure_delete_of_a_missing_blob_is_not_an_error():
    with intercept_azure_http(lambda method, url, body: (404, {"error": "BlobNotFound"})):
        azure_storage().delete("doc1/gone.docx")
