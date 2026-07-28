"""Risoluzione revisione codice per Lab storico (scan + report generator).

Nessuna scrittura DB. Nessuna dipendenza da Cecchino Today.
"""

from __future__ import annotations

import os
import subprocess
from typing import Any


def resolve_code_revision() -> dict[str, str | None]:
    """Risolve revisione codice: env Railway/CI prima, poi git locale.

    Ritorna chiavi neutre:
    - git_commit
    - git_commit_source
    - revision_status
    """
    env_chain = (
        ("RAILWAY_GIT_COMMIT_SHA", "RAILWAY_GIT_COMMIT_SHA"),
        ("SOURCE_VERSION", "SOURCE_VERSION"),
        ("GIT_COMMIT_SHA", "GIT_COMMIT_SHA"),
        ("VERCEL_GIT_COMMIT_SHA", "VERCEL_GIT_COMMIT_SHA"),
    )
    for env_key, source in env_chain:
        raw = (os.environ.get(env_key) or "").strip()
        if raw:
            return {
                "git_commit": raw[:64],
                "git_commit_source": source,
                "revision_status": "resolved",
            }
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=5,
        )
        sha = (out or "").strip()
        if sha:
            return {
                "git_commit": sha[:64],
                "git_commit_source": "git_rev_parse",
                "revision_status": "resolved",
            }
    except Exception:
        pass
    return {
        "git_commit": None,
        "git_commit_source": None,
        "revision_status": "unknown",
    }


def revision_as_source_fields(rev: dict[str, Any] | None = None) -> dict[str, str | None]:
    """Alias legacy source_* usati dallo scan run."""
    r = rev or resolve_code_revision()
    return {
        "source_git_commit": r.get("git_commit"),
        "source_git_commit_source": r.get("git_commit_source"),
        "source_revision_status": r.get("revision_status"),
    }
