"""Dataset empirico Balance v5 — Fase 2/3 Step 2A.

Contratto, persistenza, settlement e sync. Non modifica formule Balance.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from collections import Counter
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.cecchino_balance_v5_evaluation import (
    EVAL_CANCELLED,
    EVAL_NOT_EVALUABLE,
    EVAL_PENDING,
    EVAL_POSTPONED,
    EVAL_RESULT_MISSING,
    EVAL_SETTLED,
    OUTCOME_AWAY,
    OUTCOME_DRAW,
    OUTCOME_HOME,
    CecchinoBalanceV5Evaluation,
)
from app.models.cecchino_today_fixture import (
    ELIGIBILITY_ELIGIBLE,
    CecchinoTodayFixture,
)
from app.services.cecchino.cecchino_balance_v5 import VERSION as BALANCE_V5_VERSION
from app.services.cecchino.cecchino_balance_v5_monitoring import (
    BALANCE_MONITORING_SNAPSHOT_VERSION,
    resolve_balance_v5_monitoring_snapshot,
)
from app.services.cecchino.cecchino_monitoring_cohorts import (
    COHORT_FILTER_ALL,
    COHORT_HISTORICAL_DIAGNOSTIC,
    COHORT_HISTORICAL_PERSISTED_VERIFIED,
    COHORT_HISTORICAL_RECONSTRUCTED_VERIFIED,
    COHORT_PROSPECTIVE,
    COHORT_UNUSABLE,
    parse_export_cohort_filter,
)
from app.services.cecchino.cecchino_purchasability_audit import make_json_safe

logger = logging.getLogger(__name__)

BALANCE_EMPIRICAL_DATASET_VERSION = "cecchino_balance_v5_empirical_dataset_v1"
BALANCE_EMPIRICAL_TARGET_CONTRACT_VERSION = (
    "cecchino_balance_v5_empirical_target_contract_v1"
)
BALANCE_EMPIRICAL_SYNC_CONFIRM_TOKEN = "SYNC_BALANCE_V5_EMPIRICAL_DATASET"

# Alias for brief naming
CECCHINO_BALANCE_V5_EMPIRICAL_DATASET_VERSION = BALANCE_EMPIRICAL_DATASET_VERSION


def _dec(v: Any) -> Decimal | None:
    if v is None:
        return None
    try:
        return Decimal(str(v))
    except Exception:
        return None


def _parse_dt(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    try:
        raw = str(value).replace("Z", "+00:00")
        dt = datetime.fromisoformat(raw)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def _norm_selection(raw: Any) -> str | None:
    if raw is None:
        return None
    s = str(raw).strip().upper()
    if s in {"1", "HOME", "H"}:
        return "1"
    if s in {"X", "DRAW", "D"}:
        return "X"
    if s in {"2", "AWAY", "A"}:
        return "2"
    return None


def compute_balance_snapshot_hash(pre_match: dict[str, Any]) -> str:
    """SHA-256 deterministico solo su campi pre-match (no settlement/timestamps di sistema)."""
    payload = {
        "balance_version": pre_match.get("balance_version"),
        "snapshot_version": pre_match.get("snapshot_version"),
        "f36_index": pre_match.get("f36_index"),
        "f36_class": pre_match.get("f36_class"),
        "dominance_index": pre_match.get("dominance_index"),
        "dominance_class": pre_match.get("dominance_class"),
        "dominance_selection": pre_match.get("dominance_selection"),
        "draw_credibility_index": pre_match.get("draw_credibility_index"),
        "draw_credibility_class": pre_match.get("draw_credibility_class"),
        "gap_index": pre_match.get("gap_index"),
        "gap_class": pre_match.get("gap_class"),
        "prob_1_norm": pre_match.get("prob_1_norm"),
        "prob_x_norm": pre_match.get("prob_x_norm"),
        "prob_2_norm": pre_match.get("prob_2_norm"),
        "book_prob_1": pre_match.get("book_prob_1"),
        "book_prob_x": pre_match.get("book_prob_x"),
        "book_prob_2": pre_match.get("book_prob_2"),
        "source_snapshot_at": pre_match.get("source_snapshot_at"),
        "today_fixture_id": pre_match.get("today_fixture_id"),
        "provider_fixture_id": pre_match.get("provider_fixture_id"),
        "local_fixture_id": pre_match.get("local_fixture_id"),
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def build_balance_empirical_target_contract() -> dict[str, Any]:
    return make_json_safe(
        {
            "version": BALANCE_EMPIRICAL_TARGET_CONTRACT_VERSION,
            "module_version": BALANCE_V5_VERSION,
            "pillars": {
                "f36": {
                    "role": "descriptive_structure",
                    "primary_targets": [],
                    "secondary_targets": [
                        "outcome_1x2",
                        "is_draw",
                        "absolute_goal_difference",
                        "total_goals",
                    ],
                },
                "dominance": {
                    "role": "scenario_preference",
                    "primary_targets": ["dominance_selection_hit"],
                    "secondary_targets": [
                        "outcome_1x2",
                        "is_draw",
                        "absolute_goal_difference",
                    ],
                },
                "draw_credibility": {
                    "role": "draw_plausibility",
                    "primary_targets": ["is_draw"],
                    "secondary_targets": ["outcome_1x2"],
                },
                "gap": {
                    "role": "mathematical_coherence",
                    "primary_targets": [],
                    "secondary_targets": [
                        "dominance_selection_hit",
                        "is_draw",
                        "absolute_goal_difference",
                    ],
                },
            },
            "forbidden_interpretations": [
                "f36_is_direct_betting_signal",
                "gap_is_direct_betting_signal",
                "historical_diagnostic_can_promote",
                "pillars_are_directly_comparable",
                "balance_changes_signals_automatically",
            ],
        }
    )


def _promotion_eligible_for_cohort(
    cohort: str,
    *,
    pre_match_verified: bool | None,
    source_mode: str | None,
    snapshot_at: Any,
) -> bool:
    if cohort != COHORT_PROSPECTIVE:
        return False
    if pre_match_verified is not True:
        return False
    if not snapshot_at:
        return False
    if source_mode and source_mode not in {
        "prospective_scan",
        None,
    }:
        # prospective_scan is the canonical persisted mode
        pass
    return True


def build_balance_empirical_record(
    fixture: CecchinoTodayFixture,
    *,
    resolved_snapshot: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Costruisce il dict pre-match (+ placeholder settlement) da fixture."""
    resolved = resolved_snapshot or resolve_balance_v5_monitoring_snapshot(fixture)
    if resolved.get("mode") == "unavailable" or not resolved.get("payload"):
        return None
    payload = resolved["payload"]
    if not isinstance(payload, dict) or payload.get("status") == "unavailable":
        return None

    cohort = str(resolved.get("source_cohort") or COHORT_HISTORICAL_DIAGNOSTIC)
    source_mode = payload.get("source_mode") or resolved.get("mode")
    snap_at = payload.get("snapshot_timestamp")
    pre_match = bool(payload.get("pre_match_verified") is True)
    analysis_eligible = cohort != COHORT_UNUSABLE
    promotion_eligible = _promotion_eligible_for_cohort(
        cohort,
        pre_match_verified=payload.get("pre_match_verified"),
        source_mode=str(source_mode) if source_mode else None,
        snapshot_at=snap_at,
    )

    warnings = payload.get("warning_codes") or []
    if isinstance(warnings, list):
        warning_codes = json.dumps([str(w) for w in warnings], ensure_ascii=False)
    else:
        warning_codes = str(warnings) if warnings else None

    pre_match_fields = {
        "today_fixture_id": fixture.id,
        "provider_fixture_id": fixture.provider_fixture_id,
        "local_fixture_id": fixture.local_fixture_id,
        "balance_version": str(payload.get("balance_version") or BALANCE_V5_VERSION),
        "snapshot_version": str(
            payload.get("snapshot_version") or BALANCE_MONITORING_SNAPSHOT_VERSION
        ),
        "f36_index": payload.get("f36_index"),
        "f36_class": payload.get("f36_class"),
        "dominance_index": payload.get("dominance_index"),
        "dominance_class": payload.get("dominance_class"),
        "dominance_selection": _norm_selection(payload.get("dominance_selection")),
        "draw_credibility_index": payload.get("draw_credibility_index"),
        "draw_credibility_class": payload.get("draw_credibility_class"),
        "gap_index": payload.get("gap_index"),
        "gap_class": payload.get("gap_class"),
        "prob_1_norm": payload.get("prob_1_norm"),
        "prob_x_norm": payload.get("prob_x_norm"),
        "prob_2_norm": payload.get("prob_2_norm"),
        "book_prob_1": payload.get("book_prob_1"),
        "book_prob_x": payload.get("book_prob_x"),
        "book_prob_2": payload.get("book_prob_2"),
        "source_snapshot_at": snap_at,
    }
    snap_hash = compute_balance_snapshot_hash(pre_match_fields)

    return {
        "today_fixture_id": int(fixture.id),
        "local_fixture_id": fixture.local_fixture_id,
        "provider_fixture_id": fixture.provider_fixture_id,
        "competition_id": fixture.competition_id,
        "scan_date": fixture.scan_date,
        "kickoff": fixture.kickoff,
        "country_name": fixture.country_name,
        "league_name": fixture.league_name,
        "home_team_name": fixture.home_team_name,
        "away_team_name": fixture.away_team_name,
        "empirical_dataset_version": BALANCE_EMPIRICAL_DATASET_VERSION,
        "balance_version": pre_match_fields["balance_version"],
        "snapshot_version": pre_match_fields["snapshot_version"],
        "snapshot_hash": snap_hash,
        "source_mode": str(source_mode) if source_mode else None,
        "source_cohort": cohort,
        "source_snapshot_at": _parse_dt(snap_at),
        "pre_match_verified": payload.get("pre_match_verified"),
        "book_verified": payload.get("book_verified"),
        "warning_codes": warning_codes,
        "f36_index": _dec(payload.get("f36_index")),
        "f36_class": payload.get("f36_class"),
        "dominance_index": _dec(payload.get("dominance_index")),
        "dominance_class": payload.get("dominance_class"),
        "dominance_selection": pre_match_fields["dominance_selection"],
        "draw_credibility_index": _dec(payload.get("draw_credibility_index")),
        "draw_credibility_class": payload.get("draw_credibility_class"),
        "gap_index": _dec(payload.get("gap_index")),
        "gap_class": payload.get("gap_class"),
        "prob_1_norm": _dec(payload.get("prob_1_norm")),
        "prob_x_norm": _dec(payload.get("prob_x_norm")),
        "prob_2_norm": _dec(payload.get("prob_2_norm")),
        "book_prob_1": _dec(payload.get("book_prob_1")),
        "book_prob_x": _dec(payload.get("book_prob_x")),
        "book_prob_2": _dec(payload.get("book_prob_2")),
        "analysis_eligible": analysis_eligible,
        "promotion_eligible": promotion_eligible and analysis_eligible,
        "is_current": True,
    }


