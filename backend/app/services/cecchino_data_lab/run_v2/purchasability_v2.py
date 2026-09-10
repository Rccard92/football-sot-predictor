"""Acquistabilita RUN V2: V36 + estensioni V2-only (O/U 0.5, DC fair STRICT).

Non modifica `PANEL_MARKET_KEYS` / engine V35 V2 / fair-book V1 condivisi.
Estende solo il payload markets della RUN V2.
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
from app.services.cecchino.cecchino_selection_keys import (
    SEL_AWAY,
    SEL_DRAW,
    SEL_HOME,
    SEL_ONE_TWO,
    SEL_ONE_X,
    SEL_OVER_0_5,
    SEL_UNDER_0_5,
    SEL_X_TWO,
)
from app.services.cecchino_data_lab.historical_purchasability_v36_adapter import (
    DEFAULT_SNAPSHOT_LEAD,
    build_historical_purchasability_v36,
    historical_v36_snapshot_provenance,
    synthetic_pre_match_snapshot_at,
)
from app.services.cecchino_data_lab.run_v2.kpi_ou05_ext import OU05_KPI_KEYS

# Allowlist V2-only: panel V1 + O/U 0.5. Non esportata nei moduli V1.
RUN_V2_PURCHASABILITY_MARKET_KEYS: tuple[str, ...] = tuple(PANEL_MARKET_KEYS) + OU05_KPI_KEYS

# Fair DC V2: probabilità derivata da STRICT Bet365 1X2 (non è execution quote).
SOURCE_DC_FAIR_V2 = "run_v2_strict_bet365_1x2_derived_dc"
DC_V2_MARKET_KEYS: tuple[str, ...] = (SEL_ONE_X, SEL_ONE_TWO, SEL_X_TWO)
_STRICT_1X2_KEYS: tuple[str, ...] = (SEL_HOME, SEL_DRAW, SEL_AWAY)


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


def _strict_odds_value(entry: dict[str, Any] | None) -> float | None:
    """Quota STRICT valida per fair 1X2; rifiuta derived."""
    if not isinstance(entry, dict):
        return None
    if entry.get("is_derived"):
        return None
    raw = entry.get("value")
    if raw is None:
        return None
    try:
        f = float(raw)
    except (TypeError, ValueError):
        return None
    return f if f == f and f > 1.0 else None


def _dc_fair_unavailable(reason: str) -> dict[str, Any]:
    """Fair DC non disponibile: nessun fallback V1/cross-provider."""
    return {
        "fair_book_probability": None,
        "fair_book_probability_source": SOURCE_DC_FAIR_V2,
        "fair_book_probability_verified": False,
        "normalization_payload": {
            "status": "unavailable",
            "exclusion_reason": reason,
            "run_v2_dc_fair_book": True,
            "fair_input": "strict_bet365_1x2",
            "no_v1_fallback": True,
        },
        "exclusion_reason": reason,
    }


def _resolve_dc_fair_book_v2(
    strict_by_market: dict[str, dict[str, Any]] | None,
) -> dict[str, dict[str, Any]]:
    """Fair DC V2-only: ESCLUSIVAMENTE trio STRICT Bet365 HOME/DRAW/AWAY.

    - trio completo → verified (pH+pD / pH+pA / pD+pA)
    - trio incompleto → unavailable (None, verified=False)
    - nessun fallback V1 / cross-provider
    Non tocca execution quote / is_real_quote / derived_quote.
    """
    strict = strict_by_market or {}
    odds: dict[str, float] = {}
    for mk in _STRICT_1X2_KEYS:
        q = _strict_odds_value(strict.get(mk))
        if q is not None:
            odds[mk] = q

    required = frozenset(_STRICT_1X2_KEYS)
    out: dict[str, dict[str, Any]] = {}
    if not required.issubset(odds):
        for mk in DC_V2_MARKET_KEYS:
            out[mk] = _dc_fair_unavailable("incomplete_market")
        return out

    normalized, overround, status = normalize_exclusive_market(odds, required)
    if status != "ok" or not normalized:
        for mk in DC_V2_MARKET_KEYS:
            out[mk] = _dc_fair_unavailable(
                status if status != "ok" else "incomplete_market"
            )
        return out

    p_h = float(normalized[SEL_HOME])
    p_d = float(normalized[SEL_DRAW])
    p_a = float(normalized[SEL_AWAY])
    derived = {
        SEL_ONE_X: p_h + p_d,
        SEL_ONE_TWO: p_h + p_a,
        SEL_X_TWO: p_d + p_a,
    }
    payload = {
        "status": "ok",
        "overround_1x2": overround,
        "normalized_1x2": {k: round(v, 8) for k, v in normalized.items()},
        "derived_dc": {k: round(v, 8) for k, v in derived.items()},
        "run_v2_dc_fair_book": True,
        "fair_input": "strict_bet365_1x2",
        "note": (
            "DC fair probability derived from STRICT Bet365 1X2; "
            "execution quote remains DC REAL when available"
        ),
        "no_v1_fallback": True,
        "does_not_mutate_execution_quote": True,
    }
    for mk in DC_V2_MARKET_KEYS:
        out[mk] = {
            "fair_book_probability": float(derived[mk]),
            "fair_book_probability_source": SOURCE_DC_FAIR_V2,
            "fair_book_probability_verified": True,
            "normalization_payload": payload,
            "exclusion_reason": None,
        }
    return out


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


def _gate_reason_codes(item: dict[str, Any]) -> list[str]:
    gate = item.get("gate") if isinstance(item.get("gate"), dict) else {}
    codes = gate.get("gate_reason_codes")
    if isinstance(codes, list):
        return [str(c) for c in codes]
    raw = item.get("gate_reason_codes")
    if isinstance(raw, list):
        return [str(c) for c in raw]
    return []


def _compact_market_from_item(
    item: dict[str, Any],
    *,
    fair_info: dict[str, Any] | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    ref = item.get("reference") if isinstance(item.get("reference"), dict) else {}
    inp = item.get("input") if isinstance(item.get("input"), dict) else {}
    fair = fair_info if isinstance(fair_info, dict) else {}
    fair_prob = inp.get("fair_book_probability")
    if fair_prob is None:
        fair_prob = fair.get("fair_book_probability")
    fair_src = fair.get("fair_book_probability_source")
    out: dict[str, Any] = {
        "market_key": item.get("market_key"),
        "score": ref.get("score"),
        "class": ref.get("class"),
        "status": item.get("status"),
        "gate_status": item.get("gate_status"),
        "gate_reason_codes": _gate_reason_codes(item),
        "fair_book_probability": fair_prob,
        "fair_book_probability_source": fair_src,
        "formula_version": item.get("formula_version"),
    }
    if extra:
        out.update(extra)
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


def _score_dc_items(
    *,
    kpi_panel: dict[str, Any],
    fixture_meta: dict[str, Any],
    strict_by_market: dict[str, dict[str, Any]] | None,
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    """Rescore DC con fair STRICT-only. Non muta righe KPI / execution flags."""
    rows = [r for r in (kpi_panel.get("rows") or []) if isinstance(r, dict)]
    by_mk = _index_rows(rows)

    # Fair non-DC da V1 (strutturali); DC SEMPRE da STRICT, mai V1.
    # La derivazione fair non scrive derived_quote/is_real_quote sulle righe KPI.
    fair_by = resolve_fair_book_for_panel_rows(
        rows,
        today_fixture_id=fixture_meta.get("today_fixture_id"),
        snapshot_at=fixture_meta.get("snapshot_at"),
    )
    for mk in DC_V2_MARKET_KEYS:
        fair_by.pop(mk, None)
    dc_fair = _resolve_dc_fair_book_v2(strict_by_market)
    fair_by = {**fair_by, **dc_fair}

    model_probs = build_model_context_probability_map(rows)
    probs_by_market = _probs_map_v2(
        by_mk,
        fair_by=fair_by,
        model_probs=model_probs,
        fixture_meta=fixture_meta,
    )

    items: list[dict[str, Any]] = []
    for mk in DC_V2_MARKET_KEYS:
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

    return items, dc_fair


def _enrich_markets_from_engine_batch(
    markets: list[dict[str, Any]],
    engine_batch: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """Aggiunge diagnostici gate/fair ai compact V36 senza cambiare score."""
    items = (engine_batch or {}).get("items") if isinstance(engine_batch, dict) else None
    if not isinstance(items, list):
        return markets
    by_item = {
        str(it.get("market_key")): it
        for it in items
        if isinstance(it, dict) and it.get("market_key")
    }
    out: list[dict[str, Any]] = []
    for m in markets:
        if not isinstance(m, dict):
            continue
        mk = str(m.get("market_key") or "")
        it = by_item.get(mk)
        if not it:
            out.append(m)
            continue
        enriched = dict(m)
        if "gate_reason_codes" not in enriched:
            enriched["gate_reason_codes"] = _gate_reason_codes(it)
        if enriched.get("gate_status") is None:
            enriched["gate_status"] = it.get("gate_status")
        inp = it.get("input") if isinstance(it.get("input"), dict) else {}
        if "fair_book_probability" not in enriched:
            enriched["fair_book_probability"] = inp.get("fair_book_probability")
        out.append(enriched)
    return out


def build_run_v2_purchasability(
    *,
    kpi_panel: dict[str, Any] | None,
    match: Any,
    season_label: str | None = None,
    competition_name: str | None = None,
    snapshot_lead: timedelta | None = None,
    strict_by_market: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Purchasability V36 + DC fair STRICT overlay + append O/U 0.5."""
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
        "run_v2_dc_fair_strict_overlay": True,
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

    markets_out = _enrich_markets_from_engine_batch(
        list(base.get("markets") or []),
        base.get("engine_batch") if isinstance(base.get("engine_batch"), dict) else None,
    )

    # DC V2: sostituisce le entry V36 con fair STRICT-only.
    dc_items, dc_fair = _score_dc_items(
        kpi_panel=kpi_panel,
        fixture_meta=fixture_meta,
        strict_by_market=strict_by_market,
    )
    dc_compact = {
        str(it.get("market_key")): _compact_market_from_item(
            it,
            fair_info=dc_fair.get(str(it.get("market_key"))),
            extra={"v2_only_dc_fair_strict": True},
        )
        for it in dc_items
        if isinstance(it, dict) and it.get("market_key")
    }
    replaced: list[dict[str, Any]] = []
    seen_dc: set[str] = set()
    for m in markets_out:
        if not isinstance(m, dict):
            continue
        mk = str(m.get("market_key") or "")
        if mk in dc_compact:
            replaced.append(dc_compact[mk])
            seen_dc.add(mk)
        else:
            replaced.append(m)
    for mk, compact in dc_compact.items():
        if mk not in seen_dc:
            replaced.append(compact)
    markets_out = replaced

    ou05_items = _score_ou05_items(kpi_panel=kpi_panel, fixture_meta=fixture_meta)
    existing = {str(m.get("market_key")) for m in markets_out if isinstance(m, dict)}
    ou05_fair = _resolve_ou05_fair_book(_index_rows(
        [r for r in (kpi_panel.get("rows") or []) if isinstance(r, dict)]
    ))
    for it in ou05_items:
        mk = it.get("market_key")
        if mk in existing:
            continue
        markets_out.append(
            _compact_market_from_item(
                it,
                fair_info=ou05_fair.get(str(mk)),
                extra={"v2_only_ou05": True},
            )
        )

    out = dict(base)
    out["markets"] = markets_out
    out["run_v2_purchasability_market_keys"] = list(RUN_V2_PURCHASABILITY_MARKET_KEYS)
    out["run_v2_ou05_extension"] = True
    out["run_v2_dc_fair_strict_overlay"] = True
    out["dc_fair_probability_source"] = SOURCE_DC_FAIR_V2
    return out
