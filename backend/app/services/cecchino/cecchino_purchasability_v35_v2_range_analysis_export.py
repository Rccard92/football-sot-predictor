"""Export range analysis Structural V2 — ZIP read-only + holdout diagnostics."""

from __future__ import annotations

import csv
import io
import json
import zipfile
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.cecchino_signal_activation import EVAL_LOST, EVAL_WON
from app.models.cecchino_today_fixture import (
    ELIGIBILITY_ELIGIBLE,
    MATCH_CANCELLED,
    MATCH_FINISHED,
    MATCH_LIVE,
    MATCH_POSTPONED,
    MATCH_UPCOMING,
    CecchinoTodayFixture,
)
from app.schemas.cecchino_purchasability_v35_v2 import (
    PURCHASABILITY_V35_V2_ANALYSIS_EXPORT_CONTRACT_VERSION,
    PURCHASABILITY_V35_V2_ANALYSIS_MANIFEST_CONTRACT_VERSION,
    PURCHASABILITY_V35_V2_EXPERIMENT_VERSION,
)
from app.services.cecchino.cecchino_market_opposition import PANEL_MARKET_KEYS
from app.services.cecchino.cecchino_purchasability_audit import make_json_safe
from app.services.cecchino.cecchino_purchasability_v35_analysis_evaluation import (
    compute_profit_1u_from_quote,
    normalize_match_status,
)
from app.services.cecchino.cecchino_purchasability_v35_v2_analysis_export import (
    PRIMARY_DIAGNOSTIC_COHORT,
    build_purchasability_v35_v2_analysis_export,
    extract_v2_analysis_fields,
    holdout_cohort_for_scan_date,
)
from app.services.cecchino.cecchino_purchasability_v35_v2_holdout_diagnostics import (
    build_holdout_diagnostics,
)
from app.services.cecchino.cecchino_purchasability_v35_v2_snapshot import (
    EXPECTED_FORMULA_FREEZE_SHA256,
    SNAPSHOT_OUTPUT_KEY,
    fixture_has_v35_v2_score,
    validate_purchasability_preview_v35_v2_snapshot,
)

MAX_RANGE_DAYS = 31

CSV_COLUMNS = [
    "scan_date",
    "today_fixture_id",
    "provider_fixture_id",
    "country",
    "league",
    "home_team",
    "away_team",
    "kickoff",
    "source_snapshot_at",
    "generated_at",
    "holdout_cohort",
    "current_eligibility_status",
    "market_key",
    "market_label",
    "market_family",
    "holdout_market_family",
    "status",
    "gate_status",
    "execution_quote",
    "probability_cecchino",
    "fair_book_probability",
    "EV",
    "ev_source",
    "V",
    "D",
    "R",
    "base_rate_reliability",
    "VALUE_CORE",
    "ACQUISITION_CORE",
    "S",
    "S_raw",
    "structural_confidence",
    "structural_factor",
    "Q",
    "quality_factor",
    "adjusted_confidence",
    "v2_score",
    "v2_raw_score",
    "v2_class",
    "paired",
    "strict_paired",
    "pair_alignment_reason",
    "pair_key",
    "v1_source_snapshot_at",
    "v2_source_snapshot_at",
    "v1_execution_quote",
    "v2_execution_quote",
    "v1_status",
    "v2_status",
    "v1_score_A",
    "v1_raw_score_A",
    "v1_class_A",
    "input_mismatch_fields",
    "formula_freeze_sha256",
    "match_status",
    "ht_home",
    "ht_away",
    "ft_home",
    "ft_away",
    "outcome",
    "evaluation_reason",
    "profit_1u",
    "input_fingerprint_sha256",
    "engine_payload_sha256",
]


class V35V2AnalysisRangeError(ValueError):
    """Errore validazione range date analysis export V2."""


def validate_v2_analysis_date_range(date_from: date, date_to: date) -> None:
    if date_from > date_to:
        raise V35V2AnalysisRangeError("date_from must be <= date_to")
    span = (date_to - date_from).days + 1
    if span > MAX_RANGE_DAYS:
        raise V35V2AnalysisRangeError(
            f"date range exceeds maximum of {MAX_RANGE_DAYS} days"
        )


