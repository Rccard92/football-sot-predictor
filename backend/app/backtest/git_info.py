"""Lettura git commit da env (deploy) — nessuna dipendenza git CLI."""

from __future__ import annotations

import os

_ENV_KEYS = ("GIT_COMMIT_SHA", "RAILWAY_GIT_COMMIT_SHA", "VERCEL_GIT_COMMIT_SHA")


def resolve_git_commit_sha() -> str | None:
    for key in _ENV_KEYS:
        value = (os.environ.get(key) or "").strip()
        if value:
            return value[:64]
    return None