def _apply_settlement_fields(
    record: dict[str, Any],
    fixture: CecchinoTodayFixture,
) -> dict[str, Any]:
    """Calcola campi post-match senza mutare pre-match."""
    status_raw = str(getattr(fixture, "match_status", None) or "").lower()
    ft_h = fixture.score_fulltime_home
    ft_a = fixture.score_fulltime_away
    ht_h = fixture.score_halftime_home
    ht_a = fixture.score_halftime_away

    if "cancel" in status_raw:
        record.update(
            {
                "evaluation_status": EVAL_CANCELLED,
                "evaluation_reason": "match_cancelled",
                "ft_home": ft_h,
                "ft_away": ft_a,
                "ht_home": ht_h,
                "ht_away": ht_a,
                "outcome_1x2": None,
                "is_draw": None,
                "total_goals": None,
                "absolute_goal_difference": None,
                "dominance_selection_hit": None,
                "evaluated_at": datetime.now(timezone.utc),
            }
        )
        return record
    if "postpone" in status_raw:
        record.update(
            {
                "evaluation_status": EVAL_POSTPONED,
                "evaluation_reason": "match_postponed",
                "ft_home": ft_h,
                "ft_away": ft_a,
                "ht_home": ht_h,
                "ht_away": ht_a,
                "outcome_1x2": None,
                "is_draw": None,
                "total_goals": None,
                "absolute_goal_difference": None,
                "dominance_selection_hit": None,
                "evaluated_at": datetime.now(timezone.utc),
            }
        )
        return record

    if ft_h is None or ft_a is None:
        # Partita conclusa senza score → result_missing; altrimenti pending
        finished_hint = any(
            x in status_raw for x in ("ft", "finished", "ended", "aet", "pen")
        )
        if finished_hint:
            record.update(
                {
                    "evaluation_status": EVAL_RESULT_MISSING,
                    "evaluation_reason": "finished_without_score",
                    "ft_home": None,
                    "ft_away": None,
                    "ht_home": ht_h,
                    "ht_away": ht_a,
                    "outcome_1x2": None,
                    "is_draw": None,
                    "total_goals": None,
                    "absolute_goal_difference": None,
                    "dominance_selection_hit": None,
                    "evaluated_at": datetime.now(timezone.utc),
                }
            )
        else:
            record.update(
                {
                    "evaluation_status": EVAL_PENDING,
                    "evaluation_reason": "awaiting_result",
                    "ft_home": None,
                    "ft_away": None,
                    "ht_home": ht_h,
                    "ht_away": ht_a,
                    "outcome_1x2": None,
                    "is_draw": None,
                    "total_goals": None,
                    "absolute_goal_difference": None,
                    "dominance_selection_hit": None,
                    "evaluated_at": None,
                }
            )
        return record

    if ft_h > ft_a:
        outcome = OUTCOME_HOME
        code = "1"
    elif ft_h < ft_a:
        outcome = OUTCOME_AWAY
        code = "2"
    else:
        outcome = OUTCOME_DRAW
        code = "X"

    sel = _norm_selection(record.get("dominance_selection"))
    hit: bool | None
    if sel is None:
        hit = None
    else:
        hit = sel == code

    record.update(
        {
            "evaluation_status": EVAL_SETTLED,
            "evaluation_reason": "ft_available",
            "ft_home": int(ft_h),
            "ft_away": int(ft_a),
            "ht_home": ht_h,
            "ht_away": ht_a,
            "outcome_1x2": outcome,
            "is_draw": outcome == OUTCOME_DRAW,
            "total_goals": int(ft_h) + int(ft_a),
            "absolute_goal_difference": abs(int(ft_h) - int(ft_a)),
            "dominance_selection_hit": hit,
            "evaluated_at": datetime.now(timezone.utc),
        }
    )
    return record


