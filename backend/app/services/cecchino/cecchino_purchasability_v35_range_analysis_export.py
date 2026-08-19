"""Export range analysis Acquistabilità V3.5 — ZIP read-only con manifest + CSV + JSON giornalieri."""

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

from app.models.cecchino_signal_activation import (
    EVAL_LOST,
    EVAL_NOT_EVALUABLE,
    EVAL_PENDING,
    EVAL_RESULT_MISSING,
    EVAL_WON,
)
from app.models.cecchino_today_fixture import (
    ELIGIBILITY_ELIGIBLE,
    MATCH_CANCELLED,
    MATCH_FINISHED,
    MATCH_LIVE,
    MATCH_POSTPONED,
    MATCH_UPCOMING,
    CecchinoTodayFixture,
)
from app.schemas.cecchino_purchasability_v35 import (
    PURCHASABILITY_V35_ANALYSIS_EXPORT_CONTRACT_VERSION,
    PURCHASABILITY_V35_ANALYSIS_MANIFEST_CONTRACT_VERSION,
    PURCHASABILITY_V35_EXPERIMENT_VERSION,
)
from app.services.cecchino.cecchino_market_opposition import PANEL_MARKET_KEYS
from app.services.cecchino.cecchino_purchasability_audit import make_json_safe
from app.services.cecchino.cecchino_purchasability_v35_analysis_evaluation import (
    normalize_match_status,
)
from app.services.cecchino.cecchino_purchasability_v35_analysis_export import (
    build_purchasability_v35_analysis_export,
)
from app.services.cecchino.cecchino_purchasability_v35_snapshot import (
    fixture_has_v35_score,
    validate_purchasability_preview_v35_snapshot,
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
    "hours_to_kickoff",
    "market_key",
    "market_label",
    "market_status",
    "gate_status",
    "gate_reason_codes",
    "execution_quote",
    "execution_quote_real",
    "execution_quote_source",
    "probability_cecchino",
    "fair_book_probability",
    "rating",
    "overround",
    "book_fallback_used",
    "fair_probability_may_be_derived",
    "V",
    "D",
    "S",
    "S_raw",
    "S_confidence",
    "S_coverage",
    "Q",
    "score_A",
    "raw_A",
    "class_A",
    "score_B",
    "raw_B",
    "class_B",
    "score_C",
    "raw_C",
    "class_C",
    "score_D",
    "raw_D",
    "class_D",
    "match_status",
    "ht_home",
    "ht_away",
    "ft_home",
    "ft_away",
    "outcome",
    "evaluation_reason",
    "profit_1u",
    "break_even_probability",
    "input_fingerprint_sha256",
    "engine_payload_sha256",
]


class V35AnalysisRangeError(ValueError):
    """Errore validazione range date analysis export."""


def validate_analysis_date_range(date_from: date, date_to: date) -> None:
    if date_from > date_to:
        raise V35AnalysisRangeError("date_from must be <= date_to")
    span = (date_to - date_from).days + 1
    if span > MAX_RANGE_DAYS:
        raise V35AnalysisRangeError(
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
        .order_by(CecchinoTodayFixture.scan_date.asc(), CecchinoTodayFixture.kickoff.asc())
    )
    return list(db.scalars(stmt).all())


def _json_bytes(payload: Any) -> bytes:
    safe = make_json_safe(payload)
    return json.dumps(safe, indent=2, ensure_ascii=False).encode("utf-8")


def _scored_market_count(snapshot: dict[str, Any]) -> int:
    count = 0
    for item in snapshot.get("items") or []:
        if isinstance(item, dict) and item.get("status") == "score":
            count += 1
    return count


def _gate_reason_codes(gate: dict[str, Any] | None) -> str:
    if not isinstance(gate, dict):
        return ""
    codes = gate.get("reason_codes")
    if isinstance(codes, list):
        return "|".join(str(c) for c in codes)
    return ""


def _component_score(components: dict[str, Any] | None, key: str, field: str = "score") -> Any:
    if not isinstance(components, dict):
        return None
    block = components.get(key)
    if not isinstance(block, dict):
        return None
    return block.get(field)


