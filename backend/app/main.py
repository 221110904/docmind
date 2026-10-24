from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import PurePosixPath
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException, UploadFile
from pydantic import BaseModel, ConfigDict, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.db import engine, get_db, init_db
from app.models import Document, Workspace
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
