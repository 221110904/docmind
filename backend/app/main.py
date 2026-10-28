from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import PurePosixPath
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.auth import Caller, get_caller
from app.chunking import chunk_segments
from app.config import settings
from app.db import engine, get_db, init_db
from app.embeddings import Embedder, EmbeddingError, get_embedder
from app.extraction import ExtractionError, extract
from app.models import Document, DocumentSegment
from app.ocr import OcrEngine, OcrError, OcrUnavailable, Segment, get_ocr
from app.qa import NOT_FOUND, Answerer, Passage, QaError, get_answerer
from app.search_index import IndexedChunk, SearchIndex, SearchIndexError, get_search_index
from app.storage import Storage, get_storage

ALLOWED_EXTENSIONS = {".pdf", ".docx", ".pptx", ".xlsx", ".png", ".jpg", ".jpeg"}


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db(engine)
    yield


app = FastAPI(title="DocMind API", version="0.3.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
    allow_methods=["*"],
    allow_headers=["*"],
)


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    filename: str
    blob_name: str
    content_type: str
    size_bytes: int
    status: str
    status_detail: str | None = None
    created_at: datetime

    @field_validator("created_at")
    @classmethod
    def _as_utc(cls, value: datetime) -> datetime:
        # SQLite drops timezone info; every timestamp we store is UTC
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def owned_document(db: Session, caller: Caller, document_id: str) -> Document:
    """The caller's document, or a 404. Someone else's document looks exactly like a missing one."""
    document = db.get(Document, document_id)
    if document is None or document.workspace_id != caller.workspace.id:
        raise HTTPException(status_code=404, detail="Document not found.")
    return document


@app.get("/health")
def health():
    return {"status": "ok", "service": "docmind-api"}


class MeOut(BaseModel):
    email: str
    name: str | None


@app.get("/me", response_model=MeOut)
def me(caller: Caller = Depends(get_caller)):
    """Who the API thinks you are. Handy for checking that sign-in works."""
    return MeOut(email=caller.user.email, name=caller.user.display_name)


@app.post("/documents/upload", status_code=201, response_model=DocumentOut)
def upload_document(
    file: UploadFile,
    caller: Caller = Depends(get_caller),
    storage: Storage = Depends(get_storage),
    db: Session = Depends(get_db),
):
    # Keep only the file name: drop any folder parts the client sent
    safe_name = PurePosixPath((file.filename or "").replace("\\", "/")).name
    ext = PurePosixPath(safe_name).suffix.lower()
    if not safe_name or ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type. Allowed: {sorted(ALLOWED_EXTENSIONS)}",
        )

    max_bytes = settings.max_upload_mb * 1024 * 1024
    data = file.file.read(max_bytes + 1)  # one byte past the limit detects oversize
    if len(data) > max_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"File too large (limit is {settings.max_upload_mb} MB).",
        )
    if not data:
        raise HTTPException(status_code=400, detail="File is empty.")

    document_id = uuid4().hex
    blob_name = f"{document_id}/{safe_name}"
    content_type = file.content_type or "application/octet-stream"
    storage.save(blob_name, data, content_type)

    document = Document(
        id=document_id,
        workspace_id=caller.workspace.id,
        filename=safe_name,
        blob_name=blob_name,
        content_type=content_type,
        size_bytes=len(data),
        uploaded_by=caller.user.id,
    )
    db.add(document)
    db.commit()
    return document


@app.get("/documents", response_model=list[DocumentOut])
def list_documents(caller: Caller = Depends(get_caller), db: Session = Depends(get_db)):
    return db.scalars(
        select(Document)
        .where(Document.workspace_id == caller.workspace.id)
        .order_by(Document.created_at.desc())
    ).all()


@app.get("/documents/{document_id}", response_model=DocumentOut)
def get_document(
    document_id: str, caller: Caller = Depends(get_caller), db: Session = Depends(get_db)
):
    return owned_document(db, caller, document_id)


class SegmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    number: int
    label: str
    text: str
    source: str


class ProcessOut(BaseModel):
    id: str
    status: str
    status_detail: str | None
    segment_count: int


@app.post("/documents/{document_id}/process", response_model=ProcessOut)
def process_document(
    document_id: str,
    caller: Caller = Depends(get_caller),
    storage: Storage = Depends(get_storage),
    ocr: OcrEngine = Depends(get_ocr),
    index: SearchIndex = Depends(get_search_index),
    db: Session = Depends(get_db),
):
    """Extract the text of an uploaded document (OCR is used for scans and images)."""
    document = owned_document(db, caller, document_id)

    if document.status == "indexed":
        # The old text is about to be replaced, so its search entries must go too
        try:
            index.delete_document(document_id)
        except SearchIndexError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

    document.status, document.status_detail = "processing", None
    db.commit()

    # Processing again replaces any earlier result
    db.execute(delete(DocumentSegment).where(DocumentSegment.document_id == document_id))

    try:
        segments = extract(storage.read(document.blob_name), document.filename, ocr)
    except OcrUnavailable:
        document.status = "needs_ocr"
        document.status_detail = "This file needs OCR, which is not configured yet."
        segments = []
    except (ExtractionError, OcrError) as exc:
        document.status, document.status_detail = "failed", str(exc)[:500]
        segments = []
    else:
        document.status = "extracted"
        db.add_all(
            DocumentSegment(
                document_id=document_id,
                number=s.number,
                label=s.label,
                text=s.text,
                source=s.source,
            )
            for s in segments
        )
    db.commit()
    return ProcessOut(
        id=document_id,
        status=document.status,
        status_detail=document.status_detail,
        segment_count=len(segments),
    )


