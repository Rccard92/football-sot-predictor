"""Utilità gruppi kickoff atomici per Historical Scan V4."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Iterable, TypeVar

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models.cecchino_lab_historical_market_result import CecchinoLabHistoricalMarketResult
from app.models.cecchino_lab_historical_match_snapshot import CecchinoLabHistoricalMatchSnapshot

T = TypeVar("T")


def kickoff_group_token(kickoff_at: datetime | None, lab_match_id: int) -> str:
    if kickoff_at is not None:
        return kickoff_at.isoformat()
    return f"__kickoff_none__:{int(lab_match_id)}"


def group_work_by_kickoff(
    items: list[T],
    *,
    kickoff_at_getter: Any,
) -> list[list[T]]:
    if not items:
        return []
    groups: list[list[T]] = []
    current_ko = kickoff_at_getter(items[0])
    current: list[T] = []
    for it in items:
        ko = kickoff_at_getter(it)
        if current and ko != current_ko:
            groups.append(current)
            current = []
            current_ko = ko
        current.append(it)
    if current:
        groups.append(current)
    return groups


def expected_lab_match_ids_for_kickoff(
    all_work: list[tuple[Any, ...]],
    kickoff_at: datetime | None,
) -> set[int]:
    return {int(row[0].id) for row in all_work if row[0].kickoff_at == kickoff_at}


def snapshot_ids_grouped_by_kickoff(
    db: Session,
    *,
    run_id: int,
) -> dict[str, set[int]]:
    rows = db.execute(
        select(
            CecchinoLabHistoricalMatchSnapshot.kickoff_at,
            CecchinoLabHistoricalMatchSnapshot.lab_match_id,
        ).where(CecchinoLabHistoricalMatchSnapshot.run_id == run_id)
    ).all()
    grouped: dict[str, set[int]] = {}
    for kickoff_at, lab_match_id in rows:
        token = kickoff_group_token(kickoff_at, int(lab_match_id))
        grouped.setdefault(token, set()).add(int(lab_match_id))
    return grouped


def classify_kickoff_groups(
    all_work: list[tuple[Any, ...]],
    snapshot_by_kickoff: dict[str, set[int]],
) -> tuple[set[int], set[int]]:
    """Restituisce (complete_done_ids, partial_lab_match_ids)."""
    complete: set[int] = set()
    partial: set[int] = set()
    work_groups = group_work_by_kickoff(all_work, kickoff_at_getter=lambda row: row[0].kickoff_at)
    for group in work_groups:
        kickoff_at = group[0][0].kickoff_at
        token = kickoff_group_token(kickoff_at, int(group[0][0].id))
        expected = {int(row[0].id) for row in group}
        persisted = snapshot_by_kickoff.get(token, set())
        if not persisted:
            continue
        if persisted == expected:
            complete.update(expected)
        else:
            partial.update(persisted)
    return complete, partial


def purge_partial_kickoff_snapshots(
    db: Session,
    *,
    run_id: int,
    partial_lab_match_ids: Iterable[int],
) -> int:
    ids = [int(x) for x in partial_lab_match_ids]
    if not ids:
        return 0
    db.execute(
        delete(CecchinoLabHistoricalMarketResult).where(
            CecchinoLabHistoricalMarketResult.run_id == run_id,
            CecchinoLabHistoricalMarketResult.lab_match_id.in_(ids),
        )
    )
    result = db.execute(
        delete(CecchinoLabHistoricalMatchSnapshot).where(
            CecchinoLabHistoricalMatchSnapshot.run_id == run_id,
            CecchinoLabHistoricalMatchSnapshot.lab_match_id.in_(ids),
        )
    )
    return int(result.rowcount or 0)


def recompute_run_counters_from_snapshots(db: Session, *, run_id: int) -> dict[str, int]:
    rows = list(
        db.scalars(
            select(CecchinoLabHistoricalMatchSnapshot).where(
                CecchinoLabHistoricalMatchSnapshot.run_id == run_id
            )
        ).all()
    )
    processed = len(rows)
    eligible = sum(1 for s in rows if s.historical_eligibility_status == "eligible_core")
    excluded = sum(
        1
        for s in rows
        if s.historical_eligibility_status not in ("eligible_core", "error")
    )
    errors = sum(1 for s in rows if s.historical_eligibility_status == "error")
    max_order = max((int(s.chronological_order or 0) for s in rows), default=-1)
    return {
        "matches_processed": processed,
        "matches_eligible_core": eligible,
        "matches_excluded": excluded,
        "matches_error": errors,
        "next_chronological_order": max_order + 1 if rows else 0,
    }