def upsert_balance_empirical_record(
    db: Session,
    *,
    fixture: CecchinoTodayFixture,
    resolved_snapshot: dict[str, Any] | None = None,
    commit: bool = False,
) -> CecchinoBalanceV5Evaluation | None:
    t0 = time.perf_counter()
    try:
        built = build_balance_empirical_record(
            fixture, resolved_snapshot=resolved_snapshot
        )
        if built is None:
            return None
        built = _apply_settlement_fields(built, fixture)

        existing = db.scalar(
            select(CecchinoBalanceV5Evaluation).where(
                CecchinoBalanceV5Evaluation.today_fixture_id == int(fixture.id),
                CecchinoBalanceV5Evaluation.balance_version == built["balance_version"],
                CecchinoBalanceV5Evaluation.snapshot_hash == built["snapshot_hash"],
            )
        )
        if existing is not None:
            # Aggiorna solo settlement + governance is_current
            for key in (
                "evaluation_status",
                "evaluation_reason",
                "ft_home",
                "ft_away",
                "ht_home",
                "ht_away",
                "outcome_1x2",
                "is_draw",
                "total_goals",
                "absolute_goal_difference",
                "dominance_selection_hit",
                "evaluated_at",
                "analysis_eligible",
                "promotion_eligible",
            ):
                setattr(existing, key, built.get(key))
            if not existing.is_current:
                # Reactivate this hash as current
                _deactivate_other_current(
                    db,
                    today_fixture_id=int(fixture.id),
                    balance_version=built["balance_version"],
                    keep_id=existing.id,
                )
                existing.is_current = True
            logger.info(
                "balance_empirical_record_upserted fixture_id=%s source_cohort=%s "
                "balance_version=%s status=%s elapsed_ms=%s",
                fixture.id,
                existing.source_cohort,
                existing.balance_version,
                "updated",
                round((time.perf_counter() - t0) * 1000, 2),
            )
            if commit:
                db.commit()
            else:
                db.flush()
            return existing

        _deactivate_other_current(
            db,
            today_fixture_id=int(fixture.id),
            balance_version=built["balance_version"],
            keep_id=None,
        )
        row = CecchinoBalanceV5Evaluation(**built)
        db.add(row)
        if commit:
            db.commit()
            db.refresh(row)
        else:
            db.flush()
        logger.info(
            "balance_empirical_record_upserted fixture_id=%s source_cohort=%s "
            "balance_version=%s status=%s elapsed_ms=%s",
            fixture.id,
            row.source_cohort,
            row.balance_version,
            "inserted",
            round((time.perf_counter() - t0) * 1000, 2),
        )
        return row
    except Exception as exc:
        logger.exception(
            "balance_empirical_record_failed fixture_id=%s error_code=%s",
            getattr(fixture, "id", None),
            type(exc).__name__,
        )
        raise


