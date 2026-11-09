"""Endpoints for benchmarking an uploaded document against pages found on the web."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import Caller, get_caller
from app.benchmark import Benchmarker, BenchmarkError, get_benchmarker, run_benchmark
from app.config import settings
from app.db import get_db
from app.embeddings import Embedder, EmbeddingError, get_embedder
from app.models import Document, DocumentSegment
from app.search_index import SearchIndex, SearchIndexError, get_search_index
from app.web_search import WebSearch, WebSearchError, get_web_search

router = APIRouter(prefix="/benchmark", tags=["benchmark"])


def _owned_document(db: Session, caller: Caller, document_id: str) -> Document:
    document = db.get(Document, document_id)
    if document is None or document.workspace_id != caller.workspace.id:
        raise HTTPException(status_code=404, detail="Document not found.")
    return document


class CandidatesRequest(BaseModel):
    document_id: str


class CandidateOut(BaseModel):
    title: str
    url: str
    domain: str
    snippet: str


class CandidatesOut(BaseModel):
    topic: str
    queries: list[str]
    candidates: list[CandidateOut]


@router.post("/candidates", response_model=CandidatesOut)
def candidates(
    request: CandidatesRequest,
    caller: Caller = Depends(get_caller),
    db: Session = Depends(get_db),
    benchmarker: Benchmarker = Depends(get_benchmarker),
    search: WebSearch = Depends(get_web_search),
):
    """Suggest similar documents from the web. The user reviews them before anything is compared."""
    document = _owned_document(db, caller, request.document_id)
    if document.status not in ("extracted", "indexed"):
        raise HTTPException(status_code=409, detail="Extract the document's text first.")
    segments = db.scalars(
        select(DocumentSegment)
        .where(DocumentSegment.document_id == document.id)
        .order_by(DocumentSegment.number)
    ).all()
    text = "\n".join(s.text for s in segments)[:3000]
    try:
        plan = benchmarker.search_plan(document.filename, text)
        seen, found = set(), []
        for query in plan.queries:
            for result in search.search(query, 8):
                if result.url not in seen:
                    seen.add(result.url)
                    found.append(result)
    except (BenchmarkError, WebSearchError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return CandidatesOut(
        topic=plan.topic,
        queries=plan.queries,
        candidates=[
            CandidateOut(title=r.title, url=r.url, domain=r.domain, snippet=r.snippet) for r in found[:8]
        ],
    )


class RunRequest(BaseModel):
    document_id: str
    urls: list[str] = Field(min_length=1, max_length=10)


class EvidenceOut(BaseModel):
    page_number: int
    label: str
    content: str


class PeerOut(BaseModel):
    source: int
    title: str
    url: str
    page: int | None


class ItemOut(BaseModel):
    topic: str
    status: str
    expected: str
    gap: str
    suggested_edit: str
    your_evidence: list[EvidenceOut]
    peers: list[PeerOut]


class SourceOut(BaseModel):
    number: int
    title: str
    url: str
    status: str
    detail: str | None
    truncated: bool


class RunOut(BaseModel):
    summary: dict[str, int]
    items: list[ItemOut]
    sources: list[SourceOut]


@router.post("/run", response_model=RunOut)
def run(
    request: RunRequest,
    caller: Caller = Depends(get_caller),
    db: Session = Depends(get_db),
    benchmarker: Benchmarker = Depends(get_benchmarker),
    embedder: Embedder = Depends(get_embedder),
    index: SearchIndex = Depends(get_search_index),
):
    """Compare the document with the chosen pages and list what is missing or weak."""
    document = _owned_document(db, caller, request.document_id)
    if document.status != "indexed":
        raise HTTPException(status_code=409, detail="Index the document first.")
    urls = []
    for url in request.urls:
        url = url.strip()
        if not url or len(url) > 2000:
            raise HTTPException(status_code=422, detail="Each address must be 1 to 2000 characters.")
        if url not in urls:
            urls.append(url)
    if len(urls) > settings.benchmark_max_sources:
        raise HTTPException(
            status_code=422, detail=f"Choose at most {settings.benchmark_max_sources} sources."
        )
    try:
        result = run_benchmark(
            filename=document.filename,
            document_id=document.id,
            workspace_id=str(caller.workspace.id),
            urls=urls,
            benchmarker=benchmarker,
            embedder=embedder,
            index=index,
        )
    except BenchmarkError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except (EmbeddingError, SearchIndexError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    by_number = {s.number: s for s in result.sources}
    return RunOut(
        summary=result.summary,
        items=[
            ItemOut(
                topic=f.topic, status=f.status, expected=f.expected, gap=f.gap,
                suggested_edit=f.suggested_edit,
                your_evidence=[EvidenceOut(page_number=e.page_number, label=e.label, content=e.content) for e in f.evidence],
                peers=[
                    PeerOut(source=p.source, title=by_number[p.source].title, url=by_number[p.source].url, page=p.page)
                    for p in f.peers if p.source in by_number
                ],
            )
            for f in result.findings
        ],
        sources=[
            SourceOut(number=s.number, title=s.title, url=s.url, status=s.status, detail=s.detail, truncated=s.truncated)
            for s in result.sources
        ],
    )