def _load_v2_snapshot_population_range(
    db: Session,
    *,
    date_from: date,
    date_to: date,
) -> list[CecchinoTodayFixture]:
    """Snapshot-driven holdout population: KEY presence only, no eligibility gate."""
    stmt = (
        select(CecchinoTodayFixture)
        .where(
            CecchinoTodayFixture.scan_date >= date_from,
            CecchinoTodayFixture.scan_date <= date_to,
            CecchinoTodayFixture.cecchino_output_json.isnot(None),
            CecchinoTodayFixture.cecchino_output_json.has_key(SNAPSHOT_OUTPUT_KEY),
        )
        .order_by(
            CecchinoTodayFixture.scan_date.asc(),
            CecchinoTodayFixture.kickoff.asc(),
            CecchinoTodayFixture.id.asc(),
        )
    )
    rows = list(db.scalars(stmt).all())
    population: list[CecchinoTodayFixture] = []
    for row in rows:
        output = row.cecchino_output_json
        if isinstance(output, dict) and SNAPSHOT_OUTPUT_KEY in output:
            population.append(row)
    return population


def _count_current_eligible_without_v2_key(
    db: Session,
    *,
    date_from: date,
    date_to: date,
) -> int:
    """Coverage diagnostic only — must not feed analysis population/CSV/pairing."""
    stmt = (
        select(CecchinoTodayFixture)
        .where(
            CecchinoTodayFixture.scan_date >= date_from,
            CecchinoTodayFixture.scan_date <= date_to,
            CecchinoTodayFixture.eligibility_status == ELIGIBILITY_ELIGIBLE,
        )
    )
    n = 0
    for row in db.scalars(stmt).all():
        output = (
            row.cecchino_output_json
            if isinstance(row.cecchino_output_json, dict)
            else None
        )
        if output is None or SNAPSHOT_OUTPUT_KEY not in output:
            n += 1
    return n


def _json_bytes(payload: Any) -> bytes:
    return json.dumps(make_json_safe(payload), indent=2, ensure_ascii=False).encode(
        "utf-8"
    )


def _scored_market_count(snapshot: dict[str, Any]) -> int:
    return sum(
        1
        for item in snapshot.get("items") or []
        if isinstance(item, dict) and item.get("status") == "score"
    )


def _fixture_terminal_for_analysis(row: CecchinoTodayFixture) -> bool:
    status = normalize_match_status(row)
    if status in {MATCH_CANCELLED, MATCH_POSTPONED}:
        return True
    if status != MATCH_FINISHED:
        return False
    return row.score_fulltime_home is not None and row.score_fulltime_away is not None