def _deactivate_other_current(
    db: Session,
    *,
    today_fixture_id: int,
    balance_version: str,
    keep_id: int | None,
) -> None:
    q = select(CecchinoBalanceV5Evaluation).where(
        CecchinoBalanceV5Evaluation.today_fixture_id == today_fixture_id,
        CecchinoBalanceV5Evaluation.balance_version == balance_version,
        CecchinoBalanceV5Evaluation.is_current.is_(True),
    )
    for row in db.scalars(q).all():
        if keep_id is not None and row.id == keep_id:
            continue
        row.is_current = False


def settle_balance_empirical_record(
    db: Session,
    *,
    fixture: CecchinoTodayFixture,
    commit: bool = False,
) -> CecchinoBalanceV5Evaluation | None:
    t0 = time.perf_counter()
    try:
        row = db.scalar(
            select(CecchinoBalanceV5Evaluation).where(
                CecchinoBalanceV5Evaluation.today_fixture_id == int(fixture.id),
                CecchinoBalanceV5Evaluation.is_current.is_(True),
            )
        )
        if row is None:
            # Crea se manca
            return upsert_balance_empirical_record(db, fixture=fixture, commit=commit)

        snap_hash_before = row.snapshot_hash
        fields: dict[str, Any] = {
            "dominance_selection": row.dominance_selection,
        }
        settled = _apply_settlement_fields(fields, fixture)
        for key in (
            "evaluation_status",
            "evaluation_reason",
            "ft_home",
            "ft_away",
            "ht_home",
            "ht_away",
            "outcome_1x2",
            "is_draw",
            "total_goals",
            "absolute_goal_difference",
            "dominance_selection_hit",
            "evaluated_at",
        ):
            setattr(row, key, settled.get(key))
        assert row.snapshot_hash == snap_hash_before
        logger.info(
            "balance_empirical_record_settled fixture_id=%s source_cohort=%s "
            "balance_version=%s status=%s elapsed_ms=%s",
            fixture.id,
            row.source_cohort,
            row.balance_version,
            row.evaluation_status,
            round((time.perf_counter() - t0) * 1000, 2),
        )
        if commit:
            db.commit()
        else:
            db.flush()
        return row
    except Exception as exc:
        logger.exception(
            "balance_empirical_record_failed fixture_id=%s error_code=%s",
            getattr(fixture, "id", None),
            type(exc).__name__,
        )
        raise


