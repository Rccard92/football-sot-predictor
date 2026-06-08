"""Debug breakdown picchetti Cecchino — Quota Cecchino 1/X/2 e DC."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models.cecchino_today_fixture import ELIGIBILITY_ELIGIBLE, CecchinoTodayFixture
from app.services.cecchino.cecchino_goal_formulas import build_goal_market_debug
from app.services.cecchino.cecchino_constants import (
    FINAL_QUOTA_WEIGHTS,
    PICCHETTO_KEY_HOME_AWAY,
    PICCHETTO_KEY_LAST5_HOME_AWAY,
    PICCHETTO_KEY_LAST6_TOTALS,
    PICCHETTO_KEY_TOTALS,
    STATUS_AVAILABLE,
    STATUS_INSUFFICIENT_DATA,
    STATUS_PARTIAL_LOW_SAMPLE,
)
from app.services.cecchino.cecchino_selection_keys import (
    SEL_AWAY,
    SEL_DRAW,
    SEL_HOME,
    SEL_ONE_TWO,
    SEL_ONE_X,
    SEL_OVER_1_5,
    SEL_OVER_2_5,
    SEL_OVER_PT_0_5,
    SEL_OVER_PT_1_5,
    SEL_UNDER_2_5,
    SEL_UNDER_3_5,
    SEL_UNDER_PT_1_5,
    SEL_X_TWO,
)

DEBUG_VERSION = "cecchino_picchetti_debug_v3"
KPI_COHERENCE_TOLERANCE = 0.01

_PICCHETTO_ORDER = (
    PICCHETTO_KEY_TOTALS,
    PICCHETTO_KEY_HOME_AWAY,
    PICCHETTO_KEY_LAST6_TOTALS,
    PICCHETTO_KEY_LAST5_HOME_AWAY,
)

_OUTCOME_ATTR = {
    "1": ("outcome_1", "quota_1", "prob_1"),
    "X": ("outcome_x", "quota_x", "prob_x"),
    "2": ("outcome_2", "quota_2", "prob_2"),
}

_1X2_MARKETS = (
    (SEL_HOME, "1"),
    (SEL_DRAW, "X"),
    (SEL_AWAY, "2"),
)

_DC_MARKETS = (
    (SEL_ONE_X, "1X", "1 / (prob_1 + prob_x)", ("prob_1", "prob_x"), ("quota_1", "quota_x")),
    (SEL_X_TWO, "X2", "1 / (prob_x + prob_2)", ("prob_x", "prob_2"), ("quota_x", "quota_2")),
    (SEL_ONE_TWO, "12", "1 / (prob_1 + prob_2)", ("prob_1", "prob_2"), ("quota_1", "quota_2")),
)

_OU_MARKETS: tuple[tuple[str, str], ...] = (
    (SEL_OVER_1_5, "Over 1.5"),
    (SEL_OVER_2_5, "Over 2.5"),
    (SEL_UNDER_2_5, "Under 2.5"),
    (SEL_UNDER_3_5, "Under 3.5"),
    (SEL_UNDER_PT_1_5, "Under PT 1.5"),
    (SEL_OVER_PT_0_5, "Over PT 0.5"),
    (SEL_OVER_PT_1_5, "Over PT 1.5"),
)


def _num(v: Any) -> float | None:
    if v is None or isinstance(v, str):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _wdl_str(ctx: dict[str, Any] | None) -> str:
    if not ctx or not isinstance(ctx, dict):
        return "—"
    w = int(ctx.get("wins") or 0)
    d = int(ctx.get("draws") or 0)
    l = int(ctx.get("losses") or 0)
    return f"{w}-{d}-{l}"


def _outcome_from_picchetto(pic: dict[str, Any], outcome: str) -> tuple[float | None, float | None]:
    outcome_attr, quota_attr, prob_attr = _OUTCOME_ATTR[outcome]
    o = pic.get(outcome_attr) or {}
    probs = pic.get("probabilities") or {}
    math_odds = pic.get("mathematical_odds") or {}
    prob = _num(o.get("prob") if isinstance(o, dict) else None)
    if prob is None:
        prob = _num(probs.get(prob_attr))
    odd = _num(o.get("quota") if isinstance(o, dict) else None)
    if odd is None:
        odd = _num(math_odds.get(quota_attr))
    return prob, odd


def _picchetto_contribution(
    pic: dict[str, Any] | None,
    pic_name: str,
    weight: float,
    outcome: str,
    *,
    warnings: list[str],
    segno: str,
) -> dict[str, Any]:
    if not pic or not isinstance(pic, dict):
        warnings.append(f"missing_picchetto:{pic_name}")
        return {
            "name": pic_name,
            "weight": weight,
            "sample_home": None,
            "sample_away": None,
            "record_home": "—",
            "record_away": "—",
            "probability": None,
            "probability_pct": None,
            "odd": None,
            "weighted_contribution": None,
            "status": "insufficient_data",
        }

    prob, odd = _outcome_from_picchetto(pic, outcome)
    if prob is not None and prob <= 0:
        warnings.append(f"zero_probability:{segno}:{pic_name}")
    if odd is None:
        warnings.append(f"odd_not_calculable:{segno}:{pic_name}")

    contrib = round(odd * weight, 4) if odd is not None else None
    return {
        "name": pic_name,
        "weight": weight,
        "sample_home": pic.get("sample_home"),
        "sample_away": pic.get("sample_away"),
        "target_sample_home": pic.get("target_sample_home"),
        "target_sample_away": pic.get("target_sample_away"),
        "record_home": _wdl_str(pic.get("home_context")),
        "record_away": _wdl_str(pic.get("away_context")),
        "probability": round(prob, 6) if prob is not None else None,
        "probability_pct": round(prob * 100, 2) if prob is not None else None,
        "odd": round(odd, 2) if odd is not None else None,
        "weighted_contribution": contrib,
        "status": pic.get("status"),
        "picchetto_warnings": list(pic.get("warnings") or []),
    }


def _build_1x2_market_debug(
    market_key: str,
    segno: str,
    picchetti: dict[str, Any],
    final: dict[str, Any],
    *,
    warnings: list[str],
) -> dict[str, Any]:
    _, quota_attr, _ = _OUTCOME_ATTR[segno]
    picchetto_rows = [
        _picchetto_contribution(
            picchetti.get(name) if isinstance(picchetti.get(name), dict) else None,
            name,
            FINAL_QUOTA_WEIGHTS[name],
            segno,
            warnings=warnings,
            segno=segno,
        )
        for name in _PICCHETTO_ORDER
    ]
    final_odd = _num(final.get(quota_attr))
    return {
        "market_key": market_key,
        "segno": segno,
        "picchetti": picchetto_rows,
        "final_odd": round(final_odd, 2) if final_odd is not None else None,
        "formula": (
            f"quota_cecchino_{segno.lower()} = "
            "(quota_totals * 0.25) + (quota_home_away * 0.20) + "
            "(quota_last6_totals * 0.35) + (quota_last5_home_away * 0.20)"
        ),
    }


def _build_dc_market_debug(
    market_key: str,
    segno: str,
    formula: str,
    prob_keys: tuple[str, ...],
    quota_keys: tuple[str, ...],
    final: dict[str, Any],
) -> dict[str, Any]:
    inputs: dict[str, Any] = {}
    prob_sum = 0.0
    prob_ok = True
    for pk, qk in zip(prob_keys, quota_keys, strict=True):
        q = _num(final.get(qk))
        p = _num(final.get(pk))
        if p is None and q is not None and q > 0:
            p = 1.0 / q
        inputs[qk] = round(q, 4) if q is not None else None
        inputs[pk] = round(p, 6) if p is not None else None
        if p is None or p <= 0:
            prob_ok = False
        else:
            prob_sum += p

    final_odd = round(1.0 / prob_sum, 2) if prob_ok and prob_sum > 0 else None

    return {
        "market_key": market_key,
        "segno": segno,
        "formula": formula,
        "inputs": inputs,
        "final_odd": final_odd,
        "formula_status": "available" if final_odd is not None else "insufficient_data",
    }


def _missing_formula_markets(goal_markets: dict[str, Any] | None) -> list[dict[str, Any]]:
    missing: list[dict[str, Any]] = []
    gm = goal_markets if isinstance(goal_markets, dict) else {}
    for key, label in _OU_MARKETS:
        block = gm.get(key) if isinstance(gm.get(key), dict) else {}
        if block.get("final_odd") is not None:
            continue
        if block.get("formula_version"):
            continue
        missing.append(
            {
                "market_key": key,
                "label": label,
                "formula_status": "missing_formula",
            },
        )
    return missing


def _collect_picchetti_warnings(picchetti: dict[str, Any], warnings: list[str]) -> None:
    for name in _PICCHETTO_ORDER:
        pic = picchetti.get(name)
        if not pic:
            continue
        if not isinstance(pic, dict):
            continue
        for w in pic.get("warnings") or []:
            if isinstance(w, str) and w not in warnings:
                warnings.append(w)
        if pic.get("status") == STATUS_INSUFFICIENT_DATA:
            if f"missing_picchetto:{name}" not in warnings:
                warnings.append(f"missing_picchetto:{name}")


def _check_kpi_coherence(
    markets: dict[str, Any],
    kpi_panel: dict[str, Any] | None,
    *,
    warnings: list[str],
) -> None:
    if not kpi_panel:
        return
    by_key = {
        r["market_key"]: r
        for r in (kpi_panel.get("rows") or [])
        if isinstance(r, dict) and r.get("market_key")
    }
    ou_keys = [k for k, _ in _OU_MARKETS]
    for market_key in (SEL_HOME, SEL_DRAW, SEL_AWAY, SEL_ONE_X, SEL_X_TWO, SEL_ONE_TWO, *ou_keys):
        mkt = markets.get(market_key) or {}
        summary = mkt.get("summary") if isinstance(mkt.get("summary"), dict) else {}
        debug_odd = _num(summary.get("final_odd")) or _num(mkt.get("final_odd"))
        kpi_row = by_key.get(market_key) or {}
        kpi_odd = _num(kpi_row.get("quota_cecchino"))
        if debug_odd is None or kpi_odd is None:
            continue
        if abs(debug_odd - kpi_odd) > KPI_COHERENCE_TOLERANCE:
            warnings.append(f"kpi_debug_mismatch:{market_key}")


def _formula_status_from_final(final: dict[str, Any]) -> str:
    st = str(final.get("status") or STATUS_INSUFFICIENT_DATA)
    if st == STATUS_AVAILABLE:
        return "available"
    if st == STATUS_PARTIAL_LOW_SAMPLE:
        return "partial"
    return "insufficient_data"


def build_cecchino_picchetti_debug(
    *,
    cecchino_output: dict[str, Any],
    kpi_panel: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Costruisce debug completo da cecchino_output_json persistito."""
    warnings: list[str] = list(cecchino_output.get("warnings") or [])
    picchetti = cecchino_output.get("picchetti") or {}
    if not isinstance(picchetti, dict):
        picchetti = {}
    final = cecchino_output.get("final") or {}
    if not isinstance(final, dict):
        final = {}

    _collect_picchetti_warnings(picchetti, warnings)
    for w in final.get("warnings") or []:
        if isinstance(w, str) and w not in warnings:
            warnings.append(w)

    markets: dict[str, Any] = {}
    for market_key, segno in _1X2_MARKETS:
        markets[market_key] = _build_1x2_market_debug(
            market_key,
            segno,
            picchetti,
            final,
            warnings=warnings,
        )

    for market_key, segno, formula, prob_keys, quota_keys in _DC_MARKETS:
        markets[market_key] = _build_dc_market_debug(
            market_key,
            segno,
            formula,
            prob_keys,
            quota_keys,
            final,
        )

    goal_markets = cecchino_output.get("goal_markets") or {}
    if not isinstance(goal_markets, dict):
        goal_markets = {}
    for market_key, label in _OU_MARKETS:
        block = goal_markets.get(market_key)
        if isinstance(block, dict) and block:
            dbg = build_goal_market_debug(block)
            dbg["segno"] = label
            if block.get("formula_version") == "goal_market_poisson_empirical_v2":
                dbg["formula_status"] = block.get("status")
            markets[market_key] = dbg
            for w in block.get("warnings") or []:
                if isinstance(w, str) and w not in warnings:
                    warnings.append(w)

    missing = _missing_formula_markets(goal_markets)
    _check_kpi_coherence(markets, kpi_panel, warnings=warnings)

    return {
        "version": DEBUG_VERSION,
        "formula_status": _formula_status_from_final(final),
        "weights": dict(FINAL_QUOTA_WEIGHTS),
        "markets": markets,
        "missing_formulas": missing,
        "final": {
            "quota_1": final.get("quota_1"),
            "quota_x": final.get("quota_x"),
            "quota_2": final.get("quota_2"),
            "prob_1": final.get("prob_1"),
            "prob_x": final.get("prob_x"),
            "prob_2": final.get("prob_2"),
            "status": final.get("status"),
        },
        "warnings": warnings,
    }


