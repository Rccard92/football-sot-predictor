"""C1.3 — Bulk V3.6 evaluation bundle ZIP (read-only, persisted snapshots only)."""

from __future__ import annotations

import csv
import io
import json
import zipfile
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.models.cecchino_today_fixture import (
    MATCH_FINISHED,
    MATCH_LIVE,
    MATCH_UPCOMING,
    CecchinoTodayFixture,
)
from app.services.cecchino.cecchino_market_opposition import PANEL_MARKET_KEYS
from app.services.cecchino.cecchino_purchasability_audit import make_json_safe
from app.services.cecchino.cecchino_purchasability_v31_snapshot import (
    index_purchasability_v31_snapshot_by_market,
    validate_purchasability_preview_v31_snapshot,
)
from app.services.cecchino.cecchino_purchasability_v35_analysis_evaluation import (
    build_market_evaluation_block,
    compute_profit_1u_from_quote,
    normalize_match_status,
)
from app.services.cecchino.cecchino_purchasability_v35_snapshot import (
    index_purchasability_v35_snapshot_by_market,
    validate_purchasability_preview_v35_snapshot,
)
from app.services.cecchino.cecchino_purchasability_v35_v2_analysis_export import (
    COHORT_PROSPECTIVE,
    COHORT_TECHNICAL_SMOKE,
    FLOAT_ALIGNMENT_TOLERANCE,
    PRIMARY_DIAGNOSTIC_COHORT,
    extract_v2_analysis_fields,
    holdout_cohort_for_scan_date,
    resolve_paired_v1_a,
    select_top_v2_market_pre_match,
)
from app.services.cecchino.cecchino_purchasability_v35_v2_holdout_diagnostics import (
    build_holdout_diagnostics,
)
from app.services.cecchino.cecchino_purchasability_v35_v2_range_analysis_export import (
    MAX_RANGE_DAYS,
    V35V2AnalysisRangeError,
    _count_current_eligible_without_v2_key,
    _load_v2_snapshot_population_range,
)
from app.services.cecchino.cecchino_purchasability_v35_v2_snapshot import (
    EXPECTED_FORMULA_FREEZE_SHA256,
    SNAPSHOT_OUTPUT_KEY,
    index_purchasability_v35_v2_snapshot_by_market,
    validate_purchasability_preview_v35_v2_snapshot,
)
from app.services.cecchino.cecchino_purchasability_validation import market_family_for

PANEL_SIZE = len(PANEL_MARKET_KEYS)

COMPARISON_CSV_COLUMNS = [
    "scan_date",
    "today_fixture_id",
    "provider_fixture_id",
    "home_team",
    "away_team",
    "kickoff",
    "match_status",
    "current_eligibility_status",
    "holdout_cohort",
    "market_key",
    "market_family",
    "execution_quote",
    "probability_cecchino",
    "fair_book_probability",
    "EV",
    "outcome",
    "profit_1u",
    "v36_available",
    "v36_status",
    "v36_score",
    "v36_raw_score",
    "v36_class",
    "V",
    "D",
    "R",
    "S",
    "Q",
    "VALUE_CORE",
    "ACQUISITION_CORE",
    "structural_factor",
    "quality_factor",
    "adjusted_confidence",
    "v36_source_snapshot_at",
    "v36_generated_at",
    "v36_formula_freeze_sha256",
    "v35_available",
    "v35_status",
    "v35_score_A",
    "v35_raw_score_A",
    "v35_class_A",
    "v35_source_snapshot_at",
    "v31_available",
    "v31_status",
    "v31_score",
    "v31_raw_score",
    "v31_class",
    "v31_source_snapshot_at",
    "v31_generated_at",
    "v31_candidate_version",
    "strict_paired",
    "pair_alignment_reason",
    "pair_key",
    "v31_pairable",
    "v31_alignment_reason",
]

FIXTURE_SUMMARY_CSV_COLUMNS = [
    "scan_date",
    "today_fixture_id",
    "provider_fixture_id",
    "home_team",
    "away_team",
    "kickoff",
    "match_status",
    "current_eligibility_status",
    "holdout_cohort",
    "v36_snapshot_status",
    "top_v36_market",
    "top_v36_score",
    "top_v36_raw_score",
    "top_v36_quote",
    "top_v36_outcome",
    "top_v36_profit_1u",
    "top_v35_market",
    "top_v35_score",
    "top_v35_raw_score",
    "top_v35_quote",
    "top_v35_outcome",
    "top_v35_profit_1u",
    "top_v31_market",
    "top_v31_score",
    "top_v31_raw_score",
    "top_v31_quote",
    "top_v31_outcome",
    "top_v31_profit_1u",
    "strict_v36_v35_available",
    "v31_pairable_any",
    "v35_available",
    "v31_available",
]

