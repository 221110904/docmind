from app.config import settings
from app.embeddings import FakeEmbedder, get_embedder
from app.ocr import NoOcr, get_ocr
from app.search_index import MemoryIndex, get_search_index
from app.storage import LocalStorage, get_storage


def test_tests_are_pinned_to_local_stand_ins_whatever_the_env_file_says():
    assert settings.ocr_backend == "none"
    assert settings.embedding_backend == "fake"
    assert settings.search_backend == "memory"
    assert settings.storage_backend == "local"
    assert settings.database_url == "sqlite://"


def test_default_factories_never_return_a_real_azure_client():
    for factory in (get_ocr, get_embedder, get_search_index, get_storage):
        factory.cache_clear()
    assert isinstance(get_ocr(), NoOcr)
    assert isinstance(get_embedder(), FakeEmbedder)
    assert isinstance(get_search_index(), MemoryIndex)
    assert isinstance(get_storage(), LocalStorage)
