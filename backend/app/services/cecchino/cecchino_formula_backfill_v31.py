"""Backfill mirato formule Cecchino V3.1 Fase 1B — merge-only, dry-run default.

Modalità: formula_backfill_v31_phase1b
Nessuna chiamata bookmaker/provider. Solo DB + storico as-of kickoff.
Non modifica Acquistabilità V3, selected signs, né quote Cecchino FT 1X2.
"""

from __future__ import annotations

import logging
from collections import Counter
from copy import deepcopy
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.models import Fixture
from app.models.cecchino_today_fixture import CecchinoTodayFixture
from app.services.cecchino.cecchino_betfair_odds_payload import build_betfair_payload_from_snapshot
from app.services.cecchino.cecchino_bookmaker_odds_service import load_betfair_odds_payload
from app.services.cecchino.cecchino_fixture_history import build_goal_market_contexts
from app.services.cecchino.cecchino_goal_formulas import build_goal_market_cecchino_odds
from app.services.cecchino.cecchino_kpi_panel_v2_betfair import build_cecchino_kpi_panel_v2_betfair
from app.services.cecchino.cecchino_selection_keys import (
    SEL_AWAY_PT,
    SEL_DRAW_PT,
    SEL_HOME_PT,
    SEL_OVER_1_5,
    SEL_OVER_3_5,
    SEL_OVER_PT_0_5,
    SEL_UNDER_1_5,
    SEL_UNDER_3_5,
    SEL_UNDER_PT_0_5,
)
from app.services.cecchino.cecchino_today_odds_meta import read_odds_meta

logger = logging.getLogger(__name__)

BACKFILL_MODE = "formula_backfill_v31_phase1b"
CONFIRM_TOKEN = "WRITE_FORMULA_BACKFILL_V31_P1B"
MAX_RANGE_DAYS_WITHOUT_LIMIT = 14
DEFAULT_BATCH_SIZE = 50

# Mercati introdotti/consolidati in Fase 1 / 1B da popolare negli snapshot vecchi
PHASE1B_TARGET_MARKETS: tuple[str, ...] = (
    SEL_HOME_PT,
    SEL_DRAW_PT,
    SEL_AWAY_PT,
    SEL_UNDER_1_5,
    SEL_OVER_1_5,
    SEL_OVER_3_5,
    SEL_UNDER_3_5,
    SEL_UNDER_PT_0_5,
    SEL_OVER_PT_0_5,
)

_HT_FAMILY = frozenset({SEL_HOME_PT, SEL_DRAW_PT, SEL_AWAY_PT})


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _has_usable_odd(block: Any) -> bool:
    if not isinstance(block, dict):
        return False
    odd = block.get("final_odd")
    if odd is None:
        return False
    try:
        return float(odd) > 0
    except (TypeError, ValueError):
        return False


def _load_betfair_payload_offline(db: Session, row: CecchinoTodayFixture) -> dict[str, Any]:
    """Solo snapshot/cache già salvati — nessuna chiamata esterna."""
    if isinstance(row.odds_snapshot_json, dict) and row.odds_snapshot_json:
        payload = build_betfair_payload_from_snapshot(row.odds_snapshot_json)
        if isinstance(payload, dict) and payload:
            return payload
    try:
        payload = load_betfair_odds_payload(db, int(row.id), use_existing=True)
    except Exception:
        logger.exception("backfill betfair payload load failed fixture=%s", row.id)
        return {}
    return payload if isinstance(payload, dict) else {}


def _version_trace(previous: dict[str, Any], *, reason: str) -> dict[str, Any]:
    return {
        "replaced_at": _utcnow_iso(),
        "reason": reason,
        "previous_formula_version": previous.get("formula_version"),
        "previous_final_odd": previous.get("final_odd"),
        "previous_status": previous.get("status"),
        "previous_summary": previous.get("summary"),
    }


