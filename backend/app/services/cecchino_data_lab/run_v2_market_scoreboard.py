"""Cecchino contro il mercato, su tutte le partite eleggibili.

Non riguarda i pattern: misura il modello di base. Tutto a quota di chiusura
(la quota piu' vicina a quella che si gioca il giorno della partita), con le
probabilita' "giuste" del bookmaker ricavate togliendo il margine in modo
proporzionale.

Tre letture:
1. Precisione (Brier score): chi prevede meglio gli esiti, Cecchino o Bet365.
2. Margine del bookmaker per campionato: dove il bookmaker trattiene di piu'
   e dove Cecchino si avvicina o supera la sua precisione.
3. Curva del valore: quando Cecchino vede piu' probabilita' del bookmaker,
   quelle giocate vincono davvero di piu'?

Il 2025/26 e' escluso per costruzione (stagione sotto chiave).
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services.cecchino_data_lab.run_v2_grid_dataset import _CLOSING_QUOTE_SQL
from app.services.cecchino_data_lab.run_v2_scope import (
    LOCKBOX_SEASON,
    TIER_LABELS,
    TOP_TIER_COMPETITIONS,
)


def _inv(col: str) -> str:
    return f"(1.0/NULLIF({col}, 0))"


_H, _D, _A = _inv("m.bet365_closing_home"), _inv("m.bet365_closing_draw"), _inv("m.bet365_closing_away")
_HTH, _HTD, _HTA = _inv("m.bet365_ht_home"), _inv("m.bet365_ht_draw"), _inv("m.bet365_ht_away")
_T1X2 = f"({_H} + {_D} + {_A})"
_THT = f"({_HTH} + {_HTD} + {_HTA})"


def _pair(over: str, under: str) -> tuple[str, str]:
    o, u = _inv(over), _inv(under)
    return f"({o} / NULLIF({o} + {u}, 0))", f"({u} / NULLIF({o} + {u}, 0))"


_O05, _U05 = _pair("m.bet365_over_05", "m.bet365_under_05")
_O15, _U15 = _pair("m.bet365_over_15", "m.bet365_under_15")
_O25, _U25 = _pair("m.bet365_closing_over_25", "m.bet365_closing_under_25")
_O35, _U35 = _pair("m.bet365_over_35", "m.bet365_under_35")

_FAIR_PROB_SQL: dict[str, str] = {
    "HOME": f"({_H} / NULLIF({_T1X2}, 0))",
    "DRAW": f"({_D} / NULLIF({_T1X2}, 0))",
    "AWAY": f"({_A} / NULLIF({_T1X2}, 0))",
    "ONE_X": f"(({_H} + {_D}) / NULLIF({_T1X2}, 0))",
    "X_TWO": f"(({_D} + {_A}) / NULLIF({_T1X2}, 0))",
    "ONE_TWO": f"(({_H} + {_A}) / NULLIF({_T1X2}, 0))",
    "OVER_0_5": _O05,
    "UNDER_0_5": _U05,
    "OVER_1_5": _O15,
    "UNDER_1_5": _U15,
    "OVER_2_5": _O25,
    "UNDER_2_5": _U25,
    "OVER_3_5": _O35,
    "UNDER_3_5": _U35,
    "HOME_PT": f"({_HTH} / NULLIF({_THT}, 0))",
    "DRAW_PT": f"({_HTD} / NULLIF({_THT}, 0))",
    "AWAY_PT": f"({_HTA} / NULLIF({_THT}, 0))",
}


def _case(mapping: dict[str, str]) -> str:
    whens = "\n".join(f"WHEN '{k}' THEN {v}" for k, v in mapping.items())
    return f"(CASE r.market_key {whens} END)::double precision"


def _top_list() -> str:
    return ", ".join("'" + c.replace("'", "''") + "'" for c in sorted(TOP_TIER_COMPETITIONS))


def _base_cte() -> str:
    return f"""
    WITH latest_runs AS (
        SELECT DISTINCT ON (summary_json->>'season_label') id
        FROM cecchino_run_v2_runs
        WHERE status = 'completed' AND run_scope = 'full'
          AND summary_json->>'season_label' < :lockbox
        ORDER BY summary_json->>'season_label', completed_at DESC
    ),
    base AS (
        SELECT s.season_label,
               s.competition_name,
               CASE WHEN s.competition_name IN ({_top_list()}) THEN 'top' ELSE 'lower' END AS tier,
               r.market_key,
               r.market_family,
               r.won::int AS won,
               r.probability::double precision AS p_cecchino,
               {_case(_FAIR_PROB_SQL)} AS p_fair,
               {_case(_CLOSING_QUOTE_SQL)} AS q_close,
               {_T1X2} AS overround_1x2
        FROM cecchino_run_v2_market_results r
        JOIN latest_runs lr ON lr.id = r.run_id
        JOIN cecchino_run_v2_match_snapshots s ON s.id = r.match_snapshot_id
        JOIN cecchino_lab_matches m ON m.id = s.lab_match_id
        WHERE s.eligibility_status = 'eligible_core'
          AND r.observation_layer = 'core_strict'
          AND r.pre_match_input_safe IS TRUE
          AND r.won IS NOT NULL
    ),
    scored AS (
        SELECT *,
               CASE WHEN q_close > 1 THEN CASE WHEN won = 1 THEN q_close - 1 ELSE -1 END END AS profit_close,
               CASE WHEN p_cecchino IS NOT NULL AND p_fair > 0
                    THEN (p_cecchino / p_fair - 1) * 100 END AS edge_close_pct
        FROM base
    )
    """


def _rows(db: Session, sql: str) -> list[dict[str, Any]]:
    return [dict(r._mapping) for r in db.execute(text(sql), {"lockbox": LOCKBOX_SEASON})]


def _f(v: Any, nd: int = 4) -> float | None:
    return round(float(v), nd) if v is not None else None


def get_market_scoreboard(db: Session) -> dict[str, Any]:
    cte = _base_cte()

    accuracy = [
        {
            "season_label": r["season_label"],
            "market_family": r["market_family"],
            "tier": r["tier"],
            "n": int(r["n"]),
            "brier_cecchino": _f(r["brier_cecchino"]),
            "brier_book": _f(r["brier_book"]),
            "won_pct": _f(r["won_pct"], 2),
        }
        for r in _rows(
            db,
            cte
            + """
            SELECT season_label, market_family, tier, count(*) AS n,
                   avg(power(won - p_cecchino, 2)) AS brier_cecchino,
                   avg(power(won - p_fair, 2))     AS brier_book,
                   avg(won) * 100                  AS won_pct
            FROM scored
            WHERE p_cecchino IS NOT NULL AND p_fair IS NOT NULL
            GROUP BY GROUPING SETS ((season_label, market_family, tier), (season_label, market_family))
            ORDER BY season_label, market_family, tier NULLS FIRST
            """,
        )
    ]
    for a in accuracy:
        a["tier"] = a["tier"] or "all"

    by_competition = [
        {
            "competition": r["competition_name"],
            "tier": r["tier"],
            "n": int(r["n"]),
            "brier_cecchino": _f(r["brier_cecchino"]),
            "brier_book": _f(r["brier_book"]),
            "margin_pct": _f(r["margin_pct"], 2),
            "roi_all_bets_pct": _f(r["roi_all_bets_pct"], 2),
        }
        for r in _rows(
            db,
            cte
            + """
            SELECT competition_name, tier, count(*) AS n,
                   avg(power(won - p_cecchino, 2)) AS brier_cecchino,
                   avg(power(won - p_fair, 2))     AS brier_book,
                   (avg(overround_1x2) - 1) * 100  AS margin_pct,
                   avg(profit_close) * 100         AS roi_all_bets_pct
            FROM scored
            WHERE market_family = 'FT_1X2' AND p_cecchino IS NOT NULL AND p_fair IS NOT NULL
            GROUP BY competition_name, tier
            ORDER BY (avg(power(won - p_cecchino, 2)) - avg(power(won - p_fair, 2)))
            """,
        )
    ]

    edge_order = ["<-20", "-20..-10", "-10..0", "0..10", "10..20", "20..40", "40+"]
    value_curve = [
        {
            "season_label": r["season_label"],
            "tier": r["tier"] or "all",
            "bucket": r["bucket"],
            "n": int(r["n"]),
            "roi_pct": _f(r["roi_pct"], 2),
            "won_pct": _f(r["won_pct"], 2),
            "fair_pct": _f(r["fair_pct"], 2),
            "cecchino_pct": _f(r["cecchino_pct"], 2),
            "avg_quota": _f(r["avg_quota"], 2),
        }
        for r in _rows(
            db,
            cte
            + """
            , bucketed AS (
                SELECT season_label, tier, won, p_fair, p_cecchino, q_close, profit_close,
                       CASE WHEN edge_close_pct < -20 THEN '<-20' WHEN edge_close_pct < -10 THEN '-20..-10'
                            WHEN edge_close_pct < 0 THEN '-10..0' WHEN edge_close_pct < 10 THEN '0..10'
                            WHEN edge_close_pct < 20 THEN '10..20' WHEN edge_close_pct < 40 THEN '20..40'
                            ELSE '40+' END AS bucket
                FROM scored
                WHERE edge_close_pct IS NOT NULL AND profit_close IS NOT NULL
            )
            SELECT season_label, tier, bucket,
                   count(*)               AS n,
                   avg(profit_close) * 100 AS roi_pct,
                   avg(won) * 100          AS won_pct,
                   avg(p_fair) * 100       AS fair_pct,
                   avg(p_cecchino) * 100   AS cecchino_pct,
                   avg(q_close)            AS avg_quota
            FROM bucketed
            GROUP BY GROUPING SETS ((season_label, tier, bucket), (season_label, bucket))
            """,
        )
    ]
    value_curve.sort(key=lambda x: (x["season_label"], x["tier"], edge_order.index(x["bucket"])))

    seasons = sorted({a["season_label"] for a in accuracy})
    return {
        "seasons": seasons,
        "lockbox_season": LOCKBOX_SEASON,
        "odds_reference": "closing",
        "tiers": [{"key": "all", "label": "Tutte le leghe"}]
        + [{"key": k, "label": v} for k, v in TIER_LABELS.items()],
        "accuracy": accuracy,
        "by_competition": by_competition,
        "value_curve": value_curve,
    }
