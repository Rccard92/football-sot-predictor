"""Drill-down su un singolo pattern Pattern Insights.

Due domande, entrambe sullo stesso pattern gia' trovato:
1. Vale ovunque o lo tengono in piedi due o tre campionati? (scomposizione
   per lega — NON e' una nuova ricerca: nessuna ipotesi aggiuntiva viene
   testata, quindi non peggiora il problema del multiple testing.)
2. Quali partite lo hanno attivato davvero?

Il matching viene rifatto rileggendo le righe con lo stesso loader usato in
fase di scoperta: i quintili delle feature continue sono ricalcolati sullo
stesso insieme di righe, quindi le classi coincidono con quelle originali.
"""

from __future__ import annotations

import statistics
from typing import Any

from sqlalchemy.orm import Session

from app.models.cecchino_run_v2_pattern_insight import (
    TARGET_TYPE_MARKET,
    CecchinoRunV2PatternInsightCandidate,
    CecchinoRunV2PatternInsightRun,
)
from app.services.cecchino_data_lab.errors import CecchinoLabImportError
from app.services.cecchino_data_lab.run_v2_grid_dataset import (
    RunV2GridRow,
    load_run_v2_market_rows,
    load_run_v2_synthetic_rows,
)
from app.services.cecchino_data_lab.run_v2_grid_vocabulary import Atom, combo_holds

MIN_LEAGUE_SAMPLE = 5


def _stats_for(rows: list[RunV2GridRow]) -> dict[str, Any]:
    n = len(rows)
    wins = sum(1 for r in rows if r.won)
    profits = [r.profit_1u for r in rows if r.profit_1u is not None]
    quotes = [r.quota_book for r in rows if r.quota_book is not None]
    return {
        "n": n,
        "wins": wins,
        "losses": n - wins,
        "win_rate_pct": round(wins / n * 100.0, 2) if n else None,
        "roi_pct": round(statistics.fmean(profits) * 100.0, 2) if profits else None,
        "profit_units": round(sum(profits), 2) if profits else None,
        "avg_quota": round(statistics.fmean(quotes), 2) if quotes else None,
    }


def get_candidate_detail(
    db: Session, candidate_id: int, *, max_matches: int = 300
) -> dict[str, Any]:
    candidate = db.get(CecchinoRunV2PatternInsightCandidate, candidate_id)
    if not candidate:
        raise CecchinoLabImportError("candidate_not_found", "Pattern non trovato", status_code=404)

    insight_run = db.get(CecchinoRunV2PatternInsightRun, int(candidate.insight_run_id))
    if not insight_run:
        raise CecchinoLabImportError("run_not_found", "Run non trovato", status_code=404)

    combo = tuple(
        Atom(column=str(f["column"]), value=str(f["value"])) for f in (candidate.filters_json or [])
    )
    run_v2_run_id = int(insight_run.run_v2_run_id)
    is_market = candidate.target_type == TARGET_TYPE_MARKET

    if is_market:
        rows = load_run_v2_market_rows(
            db, run_id=run_v2_run_id, market_key=candidate.target_key
        )
    else:
        rows = load_run_v2_synthetic_rows(
            db,
            run_id=run_v2_run_id,
            stat_key=candidate.target_key,
            threshold=float(candidate.threshold) if candidate.threshold is not None else 0.0,
        )

    matched = [r for r in rows if combo_holds(r, combo)]
    overall = _stats_for(matched)
    baseline = (
        float(candidate.baseline_win_rate_pct)
        if candidate.baseline_win_rate_pct is not None
        else None
    )

    # --- scomposizione per campionato -------------------------------------
    by_comp: dict[str, list[RunV2GridRow]] = {}
    for r in matched:
        by_comp.setdefault(r.competition, []).append(r)

    league_rows: list[dict[str, Any]] = []
    for comp, comp_rows in by_comp.items():
        s = _stats_for(comp_rows)
        league_rows.append(
            {
                "competition": comp,
                **s,
                "deviation_pct": (
                    round(s["win_rate_pct"] - baseline, 2)
                    if s["win_rate_pct"] is not None and baseline is not None
                    else None
                ),
                "enough_sample": s["n"] >= MIN_LEAGUE_SAMPLE,
            }
        )
    league_rows.sort(key=lambda x: (x["profit_units"] if x["profit_units"] is not None else x["n"]), reverse=True)

    # --- concentrazione ----------------------------------------------------
    scored = [l for l in league_rows if l["enough_sample"]]
    metric_key = "roi_pct" if is_market else "win_rate_pct"
    positives = [l for l in scored if (l[metric_key] or 0) > (baseline or 0 if not is_market else 0)]
    total_profit = sum(l["profit_units"] or 0 for l in league_rows)
    top_share = None
    if is_market and total_profit > 0:
        best = max((l["profit_units"] or 0) for l in league_rows)
        top_share = round(best / total_profit * 100.0, 1)

    concentration = {
        "leagues_total": len(league_rows),
        "leagues_with_sample": len(scored),
        "leagues_favourable": len(positives),
        "top_league_profit_share_pct": top_share,
        "min_league_sample": MIN_LEAGUE_SAMPLE,
    }

    # --- partite che hanno attivato il pattern -----------------------------
    matched_sorted = sorted(matched, key=lambda r: r.kickoff_at or "")
    matches = [
        {
            "lab_match_id": r.lab_match_id,
            "kickoff_at": r.kickoff_at,
            "competition": r.competition,
            "home_team": r.home_team,
            "away_team": r.away_team,
            "won": r.won,
            "quota_book": r.quota_book,
            "profit_1u": r.profit_1u,
            "actual_value": r.actual_value,
        }
        for r in matched_sorted[:max_matches]
    ]

    return {
        "candidate": {
            "id": int(candidate.id),
            "target_type": candidate.target_type,
            "target_key": candidate.target_key,
            "target_label": candidate.target_label,
            "threshold": float(candidate.threshold) if candidate.threshold is not None else None,
            "filters_text_human": candidate.filters_text_human,
            "refined_from_text": candidate.refined_from_text,
            "baseline_win_rate_pct": baseline,
        },
        "overall": overall,
        "by_competition": league_rows,
        "concentration": concentration,
        "matches": matches,
        "matches_total": len(matched),
        "matches_truncated": len(matched) > len(matches),
    }