def merge_goal_markets_phase1b(
    existing: dict[str, Any] | None,
    computed: dict[str, Any],
    *,
    force: bool = False,
    target_markets: tuple[str, ...] = PHASE1B_TARGET_MARKETS,
) -> dict[str, Any]:
    """Merge mirato: aggiunge mercati mancanti; overwrite solo con force."""
    merged: dict[str, Any] = dict(existing) if isinstance(existing, dict) else {}
    report = {
        "markets_added": [],
        "markets_skipped_present": [],
        "markets_forced": [],
        "markets_not_computable": [],
        "markets_missing_in_computed": [],
    }

    # Famiglia HT: se force o almeno un membro manca, aggiorna i tre insieme
    family_needs = any(
        mk in target_markets and (force or not _has_usable_odd(merged.get(mk)))
        for mk in _HT_FAMILY
    )
    if family_needs and any(mk in target_markets for mk in _HT_FAMILY):
        for mk in _HT_FAMILY:
            if mk not in target_markets:
                continue
            new_block = computed.get(mk)
            if not isinstance(new_block, dict):
                report["markets_missing_in_computed"].append(mk)
                continue
            if not _has_usable_odd(new_block):
                report["markets_not_computable"].append(mk)
                if mk not in merged:
                    merged[mk] = deepcopy(new_block)
                continue
            old = merged.get(mk)
            if _has_usable_odd(old) and not force:
                report["markets_skipped_present"].append(mk)
                continue
            block = deepcopy(new_block)
            if isinstance(old, dict) and force and _has_usable_odd(old):
                block["previous_version_trace"] = _version_trace(old, reason="force_family_replace")
                report["markets_forced"].append(mk)
            else:
                report["markets_added"].append(mk)
            merged[mk] = block

    for mk in target_markets:
        if mk in _HT_FAMILY:
            continue
        new_block = computed.get(mk)
        if not isinstance(new_block, dict):
            report["markets_missing_in_computed"].append(mk)
            continue
        if not _has_usable_odd(new_block):
            report["markets_not_computable"].append(mk)
            if mk not in merged:
                merged[mk] = deepcopy(new_block)
            continue
        old = merged.get(mk)
        if _has_usable_odd(old) and not force:
            report["markets_skipped_present"].append(mk)
            continue
        block = deepcopy(new_block)
        if isinstance(old, dict) and force and _has_usable_odd(old):
            block["previous_version_trace"] = _version_trace(old, reason="force_replace")
            report["markets_forced"].append(mk)
        else:
            report["markets_added"].append(mk)
        merged[mk] = block

    return {"goal_markets": merged, "merge_report": report}


def backfill_fixture_formulas_phase1b(
    db: Session,
    row: CecchinoTodayFixture,
    *,
    dry_run: bool = True,
    force: bool = False,
) -> dict[str, Any]:
    """Backfill goal_markets + rebuild KPI per una riga Today."""
    result: dict[str, Any] = {
        "fixture_id": int(row.id),
        "mode": BACKFILL_MODE,
        "dry_run": dry_run,
        "force": force,
        "updated": False,
        "updatable": False,
        "skip_reason": None,
        "markets_added": [],
        "markets_skipped_present": [],
        "markets_not_computable": [],
        "markets_forced": [],
        "formula_versions": {},
        "error": None,
    }

    if row.kickoff is None:
        result["skip_reason"] = "kickoff_missing"
        return result
    if row.local_fixture_id is None:
        result["skip_reason"] = "local_fixture_missing"
        return result
    if not isinstance(row.cecchino_output_json, dict):
        result["skip_reason"] = "cecchino_output_missing"
        return result

    local_fx = db.get(Fixture, int(row.local_fixture_id))
    if local_fx is None:
        result["skip_reason"] = "local_fixture_not_found"
        return result

    # Guard look-ahead: i contesti usano già load_*_before(kickoff) nel motore history
    try:
        goal_ctx = build_goal_market_contexts(db, local_fx)
        computed = build_goal_market_cecchino_odds(db, local_fx, goal_ctx)
    except Exception as exc:
        logger.exception("formula backfill compute failed fixture=%s", row.id)
        result["error"] = f"compute_error:{exc!s}"[:300]
        return result

    if not isinstance(computed, dict):
        result["error"] = "compute_returned_non_dict"
        return result

    existing_output = dict(row.cecchino_output_json)
    existing_gm = existing_output.get("goal_markets")
    merge_out = merge_goal_markets_phase1b(
        existing_gm if isinstance(existing_gm, dict) else {},
        computed,
        force=force,
    )
    merge_report = merge_out["merge_report"]
    for key in (
        "markets_added",
        "markets_skipped_present",
        "markets_not_computable",
        "markets_forced",
    ):
        result[key] = list(merge_report.get(key) or [])

    version_dist: dict[str, int] = {}
    for mk, block in (merge_out["goal_markets"] or {}).items():
        if isinstance(block, dict) and block.get("formula_version"):
            fv = str(block["formula_version"])
            version_dist[fv] = version_dist.get(fv, 0) + 1
    result["formula_versions"] = version_dist

    changed_keys = result["markets_added"] + result["markets_forced"]
    if not changed_keys:
        result["skip_reason"] = "nothing_to_update"
        return result

    result["updatable"] = True
    if dry_run:
        result["would_update"] = True
        return result

    # Persist: merge goal_markets; preserva V3 / V3.1 / final / selected
    new_output = dict(existing_output)
    prev_v3 = existing_output.get("purchasability_preview_v3")
    prev_v31 = existing_output.get("purchasability_preview_v31")
    new_output["goal_markets"] = merge_out["goal_markets"]
    new_output["formula_backfill_v31_phase1b"] = {
        "mode": BACKFILL_MODE,
        "timestamp": _utcnow_iso(),
        "dry_run": False,
        "force": force,
        "markets_added": result["markets_added"],
        "markets_skipped": result["markets_skipped_present"],
        "markets_not_computable": result["markets_not_computable"],
        "markets_forced": result["markets_forced"],
        "formula_versions": version_dist,
    }
    if prev_v3 is not None:
        new_output["purchasability_preview_v3"] = prev_v3
    if prev_v31 is not None:
        new_output["purchasability_preview_v31"] = prev_v31

    betfair_payload = _load_betfair_payload_offline(db, row)
    kpi_panel = build_cecchino_kpi_panel_v2_betfair(
        final_odds=(new_output.get("final") or {}) if isinstance(new_output.get("final"), dict) else {},
        betfair_payload=betfair_payload,
        goal_markets=new_output.get("goal_markets"),
    )
    meta = read_odds_meta(row.odds_snapshot_json)
    if meta:
        kpi_panel["odds_meta"] = meta

    # Non ricalcolare V3: lascia preview già presenti sul output
    row.cecchino_output_json = new_output
    row.kpi_panel_json = kpi_panel
    flag_modified(row, "cecchino_output_json")
    flag_modified(row, "kpi_panel_json")
    result["updated"] = True
    return result