def _iter_source_fixtures(
    db: Session,
    *,
    date_from: date,
    date_to: date,
    competition_id: int | None,
) -> list[CecchinoTodayFixture]:
    q = select(CecchinoTodayFixture).where(
        CecchinoTodayFixture.scan_date >= date_from,
        CecchinoTodayFixture.scan_date <= date_to,
        CecchinoTodayFixture.eligibility_status == ELIGIBILITY_ELIGIBLE,
    )
    if competition_id is not None:
        q = q.where(CecchinoTodayFixture.competition_id == int(competition_id))
    return list(db.scalars(q).all())


def sync_balance_empirical_dataset(
    db: Session,
    *,
    date_from: date,
    date_to: date,
    competition_id: int | None = None,
    source_cohort: str | None = None,
    dry_run: bool = True,
    commit: bool = False,
    confirm: str | None = None,
) -> dict[str, Any]:
    if not dry_run and confirm != BALANCE_EMPIRICAL_SYNC_CONFIRM_TOKEN:
        raise ValueError("invalid_confirm_token")

    t0 = time.perf_counter()
    cohort_filter = parse_export_cohort_filter(source_cohort or COHORT_FILTER_ALL)
    logger.info(
        "balance_empirical_sync_started date_from=%s date_to=%s source_cohort=%s dry_run=%s",
        date_from.isoformat(),
        date_to.isoformat(),
        cohort_filter,
        dry_run,
    )

    fixtures = _iter_source_fixtures(
        db, date_from=date_from, date_to=date_to, competition_id=competition_id
    )
    existing_rows = list(
        db.scalars(
            select(CecchinoBalanceV5Evaluation).where(
                CecchinoBalanceV5Evaluation.scan_date >= date_from,
                CecchinoBalanceV5Evaluation.scan_date <= date_to,
                CecchinoBalanceV5Evaluation.is_current.is_(True),
            )
        ).all()
    )
    if competition_id is not None:
        existing_rows = [
            r for r in existing_rows if r.competition_id == int(competition_id)
        ]

    by_existing_fid = {int(r.today_fixture_id): r for r in existing_rows}
    plan_new = 0
    plan_update = 0
    plan_skip = 0
    errors: list[dict[str, Any]] = []
    cohort_counts: Counter[str] = Counter()
    status_counts: Counter[str] = Counter()
    versions: Counter[str] = Counter()
    inserted = 0
    updated = 0
    failed = 0
    dates: list[date] = []

    for fx in fixtures:
        try:
            resolved = resolve_balance_v5_monitoring_snapshot(fx)
            built = build_balance_empirical_record(fx, resolved_snapshot=resolved)
            if built is None:
                plan_skip += 1
                continue
            if cohort_filter != COHORT_FILTER_ALL and built["source_cohort"] != cohort_filter:
                plan_skip += 1
                continue
            built = _apply_settlement_fields(built, fx)
            cohort_counts[str(built["source_cohort"])] += 1
            status_counts[str(built["evaluation_status"])] += 1
            versions[str(built["balance_version"])] += 1
            if fx.scan_date:
                dates.append(fx.scan_date)

            prev = by_existing_fid.get(int(fx.id))
            if prev is None:
                plan_new += 1
            elif (
                prev.snapshot_hash == built["snapshot_hash"]
                and prev.evaluation_status == built["evaluation_status"]
            ):
                plan_skip += 1
            else:
                plan_update += 1

            if not dry_run:
                with db.begin_nested():
                    upsert_balance_empirical_record(
                        db, fixture=fx, resolved_snapshot=resolved, commit=False
                    )
                if prev is None:
                    inserted += 1
                else:
                    updated += 1
        except Exception as exc:
            failed += 1
            errors.append(
                {
                    "today_fixture_id": fx.id,
                    "error_code": type(exc).__name__,
                    "message": str(exc)[:200],
                }
            )
            logger.exception(
                "balance_empirical_record_failed fixture_id=%s error_code=%s",
                fx.id,
                type(exc).__name__,
            )

    if not dry_run and commit:
        db.commit()

    elapsed_ms = round((time.perf_counter() - t0) * 1000, 2)
    payload = make_json_safe(
        {
            "status": "ok",
            "dry_run": dry_run,
            "dataset_version": BALANCE_EMPIRICAL_DATASET_VERSION,
            "date_from": date_from.isoformat(),
            "date_to": date_to.isoformat(),
            "source_fixtures": len(fixtures),
            "rows_already_present": len(existing_rows),
            "rows_new": plan_new,
            "rows_updatable": plan_update,
            "rows_skipped": plan_skip,
            "inserted": inserted if not dry_run else 0,
            "updated": updated if not dry_run else 0,
            "failed": failed,
            "pending": status_counts.get(EVAL_PENDING, 0),
            "settled": status_counts.get(EVAL_SETTLED, 0),
            "not_evaluable": status_counts.get(EVAL_NOT_EVALUABLE, 0)
            + status_counts.get(EVAL_CANCELLED, 0)
            + status_counts.get(EVAL_POSTPONED, 0),
            "result_missing": status_counts.get(EVAL_RESULT_MISSING, 0),
            "cohorts": dict(cohort_counts),
            "versions": dict(versions),
            "duplicates": 0,
            "errors": errors[:50],
            "first_scan_date": min(dates).isoformat() if dates else None,
            "last_scan_date": max(dates).isoformat() if dates else None,
            "elapsed_ms": elapsed_ms,
        }
    )
    logger.info(
        "balance_empirical_sync_completed date_from=%s date_to=%s source_cohort=%s "
        "elapsed_ms=%s dry_run=%s fixtures=%s",
        date_from.isoformat(),
        date_to.isoformat(),
        cohort_filter,
        elapsed_ms,
        dry_run,
        len(fixtures),
    )
    return payload