def _csv_row_from_analysis(
    analysis: dict[str, Any],
    *,
    market_key: str,
    item: dict[str, Any],
) -> dict[str, Any]:
    fixture = analysis.get("fixture") if isinstance(analysis.get("fixture"), dict) else {}
    integrity = (
        analysis.get("snapshot_integrity")
        if isinstance(analysis.get("snapshot_integrity"), dict)
        else {}
    )
    post = analysis.get("post_match") if isinstance(analysis.get("post_match"), dict) else {}
    pre = analysis.get("pre_match") if isinstance(analysis.get("pre_match"), dict) else {}
    fields = item.get("analysis") if isinstance(item.get("analysis"), dict) else {}
    if not fields:
        fields = extract_v2_analysis_fields(item)
    paired = item.get("paired_v1") if isinstance(item.get("paired_v1"), dict) else {}
    ev = item.get("evaluation") if isinstance(item.get("evaluation"), dict) else {}
    ht = post.get("halftime") if isinstance(post.get("halftime"), dict) else {}
    ft = post.get("fulltime") if isinstance(post.get("fulltime"), dict) else {}

    return {
        "scan_date": fixture.get("scan_date"),
        "today_fixture_id": fixture.get("today_fixture_id"),
        "provider_fixture_id": fixture.get("provider_fixture_id"),
        "country": fixture.get("country"),
        "league": fixture.get("league"),
        "home_team": fixture.get("home_team"),
        "away_team": fixture.get("away_team"),
        "kickoff": fixture.get("kickoff") or pre.get("kickoff"),
        "source_snapshot_at": pre.get("source_snapshot_at"),
        "generated_at": pre.get("generated_at"),
        "holdout_cohort": fixture.get("holdout_cohort"),
        "current_eligibility_status": fixture.get("current_eligibility_status"),
        "market_key": market_key,
        "market_label": fields.get("market_label"),
        "market_family": fields.get("market_family"),
        "holdout_market_family": fields.get("holdout_market_family"),
        "status": fields.get("status") or item.get("status"),
        "gate_status": fields.get("gate_status") or item.get("gate_status"),
        "execution_quote": fields.get("execution_quote"),
        "probability_cecchino": fields.get("probability_cecchino"),
        "fair_book_probability": fields.get("fair_book_probability"),
        "EV": fields.get("EV"),
        "ev_source": fields.get("ev_source"),
        "V": fields.get("V"),
        "D": fields.get("D"),
        "R": fields.get("R"),
        "base_rate_reliability": fields.get("base_rate_reliability"),
        "VALUE_CORE": fields.get("VALUE_CORE"),
        "ACQUISITION_CORE": fields.get("ACQUISITION_CORE"),
        "S": fields.get("S"),
        "S_raw": fields.get("S_raw"),
        "structural_confidence": fields.get("structural_confidence"),
        "structural_factor": fields.get("structural_factor"),
        "Q": fields.get("Q"),
        "quality_factor": fields.get("quality_factor"),
        "adjusted_confidence": fields.get("adjusted_confidence"),
        "v2_score": fields.get("v2_score"),
        "v2_raw_score": fields.get("v2_raw_score"),
        "v2_class": fields.get("v2_class"),
        "paired": bool(paired.get("paired")),
        "strict_paired": bool(paired.get("strict_paired")),
        "pair_alignment_reason": paired.get("pair_alignment_reason"),
        "pair_key": paired.get("pair_key"),
        "v1_source_snapshot_at": paired.get("v1_source_snapshot_at"),
        "v2_source_snapshot_at": paired.get("v2_source_snapshot_at"),
        "v1_execution_quote": paired.get("v1_execution_quote"),
        "v2_execution_quote": paired.get("v2_execution_quote"),
        "v1_status": paired.get("v1_status"),
        "v2_status": paired.get("v2_status"),
        "v1_score_A": paired.get("v1_score_A"),
        "v1_raw_score_A": paired.get("v1_raw_score_A"),
        "v1_class_A": paired.get("v1_class_A"),
        "input_mismatch_fields": (
            ",".join(paired.get("input_mismatch_fields") or [])
            if isinstance(paired.get("input_mismatch_fields"), list)
            else paired.get("input_mismatch_fields")
        ),
        "formula_freeze_sha256": integrity.get("formula_freeze_sha256")
        or pre.get("formula_freeze_sha256"),
        "match_status": post.get("match_status"),
        "ht_home": ht.get("home"),
        "ht_away": ht.get("away"),
        "ft_home": ft.get("home"),
        "ft_away": ft.get("away"),
        "outcome": ev.get("outcome"),
        "evaluation_reason": ev.get("evaluation_reason"),
        "profit_1u": ev.get("profit_1u"),
        "input_fingerprint_sha256": integrity.get("input_fingerprint_sha256"),
        "engine_payload_sha256": integrity.get("engine_payload_sha256"),
    }


def _v1_rank_score(paired: dict[str, Any]) -> float | None:
    raw = paired.get("v1_raw_score_A")
    try:
        if raw is not None:
            return float(raw)
    except (TypeError, ValueError):
        pass
    try:
        sc = paired.get("v1_score_A")
        return float(sc) if sc is not None else None
    except (TypeError, ValueError):
        return None