def run_formula_backfill_v31_phase1b(
    db: Session,
    *,
    date_from: date | None = None,
    date_to: date | None = None,
    fixture_id: int | None = None,
    dry_run: bool = True,
    force: bool = False,
    limit: int | None = None,
    batch_size: int = DEFAULT_BATCH_SIZE,
) -> dict[str, Any]:
    """Esegue backfill su range date o singola fixture."""
    if fixture_id is None:
        if date_from is None or date_to is None:
            raise ValueError("Servono date_from/date_to oppure fixture_id")
        if date_to < date_from:
            raise ValueError("date_to < date_from")
        span = (date_to - date_from).days + 1
        if span > MAX_RANGE_DAYS_WITHOUT_LIMIT and (limit is None or limit <= 0):
            raise ValueError(
                f"Range di {span} giorni richiede --limit "
                f"(max senza limit: {MAX_RANGE_DAYS_WITHOUT_LIMIT} giorni)",
            )

    report: dict[str, Any] = {
        "mode": BACKFILL_MODE,
        "dry_run": dry_run,
        "force": force,
        "date_from": date_from.isoformat() if date_from else None,
        "date_to": date_to.isoformat() if date_to else None,
        "fixture_id": fixture_id,
        "limit": limit,
        "fixtures_analyzed": 0,
        "fixtures_updatable": 0,
        "fixtures_updated": 0,
        "fixtures_skipped": 0,
        "markets_calculated": 0,
        "markets_already_present": 0,
        "markets_not_computable": 0,
        "errors": [],
        "skip_reasons": Counter(),
        "formula_version_distribution": Counter(),
        "fixture_results": [],
    }

    stmt = select(CecchinoTodayFixture).where(
        CecchinoTodayFixture.cecchino_output_json.is_not(None),
    )
    if fixture_id is not None:
        stmt = stmt.where(CecchinoTodayFixture.id == int(fixture_id))
    else:
        stmt = stmt.where(
            CecchinoTodayFixture.scan_date >= date_from,
            CecchinoTodayFixture.scan_date <= date_to,
        )
    stmt = stmt.order_by(CecchinoTodayFixture.scan_date, CecchinoTodayFixture.id)
    if limit is not None and limit > 0:
        stmt = stmt.limit(int(limit))

    pending = 0
    for row in db.scalars(stmt).all():
        report["fixtures_analyzed"] += 1
        try:
            fx_result = backfill_fixture_formulas_phase1b(
                db, row, dry_run=dry_run, force=force,
            )
        except Exception as exc:
            logger.exception("formula backfill fixture failed id=%s", row.id)
            report["errors"].append({"fixture_id": int(row.id), "error": str(exc)[:300]})
            continue

        report["fixture_results"].append(fx_result)
        if fx_result.get("error"):
            report["errors"].append(
                {"fixture_id": fx_result["fixture_id"], "error": fx_result["error"]},
            )
            continue

        reason = fx_result.get("skip_reason")
        if reason:
            report["fixtures_skipped"] += 1
            report["skip_reasons"][reason] += 1

        report["markets_calculated"] += len(fx_result.get("markets_added") or [])
        report["markets_calculated"] += len(fx_result.get("markets_forced") or [])
        report["markets_already_present"] += len(fx_result.get("markets_skipped_present") or [])
        report["markets_not_computable"] += len(fx_result.get("markets_not_computable") or [])

        for fv, n in (fx_result.get("formula_versions") or {}).items():
            report["formula_version_distribution"][fv] += int(n)

        if fx_result.get("updatable"):
            report["fixtures_updatable"] += 1
        if fx_result.get("updated"):
            report["fixtures_updated"] += 1
            pending += 1
            if pending >= batch_size:
                db.commit()
                pending = 0

    if not dry_run and pending:
        db.commit()

    report["skip_reasons"] = dict(report["skip_reasons"])
    report["formula_version_distribution"] = dict(report["formula_version_distribution"])
    # Non serializzare tutti i dettagli fixture in output CLI di default se troppi
    if len(report["fixture_results"]) > 100:
        report["fixture_results_truncated"] = True
        report["fixture_results"] = report["fixture_results"][:100]
    return report
