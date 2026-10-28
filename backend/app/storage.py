from abc import ABC, abstractmethod
from functools import lru_cache
from pathlib import Path

from app.config import settings


class Storage(ABC):
    """Where uploaded files live. Switch backends with STORAGE_BACKEND in .env."""

    @abstractmethod
    def save(self, name: str, data: bytes, content_type: str) -> None: ...

    @abstractmethod
    def read(self, name: str) -> bytes: ...

    @abstractmethod
    def delete(self, name: str) -> None:
        """Remove a file. Deleting one that is already gone is not an error."""

    @abstractmethod
    def list_files(self) -> list[dict]: ...


class LocalStorage(Storage):
    def __init__(self, base_dir: str | Path):
        self.base = Path(base_dir).resolve()
        self.base.mkdir(parents=True, exist_ok=True)

    def _path(self, name: str) -> Path:
        path = (self.base / name).resolve()
        # Refuse anything that would land outside the storage folder
        if self.base not in path.parents:
            raise ValueError("Invalid storage path")
        return path

    def save(self, name: str, data: bytes, content_type: str) -> None:
        path = self._path(name)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "xb") as f:  # "x" fails if the file exists: never overwrite
            f.write(data)

    def read(self, name: str) -> bytes:
        return self._path(name).read_bytes()

    def delete(self, name: str) -> None:
        path = self._path(name)
        path.unlink(missing_ok=True)
        # Each upload lives in its own folder; tidy it away once it is empty
        if path.parent != self.base:
            try:
                path.parent.rmdir()
            except OSError:
                pass  # other files are still in it, or it is already gone

    def list_files(self) -> list[dict]:
        return [
            {"name": p.relative_to(self.base).as_posix(), "size": p.stat().st_size}
            for p in sorted(self.base.rglob("*"))
            if p.is_file()
        ]


class AzureBlobStorage(Storage):
    def __init__(self, connection_string: str, container: str):
        # Imported here so local development works without Azure configured
        from azure.storage.blob import BlobServiceClient

        service = BlobServiceClient.from_connection_string(connection_string)
        self._container = service.get_container_client(container)

    def save(self, name: str, data: bytes, content_type: str) -> None:
        from azure.storage.blob import ContentSettings

        self._container.upload_blob(
            name=name,
            data=data,
            overwrite=False,
            content_settings=ContentSettings(content_type=content_type),
        )

    def read(self, name: str) -> bytes:
        return self._container.download_blob(name).readall()

    def delete(self, name: str) -> None:
        from azure.core.exceptions import ResourceNotFoundError

        try:
            self._container.delete_blob(name)
        except ResourceNotFoundError:
            pass  # already gone

    def list_files(self) -> list[dict]:
        return [{"name": b.name, "size": b.size} for b in self._container.list_blobs()]


@lru_cache
def get_storage() -> Storage:
    if settings.storage_backend == "azure":
        if not settings.azure_storage_connection_string:
            raise RuntimeError(
                "STORAGE_BACKEND=azure but AZURE_STORAGE_CONNECTION_STRING is empty"
            )
        return AzureBlobStorage(
            settings.azure_storage_connection_string, settings.azure_storage_container
        )
    return LocalStorage(settings.local_storage_dir)
