import pytest

from app.embeddings import FakeEmbedder
from app.search_index import AzureSearchIndex, IndexedChunk, MemoryIndex, SearchIndexError
from tests.helpers import intercept_azure_http

EMBED = FakeEmbedder(dimensions=64)


def chunk(doc, n, text, workspace="1", filename="a.docx", label="Page 1"):
    return IndexedChunk(f"{doc}-{n}", doc, workspace, filename, label, 1, n, text,
                        EMBED.embed([text])[0])


def search(index, query, **kw):
    return index.search(query, EMBED.embed([query])[0], kw.pop("top_k", 5), **kw)


# ---- the local stand-in -------------------------------------------------------
def test_memory_index_finds_the_chunk_that_matches():
    index = MemoryIndex()
    index.replace_document("d1", [
        chunk("d1", 0, "Refunds are allowed within thirty days of purchase."),
        chunk("d1", 1, "The cafeteria opens at eight in the morning."),
    ])
    hits = search(index, "refund within thirty days")
    assert hits[0].content.startswith("Refunds are allowed")


def test_replace_document_removes_the_old_chunks():
    index = MemoryIndex()
    index.replace_document("d1", [chunk("d1", 0, "old text about parking")])
    index.replace_document("d1", [chunk("d1", 0, "new text about tuition")])
    texts = [h.content for h in search(index, "text")]
    assert texts == ["new text about tuition"]


def test_filters_by_workspace_and_document():
    index = MemoryIndex()
    index.replace_document("d1", [chunk("d1", 0, "shared words here", workspace="1")])
    index.replace_document("d2", [chunk("d2", 0, "shared words here", workspace="2")])
    assert {h.document_id for h in search(index, "shared words")} == {"d1", "d2"}
    assert {h.document_id for h in search(index, "shared words", workspace_id="2")} == {"d2"}
    assert {h.document_id for h in search(index, "shared words", document_id="d1")} == {"d1"}


def test_delete_document():
    index = MemoryIndex()
    index.replace_document("d1", [chunk("d1", 0, "some text")])
    index.delete_document("d1")
    assert search(index, "some text") == []


# ---- the Azure implementation, run through the real SDK ------------------------
def azure_index():
    return AzureSearchIndex("https://svc.search.windows.net", "key", "docmind-chunks", dimensions=64)


def make_handler(search_results=None, status=200):
    def handler(method, url, body):
        if status != 200:
            return status, {"error": {"code": "x", "message": "denied"}}
        if "docs/search.post.search" in url:
            return 200, {"value": search_results or []}
        if "docs/search.index" in url:
            return 200, {"value": [
                {"key": a.get("id", "k"), "status": True, "statusCode": 200}
                for a in (body or {}).get("value", [])
            ]}
        return 200, body  # creating the index: echo the definition back
    return handler


def test_azure_index_definition_has_a_vector_field_and_profile():
    with intercept_azure_http(make_handler()) as seen:
        azure_index().replace_document("d1", [chunk("d1", 0, "hello world")])
    method, url, definition = seen[0]
    assert method in ("PUT", "POST") and "docmind-chunks" in url
    fields = {f["name"]: f for f in definition["fields"]}
    assert fields["id"]["key"] is True
    assert fields["document_id"]["filterable"] is True
    assert fields["workspace_id"]["filterable"] is True
    assert fields["content"]["searchable"] is True
    vector = fields["content_vector"]
    assert vector["type"] == "Collection(Edm.Single)"
    assert vector["dimensions"] == 64
    assert vector["vectorSearchProfile"] == "vector-profile"
    assert definition["vectorSearch"]["profiles"][0]["name"] == "vector-profile"


def test_replace_document_clears_old_entries_then_uploads_the_new_ones():
    handler = make_handler(search_results=[{"id": "d1-old0"}, {"id": "d1-old1"}])
    with intercept_azure_http(handler) as seen:
        azure_index().replace_document("d1", [chunk("d1", 0, "fresh text")])
    posts = [(u, b) for m, u, b in seen if m == "POST"]
    lookup = next(b for u, b in posts if "docs/search.post.search" in u)
    assert lookup["filter"] == "document_id eq 'd1'"
    actions = [b["value"] for u, b in posts if "docs/search.index" in u]
    assert [a["@search.action"] for a in actions[0]] == ["delete", "delete"]
    assert [a["id"] for a in actions[0]] == ["d1-old0", "d1-old1"]
    assert actions[1][0]["@search.action"] == "upload"
    assert actions[1][0]["id"] == "d1-0"
    assert len(actions[1][0]["content_vector"]) == 64


def test_search_sends_a_hybrid_query_and_parses_the_hits():
    result = {"@search.score": 0.032, "id": "d1-0", "document_id": "d1", "filename": "a.docx",
              "label": "Page 2", "page_number": 2, "chunk_index": 0, "content": "refund text"}
    vector = EMBED.embed(["refund"])[0]
    with intercept_azure_http(make_handler(search_results=[result])) as seen:
        hits = azure_index().search("refund", vector, 5, workspace_id="1", document_id="d1")
    body = next(b for m, u, b in seen if "docs/search.post.search" in u)
    assert body["search"] == "refund"  # the keyword half
    (vector_query,) = body["vectorQueries"]  # the meaning half
    assert vector_query["kind"] == "vector"
    assert vector_query["fields"] == "content_vector"
    assert vector_query["vector"] == vector
    assert vector_query["k"] == 50
    assert body["filter"] == "workspace_id eq '1' and document_id eq 'd1'"
    assert body["top"] == 5
    assert (hits[0].filename, hits[0].label, hits[0].page_number) == ("a.docx", "Page 2", 2)
    assert hits[0].score == pytest.approx(0.032)


def test_filter_values_are_escaped():
    with intercept_azure_http(make_handler()) as seen:
        azure_index().search("x", [0.0] * 64, 3, document_id="a'b")
    body = next(b for m, u, b in seen if "docs/search.post.search" in u)
    assert body["filter"] == "document_id eq 'a''b'"


def test_rejected_credentials_become_a_readable_error():
    with intercept_azure_http(make_handler(status=403)):
        with pytest.raises(SearchIndexError, match="credentials"):
            azure_index().search("x", [0.0] * 64, 3)


def test_a_document_that_shrinks_leaves_no_leftover_chunks():
    index = MemoryIndex()
    index.replace_document("d1", [chunk("d1", 0, "alpha text"), chunk("d1", 1, "beta text")])
    index.replace_document("d1", [chunk("d1", 0, "gamma text")])
    assert [h.id for h in search(index, "text")] == ["d1-0"]