def _strict_paired_market_items(
    analysis: dict[str, Any],
) -> list[tuple[str, dict[str, Any], dict[str, Any]]]:
    """Same market universe for V1/V2 strict paired top picks."""
    markets = analysis.get("markets") if isinstance(analysis.get("markets"), dict) else {}
    out: list[tuple[str, dict[str, Any], dict[str, Any]]] = []
    for mk in PANEL_MARKET_KEYS:
        item = markets.get(mk)
        if not isinstance(item, dict):
            continue
        paired = item.get("paired_v1") if isinstance(item.get("paired_v1"), dict) else None
        if not paired or paired.get("strict_paired") is not True:
            continue
        out.append((mk, item, paired))
    return out


def _top_v2_strict_paired_from_analysis(analysis: dict[str, Any]) -> dict[str, Any] | None:
    fixture = analysis.get("fixture") if isinstance(analysis.get("fixture"), dict) else {}
    best_mk = None
    best_raw = None
    best_idx = 10**9
    best_item: dict[str, Any] | None = None
    best_paired: dict[str, Any] | None = None
    for mk, item, paired in _strict_paired_market_items(analysis):
        try:
            panel_idx = PANEL_MARKET_KEYS.index(mk)
        except ValueError:
            panel_idx = 10**9
        try:
            raw = float(item["raw_score"]) if item.get("raw_score") is not None else None
        except (TypeError, ValueError):
            raw = None
        if raw is None:
            continue
        if best_raw is None or raw > best_raw or (raw == best_raw and panel_idx < best_idx):
            best_mk = mk
            best_raw = raw
            best_idx = panel_idx
            best_item = item
            best_paired = paired
    if best_mk is None or best_item is None or best_paired is None:
        return None
    ev = best_item.get("evaluation") if isinstance(best_item.get("evaluation"), dict) else {}
    outcome = ev.get("outcome")
    quote = best_paired.get("v2_execution_quote")
    profit = compute_profit_1u_from_quote(
        execution_quote=quote,
        execution_quote_real=best_paired.get("v2_execution_quote_real") is True,
        outcome=str(outcome or ""),
    )
    return {
        "today_fixture_id": fixture.get("today_fixture_id"),
        "provider_fixture_id": fixture.get("provider_fixture_id"),
        "scan_date": fixture.get("scan_date"),
        "holdout_cohort": fixture.get("holdout_cohort"),
        "market_key": best_mk,
        "pair_key": best_paired.get("pair_key"),
        "v2_score": best_item.get("score"),
        "v2_raw_score": best_item.get("raw_score"),
        "outcome": outcome,
        "profit_1u": profit,
        "execution_quote": quote,
        "selection_basis": "strict_paired_v2_raw_score",
    }


def _top_v1_strict_paired_from_analysis(analysis: dict[str, Any]) -> dict[str, Any] | None:
    fixture = analysis.get("fixture") if isinstance(analysis.get("fixture"), dict) else {}
    best_mk = None
    best_score = None
    best_idx = 10**9
    best_item: dict[str, Any] | None = None
    best_paired: dict[str, Any] | None = None
    for mk, item, paired in _strict_paired_market_items(analysis):
        try:
            panel_idx = PANEL_MARKET_KEYS.index(mk)
        except ValueError:
            panel_idx = 10**9
        sc = _v1_rank_score(paired)
        if sc is None:
            continue
        if best_score is None or sc > best_score or (sc == best_score and panel_idx < best_idx):
            best_mk = mk
            best_score = sc
            best_idx = panel_idx
            best_item = item
            best_paired = paired
    if best_mk is None or best_item is None or best_paired is None:
        return None
    ev = best_item.get("evaluation") if isinstance(best_item.get("evaluation"), dict) else {}
    outcome = ev.get("outcome")
    quote = best_paired.get("v1_execution_quote")
    profit = compute_profit_1u_from_quote(
        execution_quote=quote,
        execution_quote_real=best_paired.get("v1_execution_quote_real") is True,
        outcome=str(outcome or ""),
    )
    return {
        "today_fixture_id": fixture.get("today_fixture_id"),
        "provider_fixture_id": fixture.get("provider_fixture_id"),
        "scan_date": fixture.get("scan_date"),
        "holdout_cohort": fixture.get("holdout_cohort"),
        "market_key": best_mk,
        "pair_key": best_paired.get("pair_key"),
        "v1_score_A": best_paired.get("v1_score_A"),
        "v1_raw_score_A": best_paired.get("v1_raw_score_A"),
        "outcome": outcome,
        "profit_1u": profit,
        "execution_quote": quote,
        "selection_basis": "strict_paired_v1_A_score",
    }


