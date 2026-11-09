import pytest

from app.benchmark import (
    AzureOpenAIBenchmarker, BenchmarkError, FakeBenchmarker, Provision, parse_items, parse_plan,
    parse_provisions, parse_verdicts, run_benchmark,
)
from app.benchmark_api import router  # noqa: F401
from app.benchmark import get_benchmarker
from app.web_fetch import FetchError, Page
from app.web_search import WebSearch, WebResult, get_web_search
from app.main import app
from tests.helpers import make_docx

PAGES = {
    "https://a.edu/p": Page("https://a.edu/p", "A Policy", [(1, "Attendance requirements for students\nAppeals process for grades\n")]),
    "https://b.edu/p": Page("https://b.edu/p", "B Policy", [(2, "Plagiarism and academic honesty rules\n")]),
}


def fake_fetch(url, max_chars=0):
    if url not in PAGES:
        raise FetchError("The site could not be reached.")
    return PAGES[url]


def test_parse_verdicts_downgrades_uncited_and_rejects_foreign_citations():
    data = {"results": [
        {"item": 1, "status": "covered", "citations": [99], "gap": "", "suggested_edit": ""},
        {"item": 2, "status": "partial", "citations": [5], "gap": "weak", "suggested_edit": "add"},
        {"item": 7, "status": "covered", "citations": [5]},
        {"item": 3, "status": "nonsense", "citations": []},
    ]}
    out = parse_verdicts(data, {1: {1, 2}, 2: {5}, 3: {6}})
    assert out[1].status == "missing" and out[1].cited == []
    assert out[2].status == "partial" and out[2].cited == [5]
    assert 7 not in out
    assert out[3].status == "missing"


def test_parse_items_keeps_only_real_provisions():
    provs = {1: Provision("a", "s", 1, 1)}
    data = {"items": [
        {"topic": "T", "expected": "E", "provisions": [1, 42, "x"]},
        {"topic": "Invented", "expected": "E", "provisions": [42]},
        {"topic": "", "expected": "E", "provisions": [1]},
    ]}
    items = parse_items(data, provs, 20)
    assert [i.topic for i in items] == ["T"] and len(items[0].peers) == 1


def test_parse_plan_and_provisions():
    assert parse_plan({"topic": "t", "queries": ["a", "", "b", "c"]}, "f").queries == ["a", "b"]
    with pytest.raises(BenchmarkError):
        parse_plan({"queries": []}, "f")
    ps = parse_provisions({"provisions": [{"topic": "x", "summary": "y", "page": 3}, {"topic": "", "summary": "y"}, "bad"]}, 2)
    assert len(ps) == 1 and ps[0].page == 3 and ps[0].source == 2


def test_run_benchmark_end_to_end(embedder, search_index):
    from app.search_index import IndexedChunk

    texts = ["Students must meet attendance requirements each semester.", "Our budget policy covers travel."]
    vectors = embedder.embed(texts)
    search_index.replace_document("d1", [
        IndexedChunk(f"d1-{i}", "d1", "1", "doc.docx", "Page 1", 1, i, t, v) for i, (t, v) in enumerate(zip(texts, vectors))
    ])
    result = run_benchmark(
        filename="doc.docx", document_id="d1", workspace_id="1",
        urls=["https://a.edu/p", "https://b.edu/p", "https://bad.edu/p"],
        benchmarker=FakeBenchmarker(), embedder=embedder, index=search_index, fetch=fake_fetch,
    )
    assert [s.status for s in result.sources] == ["read", "read", "failed"]
    s = result.summary
    assert s["total"] == s["covered"] + s["partial"] + s["missing"] and s["total"] >= 3
    assert result.findings[0].status == "missing"  # missing first
    covered = [f for f in result.findings if f.status == "covered"]
    assert covered and all(f.evidence for f in covered)


def test_run_benchmark_no_readable_sources(embedder, search_index):
    with pytest.raises(BenchmarkError):
        run_benchmark(filename="d", document_id="d1", workspace_id="1", urls=["https://bad.edu/"],
                      benchmarker=FakeBenchmarker(), embedder=embedder, index=search_index, fetch=fake_fetch)


class StubSearch(WebSearch):
    def search(self, query, max_results=8):
        return [WebResult("T", "https://a.edu/p", "s"), WebResult("T2", "https://a.edu/p", "dup")]


def _indexed_doc(client, name="attendance_policy.docx"):
    data = make_docx(["Students must meet attendance requirements each semester."] * 3)
    doc = client.post("/documents/upload", files={"file": (name, data)}).json()
    client.post(f"/documents/{doc['id']}/process")
    return doc


def test_api_flow(client, monkeypatch):
    import app.benchmark_api as api

    app.dependency_overrides[get_web_search] = lambda: StubSearch()
    app.dependency_overrides[get_benchmarker] = lambda: FakeBenchmarker()
    monkeypatch.setattr(api, "run_benchmark", lambda **kw: __import__("app.benchmark", fromlist=["x"]).run_benchmark(**kw, fetch=fake_fetch))
    doc = _indexed_doc(client)

    r = client.post("/benchmark/candidates", json={"document_id": doc["id"]})
    assert r.status_code == 200 and len(r.json()["candidates"]) == 1  # duplicate removed
    assert r.json()["candidates"][0]["domain"] == "a.edu"

    r = client.post("/benchmark/run", json={"document_id": doc["id"], "urls": ["https://a.edu/p"]})
    assert r.status_code == 409  # not indexed yet

    assert client.post(f"/documents/{doc['id']}/index").status_code == 200
    r = client.post("/benchmark/run", json={"document_id": doc["id"], "urls": ["https://a.edu/p", "https://b.edu/p"]})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["summary"]["total"] == len(body["items"]) and body["sources"][0]["status"] == "read"
    assert all(p["url"].startswith("https://") for i in body["items"] for p in i["peers"])

    r = client.post("/benchmark/run", json={"document_id": doc["id"], "urls": ["https://bad.edu/x"]})
    assert r.status_code == 422


def test_api_limits_and_ownership(client):
    app.dependency_overrides[get_benchmarker] = lambda: FakeBenchmarker()
    assert client.post("/benchmark/candidates", json={"document_id": "nope"}).status_code == 404
    assert client.post("/benchmark/run", json={"document_id": "nope", "urls": ["https://a.edu"]}).status_code == 404
    assert client.post("/benchmark/run", json={"document_id": "nope", "urls": []}).status_code == 422
    doc = _indexed_doc(client)
    client.post(f"/documents/{doc['id']}/index")
    urls = [f"https://s{n}.edu/p" for n in range(5)]
    assert client.post("/benchmark/run", json={"document_id": doc["id"], "urls": urls}).status_code == 422


class FakeChat:
    """Stands in for the OpenAI client: returns a prepared JSON string."""

    def __init__(self, content):
        self.chat = self
        self.completions = self
        self._content = content

    def create(self, **kw):
        from types import SimpleNamespace as N
        return N(choices=[N(finish_reason="stop", message=N(content=self._content))])


def test_azure_benchmarker_parses_and_rejects_garbage():
    ok = AzureOpenAIBenchmarker("https://x", "k", "gpt", client=FakeChat('{"topic":"t","queries":["q"]}'))
    assert ok.search_plan("f.docx", "text").queries == ["q"]
    bad = AzureOpenAIBenchmarker("https://x", "k", "gpt", client=FakeChat("not json"))
    with pytest.raises(BenchmarkError):
        bad.search_plan("f.docx", "text")