README_TXT = """Cecchino V3.6 Evaluation Bundle (C1.3)
=====================================

Read-only offline package. No DB/API required.

Contents
--------
- manifest.json                 Cumulative + per-day summary, self-checks, freeze SHA
- comparison_rows.csv           One row per valid V3.6 fixture x 19 PANEL markets
- fixture_summary.csv           One row per population fixture (incl. invalid V3.6)
- diagnostics/v36_holdout_diagnostics.json
- snapshots/v36|v35|v31/*.json  Persisted snapshots when available
- README.txt

Population
----------
population_inclusion_basis = persisted_v2_snapshot_key (purchasability_preview_v35_v2)
Current eligibility is metadata only.

Cohorts
-------
2026-08-26 = technical_smoke_cohort
2026-08-27.. = prospective_holdout
PRIMARY_DIAGNOSTIC_COHORT = prospective_holdout

Flags
-----
recompute_used = false
outcome_join_post_freeze_only = true
formula_freeze_sha256_expected must match V3.6 freeze.
"""


class V36EvaluationBundleRangeError(ValueError):
    """Errore validazione range date evaluation bundle."""


def validate_evaluation_bundle_date_range(date_from: date, date_to: date) -> None:
    if date_from > date_to:
        raise V36EvaluationBundleRangeError("date_from must be <= date_to")
    span = (date_to - date_from).days + 1
    if span > MAX_RANGE_DAYS:
        raise V36EvaluationBundleRangeError(
            f"date range exceeds maximum of {MAX_RANGE_DAYS} days"
        )


def _json_bytes(payload: Any) -> bytes:
    return json.dumps(make_json_safe(payload), indent=2, ensure_ascii=False).encode(
        "utf-8"
    )


def _csv_bytes(rows: list[dict[str, Any]], columns: list[str]) -> bytes:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=columns, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow(row)
    return buf.getvalue().encode("utf-8")


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    if f != f:
        return None
    return f


def _parse_dt(raw: Any) -> datetime | None:
    if raw is None:
        return None
    if isinstance(raw, datetime):
        dt = raw
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt
    text = str(raw).strip()
    if not text:
        return None
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _normalize_source_snapshot_at(raw: Any) -> str | None:
    parsed = _parse_dt(raw)
    if parsed is not None:
        return parsed.astimezone(timezone.utc).isoformat()
    if raw is None:
        return None
    text = str(raw).strip()
    return text or None


def _floats_aligned(a: Any, b: Any, *, tol: float = FLOAT_ALIGNMENT_TOLERANCE) -> bool:
    fa = _safe_float(a)
    fb = _safe_float(b)
    if fa is None and fb is None:
        return True
    if fa is None or fb is None:
        return False
    return abs(fa - fb) <= tol


def _rank_score(raw: Any, score: Any) -> float | None:
    r = _safe_float(raw)
    if r is not None:
        return r
    return _safe_float(score)


def _v31_score_fields(item: dict[str, Any]) -> tuple[Any, Any, Any]:
    score = item.get("score_v31")
    if score is None:
        score = item.get("score")
    raw = item.get("raw_score_v31")
    if raw is None:
        raw = item.get("raw_score")
    klass = item.get("class_v31")
    if klass is None:
        klass = item.get("class")
    return score, raw, klass


def _v31_is_scored(item: dict[str, Any]) -> bool:
    status = str(item.get("status") or "")
    if status not in {"score", "score_provisional"}:
        return False
    score, raw, _ = _v31_score_fields(item)
    return _safe_float(score) is not None or _safe_float(raw) is not None


def _snapshot_availability(raw: Any, validator) -> tuple[str, dict[str, Any] | None]:
    """Return (available|missing|invalid, snapshot_or_none)."""
    if raw is None:
        return "missing", None
    if not isinstance(raw, dict):
        return "invalid", None
    check = validator(raw)
    if not check.get("ok"):
        return "invalid", raw
    return "available", raw


