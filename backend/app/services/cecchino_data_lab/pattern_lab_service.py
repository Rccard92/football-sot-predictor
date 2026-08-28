"""Orchestrazione Pattern Lab — query multi-run streaming READ-ONLY."""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Iterator

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.cecchino_lab_historical_scan_run import CecchinoLabHistoricalScanRun
from app.services.cecchino_data_lab.errors import CecchinoLabImportError
from app.services.cecchino_data_lab.historical_bet_builder_projection import (
    bet_builder_meta_by_market,
)
from app.services.cecchino_data_lab.historical_scan_service import run_to_dict
from app.services.cecchino_data_lab.pattern_lab_aggregations import PatternLabAccumulator
from app.services.cecchino_data_lab.pattern_lab_constants import (
    DEFAULT_ELIGIBILITY,
    PATTERN_LAB_SORT_POLICY_BB,
    PATTERN_LAB_VERSION,
    SNAPSHOT_CHUNK_SIZE,
)
from app.services.cecchino_data_lab.pattern_lab_filters import (
    parse_pattern_lab_filters,
    row_passes_filters,
)
from app.services.cecchino_data_lab.pattern_lab_projection import (
    index_kpi_rows,
    index_purch_v36,
    iter_snapshot_id_batches,
    load_markets_for_snapshots,
    load_snapshots_by_ids,
    project_row,
)


def list_pattern_lab_runs(
    db: Session,
    *,
    season_label: str | None = None,
    include_pilots: bool = False,
) -> list[dict[str, Any]]:
    q = select(CecchinoLabHistoricalScanRun).order_by(CecchinoLabHistoricalScanRun.id.desc())
    if season_label:
        q = q.where(CecchinoLabHistoricalScanRun.season_label == season_label)
    out: list[dict[str, Any]] = []
    for run in db.scalars(q).all():
        d = run_to_dict(run)
        status = str(d.get("status") or "")
        if not status.startswith("completed"):
            continue
        scope = str(d.get("run_scope") or "full")
        is_pilot = scope in ("pilot", "balanced_pilot") or bool(d.get("is_partial_run"))
        if is_pilot and not include_pilots:
            continue
        if not is_pilot and scope != "full" and not include_pilots:
            # unknown scope treated as full if not partial
            if d.get("is_partial_run"):
                continue
        out.append(
            {
                "run_id": d["id"],
                "season_label": d["season_label"],
                "status": d["status"],
                "scan_version": d["scan_version"],
                "run_scope": d.get("run_scope"),
                "is_partial_run": d.get("is_partial_run"),
                "is_pilot": is_pilot,
                "matches_eligible_core": d.get("matches_eligible_core"),
                "matches_processed": d.get("matches_processed"),
                "completed_at": d.get("completed_at"),
                "source_git_commit": d.get("source_git_commit"),
            }
        )
    return out


def _resolve_runs(db: Session, run_ids: list[int]) -> list[CecchinoLabHistoricalScanRun]:
    if not run_ids:
        raise CecchinoLabImportError(
            "run_ids_required",
            "Selezionare almeno una run",
            status_code=400,
        )
    runs = list(
        db.scalars(
            select(CecchinoLabHistoricalScanRun).where(
                CecchinoLabHistoricalScanRun.id.in_(run_ids)
            )
        ).all()
    )
    found = {int(r.id) for r in runs}
    missing = [rid for rid in run_ids if rid not in found]
    if missing:
        raise CecchinoLabImportError(
            "run_not_found",
            f"Run non trovate: {missing}",
            status_code=404,
        )
    return runs