def build_range_purchasability_v35_v2_analysis_manifest_and_files(
    db: Session,
    *,
    date_from: date,
    date_to: date,
) -> tuple[dict[str, Any], dict[str, bytes], list[dict[str, Any]]]:
    validate_v2_analysis_date_range(date_from, date_to)
    fixtures = _load_v2_snapshot_population_range(
        db, date_from=date_from, date_to=date_to
    )
    eligible_without_v2 = _count_current_eligible_without_v2_key(
        db, date_from=date_from, date_to=date_to
    )
    generated_at = datetime.now(timezone.utc).isoformat()

    manifest_fixtures: list[dict[str, Any]] = []
    file_entries: dict[str, bytes] = {}
    csv_rows: list[dict[str, Any]] = []
    top_v2_all_rows: list[dict[str, Any]] = []
    top_v2_strict_rows: list[dict[str, Any]] = []
    top_v1_strict_rows: list[dict[str, Any]] = []
    days_summary: dict[str, dict[str, int]] = defaultdict(
        lambda: {
            "snapshot_population_count": 0,
            "valid_v2_snapshots": 0,
            "invalid_v2_snapshots": 0,
            "snapshot_invalid": 0,
            "analysis_included_count": 0,
        }
    )

    eligibility_counter: Counter[str] = Counter()
    valid_current_eligible_count = 0
    valid_current_noneligible_count = 0
    population_current_eligible_count = 0

    summary: dict[str, Any] = {
        "population_inclusion_basis": "persisted_v2_snapshot_key",
        "snapshot_population_count": len(fixtures),
        "v2_key_present_count": len(fixtures),
        "valid_v2_snapshots": 0,
        "invalid_v2_snapshots": 0,
        "snapshot_invalid": 0,
        "analysis_included_count": 0,
        "snapshot_unavailable": 0,
        "eligible_fixtures": 0,
        "valid_current_eligible_count": 0,
        "valid_current_noneligible_count": 0,
        "current_eligibility_counts": {},
        "current_eligible_without_v2_key_count": eligible_without_v2,
        "finished": 0,
        "pending": 0,
        "cancelled": 0,
        "postponed": 0,
        "scored_market_rows": 0,
        "settled_scored_rows": 0,
        "won_scored_rows": 0,
        "lost_scored_rows": 0,
        "analysis_ready": True,
        "formula_freeze_sha256_expected": EXPECTED_FORMULA_FREEZE_SHA256,
        "PRIMARY_DIAGNOSTIC_COHORT": PRIMARY_DIAGNOSTIC_COHORT,
    }

    valid_pairs: list[tuple[CecchinoTodayFixture, dict[str, Any]]] = []

    for row in fixtures:
        scan_key = row.scan_date.isoformat() if row.scan_date else "unknown"
        days_summary[scan_key]["snapshot_population_count"] += 1
        elig = row.eligibility_status
        eligibility_counter[str(elig)] += 1
        if elig == ELIGIBILITY_ELIGIBLE:
            population_current_eligible_count += 1

        output = row.cecchino_output_json if isinstance(row.cecchino_output_json, dict) else {}
        snap = output[SNAPSHOT_OUTPUT_KEY]
        match_status = normalize_match_status(row)
        entry: dict[str, Any] = {
            "today_fixture_id": int(row.id),
            "provider_fixture_id": int(row.provider_fixture_id),
            "scan_date": scan_key,
            "holdout_cohort": holdout_cohort_for_scan_date(row.scan_date),
            "league": row.league_name,
            "country": row.country_name,
            "home_team": row.home_team_name,
            "away_team": row.away_team_name,
            "kickoff": row.kickoff.isoformat() if row.kickoff else None,
            "match_status": match_status,
            "current_eligibility_status": elig,
        }

        if match_status == MATCH_FINISHED:
            summary["finished"] += 1
        elif match_status in {MATCH_UPCOMING, MATCH_LIVE}:
            summary["pending"] += 1
        elif match_status == MATCH_CANCELLED:
            summary["cancelled"] += 1
        elif match_status == MATCH_POSTPONED:
            summary["postponed"] += 1

        check = validate_purchasability_preview_v35_v2_snapshot(snap)
        if not check.get("ok"):
            entry["analysis_status"] = "snapshot_invalid"
            entry["snapshot_invalid_reason"] = check.get("reason")
            summary["invalid_v2_snapshots"] += 1
            summary["snapshot_invalid"] += 1
            days_summary[scan_key]["invalid_v2_snapshots"] += 1
            days_summary[scan_key]["snapshot_invalid"] += 1
            manifest_fixtures.append(entry)
            continue

        summary["valid_v2_snapshots"] += 1
        days_summary[scan_key]["valid_v2_snapshots"] += 1
        if elig == ELIGIBILITY_ELIGIBLE:
            valid_current_eligible_count += 1
        else:
            valid_current_noneligible_count += 1
        valid_pairs.append((row, snap))
        if not _fixture_terminal_for_analysis(row):
            summary["analysis_ready"] = False

        entry.update(
            {
                "analysis_status": "included",
                "source_snapshot_at": snap.get("source_snapshot_at"),
                "generated_at": snap.get("generated_at"),
                "formula_freeze_sha256": snap.get("formula_freeze_sha256"),
                "has_v2_score": fixture_has_v35_v2_score(snap),
                "scored_market_count": _scored_market_count(snap),
            }
        )
        manifest_fixtures.append(entry)

    summary["eligible_fixtures"] = population_current_eligible_count
    summary["valid_current_eligible_count"] = valid_current_eligible_count
    summary["valid_current_noneligible_count"] = valid_current_noneligible_count
    summary["current_eligibility_counts"] = dict(eligibility_counter)

    for row, snap in valid_pairs:
        analysis = build_purchasability_v35_v2_analysis_export(row, snap)
        scan_key = row.scan_date.isoformat() if row.scan_date else "unknown"
        fname = f"purchasability-v35-v2-analysis-{int(row.provider_fixture_id)}.json"
        file_entries[f"days/{scan_key}/{fname}"] = _json_bytes(analysis)
        summary["analysis_included_count"] += 1
        days_summary[scan_key]["analysis_included_count"] += 1

        fixture_block = (
            analysis.get("fixture") if isinstance(analysis.get("fixture"), dict) else {}
        )
        # Inject eligibility into analysis fixture for CSV extraction (export contract unchanged).
        fixture_block["current_eligibility_status"] = row.eligibility_status
        analysis["fixture"] = fixture_block

        markets = analysis.get("markets") if isinstance(analysis.get("markets"), dict) else {}
        for mk in PANEL_MARKET_KEYS:
            item = markets.get(mk)
            if not isinstance(item, dict):
                continue
            csv_rows.append(_csv_row_from_analysis(analysis, market_key=mk, item=item))
            is_scored = str(item.get("status") or "") == "score"
            if is_scored:
                summary["scored_market_rows"] += 1
            ev = item.get("evaluation") if isinstance(item.get("evaluation"), dict) else {}
            if is_scored and ev.get("profit_1u") is not None:
                summary["settled_scored_rows"] += 1
            if is_scored and ev.get("outcome") == EVAL_WON:
                summary["won_scored_rows"] += 1
            elif is_scored and ev.get("outcome") == EVAL_LOST:
                summary["lost_scored_rows"] += 1

        top_v2 = analysis.get("top_v2_market")
        fixture = analysis.get("fixture") if isinstance(analysis.get("fixture"), dict) else {}
        if isinstance(top_v2, dict):
            top_v2_all_rows.append(
                {
                    "today_fixture_id": fixture.get("today_fixture_id"),
                    "provider_fixture_id": fixture.get("provider_fixture_id"),
                    "scan_date": fixture.get("scan_date"),
                    "holdout_cohort": fixture.get("holdout_cohort"),
                    "market_key": top_v2.get("market_key"),
                    "v2_score": top_v2.get("v2_score"),
                    "v2_raw_score": top_v2.get("v2_raw_score"),
                    "outcome": top_v2.get("outcome"),
                    "profit_1u": top_v2.get("profit_1u"),
                    "execution_quote": top_v2.get("execution_quote"),
                }
            )
        top_v2_strict = _top_v2_strict_paired_from_analysis(analysis)
        if top_v2_strict is not None:
            top_v2_strict_rows.append(top_v2_strict)
        top_v1_strict = _top_v1_strict_paired_from_analysis(analysis)
        if top_v1_strict is not None:
            top_v1_strict_rows.append(top_v1_strict)

    assert summary["snapshot_population_count"] == (
        summary["valid_v2_snapshots"] + summary["invalid_v2_snapshots"]
    )

    diagnostics = build_holdout_diagnostics(
        csv_rows,
        top_v2_all_markets_rows=top_v2_all_rows,
        top_v2_strict_paired_rows=top_v2_strict_rows,
        top_v1_strict_paired_rows=top_v1_strict_rows,
    )

    manifest = make_json_safe(
        {
            "contract_version": PURCHASABILITY_V35_V2_ANALYSIS_MANIFEST_CONTRACT_VERSION,
            "analysis_contract_version": PURCHASABILITY_V35_V2_ANALYSIS_EXPORT_CONTRACT_VERSION,
            "date_from": date_from.isoformat(),
            "date_to": date_to.isoformat(),
            "generated_at": generated_at,
            "experiment_version": PURCHASABILITY_V35_V2_EXPERIMENT_VERSION,
            "formula_freeze_sha256_expected": EXPECTED_FORMULA_FREEZE_SHA256,
            "PRIMARY_DIAGNOSTIC_COHORT": PRIMARY_DIAGNOSTIC_COHORT,
            "summary": summary,
            "days": dict(days_summary),
            "fixtures": manifest_fixtures,
            "holdout_diagnostics": diagnostics,
            "terminology": {
                "R": "Base-rate Reliability",
                "base_rate_reliability": "Base-rate Reliability",
            },
            "pre_match_only_snapshot": True,
            "outcome_join_post_freeze_only": True,
        }
    )
    return manifest, file_entries, csv_rows


