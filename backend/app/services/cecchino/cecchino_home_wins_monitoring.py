"""Monitoraggio storico esito reale 1 (vittorie casalinghe) — snapshot-only, read-only.

La coorte dipende esclusivamente da stato finished + punteggio FT casa > trasferta.
Il Segnale 1 non è mai usato per la selezione.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import zipfile
from collections import Counter
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.models.cecchino_goal_intensity_v5_preview import (
    CecchinoGoalIntensityV5PreviewSnapshot,
)
from app.models.cecchino_today_fixture import MATCH_FINISHED, CecchinoTodayFixture
from app.services.cecchino.cecchino_purchasability_audit import make_json_safe
from app.services.cecchino.cecchino_selection_keys import SEL_AWAY, SEL_DRAW, SEL_HOME

DATASET_VERSION = "cecchino_home_wins_monitoring_v1"
CSV_SCHEMA_VERSION = "cecchino_home_wins_features_csv_v1"
COHORT_ID = "finished_home_wins"
SELECTION_CONTRACT = {
    "cohort": COHORT_ID,
    "outcome": "1",
    "signal_1_used_for_selection": False,
    "inclusion_rule": (
        "match_display_status=finished AND fulltime_home > fulltime_away "
        "with scores available; eligibility/signals/edge/odds never used for selection"
    ),
}

COMPLETENESS_COMPLETE = "complete"
COMPLETENESS_PARTIAL = "partial"
RESULT_SOURCE_FULLTIME = "score_fulltime"
RESULT_SOURCE_GOALS_FALLBACK = "goals_fallback"

_CSV_COLUMNS: list[str] = [
    "today_fixture_id",
    "provider_fixture_id",
    "local_fixture_id",
    "competition_id",
    "scan_date",
    "kickoff",
    "country",
    "league",
    "home_team",
    "away_team",
    "ft_home",
    "ft_away",
    "ht_home",
    "ht_away",
    "goal_difference",
    "total_goals",
    "outcome_1x2",
    "result_source",
    "eligibility_status",
    "completeness_status",
    "pre_match_snapshot_timestamp",
    "pre_match_verified",
    "has_kpi",
    "has_balance",
    "has_goal_intensity_v5",
    "has_odds",
    "has_stats",
    "has_xg_profiles",
    "cecchino_version",
    "kpi_version",
    "balance_snapshot_version",
    "goal_intensity_version",
    "cecchino_quota_1",
    "cecchino_quota_x",
    "cecchino_quota_2",
    "cecchino_prob_1",
    "cecchino_prob_x",
    "cecchino_prob_2",
    "kpi_1_quota_book",
    "kpi_1_quota_cecchino",
    "kpi_1_prob_book",
    "kpi_1_prob_cecchino",
    "kpi_1_vantaggio_prob",
    "kpi_1_edge",
    "kpi_1_score_acquisto",
    "kpi_1_rating",
    "kpi_1_rating_label",
    "kpi_1_status",
    "kpi_x_quota_book",
    "kpi_x_quota_cecchino",
    "kpi_x_prob_book",
    "kpi_x_prob_cecchino",
    "kpi_x_vantaggio_prob",
    "kpi_x_edge",
    "kpi_x_score_acquisto",
    "kpi_x_rating",
    "kpi_x_rating_label",
    "kpi_x_status",
    "kpi_2_quota_book",
    "kpi_2_quota_cecchino",
    "kpi_2_prob_book",
    "kpi_2_prob_cecchino",
    "kpi_2_vantaggio_prob",
    "kpi_2_edge",
    "kpi_2_score_acquisto",
    "kpi_2_rating",
    "kpi_2_rating_label",
    "kpi_2_status",
    "purchasability_1_score",
    "purchasability_1_class",
    "purchasability_1_status",
    "purchasability_x_score",
    "purchasability_x_class",
    "purchasability_x_status",
    "purchasability_2_score",
    "purchasability_2_class",
    "purchasability_2_status",
    "balance_f36_index",
    "balance_f36_class",
    "balance_dominance_index",
    "balance_dominance_class",
    "balance_dominance_direction",
    "balance_draw_credibility_index",
    "balance_draw_credibility_class",
    "balance_gap_index",
    "balance_gap_class",
    "balance_prob_1_norm",
    "balance_prob_x_norm",
    "balance_prob_2_norm",
    "balance_book_prob_1",
    "balance_book_prob_x",
    "balance_book_prob_2",
    "balance_book_verified",
    "balance_pre_match_verified",
    "balance_source_mode",
    "balance_source_cohort",
    "balance_warning_codes",
    "gi_v5_primary_candidate_score",
    "gi_v5_challenger_candidate_score",
    "gi_v5_benchmark_score",
    "gi_v5_diagnostic_score",
    "gi_v5_expected_total_goals",
    "gi_v5_probability_goals_ge_2",
    "gi_v5_probability_goals_ge_3",
    "gi_v5_probability_btts",
    "gi_v5_history_sample_size",
    "gi_v5_xg_status",
    "gi_v5_preview_status",
    "gi_v5_source_snapshot_timestamp",
    "gi_v5_source_snapshot_before_kickoff",
    "gi_v5_no_target_used_in_score",
]


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _json_bytes(payload: Any) -> bytes:
    safe = make_json_safe(payload)
    return json.dumps(safe, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode(
        "utf-8"
    )


def _resolve_match_status(row: CecchinoTodayFixture) -> str:
    status = getattr(row, "match_display_status", None)
    if isinstance(status, str) and status.strip():
        return status.strip().lower()
    return ""


def classify_finished_home_win(row: CecchinoTodayFixture) -> dict[str, Any] | None:
    """Classifica una vittoria casalinga finished. None se fuori coorte."""
    if _resolve_match_status(row) != MATCH_FINISHED:
        return None

    result_source = RESULT_SOURCE_FULLTIME
    ft_home = row.score_fulltime_home
    ft_away = row.score_fulltime_away
    if ft_home is None or ft_away is None:
        if row.goals_home is not None and row.goals_away is not None:
            ft_home = row.goals_home
            ft_away = row.goals_away
            result_source = RESULT_SOURCE_GOALS_FALLBACK
        else:
            return None

    try:
        ft_home_i = int(ft_home)
        ft_away_i = int(ft_away)
    except (TypeError, ValueError):
        return None

    if ft_home_i <= ft_away_i:
        return None

    return {
        "ft_home": ft_home_i,
        "ft_away": ft_away_i,
        "ht_home": row.score_halftime_home,
        "ht_away": row.score_halftime_away,
        "goal_difference": ft_home_i - ft_away_i,
        "total_goals": ft_home_i + ft_away_i,
        "outcome_1x2": "1",
        "result_source": result_source,
    }


def _output_dict(row: CecchinoTodayFixture) -> dict[str, Any]:
    output = row.cecchino_output_json
    return output if isinstance(output, dict) else {}


def _persisted_balance_snapshot(row: CecchinoTodayFixture) -> dict[str, Any]:
    """Solo snapshot persistito — nessun derived/rebuild."""
    persisted = _output_dict(row).get("balance_v5_monitoring")
    if isinstance(persisted, dict) and persisted:
        status = str(persisted.get("status") or "").strip().lower()
        if status == "unavailable":
            return {
                "status": "unavailable",
                "reason": "persisted_balance_snapshot_unavailable",
                **{k: v for k, v in persisted.items() if k not in {"status", "reason"}},
            }
        if (
            persisted.get("f36_index") is not None
            or persisted.get("prob_1_norm") is not None
            or persisted.get("pillars")
            or status in {"ok", "available"}
        ):
            payload = dict(persisted)
            payload.setdefault("status", "ok")
            return payload
    return {
        "status": "unavailable",
        "reason": "persisted_balance_snapshot_missing",
    }


def _persisted_kpi(row: CecchinoTodayFixture) -> dict[str, Any] | None:
    panel = row.kpi_panel_json
    if isinstance(panel, dict) and panel:
        return panel
    return None


def _persisted_purchasability(row: CecchinoTodayFixture) -> dict[str, Any]:
    preview = _output_dict(row).get("purchasability_preview")
    if isinstance(preview, dict) and preview:
        return preview
    return {
        "status": "unavailable",
        "reason": "persisted_purchasability_preview_missing",
    }


def _extract_odds_snapshot_at(row: CecchinoTodayFixture) -> str | None:
    odds = row.odds_snapshot_json if isinstance(row.odds_snapshot_json, dict) else {}
    meta = odds.get("odds_meta") if isinstance(odds.get("odds_meta"), dict) else {}
    for key in ("odds_fetched_at", "odds_cached_at", "snapshot_at", "fetched_at"):
        val = meta.get(key) or odds.get(key)
        if val:
            return str(val)
    output = _output_dict(row)
    dq = output.get("data_quality") if isinstance(output.get("data_quality"), dict) else {}
    leak = dq.get("leakage_check") if isinstance(dq.get("leakage_check"), dict) else {}
    for key in ("odds_fetched_at", "snapshot_at"):
        if leak.get(key):
            return str(leak.get(key))
    return None


def _pre_match_verified(row: CecchinoTodayFixture) -> bool | None:
    ts = _extract_odds_snapshot_at(row)
    kickoff = row.kickoff
    if not ts or kickoff is None:
        return None
    try:
        parsed = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        ko = kickoff if kickoff.tzinfo else kickoff.replace(tzinfo=timezone.utc)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed < ko
    except (TypeError, ValueError):
        return None


def _gi_snapshot_payload(snap: CecchinoGoalIntensityV5PreviewSnapshot | None) -> dict[str, Any]:
    if snap is None:
        return {
            "status": "unavailable",
            "reason": "persisted_goal_intensity_v5_snapshot_missing",
        }
    calibrated = (
        snap.calibrated_predictions_payload
        if isinstance(snap.calibrated_predictions_payload, dict)
        else {}
    )
    primary_cal = calibrated.get("GI_A_STRICT_CORE")
    if not isinstance(primary_cal, dict):
        primary_cal = next((v for v in calibrated.values() if isinstance(v, dict)), {}) or {}

    before_ko: bool | None = None
    if snap.source_snapshot_at and snap.kickoff:
        try:
            src = snap.source_snapshot_at
            ko = snap.kickoff
            if src.tzinfo is None:
                src = src.replace(tzinfo=timezone.utc)
            if ko.tzinfo is None:
                ko = ko.replace(tzinfo=timezone.utc)
            before_ko = src < ko
        except (TypeError, ValueError):
            before_ko = None

    return {
        "status": "ok",
        "snapshot_id": snap.id,
        "bundle_id": snap.bundle_id,
        "preview_status": snap.preview_status,
        "snapshot_status": snap.snapshot_status,
        "primary_candidate_score": snap.primary_candidate_score,
        "challenger_candidate_score": snap.challenger_candidate_score,
        "benchmark_score": snap.benchmark_score,
        "diagnostic_score": snap.diagnostic_score,
        "expected_total_goals": primary_cal.get("expected_total_goals"),
        "probability_goals_ge_2": primary_cal.get("probability_goals_ge_2"),
        "probability_goals_ge_3": primary_cal.get("probability_goals_ge_3"),
        "probability_btts": primary_cal.get("probability_btts"),
        "history_sample_size": snap.history_sample_size,
        "xg_status": snap.xg_status,
        "source_snapshot_at": _iso(snap.source_snapshot_at),
        "source_snapshot_before_kickoff": before_ko,
        "no_target_used_in_score": snap.no_target_used_in_score,
        "feature_status": snap.feature_status,
        "candidate_scores": snap.candidate_scores_payload,
        "pillar_scores": snap.pillar_scores_payload,
        "calibrated_predictions": snap.calibrated_predictions_payload,
        "feature_payload": snap.feature_payload,
        "diagnostic_reason_codes": snap.diagnostic_reason_codes,
    }


def _load_gi_snapshots_bulk(
    db: Session, today_fixture_ids: list[int]
) -> dict[int, CecchinoGoalIntensityV5PreviewSnapshot]:
    """Una query bulk; in caso di multipli snapshot per id prende l'id più alto."""
    if not today_fixture_ids:
        return {}
    rows = list(
        db.scalars(
            select(CecchinoGoalIntensityV5PreviewSnapshot)
            .where(
                CecchinoGoalIntensityV5PreviewSnapshot.today_fixture_id.in_(
                    today_fixture_ids
                )
            )
            .order_by(
                CecchinoGoalIntensityV5PreviewSnapshot.today_fixture_id.asc(),
                CecchinoGoalIntensityV5PreviewSnapshot.id.desc(),
            )
        ).all()
    )
    out: dict[int, CecchinoGoalIntensityV5PreviewSnapshot] = {}
    for snap in rows:
        tid = int(snap.today_fixture_id)
        if tid not in out:
            out[tid] = snap
    return out


