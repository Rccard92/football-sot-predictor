"""Acquistabilita RUN V2: V36 invariata + scoring V2-only per O/U 0.5.

Non modifica `PANEL_MARKET_KEYS` / engine V35 V2 condivisi. Estende solo il
payload markets della RUN V2 cosi OVER_0_5 / UNDER_0_5 entrano in freeze e
decision path.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from app.services.cecchino.cecchino_market_opposition import PANEL_MARKET_KEYS
from app.services.cecchino.cecchino_purchasability_fair_book import (
    SOURCE_TWO_WAY,
    normalize_exclusive_market,
    resolve_fair_book_for_panel_rows,
)
from app.services.cecchino.cecchino_purchasability_features import (
    build_model_context_probability_map,
)
from app.services.cecchino.cecchino_purchasability_v35_v2_engine import (
    calculate_purchasability_v35_v2_item,
)
from app.services.cecchino.cecchino_purchasability_v35_v2_features import (
    build_market_input_context_v2,
)
from app.services.cecchino.cecchino_selection_keys import SEL_OVER_0_5, SEL_UNDER_0_5
from app.services.cecchino_data_lab.historical_purchasability_v36_adapter import (
    DEFAULT_SNAPSHOT_LEAD,
    build_historical_purchasability_v36,
    historical_v36_snapshot_provenance,
    synthetic_pre_match_snapshot_at,
)
from app.services.cecchino_data_lab.run_v2.kpi_ou05_ext import OU05_KPI_KEYS

# Allowlist V2-only: panel V1 + O/U 0.5. Non esportata nei moduli V1.
RUN_V2_PURCHASABILITY_MARKET_KEYS: tuple[str, ...] = tuple(PANEL_MARKET_KEYS) + OU05_KPI_KEYS


def _index_rows(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    by_mk: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        mk = str(row.get("market_key") or row.get("segno") or "").strip()
        if mk:
            by_mk[mk] = row
    return by_mk


def _quota_book(row: dict[str, Any] | None) -> float | None:
    if not isinstance(row, dict):
        return None
    raw = row.get("quota_book")
    if raw is None:
        return None
    try:
        f = float(raw)
    except (TypeError, ValueError):
        return None
    return f if f == f and f > 1.0 else None


def _resolve_ou05_fair_book(
    by_mk: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Fair book V2-only per O/U 0.5 (two-way), senza toccare il resolver V1."""
    required = frozenset({SEL_OVER_0_5, SEL_UNDER_0_5})
    odds: dict[str, float] = {}
    for mk in required:
        q = _quota_book(by_mk.get(mk))
        if q is not None:
            odds[mk] = q
    normalized, overround, status = normalize_exclusive_market(odds, required)
    out: dict[str, dict[str, Any]] = {}
    if status != "ok" or not normalized:
        for mk in required:
            row = by_mk.get(mk) or {}
            q = _quota_book(row)
            raw = (1.0 / q) if q else None
            out[mk] = {
                "fair_book_probability": raw,
                "fair_book_probability_source": "raw_implied_secondary_only",
                "fair_book_probability_verified": False,
                "normalization_payload": {
                    "status": "fallback_raw_implied",
                    "exclusion_reason": status if status != "ok" else "incomplete_market",
                },
                "exclusion_reason": status if status != "ok" else "incomplete_market",
            }
        return out

    payload = {
        "status": status,
        "overround": overround,
        "period": "FT",
        "line": 0.5,
        "normalized_map": {k: round(v, 8) for k, v in normalized.items()},
        "required": sorted(required),
        "run_v2_ou05_fair_book": True,
    }
    for mk in required:
        out[mk] = {
            "fair_book_probability": float(normalized[mk]),
            "fair_book_probability_source": SOURCE_TWO_WAY,
            "fair_book_probability_verified": True,
            "normalization_payload": payload,
            "exclusion_reason": None,
        }
    return out