def build_picchetti_debug_summary(full_debug: dict[str, Any]) -> dict[str, Any]:
    return {
        "version": full_debug.get("version"),
        "formula_status": full_debug.get("formula_status"),
        "weights": full_debug.get("weights"),
        "missing_formulas_count": len(full_debug.get("missing_formulas") or []),
    }


def build_picchetti_debug_for_row(
    row: CecchinoTodayFixture,
    *,
    kpi_panel: dict[str, Any] | None = None,
) -> dict[str, Any]:
    output = row.cecchino_output_json or {}
    if not isinstance(output, dict):
        output = {}
    debug = build_cecchino_picchetti_debug(
        cecchino_output=output,
        kpi_panel=kpi_panel,
    )
    return {
        "fixture": {
            "today_fixture_id": int(row.id),
            "local_fixture_id": int(row.local_fixture_id) if row.local_fixture_id else None,
            "provider_fixture_id": int(row.provider_fixture_id),
            "home_team": row.home_team_name,
            "away_team": row.away_team_name,
            "kickoff": row.kickoff.isoformat() if row.kickoff else None,
        },
        **debug,
    }


def get_picchetti_debug_json(db: Session, today_fixture_id: int) -> dict[str, Any] | None:
    row = db.get(CecchinoTodayFixture, today_fixture_id)
    if row is None:
        return None
    if row.eligibility_status != ELIGIBILITY_ELIGIBLE:
        return {
            "status": "error",
            "code": "not_eligible",
            "message": "Fixture non eleggibile",
        }

    from app.services.cecchino.cecchino_today_service import _resolve_kpi_panel_for_detail

    kpi_panel = _resolve_kpi_panel_for_detail(row, db)
    payload = build_picchetti_debug_for_row(row, kpi_panel=kpi_panel)
    return {"status": "ok", **payload}