def _query_base(
    db: Session,
    *,
    date_from: date,
    date_to: date,
    competition_id: int | None = None,
    source_cohort: str | None = None,
    evaluation_status: str | None = None,
    f36_class: str | None = None,
    dominance_class: str | None = None,
    draw_credibility_class: str | None = None,
    gap_class: str | None = None,
    only_current: bool = True,
):
    q = select(CecchinoBalanceV5Evaluation).where(
        CecchinoBalanceV5Evaluation.scan_date >= date_from,
        CecchinoBalanceV5Evaluation.scan_date <= date_to,
    )
    if only_current:
        q = q.where(CecchinoBalanceV5Evaluation.is_current.is_(True))
    if competition_id is not None:
        q = q.where(CecchinoBalanceV5Evaluation.competition_id == int(competition_id))
    cohort = parse_export_cohort_filter(source_cohort or COHORT_FILTER_ALL)
    if cohort != COHORT_FILTER_ALL:
        q = q.where(CecchinoBalanceV5Evaluation.source_cohort == cohort)
    if evaluation_status:
        q = q.where(CecchinoBalanceV5Evaluation.evaluation_status == evaluation_status)
    if f36_class:
        q = q.where(CecchinoBalanceV5Evaluation.f36_class == f36_class)
    if dominance_class:
        q = q.where(CecchinoBalanceV5Evaluation.dominance_class == dominance_class)
    if draw_credibility_class:
        q = q.where(
            CecchinoBalanceV5Evaluation.draw_credibility_class == draw_credibility_class
        )
    if gap_class:
        q = q.where(CecchinoBalanceV5Evaluation.gap_class == gap_class)
    return q