def iter_pattern_lab_rows(
    db: Session,
    run_ids: list[int],
    *,
    filters: dict[str, Any] | None = None,
    apply_filters: bool = True,
    chunk_size: int = SNAPSHOT_CHUNK_SIZE,
) -> Iterator[dict[str, Any]]:
    """Generatore chunked: non materializza tutte le righe in RAM."""
    parsed = parse_pattern_lab_filters(filters) if filters is not None else parse_pattern_lab_filters({})
    eligibility = parsed.get("eligibility") or DEFAULT_ELIGIBILITY
    _resolve_runs(db, run_ids)

    for batch_ids in iter_snapshot_id_batches(
        db,
        run_ids,
        eligibility=eligibility,
        chunk_size=chunk_size,
    ):
        snaps = load_snapshots_by_ids(db, batch_ids)
        markets = load_markets_for_snapshots(db, batch_ids)
        by_snap: dict[int, list] = defaultdict(list)
        for m in markets:
            by_snap[int(m.match_snapshot_id)].append(m)

        snap_by_id = {int(s.id): s for s in snaps}
        for sid in batch_ids:
            snap = snap_by_id.get(sid)
            if snap is None:
                continue
            kpi_idx = index_kpi_rows(snap.historical_kpi_json)
            purch_idx = index_purch_v36(snap.purchasability_compatibility_json)
            bb_by_mk = bet_builder_meta_by_market(snap)
            for market in by_snap.get(sid, []):
                row = project_row(
                    snap,
                    market,
                    kpi_by_market=kpi_idx,
                    purch_by_market=purch_idx,
                    bb_meta=bb_by_mk.get(market.market_key),
                )
                if apply_filters and not row_passes_filters(row, parsed):
                    continue
                yield row
        db.expire_all()


def query_pattern_lab(
    db: Session,
    *,
    run_ids: list[int],
    filters: dict[str, Any] | None = None,
    include_rows: bool = False,
    page: int = 1,
    page_size: int = 50,
) -> dict[str, Any]:
    page = max(1, int(page or 1))
    page_size = max(1, min(500, int(page_size or 50)))
    offset = (page - 1) * page_size
    limit_end = offset + page_size

    acc = PatternLabAccumulator()
    page_rows: list[dict[str, Any]] = []
    idx = 0
    for row in iter_pattern_lab_rows(db, run_ids, filters=filters, apply_filters=True):
        acc.add(row)
        if include_rows and offset <= idx < limit_end:
            page_rows.append(row)
        idx += 1

    runs = _resolve_runs(db, run_ids)
    agg = acc.result()
    return {
        "meta": {
            "pattern_lab_version": PATTERN_LAB_VERSION,
            "run_ids": [int(r) for r in run_ids],
            "seasons": sorted({str(r.season_label) for r in runs}),
            "filters_applied": parse_pattern_lab_filters(filters),
            "selection_count": agg["market_row_count"],
            "match_count": agg["match_count"],
            "page": page,
            "page_size": page_size,
            "bet_builder_sort_policy": PATTERN_LAB_SORT_POLICY_BB,
            "goal_intensity_note": "goal fields are V4-compat historical, not live V5",
        },
        "summary": agg["summary"],
        "breakdown": agg["breakdown"],
        "rows": page_rows if include_rows else [],
    }


def bet_builder_replay(
    db: Session,
    *,
    run_ids: list[int],
    filters: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Vista dedicata: solo active Bet Builder + timeline per giornata."""
    base_filters = dict(filters or {})
    base_filters["bet_builder_active"] = True
    acc = PatternLabAccumulator()
    by_day: dict[str, dict[str, Any]] = {}

    for row in iter_pattern_lab_rows(db, run_ids, filters=base_filters, apply_filters=True):
        acc.add(row)
        kickoff = str(row.get("kickoff_at") or "")[:10] or "unknown"
        day = by_day.setdefault(
            kickoff,
            {"date": kickoff, "selections": 0, "wins": 0, "losses": 0, "profit_1u": 0.0},
        )
        day["selections"] += 1
        if row.get("target_won") is True:
            day["wins"] += 1
        elif row.get("target_lost") is True:
            day["losses"] += 1
        if row.get("target_profit_1u") is not None:
            day["profit_1u"] += float(row["target_profit_1u"])

    agg = acc.result()
    timeline = []
    for date_key in sorted(by_day.keys()):
        d = by_day[date_key]
        n = int(d["selections"])
        profit = float(d["profit_1u"])
        timeline.append(
            {
                **d,
                "roi": (profit / n) if n else None,
            }
        )

    return {
        "meta": {
            "pattern_lab_version": PATTERN_LAB_VERSION,
            "run_ids": [int(r) for r in run_ids],
            "sort_policy": PATTERN_LAB_SORT_POLICY_BB,
            "note": "Historical Bet Builder uses V3.6 for evidence sort (not live V3.1)",
        },
        "summary": agg["summary"],
        "breakdown": agg["breakdown"],
        "timeline_by_day": timeline,
    }
