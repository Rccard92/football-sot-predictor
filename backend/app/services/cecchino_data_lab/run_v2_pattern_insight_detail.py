"""Drill-down su un singolo pattern Pattern Insights.

Per la stagione di scoperta e per ogni stagione di verifica completata:
1. vale ovunque o lo tengono in piedi due o tre campionati? (scomposizione
   per lega — NON e' una nuova ricerca: nessuna ipotesi aggiuntiva testata)
2. quali partite lo hanno attivato davvero?

Le fasce di tiri/corner/cartellini/arbitro sono sempre quelle della stagione
di scoperta, anche quando si leggono le stagioni di verifica.
"""

from __future__ import annotations

import statistics
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.cecchino_run_v2_pattern_insight import (
    STATUS_COMPLETED,
    TARGET_TYPE_MARKET,
    CecchinoRunV2PatternInsightCandidate,
    CecchinoRunV2PatternInsightRun,
    CecchinoRunV2PatternValidation,
    CecchinoRunV2PatternValidationRun,
)
from app.models.cecchino_run_v2 import CecchinoRunV2Run
from app.services.cecchino_data_lab.errors import CecchinoLabImportError
from app.services.cecchino_data_lab.run_v2_grid_dataset import (
    RunV2GridRow,
    load_market_raw,
    load_season_binners,
    load_synthetic_raw,
    market_rows_from_raw,
    synthetic_rows_from_raw,
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


def _season_block(
    rows: list[RunV2GridRow],
    combo: tuple[Atom, ...],
    *,
    is_market: bool,
    baseline: float | None,
    max_matches: int,
) -> dict[str, Any]:
    matched = [r for r in rows if combo_holds(r, combo)]

    by_comp: dict[str, list[RunV2GridRow]] = {}
    for r in matched:
        by_comp.setdefault(r.competition, []).append(r)

    leagues: list[dict[str, Any]] = []
    for comp, comp_rows in by_comp.items():
        s = _stats_for(comp_rows)
        leagues.append(
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
    leagues.sort(
        key=lambda x: (x["profit_units"] if x["profit_units"] is not None else x["n"]), reverse=True
    )

    scored = [l for l in leagues if l["enough_sample"]]
    if is_market:
        favourable = [l for l in scored if (l["roi_pct"] or 0) > 0]
    else:
        favourable = [l for l in scored if (l["deviation_pct"] or 0) > 0]
    # Quota sui guadagni LORDI delle leghe in attivo, non sul netto: il netto
    # puo' essere vicino a zero (o piu' piccolo della lega migliore) e farebbe
    # esplodere la percentuale oltre il 100%.
    gross_gains = sum(max(0.0, l["profit_units"] or 0.0) for l in leagues)
    top_share = None
    if is_market and gross_gains > 0:
        top_share = round(max((l["profit_units"] or 0) for l in leagues) / gross_gains * 100.0, 1)

    ordered = sorted(matched, key=lambda r: r.kickoff_at or "")
    return {
        "overall": _stats_for(matched),
        "baseline_win_rate_pct": baseline,
        "by_competition": leagues,
        "concentration": {
            "leagues_total": len(leagues),
            "leagues_with_sample": len(scored),
            "leagues_favourable": len(favourable),
            "top_league_profit_share_pct": top_share,
            "min_league_sample": MIN_LEAGUE_SAMPLE,
        },
        "matches": [
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
            for r in ordered[:max_matches]
        ],
        "matches_total": len(matched),
        "matches_truncated": len(matched) > max_matches,
    }


def _rows_for(
    db: Session,
    candidate: CecchinoRunV2PatternInsightCandidate,
    *,
    run_v2_run_id: int,
    binners: dict,
    odds_mode: str,
) -> list[RunV2GridRow]:
    if candidate.target_type == TARGET_TYPE_MARKET:
        raw = load_market_raw(
            db, run_id=run_v2_run_id, market_key=candidate.target_key, odds_mode=odds_mode
        )
        return market_rows_from_raw(raw, binners)
    raw = load_synthetic_raw(db, run_id=run_v2_run_id, stat_key=candidate.target_key)
    threshold = float(candidate.threshold) if candidate.threshold is not None else 0.0
    return synthetic_rows_from_raw(raw, binners, threshold)


def _baseline(rows: list[RunV2GridRow]) -> float | None:
    return round(sum(1 for r in rows if r.won) / len(rows) * 100.0, 3) if rows else None


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
    is_market = candidate.target_type == TARGET_TYPE_MARKET
    disc_id = int(insight_run.run_v2_run_id)
    binners = load_season_binners(db, run_id=disc_id)

    disc_rows = _rows_for(
        db, candidate, run_v2_run_id=disc_id, binners=binners, odds_mode=insight_run.odds_mode
    )
    disc_run = db.get(CecchinoRunV2Run, disc_id)
    seasons: list[dict[str, Any]] = [
        {
            "role": "discovery",
            "season_label": (disc_run.summary_json or {}).get("season_label") if disc_run else None,
            "run_v2_run_id": disc_id,
            "verdict": None,
            **_season_block(
                disc_rows,
                combo,
                is_market=is_market,
                baseline=(
                    float(candidate.baseline_win_rate_pct)
                    if candidate.baseline_win_rate_pct is not None
                    else _baseline(disc_rows)
                ),
                max_matches=max_matches,
            ),
        }
    ]

    from app.services.cecchino_data_lab.run_v2_pattern_validation_analytics import (
        _completed_validations,
    )

    vruns = _completed_validations(db, int(insight_run.id))
    seen_runs: set[int] = set()
    for vrun in vruns:
        oos_id = int(vrun.run_v2_run_id)
        if oos_id in seen_runs:
            continue
        seen_runs.add(oos_id)
        verdict_row = db.scalars(
            select(CecchinoRunV2PatternValidation).where(
                CecchinoRunV2PatternValidation.validation_run_id == vrun.id,
                CecchinoRunV2PatternValidation.candidate_id == candidate.id,
            )
        ).first()
        oos_rows = _rows_for(
            db, candidate, run_v2_run_id=oos_id, binners=binners, odds_mode=insight_run.odds_mode
        )
        seasons.append(
            {
                "role": "validation",
                "season_label": vrun.season_label,
                "run_v2_run_id": oos_id,
                "verdict": verdict_row.verdict if verdict_row else None,
                "tier_json": verdict_row.tier_json if verdict_row else None,
                "null_confirm_prob": (
                    float(verdict_row.null_confirm_prob)
                    if verdict_row and verdict_row.null_confirm_prob is not None
                    else None
                ),
                **_season_block(
                    oos_rows,
                    combo,
                    is_market=is_market,
                    baseline=_baseline(oos_rows),
                    max_matches=max_matches,
                ),
            }
        )

    discovery = seasons[0]
    return {
        "candidate": {
            "id": int(candidate.id),
            "target_type": candidate.target_type,
            "target_key": candidate.target_key,
            "target_label": candidate.target_label,
            "threshold": float(candidate.threshold) if candidate.threshold is not None else None,
            "filters_text_human": candidate.filters_text_human,
            "refined_from_text": candidate.refined_from_text,
            "baseline_win_rate_pct": discovery["baseline_win_rate_pct"],
        },
        "overall": discovery["overall"],
        "by_competition": discovery["by_competition"],
        "concentration": discovery["concentration"],
        "matches": discovery["matches"],
        "matches_total": discovery["matches_total"],
        "matches_truncated": discovery["matches_truncated"],
        "seasons": seasons,
    }
