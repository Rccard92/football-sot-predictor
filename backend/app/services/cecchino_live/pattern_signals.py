"""Segnali dei pattern Master sulle partite live.

Un pattern si accende su una partita solo se TUTTE le sue condizioni sono verificabili con i
dati pre-partita e tutte valgono. Se manca un dato (es. statistiche squadra non disponibili per
quella competizione) il pattern resta "non verificabile": non viene mai acceso per ipotesi.
"""

from __future__ import annotations

import logging
import threading
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.cecchino_master_pattern import (
    MASTER_STATUS_COMPLETED,
    CecchinoMasterPattern,
    CecchinoMasterPatternBuild,
)
from app.services.cecchino_data_lab.run_v2_grid_vocabulary import SIGNAL_ACTIVE_COLUMN

logger = logging.getLogger(__name__)

_cache: dict[str, tuple[int, list[dict[str, Any]], int | None]] = {}
_lock = threading.Lock()


def _f(v: Any) -> float | None:
    return float(v) if v is not None else None


def load_winners(db: Session, model: str) -> tuple[int | None, list[dict[str, Any]], int | None]:
    """(id build, pattern vincenti, RUN della stagione di scoperta) dell'ultimo calcolo completato."""
    build = db.scalars(
        select(CecchinoMasterPatternBuild)
        .where(CecchinoMasterPatternBuild.model == model, CecchinoMasterPatternBuild.status == MASTER_STATUS_COMPLETED)
        .order_by(CecchinoMasterPatternBuild.completed_at.desc())
    ).first()
    if build is None:
        return None, [], None
    with _lock:
        cached = _cache.get(model)
        if cached is not None and cached[0] == int(build.id):
            return cached
    source = (build.summary_json or {}).get("source") or {}
    discovery_run = source.get("discovery_run_v2_run_id")
    patterns = [
        {
            "id": int(p.id),
            "target_type": p.target_type,
            "target_key": p.target_key,
            "threshold": _f(p.threshold),
            "direction": int(p.direction),
            "market_label": p.market_label,
            "conditions": list(p.conditions_json or []),
            "conditions_text": p.conditions_text,
            "total_n": int(p.total_n),
            "win_rate_pct": _f(p.win_rate_pct),
            "roi_pct": _f(p.roi_pct),
            "avg_quota": _f(p.avg_quota),
            "avg_deviation_pct": _f(p.avg_deviation_pct),
        }
        for p in db.scalars(select(CecchinoMasterPattern).where(CecchinoMasterPattern.build_id == build.id)).all()
    ]
    entry = (int(build.id), patterns, int(discovery_run) if discovery_run else None)
    with _lock:
        _cache[model] = entry
    return entry


def warm_winners_cache(models: tuple[str, ...] = ("V2", "V2.5", "V3")) -> None:
    """Carica in anticipo i pattern vincenti (stessa cache di load_winners), senza scrivere nulla."""
    from app.core.database import SessionLocal

    db = SessionLocal()
    try:
        for model in models:
            try:
                load_winners(db, model)
            except Exception:  # noqa: BLE001
                logger.exception("precaricamento pattern %s non riuscito", model)
                db.rollback()
    finally:
        db.rollback()
        db.close()


def _holds(
    condition: dict[str, Any],
    *,
    pattern: dict[str, Any],
    features: dict[str, str | None],
    markets: dict[str, dict[str, Any]],
) -> bool | None:
    column, value = str(condition["column"]), str(condition["value"])
    market = markets.get(pattern["target_key"]) if pattern["target_type"] == "market" else None
    if column == SIGNAL_ACTIVE_COLUMN:
        if market is None:
            return False
        return bool(market.get("signal_active"))
    if column == "purchasability_class":
        cls = (market or {}).get("buyability_class")
        return None if cls is None else cls == value
    actual = features.get(column)
    return None if actual is None else actual == value


def evaluate_patterns(
    patterns: list[dict[str, Any]],
    *,
    features: dict[str, str | None],
    markets: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    active: list[dict[str, Any]] = []
    unverifiable = 0
    for p in patterns:
        results = [_holds(c, pattern=p, features=features, markets=markets) for c in p["conditions"]]
        if any(r is False for r in results):
            continue
        if any(r is None for r in results):
            unverifiable += 1
            continue
        market = markets.get(p["target_key"]) if p["target_type"] == "market" else None
        active.append(
            {
                **{k: p[k] for k in ("id", "target_type", "target_key", "threshold", "direction", "market_label",
                                     "conditions_text", "total_n", "win_rate_pct", "roi_pct", "avg_quota",
                                     "avg_deviation_pct")},
                "quota_book": (market or {}).get("quota_book"),
            }
        )
    active.sort(key=lambda a: (a["target_type"] != "market", -(a["roi_pct"] or a["avg_deviation_pct"] or 0)))
    return {"active": active, "active_count": len(active), "unverifiable_count": unverifiable, "patterns_total": len(patterns)}


def v25_features(modules: dict[str, Any], delta: dict[str, str | None]) -> dict[str, str | None]:
    """Colonne della ricerca pattern dai moduli V2.5 congelati."""
    gi = modules.get("goal_intensity_classes") or {}
    bal = modules.get("balance_classes") or {}
    return {
        "goal_offensive_production_class": gi.get("offensive_production"),
        "goal_defensive_solidity_class": gi.get("defensive_solidity"),
        "goal_match_tempo_class": gi.get("match_tempo"),
        "goal_offensive_stability_class": gi.get("offensive_stability"),
        "goal_final_class": modules.get("goal_intensity_final"),
        "balance_f36_class": bal.get("f36"),
        "balance_dominance_class": bal.get("dominance"),
        "balance_draw_credibility_class": bal.get("draw_credibility"),
        "balance_gap_coherence_class": bal.get("gap_coherence"),
        **delta,
    }


# Condizioni che usano la quota del bookmaker invece dei soli moduli: la classe di acquistabilita'
# (costruita sul confronto con il book), la distanza V3 dal book e la fascia di quota. Nella V2 anche
# la geometria F36 dell'Equilibrio, corretta con la quota X del book.
BOOK_CONDITION_COLUMNS: dict[str, frozenset[str]] = {
    "V2": frozenset({"purchasability_class", "balance_f36_class"}),
    "V2.5": frozenset({"purchasability_class"}),
    "V3": frozenset({"purchasability_class", "v3_vs_book", "quota"}),
}


def annotate_book_conditions(db: Session, model: str, patterns: dict[str, Any] | None) -> None:
    """Segna sui pattern accesi (anche registrati prima di questo campo) se una condizione usa la quota del book."""
    active = (patterns or {}).get("active")
    columns = BOOK_CONDITION_COLUMNS.get(model)
    if not active or not columns:
        return
    _, winners, _ = load_winners(db, model)
    by_id = {int(p["id"]): p for p in winners}
    for p in active:
        winner = by_id.get(int(p.get("id") or 0))
        if winner is not None:
            p["uses_book"] = any(str(c.get("column")) in columns for c in winner["conditions"])