def resolve_v31_pairability(
    *,
    row: CecchinoTodayFixture,
    market_key: str,
    v36_item: dict[str, Any] | None,
    v31_snapshot: dict[str, Any] | None,
    v31_availability: str,
) -> dict[str, Any]:
    """Conservative V3.1 pairability — never assume pre-match."""
    base = {
        "v31_pairable": False,
        "v31_alignment_reason": None,
        "v31_available": v31_availability == "available",
        "v31_status": None,
        "v31_score": None,
        "v31_raw_score": None,
        "v31_class": None,
        "v31_source_snapshot_at": None,
        "v31_generated_at": None,
        "v31_candidate_version": None,
    }
    if v31_availability == "missing" or v31_snapshot is None:
        base["v31_alignment_reason"] = "v31_missing"
        return base
    if v31_availability == "invalid":
        base["v31_alignment_reason"] = "v31_invalid"
        return base

    base["v31_source_snapshot_at"] = _normalize_source_snapshot_at(
        v31_snapshot.get("source_snapshot_at")
    )
    base["v31_generated_at"] = v31_snapshot.get("generated_at")
    base["v31_candidate_version"] = v31_snapshot.get("candidate_version")

    by_mk = index_purchasability_v31_snapshot_by_market(v31_snapshot)
    v31_item = by_mk.get(market_key)
    if not isinstance(v31_item, dict):
        base["v31_alignment_reason"] = "v31_missing"
        return base

    score, raw, klass = _v31_score_fields(v31_item)
    base["v31_status"] = v31_item.get("status")
    base["v31_score"] = score
    base["v31_raw_score"] = raw
    base["v31_class"] = klass

    if not _v31_is_scored(v31_item):
        base["v31_alignment_reason"] = "v31_not_scored"
        return base

    # Temporal pre-match evidence (snapshot-level + item fallbacks)
    pre_match_only = v31_snapshot.get("pre_match_only")
    if pre_match_only is None:
        pre_match_only = v31_item.get("pre_match_only")
    before_ko = v31_snapshot.get("source_snapshot_before_kickoff")
    snap_at_raw = v31_snapshot.get("source_snapshot_at")
    if snap_at_raw is None:
        snap_at_raw = v31_item.get("snapshot_at")
    snap_at = _parse_dt(snap_at_raw)
    kickoff = row.kickoff if isinstance(row.kickoff, datetime) else _parse_dt(row.kickoff)

    temporal_ok = (
        pre_match_only is True
        and before_ko is True
        and snap_at is not None
        and kickoff is not None
        and snap_at < kickoff
    )
    if not temporal_ok:
        base["v31_alignment_reason"] = "v31_pre_match_not_verified"
        return base

    if not isinstance(v36_item, dict):
        base["v31_alignment_reason"] = "input_context_mismatch"
        return base

    v36_inp = (
        v36_item.get("input") if isinstance(v36_item.get("input"), dict) else {}
    )
    v31_inp = (
        v31_item.get("input") if isinstance(v31_item.get("input"), dict) else {}
    )
    mismatch: list[str] = []
    for field in ("execution_quote", "probability_cecchino", "fair_book_probability"):
        if not _floats_aligned(v36_inp.get(field), v31_inp.get(field)):
            mismatch.append(field)
    if mismatch:
        base["v31_alignment_reason"] = "input_context_mismatch"
        return base

    base["v31_pairable"] = True
    base["v31_alignment_reason"] = None
    return base