def _candidate_fields(candidates: dict[str, Any] | None, ck: str) -> tuple[Any, Any, Any]:
    if not isinstance(candidates, dict):
        return None, None, None
    cand = candidates.get(ck)
    if not isinstance(cand, dict):
        return None, None, None
    return cand.get("score"), cand.get("raw_score"), cand.get("class")


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
    inp = item.get("input") if isinstance(item.get("input"), dict) else {}
    gate = item.get("gate") if isinstance(item.get("gate"), dict) else {}
    components = item.get("components") if isinstance(item.get("components"), dict) else {}
    diagnostics = item.get("diagnostics") if isinstance(item.get("diagnostics"), dict) else {}
    candidates = item.get("candidates") if isinstance(item.get("candidates"), dict) else {}
    ev = item.get("evaluation") if isinstance(item.get("evaluation"), dict) else {}
    ht = post.get("halftime") if isinstance(post.get("halftime"), dict) else {}
    ft = post.get("fulltime") if isinstance(post.get("fulltime"), dict) else {}

    s_block = components.get("structural_coherence")
    s_raw = s_conf = s_cov = None
    if isinstance(s_block, dict):
        s_raw = s_block.get("raw_score")
        s_conf = s_block.get("confidence")
        s_cov = s_block.get("coverage")

    score_a, raw_a, class_a = _candidate_fields(candidates, "A")
    score_b, raw_b, class_b = _candidate_fields(candidates, "B")
    score_c, raw_c, class_c = _candidate_fields(candidates, "C")
    score_d, raw_d, class_d = _candidate_fields(candidates, "D")

    return {
        "scan_date": fixture.get("scan_date"),
        "today_fixture_id": fixture.get("today_fixture_id"),
        "provider_fixture_id": fixture.get("provider_fixture_id"),
        "country": fixture.get("country"),
        "league": fixture.get("league"),
        "home_team": fixture.get("home_team"),
        "away_team": fixture.get("away_team"),
        "kickoff": fixture.get("kickoff"),
        "source_snapshot_at": pre.get("source_snapshot_at"),
        "hours_to_kickoff": diagnostics.get("hours_to_kickoff"),
        "market_key": market_key,
        "market_label": item.get("label"),
        "market_status": item.get("status"),
        "gate_status": item.get("gate_status"),
        "gate_reason_codes": _gate_reason_codes(gate),
        "execution_quote": inp.get("execution_quote"),
        "execution_quote_real": inp.get("execution_quote_real"),
        "execution_quote_source": inp.get("execution_quote_source"),
        "probability_cecchino": inp.get("probability_cecchino"),
        "fair_book_probability": inp.get("fair_book_probability"),
        "rating": inp.get("rating"),
        "overround": inp.get("overround"),
        "book_fallback_used": inp.get("book_fallback_used"),
        "fair_probability_may_be_derived": inp.get("fair_probability_may_be_derived"),
        "V": _component_score(components, "executable_value"),
        "D": _component_score(components, "market_disagreement"),
        "S": _component_score(components, "structural_coherence"),
        "S_raw": s_raw,
        "S_confidence": s_conf,
        "S_coverage": s_cov,
        "Q": _component_score(components, "information_quality"),
        "score_A": score_a,
        "raw_A": raw_a,
        "class_A": class_a,
        "score_B": score_b,
        "raw_B": raw_b,
        "class_B": class_b,
        "score_C": score_c,
        "raw_C": raw_c,
        "class_C": class_c,
        "score_D": score_d,
        "raw_D": raw_d,
        "class_D": class_d,
        "match_status": post.get("match_status"),
        "ht_home": ht.get("home"),
        "ht_away": ht.get("away"),
        "ft_home": ft.get("home"),
        "ft_away": ft.get("away"),
        "outcome": ev.get("outcome"),
        "evaluation_reason": ev.get("evaluation_reason"),
        "profit_1u": ev.get("profit_1u"),
        "break_even_probability": ev.get("break_even_probability"),
        "input_fingerprint_sha256": integrity.get("input_fingerprint_sha256"),
        "engine_payload_sha256": integrity.get("engine_payload_sha256"),
    }


def _fixture_terminal_for_analysis(row: CecchinoTodayFixture) -> bool:
    """True se fixture terminalmente valutabile per analysis_ready."""
    status = normalize_match_status(row)
    if status in {MATCH_CANCELLED, MATCH_POSTPONED}:
        return True
    if status != MATCH_FINISHED:
        return False
    match_result = {
        "halftime": {
            "home": row.score_halftime_home,
            "away": row.score_halftime_away,
            "available": row.score_halftime_home is not None
            and row.score_halftime_away is not None,
        },
        "fulltime": {
            "home": row.score_fulltime_home,
            "away": row.score_fulltime_away,
            "available": row.score_fulltime_home is not None
            and row.score_fulltime_away is not None,
        },
    }
    return bool(match_result["fulltime"]["available"])


