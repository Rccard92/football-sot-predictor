"""Backfill e diagnostics segnali Cecchino — offline-only (formula V3 + consenso)."""

from __future__ import annotations

import logging
from datetime import date
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models.cecchino_signal_activation import (
    EVAL_LOST,
    EVAL_NOT_EVALUABLE,
    EVAL_PENDING,
    EVAL_RESULT_MISSING,
    EVAL_WON,
    CecchinoSignalActivation,
)
from app.models.cecchino_today_fixture import ELIGIBILITY_ELIGIBLE, CecchinoTodayFixture
from app.services.cecchino.cecchino_constants import STATUS_AVAILABLE
from app.services.cecchino.cecchino_signal_consensus import (
    CURRENT_SIGNAL_FORMULA_VERSION,
    FORMULA_SOURCE_RECOMPUTED_PREMATCH,
    LEGACY_SIGNAL_FORMULA_VERSION,
    PREVIOUS_SIGNAL_FORMULA_VERSION,
    SIGNAL_CONSENSUS_POLICY_VERSION,
    consensus_by_group_from_matrix,
    is_current_signal_matrix,
    normalize_formula_version,
)
from app.services.cecchino.cecchino_signal_evaluation import evaluate_activations_for_fixture
from app.services.cecchino.cecchino_signal_sync import (
    remap_legacy_scala_activations_in_range,
    sync_cecchino_signal_activations,
)
from app.services.cecchino.cecchino_signal_min_odds import list_min_book_odds_for_api
from app.services.cecchino.cecchino_signal_value_gate import merge_sync_value_counters
from app.services.cecchino.cecchino_signal_target_mapping import remap_under_over_activations_in_range
from app.services.cecchino.cecchino_signal_goal_refs import (
    rebuild_signals_matrix_for_output,
    resolve_under_2_5_cecchino_odd_from_fixture,
)
from app.services.cecchino.cecchino_signals_matrix import build_signals_matrix

logger = logging.getLogger(__name__)

DATE_FILTER_FIELD = "scan_date"

_CONSENSUS_SYNC_COUNTER_KEYS: tuple[str, ...] = (
    "groups_consensus_passed",
    "groups_consensus_rejected",
    "single_formula_exempt_acquired",
    "raw_si_cells",
    "acquired_formula_cells",
    "draw_pt_blocked_by_consensus",
)


def _fixtures_in_range(db: Session, date_from: date, date_to: date) -> list[CecchinoTodayFixture]:
    return list(
        db.scalars(
            select(CecchinoTodayFixture).where(
                CecchinoTodayFixture.scan_date >= date_from,
                CecchinoTodayFixture.scan_date <= date_to,
            ),
        ).all(),
    )


def _has_available_matrix(row: CecchinoTodayFixture) -> bool:
    output = row.cecchino_output_json or {}
    if not isinstance(output, dict):
        return False
    matrix = output.get("signals_matrix")
    return isinstance(matrix, dict) and matrix.get("status") == STATUS_AVAILABLE


def _sample_from_stats(stats_snapshot: dict[str, Any] | None) -> int:
    if not stats_snapshot or not isinstance(stats_snapshot, dict):
        return 0
    block = (stats_snapshot.get("input_snapshot") or stats_snapshot).get("home_away") or {}
    home = int(block.get("home_sample_count") or block.get("home_sample") or 0)
    away = int(block.get("away_sample_count") or block.get("away_sample") or 0)
    return max(0, home + away)


