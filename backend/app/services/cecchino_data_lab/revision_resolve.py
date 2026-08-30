"""Risoluzione revisione codice per Lab storico (scan + report generator).

Nessuna scrittura DB. Nessuna dipendenza da Cecchino Today.
"""

from __future__ import annotations

import os
import subprocess
from typing import Any


# Platform revision first — evita che un GIT_COMMIT_SHA stale mascheri Railway.
_ENV_CHAIN: tuple[tuple[str, str], ...] = (
    ("RAILWAY_GIT_COMMIT_SHA", "RAILWAY_GIT_COMMIT_SHA"),
    ("VERCEL_GIT_COMMIT_SHA", "VERCEL_GIT_COMMIT_SHA"),
    ("GIT_COMMIT_SHA", "GIT_COMMIT_SHA"),
    ("SOURCE_VERSION", "SOURCE_VERSION"),
)


def _collect_env_revisions() -> list[tuple[str, str]]:
    """Elenca (source, sha) per ogni env non vuota, in ordine di precedence."""
    found: list[tuple[str, str]] = []
    for env_key, source in _ENV_CHAIN:
        raw = (os.environ.get(env_key) or "").strip()
        if raw:
            found.append((source, raw[:64]))
    return found


def resolve_code_revision() -> dict[str, Any]:
    """Risolve revisione codice: platform deploy, poi override manuale, poi git locale.

    Precedence:
    ``RAILWAY_GIT_COMMIT_SHA`` → ``VERCEL_GIT_COMMIT_SHA`` → ``GIT_COMMIT_SHA`` →
    ``SOURCE_VERSION`` → ``git rev-parse HEAD`` → unknown.

    Se più fonti env espongono SHA differenti, la prima (autorevole) vince, ma
    ``revision_conflict=True`` e ``revision_conflict_sources`` espongono la discordanza.

    Ritorna:
    - git_commit
    - git_commit_source
    - revision_status (``resolved`` | ``unknown``)
    - revision_conflict (bool)
    - revision_conflict_sources (dict source→sha | None)
    """
    env_found = _collect_env_revisions()
    conflict = False
    conflict_sources: dict[str, str] | None = None
    if env_found:
        unique_shas = {sha for _, sha in env_found}
        if len(unique_shas) > 1:
            conflict = True
            conflict_sources = {source: sha for source, sha in env_found}
        winner_source, winner_sha = env_found[0]
        return {
            "git_commit": winner_sha,
            "git_commit_source": winner_source,
            "revision_status": "resolved",
            "revision_conflict": conflict,
            "revision_conflict_sources": conflict_sources,
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
                "revision_conflict": False,
                "revision_conflict_sources": None,
            }
    except Exception:
        pass
    return {
        "git_commit": None,
        "git_commit_source": None,
        "revision_status": "unknown",
        "revision_conflict": False,
        "revision_conflict_sources": None,
    }


def revision_as_source_fields(rev: dict[str, Any] | None = None) -> dict[str, Any]:
    """Alias legacy source_* usati dallo scan run."""
    r = rev or resolve_code_revision()
    return {
        "source_git_commit": r.get("git_commit"),
        "source_git_commit_source": r.get("git_commit_source"),
        "source_revision_status": r.get("revision_status"),
    }
