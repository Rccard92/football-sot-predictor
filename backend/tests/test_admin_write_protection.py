"""Guardia (20/10/2026): ogni rotta /api/admin che scrive e' protetta dalla sessione admin."""

from __future__ import annotations

import os

os.environ.setdefault("DATABASE_URL", "postgresql://user:pass@localhost:5432/test")

from fastapi.routing import APIRoute

from app.core.admin_session import require_admin_session, require_admin_session_for_writes
from app.main import app

WRITE = {"POST", "PUT", "PATCH", "DELETE"}
OPEN = ("/api/admin/auth/",)  # login, stato e logout restano aperti


def _deps(route: APIRoute) -> set:
    found = set()
    stack = list(route.dependant.dependencies)
    while stack:
        d = stack.pop()
        if d.call is not None:
            found.add(d.call)
        stack.extend(d.dependencies)
    return found


def test_every_admin_write_route_requires_the_session():
    missing = []
    for route in app.routes:
        if not isinstance(route, APIRoute) or not route.path.startswith("/api/admin"):
            continue
        if route.path.startswith(OPEN) or not (set(route.methods) & WRITE):
            continue
        deps = _deps(route)
        if require_admin_session not in deps and require_admin_session_for_writes not in deps:
            missing.append(f"{sorted(route.methods)} {route.path}")
    assert missing == []


def test_write_dependency_lets_reads_through():
    class _Req:
        method = "GET"

    assert require_admin_session_for_writes(_Req(), settings=None) is None