@app.get("/documents/{document_id}/text", response_model=list[SegmentOut])
def get_document_text(
    document_id: str, caller: Caller = Depends(get_caller), db: Session = Depends(get_db)
):
    owned_document(db, caller, document_id)
    return db.scalars(
        select(DocumentSegment)
        .where(DocumentSegment.document_id == document_id)
        .order_by(DocumentSegment.number)
    ).all()


class IndexOut(BaseModel):
    id: str
    status: str
    chunk_count: int


@app.post("/documents/{document_id}/index", response_model=IndexOut)
def index_document(
    document_id: str,
    caller: Caller = Depends(get_caller),
    embedder: Embedder = Depends(get_embedder),
    index: SearchIndex = Depends(get_search_index),
    db: Session = Depends(get_db),
):
    """Split the extracted text into chunks, embed them, and store them for search."""
    document = owned_document(db, caller, document_id)
    segments = db.scalars(
        select(DocumentSegment)
        .where(DocumentSegment.document_id == document_id)
        .order_by(DocumentSegment.number)
    ).all()
    if document.status not in ("extracted", "indexed") or not segments:
        raise HTTPException(
            status_code=409,
            detail="Extract the document's text first (POST /documents/{id}/process).",
        )

    chunks = chunk_segments(
        [Segment(s.number, s.label, s.text, s.source) for s in segments],
        settings.chunk_chars,
        settings.chunk_overlap_chars,
    )
    try:
        vectors = embedder.embed([c.text for c in chunks])
        index.replace_document(
            document_id,
            [
                IndexedChunk(
                    id=f"{document_id}-{c.index}",
                    document_id=document_id,
                    workspace_id=str(document.workspace_id),
                    filename=document.filename,
                    label=c.label,
                    page_number=c.segment_number,
                    chunk_index=c.index,
                    content=c.text,
                    vector=vector,
                )
                for c, vector in zip(chunks, vectors)
            ],
        )
    except (EmbeddingError, SearchIndexError) as exc:
        document.status_detail = f"Indexing failed: {exc}"[:500]
        db.commit()
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    document.status, document.status_detail = "indexed", None
    db.commit()
    return IndexOut(id=document_id, status=document.status, chunk_count=len(chunks))


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=1000)
    top_k: int = Field(default=5, ge=1, le=20)
    document_id: str | None = None


class SearchHitOut(BaseModel):
    document_id: str
    filename: str
    label: str
    page_number: int
    chunk_index: int
    content: str
    score: float


@app.post("/search", response_model=list[SearchHitOut])
def search(
    request: SearchRequest,
    caller: Caller = Depends(get_caller),
    embedder: Embedder = Depends(get_embedder),
    index: SearchIndex = Depends(get_search_index),
):
    """Hybrid search (keywords and meaning) over the caller's indexed documents."""
    try:
        vector = embedder.embed([request.query])[0]
        hits = index.search(
            request.query, vector, request.top_k,
            workspace_id=str(caller.workspace.id), document_id=request.document_id,
        )
    except (EmbeddingError, SearchIndexError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return [SearchHitOut(**{k: getattr(h, k) for k in SearchHitOut.model_fields}) for h in hits]


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=1000)
    top_k: int = Field(default=5, ge=1, le=10)
    document_id: str | None = None


class SourceOut(BaseModel):
    number: int
    document_id: str
    filename: str
    label: str
    page_number: int
    chunk_index: int
    content: str


class AskOut(BaseModel):
    answer: str
    found: bool
    sources: list[SourceOut]


@app.post("/ask", response_model=AskOut)
def ask(
    request: AskRequest,
    caller: Caller = Depends(get_caller),
    embedder: Embedder = Depends(get_embedder),
    index: SearchIndex = Depends(get_search_index),
    answerer: Answerer = Depends(get_answerer),
):
    """Answer a question from the caller's indexed documents, citing the sources used."""
    try:
        vector = embedder.embed([request.question])[0]
        hits = index.search(
            request.question, vector, request.top_k,
            workspace_id=str(caller.workspace.id), document_id=request.document_id,
        )
        if not hits:
            return AskOut(answer=NOT_FOUND, found=False, sources=[])
        passages = [
            Passage(
                number=n, document_id=h.document_id, filename=h.filename, label=h.label,
                page_number=h.page_number, chunk_index=h.chunk_index, content=h.content,
            )
            for n, h in enumerate(hits, start=1)
        ]
        result = answerer.answer(request.question, passages)
    except (EmbeddingError, SearchIndexError, QaError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    by_number = {p.number: p for p in passages}
    sources = [SourceOut(**vars(by_number[n])) for n in result.cited]
    return AskOut(answer=result.text, found=result.found, sources=sources)


@app.delete("/documents/{document_id}", status_code=204)
def delete_document(
    document_id: str,
    caller: Caller = Depends(get_caller),
    storage: Storage = Depends(get_storage),
    index: SearchIndex = Depends(get_search_index),
    db: Session = Depends(get_db),
):
    """Remove a document: its search entries, its stored file and its extracted text."""
    document = owned_document(db, caller, document_id)
    # Outside services go first. If one fails, the document stays listed and can be retried.
    try:
        index.delete_document(document_id)
    except SearchIndexError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    try:
        storage.delete(document.blob_name)
    except Exception as exc:
        raise HTTPException(
            status_code=502, detail=f"Could not delete the stored file: {exc}"[:300]
        ) from exc
    db.execute(delete(DocumentSegment).where(DocumentSegment.document_id == document_id))
    db.delete(document)
    db.commit()