def _top_v35_from_snapshot(
    row: CecchinoTodayFixture,
    v35_snapshot: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if not isinstance(v35_snapshot, dict):
        return None
    by_mk = index_purchasability_v35_snapshot_by_market(v35_snapshot)
    best_mk: str | None = None
    best_rank: float | None = None
    best_idx = 10**9
    best_item: dict[str, Any] | None = None
    best_cand: dict[str, Any] | None = None
    for idx, mk in enumerate(PANEL_MARKET_KEYS):
        item = by_mk.get(mk)
        if not isinstance(item, dict) or str(item.get("status") or "") != "score":
            continue
        cands = item.get("candidates") if isinstance(item.get("candidates"), dict) else {}
        cand_a = cands.get("A") if isinstance(cands.get("A"), dict) else None
        if cand_a is None:
            continue
        rank = _rank_score(cand_a.get("raw_score"), cand_a.get("score"))
        if rank is None:
            continue
        if best_rank is None or rank > best_rank or (rank == best_rank and idx < best_idx):
            best_mk = mk
            best_rank = rank
            best_idx = idx
            best_item = item
            best_cand = cand_a
    if best_mk is None or best_item is None or best_cand is None:
        return None
    ev = build_market_evaluation_block(best_item, row, market_key=best_mk)
    inp = best_item.get("input") if isinstance(best_item.get("input"), dict) else {}
    return {
        "market_key": best_mk,
        "score": best_cand.get("score"),
        "raw_score": best_cand.get("raw_score"),
        "quote": inp.get("execution_quote"),
        "outcome": ev.get("outcome"),
        "profit_1u": compute_profit_1u_from_quote(
            execution_quote=inp.get("execution_quote"),
            execution_quote_real=inp.get("execution_quote_real") is True,
            outcome=str(ev.get("outcome") or ""),
        ),
    }


def _top_v31_from_snapshot(
    row: CecchinoTodayFixture,
    v31_snapshot: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if not isinstance(v31_snapshot, dict):
        return None
    by_mk = index_purchasability_v31_snapshot_by_market(v31_snapshot)
    best_mk: str | None = None
    best_rank: float | None = None
    best_idx = 10**9
    best_item: dict[str, Any] | None = None
    for idx, mk in enumerate(PANEL_MARKET_KEYS):
        item = by_mk.get(mk)
        if not isinstance(item, dict) or not _v31_is_scored(item):
            continue
        score, raw, _ = _v31_score_fields(item)
        rank = _rank_score(raw, score)
        if rank is None:
            continue
        if best_rank is None or rank > best_rank or (rank == best_rank and idx < best_idx):
            best_mk = mk
            best_rank = rank
            best_idx = idx
            best_item = item
    if best_mk is None or best_item is None:
        return None
    # Reuse V35 evaluation path (same market outcome rules) with V31 item input.
    ev = build_market_evaluation_block(best_item, row, market_key=best_mk)
    inp = best_item.get("input") if isinstance(best_item.get("input"), dict) else {}
    score, raw, _ = _v31_score_fields(best_item)
    return {
        "market_key": best_mk,
        "score": score,
        "raw_score": raw,
        "quote": inp.get("execution_quote"),
        "outcome": ev.get("outcome"),
        "profit_1u": compute_profit_1u_from_quote(
            execution_quote=inp.get("execution_quote"),
            execution_quote_real=inp.get("execution_quote_real") is True,
            outcome=str(ev.get("outcome") or ""),
        ),
    }


def _empty_day_bucket() -> dict[str, Any]:
    return {
        "snapshot_population_count": 0,
        "valid_v36_snapshots": 0,
        "invalid_v36_snapshots": 0,
        "settled_fixture_count": 0,
        "pending_fixture_count": 0,
        "scored_market_rows": 0,
        "holdout_cohort": None,
    }


def build_v36_evaluation_bundle_payload(
    db: Session,
    *,
    date_from: date,
    date_to: date,
) -> tuple[
    dict[str, Any],
    dict[str, bytes],
    list[dict[str, Any]],
    list[dict[str, Any]],
    dict[str, Any],
]:
    validate_evaluation_bundle_date_range(date_from, date_to)
    fixtures = _load_v2_snapshot_population_range(
        db, date_from=date_from, date_to=date_to
    )
    eligible_without_v2 = _count_current_eligible_without_v2_key(
        db, date_from=date_from, date_to=date_to
    )
    generated_at = datetime.now(timezone.utc).isoformat()

    comparison_rows: list[dict[str, Any]] = []
    diagnostic_rows: list[dict[str, Any]] = []
    fixture_summary_rows: list[dict[str, Any]] = []
    snapshot_files: dict[str, bytes] = {}
    manifest_fixtures: list[dict[str, Any]] = []

    days: dict[str, dict[str, Any]] = defaultdict(_empty_day_bucket)
    eligibility_counter: Counter[str] = Counter()

    valid_v36 = 0
    invalid_v36 = 0
    settled_fixture_count = 0
    pending_fixture_count = 0
    scored_market_rows = 0
    strict_v36_v35_rows = 0
    pairable_v36_v31_rows = 0
    v35_available_fixture_count = 0
    v35_missing_fixture_count = 0
    v31_available_fixture_count = 0
    v31_missing_fixture_count = 0
    technical_smoke_fixture_count = 0
    prospective_holdout_fixture_count = 0
    technical_smoke_settled_fixture_count = 0
    prospective_holdout_settled_fixture_count = 0

    top_v2_all_rows: list[dict[str, Any]] = []
    top_v2_strict_rows: list[dict[str, Any]] = []
    top_v1_strict_rows: list[dict[str, Any]] = []

    for row in fixtures:
        scan_key = row.scan_date.isoformat() if row.scan_date else "unknown"
        cohort = holdout_cohort_for_scan_date(row.scan_date)
        day = days[scan_key]
        day["snapshot_population_count"] += 1
        day["holdout_cohort"] = cohort
        eligibility_counter[str(row.eligibility_status)] += 1

        if cohort == COHORT_TECHNICAL_SMOKE:
            technical_smoke_fixture_count += 1
        elif cohort == COHORT_PROSPECTIVE:
            prospective_holdout_fixture_count += 1

        match_status = normalize_match_status(row)
        is_settled = match_status == MATCH_FINISHED
        is_pending = match_status in {MATCH_UPCOMING, MATCH_LIVE}
        if is_settled:
            settled_fixture_count += 1
            day["settled_fixture_count"] += 1
            if cohort == COHORT_TECHNICAL_SMOKE:
                technical_smoke_settled_fixture_count += 1
            elif cohort == COHORT_PROSPECTIVE:
                prospective_holdout_settled_fixture_count += 1
        if is_pending:
            pending_fixture_count += 1
            day["pending_fixture_count"] += 1

        output = row.cecchino_output_json if isinstance(row.cecchino_output_json, dict) else {}
        v36_raw = output.get(SNAPSHOT_OUTPUT_KEY)
        v35_raw = output.get("purchasability_preview_v35")
        v31_raw = output.get("purchasability_preview_v31")

        v36_avail, v36_snap = _snapshot_availability(
            v36_raw, validate_purchasability_preview_v35_v2_snapshot
        )
        # Population key present → treat non-ok as invalid (never missing here)
        if v36_avail != "available":
            v36_avail = "invalid"
            v36_snap = v36_raw if isinstance(v36_raw, dict) else None

        v35_avail, v35_snap = _snapshot_availability(
            v35_raw, validate_purchasability_preview_v35_snapshot
        )
        v31_avail, v31_snap = _snapshot_availability(
            v31_raw, validate_purchasability_preview_v31_snapshot
        )

        if v35_avail == "available":
            v35_available_fixture_count += 1
        else:
            v35_missing_fixture_count += 1
        if v31_avail == "available":
            v31_available_fixture_count += 1
        else:
            v31_missing_fixture_count += 1

        provider_id = int(row.provider_fixture_id)
        if isinstance(v36_raw, dict):
            snapshot_files[f"snapshots/v36/{provider_id}.json"] = _json_bytes(v36_raw)
        if isinstance(v35_raw, dict):
            snapshot_files[f"snapshots/v35/{provider_id}.json"] = _json_bytes(v35_raw)
        if isinstance(v31_raw, dict):
            snapshot_files[f"snapshots/v31/{provider_id}.json"] = _json_bytes(v31_raw)

        fixture_meta = {
            "today_fixture_id": int(row.id),
            "provider_fixture_id": provider_id,
            "scan_date": scan_key,
            "holdout_cohort": cohort,
            "home_team": row.home_team_name,
            "away_team": row.away_team_name,
            "kickoff": row.kickoff.isoformat() if row.kickoff else None,
            "match_status": match_status,
            "current_eligibility_status": row.eligibility_status,
            "v36_snapshot_status": v36_avail,
            "v35_available": v35_avail == "available",
            "v31_available": v31_avail == "available",
            "v35_status": v35_avail,
            "v31_status": v31_avail,
        }

        if v36_avail != "available" or not isinstance(v36_snap, dict):
            invalid_v36 += 1
            day["invalid_v36_snapshots"] += 1
            manifest_fixtures.append({**fixture_meta, "analysis_status": "snapshot_invalid"})
            fixture_summary_rows.append(
                {
                    **fixture_meta,
                    "top_v36_market": None,
                    "top_v36_score": None,
                    "top_v36_raw_score": None,
                    "top_v36_quote": None,
                    "top_v36_outcome": None,
                    "top_v36_profit_1u": None,
                    "top_v35_market": None,
                    "top_v35_score": None,
                    "top_v35_raw_score": None,
                    "top_v35_quote": None,
                    "top_v35_outcome": None,
                    "top_v35_profit_1u": None,
                    "top_v31_market": None,
                    "top_v31_score": None,
                    "top_v31_raw_score": None,
                    "top_v31_quote": None,
                    "top_v31_outcome": None,
                    "top_v31_profit_1u": None,
                    "strict_v36_v35_available": False,
                    "v31_pairable_any": False,
                }
            )
            # Still attach TOP v35/v31 from persisted when present
            top_v35 = _top_v35_from_snapshot(row, v35_snap)
            top_v31 = _top_v31_from_snapshot(row, v31_snap)
            if top_v35:
                fixture_summary_rows[-1].update(
                    {
                        "top_v35_market": top_v35["market_key"],
                        "top_v35_score": top_v35["score"],
                        "top_v35_raw_score": top_v35["raw_score"],
                        "top_v35_quote": top_v35["quote"],
                        "top_v35_outcome": top_v35["outcome"],
                        "top_v35_profit_1u": top_v35["profit_1u"],
                    }
                )
            if top_v31:
                fixture_summary_rows[-1].update(
                    {
                        "top_v31_market": top_v31["market_key"],
                        "top_v31_score": top_v31["score"],
                        "top_v31_raw_score": top_v31["raw_score"],
                        "top_v31_quote": top_v31["quote"],
                        "top_v31_outcome": top_v31["outcome"],
                        "top_v31_profit_1u": top_v31["profit_1u"],
                    }
                )
            continue

        valid_v36 += 1
        day["valid_v36_snapshots"] += 1
        by_v36 = index_purchasability_v35_v2_snapshot_by_market(v36_snap)
        top_pre = select_top_v2_market_pre_match(by_v36)

        fixture_strict_any = False
        fixture_v31_pairable_any = False
        best_strict_v2: dict[str, Any] | None = None
        best_strict_v2_rank: float | None = None
        best_strict_v1: dict[str, Any] | None = None
        best_strict_v1_rank: float | None = None

        for mk in PANEL_MARKET_KEYS:
            item = by_v36.get(mk)
            fields = extract_v2_analysis_fields(item) if isinstance(item, dict) else {}
            ev = (
                build_market_evaluation_block(item, row, market_key=mk)
                if isinstance(item, dict)
                else {
                    "outcome": None,
                    "profit_1u": None,
                    "evaluation_reason": "market_missing",
                }
            )
            paired = None
            if isinstance(item, dict):
                paired = resolve_paired_v1_a(
                    row=row,
                    market_key=mk,
                    v2_snapshot=v36_snap,
                    v2_item=item,
                )
            v35_fields = {
                "v35_available": v35_avail == "available",
                "v35_status": None,
                "v35_score_A": None,
                "v35_raw_score_A": None,
                "v35_class_A": None,
                "v35_source_snapshot_at": (
                    _normalize_source_snapshot_at(v35_snap.get("source_snapshot_at"))
                    if isinstance(v35_snap, dict)
                    else None
                ),
            }
            if paired is not None:
                v35_fields.update(
                    {
                        "v35_available": True,
                        "v35_status": paired.get("v1_status"),
                        "v35_score_A": paired.get("v1_score_A"),
                        "v35_raw_score_A": paired.get("v1_raw_score_A"),
                        "v35_class_A": paired.get("v1_class_A"),
                        "v35_source_snapshot_at": paired.get("v1_source_snapshot_at"),
                    }
                )
            elif v35_avail == "available" and isinstance(v35_snap, dict):
                v35_by = index_purchasability_v35_snapshot_by_market(v35_snap)
                v35_item = v35_by.get(mk)
                if isinstance(v35_item, dict):
                    cands = (
                        v35_item.get("candidates")
                        if isinstance(v35_item.get("candidates"), dict)
                        else {}
                    )
                    cand_a = cands.get("A") if isinstance(cands.get("A"), dict) else None
                    v35_fields["v35_status"] = v35_item.get("status")
                    if cand_a:
                        v35_fields["v35_score_A"] = cand_a.get("score")
                        v35_fields["v35_raw_score_A"] = cand_a.get("raw_score")
                        v35_fields["v35_class_A"] = cand_a.get("class")
            elif v35_avail == "invalid":
                v35_fields["v35_available"] = False
                v35_fields["v35_status"] = "invalid"
            else:
                v35_fields["v35_status"] = "missing"

            v31_pair = resolve_v31_pairability(
                row=row,
                market_key=mk,
                v36_item=item if isinstance(item, dict) else None,
                v31_snapshot=v31_snap,
                v31_availability=v31_avail,
            )

            strict = bool(paired and paired.get("strict_paired") is True)
            if strict:
                strict_v36_v35_rows += 1
                fixture_strict_any = True
            if v31_pair.get("v31_pairable"):
                pairable_v36_v31_rows += 1
                fixture_v31_pairable_any = True

            is_scored = str((fields.get("status") if fields else None) or "") == "score"
            if is_scored:
                scored_market_rows += 1
                day["scored_market_rows"] += 1

            row_out = {
                "scan_date": scan_key,
                "today_fixture_id": int(row.id),
                "provider_fixture_id": provider_id,
                "home_team": row.home_team_name,
                "away_team": row.away_team_name,
                "kickoff": row.kickoff.isoformat() if row.kickoff else None,
                "match_status": match_status,
                "current_eligibility_status": row.eligibility_status,
                "holdout_cohort": cohort,
                "market_key": mk,
                "market_family": fields.get("market_family")
                or market_family_for(mk),
                "execution_quote": fields.get("execution_quote"),
                "probability_cecchino": fields.get("probability_cecchino"),
                "fair_book_probability": fields.get("fair_book_probability"),
                "EV": fields.get("EV"),
                "outcome": ev.get("outcome"),
                "profit_1u": ev.get("profit_1u"),
                "v36_available": True,
                "v36_status": fields.get("status")
                if fields
                else ("missing" if item is None else None),
                "v36_score": fields.get("v2_score"),
                "v36_raw_score": fields.get("v2_raw_score"),
                "v36_class": fields.get("v2_class"),
                "V": fields.get("V"),
                "D": fields.get("D"),
                "R": fields.get("R"),
                "S": fields.get("S"),
                "Q": fields.get("Q"),
                "VALUE_CORE": fields.get("VALUE_CORE"),
                "ACQUISITION_CORE": fields.get("ACQUISITION_CORE"),
                "structural_factor": fields.get("structural_factor"),
                "quality_factor": fields.get("quality_factor"),
                "adjusted_confidence": fields.get("adjusted_confidence"),
                "v36_source_snapshot_at": _normalize_source_snapshot_at(
                    v36_snap.get("source_snapshot_at")
                ),
                "v36_generated_at": v36_snap.get("generated_at"),
                "v36_formula_freeze_sha256": v36_snap.get("formula_freeze_sha256"),
                **v35_fields,
                "v31_available": v31_pair.get("v31_available"),
                "v31_status": v31_pair.get("v31_status")
                or (
                    "invalid"
                    if v31_avail == "invalid"
                    else ("missing" if v31_avail == "missing" else None)
                ),
                "v31_score": v31_pair.get("v31_score"),
                "v31_raw_score": v31_pair.get("v31_raw_score"),
                "v31_class": v31_pair.get("v31_class"),
                "v31_source_snapshot_at": v31_pair.get("v31_source_snapshot_at"),
                "v31_generated_at": v31_pair.get("v31_generated_at"),
                "v31_candidate_version": v31_pair.get("v31_candidate_version"),
                "strict_paired": strict,
                "pair_alignment_reason": (
                    paired.get("pair_alignment_reason") if paired else (
                        "v35_missing" if v35_avail == "missing" else (
                            "v35_invalid" if v35_avail == "invalid" else None
                        )
                    )
                ),
                "pair_key": (
                    paired.get("pair_key")
                    if paired
                    else f"{int(row.id)}::{mk}"
                ),
                "v31_pairable": bool(v31_pair.get("v31_pairable")),
                "v31_alignment_reason": v31_pair.get("v31_alignment_reason"),
            }
            comparison_rows.append(row_out)

            # Diagnostic alias for holdout builder (expects v2_* columns)
            diagnostic_rows.append(
                {
                    **row_out,
                    "v2_score": row_out["v36_score"],
                    "v2_raw_score": row_out["v36_raw_score"],
                    "v2_class": row_out["v36_class"],
                    "status": row_out["v36_status"],
                    "v1_score_A": row_out["v35_score_A"],
                    "v1_raw_score_A": row_out["v35_raw_score_A"],
                    "v1_class_A": row_out["v35_class_A"],
                    "v1_status": row_out["v35_status"],
                    "v2_status": row_out["v36_status"],
                    "paired": bool(paired),
                }
            )

            if strict and paired is not None and isinstance(item, dict):
                v2_rank = _rank_score(item.get("raw_score"), item.get("score"))
                v1_rank = _rank_score(paired.get("v1_raw_score_A"), paired.get("v1_score_A"))
                if v2_rank is not None and (
                    best_strict_v2_rank is None or v2_rank > best_strict_v2_rank
                ):
                    best_strict_v2_rank = v2_rank
                    best_strict_v2 = {
                        "today_fixture_id": int(row.id),
                        "provider_fixture_id": provider_id,
                        "scan_date": scan_key,
                        "holdout_cohort": cohort,
                        "market_key": mk,
                        "pair_key": paired.get("pair_key"),
                        "v2_score": item.get("score"),
                        "v2_raw_score": item.get("raw_score"),
                        "outcome": ev.get("outcome"),
                        "profit_1u": ev.get("profit_1u"),
                        "execution_quote": fields.get("execution_quote"),
                        "selection_basis": "strict_paired_v2_score",
                    }
                if v1_rank is not None and (
                    best_strict_v1_rank is None or v1_rank > best_strict_v1_rank
                ):
                    best_strict_v1_rank = v1_rank
                    best_strict_v1 = {
                        "today_fixture_id": int(row.id),
                        "provider_fixture_id": provider_id,
                        "scan_date": scan_key,
                        "holdout_cohort": cohort,
                        "market_key": mk,
                        "pair_key": paired.get("pair_key"),
                        "v1_score_A": paired.get("v1_score_A"),
                        "v1_raw_score_A": paired.get("v1_raw_score_A"),
                        "outcome": ev.get("outcome"),
                        "profit_1u": compute_profit_1u_from_quote(
                            execution_quote=paired.get("v1_execution_quote"),
                            execution_quote_real=paired.get("v1_execution_quote_real")
                            is True,
                            outcome=str(ev.get("outcome") or ""),
                        ),
                        "execution_quote": paired.get("v1_execution_quote"),
                        "selection_basis": "strict_paired_v1_A_score",
                    }

        # TOP V36 from pre-match selection
        top_v36_summary: dict[str, Any] | None = None
        if top_pre is not None:
            tmk = top_pre["market_key"]
            titem = by_v36.get(tmk)
            if isinstance(titem, dict):
                tev = build_market_evaluation_block(titem, row, market_key=tmk)
                tinp = titem.get("input") if isinstance(titem.get("input"), dict) else {}
                top_v36_summary = {
                    "market_key": tmk,
                    "score": titem.get("score"),
                    "raw_score": titem.get("raw_score"),
                    "quote": tinp.get("execution_quote"),
                    "outcome": tev.get("outcome"),
                    "profit_1u": tev.get("profit_1u"),
                }
                top_v2_all_rows.append(
                    {
                        "today_fixture_id": int(row.id),
                        "provider_fixture_id": provider_id,
                        "scan_date": scan_key,
                        "holdout_cohort": cohort,
                        "market_key": tmk,
                        "v2_score": titem.get("score"),
                        "v2_raw_score": titem.get("raw_score"),
                        "outcome": tev.get("outcome"),
                        "profit_1u": tev.get("profit_1u"),
                        "execution_quote": tinp.get("execution_quote"),
                    }
                )
        if best_strict_v2 is not None:
            top_v2_strict_rows.append(best_strict_v2)
        if best_strict_v1 is not None:
            top_v1_strict_rows.append(best_strict_v1)

        top_v35 = _top_v35_from_snapshot(row, v35_snap)
        top_v31 = _top_v31_from_snapshot(row, v31_snap)

        fixture_summary_rows.append(
            {
                **fixture_meta,
                "top_v36_market": (top_v36_summary or {}).get("market_key"),
                "top_v36_score": (top_v36_summary or {}).get("score"),
                "top_v36_raw_score": (top_v36_summary or {}).get("raw_score"),
                "top_v36_quote": (top_v36_summary or {}).get("quote"),
                "top_v36_outcome": (top_v36_summary or {}).get("outcome"),
                "top_v36_profit_1u": (top_v36_summary or {}).get("profit_1u"),
                "top_v35_market": (top_v35 or {}).get("market_key"),
                "top_v35_score": (top_v35 or {}).get("score"),
                "top_v35_raw_score": (top_v35 or {}).get("raw_score"),
                "top_v35_quote": (top_v35 or {}).get("quote"),
                "top_v35_outcome": (top_v35 or {}).get("outcome"),
                "top_v35_profit_1u": (top_v35 or {}).get("profit_1u"),
                "top_v31_market": (top_v31 or {}).get("market_key"),
                "top_v31_score": (top_v31 or {}).get("score"),
                "top_v31_raw_score": (top_v31 or {}).get("raw_score"),
                "top_v31_quote": (top_v31 or {}).get("quote"),
                "top_v31_outcome": (top_v31 or {}).get("outcome"),
                "top_v31_profit_1u": (top_v31 or {}).get("profit_1u"),
                "strict_v36_v35_available": fixture_strict_any,
                "v31_pairable_any": fixture_v31_pairable_any,
            }
        )
        manifest_fixtures.append({**fixture_meta, "analysis_status": "included"})

    expected_comparison_rows = valid_v36 * PANEL_SIZE
    comparison_rows_count = len(comparison_rows)
    unique_summary = len({r["today_fixture_id"] for r in fixture_summary_rows})
    unique_pop = len({int(r.id) for r in fixtures})

    summary: dict[str, Any] = {
        "population_inclusion_basis": "persisted_v2_snapshot_key",
        "snapshot_population_count": len(fixtures),
        "valid_v36_snapshots": valid_v36,
        "invalid_v36_snapshots": invalid_v36,
        "analysis_included_count": valid_v36,
        "v35_available_fixture_count": v35_available_fixture_count,
        "v35_missing_fixture_count": v35_missing_fixture_count,
        "v31_available_fixture_count": v31_available_fixture_count,
        "v31_missing_fixture_count": v31_missing_fixture_count,
        "settled_fixture_count": settled_fixture_count,
        "pending_fixture_count": pending_fixture_count,
        "scored_market_rows": scored_market_rows,
        "comparison_rows_count": comparison_rows_count,
        "expected_comparison_rows_count": expected_comparison_rows,
        "comparison_rows_complete": comparison_rows_count == expected_comparison_rows,
        "unique_v36_population_fixture_count": unique_pop,
        "unique_fixture_summary_count": unique_summary,
        "fixture_summary_matches_population": unique_summary == len(fixtures),
        "strict_v36_v35_rows": strict_v36_v35_rows,
        "pairable_v36_v31_rows": pairable_v36_v31_rows,
        "current_eligibility_counts": dict(eligibility_counter),
        "current_eligible_without_v2_key_count": eligible_without_v2,
        "technical_smoke_fixture_count": technical_smoke_fixture_count,
        "prospective_holdout_fixture_count": prospective_holdout_fixture_count,
        "technical_smoke_settled_fixture_count": technical_smoke_settled_fixture_count,
        "prospective_holdout_settled_fixture_count": prospective_holdout_settled_fixture_count,
        "formula_freeze_sha256_expected": EXPECTED_FORMULA_FREEZE_SHA256,
        "outcome_join_post_freeze_only": True,
        "recompute_used": False,
        "PRIMARY_DIAGNOSTIC_COHORT": PRIMARY_DIAGNOSTIC_COHORT,
    }

    diagnostics = build_holdout_diagnostics(
        diagnostic_rows,
        top_v2_all_markets_rows=top_v2_all_rows,
        top_v2_strict_paired_rows=top_v2_strict_rows,
        top_v1_strict_paired_rows=top_v1_strict_rows,
    )

    manifest = make_json_safe(
        {
            "contract_version": "purchasability_v36_evaluation_bundle_manifest_v1",
            "date_from": date_from.isoformat(),
            "date_to": date_to.isoformat(),
            "range_inclusive": True,
            "generated_at": generated_at,
            "formula_freeze_sha256_expected": EXPECTED_FORMULA_FREEZE_SHA256,
            "PRIMARY_DIAGNOSTIC_COHORT": PRIMARY_DIAGNOSTIC_COHORT,
            "population_inclusion_basis": "persisted_v2_snapshot_key",
            "outcome_join_post_freeze_only": True,
            "recompute_used": False,
            "summary": summary,
            "days": dict(days),
            "fixtures": manifest_fixtures,
            "self_check": {
                "comparison_rows_count": comparison_rows_count,
                "expected_comparison_rows_count": expected_comparison_rows,
                "comparison_rows_complete": comparison_rows_count
                == expected_comparison_rows,
                "unique_v36_population_fixture_count": unique_pop,
                "unique_fixture_summary_count": unique_summary,
                "unique_fixture_summary_equals_population": unique_summary
                == len(fixtures),
            },
        }
    )
    return manifest, snapshot_files, comparison_rows, fixture_summary_rows, diagnostics


def build_v36_evaluation_bundle_zip(
    db: Session,
    *,
    date_from: date,
    date_to: date,
) -> tuple[bytes, str]:
    (
        manifest,
        snapshot_files,
        comparison_rows,
        fixture_summary_rows,
        diagnostics,
    ) = build_v36_evaluation_bundle_payload(
        db, date_from=date_from, date_to=date_to
    )
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", _json_bytes(manifest))
        archive.writestr(
            "comparison_rows.csv",
            _csv_bytes(comparison_rows, COMPARISON_CSV_COLUMNS),
        )
        archive.writestr(
            "fixture_summary.csv",
            _csv_bytes(fixture_summary_rows, FIXTURE_SUMMARY_CSV_COLUMNS),
        )
        archive.writestr(
            "diagnostics/v36_holdout_diagnostics.json",
            _json_bytes(diagnostics),
        )
        archive.writestr("README.txt", README_TXT.encode("utf-8"))
        for name in sorted(snapshot_files):
            archive.writestr(name, snapshot_files[name])
    filename = (
        f"cecchino-v36-analysis-{date_from.isoformat()}_{date_to.isoformat()}.zip"
    )
    return buf.getvalue(), filename


__all__ = [
    "COMPARISON_CSV_COLUMNS",
    "FIXTURE_SUMMARY_CSV_COLUMNS",
    "PANEL_SIZE",
    "V36EvaluationBundleRangeError",
    "build_v36_evaluation_bundle_payload",
    "build_v36_evaluation_bundle_zip",
    "resolve_v31_pairability",
    "validate_evaluation_bundle_date_range",
]
