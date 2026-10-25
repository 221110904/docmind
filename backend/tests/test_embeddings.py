import json
import math

import httpx
import pytest
from openai import OpenAI

from app.embeddings import AzureOpenAIEmbedder, EmbeddingError, FakeEmbedder


def cosine(a, b):
    return sum(x * y for x, y in zip(a, b)) / (math.hypot(*a) * math.hypot(*b))


def test_fake_embedder_is_deterministic_and_normalized():
    e = FakeEmbedder(dimensions=32)
    a, b = e.embed(["refund policy"])[0], e.embed(["refund policy"])[0]
    assert a == b and len(a) == 32
    assert math.isclose(math.hypot(*a), 1.0)


def test_fake_embedder_gives_shared_words_higher_similarity():
    e = FakeEmbedder(dimensions=256)
    query, related, unrelated = e.embed(
        ["refund policy for returns", "returns and refund rules", "quarterly sales forecast"]
    )
    assert cosine(query, related) > cosine(query, unrelated)


def make_client(handler):
    return OpenAI(
        base_url="https://res.openai.azure.com/openai/v1/",
        api_key="secret",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
        max_retries=0,
    )


def embeddings_reply(request):
    body = json.loads(request.content)
    data = [
        {"object": "embedding", "index": i, "embedding": [float(len(t)), 1.0, 0.0]}
        for i, t in enumerate(body["input"])
    ]
    data.reverse()  # the service may return items out of order; index says where they belong
    return httpx.Response(200, json={
        "object": "list", "data": data, "model": "m",
        "usage": {"prompt_tokens": 1, "total_tokens": 1},
    })


def test_azure_embedder_sends_the_right_request_and_keeps_order():
    seen = []

    def handler(request):
        seen.append(request)
        return embeddings_reply(request)

    embedder = AzureOpenAIEmbedder(
        "https://res.openai.azure.com", "secret", "text-embedding-3-large",
        dimensions=3, client=make_client(handler),
    )
    vectors = embedder.embed(["a", "bb", "ccc"])

    assert [v[0] for v in vectors] == [1.0, 2.0, 3.0]  # restored to input order
    request = seen[0]
    assert request.url.path == "/openai/v1/embeddings"
    body = json.loads(request.content)
    assert body["model"] == "text-embedding-3-large"
    assert body["dimensions"] == 3
    assert body["input"] == ["a", "bb", "ccc"]


def test_azure_embedder_sends_batches_of_sixteen():
    sizes = []

    def handler(request):
        sizes.append(len(json.loads(request.content)["input"]))
        return embeddings_reply(request)

    embedder = AzureOpenAIEmbedder("https://x", "k", "dep", 3, client=make_client(handler))
    vectors = embedder.embed([f"text {i}" for i in range(35)])
    assert sizes == [16, 16, 3]
    assert len(vectors) == 35


@pytest.mark.parametrize(
    "status, expected",
    [(429, "rate limit"), (401, "credentials"), (500, "Embedding service error")],
)
def test_service_errors_become_readable_embedding_errors(status, expected):
    def handler(request):
        return httpx.Response(status, json={"error": {"message": "nope", "code": "x"}})

    embedder = AzureOpenAIEmbedder("https://x", "k", "dep", 3, client=make_client(handler))
    with pytest.raises(EmbeddingError, match=expected):
        embedder.embed(["hello"])