def build_range_purchasability_v35_analysis_manifest_and_files(
    db: Session,
    *,
    date_from: date,
    date_to: date,
) -> tuple[dict[str, Any], dict[str, bytes], list[dict[str, Any]]]:
    """Costruisce manifest + file ZIP + righe CSV per range analysis V3.5."""
    validate_analysis_date_range(date_from, date_to)
    fixtures = _load_eligible_fixtures_range(db, date_from=date_from, date_to=date_to)
    generated_at = datetime.now(timezone.utc).isoformat()

    manifest_fixtures: list[dict[str, Any]] = []
    file_entries: dict[str, bytes] = {}
    csv_rows: list[dict[str, Any]] = []
    days_summary: dict[str, dict[str, int]] = defaultdict(
        lambda: {
            "eligible_fixtures": 0,
            "valid_v35_snapshots": 0,
            "snapshot_unavailable": 0,
            "snapshot_invalid": 0,
        }
    )

    summary = {
        "eligible_fixtures": len(fixtures),
        "valid_v35_snapshots": 0,
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
        "result_missing_scored_rows": 0,
        "analysis_ready": True,
    }

    valid_fixture_rows: list[tuple[CecchinoTodayFixture, dict[str, Any]]] = []

    for row in fixtures:
        scan_key = row.scan_date.isoformat() if row.scan_date else "unknown"
        days_summary[scan_key]["eligible_fixtures"] += 1

        output = row.cecchino_output_json if isinstance(row.cecchino_output_json, dict) else {}
        v35_snapshot = output.get("purchasability_preview_v35")
        match_status = normalize_match_status(row)

        entry: dict[str, Any] = {
            "today_fixture_id": int(row.id),
            "provider_fixture_id": int(row.provider_fixture_id),
            "scan_date": scan_key,
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

        if not isinstance(v35_snapshot, dict):
            entry["analysis_status"] = "snapshot_unavailable"
            summary["snapshot_unavailable"] += 1
            days_summary[scan_key]["snapshot_unavailable"] += 1
            manifest_fixtures.append(entry)
            continue

        check = validate_purchasability_preview_v35_snapshot(v35_snapshot)
        if not check.get("ok"):
            entry["analysis_status"] = "snapshot_invalid"
            entry["snapshot_invalid_reason"] = check.get("reason")
            summary["snapshot_invalid"] += 1
            days_summary[scan_key]["snapshot_invalid"] += 1
            manifest_fixtures.append(entry)
            continue

        summary["valid_v35_snapshots"] += 1
        days_summary[scan_key]["valid_v35_snapshots"] += 1
        valid_fixture_rows.append((row, v35_snapshot))

        if not _fixture_terminal_for_analysis(row):
            summary["analysis_ready"] = False

        has_score = fixture_has_v35_score(v35_snapshot)
        entry.update(
            {
                "analysis_status": "included",
                "source_snapshot_at": v35_snapshot.get("source_snapshot_at"),
                "input_fingerprint_sha256": v35_snapshot.get("input_fingerprint_sha256"),
                "engine_payload_sha256": v35_snapshot.get("engine_payload_sha256"),
                "has_v35_score": has_score,
                "scored_market_count": _scored_market_count(v35_snapshot),
            }
        )
        manifest_fixtures.append(entry)

    for row, v35_snapshot in valid_fixture_rows:
        analysis = build_purchasability_v35_analysis_export(row, v35_snapshot)
        scan_key = row.scan_date.isoformat() if row.scan_date else "unknown"
        filename = f"purchasability-v35-analysis-{int(row.provider_fixture_id)}.json"
        file_entries[f"days/{scan_key}/{filename}"] = _json_bytes(analysis)

        markets = analysis.get("markets") if isinstance(analysis.get("markets"), dict) else {}
        for mk in PANEL_MARKET_KEYS:
            item = markets.get(mk)
            if not isinstance(item, dict):
                continue
            csv_rows.append(_csv_row_from_analysis(analysis, market_key=mk, item=item))
            if str(item.get("status") or "") == "score":
                summary["scored_market_rows"] += 1
            ev = item.get("evaluation") if isinstance(item.get("evaluation"), dict) else {}
            outcome = ev.get("outcome")
            profit = ev.get("profit_1u")
            if profit is not None:
                summary["settled_scored_rows"] += 1
            if outcome == EVAL_WON:
                summary["won_scored_rows"] += 1
            elif outcome == EVAL_LOST:
                summary["lost_scored_rows"] += 1
            elif outcome == EVAL_RESULT_MISSING:
                summary["result_missing_scored_rows"] += 1

    manifest = make_json_safe(
        {
            "contract_version": PURCHASABILITY_V35_ANALYSIS_MANIFEST_CONTRACT_VERSION,
            "analysis_contract_version": PURCHASABILITY_V35_ANALYSIS_EXPORT_CONTRACT_VERSION,
            "date_from": date_from.isoformat(),
            "date_to": date_to.isoformat(),
            "generated_at": generated_at,
            "experiment_version": PURCHASABILITY_V35_EXPERIMENT_VERSION,
            "summary": summary,
            "days": dict(days_summary),
            "fixtures": manifest_fixtures,
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


def build_range_purchasability_v35_analysis_zip(
    db: Session,
    *,
    date_from: date,
    date_to: date,
) -> tuple[bytes, str]:
    """Assembla ZIP purchasability-v35-analysis-{from}_{to}.zip."""
    manifest, file_entries, csv_rows = build_range_purchasability_v35_analysis_manifest_and_files(
        db, date_from=date_from, date_to=date_to
    )
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", _json_bytes(manifest))
        archive.writestr("analysis_rows.csv", build_csv_bytes(csv_rows))
        for name in sorted(file_entries):
            archive.writestr(name, file_entries[name])
    filename = (
        f"purchasability-v35-analysis-{date_from.isoformat()}_{date_to.isoformat()}.zip"
    )
    return buf.getvalue(), filename


__all__ = [
    "CSV_COLUMNS",
    "MAX_RANGE_DAYS",
    "V35AnalysisRangeError",
    "build_csv_bytes",
    "build_range_purchasability_v35_analysis_manifest_and_files",
    "build_range_purchasability_v35_analysis_zip",
    "validate_analysis_date_range",
]
