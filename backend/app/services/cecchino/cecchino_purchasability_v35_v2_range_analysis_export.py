"""Export range analysis Structural V2 — ZIP read-only + holdout diagnostics."""

from __future__ import annotations

import csv
import io
import json
import zipfile
from collections import defaultdict
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
    "v1_score_A",
    "v1_raw_score_A",
    "v1_class_A",
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


def _load_eligible_fixtures_range(
    db: Session,
    *,
    date_from: date,
    date_to: date,
) -> list[CecchinoTodayFixture]:
    stmt = (
        select(CecchinoTodayFixture)
        .where(
            CecchinoTodayFixture.scan_date >= date_from,
            CecchinoTodayFixture.scan_date <= date_to,
            CecchinoTodayFixture.eligibility_status == ELIGIBILITY_ELIGIBLE,
        )
        .order_by(
            CecchinoTodayFixture.scan_date.asc(), CecchinoTodayFixture.kickoff.asc()
        )
    )
    return list(db.scalars(stmt).all())


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
        "v1_score_A": paired.get("v1_score_A"),
        "v1_raw_score_A": paired.get("v1_raw_score_A"),
        "v1_class_A": paired.get("v1_class_A"),
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


def _top_v1_from_analysis(analysis: dict[str, Any]) -> dict[str, Any] | None:
    """Top V1 A among paired scored markets — select pre-match then attach outcome."""
    markets = analysis.get("markets") if isinstance(analysis.get("markets"), dict) else {}
    fixture = analysis.get("fixture") if isinstance(analysis.get("fixture"), dict) else {}
    best_mk = None
    best_score = None
    best_idx = 10**9
    for idx, mk in enumerate(PANEL_MARKET_KEYS):
        item = markets.get(mk)
        if not isinstance(item, dict) or str(item.get("status") or "") != "score":
            continue
        paired = item.get("paired_v1") if isinstance(item.get("paired_v1"), dict) else None
        if not paired:
            continue
        try:
            sc = float(paired.get("v1_score_A"))
        except (TypeError, ValueError):
            continue
        if best_score is None or sc > best_score or (sc == best_score and idx < best_idx):
            best_mk = mk
            best_score = sc
            best_idx = idx
    if best_mk is None:
        return None
    item = markets[best_mk]
    paired = item.get("paired_v1") or {}
    ev = item.get("evaluation") if isinstance(item.get("evaluation"), dict) else {}
    inp = item.get("input") if isinstance(item.get("input"), dict) else {}
    return {
        "today_fixture_id": fixture.get("today_fixture_id"),
        "provider_fixture_id": fixture.get("provider_fixture_id"),
        "scan_date": fixture.get("scan_date"),
        "holdout_cohort": fixture.get("holdout_cohort"),
        "market_key": best_mk,
        "v1_score_A": paired.get("v1_score_A"),
        "v1_raw_score_A": paired.get("v1_raw_score_A"),
        "outcome": ev.get("outcome"),
        "profit_1u": ev.get("profit_1u"),
        "execution_quote": inp.get("execution_quote"),
    }


def build_range_purchasability_v35_v2_analysis_manifest_and_files(
    db: Session,
    *,
    date_from: date,
    date_to: date,
) -> tuple[dict[str, Any], dict[str, bytes], list[dict[str, Any]]]:
    validate_v2_analysis_date_range(date_from, date_to)
    fixtures = _load_eligible_fixtures_range(db, date_from=date_from, date_to=date_to)
    generated_at = datetime.now(timezone.utc).isoformat()

    manifest_fixtures: list[dict[str, Any]] = []
    file_entries: dict[str, bytes] = {}
    csv_rows: list[dict[str, Any]] = []
    top_v2_rows: list[dict[str, Any]] = []
    top_v1_rows: list[dict[str, Any]] = []
    days_summary: dict[str, dict[str, int]] = defaultdict(
        lambda: {
            "eligible_fixtures": 0,
            "valid_v2_snapshots": 0,
            "snapshot_unavailable": 0,
            "snapshot_invalid": 0,
        }
    )

    summary = {
        "eligible_fixtures": len(fixtures),
        "valid_v2_snapshots": 0,
        "snapshot_unavailable": 0,
        "snapshot_invalid": 0,
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
        days_summary[scan_key]["eligible_fixtures"] += 1
        output = row.cecchino_output_json if isinstance(row.cecchino_output_json, dict) else {}
        snap = output.get(SNAPSHOT_OUTPUT_KEY)
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
        }

        if match_status == MATCH_FINISHED:
            summary["finished"] += 1
        elif match_status in {MATCH_UPCOMING, MATCH_LIVE}:
            summary["pending"] += 1
        elif match_status == MATCH_CANCELLED:
            summary["cancelled"] += 1
        elif match_status == MATCH_POSTPONED:
            summary["postponed"] += 1

        if not isinstance(snap, dict):
            entry["analysis_status"] = "snapshot_unavailable"
            summary["snapshot_unavailable"] += 1
            days_summary[scan_key]["snapshot_unavailable"] += 1
            manifest_fixtures.append(entry)
            continue

        check = validate_purchasability_preview_v35_v2_snapshot(snap)
        if not check.get("ok"):
            entry["analysis_status"] = "snapshot_invalid"
            entry["snapshot_invalid_reason"] = check.get("reason")
            summary["snapshot_invalid"] += 1
            days_summary[scan_key]["snapshot_invalid"] += 1
            manifest_fixtures.append(entry)
            continue

        summary["valid_v2_snapshots"] += 1
        days_summary[scan_key]["valid_v2_snapshots"] += 1
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

    for row, snap in valid_pairs:
        analysis = build_purchasability_v35_v2_analysis_export(row, snap)
        scan_key = row.scan_date.isoformat() if row.scan_date else "unknown"
        fname = f"purchasability-v35-v2-analysis-{int(row.provider_fixture_id)}.json"
        file_entries[f"days/{scan_key}/{fname}"] = _json_bytes(analysis)

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
            top_v2_rows.append(
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
        top_v1 = _top_v1_from_analysis(analysis)
        if top_v1 is not None:
            top_v1_rows.append(top_v1)

    diagnostics = build_holdout_diagnostics(
        csv_rows,
        top_v2_fixture_rows=top_v2_rows,
        top_v1_fixture_rows=top_v1_rows,
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
]