def _probs_map_v2(
    by_mk: dict[str, dict[str, Any]],
    *,
    fair_by: dict[str, dict[str, Any]],
    model_probs: dict[str, float | None] | None,
    fixture_meta: dict[str, Any] | None,
) -> dict[str, dict[str, float | None]]:
    out: dict[str, dict[str, float | None]] = {}
    for mk in RUN_V2_PURCHASABILITY_MARKET_KEYS:
        ctx = build_market_input_context_v2(
            row=by_mk.get(mk) or {},
            fair_info=fair_by.get(mk),
            model_probs=model_probs,
            market_key=mk,
            fixture_meta=fixture_meta,
        )
        out[mk] = {
            "probability_cecchino": ctx["probability_cecchino"],
            "fair_book_probability": ctx["fair_book_probability"],
        }
    return out


def _score_ou05_items(
    *,
    kpi_panel: dict[str, Any],
    fixture_meta: dict[str, Any],
) -> list[dict[str, Any]]:
    rows = [r for r in (kpi_panel.get("rows") or []) if isinstance(r, dict)]
    by_mk = _index_rows(rows)
    fair_by = resolve_fair_book_for_panel_rows(
        rows,
        today_fixture_id=fixture_meta.get("today_fixture_id"),
        snapshot_at=fixture_meta.get("snapshot_at"),
    )
    # Overlay V2-only: FT O/U 0.5 non e nel fair-book V1.
    fair_by = {**fair_by, **_resolve_ou05_fair_book(by_mk)}
    model_probs = build_model_context_probability_map(rows)
    probs_by_market = _probs_map_v2(
        by_mk,
        fair_by=fair_by,
        model_probs=model_probs,
        fixture_meta=fixture_meta,
    )

    items: list[dict[str, Any]] = []
    for mk in (SEL_OVER_0_5, SEL_UNDER_0_5):
        item = calculate_purchasability_v35_v2_item(
            mk,
            by_mk.get(mk) or {},
            by_mk,
            fair_by=fair_by,
            model_probs=model_probs,
            fixture_meta=fixture_meta,
            probs_by_market=probs_by_market,
        )
        items.append(item)
    return items


def build_run_v2_purchasability(
    *,
    kpi_panel: dict[str, Any] | None,
    match: Any,
    season_label: str | None = None,
    competition_name: str | None = None,
    snapshot_lead: timedelta | None = None,
) -> dict[str, Any]:
    """Purchasability V36 sui mercati panel + append O/U 0.5 con stesse formule."""
    base = build_historical_purchasability_v36(
        kpi_panel=kpi_panel,
        match=match,
        season_label=season_label,
        competition_name=competition_name,
        snapshot_lead=snapshot_lead,
    )
    if not isinstance(kpi_panel, dict) or not kpi_panel.get("rows"):
        return base

    kickoff = getattr(match, "kickoff_at", None)
    lead = snapshot_lead if snapshot_lead is not None else DEFAULT_SNAPSHOT_LEAD
    snapshot_at = (
        synthetic_pre_match_snapshot_at(kickoff, lead=lead) if kickoff is not None else None
    )
    provenance = {
        **historical_v36_snapshot_provenance(),
        "lead_hours": lead.total_seconds() / 3600.0,
        "run_v2_ou05_extension": True,
    }
    fixture_meta = {
        "today_fixture_id": int(getattr(match, "id", 0) or 0),
        "kickoff": kickoff.isoformat() if kickoff is not None else None,
        "snapshot_at": snapshot_at.isoformat() if snapshot_at is not None else None,
        "home_team": getattr(match, "home_team", None),
        "away_team": getattr(match, "away_team", None),
        "competition": competition_name,
        "season_label": season_label,
        "historical_lab_replay": True,
        **provenance,
    }

    ou05_items = _score_ou05_items(kpi_panel=kpi_panel, fixture_meta=fixture_meta)
    markets_out = list(base.get("markets") or [])
    existing = {str(m.get("market_key")) for m in markets_out if isinstance(m, dict)}
    for it in ou05_items:
        mk = it.get("market_key")
        if mk in existing:
            continue
        ref = it.get("reference") if isinstance(it.get("reference"), dict) else {}
        markets_out.append(
            {
                "market_key": mk,
                "score": ref.get("score"),
                "class": ref.get("class"),
                "status": it.get("status"),
                "gate_status": it.get("gate_status"),
                "v2_only_ou05": True,
            }
        )

    out = dict(base)
    out["markets"] = markets_out
    out["run_v2_purchasability_market_keys"] = list(RUN_V2_PURCHASABILITY_MARKET_KEYS)
    out["run_v2_ou05_extension"] = True
    return out
