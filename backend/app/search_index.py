import math
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from functools import lru_cache

from app.config import settings


class SearchIndexError(Exception):
    """The search service rejected a request or could not be reached."""


@dataclass
class IndexedChunk:
    id: str
    document_id: str
    workspace_id: str
    filename: str
    label: str
    page_number: int
    chunk_index: int
    content: str
    vector: list[float]


@dataclass
class SearchHit:
    id: str
    document_id: str
    filename: str
    label: str
    page_number: int
    chunk_index: int
    content: str
    score: float


class SearchIndex(ABC):
    @abstractmethod
    def replace_document(self, document_id: str, chunks: list[IndexedChunk]) -> None:
        """Remove everything stored for the document, then store the new chunks."""

    @abstractmethod
    def delete_document(self, document_id: str) -> None: ...

    @abstractmethod
    def search(
        self,
        query_text: str,
        query_vector: list[float],
        top_k: int,
        workspace_id: str | None = None,
        document_id: str | None = None,
    ) -> list[SearchHit]: ...


def _words(text: str) -> set[str]:
    return set(re.findall(r"\w+", text.lower()))


class MemoryIndex(SearchIndex):
    """Local stand-in that mimics hybrid search: keyword rank + vector rank, fused (RRF)."""

    def __init__(self):
        self._chunks: dict[str, IndexedChunk] = {}

    def replace_document(self, document_id, chunks):
        self.delete_document(document_id)
        for chunk in chunks:
            self._chunks[chunk.id] = chunk

    def delete_document(self, document_id):
        self._chunks = {k: c for k, c in self._chunks.items() if c.document_id != document_id}

    def search(self, query_text, query_vector, top_k, workspace_id=None, document_id=None):
        pool = [
            c
            for c in self._chunks.values()
            if (workspace_id is None or c.workspace_id == workspace_id)
            and (document_id is None or c.document_id == document_id)
        ]
        query_words = _words(query_text)
        keyword_rank = sorted(
            (c for c in pool if query_words & _words(c.content)),
            key=lambda c: -len(query_words & _words(c.content)),
        )
        vector_rank = sorted(pool, key=lambda c: -_cosine(query_vector, c.vector))

        scores: dict[str, float] = {}
        for ranking in (keyword_rank, vector_rank):
            for position, chunk in enumerate(ranking, start=1):
                scores[chunk.id] = scores.get(chunk.id, 0.0) + 1.0 / (60 + position)
        best = sorted(pool, key=lambda c: -scores.get(c.id, 0.0))[:top_k]
        return [_hit(c, scores.get(c.id, 0.0)) for c in best]


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    return dot / norm if norm else 0.0


def _hit(c: IndexedChunk, score: float) -> SearchHit:
    return SearchHit(c.id, c.document_id, c.filename, c.label, c.page_number,
                     c.chunk_index, c.content, score)


def _odata(value: str) -> str:
    return value.replace("'", "''")