def query_balance_empirical_rows(
    db: Session,
    *,
    date_from: date,
    date_to: date,
    competition_id: int | None = None,
    source_cohort: str | None = None,
    evaluation_status: str | None = None,
    f36_class: str | None = None,
    dominance_class: str | None = None,
    draw_credibility_class: str | None = None,
    gap_class: str | None = None,
    limit: int | None = 200,
    offset: int | None = 0,
) -> dict[str, Any]:
    q = _query_base(
        db,
        date_from=date_from,
        date_to=date_to,
        competition_id=competition_id,
        source_cohort=source_cohort,
        evaluation_status=evaluation_status,
        f36_class=f36_class,
        dominance_class=dominance_class,
        draw_credibility_class=draw_credibility_class,
        gap_class=gap_class,
    )
    rows = list(db.scalars(q.order_by(CecchinoBalanceV5Evaluation.scan_date.desc())).all())
    total = len(rows)
    off = int(offset or 0)
    lim = int(limit) if limit is not None else total
    page = rows[off : off + lim]
    return make_json_safe(
        {
            "status": "ok",
            "dataset_version": BALANCE_EMPIRICAL_DATASET_VERSION,
            "total": total,
            "limit": lim,
            "offset": off,
            "items": [_serialize_row(r) for r in page],
        }
    )


def _serialize_row(r: CecchinoBalanceV5Evaluation) -> dict[str, Any]:
    return {
        "id": r.id,
        "today_fixture_id": r.today_fixture_id,
        "local_fixture_id": r.local_fixture_id,
        "provider_fixture_id": r.provider_fixture_id,
        "competition_id": r.competition_id,
        "scan_date": r.scan_date.isoformat() if r.scan_date else None,
        "kickoff": r.kickoff.isoformat() if r.kickoff else None,
        "country_name": r.country_name,
        "league_name": r.league_name,
        "home_team_name": r.home_team_name,
        "away_team_name": r.away_team_name,
        "empirical_dataset_version": r.empirical_dataset_version,
        "balance_version": r.balance_version,
        "snapshot_version": r.snapshot_version,
        "snapshot_hash": r.snapshot_hash,
        "source_mode": r.source_mode,
        "source_cohort": r.source_cohort,
        "source_snapshot_at": (
            r.source_snapshot_at.isoformat() if r.source_snapshot_at else None
        ),
        "pre_match_verified": r.pre_match_verified,
        "book_verified": r.book_verified,
        "warning_codes": r.warning_codes,
        "f36_index": float(r.f36_index) if r.f36_index is not None else None,
        "f36_class": r.f36_class,
        "dominance_index": float(r.dominance_index) if r.dominance_index is not None else None,
        "dominance_class": r.dominance_class,
        "dominance_selection": r.dominance_selection,
        "draw_credibility_index": (
            float(r.draw_credibility_index) if r.draw_credibility_index is not None else None
        ),
        "draw_credibility_class": r.draw_credibility_class,
        "gap_index": float(r.gap_index) if r.gap_index is not None else None,
        "gap_class": r.gap_class,
        "prob_1_norm": float(r.prob_1_norm) if r.prob_1_norm is not None else None,
        "prob_x_norm": float(r.prob_x_norm) if r.prob_x_norm is not None else None,
        "prob_2_norm": float(r.prob_2_norm) if r.prob_2_norm is not None else None,
        "book_prob_1": float(r.book_prob_1) if r.book_prob_1 is not None else None,
        "book_prob_x": float(r.book_prob_x) if r.book_prob_x is not None else None,
        "book_prob_2": float(r.book_prob_2) if r.book_prob_2 is not None else None,
        "evaluation_status": r.evaluation_status,
        "evaluation_reason": r.evaluation_reason,
        "ft_home": r.ft_home,
        "ft_away": r.ft_away,
        "ht_home": r.ht_home,
        "ht_away": r.ht_away,
        "outcome_1x2": r.outcome_1x2,
        "is_draw": r.is_draw,
        "total_goals": r.total_goals,
        "absolute_goal_difference": r.absolute_goal_difference,
        "dominance_selection_hit": r.dominance_selection_hit,
        "evaluated_at": r.evaluated_at.isoformat() if r.evaluated_at else None,
        "analysis_eligible": r.analysis_eligible,
        "promotion_eligible": r.promotion_eligible,
        "is_current": r.is_current,
    }