def build_csv_bytes(csv_rows: list[dict[str, Any]]) -> bytes:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=CSV_COLUMNS, extrasaction="ignore")
    writer.writeheader()
    for row in csv_rows:
        writer.writerow(row)
    return buf.getvalue().encode("utf-8")


def build_range_purchasability_v35_v2_analysis_zip(
    db: Session,
    *,
    date_from: date,
    date_to: date,
) -> tuple[bytes, str]:
    manifest, file_entries, csv_rows = (
        build_range_purchasability_v35_v2_analysis_manifest_and_files(
            db, date_from=date_from, date_to=date_to
        )
    )
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", _json_bytes(manifest))
        archive.writestr("analysis_rows.csv", build_csv_bytes(csv_rows))
        for name in sorted(file_entries):
            archive.writestr(name, file_entries[name])
    filename = (
        f"purchasability-v35-v2-analysis-"
        f"{date_from.isoformat()}_{date_to.isoformat()}.zip"
    )
    return buf.getvalue(), filename


__all__ = [
    "CSV_COLUMNS",
    "MAX_RANGE_DAYS",
    "V35V2AnalysisRangeError",
    "build_csv_bytes",
    "build_range_purchasability_v35_v2_analysis_manifest_and_files",
    "build_range_purchasability_v35_v2_analysis_zip",
    "validate_v2_analysis_date_range",
    "_count_current_eligible_without_v2_key",
    "_load_v2_snapshot_population_range",
]