class AzureSearchIndex(SearchIndex):
    """Hybrid (keyword + vector) search in Azure AI Search."""

    FIELDS = ["id", "document_id", "filename", "label", "page_number", "chunk_index", "content"]

    def __init__(self, endpoint, key, index_name, dimensions, index_client=None, search_client=None):
        from azure.core.credentials import AzureKeyCredential
        from azure.search.documents import SearchClient
        from azure.search.documents.indexes import SearchIndexClient

        credential = AzureKeyCredential(key)
        self._index_name = index_name
        self._dimensions = dimensions
        self._index_client = index_client or SearchIndexClient(endpoint, credential)
        self._client = search_client or SearchClient(endpoint, index_name, credential)
        self._ready = False

    def _ensure_index(self) -> None:
        if self._ready:
            return
        from azure.core.exceptions import HttpResponseError
        from azure.search.documents.indexes.models import (
            HnswAlgorithmConfiguration, SearchableField, SearchField, SearchFieldDataType,
            SearchIndex as AzureIndex, SimpleField, VectorSearch, VectorSearchProfile,
        )

        index = AzureIndex(
            name=self._index_name,
            fields=[
                SimpleField(name="id", type=SearchFieldDataType.String, key=True),
                SimpleField(name="document_id", type=SearchFieldDataType.String, filterable=True),
                SimpleField(name="workspace_id", type=SearchFieldDataType.String, filterable=True),
                SimpleField(name="filename", type=SearchFieldDataType.String),
                SimpleField(name="label", type=SearchFieldDataType.String),
                SimpleField(name="page_number", type=SearchFieldDataType.Int32),
                SimpleField(name="chunk_index", type=SearchFieldDataType.Int32),
                SearchableField(name="content", type=SearchFieldDataType.String),
                SearchField(
                    name="content_vector",
                    type=SearchFieldDataType.Collection(SearchFieldDataType.Single),
                    searchable=True,
                    vector_search_dimensions=self._dimensions,
                    vector_search_profile_name="vector-profile",
                ),
            ],
            vector_search=VectorSearch(
                algorithms=[HnswAlgorithmConfiguration(name="hnsw")],
                profiles=[VectorSearchProfile(
                    name="vector-profile", algorithm_configuration_name="hnsw")],
            ),
        )
        try:
            self._index_client.create_or_update_index(index)
        except HttpResponseError as exc:
            raise SearchIndexError(_describe(exc)) from exc
        self._ready = True

    def replace_document(self, document_id, chunks):
        from azure.core.exceptions import HttpResponseError

        self._ensure_index()
        self.delete_document(document_id)
        documents = [
            {
                "id": c.id, "document_id": c.document_id, "workspace_id": c.workspace_id,
                "filename": c.filename, "label": c.label, "page_number": c.page_number,
                "chunk_index": c.chunk_index, "content": c.content, "content_vector": c.vector,
            }
            for c in chunks
        ]
        try:
            for start in range(0, len(documents), 500):  # the service accepts up to 1000
                self._client.upload_documents(documents[start : start + 500])
        except HttpResponseError as exc:
            raise SearchIndexError(_describe(exc)) from exc

    def delete_document(self, document_id):
        from azure.core.exceptions import HttpResponseError

        self._ensure_index()
        try:
            found = self._client.search(
                search_text="*", filter=f"document_id eq '{_odata(document_id)}'",
                select=["id"], top=1000,
            )
            stale = [{"id": item["id"]} for item in found]
            if stale:
                self._client.delete_documents(stale)
        except HttpResponseError as exc:
            raise SearchIndexError(_describe(exc)) from exc

    def search(self, query_text, query_vector, top_k, workspace_id=None, document_id=None):
        from azure.core.exceptions import HttpResponseError
        from azure.search.documents.models import VectorizedQuery

        self._ensure_index()
        clauses = []
        if workspace_id is not None:
            clauses.append(f"workspace_id eq '{_odata(workspace_id)}'")
        if document_id is not None:
            clauses.append(f"document_id eq '{_odata(document_id)}'")
        try:
            results = self._client.search(
                search_text=query_text,
                vector_queries=[VectorizedQuery(
                    vector=query_vector, k_nearest_neighbors=max(top_k, 50),
                    fields="content_vector")],
                filter=" and ".join(clauses) or None,
                select=self.FIELDS,
                top=top_k,
            )
            return [
                SearchHit(r["id"], r["document_id"], r["filename"], r["label"],
                          r["page_number"], r["chunk_index"], r["content"], r["@search.score"])
                for r in results
            ]
        except HttpResponseError as exc:
            raise SearchIndexError(_describe(exc)) from exc


def _describe(exc) -> str:
    status = getattr(exc, "status_code", None)
    if status in (401, 403):
        return "Search service rejected the credentials (check the endpoint and admin key)."
    reason = (getattr(exc, "message", None) or str(exc)).strip().splitlines()[0][:200]
    return f"Search service error ({status}): {reason}"


@lru_cache
def get_search_index() -> SearchIndex:
    if settings.search_backend == "azure":
        if not (settings.azure_search_endpoint and settings.azure_search_key):
            raise RuntimeError(
                "SEARCH_BACKEND=azure but AZURE_SEARCH_ENDPOINT or AZURE_SEARCH_KEY is empty"
            )
        return AzureSearchIndex(
            settings.azure_search_endpoint, settings.azure_search_key,
            settings.azure_search_index, settings.embedding_dimensions,
        )
    return MemoryIndex()
