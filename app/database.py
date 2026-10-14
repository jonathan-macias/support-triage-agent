from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends
from sqlmodel import Session, SQLModel, create_engine

from app.config import settings

engine = create_engine(settings.database_url)


def create_db_and_tables() -> None:
    # Importing the models registers their tables in SQLModel.metadata.
    from app import models  # noqa: F401

    SQLModel.metadata.create_all(engine)


def get_session() -> Iterator[Session]:
    """One session per request, closed when the response is done."""
    with Session(engine) as session:
        yield session


SessionDep = Annotated[Session, Depends(get_session)]
