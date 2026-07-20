"""Validazione prospettica Acquistabilità — Fase 5/5.

Versione: cecchino_purchasability_validation_v1

Sync da snapshot persistito pre-match; settlement post-match senza
contaminare input. Nessuna promozione automatica del candidate.
"""

from __future__ import annotations

import csv
import io
import logging
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import Select, and_, select
from sqlalchemy.orm import Session

from app.models.cecchino_purchasability_evaluation import (
    DEFAULT_STAKE_UNITS,
    EVAL_LOST,
    EVAL_NOT_EVALUABLE,
    EVAL_PENDING,
    EVAL_RESULT_MISSING,
    EVAL_WON,
    SOURCE_LEGACY_BACKFILL,
    SOURCE_LEGACY_DERIVED,
    SOURCE_PROSPECTIVE,
    CecchinoPurchasabilityEvaluation,
)
from app.models.cecchino_today_fixture import (
    ELIGIBILITY_ELIGIBLE,
    CecchinoTodayFixture,
)
from app.schemas.cecchino_purchasability_preview import (
    PURCHASABILITY_CANDIDATE_VERSION,
)
from app.services.cecchino.cecchino_purchasability_audit import make_json_safe
from app.services.cecchino.cecchino_purchasability_fair_book import (
    resolve_fair_book_for_panel_rows,
)
from app.services.cecchino.cecchino_purchasability_snapshot import (
    validate_purchasability_preview_snapshot,
)
from app.services.cecchino.cecchino_selection_keys import (
    SEL_AWAY,
    SEL_DRAW,
    SEL_HOME,
    SEL_ONE_TWO,
    SEL_ONE_X,
    SEL_OVER_2_5,
    SEL_OVER_PT_1_5,
    SEL_UNDER_2_5,
    SEL_UNDER_PT_1_5,
    SEL_X_TWO,
)
from app.services.cecchino.cecchino_signal_evaluation import (
    evaluate_market_selection,
    match_result_from_fixture,
)

logger = logging.getLogger(__name__)

PURCHASABILITY_VALIDATION_VERSION = "cecchino_purchasability_validation_v1"

EVALUABLE_MARKETS = frozenset(
    {
        SEL_HOME,
        SEL_DRAW,
        SEL_AWAY,
        SEL_ONE_X,
        SEL_X_TWO,
        SEL_ONE_TWO,
        SEL_OVER_2_5,
        SEL_UNDER_2_5,
        SEL_OVER_PT_1_5,
        SEL_UNDER_PT_1_5,
    }
)

SCORE_BAND_ZERO = "ZERO"
SCORE_BANDS_ORDERED = (
    SCORE_BAND_ZERO,
    "1-19",
    "20-39",
    "40-59",
    "60-79",
    "80-100",
)

MARKET_FAMILY_MATCH_WINNER = "match_winner"
MARKET_FAMILY_DOUBLE_CHANCE = "double_chance"
MARKET_FAMILY_OU_FT = "over_under_ft"
MARKET_FAMILY_OU_HT = "over_under_ht"

MARKET_FAMILY_FOR_KEY: dict[str, str] = {
    SEL_HOME: MARKET_FAMILY_MATCH_WINNER,
    SEL_DRAW: MARKET_FAMILY_MATCH_WINNER,
    SEL_AWAY: MARKET_FAMILY_MATCH_WINNER,
    SEL_ONE_X: MARKET_FAMILY_DOUBLE_CHANCE,
    SEL_X_TWO: MARKET_FAMILY_DOUBLE_CHANCE,
    SEL_ONE_TWO: MARKET_FAMILY_DOUBLE_CHANCE,
    SEL_OVER_2_5: MARKET_FAMILY_OU_FT,
    SEL_UNDER_2_5: MARKET_FAMILY_OU_FT,
    SEL_OVER_PT_1_5: MARKET_FAMILY_OU_HT,
    SEL_UNDER_PT_1_5: MARKET_FAMILY_OU_HT,
}


def score_band_for(score: int | None) -> str | None:
    if score is None:
        return None
    if score == 0:
        return SCORE_BAND_ZERO
    if 1 <= score <= 19:
        return "1-19"
    if 20 <= score <= 39:
        return "20-39"
    if 40 <= score <= 59:
        return "40-59"
    if 60 <= score <= 79:
        return "60-79"
    if 80 <= score <= 100:
        return "80-100"
    return None


def market_family_for(market_key: str | None) -> str | None:
    if not market_key:
        return None
    return MARKET_FAMILY_FOR_KEY.get(str(market_key).strip().upper())


def compute_profit_units(evaluation_status: str, quota_book: Decimal | float | None) -> Decimal | None:
    if evaluation_status == EVAL_WON:
        if quota_book is None:
            return None
        return Decimal(str(round(float(quota_book) - 1.0, 4)))
    if evaluation_status == EVAL_LOST:
        return Decimal("-1")
    return None


def _parse_dt(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str):
        try:
            raw = value.replace("Z", "+00:00")
            out = datetime.fromisoformat(raw)
            return out if out.tzinfo else out.replace(tzinfo=timezone.utc)
        except ValueError:
            return None
    return None


