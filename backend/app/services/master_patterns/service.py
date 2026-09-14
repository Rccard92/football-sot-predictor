"""Master Pattern: calcolo dei pattern vincenti 4/4 per modello e lettura per la pagina."""

from __future__ import annotations

import logging
import threading
import traceback
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import func, insert, select
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models.cecchino_master_pattern import (
    MASTER_ACTIVE_STATUSES,
    MASTER_STATUS_COMPLETED,
    MASTER_STATUS_FAILED,
    MASTER_STATUS_PENDING,
    MASTER_STATUS_RUNNING,
    CecchinoMasterPattern,
    CecchinoMasterPatternBuild,
)
from app.services.cecchino_data_lab.errors import CecchinoLabImportError
from app.services.cecchino_data_lab.revision_resolve import revision_as_source_fields
from app.services.master_patterns.constants import (
    ALL_SEASONS,
    BUILDABLE_MODELS,
    DISCOVERY_SEASON,
    MASTER_ENGINE_VERSION,
    MIN_SAMPLE,
    MODEL_V2,
    MODEL_V25,
    MODEL_V3,
    MODELS,
    SYNTHETIC_CONFIRM_DEVIATION_PCT,
    TARGET_MARKET,
    TARGET_SYNTHETIC,
    VERIFY_SEASONS,
)
from app.services.master_patterns.orientation import orient_season
from app.services.master_patterns.scoring import chance_probability, is_winner, tally, totals

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_active_threads: dict[int, threading.Thread] = {}
_INSERT_CHUNK = 1000


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _dec(v: float | None, places: int) -> Decimal | None:
    return Decimal(str(round(float(v), places))) if v is not None else None


def build_to_dict(build: CecchinoMasterPatternBuild) -> dict[str, Any]:
    return {
        "id": int(build.id),
        "model": build.model,
        "status": build.status,
        "requested_at": build.requested_at.isoformat() if build.requested_at else None,
        "completed_at": build.completed_at.isoformat() if build.completed_at else None,
        "current_step": build.current_step,
        "summary": build.summary_json,
        "error": build.error_json,
    }


def start_build(db: Session, model: str, *, spawn: bool = True) -> dict[str, Any]:
    if model not in BUILDABLE_MODELS:
        raise CecchinoLabImportError("invalid_model", f"Modello non calcolabile: {model}", status_code=400)
    active = db.scalars(
        select(CecchinoMasterPatternBuild).where(CecchinoMasterPatternBuild.status.in_(MASTER_ACTIVE_STATUSES))
    ).first()
    if active:
        raise CecchinoLabImportError(
            "duplicate_active_run", f"Calcolo Master Pattern gia' in corso (id={active.id})", status_code=409
        )
    build = CecchinoMasterPatternBuild(
        model=model,
        engine_version=MASTER_ENGINE_VERSION,
        status=MASTER_STATUS_PENDING,
        requested_at=_utcnow(),
        source_git_commit=revision_as_source_fields().get("source_git_commit"),
    )
    db.add(build)
    db.commit()
    db.refresh(build)
    if not spawn:
        _execute(int(build.id))
        db.refresh(build)
        return build_to_dict(build)
    with _lock:
        t = threading.Thread(target=_execute, args=(int(build.id),), name=f"master-pattern-{build.id}", daemon=True)
        _active_threads[int(build.id)] = t
        t.start()
    return build_to_dict(build)


def _latest_completed(db: Session, model: str) -> CecchinoMasterPatternBuild | None:
    return db.scalars(
        select(CecchinoMasterPatternBuild)
        .where(CecchinoMasterPatternBuild.model == model, CecchinoMasterPatternBuild.status == MASTER_STATUS_COMPLETED)
        .order_by(CecchinoMasterPatternBuild.completed_at.desc())
    ).first()


def overview(db: Session) -> dict[str, Any]:
    out = []
    for model in MODELS:
        latest = db.scalars(
            select(CecchinoMasterPatternBuild)
            .where(CecchinoMasterPatternBuild.model == model)
            .order_by(CecchinoMasterPatternBuild.id.desc())
        ).first()
        completed = _latest_completed(db, model)
        out.append(
            {
                "model": model,
                "available": model in BUILDABLE_MODELS,
                "latest": build_to_dict(latest) if latest else None,
                "completed": build_to_dict(completed) if completed else None,
            }
        )
    return {
        "models": out,
        "rules": {
            "discovery_season": DISCOVERY_SEASON,
            "verify_seasons": list(VERIFY_SEASONS),
            "min_sample": MIN_SAMPLE,
            "synthetic_confirm_deviation_pct": SYNTHETIC_CONFIRM_DEVIATION_PCT,
        },
    }


# --- calcolo -------------------------------------------------------------------------------