def _module_availability(
    row: CecchinoTodayFixture,
    gi_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    kpi = _persisted_kpi(row)
    balance = _persisted_balance_snapshot(row)
    purch = _persisted_purchasability(row)
    gi = gi_payload if gi_payload is not None else {
        "status": "unavailable",
        "reason": "persisted_goal_intensity_v5_snapshot_missing",
    }
    has_kpi = kpi is not None
    has_balance = str(balance.get("status") or "").lower() not in {"", "unavailable"}
    has_gi = str(gi.get("status") or "").lower() not in {"", "unavailable"}
    has_odds = isinstance(row.odds_snapshot_json, dict) and bool(row.odds_snapshot_json)
    has_stats = isinstance(row.stats_snapshot_json, dict) and bool(row.stats_snapshot_json)
    has_xg = isinstance(row.xg_profiles_json, dict) and bool(row.xg_profiles_json)
    has_purch = str(purch.get("status") or "").lower() not in {"", "unavailable"}

    missing: list[str] = []
    if not has_kpi:
        missing.append("kpi_panel")
    if not has_balance:
        missing.append("balance_v5_monitoring")
    if not has_gi:
        missing.append("goal_intensity_v5")
    if not has_odds:
        missing.append("odds_snapshot")
    if not has_stats:
        missing.append("stats_snapshot")

    completeness = COMPLETENESS_COMPLETE if not missing else COMPLETENESS_PARTIAL
    return {
        "has_kpi": has_kpi,
        "has_balance": has_balance,
        "has_goal_intensity_v5": has_gi,
        "has_odds": has_odds,
        "has_stats": has_stats,
        "has_xg_profiles": has_xg,
        "has_purchasability": has_purch,
        "completeness_status": completeness,
        "missing_modules": missing,
        "kpi_availability": "available" if has_kpi else "unavailable",
        "balance_availability": "available" if has_balance else "unavailable",
        "goal_intensity_availability": "available" if has_gi else "unavailable",
    }


def _signal_1_was_active(output: dict[str, Any]) -> bool | None:
    matrix = output.get("signals_matrix")
    if not isinstance(matrix, dict):
        return None
    rows = matrix.get("rows") or []
    if not isinstance(rows, list):
        return None
    for row in rows:
        if not isinstance(row, dict):
            continue
        key = str(row.get("key") or "").lower()
        label = str(row.get("label") or "").strip()
        if key not in {"one", "home"} and label not in {"1", "HOME"}:
            continue
        signals = row.get("signals") if isinstance(row.get("signals"), dict) else {}
        for col, val in signals.items():
            if str(val).strip().upper() == "SI":
                return True
        # also accept active/flag style
        if row.get("active") is True or str(row.get("status") or "").upper() == "SI":
            return True
        return False
    return None


def evaluate_completeness_for_row(
    row: CecchinoTodayFixture,
    *,
    gi_snap: CecchinoGoalIntensityV5PreviewSnapshot | None = None,
) -> dict[str, Any]:
    gi_payload = _gi_snapshot_payload(gi_snap)
    return _module_availability(row, gi_payload)


def _base_filters(
    *,
    date_from: date | None = None,
    date_to: date | None = None,
    competition_id: int | None = None,
    country: str | None = None,
    league: str | None = None,
    team: str | None = None,
) -> list[Any]:
    clauses: list[Any] = [
        CecchinoTodayFixture.match_display_status == MATCH_FINISHED,
        or_(
            and_(
                CecchinoTodayFixture.score_fulltime_home.is_not(None),
                CecchinoTodayFixture.score_fulltime_away.is_not(None),
                CecchinoTodayFixture.score_fulltime_home
                > CecchinoTodayFixture.score_fulltime_away,
            ),
            and_(
                CecchinoTodayFixture.score_fulltime_home.is_(None),
                CecchinoTodayFixture.score_fulltime_away.is_(None),
                CecchinoTodayFixture.goals_home.is_not(None),
                CecchinoTodayFixture.goals_away.is_not(None),
                CecchinoTodayFixture.goals_home > CecchinoTodayFixture.goals_away,
            ),
        ),
    ]
    if date_from is not None:
        clauses.append(CecchinoTodayFixture.scan_date >= date_from)
    if date_to is not None:
        clauses.append(CecchinoTodayFixture.scan_date <= date_to)
    if competition_id is not None:
        clauses.append(CecchinoTodayFixture.competition_id == int(competition_id))
    if country:
        clauses.append(CecchinoTodayFixture.country_name.ilike(f"%{country.strip()}%"))
    if league:
        clauses.append(CecchinoTodayFixture.league_name.ilike(f"%{league.strip()}%"))
    if team:
        t = team.strip()
        clauses.append(
            or_(
                CecchinoTodayFixture.home_team_name.ilike(f"%{t}%"),
                CecchinoTodayFixture.away_team_name.ilike(f"%{t}%"),
            )
        )
    return clauses


def fetch_home_win_rows(
    db: Session,
    *,
    date_from: date | None = None,
    date_to: date | None = None,
    competition_id: int | None = None,
    country: str | None = None,
    league: str | None = None,
    team: str | None = None,
) -> list[CecchinoTodayFixture]:
    """Carica candidati SQL; classificazione pura applica ancora il gate numerico."""
    q = (
        select(CecchinoTodayFixture)
        .where(
            *_base_filters(
                date_from=date_from,
                date_to=date_to,
                competition_id=competition_id,
                country=country,
                league=league,
                team=team,
            )
        )
        .order_by(
            CecchinoTodayFixture.kickoff.desc().nulls_last(),
            CecchinoTodayFixture.id.desc(),
        )
    )
    candidates = list(db.scalars(q).all())
    return [r for r in candidates if classify_finished_home_win(r) is not None]


def _list_item(
    row: CecchinoTodayFixture,
    outcome: dict[str, Any],
    availability: dict[str, Any],
) -> dict[str, Any]:
    return {
        "today_fixture_id": row.id,
        "provider_fixture_id": row.provider_fixture_id,
        "local_fixture_id": row.local_fixture_id,
        "competition_id": row.competition_id,
        "scan_date": _iso(row.scan_date),
        "kickoff": _iso(row.kickoff),
        "country": row.country_name,
        "league": row.league_name,
        "home_team": row.home_team_name,
        "away_team": row.away_team_name,
        "ft_home": outcome["ft_home"],
        "ft_away": outcome["ft_away"],
        "ht_home": outcome.get("ht_home"),
        "ht_away": outcome.get("ht_away"),
        "goal_difference": outcome["goal_difference"],
        "total_goals": outcome["total_goals"],
        "outcome_1x2": "1",
        "result_source": outcome["result_source"],
        "eligibility_status": row.eligibility_status,
        "kpi_availability": availability["kpi_availability"],
        "balance_availability": availability["balance_availability"],
        "goal_intensity_availability": availability["goal_intensity_availability"],
        "completeness_status": availability["completeness_status"],
        "has_kpi": availability["has_kpi"],
        "has_balance": availability["has_balance"],
        "has_goal_intensity_v5": availability["has_goal_intensity_v5"],
    }


def _build_enriched_rows(
    db: Session,
    rows: list[CecchinoTodayFixture],
) -> list[tuple[CecchinoTodayFixture, dict[str, Any], dict[str, Any], dict[str, Any]]]:
    gi_map = _load_gi_snapshots_bulk(db, [int(r.id) for r in rows])
    enriched: list[tuple[CecchinoTodayFixture, dict[str, Any], dict[str, Any], dict[str, Any]]] = []
    for row in rows:
        outcome = classify_finished_home_win(row)
        if outcome is None:
            continue
        gi_payload = _gi_snapshot_payload(gi_map.get(int(row.id)))
        availability = _module_availability(row, gi_payload)
        enriched.append((row, outcome, availability, gi_payload))
    return enriched


def _available_filters(
    enriched: list[tuple[CecchinoTodayFixture, dict[str, Any], dict[str, Any], dict[str, Any]]],
) -> dict[str, Any]:
    countries = sorted({r.country_name for r, *_ in enriched if r.country_name})
    leagues = sorted({r.league_name for r, *_ in enriched if r.league_name})
    competitions = sorted(
        {
            (r.competition_id, r.league_name or "", r.country_name or "")
            for r, *_ in enriched
            if r.competition_id is not None
        }
    )
    return {
        "countries": countries,
        "leagues": leagues,
        "competitions": [
            {"competition_id": c[0], "league": c[1], "country": c[2]} for c in competitions
        ],
        "completeness": [COMPLETENESS_COMPLETE, COMPLETENESS_PARTIAL],
    }


def _summary_from_enriched(
    enriched: list[tuple[CecchinoTodayFixture, dict[str, Any], dict[str, Any], dict[str, Any]]],
) -> dict[str, Any]:
    total = len(enriched)
    complete = sum(1 for _, _, a, _gi in enriched if a["completeness_status"] == COMPLETENESS_COMPLETE)
    partial = total - complete
    with_kpi = sum(1 for _, _, a, _ in enriched if a["has_kpi"])
    with_balance = sum(1 for _, _, a, _ in enriched if a["has_balance"])
    with_gi = sum(1 for _, _, a, _ in enriched if a["has_goal_intensity_v5"])
    competitions = {r.competition_id for r, *_ in enriched if r.competition_id is not None}
    scan_dates = [r.scan_date for r, *_ in enriched if r.scan_date is not None]
    return {
        "total_home_wins": total,
        "complete": complete,
        "partial": partial,
        "competitions_count": len(competitions),
        "scan_date_min": _iso(min(scan_dates)) if scan_dates else None,
        "scan_date_max": _iso(max(scan_dates)) if scan_dates else None,
        "pct_with_kpi": round(100.0 * with_kpi / total, 1) if total else 0.0,
        "pct_with_balance": round(100.0 * with_balance / total, 1) if total else 0.0,
        "pct_with_goal_intensity_v5": round(100.0 * with_gi / total, 1) if total else 0.0,
    }


def list_home_wins(
    db: Session,
    *,
    date_from: date | None = None,
    date_to: date | None = None,
    competition_id: int | None = None,
    country: str | None = None,
    league: str | None = None,
    team: str | None = None,
    completeness: str | None = None,
    page: int = 1,
    page_size: int = 50,
) -> dict[str, Any]:
    page = max(1, int(page or 1))
    page_size = min(200, max(1, int(page_size or 50)))

    rows = fetch_home_win_rows(
        db,
        date_from=date_from,
        date_to=date_to,
        competition_id=competition_id,
        country=country,
        league=league,
        team=team,
    )
    enriched = _build_enriched_rows(db, rows)
    if completeness:
        target = completeness.strip().lower()
        enriched = [e for e in enriched if e[2]["completeness_status"] == target]

    total = len(enriched)
    start = (page - 1) * page_size
    page_rows = enriched[start : start + page_size]
    items = [_list_item(r, outcome, avail) for r, outcome, avail, _gi in page_rows]

    return make_json_safe(
        {
            "status": "ok",
            "dataset_version": DATASET_VERSION,
            "selection_contract": SELECTION_CONTRACT,
            "total": total,
            "page": page,
            "page_size": page_size,
            "summary": _summary_from_enriched(enriched),
            "available_filters": _available_filters(enriched),
            "items": items,
        }
    )


def build_home_win_detail_record(
    row: CecchinoTodayFixture,
    *,
    gi_snap: CecchinoGoalIntensityV5PreviewSnapshot | None = None,
) -> dict[str, Any] | None:
    outcome = classify_finished_home_win(row)
    if outcome is None:
        return None

    gi_payload = _gi_snapshot_payload(gi_snap)
    availability = _module_availability(row, gi_payload)
    output = _output_dict(row)
    kpi = _persisted_kpi(row)
    balance = _persisted_balance_snapshot(row)
    purch = _persisted_purchasability(row)
    odds = row.odds_snapshot_json if isinstance(row.odds_snapshot_json, dict) else None
    stats = row.stats_snapshot_json if isinstance(row.stats_snapshot_json, dict) else None
    xg = row.xg_profiles_json if isinstance(row.xg_profiles_json, dict) else None
    pre_ts = _extract_odds_snapshot_at(row)
    pre_verified = _pre_match_verified(row)
    warnings: list[str] = []
    if availability["completeness_status"] == COMPLETENESS_PARTIAL:
        warnings.append("partial_pre_match_snapshots")
    for code in availability.get("missing_modules") or []:
        warnings.append(f"missing_{code}")

    cecchino_out = None
    if output:
        # strip heavy observational duplication; keep full output in pre_match without FT
        cecchino_out = dict(output)

    return make_json_safe(
        {
            "status": "ok",
            "dataset_version": DATASET_VERSION,
            "selection_contract": SELECTION_CONTRACT,
            "identity": {
                "today_fixture_id": row.id,
                "provider_fixture_id": row.provider_fixture_id,
                "local_fixture_id": row.local_fixture_id,
                "competition_id": row.competition_id,
                "scan_date": _iso(row.scan_date),
                "kickoff": _iso(row.kickoff),
                "country": row.country_name,
                "league": row.league_name,
                "home_team": row.home_team_name,
                "away_team": row.away_team_name,
                "eligibility_status": row.eligibility_status,
                "eligibility_reason": row.eligibility_reason,
            },
            "post_match_outcome": {
                "match_display_status": row.match_display_status,
                "fixture_status": row.fixture_status,
                "ft_home": outcome["ft_home"],
                "ft_away": outcome["ft_away"],
                "ht_home": outcome.get("ht_home"),
                "ht_away": outcome.get("ht_away"),
                "goal_difference": outcome["goal_difference"],
                "total_goals": outcome["total_goals"],
                "outcome_1x2": "1",
                "result_source": outcome["result_source"],
            },
            "source_integrity": {
                "pre_match_snapshot_timestamp": pre_ts,
                "pre_match_verified": pre_verified,
                "completeness_status": availability["completeness_status"],
                "availability": {
                    "kpi": availability["kpi_availability"],
                    "balance": availability["balance_availability"],
                    "goal_intensity_v5": availability["goal_intensity_availability"],
                    "odds": "available" if availability["has_odds"] else "unavailable",
                    "stats": "available" if availability["has_stats"] else "unavailable",
                    "xg_profiles": "available" if availability["has_xg_profiles"] else "unavailable",
                    "purchasability": (
                        "available" if availability["has_purchasability"] else "unavailable"
                    ),
                },
                "missing_modules": availability["missing_modules"],
                "signal_1_used_for_selection": False,
            },
            "pre_match_snapshot": {
                "kpi_panel": kpi
                if kpi is not None
                else {"status": "unavailable", "reason": "persisted_kpi_panel_missing"},
                "cecchino_output": cecchino_out
                if cecchino_out is not None
                else {"status": "unavailable", "reason": "persisted_cecchino_output_missing"},
                "balance_v5_monitoring": balance,
                "goal_intensity_v5_preview": gi_payload,
                "purchasability_preview": purch,
                "odds_snapshot": odds
                if odds is not None
                else {"status": "unavailable", "reason": "persisted_odds_snapshot_missing"},
                "stats_snapshot": stats
                if stats is not None
                else {"status": "unavailable", "reason": "persisted_stats_snapshot_missing"},
                "xg_profiles": xg
                if xg is not None
                else {"status": "unavailable", "reason": "persisted_xg_profiles_missing"},
            },
            "observational": {
                "signals_matrix": output.get("signals_matrix"),
                "signal_1_was_active": _signal_1_was_active(output),
                "signal_1_used_for_selection": False,
            },
            "warnings": warnings,
        }
    )


def get_home_win_detail(db: Session, today_fixture_id: int) -> dict[str, Any]:
    row = db.get(CecchinoTodayFixture, int(today_fixture_id))
    if row is None:
        return {"status": "error", "reason": "not_found", "today_fixture_id": today_fixture_id}
    gi_map = _load_gi_snapshots_bulk(db, [int(today_fixture_id)])
    detail = build_home_win_detail_record(row, gi_snap=gi_map.get(int(today_fixture_id)))
    if detail is None:
        return {
            "status": "error",
            "reason": "not_in_home_wins_cohort",
            "today_fixture_id": today_fixture_id,
            "selection_contract": SELECTION_CONTRACT,
        }
    return detail


def _kpi_row_by_market(panel: dict[str, Any] | None, market_key: str) -> dict[str, Any]:
    if not isinstance(panel, dict):
        return {}
    for row in panel.get("rows") or []:
        if isinstance(row, dict) and row.get("market_key") == market_key:
            return row
    return {}


def _purch_item_by_market(preview: dict[str, Any], market_key: str) -> dict[str, Any]:
    items = preview.get("items") if isinstance(preview, dict) else None
    if not isinstance(items, list):
        return {}
    for item in items:
        if isinstance(item, dict) and item.get("market_key") == market_key:
            return item
    return {}


def _csv_row(
    row: CecchinoTodayFixture,
    outcome: dict[str, Any],
    availability: dict[str, Any],
    gi_payload: dict[str, Any],
) -> dict[str, Any]:
    output = _output_dict(row)
    final = output.get("final") if isinstance(output.get("final"), dict) else {}
    kpi = _persisted_kpi(row)
    balance = _persisted_balance_snapshot(row)
    purch = _persisted_purchasability(row)
    k1 = _kpi_row_by_market(kpi, SEL_HOME)
    kx = _kpi_row_by_market(kpi, SEL_DRAW)
    k2 = _kpi_row_by_market(kpi, SEL_AWAY)
    p1 = _purch_item_by_market(purch, SEL_HOME)
    px = _purch_item_by_market(purch, SEL_DRAW)
    p2 = _purch_item_by_market(purch, SEL_AWAY)

    def kpi_fields(prefix: str, kr: dict[str, Any]) -> dict[str, Any]:
        return {
            f"kpi_{prefix}_quota_book": kr.get("quota_book"),
            f"kpi_{prefix}_quota_cecchino": kr.get("quota_cecchino"),
            f"kpi_{prefix}_prob_book": kr.get("prob_book"),
            f"kpi_{prefix}_prob_cecchino": kr.get("prob_cecchino"),
            f"kpi_{prefix}_vantaggio_prob": kr.get("vantaggio_prob"),
            f"kpi_{prefix}_edge": kr.get("edge_pct") if "edge_pct" in kr else kr.get("edge"),
            f"kpi_{prefix}_score_acquisto": kr.get("score_acquisto"),
            f"kpi_{prefix}_rating": kr.get("rating"),
            f"kpi_{prefix}_rating_label": kr.get("rating_label"),
            f"kpi_{prefix}_status": kr.get("status"),
        }

    warnings = balance.get("warning_codes") if isinstance(balance, dict) else None
    if isinstance(warnings, list):
        warning_str = "|".join(str(w) for w in warnings)
    else:
        warning_str = None

    return {
        "today_fixture_id": row.id,
        "provider_fixture_id": row.provider_fixture_id,
        "local_fixture_id": row.local_fixture_id,
        "competition_id": row.competition_id,
        "scan_date": _iso(row.scan_date),
        "kickoff": _iso(row.kickoff),
        "country": row.country_name,
        "league": row.league_name,
        "home_team": row.home_team_name,
        "away_team": row.away_team_name,
        "ft_home": outcome["ft_home"],
        "ft_away": outcome["ft_away"],
        "ht_home": outcome.get("ht_home"),
        "ht_away": outcome.get("ht_away"),
        "goal_difference": outcome["goal_difference"],
        "total_goals": outcome["total_goals"],
        "outcome_1x2": "1",
        "result_source": outcome["result_source"],
        "eligibility_status": row.eligibility_status,
        "completeness_status": availability["completeness_status"],
        "pre_match_snapshot_timestamp": _extract_odds_snapshot_at(row),
        "pre_match_verified": _pre_match_verified(row),
        "has_kpi": availability["has_kpi"],
        "has_balance": availability["has_balance"],
        "has_goal_intensity_v5": availability["has_goal_intensity_v5"],
        "has_odds": availability["has_odds"],
        "has_stats": availability["has_stats"],
        "has_xg_profiles": availability["has_xg_profiles"],
        "cecchino_version": output.get("version") or output.get("cecchino_version"),
        "kpi_version": (kpi or {}).get("version") if kpi else None,
        "balance_snapshot_version": balance.get("snapshot_version")
        if isinstance(balance, dict)
        else None,
        "goal_intensity_version": gi_payload.get("preview_status")
        if gi_payload.get("status") == "ok"
        else None,
        "cecchino_quota_1": final.get("quota_1"),
        "cecchino_quota_x": final.get("quota_x"),
        "cecchino_quota_2": final.get("quota_2"),
        "cecchino_prob_1": final.get("prob_1"),
        "cecchino_prob_x": final.get("prob_x"),
        "cecchino_prob_2": final.get("prob_2"),
        **kpi_fields("1", k1),
        **kpi_fields("x", kx),
        **kpi_fields("2", k2),
        "purchasability_1_score": p1.get("score"),
        "purchasability_1_class": p1.get("class"),
        "purchasability_1_status": p1.get("status"),
        "purchasability_x_score": px.get("score"),
        "purchasability_x_class": px.get("class"),
        "purchasability_x_status": px.get("status"),
        "purchasability_2_score": p2.get("score"),
        "purchasability_2_class": p2.get("class"),
        "purchasability_2_status": p2.get("status"),
        "balance_f36_index": balance.get("f36_index"),
        "balance_f36_class": balance.get("f36_class"),
        "balance_dominance_index": balance.get("dominance_index"),
        "balance_dominance_class": balance.get("dominance_class"),
        "balance_dominance_direction": balance.get("dominance_selection")
        or balance.get("dominance_direction"),
        "balance_draw_credibility_index": balance.get("draw_credibility_index"),
        "balance_draw_credibility_class": balance.get("draw_credibility_class"),
        "balance_gap_index": balance.get("gap_index"),
        "balance_gap_class": balance.get("gap_class"),
        "balance_prob_1_norm": balance.get("prob_1_norm"),
        "balance_prob_x_norm": balance.get("prob_x_norm"),
        "balance_prob_2_norm": balance.get("prob_2_norm"),
        "balance_book_prob_1": balance.get("book_prob_1"),
        "balance_book_prob_x": balance.get("book_prob_x"),
        "balance_book_prob_2": balance.get("book_prob_2"),
        "balance_book_verified": balance.get("book_verified"),
        "balance_pre_match_verified": balance.get("pre_match_verified"),
        "balance_source_mode": balance.get("source_mode"),
        "balance_source_cohort": balance.get("source_cohort"),
        "balance_warning_codes": warning_str,
        "gi_v5_primary_candidate_score": gi_payload.get("primary_candidate_score"),
        "gi_v5_challenger_candidate_score": gi_payload.get("challenger_candidate_score"),
        "gi_v5_benchmark_score": gi_payload.get("benchmark_score"),
        "gi_v5_diagnostic_score": gi_payload.get("diagnostic_score"),
        "gi_v5_expected_total_goals": gi_payload.get("expected_total_goals"),
        "gi_v5_probability_goals_ge_2": gi_payload.get("probability_goals_ge_2"),
        "gi_v5_probability_goals_ge_3": gi_payload.get("probability_goals_ge_3"),
        "gi_v5_probability_btts": gi_payload.get("probability_btts"),
        "gi_v5_history_sample_size": gi_payload.get("history_sample_size"),
        "gi_v5_xg_status": gi_payload.get("xg_status"),
        "gi_v5_preview_status": gi_payload.get("preview_status"),
        "gi_v5_source_snapshot_timestamp": gi_payload.get("source_snapshot_at"),
        "gi_v5_source_snapshot_before_kickoff": gi_payload.get(
            "source_snapshot_before_kickoff"
        ),
        "gi_v5_no_target_used_in_score": gi_payload.get("no_target_used_in_score"),
    }


def _schema_document() -> dict[str, Any]:
    fields = []
    for col in _CSV_COLUMNS:
        group = "identity"
        nature = "identity"
        if col.startswith(("ft_", "ht_", "goal_", "total_", "outcome_", "result_")):
            group = "post_match_outcome"
            nature = "post_match"
        elif col.startswith(("has_", "completeness", "pre_match", "eligibility")):
            group = "source_integrity"
            nature = "metadata"
        elif col.startswith(("kpi_", "cecchino_", "purchasability_", "balance_", "gi_v5_")):
            group = "pre_match_snapshot"
            nature = "pre_match"
        fields.append(
            {
                "name": col,
                "type": "string|number|boolean|null",
                "nullable": True,
                "group": group,
                "source_path": col,
                "description": col.replace("_", " "),
                "nature": nature,
            }
        )
    return {
        "schema_version": CSV_SCHEMA_VERSION,
        "dataset_version": DATASET_VERSION,
        "fields": fields,
    }


def _quality_report(
    enriched: list[tuple[CecchinoTodayFixture, dict[str, Any], dict[str, Any], dict[str, Any]]],
) -> dict[str, Any]:
    total = len(enriched)
    provider_ids = [r.provider_fixture_id for r, *_ in enriched]
    provider_counts = Counter(provider_ids)
    duplicates = {str(k): v for k, v in provider_counts.items() if v > 1 and k is not None}
    eligibility = Counter(r.eligibility_status for r, *_ in enriched)
    competitions = Counter(
        (r.league_name or f"competition_{r.competition_id}") for r, *_ in enriched
    )
    scan_dates = [r.scan_date for r, *_ in enriched if r.scan_date is not None]
    verified = sum(1 for r, *_ in enriched if _pre_match_verified(r) is True)
    unverifiable = sum(1 for r, *_ in enriched if _pre_match_verified(r) is None)

    return {
        "total_home_wins": total,
        "records_complete": sum(
            1 for _, _, a, _ in enriched if a["completeness_status"] == COMPLETENESS_COMPLETE
        ),
        "records_partial": sum(
            1 for _, _, a, _ in enriched if a["completeness_status"] == COMPLETENESS_PARTIAL
        ),
        "records_without_kpi": sum(1 for _, _, a, _ in enriched if not a["has_kpi"]),
        "records_without_balance": sum(1 for _, _, a, _ in enriched if not a["has_balance"]),
        "records_without_goal_intensity_v5": sum(
            1 for _, _, a, _ in enriched if not a["has_goal_intensity_v5"]
        ),
        "records_without_odds_snapshot": sum(1 for _, _, a, _ in enriched if not a["has_odds"]),
        "records_without_stats_snapshot": sum(1 for _, _, a, _ in enriched if not a["has_stats"]),
        "records_pre_match_verified": verified,
        "records_pre_match_unverifiable": unverifiable,
        "duplicate_provider_fixture_ids": duplicates,
        "eligibility_status_distribution": dict(eligibility),
        "competition_distribution": dict(competitions),
        "scan_date_min": _iso(min(scan_dates)) if scan_dates else None,
        "scan_date_max": _iso(max(scan_dates)) if scan_dates else None,
    }


def build_home_wins_export_files(
    db: Session,
    *,
    date_from: date | None = None,
    date_to: date | None = None,
    competition_id: int | None = None,
    country: str | None = None,
    league: str | None = None,
    team: str | None = None,
    completeness: str | None = None,
) -> dict[str, bytes]:
    rows = fetch_home_win_rows(
        db,
        date_from=date_from,
        date_to=date_to,
        competition_id=competition_id,
        country=country,
        league=league,
        team=team,
    )
    enriched = _build_enriched_rows(db, rows)
    if completeness:
        target = completeness.strip().lower()
        enriched = [e for e in enriched if e[2]["completeness_status"] == target]

    # Deterministic order already from query; ensure unique today_fixture_id
    seen: set[int] = set()
    unique_enriched: list[
        tuple[CecchinoTodayFixture, dict[str, Any], dict[str, Any], dict[str, Any]]
    ] = []
    for item in enriched:
        tid = int(item[0].id)
        if tid in seen:
            continue
        seen.add(tid)
        unique_enriched.append(item)
    enriched = unique_enriched

    generated_at = datetime.now(timezone.utc)
    filters_applied = {
        "date_from": _iso(date_from),
        "date_to": _iso(date_to),
        "competition_id": competition_id,
        "country": country,
        "league": league,
        "team": team,
        "completeness": completeness,
    }

    csv_buf = io.StringIO()
    writer = csv.DictWriter(csv_buf, fieldnames=_CSV_COLUMNS, extrasaction="ignore")
    writer.writeheader()
    jsonl_lines: list[str] = []
    for row, outcome, availability, gi_payload in enriched:
        csv_writer_row = _csv_row(row, outcome, availability, gi_payload)
        writer.writerow({k: csv_writer_row.get(k) for k in _CSV_COLUMNS})
        detail = build_home_win_detail_record(
            row,
            gi_snap=None,
        )
        # Rebuild with gi from payload already computed — attach snap-like via detail override
        if detail is not None:
            detail["pre_match_snapshot"]["goal_intensity_v5_preview"] = gi_payload
            jsonl_lines.append(
                json.dumps(make_json_safe(detail), ensure_ascii=False, allow_nan=False)
            )

    csv_bytes = ("\ufeff" + csv_buf.getvalue()).encode("utf-8")
    jsonl_bytes = ("\n".join(jsonl_lines) + ("\n" if jsonl_lines else "")).encode("utf-8")
    schema_bytes = _json_bytes(_schema_document())
    quality = _quality_report(enriched)
    quality_bytes = _json_bytes(quality)

    file_entries = {
        "schema.json": schema_bytes,
        "quality_report.json": quality_bytes,
        "home_wins_features.csv": csv_bytes,
        "home_wins_full.jsonl": jsonl_bytes,
    }
    file_manifest = []
    for name in sorted(file_entries):
        content = file_entries[name]
        file_manifest.append(
            {
                "name": name,
                "size_bytes": len(content),
                "sha256": _sha256(content),
            }
        )

    scan_dates = [r.scan_date for r, *_ in enriched if r.scan_date is not None]
    dataset_hash = _sha256(
        "|".join(str(r.id) for r, *_ in enriched).encode("utf-8")
        + b"|"
        + DATASET_VERSION.encode("utf-8")
    )

    manifest = {
        "dataset_version": DATASET_VERSION,
        "csv_schema_version": CSV_SCHEMA_VERSION,
        "generated_at": generated_at.isoformat(),
        "record_count": len(enriched),
        "temporal_range": {
            "scan_date_min": _iso(min(scan_dates)) if scan_dates else None,
            "scan_date_max": _iso(max(scan_dates)) if scan_dates else None,
        },
        "filters_applied": filters_applied,
        "inclusion_rule": SELECTION_CONTRACT["inclusion_rule"],
        "selection_contract": SELECTION_CONTRACT,
        "ordering": "kickoff DESC, today_fixture_id DESC",
        "data_provenance": {
            "primary_table": "cecchino_today_fixtures",
            "goal_intensity_table": "cecchino_goal_intensity_v5_preview_snapshots",
            "no_new_home_wins_table": True,
        },
        "anti_leakage_policy": {
            "pre_match_and_post_match_separated": True,
            "no_module_rebuild_on_read": True,
            "post_match_targets_not_exported_as_pre_match_features": True,
        },
        "signal_1_used_for_selection": False,
        "module_versions": {
            "dataset": DATASET_VERSION,
            "balance_key": "balance_v5_monitoring",
            "goal_intensity": "cecchino_goal_intensity_v5_preview",
        },
        "files": file_manifest,
        "dataset_content_hash_sha256": dataset_hash,
    }
    files = {"manifest.json": _json_bytes(manifest), **file_entries}
    return files


def build_home_wins_export_zip(
    db: Session,
    **filters: Any,
) -> tuple[bytes, str]:
    files = build_home_wins_export_files(db, **filters)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name in sorted(files):
            archive.writestr(name, files[name])
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    filename = f"SOT_CECCHINO_HOME_WINS_DATASET_{stamp}.zip"
    return buf.getvalue(), filename


def row_in_home_wins_cohort(row: CecchinoTodayFixture) -> bool:
    return classify_finished_home_win(row) is not None
