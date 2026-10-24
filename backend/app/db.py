from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings


class Base(DeclarativeBase):
    pass


def make_engine(url: str):
    # SQLite needs this flag because FastAPI serves requests from several threads
    kwargs = {"connect_args": {"check_same_thread": False}} if url.startswith("sqlite") else {}
    return create_engine(url, **kwargs)


engine = make_engine(settings.database_url)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db(bind=None) -> None:
    """Create the tables and seed the starting data (roles and one workspace)."""
    from app import models  # imported here so the tables are registered on Base

    bind = bind or engine
    Base.metadata.create_all(bind)
    with Session(bind) as session:
        if session.scalar(select(func.count()).select_from(models.Role)) == 0:
            session.add_all([models.Role(name="admin"), models.Role(name="viewer")])
        if session.scalar(select(func.count()).select_from(models.Workspace)) == 0:
            session.add(models.Workspace(name="Default"))
        session.commit()
