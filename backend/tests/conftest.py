import os

# Tests must never depend on, or talk to, real services. Environment variables beat the
# developer's .env file, so pin every backend to its local stand-in before the app loads.
os.environ.update(
    STORAGE_BACKEND="local",
    OCR_BACKEND="none",
    EMBEDDING_BACKEND="fake",
    SEARCH_BACKEND="memory",
    DATABASE_URL="sqlite://",
    AZURE_STORAGE_CONNECTION_STRING="",
    DOCUMENT_INTELLIGENCE_ENDPOINT="",
    DOCUMENT_INTELLIGENCE_KEY="",
    AZURE_OPENAI_ENDPOINT="",
    AZURE_OPENAI_KEY="",
    AZURE_SEARCH_ENDPOINT="",
    AZURE_SEARCH_KEY="",
    QA_BACKEND="fake",
    CORS_ORIGINS="http://localhost:5173,http://127.0.0.1:5173",
    AUTH_BACKEND="none",
    ENTRA_TENANT_ID="",
    ENTRA_TENANT_SUBDOMAIN="",
    ENTRA_API_CLIENT_ID="",
)

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import get_db, init_db
from app.embeddings import FakeEmbedder, get_embedder
from app.ocr import NoOcr, get_ocr
from app.main import app
from app.search_index import MemoryIndex, get_search_index
from app.storage import LocalStorage, get_storage
from app.qa import FakeAnswerer, get_answerer


@pytest.fixture
def storage(tmp_path):
    return LocalStorage(tmp_path / "uploads")


@pytest.fixture
def session_factory():
    # A throwaway in-memory database, so tests never touch real data
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    init_db(engine)
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


@pytest.fixture
def embedder():
    return FakeEmbedder(dimensions=64)


@pytest.fixture
def search_index():
    return MemoryIndex()


@pytest.fixture
def client(storage, session_factory, embedder, search_index):
    def override_db():
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_storage] = lambda: storage
    app.dependency_overrides[get_embedder] = lambda: embedder
    app.dependency_overrides[get_ocr] = lambda: NoOcr()
    app.dependency_overrides[get_search_index] = lambda: search_index
    app.dependency_overrides[get_answerer] = lambda: FakeAnswerer()
    # Used without "with", so the real startup (real database) does not run
    yield TestClient(app)
    app.dependency_overrides.clear()
