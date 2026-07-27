"""Settlement storico 14 mercati + profitto real/synthetic."""

from __future__ import annotations

from typing import Any

from app.models.cecchino_signal_activation import EVAL_LOST, EVAL_WON
from app.services.cecchino.cecchino_kpi_panel_v2_betfair import KPI_V2_ROW_DEFS
from app.services.cecchino.cecchino_signal_evaluation import evaluate_market_selection

PROFIT_ACTUAL = "actual_bet365"
PROFIT_SYNTHETIC = "synthetic_derived"
PROFIT_NO_BOOK = "no_book_quote"


def match_result_from_lab_match(match: Any) -> dict[str, Any]:
    return {
        "fulltime": {
            "home": match.ft_home_goals,
            "away": match.ft_away_goals,
        },
        "halftime": {
            "home": match.ht_home_goals,
            "away": match.ht_away_goals,
        },
    }


def _period_line(market_key: str) -> tuple[str | None, str | None]:
    if market_key in ("HOME", "DRAW", "AWAY", "ONE_X", "X_TWO", "ONE_TWO"):
        return "FT", None
    if market_key == "DRAW_PT":
        return "HT", None
    if market_key in ("OVER_1_5",):
        return "FT", "1.5"
    if market_key in ("OVER_2_5", "UNDER_2_5"):
        return "FT", "2.5"
    if market_key == "UNDER_3_5":
        return "FT", "3.5"
    if market_key in ("UNDER_PT_1_5", "OVER_PT_1_5"):
        return "HT", "1.5"
    if market_key == "OVER_PT_0_5":
        return "HT", "0.5"
    return None, None


def settle_historical_markets(
    *,
    match: Any,
    kpi_panel: dict[str, Any],
    quote_bundle: dict[str, Any],
    signals_json: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    result = match_result_from_lab_match(match)
    quotes = quote_bundle.get("quotes") or {}
    rows_by_key = {
        r.get("market_key"): r for r in (kpi_panel.get("rows") or []) if isinstance(r, dict)
    }
    label_by_key = {k: lab for k, lab in KPI_V2_ROW_DEFS}

    active_signals: set[str] = set()
    if signals_json:
        for row in signals_json.get("rows") or []:
            if not isinstance(row, dict):
                continue
            for col, cell in row.items():
                if col in ("group", "label", "model", "affidabilita"):
                    continue
                if cell in ("SI", "YES", True):
                    # best-effort: market keys may appear in column names
                    active_signals.add(str(col))

    out: list[dict[str, Any]] = []
    for market_key, label in KPI_V2_ROW_DEFS:
        period, line = _period_line(market_key)
        kpi_row = rows_by_key.get(market_key) or {}
        qmeta = quotes.get(market_key) or {}
        eval_res = evaluate_market_selection(market_key, result)
        status = eval_res.get("evaluation_status")
        won: bool | None
        if status == EVAL_WON:
            won = True
        elif status == EVAL_LOST:
            won = False
        else:
            won = None

        is_real = bool(qmeta.get("is_real_book_quote"))
        is_derived = bool(qmeta.get("is_derived"))
        quota_book = qmeta.get("value")
        if quota_book is None:
            quota_book = kpi_row.get("quota_book")

        profit_real = None
        profit_synth = None
        category = PROFIT_NO_BOOK
        if won is not None and quota_book is not None:
            delta = (float(quota_book) - 1.0) if won else -1.0
            if is_real:
                profit_real = round(delta, 4)
                category = PROFIT_ACTUAL
            elif is_derived:
                profit_synth = round(delta, 4)
                category = PROFIT_SYNTHETIC

        out.append(
            {
                "market_key": market_key,
                "market_label": label_by_key.get(market_key, label),
                "period": period,
                "line": line,
                "quota_cecchino": kpi_row.get("quota_cecchino"),
                "prob_cecchino": kpi_row.get("prob_cecchino"),
                "quota_book": quota_book,
                "prob_book_raw": qmeta.get("prob_raw") or kpi_row.get("prob_book"),
                "prob_book_fair": qmeta.get("prob_fair"),
                "quote_source_type": qmeta.get("source_type"),
                "is_real_book_quote": is_real,
                "is_derived_quote": is_derived,
                "derivation_method": qmeta.get("derivation_method"),
                "edge_pct": kpi_row.get("edge_pct"),
                "vantaggio_prob": kpi_row.get("vantaggio_prob"),
                "rating": kpi_row.get("rating"),
                "signal_active": market_key in active_signals,
                "signal_sources_json": [],
                "evaluation_status": status,
                "won": won,
                "profit_1u_real": profit_real,
                "profit_1u_synthetic": profit_synth,
                "result_reason": eval_res.get("evaluation_reason"),
                "profit_category": category,
            }
        )
    return out


def settlement_summary(market_rows: list[dict[str, Any]]) -> dict[str, Any]:
    won = sum(1 for r in market_rows if r.get("won") is True)
    lost = sum(1 for r in market_rows if r.get("won") is False)
    real_profit = sum(
        float(r["profit_1u_real"]) for r in market_rows if r.get("profit_1u_real") is not None
    )
    synth_profit = sum(
        float(r["profit_1u_synthetic"])
        for r in market_rows
        if r.get("profit_1u_synthetic") is not None
    )
    return {
        "won": won,
        "lost": lost,
        "evaluable": won + lost,
        "real_profit_1u": round(real_profit, 4),
        "synthetic_profit_1u": round(synth_profit, 4),
        "real_quote_settled": sum(
            1 for r in market_rows if r.get("is_real_book_quote") and r.get("won") is not None
        ),
        "derived_quote_settled": sum(
            1 for r in market_rows if r.get("is_derived_quote") and r.get("won") is not None
        ),
    }