def _dec(value: Any, places: int = 4) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(round(float(value), places)))
    except (TypeError, ValueError):
        return None


def _int_or_none(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _panel_rows(panel: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(panel, dict):
        return []
    rows = panel.get("rows")
    if not isinstance(rows, list):
        return []
    return [r for r in rows if isinstance(r, dict)]


def _index_panel_by_market(panel: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for row in _panel_rows(panel):
        key = str(row.get("market_key") or row.get("selection") or "").strip().upper()
        if key:
            out[key] = row
    return out


def _panel_snapshot_at(panel: dict[str, Any] | None) -> str | None:
    if not isinstance(panel, dict):
        return None
    meta = panel.get("odds_meta")
    if isinstance(meta, dict):
        for fld in ("odds_fetched_at", "fetched_at", "snapshot_at"):
            if meta.get(fld):
                return str(meta.get(fld))
    return None


def _timestamps_mismatch(a: Any, b: Any) -> bool:
    da, db = _parse_dt(a), _parse_dt(b)
    if da is None or db is None:
        return False
    return abs((da - db).total_seconds()) > 1.0


def _is_kickoff_passed(row: CecchinoTodayFixture) -> bool:
    kick = row.kickoff
    if kick is None:
        return False
    if kick.tzinfo is None:
        kick = kick.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) >= kick


def _extract_preview(row: CecchinoTodayFixture) -> dict[str, Any] | None:
    output = row.cecchino_output_json
    if not isinstance(output, dict):
        return None
    preview = output.get("purchasability_preview")
    if not isinstance(preview, dict):
        return None
    check = validate_purchasability_preview_snapshot(preview)
    if not check["ok"]:
        return None
    return preview


def _deactivate_current(
    db: Session,
    *,
    today_fixture_id: int,
    candidate_version: str,
    market_key: str,
    keep_id: int | None = None,
) -> int:
    now = datetime.now(timezone.utc)
    q = select(CecchinoPurchasabilityEvaluation).where(
        CecchinoPurchasabilityEvaluation.today_fixture_id == int(today_fixture_id),
        CecchinoPurchasabilityEvaluation.candidate_version == candidate_version,
        CecchinoPurchasabilityEvaluation.market_key == market_key,
        CecchinoPurchasabilityEvaluation.is_current.is_(True),
    )
    if keep_id is not None:
        q = q.where(CecchinoPurchasabilityEvaluation.id != keep_id)
    deactivated = 0
    for existing in db.scalars(q).all():
        existing.is_current = False
        existing.deactivated_at = now
        deactivated += 1
    return deactivated


def sync_purchasability_validation_for_fixture(
    db: Session,
    today_fixture_id: int,
    *,
    source_cohort: str = SOURCE_PROSPECTIVE,
    allow_update_prematch: bool | None = None,
) -> dict[str, Any]:
    """Sincronizza righe validation da purchasability_preview persistito."""
    row = db.get(CecchinoTodayFixture, int(today_fixture_id))
    if row is None:
        return {"synced": 0, "skipped": 0, "reason": "fixture_not_found"}

    preview = _extract_preview(row)
    if preview is None:
        return {"synced": 0, "skipped": 1, "reason": "no_valid_persisted_preview"}

    verified = bool(preview.get("source_snapshot_verified"))
    before = preview.get("source_snapshot_before_kickoff")
    if before is None:
        snap_dt = _parse_dt(preview.get("source_snapshot_at"))
        kick_dt = row.kickoff
        if kick_dt is not None and kick_dt.tzinfo is None:
            kick_dt = kick_dt.replace(tzinfo=timezone.utc)
        if snap_dt is not None and kick_dt is not None:
            before = snap_dt < kick_dt

    if not verified or before is not True:
        return {
            "synced": 0,
            "skipped": 1,
            "reason": "preview_not_verified_pre_match",
            "verified": verified,
            "before_kickoff": before,
        }

    candidate_version = str(
        preview.get("candidate_version") or PURCHASABILITY_CANDIDATE_VERSION
    )
    candidate_name = preview.get("candidate_name")
    feature_version = preview.get("feature_version")
    snapshot_version = preview.get("snapshot_version")
    snapshot_hash = preview.get("full_candidate_payload_sha256")
    source_snapshot_at = _parse_dt(preview.get("source_snapshot_at"))

    panel = row.kpi_panel_json if isinstance(row.kpi_panel_json, dict) else {}
    panel_by_m = _index_panel_by_market(panel)
    panel_ts = _panel_snapshot_at(panel)
    fair_by_m = resolve_fair_book_for_panel_rows(
        _panel_rows(panel),
        today_fixture_id=int(row.id),
        snapshot_at=panel_ts or (
            source_snapshot_at.isoformat() if source_snapshot_at else None
        ),
    )

    kickoff_passed = _is_kickoff_passed(row)
    if allow_update_prematch is None:
        allow_update_prematch = not kickoff_passed

    items = preview.get("items") if isinstance(preview.get("items"), list) else []
    synced = 0
    skipped = 0
    diagnostic_unavailable = 0
    mismatch_count = 0

    for item in items:
        if not isinstance(item, dict):
            continue
        market_key = str(item.get("market_key") or item.get("selection") or "").strip().upper()
        if not market_key:
            skipped += 1
            continue
        status = str(item.get("status") or "")
        score = item.get("score")
        if status == "unavailable" or score is None:
            diagnostic_unavailable += 1
            skipped += 1
            continue
        if status not in ("available", "partial"):
            skipped += 1
            continue

        panel_row = panel_by_m.get(market_key) or {}
        fair = fair_by_m.get(market_key) or {}

        row_cohort = source_cohort
        promotion_eligible = source_cohort in (
            SOURCE_PROSPECTIVE,
            SOURCE_LEGACY_BACKFILL,
        )
        reason_codes: list[str] = []

        if _timestamps_mismatch(panel_ts, preview.get("source_snapshot_at")):
            promotion_eligible = False
            row_cohort = SOURCE_LEGACY_DERIVED
            reason_codes.append("snapshot_panel_timestamp_mismatch")
            mismatch_count += 1

        if source_cohort == SOURCE_LEGACY_DERIVED:
            promotion_eligible = False

        existing = db.scalar(
            select(CecchinoPurchasabilityEvaluation).where(
                CecchinoPurchasabilityEvaluation.today_fixture_id == int(row.id),
                CecchinoPurchasabilityEvaluation.candidate_version == candidate_version,
                CecchinoPurchasabilityEvaluation.market_key == market_key,
                CecchinoPurchasabilityEvaluation.is_current.is_(True),
            )
        )

        settled = existing is not None and existing.evaluation_status in (
            EVAL_WON,
            EVAL_LOST,
        )

        if existing is not None and (kickoff_passed or settled) and not allow_update_prematch:
            # post-kickoff / settled: non mutare input pre-match
            skipped += 1
            continue

        payload = {
            "today_fixture_id": int(row.id),
            "local_fixture_id": row.local_fixture_id,
            "provider_fixture_id": row.provider_fixture_id,
            "competition_id": row.competition_id,
            "scan_date": row.scan_date,
            "kickoff": row.kickoff,
            "country_name": row.country_name,
            "league_name": row.league_name,
            "home_team_name": row.home_team_name,
            "away_team_name": row.away_team_name,
            "snapshot_version": snapshot_version,
            "snapshot_hash": snapshot_hash,
            "source_snapshot_at": source_snapshot_at,
            "snapshot_timestamp_verified": verified,
            "snapshot_before_kickoff": True,
            "source_cohort": row_cohort,
            "candidate_version": candidate_version,
            "candidate_name": candidate_name,
            "feature_version": feature_version,
            "market_key": market_key,
            "selection": str(item.get("selection") or market_key),
            "calculation_status": status,
            "calculation_quality": item.get("calculation_quality"),
            "purchasability_score": _int_or_none(score),
            "raw_score": _dec(item.get("raw_score")),
            "purchasability_class": item.get("class"),
            "phase_1_score": _dec(item.get("phase_1_score")),
            "phase_2_score": _dec(item.get("phase_2_score")),
            "reading": item.get("reading"),
            "quota_book": _dec(panel_row.get("quota_book")),
            "quota_cecchino": _dec(panel_row.get("quota_cecchino")),
            "fair_book_probability": _dec(
                fair.get("fair_book_probability"), places=6
            ),
            "prob_cecchino": _dec(panel_row.get("prob_cecchino"), places=6),
            "edge_pct": _dec(panel_row.get("edge_pct")),
            "rating_score": _int_or_none(panel_row.get("rating")),
            "score_acquisto": _dec(panel_row.get("score_acquisto"), places=6),
            "promotion_eligible": promotion_eligible,
            "is_current": True,
            "deactivated_at": None,
            "stake_units": DEFAULT_STAKE_UNITS,
        }
        if reason_codes and existing is None:
            payload["evaluation_reason"] = ",".join(reason_codes)

        if existing is None:
            ev = CecchinoPurchasabilityEvaluation(
                evaluation_status=EVAL_PENDING,
                **payload,
            )
            db.add(ev)
            db.flush()
            if ev.id is not None:
                _deactivate_current(
                    db,
                    today_fixture_id=int(row.id),
                    candidate_version=candidate_version,
                    market_key=market_key,
                    keep_id=int(ev.id),
                )
            synced += 1
        else:
            for key, val in payload.items():
                setattr(existing, key, val)
            if existing.evaluation_status is None:
                existing.evaluation_status = EVAL_PENDING
            if existing.id is not None:
                _deactivate_current(
                    db,
                    today_fixture_id=int(row.id),
                    candidate_version=candidate_version,
                    market_key=market_key,
                    keep_id=int(existing.id),
                )
            synced += 1

    return make_json_safe(
        {
            "synced": synced,
            "skipped": skipped,
            "diagnostic_unavailable": diagnostic_unavailable,
            "timestamp_mismatch_count": mismatch_count,
            "candidate_version": candidate_version,
            "source_cohort": source_cohort,
        }
    )


def evaluate_purchasability_validation_for_fixture(
    db: Session,
    today_fixture_id: int,
) -> dict[str, Any]:
    """Valuta settlement sulle righe current della fixture."""
    row = db.get(CecchinoTodayFixture, int(today_fixture_id))
    if row is None:
        return {"evaluated": 0, "pending": 0, "not_evaluable": 0}

    match_result = match_result_from_fixture(row)
    activations = list(
        db.scalars(
            select(CecchinoPurchasabilityEvaluation).where(
                CecchinoPurchasabilityEvaluation.today_fixture_id == int(today_fixture_id),
                CecchinoPurchasabilityEvaluation.is_current.is_(True),
            )
        ).all()
    )

    counts = {"evaluated": 0, "pending": 0, "not_evaluable": 0, "result_missing": 0}
    for ev in activations:
        market_key = str(ev.market_key or "").strip().upper()
        if market_key not in EVALUABLE_MARKETS:
            ev.evaluation_status = EVAL_NOT_EVALUABLE
            ev.evaluation_reason = "unsupported_selection_key"
            ev.evaluated_at = datetime.now(timezone.utc)
            ev.profit_units = None
            counts["not_evaluable"] += 1
            continue

        result = evaluate_market_selection(market_key, match_result)
        status = result["evaluation_status"]
        ev.evaluation_status = status
        ev.evaluation_reason = result.get("evaluation_reason")
        ev.evaluated_at = result.get("evaluated_at")
        if result.get("result_home_ft") is not None:
            ev.result_home_ft = result.get("result_home_ft")
            ev.result_away_ft = result.get("result_away_ft")
        if result.get("result_home_ht") is not None:
            ev.result_home_ht = result.get("result_home_ht")
            ev.result_away_ht = result.get("result_away_ht")
        ev.profit_units = compute_profit_units(status, ev.quota_book)

        if status in (EVAL_WON, EVAL_LOST):
            counts["evaluated"] += 1
        elif status == EVAL_PENDING:
            counts["pending"] += 1
        elif status == EVAL_RESULT_MISSING:
            counts["result_missing"] += 1
        else:
            counts["not_evaluable"] += 1

    return counts


def sync_and_evaluate_purchasability_validation_range(
    db: Session,
    *,
    date_from: date,
    date_to: date,
    include_legacy_derived: bool = False,
    evaluate_after: bool = True,
    source_cohort: str | None = None,
) -> dict[str, Any]:
    """Backfill sync (+ evaluate) su range date."""
    cohort = source_cohort or SOURCE_LEGACY_BACKFILL
    rows = list(
        db.scalars(
            select(CecchinoTodayFixture).where(
                CecchinoTodayFixture.scan_date >= date_from,
                CecchinoTodayFixture.scan_date <= date_to,
                CecchinoTodayFixture.eligibility_status == ELIGIBILITY_ELIGIBLE,
            )
        ).all()
    )
    sync_ok = 0
    sync_skip = 0
    eval_ok = 0
    errors: list[dict[str, Any]] = []

    for row in rows:
        try:
            with db.begin_nested():
                result = sync_purchasability_validation_for_fixture(
                    db,
                    int(row.id),
                    source_cohort=cohort,
                    allow_update_prematch=True,
                )
                sync_ok += int(result.get("synced") or 0)
                sync_skip += int(result.get("skipped") or 0)
                if evaluate_after:
                    ev = evaluate_purchasability_validation_for_fixture(db, int(row.id))
                    eval_ok += int(ev.get("evaluated") or 0)
        except Exception as exc:
            logger.exception(
                "purchasability_validation_range_error fixture_id=%s", row.id
            )
            errors.append(
                {
                    "today_fixture_id": int(row.id),
                    "error": str(exc)[:300],
                }
            )

    if include_legacy_derived:
        # Diagnostic path: non entra nei gate; solo contatore
        derived_note = "legacy_derived_requested_but_primary_uses_persisted_only"
    else:
        derived_note = None

    db.commit()
    return make_json_safe(
        {
            "status": "ok",
            "version": PURCHASABILITY_VALIDATION_VERSION,
            "date_from": date_from.isoformat(),
            "date_to": date_to.isoformat(),
            "fixtures": len(rows),
            "synced": sync_ok,
            "skipped": sync_skip,
            "evaluated": eval_ok,
            "include_legacy_derived": include_legacy_derived,
            "source_cohort": cohort,
            "derived_note": derived_note,
            "errors": errors[:50],
        }
    )


def _filters_clause(
    *,
    date_from: date | None,
    date_to: date | None,
    candidate_version: str | None,
    competition_id: int | None,
    market_key: str | None,
    score_band: str | None,
    evaluation_status: str | None,
    source_cohort: str | None,
    promotion_eligible_only: bool,
    only_current: bool = True,
    source_cohorts: list[str] | None = None,
) -> list[Any]:
    clauses: list[Any] = []
    if only_current:
        clauses.append(CecchinoPurchasabilityEvaluation.is_current.is_(True))
    if date_from is not None:
        clauses.append(CecchinoPurchasabilityEvaluation.scan_date >= date_from)
    if date_to is not None:
        clauses.append(CecchinoPurchasabilityEvaluation.scan_date <= date_to)
    if candidate_version:
        clauses.append(
            CecchinoPurchasabilityEvaluation.candidate_version == candidate_version
        )
    if competition_id is not None:
        clauses.append(
            CecchinoPurchasabilityEvaluation.competition_id == int(competition_id)
        )
    if market_key:
        clauses.append(
            CecchinoPurchasabilityEvaluation.market_key == market_key.strip().upper()
        )
    if evaluation_status:
        clauses.append(
            CecchinoPurchasabilityEvaluation.evaluation_status == evaluation_status
        )
    if source_cohorts:
        clauses.append(CecchinoPurchasabilityEvaluation.source_cohort.in_(source_cohorts))
    elif source_cohort:
        clauses.append(CecchinoPurchasabilityEvaluation.source_cohort == source_cohort)
    if promotion_eligible_only:
        clauses.append(CecchinoPurchasabilityEvaluation.promotion_eligible.is_(True))
    if score_band:
        if score_band == SCORE_BAND_ZERO:
            clauses.append(CecchinoPurchasabilityEvaluation.purchasability_score == 0)
        elif score_band == "1-19":
            clauses.append(
                and_(
                    CecchinoPurchasabilityEvaluation.purchasability_score >= 1,
                    CecchinoPurchasabilityEvaluation.purchasability_score <= 19,
                )
            )
        elif score_band == "20-39":
            clauses.append(
                and_(
                    CecchinoPurchasabilityEvaluation.purchasability_score >= 20,
                    CecchinoPurchasabilityEvaluation.purchasability_score <= 39,
                )
            )
        elif score_band == "40-59":
            clauses.append(
                and_(
                    CecchinoPurchasabilityEvaluation.purchasability_score >= 40,
                    CecchinoPurchasabilityEvaluation.purchasability_score <= 59,
                )
            )
        elif score_band == "60-79":
            clauses.append(
                and_(
                    CecchinoPurchasabilityEvaluation.purchasability_score >= 60,
                    CecchinoPurchasabilityEvaluation.purchasability_score <= 79,
                )
            )
        elif score_band == "80-100":
            clauses.append(
                and_(
                    CecchinoPurchasabilityEvaluation.purchasability_score >= 80,
                    CecchinoPurchasabilityEvaluation.purchasability_score <= 100,
                )
            )
    return clauses


def query_validation_rows(
    db: Session,
    *,
    date_from: date | None = None,
    date_to: date | None = None,
    candidate_version: str | None = None,
    competition_id: int | None = None,
    market_key: str | None = None,
    score_band: str | None = None,
    evaluation_status: str | None = None,
    source_cohort: str | None = None,
    source_cohorts: list[str] | None = None,
    promotion_eligible_only: bool = True,
    only_current: bool = True,
) -> list[CecchinoPurchasabilityEvaluation]:
    clauses = _filters_clause(
        date_from=date_from,
        date_to=date_to,
        candidate_version=candidate_version,
        competition_id=competition_id,
        market_key=market_key,
        score_band=score_band,
        evaluation_status=evaluation_status,
        source_cohort=source_cohort,
        source_cohorts=source_cohorts,
        promotion_eligible_only=promotion_eligible_only,
        only_current=only_current,
    )
    stmt: Select[Any] = (
        select(CecchinoPurchasabilityEvaluation)
        .where(*clauses)
        .order_by(
            CecchinoPurchasabilityEvaluation.scan_date.desc(),
            CecchinoPurchasabilityEvaluation.id.desc(),
        )
    )
    return list(db.scalars(stmt).all())


def build_purchasability_validation_health(
    db: Session,
    *,
    date_from: date,
    date_to: date,
    competition_id: int | None = None,
) -> dict[str, Any]:
    q = select(CecchinoTodayFixture).where(
        CecchinoTodayFixture.scan_date >= date_from,
        CecchinoTodayFixture.scan_date <= date_to,
        CecchinoTodayFixture.eligibility_status == ELIGIBILITY_ELIGIBLE,
    )
    if competition_id is not None:
        q = q.where(CecchinoTodayFixture.competition_id == int(competition_id))
    fixtures = list(db.scalars(q).all())

    with_panel = 0
    with_preview = 0
    with_verified = 0
    with_active_candidate = 0
    only_derived = 0
    unavailable = 0
    candidate_dist: dict[str, int] = {}
    feature_dist: dict[str, int] = {}
    snapshot_dist: dict[str, int] = {}
    invalid_reasons: dict[str, int] = {}
    mismatch = 0
    first_persisted_snapshot_at: datetime | str | None = None
    last_persisted_snapshot_at: datetime | str | None = None
    newest_eligible_scan_date: date | None = None
    newest_persisted_scan_date: date | None = None
    persisted_ats: list[Any] = []

    for fx in fixtures:
        if fx.scan_date is not None:
            if newest_eligible_scan_date is None or fx.scan_date > newest_eligible_scan_date:
                newest_eligible_scan_date = fx.scan_date
        panel = fx.kpi_panel_json if isinstance(fx.kpi_panel_json, dict) else None
        if panel and _panel_rows(panel):
            with_panel += 1
        else:
            continue

        output = fx.cecchino_output_json if isinstance(fx.cecchino_output_json, dict) else {}
        preview = output.get("purchasability_preview")
        if not isinstance(preview, dict):
            only_derived += 1
            continue
        check = validate_purchasability_preview_snapshot(preview)
        if not check["ok"]:
            for r in check.get("reason_codes") or []:
                invalid_reasons[str(r)] = invalid_reasons.get(str(r), 0) + 1
            unavailable += 1
            continue
        with_preview += 1
        if fx.scan_date is not None:
            if (
                newest_persisted_scan_date is None
                or fx.scan_date > newest_persisted_scan_date
            ):
                newest_persisted_scan_date = fx.scan_date
        snap_at = preview.get("source_snapshot_at")
        if snap_at:
            persisted_ats.append(snap_at)
        if preview.get("status") == "unavailable":
            unavailable += 1
        verified = bool(preview.get("source_snapshot_verified"))
        before = preview.get("source_snapshot_before_kickoff")
        if verified and before is True:
            with_verified += 1
        cv = str(preview.get("candidate_version") or "")
        if cv:
            candidate_dist[cv] = candidate_dist.get(cv, 0) + 1
            if cv == PURCHASABILITY_CANDIDATE_VERSION:
                with_active_candidate += 1
        fv = str(preview.get("feature_version") or "")
        if fv:
            feature_dist[fv] = feature_dist.get(fv, 0) + 1
        sv = str(preview.get("snapshot_version") or "")
        if sv:
            snapshot_dist[sv] = snapshot_dist.get(sv, 0) + 1
        if _timestamps_mismatch(_panel_snapshot_at(panel), preview.get("source_snapshot_at")):
            mismatch += 1

    if persisted_ats:
        try:
            sorted_ats = sorted(str(a) for a in persisted_ats)
            first_persisted_snapshot_at = sorted_ats[0]
            last_persisted_snapshot_at = sorted_ats[-1]
        except Exception:
            first_persisted_snapshot_at = str(persisted_ats[0])
            last_persisted_snapshot_at = str(persisted_ats[-1])

    # Floor prospettico = primo snapshot candidate_2 osservato (non data deploy inventata)
    prospective_floor = first_persisted_snapshot_at
    post_deploy_fixtures = 0
    post_deploy_with_preview = 0
    if prospective_floor:
        # Con floor: tutte le fixture nel range sono "post" rispetto al primo osservato
        # se scan_date >= data del primo snapshot (best-effort da ISO date prefix)
        floor_date = None
        try:
            floor_date = date.fromisoformat(str(prospective_floor)[:10])
        except ValueError:
            floor_date = None
        for fx in fixtures:
            if floor_date is None or (
                fx.scan_date is not None and fx.scan_date >= floor_date
            ):
                post_deploy_fixtures += 1
                out = (
                    fx.cecchino_output_json
                    if isinstance(fx.cecchino_output_json, dict)
                    else {}
                )
                if isinstance(out.get("purchasability_preview"), dict):
                    post_deploy_with_preview += 1
    else:
        post_deploy_fixtures = 0
        post_deploy_with_preview = 0

    denom = with_panel
    coverage = (with_verified / denom) if denom else None

    # Table availability
    table_unavailable = False
    sync_error_count = 0
    try:
        ev_q = select(CecchinoPurchasabilityEvaluation).where(
            CecchinoPurchasabilityEvaluation.scan_date >= date_from,
            CecchinoPurchasabilityEvaluation.scan_date <= date_to,
            CecchinoPurchasabilityEvaluation.is_current.is_(True),
        )
        if competition_id is not None:
            ev_q = ev_q.where(
                CecchinoPurchasabilityEvaluation.competition_id == int(competition_id)
            )
        evals = list(db.scalars(ev_q).all())
    except Exception:
        table_unavailable = True
        evals = []
        sync_error_count = 1

    pending = sum(1 for e in evals if e.evaluation_status == EVAL_PENDING)
    settled = sum(1 for e in evals if e.evaluation_status in (EVAL_WON, EVAL_LOST))
    not_evaluable_count = sum(1 for e in evals if e.evaluation_status == EVAL_NOT_EVALUABLE)
    result_missing_count = sum(1 for e in evals if e.evaluation_status == EVAL_RESULT_MISSING)

    by_cohort: dict[str, int] = {}
    by_status: dict[str, int] = {}
    by_candidate: dict[str, int] = {}
    prospective_rows = 0
    historical_rows = 0
    for e in evals:
        by_cohort[str(e.source_cohort)] = by_cohort.get(str(e.source_cohort), 0) + 1
        by_status[str(e.evaluation_status)] = by_status.get(str(e.evaluation_status), 0) + 1
        by_candidate[str(e.candidate_version)] = (
            by_candidate.get(str(e.candidate_version), 0) + 1
        )
        if e.source_cohort == "prospective_persisted" or e.promotion_eligible:
            prospective_rows += 1
        else:
            historical_rows += 1

    dup_keys: dict[tuple[Any, ...], int] = {}
    for e in evals:
        key = (e.today_fixture_id, e.candidate_version, e.market_key)
        dup_keys[key] = dup_keys.get(key, 0) + 1
    duplicates = sum(1 for v in dup_keys.values() if v > 1)

    persistence_blocking_reason: str | None = None
    if table_unavailable:
        persistence_blocking_reason = "migration_or_table_unavailable"
    elif with_panel > 0 and with_preview == 0 and only_derived == with_panel:
        persistence_blocking_reason = (
            "only_legacy_derived_available"
            if prospective_floor is None
            else "no_post_deploy_scan_detected"
        )
    elif with_preview == 0 and prospective_floor is None:
        persistence_blocking_reason = "no_post_deploy_scan_detected"
    elif with_preview > 0 and len(evals) == 0 and not table_unavailable:
        persistence_blocking_reason = "validation_sync_failed"
    elif with_panel > 0 and with_preview == 0 and invalid_reasons:
        persistence_blocking_reason = "snapshot_build_failed"
    elif with_panel > 0 and with_preview == 0:
        persistence_blocking_reason = "snapshot_not_committed"

    return make_json_safe(
        {
            "status": "ok",
            "version": PURCHASABILITY_VALIDATION_VERSION,
            "date_from": date_from.isoformat(),
            "date_to": date_to.isoformat(),
            "eligible_today_fixtures": len(fixtures),
            "fixtures_with_kpi_panel": with_panel,
            "fixtures_with_persisted_preview": with_preview,
            "fixtures_with_verified_pre_match_preview": with_verified,
            "fixtures_with_active_candidate": with_active_candidate,
            "fixtures_only_derived": only_derived,
            "fixtures_unavailable": unavailable,
            "snapshot_persistence_coverage": coverage,
            "candidate_version_distribution": candidate_dist,
            "feature_version_distribution": feature_dist,
            "snapshot_version_distribution": snapshot_dist,
            "invalid_snapshot_reasons": invalid_reasons,
            "timestamp_mismatch_count": mismatch,
            "duplicate_validation_rows": duplicates,
            "result_pending_count": pending,
            "result_settled_count": settled,
            "validation_rows_total": len(evals),
            "validation_rows_current": len(evals),
            "validation_rows_by_source_cohort": by_cohort,
            "validation_rows_by_evaluation_status": by_status,
            "validation_rows_by_candidate_version": by_candidate,
            "historical_rows_available": historical_rows,
            "prospective_rows_available": prospective_rows,
            "not_evaluable_count": not_evaluable_count,
            "result_missing_count": result_missing_count,
            "first_persisted_snapshot_at": first_persisted_snapshot_at,
            "last_persisted_snapshot_at": last_persisted_snapshot_at,
            "newest_eligible_scan_date": (
                newest_eligible_scan_date.isoformat()
                if newest_eligible_scan_date
                else None
            ),
            "newest_persisted_scan_date": (
                newest_persisted_scan_date.isoformat()
                if newest_persisted_scan_date
                else None
            ),
            "post_deploy_fixtures": post_deploy_fixtures,
            "post_deploy_fixtures_with_preview": post_deploy_with_preview,
            "sync_error_count": sync_error_count,
            "persistence_blocking_reason": persistence_blocking_reason,
            "prospective_monitoring_floor": prospective_floor,
            "persistence_blocking_note": (
                "Describes missing prospective purchasability_preview snapshots; "
                "does not imply absence of historical validation rows."
                if persistence_blocking_reason == "only_legacy_derived_available"
                else None
            ),
        }
    )


def build_purchasability_validation_rows(
    db: Session,
    *,
    date_from: date,
    date_to: date,
    candidate_version: str | None = None,
    competition_id: int | None = None,
    market_key: str | None = None,
    score_band: str | None = None,
    evaluation_status: str | None = None,
    source_cohort: str | None = None,
    source_cohorts: list[str] | None = None,
    promotion_eligible_only: bool = True,
    only_current: bool = True,
    limit: int = 200,
    offset: int = 0,
) -> dict[str, Any]:
    rows = query_validation_rows(
        db,
        date_from=date_from,
        date_to=date_to,
        candidate_version=candidate_version or PURCHASABILITY_CANDIDATE_VERSION,
        competition_id=competition_id,
        market_key=market_key,
        score_band=score_band,
        evaluation_status=evaluation_status,
        source_cohort=source_cohort,
        source_cohorts=source_cohorts,
        promotion_eligible_only=promotion_eligible_only,
        only_current=only_current,
    )
    total = len(rows)
    page = rows[offset : offset + limit]
    items = []
    for e in page:
        items.append(_serialize_validation_row_forensic(e))
    return make_json_safe(
        {
            "status": "ok",
            "version": PURCHASABILITY_VALIDATION_VERSION,
            "total": total,
            "limit": limit,
            "offset": offset,
            "items": items,
        }
    )


def _source_mode_for_cohort(source_cohort: str | None) -> str | None:
    """Deriva source_mode export da source_cohort persistita."""
    if not source_cohort:
        return None
    cohort = str(source_cohort)
    if cohort == "historical_reconstructed_verified":
        return "historical_reconstruction"
    if cohort == "prospective_persisted":
        return "prospective_scan"
    if cohort in {"historical_persisted_verified", "legacy_persisted_backfill"}:
        return "legacy_persisted"
    if cohort in {"historical_diagnostic", "legacy_derived_diagnostic"}:
        return "historical_diagnostic"
    return None


def _serialize_validation_row_forensic(e: CecchinoPurchasabilityEvaluation) -> dict[str, Any]:
    """Schema forensic completo — campi assenti restano null, mai ricostruiti."""
    return {
        "id": e.id,
        "today_fixture_id": e.today_fixture_id,
        "local_fixture_id": e.local_fixture_id,
        "provider_fixture_id": e.provider_fixture_id,
        "competition_id": e.competition_id,
        "scan_date": e.scan_date.isoformat() if e.scan_date else None,
        "kickoff": e.kickoff.isoformat() if e.kickoff else None,
        "country_name": e.country_name,
        "league_name": e.league_name,
        "home_team_name": e.home_team_name,
        "away_team_name": e.away_team_name,
        "source_cohort": e.source_cohort,
        "source_mode": _source_mode_for_cohort(e.source_cohort),
        "snapshot_version": e.snapshot_version,
        "snapshot_hash": e.snapshot_hash,
        "source_snapshot_at": (
            e.source_snapshot_at.isoformat() if e.source_snapshot_at else None
        ),
        "snapshot_timestamp_verified": e.snapshot_timestamp_verified,
        "snapshot_before_kickoff": e.snapshot_before_kickoff,
        "candidate_version": e.candidate_version,
        "candidate_name": e.candidate_name,
        "feature_version": e.feature_version,
        "validation_version": PURCHASABILITY_VALIDATION_VERSION,
        "market_key": e.market_key,
        "market_family": market_family_for(e.market_key),
        "selection": e.selection,
        "calculation_status": e.calculation_status,
        "calculation_quality": e.calculation_quality,
        "purchasability_score": e.purchasability_score,
        "raw_score": float(e.raw_score) if e.raw_score is not None else None,
        "score_band": score_band_for(e.purchasability_score),
        "purchasability_class": e.purchasability_class,
        "phase_1_score": float(e.phase_1_score) if e.phase_1_score is not None else None,
        "phase_2_score": float(e.phase_2_score) if e.phase_2_score is not None else None,
        "reading": e.reading,
        "quota_book": float(e.quota_book) if e.quota_book is not None else None,
        "quota_cecchino": float(e.quota_cecchino) if e.quota_cecchino is not None else None,
        "fair_book_probability": (
            float(e.fair_book_probability) if e.fair_book_probability is not None else None
        ),
        "prob_cecchino": float(e.prob_cecchino) if e.prob_cecchino is not None else None,
        "edge_pct": float(e.edge_pct) if e.edge_pct is not None else None,
        "rating_score": e.rating_score,
        "score_acquisto": float(e.score_acquisto) if e.score_acquisto is not None else None,
        "evaluation_status": e.evaluation_status,
        "evaluation_reason": e.evaluation_reason,
        "result_home_ft": e.result_home_ft,
        "result_away_ft": e.result_away_ft,
        "result_home_ht": e.result_home_ht,
        "result_away_ht": e.result_away_ht,
        "stake_units": float(e.stake_units) if e.stake_units is not None else None,
        "profit_units": float(e.profit_units) if e.profit_units is not None else None,
        "evaluated_at": e.evaluated_at.isoformat() if e.evaluated_at else None,
        "promotion_eligible": e.promotion_eligible,
        "is_current": e.is_current,
        "created_at": e.created_at.isoformat() if getattr(e, "created_at", None) else None,
        "updated_at": e.updated_at.isoformat() if getattr(e, "updated_at", None) else None,
    }


def export_purchasability_validation_csv(
    db: Session,
    *,
    date_from: date,
    date_to: date,
    candidate_version: str | None = None,
    competition_id: int | None = None,
    market_key: str | None = None,
    score_band: str | None = None,
    evaluation_status: str | None = None,
    source_cohort: str | None = None,
    promotion_eligible_only: bool = True,
) -> str:
    payload = build_purchasability_validation_rows(
        db,
        date_from=date_from,
        date_to=date_to,
        candidate_version=candidate_version,
        competition_id=competition_id,
        market_key=market_key,
        score_band=score_band,
        evaluation_status=evaluation_status,
        source_cohort=source_cohort,
        promotion_eligible_only=promotion_eligible_only,
        limit=100_000,
        offset=0,
    )
    buf = io.StringIO()
    fields = [
        "id",
        "today_fixture_id",
        "scan_date",
        "market_key",
        "purchasability_score",
        "score_band",
        "evaluation_status",
        "quota_book",
        "profit_units",
        "source_cohort",
        "promotion_eligible",
        "candidate_version",
    ]
    writer = csv.DictWriter(buf, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    for item in payload.get("items") or []:
        writer.writerow(item)
    return buf.getvalue()