def _record(build_id: int, engine_version: str, p: dict[str, Any]) -> dict[str, Any]:
    t = totals(p["seasons"], p["target_type"])
    return {
        "build_id": build_id,
        "model": p["model"],
        "engine_version": engine_version,
        "source_ref": str(p["source_ref"]),
        "target_type": p["target_type"],
        "target_key": p["target_key"],
        "target_label": p["target_label"],
        "threshold": _dec(p["threshold"], 2),
        "direction": int(p["direction"]),
        "market_label": p["market_label"],
        "conditions_json": p["conditions"],
        "conditions_text": p["conditions_text"],
        "seasons_json": p["seasons"],
        "total_n": t["n"],
        "total_wins": t["wins"],
        "win_rate_pct": _dec(t["win_rate_pct"], 2),
        "profit_units": _dec(t.get("profit_units"), 2),
        "roi_pct": _dec(t.get("roi_pct"), 2),
        "avg_quota": _dec(t.get("avg_quota"), 3),
        "avg_deviation_pct": _dec(t.get("avg_deviation_pct"), 2),
        "chance_p": _dec(chance_probability(p["seasons"]), 8),
    }


def _set_step(db: Session, build_id: int, step: str) -> None:
    build = db.get(CecchinoMasterPatternBuild, build_id)
    if build is not None:
        build.current_step = step[:128]
        db.commit()


def summarize_patterns(patterns: list[dict[str, Any]]) -> dict[str, Any]:
    by_type = {}
    for target_type in (TARGET_MARKET, TARGET_SYNTHETIC):
        group = [p for p in patterns if p["target_type"] == target_type]
        by_type[target_type] = {"patterns": len(group), **tally(group)}
    return by_type


def _execute(build_id: int) -> None:
    db = SessionLocal()
    try:
        build = db.get(CecchinoMasterPatternBuild, build_id)
        if build is None:
            return
        model = build.model
        build.status = MASTER_STATUS_RUNNING
        build.started_at = _utcnow()
        db.commit()
        try:
            summary: dict[str, Any] = {}
            if model in (MODEL_V2, MODEL_V25):
                from app.services.master_patterns.v2_source import load_v2_patterns

                _set_step(db, build_id, f"Lettura pattern e verifiche {model}")
                patterns, source = load_v2_patterns(db, model)
                if source.get("missing_seasons") or source.get("error"):
                    raise RuntimeError(f"Sorgente {model} incompleta: {source}")
                engine_version = source["engine_version"]
            else:
                from app.services.master_patterns.v3_source import (
                    _matches,
                    build_v3_market_patterns,
                    build_v3_synthetic_patterns,
                    v3_source,
                )

                source = v3_source(db)
                if source is None:
                    raise RuntimeError("Sorgente V3 incompleta: servono calcolo finale, indici e ricerca pattern")
                matches = _matches(db)
                _set_step(db, build_id, "V3 mercati con quota: statistiche sulle 5 stagioni")
                market = build_v3_market_patterns(db, source, matches)
                _set_step(db, build_id, "V3 mercati senza quota: ricerca e verifica")
                synthetic, synthetic_edges = build_v3_synthetic_patterns(db, source, matches)
                patterns = market + synthetic
                summary["synthetic_edges"] = synthetic_edges
                engine_version = source["engine_version"]

            summary["source"] = source
            summary["tally"] = summarize_patterns(patterns)
            winners = [p for p in patterns if is_winner(p["seasons"])]
            summary["winners"] = len(winners)

            _set_step(db, build_id, "Salvataggio pattern vincenti")
            records = [_record(build_id, engine_version, p) for p in winners]
            for start in range(0, len(records), _INSERT_CHUNK):
                db.execute(insert(CecchinoMasterPattern), records[start : start + _INSERT_CHUNK])
                db.commit()

            build = db.get(CecchinoMasterPatternBuild, build_id)
            build.summary_json = summary
            build.status = MASTER_STATUS_COMPLETED
            build.current_step = None
            build.completed_at = _utcnow()
            db.commit()
        except Exception as exc:  # noqa: BLE001
            db.rollback()
            build = db.get(CecchinoMasterPatternBuild, build_id)
            if build:
                build.status = MASTER_STATUS_FAILED
                build.completed_at = _utcnow()
                build.error_json = {"message": str(exc), "traceback": traceback.format_exc()}
                db.commit()
            logger.exception("master pattern build %s failed", build_id)
    finally:
        db.close()
        with _lock:
            _active_threads.pop(build_id, None)


# --- lettura -------------------------------------------------------------------------------


def pattern_to_dict(p: CecchinoMasterPattern) -> dict[str, Any]:
    return {
        "id": int(p.id),
        "model": p.model,
        "engine_version": p.engine_version,
        "target_type": p.target_type,
        "target_key": p.target_key,
        "target_label": p.target_label,
        "threshold": float(p.threshold) if p.threshold is not None else None,
        "direction": p.direction,
        "market_label": p.market_label,
        "conditions": p.conditions_json,
        "conditions_text": p.conditions_text,
        "seasons": p.seasons_json,
        "total_n": p.total_n,
        "total_wins": p.total_wins,
        "total_losses": p.total_n - p.total_wins,
        "win_rate_pct": float(p.win_rate_pct) if p.win_rate_pct is not None else None,
        "profit_units": float(p.profit_units) if p.profit_units is not None else None,
        "roi_pct": float(p.roi_pct) if p.roi_pct is not None else None,
        "avg_quota": float(p.avg_quota) if p.avg_quota is not None else None,
        "avg_deviation_pct": float(p.avg_deviation_pct) if p.avg_deviation_pct is not None else None,
    }


