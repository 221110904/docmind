import hashlib
import math
import re
from abc import ABC, abstractmethod
from functools import lru_cache

from app.config import settings


class EmbeddingError(Exception):
    """The embedding service could not turn the text into vectors."""


class Embedder(ABC):
    dimensions: int

    @abstractmethod
    def embed(self, texts: list[str]) -> list[list[float]]: ...


class FakeEmbedder(Embedder):
    """Local stand-in: hashes words into a vector.

    Texts that share words get similar vectors, which is enough to test the pipeline,
    but this is NOT semantic. Real meaning-based search needs the Azure embedder.
    """

    def __init__(self, dimensions: int = 64):
        self.dimensions = dimensions

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._one(t) for t in texts]

    def _one(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        for word in re.findall(r"\w+", text.lower()):
            digest = hashlib.md5(word.encode()).digest()
            slot = int.from_bytes(digest[:4], "big") % self.dimensions
            vector[slot] += 1.0 if digest[4] % 2 == 0 else -1.0
        norm = math.sqrt(sum(v * v for v in vector)) or 1.0
        return [v / norm for v in vector]


class AzureOpenAIEmbedder(Embedder):
    """Embeddings from an Azure OpenAI deployment, using the v1 API (no api-version)."""

    def __init__(
        self,
        endpoint: str,
        key: str,
        deployment: str,
        dimensions: int,
        batch_size: int = 16,
        client=None,
    ):
        if client is None:
            from openai import OpenAI

            client = OpenAI(
                base_url=f"{endpoint.rstrip('/')}/openai/v1/", api_key=key, max_retries=5
            )
        self._client = client
        self._deployment = deployment
        self._batch_size = batch_size
        self.dimensions = dimensions

    def embed(self, texts: list[str]) -> list[list[float]]:
        import openai

        vectors: list[list[float]] = []
        for start in range(0, len(texts), self._batch_size):
            batch = texts[start : start + self._batch_size]
            try:
                response = self._client.embeddings.create(
                    model=self._deployment, input=batch, dimensions=self.dimensions
                )
            except openai.AuthenticationError as exc:
                raise EmbeddingError(
                    "Embedding service rejected the credentials (check the endpoint and key)."
                ) from exc
            except openai.RateLimitError as exc:
                raise EmbeddingError(
                    "Embedding rate limit reached. Retry shortly, or raise the deployment capacity."
                ) from exc
            except openai.OpenAIError as exc:
                raise EmbeddingError(f"Embedding service error: {str(exc)[:200]}") from exc
            ordered = sorted(response.data, key=lambda item: item.index)
            vectors.extend(list(item.embedding) for item in ordered)
        return vectors


@lru_cache
def get_embedder() -> Embedder:
    if settings.embedding_backend == "azure":
        if not (settings.azure_openai_endpoint and settings.azure_openai_key):
            raise RuntimeError(
                "EMBEDDING_BACKEND=azure but AZURE_OPENAI_ENDPOINT or AZURE_OPENAI_KEY is empty"
            )
        return AzureOpenAIEmbedder(
            settings.azure_openai_endpoint,
            settings.azure_openai_key,
            settings.azure_openai_embedding_deployment,
            settings.embedding_dimensions,
        )
    return FakeEmbedder(settings.embedding_dimensions)
