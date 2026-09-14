"""Pattern V2 per la Master Pattern: letti dalle verifiche Pattern Insights gia' salvate
(analisi a quota di chiusura, scoperta 2021/22, verifiche 2022/23-2025/26)."""

from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services.master_patterns.constants import (
    DISCOVERY_SEASON,
    MARKET_LABELS,
    MIN_SAMPLE,
    MODEL_V2,
    TARGET_MARKET,
    VERIFY_SEASONS,
)
from app.services.master_patterns.orientation import orient_season, synthetic_market_label


def _f(v: Any) -> float | None:
    return float(v) if v is not None else None


def latest_closing_insight(db: Session) -> dict[str, Any] | None:
    row = db.execute(
        text(
            """
            SELECT i.id, i.run_v2_run_id, i.engine_version
            FROM cecchino_run_v2_pattern_insight_runs i
            WHERE i.status = 'completed' AND i.odds_mode = 'closing'
            ORDER BY i.completed_at DESC LIMIT 1
            """
        )
    ).first()
    return dict(row._mapping) if row else None


def validation_runs(db: Session, insight_run_id: int) -> dict[str, int]:
    return {
        r.season_label: int(r.id)
        for r in db.execute(
            text(
                """
                SELECT DISTINCT ON (season_label) id, season_label
                FROM cecchino_run_v2_pattern_validation_runs
                WHERE insight_run_id = :iid AND status = 'completed'
                ORDER BY season_label, completed_at DESC
                """
            ),
            {"iid": insight_run_id},
        )
    }


def _season_stats(r: dict[str, Any], verdict: str | None, null_p: float | None) -> dict[str, Any]:
    return {
        "n": int(r["n"]),
        "wins": int(r["wins"]),
        "losses": int(r["losses"]),
        "win_rate_pct": _f(r["win_rate_pct"]),
        "roi_pct": _f(r["roi_pct"]),
        "profit_units": _f(r["profit_units"]),
        "n_priced": int(r["n_priced"]) if r.get("n_priced") is not None else None,
        "avg_quota": _f(r["avg_quota"]),
        "baseline_win_rate_pct": _f(r["baseline_win_rate_pct"]),
        "deviation_pct": _f(r["deviation_pct"]),
        "verdict": verdict,
        "null_p": null_p,
    }


def load_v2_patterns(db: Session) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Tutti i pattern V2 (con le stagioni), piu' i riferimenti della sorgente."""
    insight = latest_closing_insight(db)
    if insight is None:
        return [], {"error": "Nessuna analisi Pattern Insights a quota di chiusura"}
    runs = validation_runs(db, int(insight["id"]))
    missing = [s for s in VERIFY_SEASONS if s not in runs]
    source = {
        "insight_run_id": int(insight["id"]),
        "discovery_run_v2_run_id": int(insight["run_v2_run_id"]),
        "validation_run_ids": runs,
        "missing_seasons": missing,
        "engine_version": f"run_v2|pattern_insight_{insight['engine_version']}",
    }
    if missing:
        return [], source

    run_to_season = {v: k for k, v in runs.items() if k in VERIFY_SEASONS}
    candidates: dict[int, dict[str, Any]] = {}
    for r in db.execute(
        text(
            """
            SELECT id, target_type, target_key, target_label, threshold, filters_json, filters_text_human,
                   n, wins, losses, win_rate_pct, roi_pct, profit_units, n_priced, avg_quota,
                   baseline_win_rate_pct, deviation_pct
            FROM cecchino_run_v2_pattern_insight_candidates
            WHERE insight_run_id = :iid AND n >= :min_n
            """
        ),
        {"iid": int(insight["id"]), "min_n": MIN_SAMPLE},
    ):
        d = dict(r._mapping)
        is_market = d["target_type"] == TARGET_MARKET
        direction = 1 if is_market or (d["deviation_pct"] or 0) >= 0 else -1
        threshold = _f(d["threshold"])
        discovery = _season_stats(d, "discovery", None)
        candidates[int(d["id"])] = {
            "model": MODEL_V2,
            "source_ref": int(d["id"]),
            "target_type": d["target_type"],
            "target_key": d["target_key"],
            "target_label": d["target_label"],
            "threshold": threshold,
            "direction": direction,
            "market_label": (
                MARKET_LABELS.get(d["target_key"], d["target_label"])
                if is_market
                else synthetic_market_label(d["target_label"], threshold, direction)
            ),
            "conditions": list(d["filters_json"] or []),
            "conditions_text": d["filters_text_human"],
            "seasons": {DISCOVERY_SEASON: discovery if is_market else orient_season(discovery, direction)},
        }

    for r in db.execute(
        text(
            """
            SELECT candidate_id, validation_run_id, n, wins, losses, win_rate_pct, roi_pct, profit_units,
                   n_priced, avg_quota, baseline_win_rate_pct, deviation_pct, verdict, null_confirm_prob
            FROM cecchino_run_v2_pattern_validations
            WHERE validation_run_id = ANY(:ids)
            """
        ),
        {"ids": list(run_to_season)},
    ):
        d = dict(r._mapping)
        pattern = candidates.get(int(d["candidate_id"]))
        if pattern is None:
            continue
        stats = _season_stats(d, d["verdict"], _f(d["null_confirm_prob"]))
        if pattern["target_type"] != TARGET_MARKET:
            stats = orient_season(stats, pattern["direction"])
        pattern["seasons"][run_to_season[int(d["validation_run_id"])]] = stats
    return list(candidates.values()), source
