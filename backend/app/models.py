from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, String, Unicode
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

# Text that can hold anything a person types (Arabic included) uses Unicode types.
# On SQL Server a plain String becomes VARCHAR, which turns Arabic letters into "?".
# Identifiers that are always plain ASCII (hex ids, status words) stay as String.


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Role(Base):
    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(50), unique=True)  # admin, viewer


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    # The user's id in Microsoft Entra External ID, filled in once login exists
    external_id: Mapped[str | None] = mapped_column(String(64), unique=True)
    email: Mapped[str] = mapped_column(Unicode(255), unique=True)
    display_name: Mapped[str | None] = mapped_column(Unicode(255))
    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    role: Mapped[Role] = relationship()


class Workspace(Base):
    __tablename__ = "workspaces"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(Unicode(100))
    # The user this workspace belongs to; empty for the shared starter workspace
    owner_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)  # random hex id
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id"))
    filename: Mapped[str] = mapped_column(Unicode(255))
    blob_name: Mapped[str] = mapped_column(String(512))
    content_type: Mapped[str] = mapped_column(String(255))
    size_bytes: Mapped[int]
    # uploaded -> processing -> extracted -> indexed, or needs_ocr / failed
    status: Mapped[str] = mapped_column(String(20), default="uploaded")
    status_detail: Mapped[str | None] = mapped_column(Unicode(500))  # why it failed
    uploaded_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class DocumentSegment(Base):
    """Text extracted from a document, one row per page, slide or sheet."""

    __tablename__ = "document_segments"

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id"), index=True)
    number: Mapped[int]
    label: Mapped[str] = mapped_column(Unicode(255))
    text: Mapped[str] = mapped_column(Unicode())  # NVARCHAR(max) on SQL Server
    source: Mapped[str] = mapped_column(String(10))  # "text" or "ocr"
