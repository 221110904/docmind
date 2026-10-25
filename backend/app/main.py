from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import PurePosixPath
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException, UploadFile
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.chunking import chunk_segments
from app.config import settings
from app.db import engine, get_db, init_db
from app.embeddings import Embedder, EmbeddingError, get_embedder
from app.extraction import ExtractionError, extract
from app.models import Document, DocumentSegment, Workspace
from app.ocr import OcrEngine, OcrError, OcrUnavailable, Segment, get_ocr
from app.search_index import IndexedChunk, SearchIndex, SearchIndexError, get_search_index
from app.storage import Storage, get_storage

ALLOWED_EXTENSIONS = {".pdf", ".docx", ".pptx", ".xlsx", ".png", ".jpg", ".jpeg"}


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db(engine)
    yield


app = FastAPI(title="DocMind API", version="0.2.0", lifespan=lifespan)


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


@app.get("/health")
def health():
    return {"status": "ok", "service": "docmind-api"}


@app.post("/documents/upload", status_code=201, response_model=DocumentOut)
def upload_document(
    file: UploadFile,
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

    workspace = db.scalars(select(Workspace).order_by(Workspace.id)).first()
    if workspace is None:
        raise HTTPException(status_code=500, detail="No workspace configured.")

    document_id = uuid4().hex
    blob_name = f"{document_id}/{safe_name}"
    content_type = file.content_type or "application/octet-stream"
    storage.save(blob_name, data, content_type)

    document = Document(
        id=document_id,
        workspace_id=workspace.id,
        filename=safe_name,
        blob_name=blob_name,
        content_type=content_type,
        size_bytes=len(data),
    )
    db.add(document)
    db.commit()
    return document


@app.get("/documents", response_model=list[DocumentOut])
def list_documents(db: Session = Depends(get_db)):
    return db.scalars(select(Document).order_by(Document.created_at.desc())).all()


@app.get("/documents/{document_id}", response_model=DocumentOut)
def get_document(document_id: str, db: Session = Depends(get_db)):
    document = db.get(Document, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found.")
    return document


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
    storage: Storage = Depends(get_storage),
    ocr: OcrEngine = Depends(get_ocr),
    index: SearchIndex = Depends(get_search_index),
    db: Session = Depends(get_db),
):
    """Extract the text of an uploaded document (OCR is used for scans and images)."""
    document = db.get(Document, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found.")

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
def get_document_text(document_id: str, db: Session = Depends(get_db)):
    if db.get(Document, document_id) is None:
        raise HTTPException(status_code=404, detail="Document not found.")
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
    embedder: Embedder = Depends(get_embedder),
    index: SearchIndex = Depends(get_search_index),
    db: Session = Depends(get_db),
):
    """Split the extracted text into chunks, embed them, and store them for search."""
    document = db.get(Document, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found.")
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
    embedder: Embedder = Depends(get_embedder),
    index: SearchIndex = Depends(get_search_index),
    db: Session = Depends(get_db),
):
    """Hybrid search (keywords and meaning) over everything indexed in the workspace."""
    workspace = db.scalars(select(Workspace).order_by(Workspace.id)).first()
    if workspace is None:
        raise HTTPException(status_code=500, detail="No workspace configured.")
    try:
        vector = embedder.embed([request.query])[0]
        hits = index.search(
            request.query, vector, request.top_k,
            workspace_id=str(workspace.id), document_id=request.document_id,
        )
    except (EmbeddingError, SearchIndexError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return [SearchHitOut(**{k: getattr(h, k) for k in SearchHitOut.model_fields}) for h in hits]