def build_balance_empirical_cardinality(
    db: Session,
    *,
    date_from: date,
    date_to: date,
    competition_id: int | None = None,
    source_cohort: str | None = None,
) -> dict[str, Any]:
    rows = list(
        db.scalars(
            _query_base(
                db,
                date_from=date_from,
                date_to=date_to,
                competition_id=competition_id,
                source_cohort=source_cohort,
            )
        ).all()
    )
    fixtures = {int(r.today_fixture_id) for r in rows}
    return make_json_safe(
        {
            "status": "ok",
            "dataset_version": BALANCE_EMPIRICAL_DATASET_VERSION,
            "fixtures": len(fixtures),
            "rows": len(rows),
            "settled": sum(1 for r in rows if r.evaluation_status == EVAL_SETTLED),
            "pending": sum(1 for r in rows if r.evaluation_status == EVAL_PENDING),
            "verified": sum(
                1
                for r in rows
                if r.source_cohort
                in {
                    COHORT_PROSPECTIVE,
                    COHORT_HISTORICAL_PERSISTED_VERIFIED,
                    COHORT_HISTORICAL_RECONSTRUCTED_VERIFIED,
                }
            ),
            "diagnostic": sum(
                1 for r in rows if r.source_cohort == COHORT_HISTORICAL_DIAGNOSTIC
            ),
            "prospective": sum(1 for r in rows if r.source_cohort == COHORT_PROSPECTIVE),
            "analysis_eligible": sum(1 for r in rows if r.analysis_eligible),
            "promotion_eligible": sum(1 for r in rows if r.promotion_eligible),
            "by_source_cohort": dict(Counter(r.source_cohort for r in rows)),
            "by_evaluation_status": dict(Counter(r.evaluation_status for r in rows)),
        }
    )


def build_balance_empirical_health(
    db: Session,
    *,
    date_from: date,
    date_to: date,
    competition_id: int | None = None,
    source_cohort: str | None = None,
) -> dict[str, Any]:
    card = build_balance_empirical_cardinality(
        db,
        date_from=date_from,
        date_to=date_to,
        competition_id=competition_id,
        source_cohort=source_cohort,
    )
    rows = list(
        db.scalars(
            _query_base(
                db,
                date_from=date_from,
                date_to=date_to,
                competition_id=competition_id,
                source_cohort=source_cohort,
            )
        ).all()
    )
    ts_verified = sum(1 for r in rows if r.pre_match_verified is True)
    ts_unverified = sum(1 for r in rows if r.pre_match_verified is not True)
    book_verified = sum(1 for r in rows if r.book_verified is True)
    with_snap = sum(1 for r in rows if r.source_snapshot_at is not None)
    return make_json_safe(
        {
            "status": "ok",
            "dataset_version": BALANCE_EMPIRICAL_DATASET_VERSION,
            "target_contract_version": BALANCE_EMPIRICAL_TARGET_CONTRACT_VERSION,
            "balance_version": BALANCE_V5_VERSION,
            "readiness": "empirical_dataset_collecting",
            "cardinality": card,
            "timestamp_verified": ts_verified,
            "timestamp_unverified": ts_unverified,
            "pre_match_snapshots": with_snap,
            "book_verified": book_verified,
            "analysis_eligible": card.get("analysis_eligible"),
            "promotion_eligible": card.get("promotion_eligible"),
            "notes": [
                "Dataset empirico in raccolta",
                "historical_diagnostic non promuove il modulo",
                "Nessuna modifica alle formule Balance",
            ],
        }
    )


def build_balance_empirical_summary(
    db: Session,
    *,
    date_from: date,
    date_to: date,
    competition_id: int | None = None,
    source_cohort: str | None = None,
) -> dict[str, Any]:
    health = build_balance_empirical_health(
        db,
        date_from=date_from,
        date_to=date_to,
        competition_id=competition_id,
        source_cohort=source_cohort,
    )
    return make_json_safe(
        {
            "status": "ok",
            "dataset_version": BALANCE_EMPIRICAL_DATASET_VERSION,
            "health": health,
            "target_contract": build_balance_empirical_target_contract(),
        }
    )


def upsert_balance_empirical_for_fixture_id(
    db: Session,
    today_fixture_id: int,
    *,
    commit: bool = False,
) -> CecchinoBalanceV5Evaluation | None:
    fx = db.get(CecchinoTodayFixture, int(today_fixture_id))
    if fx is None:
        return None
    return upsert_balance_empirical_record(db, fixture=fx, commit=commit)


def settle_balance_empirical_for_fixture_id(
    db: Session,
    today_fixture_id: int,
    *,
    commit: bool = False,
) -> CecchinoBalanceV5Evaluation | None:
    fx = db.get(CecchinoTodayFixture, int(today_fixture_id))
    if fx is None:
        return None
    return settle_balance_empirical_record(db, fixture=fx, commit=commit)
