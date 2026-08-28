"""Ordinamento e identità stabili V4-only — nessun effetto su V3 legacy."""

from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Any

from app.models.cecchino_lab_match import CecchinoLabMatch


def stable_competition_id_v4(name: str) -> int:
    """ID competizione stabile tra processi (SHA-1, non Python hash())."""
    h = hashlib.sha1(name.strip().lower().encode("utf-8")).hexdigest()
    return int(h[:9], 16) % (10**9) + 1


def match_sort_key_v4(
    m: CecchinoLabMatch,
    *,
    competition_name: str,
    dataset_id: int,
) -> tuple:
    """Sort key globale V4 — tie-break esplicito cross-campionato."""
    return (
        m.kickoff_at is None,
        m.kickoff_at or datetime.min,
        m.match_date is None,
        m.match_date or datetime.min.date(),
        m.match_time is None,
        str(m.match_time) if m.match_time else "",
        str(competition_name or ""),
        int(dataset_id or 0),
        int(m.source_row_number or 0),
        int(m.id),
    )


def global_sort_key_v4(item: tuple[CecchinoLabMatch, str, Any, Any]) -> tuple:
    m, comp, dataset, _ = item
    return match_sort_key_v4(
        m,
        competition_name=str(comp),
        dataset_id=int(dataset.id) if dataset is not None else int(m.dataset_id or 0),
    )