def _num(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _build_current_signals_matrix_from_prematch(row: CecchinoTodayFixture) -> dict[str, Any] | None:
    """Ricostruisce la matrice corrente (V3) in memoria da snapshot pre-match (senza mutare JSON)."""
    output = row.cecchino_output_json
    if not isinstance(output, dict):
        return None
    kpi_panel = row.kpi_panel_json if isinstance(row.kpi_panel_json, dict) else None
    matrix = rebuild_signals_matrix_for_output(
        output,
        sample_home_away_split=_sample_from_stats(row.stats_snapshot_json),
        kpi_panel=kpi_panel,
    )
    if isinstance(matrix, dict) and matrix.get("status") == STATUS_AVAILABLE:
        return matrix

    # Fallback su quote finali + under da fixture (sempre CURRENT via build_signals_matrix)
    final = output.get("final") or {}
    if not isinstance(final, dict) or final.get("status") != STATUS_AVAILABLE:
        return None
    q1 = _num(final.get("quota_1"))
    qx = _num(final.get("quota_x"))
    q2 = _num(final.get("quota_2"))
    if q1 is None or qx is None or q2 is None:
        return None
    matrix = build_signals_matrix(
        q1=q1,
        qx=qx,
        q2=q2,
        sample_home_away_split=_sample_from_stats(row.stats_snapshot_json),
        prob_1=_num(final.get("prob_1")),
        prob_x=_num(final.get("prob_x")),
        prob_2=_num(final.get("prob_2")),
        under_2_5_cecchino_odd=resolve_under_2_5_cecchino_odd_from_fixture(row),
    )
    if matrix.get("status") != STATUS_AVAILABLE:
        return None
    return matrix


def _build_v2_signals_matrix_from_prematch(row: CecchinoTodayFixture) -> dict[str, Any] | None:
    """Compat alias — ricostruisce sempre la formula corrente (V3)."""
    return _build_current_signals_matrix_from_prematch(row)


def _rebuild_signals_matrix_on_row(row: CecchinoTodayFixture) -> bool:
    """Ricostruisce e persiste signals_matrix V3 sul JSON (solo percorsi diagnostics/live)."""
    matrix = _build_current_signals_matrix_from_prematch(row)
    if matrix is None:
        return False
    output = row.cecchino_output_json
    if not isinstance(output, dict):
        return False
    output = dict(output)
    output["signals_matrix"] = matrix
    row.cecchino_output_json = output
    return True


def _matrix_on_row(row: CecchinoTodayFixture) -> dict[str, Any] | None:
    output = row.cecchino_output_json or {}
    if not isinstance(output, dict):
        return None
    matrix = output.get("signals_matrix")
    return matrix if isinstance(matrix, dict) else None


def _ensure_current_signals_matrix_on_row(row: CecchinoTodayFixture) -> bool:
    """Garantisce matrice V3: se già corrente la lascia; altrimenti rebuild da prematch."""
    matrix = _matrix_on_row(row)
    if is_current_signal_matrix(matrix):
        return True
    return _rebuild_signals_matrix_on_row(row)


def _ensure_signals_matrix_on_row(row: CecchinoTodayFixture, *, force_rebuild: bool = False) -> bool:
    if force_rebuild:
        return _rebuild_signals_matrix_on_row(row)
    # Flusso operativo: richiede matrice V3 (non basta available legacy/V2)
    return _ensure_current_signals_matrix_on_row(row)


def _fixture_has_current_formula_activations(
    db: Session,
    today_fixture_id: int,
    *,
    formula_version: str = CURRENT_SIGNAL_FORMULA_VERSION,
) -> bool:
    """True solo se esistono activation correnti della formula version richiesta (default V3)."""
    if formula_version in (CURRENT_SIGNAL_FORMULA_VERSION, "current", "v3"):
        fv = CURRENT_SIGNAL_FORMULA_VERSION
    elif formula_version in (PREVIOUS_SIGNAL_FORMULA_VERSION, "v2"):
        fv = PREVIOUS_SIGNAL_FORMULA_VERSION
    else:
        fv = normalize_formula_version(formula_version)
    count = db.scalar(
        select(func.count())
        .select_from(CecchinoSignalActivation)
        .where(
            CecchinoSignalActivation.today_fixture_id == int(today_fixture_id),
            CecchinoSignalActivation.is_current.is_(True),
            CecchinoSignalActivation.signal_formula_version == fv,
        ),
    )
    return int(count or 0) > 0


def _fixture_has_current_activations(db: Session, today_fixture_id: int) -> bool:
    """Compat: verifica presence V3 corrente (V1/V2 non bastano)."""
    return _fixture_has_current_formula_activations(db, today_fixture_id)


def _count_legacy_activations_preserved(
    db: Session,
    date_from: date,
    date_to: date,
) -> int:
    count = db.scalar(
        select(func.count())
        .select_from(CecchinoSignalActivation)
        .where(
            CecchinoSignalActivation.scan_date >= date_from,
            CecchinoSignalActivation.scan_date <= date_to,
            or_(
                CecchinoSignalActivation.signal_formula_version.is_(None),
                CecchinoSignalActivation.signal_formula_version == LEGACY_SIGNAL_FORMULA_VERSION,
                CecchinoSignalActivation.signal_formula_version == "legacy",
                CecchinoSignalActivation.signal_formula_version == "v1",
            ),
        ),
    )
    return int(count or 0)


def _count_unique_acquired_signs(
    db: Session,
    date_from: date,
    date_to: date,
    *,
    formula_version: str = CURRENT_SIGNAL_FORMULA_VERSION,
) -> int:
    fv = normalize_formula_version(formula_version)
    rows = list(
        db.scalars(
            select(CecchinoSignalActivation).where(
                CecchinoSignalActivation.scan_date >= date_from,
                CecchinoSignalActivation.scan_date <= date_to,
                CecchinoSignalActivation.is_current.is_(True),
                CecchinoSignalActivation.signal_formula_version == fv,
                CecchinoSignalActivation.is_acquired.is_(True),
                CecchinoSignalActivation.signal_value.is_(True),
            ),
        ).all(),
    )
    keys = {
        (
            int(r.today_fixture_id),
            str(r.model_key or ""),
            str(r.signal_group or ""),
            str(r.target_market_key or ""),
        )
        for r in rows
        if getattr(r, "today_fixture_id", None) is not None
        and getattr(r, "signal_group", None) is not None
    }
    return len(keys)


def _unique_acquired_keys_from_matrix(matrix: dict[str, Any], fixture_id: int) -> set[tuple]:
    keys: set[tuple] = set()
    for group, consensus in consensus_by_group_from_matrix(matrix).items():
        if consensus.get("is_acquired"):
            keys.add((int(fixture_id), str(group)))
    return keys


def _merge_consensus_sync_counters(base: dict[str, int], other: dict[str, Any]) -> None:
    merge_sync_value_counters(base, other)
    for key in _CONSENSUS_SYNC_COUNTER_KEYS:
        base[key] = int(base.get(key, 0)) + int(other.get(key, 0) or 0)


def _activation_status_counts(
    db: Session,
    date_from: date,
    date_to: date,
    *,
    only_current: bool = True,
    formula_version: str | None = None,
) -> dict[str, int]:
    query = select(CecchinoSignalActivation.evaluation_status, func.count()).where(
        CecchinoSignalActivation.scan_date >= date_from,
        CecchinoSignalActivation.scan_date <= date_to,
        CecchinoSignalActivation.signal_value.is_(True),
    )
    if only_current:
        query = query.where(CecchinoSignalActivation.is_current.is_(True))
    if formula_version is not None:
        query = query.where(
            CecchinoSignalActivation.signal_formula_version
            == normalize_formula_version(formula_version),
        )
    query = query.group_by(CecchinoSignalActivation.evaluation_status)
    rows = db.execute(query).all()
    counts = {
        EVAL_WON: 0,
        EVAL_LOST: 0,
        EVAL_PENDING: 0,
        EVAL_NOT_EVALUABLE: 0,
        EVAL_RESULT_MISSING: 0,
    }
    for status, cnt in rows:
        if status in counts:
            counts[status] = int(cnt)
        elif status in (EVAL_PENDING, EVAL_RESULT_MISSING):
            counts[EVAL_PENDING] += int(cnt)
    evaluated = counts[EVAL_WON] + counts[EVAL_LOST]
    pending = counts[EVAL_PENDING] + counts.get(EVAL_RESULT_MISSING, 0)
    return {
        "won": counts[EVAL_WON],
        "lost": counts[EVAL_LOST],
        "pending": pending,
        "not_evaluable": counts[EVAL_NOT_EVALUABLE],
        "evaluated_count": evaluated,
    }


def build_signal_diagnostics(
    db: Session,
    *,
    date_from: date,
    date_to: date,
) -> dict[str, Any]:
    fixtures = _fixtures_in_range(db, date_from, date_to)
    eligible = [r for r in fixtures if r.eligibility_status == ELIGIBILITY_ELIGIBLE]
    with_matrix = [r for r in fixtures if _has_available_matrix(r)]
    warnings: list[str] = []

    for row in eligible:
        output = row.cecchino_output_json
        if isinstance(output, dict) and output and not _has_available_matrix(row):
            if _ensure_signals_matrix_on_row(row):
                with_matrix.append(row)
            else:
                warnings.append(
                    f"fixture_{row.id}:output_without_signals_matrix",
                )

    activations_total = db.scalar(
        select(func.count())
        .select_from(CecchinoSignalActivation)
        .where(
            CecchinoSignalActivation.scan_date >= date_from,
            CecchinoSignalActivation.scan_date <= date_to,
            CecchinoSignalActivation.signal_value.is_(True),
        ),
    ) or 0
    current_total = db.scalar(
        select(func.count())
        .select_from(CecchinoSignalActivation)
        .where(
            CecchinoSignalActivation.scan_date >= date_from,
            CecchinoSignalActivation.scan_date <= date_to,
            CecchinoSignalActivation.signal_value.is_(True),
            CecchinoSignalActivation.is_current.is_(True),
        ),
    ) or 0
    status_counts = _activation_status_counts(db, date_from, date_to, only_current=True)
    legacy_wrong_scala_mapping_count = int(
        db.scalar(
            select(func.count())
            .select_from(CecchinoSignalActivation)
            .where(
                CecchinoSignalActivation.scan_date >= date_from,
                CecchinoSignalActivation.scan_date <= date_to,
                CecchinoSignalActivation.is_current.is_(True),
                CecchinoSignalActivation.source_column == "SCALA",
                or_(
                    CecchinoSignalActivation.signal_group == "HOME",
                    CecchinoSignalActivation.signal_group == "AWAY",
                ),
            ),
        )
        or 0,
    )
    if legacy_wrong_scala_mapping_count > 0:
        warnings.append(
            "Esistono activation legacy errate in SCALA su 1/2. Eseguire Ricalcola mapping segnali.",
        )

    payload = {
        "date_from": date_from.isoformat(),
        "date_to": date_to.isoformat(),
        "today_fixtures_count": len(fixtures),
        "eligible_fixtures_count": len(eligible),
        "fixtures_with_signal_matrix_count": len(with_matrix),
        "signal_activations_count": int(activations_total),
        "current_signal_activations_count": int(current_total),
        "value_eligible_activations_count": int(current_total),
        "legacy_wrong_scala_mapping_count": legacy_wrong_scala_mapping_count,
        "evaluated_count": status_counts["evaluated_count"],
        "won": status_counts["won"],
        "lost": status_counts["lost"],
        "pending": status_counts["pending"],
        "not_evaluable": status_counts["not_evaluable"],
        "date_filter_field_used": DATE_FILTER_FIELD,
        "monitoring_note": (
            "Il monitoraggio include solo segnali comprabili: quota book >= quota Cecchino "
            "e quota book >= soglia minima del segno."
        ),
        "min_book_odds_thresholds": list_min_book_odds_for_api(db=db),
        "warnings": warnings[:50],
    }
    logger.info(
        "cecchino_signal_diagnostics date_from=%s date_to=%s fixtures=%s activations=%s",
        date_from.isoformat(),
        date_to.isoformat(),
        len(fixtures),
        int(activations_total),
    )
    return payload


def backfill_signal_activations(
    db: Session,
    *,
    date_from: date,
    date_to: date,
    only_missing: bool = True,
    evaluate_after: bool = True,
    force_remap: bool = False,
    min_book_odds: dict | None = None,
    persist_recomputed_matrix: bool = False,
    formula_version: str = CURRENT_SIGNAL_FORMULA_VERSION,
) -> dict[str, Any]:
    """Backfill activation V3 da snapshot pre-match; non sovrascrive JSON salvo opzione esplicita."""
    from decimal import Decimal

    from app.services.cecchino.cecchino_signal_min_book_odd_settings_service import (
        load_signal_min_book_odds,
    )

    if min_book_odds is None:
        min_book_odds = load_signal_min_book_odds(db)
    elif not isinstance(next(iter(min_book_odds.values()), None), Decimal):
        min_book_odds = {k: Decimal(str(v)) for k, v in min_book_odds.items()}

    # Backfill operativo (se invocato) scrive soltanto V3 — non rinomina matrici legacy.
    target_formula_version = CURRENT_SIGNAL_FORMULA_VERSION
    _ = formula_version  # parametro accettato per compat; target fisso CURRENT
    fixtures = _fixtures_in_range(db, date_from, date_to)
    warnings: list[str] = []
    totals = {
        "fixtures_found": len(fixtures),
        "fixtures_with_signals": 0,
        "fixtures_skipped": 0,
        "signals_created": 0,
        "signals_updated": 0,
        "signals_deactivated": 0,
        "si_cells_seen": 0,
        "value_passed": 0,
        "no_value_skipped": 0,
        "missing_book_quote_skipped": 0,
        "missing_cecchino_quote_skipped": 0,
        "invalid_quote_skipped": 0,
        "deactivated_no_value": 0,
        "min_book_odd_skipped": 0,
        "deactivated_min_book_odd": 0,
        "min_book_odd_threshold_applied": 0,
        "missing_value_quote": 0,
        "evaluated": 0,
        "won": 0,
        "lost": 0,
        "pending": 0,
        "not_evaluable": 0,
        "groups_consensus_passed": 0,
        "groups_consensus_rejected": 0,
        "single_formula_exempt_acquired": 0,
        "raw_si_cells": 0,
        "acquired_formula_cells": 0,
        "draw_pt_blocked_by_consensus": 0,
        "unique_acquired_signs": 0,
        "legacy_rows_preserved": 0,
    }
    processed_fixture_ids: list[int] = []
    matrix_by_fixture: dict[int, dict[str, Any]] = {}
    unique_acquired_keys: set[tuple] = set()
    effective_only_missing = only_missing and not force_remap

    for row in fixtures:
        if row.eligibility_status != ELIGIBILITY_ELIGIBLE:
            continue
        # only_missing: legacy non è sufficiente — serve V2 della formula richiesta
        if effective_only_missing and _fixture_has_current_formula_activations(
            db,
            int(row.id),
            formula_version=target_formula_version,
        ):
            totals["fixtures_skipped"] += 1
            continue

        matrix = _build_v2_signals_matrix_from_prematch(row)
        if matrix is None:
            warnings.append(f"fixture_{row.id}:no_signals_matrix")
            continue

        if persist_recomputed_matrix:
            output = row.cecchino_output_json
            if isinstance(output, dict):
                output = dict(output)
                output["signals_matrix"] = matrix
                row.cecchino_output_json = output
        else:
            totals["legacy_rows_preserved"] += 1

        totals["fixtures_with_signals"] += 1
        fid = int(row.id)
        processed_fixture_ids.append(fid)
        matrix_by_fixture[fid] = matrix
        unique_acquired_keys |= _unique_acquired_keys_from_matrix(matrix, fid)

        if not force_remap:
            sync_counts = sync_cecchino_signal_activations(
                db,
                fid,
                signals_matrix=matrix,
                min_book_odds=min_book_odds,
                formula_source_mode=FORMULA_SOURCE_RECOMPUTED_PREMATCH,
                formula_version=target_formula_version,
            )
            totals["signals_created"] += sync_counts.get("created", 0)
            totals["signals_updated"] += sync_counts.get("updated", 0)
            totals["signals_deactivated"] += sync_counts.get("deactivated", 0)
            _merge_consensus_sync_counters(totals, sync_counts)

    legacy_scala_deactivated = 0
    if force_remap:
        legacy_scala_deactivated = remap_legacy_scala_activations_in_range(
            db,
            date_from=date_from,
            date_to=date_to,
        )
        for fid in processed_fixture_ids:
            matrix = matrix_by_fixture.get(fid)
            sync_counts = sync_cecchino_signal_activations(
                db,
                fid,
                signals_matrix=matrix,
                min_book_odds=min_book_odds,
                formula_source_mode=FORMULA_SOURCE_RECOMPUTED_PREMATCH,
                formula_version=target_formula_version,
            )
            totals["signals_created"] += sync_counts.get("created", 0)
            totals["signals_updated"] += sync_counts.get("updated", 0)
            totals["signals_deactivated"] += sync_counts.get("deactivated", 0)
            _merge_consensus_sync_counters(totals, sync_counts)

    remapped = remap_under_over_activations_in_range(db, date_from=date_from, date_to=date_to)

    from app.services.cecchino.cecchino_signal_odds_refresh import refresh_activation_odds_from_kpi

    odds_refresh = refresh_activation_odds_from_kpi(
        db,
        date_from=date_from,
        date_to=date_to,
        only_null=True,
        only_current=True,
    )

    # Settlement dopo formula/consenso
    if evaluate_after:
        for fid in processed_fixture_ids:
            eval_counts = evaluate_activations_for_fixture(db, fid)
            totals["evaluated"] += eval_counts.get("evaluated", 0)
            totals["pending"] += eval_counts.get("pending", 0)
            totals["not_evaluable"] += eval_counts.get("not_evaluable", 0)

    if evaluate_after and processed_fixture_ids:
        status_counts = _activation_status_counts(
            db,
            date_from,
            date_to,
            only_current=True,
            formula_version=target_formula_version,
        )
        totals["won"] = status_counts["won"]
        totals["lost"] = status_counts["lost"]
        totals["pending"] = status_counts["pending"]
        totals["not_evaluable"] = status_counts["not_evaluable"]
        totals["evaluated"] = status_counts["evaluated_count"]

    totals["missing_value_quote"] = (
        totals["missing_book_quote_skipped"] + totals["missing_cecchino_quote_skipped"]
    )
    totals["unique_acquired_signs"] = (
        _count_unique_acquired_signs(
            db,
            date_from,
            date_to,
            formula_version=target_formula_version,
        )
        if processed_fixture_ids
        else len(unique_acquired_keys)
    )
    # Activation legacy rimaste intatte (V1 non eliminata)
    if not persist_recomputed_matrix:
        # già incrementato per fixture processate; aggiungi conteggio activation legacy residue
        totals["legacy_activation_rows_preserved"] = _count_legacy_activations_preserved(
            db, date_from, date_to,
        )
    else:
        totals["legacy_activation_rows_preserved"] = _count_legacy_activations_preserved(
            db, date_from, date_to,
        )

    db.commit()
    logger.info(
        "cecchino_signal_backfill date_from=%s date_to=%s created=%s fixtures_with_signals=%s fv=%s",
        date_from.isoformat(),
        date_to.isoformat(),
        totals["signals_created"],
        totals["fixtures_with_signals"],
        target_formula_version,
    )
    return {
        "status": "ok",
        "formula_version": target_formula_version,
        "consensus_policy_version": SIGNAL_CONSENSUS_POLICY_VERSION,
        "formula_source_mode": FORMULA_SOURCE_RECOMPUTED_PREMATCH,
        "persist_recomputed_matrix": persist_recomputed_matrix,
        **totals,
        "remapped": remapped,
        "legacy_scala_deactivated": legacy_scala_deactivated,
        "force_remap": force_remap,
        "odds_refresh_summary": odds_refresh,
        "warnings": warnings[:100],
    }


def sync_signals_for_scan_date(db: Session, scan_date: date) -> dict[str, int]:
    from app.services.cecchino.cecchino_signal_min_book_odd_settings_service import (
        load_signal_min_book_odds,
    )

    min_book_odds = load_signal_min_book_odds(db)
    fixtures = list(
        db.scalars(
            select(CecchinoTodayFixture).where(
                CecchinoTodayFixture.scan_date == scan_date,
                CecchinoTodayFixture.eligibility_status == ELIGIBILITY_ELIGIBLE,
            ),
        ).all(),
    )
    totals: dict[str, int] = {
        "fixtures": 0,
        "created": 0,
        "updated": 0,
        "deactivated": 0,
        "skipped": 0,
        "skipped_non_current_formula_matrix": 0,
        "si_cells_seen": 0,
        "value_passed": 0,
        "no_value_skipped": 0,
        "missing_book_quote_skipped": 0,
        "missing_cecchino_quote_skipped": 0,
        "invalid_quote_skipped": 0,
        "deactivated_no_value": 0,
    }
    for row in fixtures:
        # V3 già presente → sync; altrimenti prova rebuild da prematch (non copia SI/NO legacy)
        if not _ensure_current_signals_matrix_on_row(row):
            totals["skipped"] += 1
            totals["skipped_non_current_formula_matrix"] += 1
            continue
        totals["fixtures"] += 1
        counts = sync_cecchino_signal_activations(db, int(row.id), min_book_odds=min_book_odds)
        totals["created"] += counts.get("created", 0)
        totals["updated"] += counts.get("updated", 0)
        totals["deactivated"] += counts.get("deactivated", 0)
        totals["skipped_non_current_formula_matrix"] += counts.get(
            "skipped_non_current_formula_matrix",
            0,
        )
        if counts.get("skipped_non_current_formula_matrix"):
            totals["skipped"] += counts.get("skipped", 0)
        merge_sync_value_counters(totals, counts)
    totals["missing_value_quote"] = (
        totals["missing_book_quote_skipped"] + totals["missing_cecchino_quote_skipped"]
    )
    db.flush()
    return totals
