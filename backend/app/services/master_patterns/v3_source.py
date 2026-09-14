"""Pattern V3 per la Master Pattern.

- Mercati con quota: i pattern gia' scoperti dalla ricerca V3 (protocollo V2),
  con le statistiche complete ricalcolate su tutte e 5 le stagioni.
- Mercati senza quota: ricerca V3 nuova con le stesse regole della V2.
Previsioni dal calcolo V3 esteso al 2025/26 (identico al modello di riferimento
sulle stagioni precedenti), condizioni dagli indici dello stesso calcolo.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from typing import Any

import numpy as np
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.models.cecchino_v3 import V3_STATUS_COMPLETED, CecchinoV3Pattern, CecchinoV3PatternRun
from app.services.cecchino_data_lab.run_v2_scope import tier_of
from app.services.cecchino_v3.data import MatchRecord, load_matches
from app.services.cecchino_v3.evaluator import MarketRow
from app.services.cecchino_v3.market_data import load_market_rows
from app.services.cecchino_v3.pattern_service import _index_run_for, load_contexts
from app.services.cecchino_v3.patterns import PATTERN_COLUMNS, MarketMatrix, MatchContext, NullModel, build_matrices
from app.services.cecchino_v3.runs import final_model_run, reference_model_run
from app.services.cecchino_v3.synthetic_patterns import (
    StatMatrix,
    SyntheticRow,
    build_stat_matrix,
    discover_synthetic,
    synthetic_edges,
    validate_synthetic,
)
from app.services.master_patterns.constants import (
    ALL_SEASONS,
    DISCOVERY_SEASON,
    MARKET_LABELS,
    MODEL_V3,
    SYNTHETIC_CONFIRM_DEVIATION_PCT,
    SYNTHETIC_TARGETS,
    TARGET_MARKET,
    TARGET_SYNTHETIC,
    VERDICT_INSUFFICIENT,
    VERIFY_SEASONS,
)
from app.services.master_patterns.labels import condition_label, conditions_text
from app.services.master_patterns.orientation import orient_season, synthetic_market_label
from app.services.master_patterns.scoring import market_verdict

_ACTUAL_COLUMNS: dict[str, tuple[str, str]] = {
    "shots": ("home_shots", "away_shots"),
    "sot": ("home_shots_on_target", "away_shots_on_target"),
    "corners": ("home_corners", "away_corners"),
    "yellow_cards": ("home_yellow_cards", "away_yellow_cards"),
}


# --- sorgenti -------------------------------------------------------------------------------


def v3_source(db: Session) -> dict[str, Any] | None:
    final = final_model_run(db)
    reference = reference_model_run(db)
    if final is None or reference is None:
        return None
    index_run = _index_run_for(db, int(final.id))
    pattern_run = db.scalars(
        select(CecchinoV3PatternRun)
        .where(CecchinoV3PatternRun.status == V3_STATUS_COMPLETED, CecchinoV3PatternRun.source_run_id == reference.id)
        .order_by(CecchinoV3PatternRun.completed_at.desc())
    ).first()
    if index_run is None or pattern_run is None:
        return None
    return {
        "final_model_run_id": int(final.id),
        "reference_model_run_id": int(reference.id),
        "index_run_id": int(index_run.id),
        "pattern_run_id": int(pattern_run.id),
        "market_edges": (pattern_run.summary_json or {}).get("edges") or {},
        "engine_version": f"cecchino_v3|modello #{reference.id}|esteso #{final.id}|pattern #{pattern_run.id}",
    }


def _matches(db: Session) -> dict[int, MatchRecord]:
    return {m.lab_match_id: m for m in load_matches(db, include_lockbox=True)}


def load_synthetic_rows(db: Session, final_run_id: int, matches: dict[int, MatchRecord]) -> list[SyntheticRow]:
    cols = ", ".join(f"m.{c}" for pair in _ACTUAL_COLUMNS.values() for c in pair)
    out: list[SyntheticRow] = []
    for r in db.execute(
        text(
            f"""
            SELECT m.id, {cols},
                   (mp.specialists_json->'shots'->>'volume_home')::double precision AS shots_home,
                   (mp.specialists_json->'shots'->>'volume_away')::double precision AS shots_away,
                   (mp.specialists_json->'sot'->>'volume_home')::double precision AS sot_home,
                   (mp.specialists_json->'sot'->>'volume_away')::double precision AS sot_away
            FROM cecchino_lab_matches m
            JOIN cecchino_v3_match_predictions mp ON mp.lab_match_id = m.id AND mp.run_id = :run_id
            """
        ),
        {"run_id": final_run_id},
    ):
        d = dict(r._mapping)
        m = matches.get(int(d["id"]))
        if m is None:
            continue
        actuals: dict[str, float | None] = {}
        for stat, (home_col, away_col) in _ACTUAL_COLUMNS.items():
            home, away = d[home_col], d[away_col]
            actuals[f"home_{stat}"] = float(home) if home is not None else None
            actuals[f"away_{stat}"] = float(away) if away is not None else None
            actuals[f"total_{stat}"] = float(home + away) if home is not None and away is not None else None
        out.append(
            SyntheticRow(
                lab_match_id=m.lab_match_id,
                season_label=m.season_label,
                competition=m.competition,
                tier=tier_of(m.competition),
                match_date=m.match_date,
                phase=m.phase,
                eligible=m.eval_eligible,
                home_team=m.home_team,
                away_team=m.away_team,
                actuals=actuals,
                volumes={k: d[k] for k in ("shots_home", "shots_away", "sot_home", "sot_away")},
            )
        )
    out.sort(key=lambda r: (r.match_date, r.lab_match_id))
    return out


# --- statistiche per stagione (mercati con quota) -------------------------------------------


def _market_arrays(rows: Sequence[MarketRow], market: str) -> tuple[np.ndarray, list[MarketRow]]:
    kept = [r for r in rows if r.eligible and r.market_key == market]  # stesso ordine di build_matrices
    return np.array([r.odds for r in kept]), kept


def market_season_stats(
    matrix: MarketMatrix, odds: np.ndarray, combo: Sequence[tuple[int, int]], season: str, null: NullModel | None
) -> dict[str, Any]:
    mask = matrix.combo_mask(combo) & matrix.season_mask(season)
    n = int(mask.sum())
    profit = matrix.profit[mask]
    wins = int((profit > 0).sum())
    roi_pct = float(profit.mean() * 100.0) if n else None
    verdict = "discovery" if season == DISCOVERY_SEASON else market_verdict(n, roi_pct)
    null_p = (
        null.p_roi_positive(n) if null is not None and verdict not in ("discovery", VERDICT_INSUFFICIENT) else None
    )
    return {
        "n": n,
        "wins": wins,
        "losses": n - wins,
        "win_rate_pct": round(wins / n * 100.0, 3) if n else None,
        "roi_pct": round(roi_pct, 3) if roi_pct is not None else None,
        "profit_units": round(float(profit.sum()), 3) if n else None,
        "n_priced": n,
        "avg_quota": round(float(odds[mask].mean()), 3) if n else None,
        "verdict": verdict,
        "null_p": null_p,
    }


def _combo_from_conditions(matrix: MarketMatrix, conditions: Sequence[dict[str, str]]) -> tuple[tuple[int, int], ...]:
    combo = []
    for cond in conditions:
        c = PATTERN_COLUMNS.index(cond["column"])
        values = matrix.values[c]
        combo.append((c, values.index(cond["value"]) if cond["value"] in values else -2))
    return tuple(combo)


def _labelled(conditions: Sequence[dict[str, str]]) -> list[dict[str, str]]:
    return [{**c, "label": condition_label(c["column"], c["value"])} for c in conditions]


def build_v3_market_patterns(db: Session, source: dict[str, Any], matches: dict[int, MatchRecord]) -> list[dict[str, Any]]:
    rows = load_market_rows(db, source["final_model_run_id"], include_lockbox=True, matches=matches)
    contexts = load_contexts(db, source["index_run_id"])
    matrices = build_matrices(rows, contexts, source["market_edges"])
    stored = db.scalars(
        select(CecchinoV3Pattern).where(CecchinoV3Pattern.pattern_run_id == source["pattern_run_id"])
    ).all()
    by_market: dict[str, list[CecchinoV3Pattern]] = defaultdict(list)
    for rec in stored:
        by_market[rec.market_key].append(rec)

    out: list[dict[str, Any]] = []
    for market, records in sorted(by_market.items()):
        matrix = matrices.get(market)
        if matrix is None:
            continue
        odds, _ = _market_arrays(rows, market)
        nulls = {
            season: NullModel(matrix.profit[matrix.season_mask(season)], seed_offset=idx)
            for idx, season in enumerate(VERIFY_SEASONS)
        }
        for rec in records:
            combo = _combo_from_conditions(matrix, rec.conditions_json)
            seasons = {
                season: market_season_stats(matrix, odds, combo, season, nulls.get(season))
                for season in ALL_SEASONS
            }
            out.append(
                {
                    "model": MODEL_V3,
                    "source_ref": f"pattern:{rec.id}",
                    "target_type": TARGET_MARKET,
                    "target_key": market,
                    "target_label": MARKET_LABELS.get(market, market),
                    "threshold": None,
                    "direction": 1,
                    "market_label": MARKET_LABELS.get(market, market),
                    "conditions": _labelled(rec.conditions_json),
                    "conditions_text": conditions_text(rec.conditions_json),
                    "seasons": seasons,
                }
            )
    return out


def _synthetic_label(stat_key: str) -> str:
    return next(label for key, label, _ in SYNTHETIC_TARGETS if key == stat_key)


def build_v3_synthetic_patterns(
    db: Session, source: dict[str, Any], matches: dict[int, MatchRecord]
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows = load_synthetic_rows(db, source["final_model_run_id"], matches)
    contexts = load_contexts(db, source["index_run_id"])
    stat_keys = [key for key, _, _ in SYNTHETIC_TARGETS]
    edges = synthetic_edges(rows, contexts, stat_keys)
    out: list[dict[str, Any]] = []
    for key, label, thresholds in SYNTHETIC_TARGETS:
        matrix = build_stat_matrix(rows, contexts, key, edges)
        patterns = [p for threshold in thresholds for p in discover_synthetic(matrix, threshold)]
        validate_synthetic(matrix, patterns, VERIFY_SEASONS, SYNTHETIC_CONFIRM_DEVIATION_PCT)
        for p in patterns:
            out.append(
                {
                    "model": MODEL_V3,
                    "source_ref": f"synthetic:{key}:{p.threshold:g}:{'+'.join(f'{c}={v}' for c, v in p.combo)}",
                    "target_type": TARGET_SYNTHETIC,
                    "target_key": key,
                    "target_label": label,
                    "threshold": p.threshold,
                    "direction": p.direction,
                    "market_label": synthetic_market_label(label, p.threshold, p.direction),
                    "conditions": _labelled(p.conditions),
                    "conditions_text": conditions_text(p.conditions),
                    "seasons": {s: orient_season(stats, p.direction) for s, stats in p.seasons.items()},
                }
            )
    return out, edges


# --- dettaglio al clic -----------------------------------------------------------------------


def _group_stats(items: list[dict[str, Any]], is_market: bool) -> dict[str, Any]:
    n = len(items)
    wins = sum(1 for i in items if i["won"])
    out: dict[str, Any] = {"n": n, "wins": wins, "losses": n - wins, "win_rate_pct": round(wins / n * 100.0, 2) if n else None}
    if is_market and n:
        profit = sum(i["profit"] for i in items)
        out.update(
            {
                "profit_units": round(profit, 2),
                "roi_pct": round(profit / n * 100.0, 2),
                "avg_quota": round(sum(i["quota"] for i in items) / n, 3),
            }
        )
    return out


def _season_blocks(items: list[dict[str, Any]], stored_seasons: dict[str, Any], is_market: bool, max_matches: int) -> list[dict[str, Any]]:
    blocks = []
    for season in ALL_SEASONS:
        season_items = [i for i in items if i["season_label"] == season]
        by_comp: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for i in season_items:
            by_comp[i["competition"]].append(i)
        stored = stored_seasons.get(season, {})
        blocks.append(
            {
                "season_label": season,
                "role": "discovery" if season == DISCOVERY_SEASON else "validation",
                "verdict": stored.get("verdict"),
                "overall": {
                    **_group_stats(season_items, is_market),
                    "baseline_win_rate_pct": stored.get("baseline_win_rate_pct"),
                    "deviation_pct": stored.get("deviation_pct"),
                },
                "by_competition": sorted(
                    ({"competition": c, **_group_stats(v, is_market)} for c, v in by_comp.items()),
                    key=lambda x: -x["n"],
                ),
                "matches": season_items[:max_matches],
                "matches_total": len(season_items),
            }
        )
    return blocks


def v3_detail(db: Session, pattern: dict[str, Any], build_summary: dict[str, Any], *, max_matches: int = 400) -> list[dict[str, Any]]:
    source = build_summary["source"]
    matches = _matches(db)
    contexts: dict[int, MatchContext] = load_contexts(db, source["index_run_id"])
    items: list[dict[str, Any]] = []
    if pattern["target_type"] == TARGET_MARKET:
        rows = load_market_rows(
            db, source["final_model_run_id"], include_lockbox=True, market_keys=[pattern["target_key"]], matches=matches
        )
        matrix = build_matrices(rows, contexts, source["market_edges"]).get(pattern["target_key"])
        if matrix is None:
            return []
        _, kept = _market_arrays(rows, pattern["target_key"])
        mask = matrix.combo_mask(_combo_from_conditions(matrix, pattern["conditions"]))
        for idx in np.flatnonzero(mask):
            r = kept[idx]
            items.append(
                {
                    "season_label": r.season_label,
                    "lab_match_id": r.lab_match_id,
                    "match_date": r.match_date.isoformat(),
                    "competition": r.competition,
                    "home_team": r.home_team,
                    "away_team": r.away_team,
                    "won": r.won,
                    "quota": round(r.odds, 3),
                    "profit": round(r.odds - 1.0 if r.won else -1.0, 3),
                    "actual_value": None,
                }
            )
    else:
        rows = load_synthetic_rows(db, source["final_model_run_id"], matches)
        matrix: StatMatrix = build_stat_matrix(rows, contexts, pattern["target_key"], build_summary["synthetic_edges"])
        combo = matrix.combo_from_conditions(pattern["conditions"])
        mask = matrix.combo_mask(combo)
        threshold = float(pattern["threshold"])
        for idx in np.flatnonzero(mask):
            r = matrix.row_index[idx]
            value = float(r.actuals[pattern["target_key"]])
            over = value > threshold
            items.append(
                {
                    "season_label": r.season_label,
                    "lab_match_id": r.lab_match_id,
                    "match_date": r.match_date.isoformat(),
                    "competition": r.competition,
                    "home_team": r.home_team,
                    "away_team": r.away_team,
                    "won": over if int(pattern["direction"]) >= 0 else not over,
                    "quota": None,
                    "profit": None,
                    "actual_value": value,
                }
            )
    items.sort(key=lambda i: (i["match_date"], i["lab_match_id"]))
    return _season_blocks(items, pattern["seasons"], pattern["target_type"] == TARGET_MARKET, max_matches)
