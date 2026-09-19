"""Fixture comuni ai test V4: DATABASE_URL fasulla prima di importare l'app, sessione SQLite con le sole tabelle V4."""

from __future__ import annotations

import os

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("API_FOOTBALL_KEY", "test-key")

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.models import Base
from app.models.cecchino_v4 import V4_TABLES


@pytest.fixture()
def v4_engine():
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine, tables=list(V4_TABLES))
    yield engine
    engine.dispose()


@pytest.fixture()
def v4_db(v4_engine) -> Session:
    factory = sessionmaker(bind=v4_engine, autocommit=False, autoflush=False, expire_on_commit=False)
    db = factory()
    try:
        yield db
    finally:
        db.close()