_SORTS = {
    "profit": (CecchinoMasterPattern.profit_units.desc().nulls_last(),),
    "roi": (CecchinoMasterPattern.roi_pct.desc().nulls_last(),),
    "partite": (CecchinoMasterPattern.total_n.desc(),),
    "frequenza": (CecchinoMasterPattern.win_rate_pct.desc().nulls_last(),),
    "scostamento": (CecchinoMasterPattern.avg_deviation_pct.desc().nulls_last(),),
}


def list_patterns(
    db: Session,
    *,
    model: str,
    target_type: str,
    market: str | None,
    min_matches: int | None,
    min_quota: float | None,
    max_quota: float | None,
    sort: str,
    limit: int,
    offset: int,
) -> dict[str, Any]:
    build = _latest_completed(db, model)
    if build is None:
        return {"build": None, "total": 0, "items": [], "markets": []}
    mp = CecchinoMasterPattern
    base = [mp.build_id == build.id, mp.target_type == target_type]
    market_column = mp.market_label if target_type == TARGET_SYNTHETIC else mp.target_key
    markets = db.execute(
        select(market_column, func.count(mp.id)).where(*base).group_by(market_column).order_by(market_column)
    ).all()
    filters = list(base)
    if market:
        filters.append(market_column == market)
    if min_matches:
        filters.append(mp.total_n >= min_matches)
    if min_quota is not None:
        filters.append(mp.avg_quota >= min_quota)
    if max_quota is not None:
        filters.append(mp.avg_quota <= max_quota)
    total = int(db.scalar(select(func.count(mp.id)).where(*filters)) or 0)
    order = _SORTS.get(sort) or _SORTS["profit" if target_type == TARGET_MARKET else "scostamento"]
    rows = db.scalars(select(mp).where(*filters).order_by(*order, mp.id).limit(limit).offset(offset)).all()
    return {
        "build": build_to_dict(build),
        "total": total,
        "items": [pattern_to_dict(r) for r in rows],
        "markets": [{"key": k, "count": int(c)} for k, c in markets],
    }


def _v2_detail(db: Session, pattern: CecchinoMasterPattern) -> list[dict[str, Any]]:
    from app.services.cecchino_data_lab.run_v2_pattern_insight_detail import get_candidate_detail

    detail = get_candidate_detail(db, int(pattern.source_ref), max_matches=400)
    direction = int(pattern.direction)
    is_market = pattern.target_type == TARGET_MARKET
    blocks = []
    for season in detail["seasons"]:
        label = season.get("season_label")
        if label not in ALL_SEASONS:
            continue
        overall = dict(season["overall"])
        overall["baseline_win_rate_pct"] = season.get("baseline_win_rate_pct")
        if overall.get("win_rate_pct") is not None and overall.get("baseline_win_rate_pct") is not None:
            overall["deviation_pct"] = round(overall["win_rate_pct"] - overall["baseline_win_rate_pct"], 2)
        leagues = [dict(l) for l in season["by_competition"]]
        matches = []
        for m in season["matches"]:
            won = bool(m["won"]) if m["won"] is not None else None
            if not is_market and direction < 0 and won is not None:
                won = not won
            matches.append(
                {
                    "season_label": label,
                    "lab_match_id": m["lab_match_id"],
                    "match_date": (m["kickoff_at"] or "")[:10],
                    "competition": m["competition"],
                    "home_team": m["home_team"],
                    "away_team": m["away_team"],
                    "won": won,
                    "quota": m.get("quota_book"),
                    "profit": m.get("profit_1u"),
                    "actual_value": m.get("actual_value"),
                }
            )
        if not is_market:
            overall = orient_season(overall, direction)
            leagues = [orient_season(l, direction) for l in leagues]
        blocks.append(
            {
                "season_label": label,
                "role": season["role"],
                "verdict": (pattern.seasons_json.get(label) or {}).get("verdict"),
                "overall": overall,
                "by_competition": leagues,
                "matches": matches,
                "matches_total": season["matches_total"],
            }
        )
    blocks.sort(key=lambda b: b["season_label"])
    return blocks


def pattern_detail(db: Session, pattern_id: int) -> dict[str, Any]:
    pattern = db.get(CecchinoMasterPattern, pattern_id)
    if pattern is None:
        raise CecchinoLabImportError("pattern_not_found", "Pattern non trovato", status_code=404)
    build = db.get(CecchinoMasterPatternBuild, int(pattern.build_id))
    if pattern.model in (MODEL_V2, MODEL_V25):
        seasons = _v2_detail(db, pattern)
    elif pattern.model == MODEL_V3:
        from app.services.master_patterns.v3_source import v3_detail

        seasons = v3_detail(db, pattern_to_dict(pattern), build.summary_json or {})
    else:
        seasons = []
    return {"pattern": pattern_to_dict(pattern), "seasons": seasons}
