"""Bet Builder V3: le giocate consigliate da V2.5 e V3, lette dal registro live (sola lettura).

Ogni modello lavora da solo: opportunita' = predizioni del suo Indice di Acquistabilita' (punteggio
>= 70); giocabile = quota Bet365 >= 1,50; pattern che confermano = pattern con quota (senza condizioni
sulla quota del bookmaker) accesi sullo stesso mercato. Combo = stesso mercato predetto da V2.5 e V3,
nessun pattern dei due modelli in contrasto. Stesse regole di Osservazione live.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.cecchino_live_prediction import CecchinoLivePrediction
from app.models.cecchino_today_fixture import CecchinoTodayFixture
from app.services.cecchino.cecchino_bet_builder_results import normalize_match_status
from app.services.cecchino_live.observation import group_active_patterns, markets_conflict
from app.services.cecchino_live.observation_models import (
    INDEX_MIN_SCORE,
    PLAYABLE_MIN_QUOTA,
    _annotated_patterns,
    _won,
    market_family,
)

# primo giorno con l'indice orchestratore registrato per V2.5 e V3
AVAILABLE_FROM = date(2026, 9, 16)
MODELS = ("V2.5", "V3")


def _clean_pattern_groups(db: Session, pred: CecchinoLivePrediction) -> dict[str, dict[str, Any]]:
    """Pattern con quota accesi (esclusi quelli con condizioni sulla quota del book), uno per mercato."""
    active = [
        p for p in _annotated_patterns(db, pred) if p.get("target_type") == "market" and not p.get("uses_book")
    ]
    return {str(g["target_key"]): g for g in group_active_patterns(active)}


def _pattern_relation(key: str, groups: dict[str, dict[str, Any]]) -> str:
    if key in groups:
        return "confermata"
    if any(markets_conflict(key, other) for other in groups):
        return "in_contrasto"
    if groups:
        return "altri_pattern"
    return "senza_pattern"


def _model_block(db: Session, pred: CecchinoLivePrediction) -> dict[str, Any]:
    groups = _clean_pattern_groups(db, pred)
    index = (pred.modules_json or {}).get("purchasability_index") or {}
    predictions: list[dict[str, Any]] = []
    if index.get("status") == "ok":
        for key, m in (index.get("markets") or {}).items():
            score = float(m.get("score") or 0.0)
            if score < INDEX_MIN_SCORE:
                continue
            quota = m.get("quota")
            g = groups.get(key)
            predictions.append(
                {
                    "market_key": key,
                    "family": market_family(key),
                    "score": round(score, 1),
                    "probability": m.get("probability"),
                    "base_rate": m.get("base_rate"),
                    "quota": quota,
                    "min_quota": m.get("min_quota"),
                    "playable": quota is not None and float(quota) >= PLAYABLE_MIN_QUOTA,
                    "pattern": _pattern_relation(key, groups),
                    "pattern_info": (
                        {
                            "patterns_count": int(g["patterns_count"]),
                            "hist_win_pct": g.get("hist_win_rate_pct"),
                            "hist_roi_pct": g.get("hist_roi_pct_best"),
                        }
                        if g
                        else None
                    ),
                    "won": _won(pred, key),
                }
            )
    predictions.sort(key=lambda p: -p["score"])
    return {
        "available": index.get("status") == "ok",
        "status": pred.status,
        "frozen_at": pred.frozen_at.isoformat() if pred.frozen_at else None,
        "predictions": predictions,
        "patterns": [
            {
                "market_key": key,
                "patterns_count": int(g["patterns_count"]),
                "hist_win_pct": g.get("hist_win_rate_pct"),
                "hist_roi_pct": g.get("hist_roi_pct_best"),
                "quota": g.get("quota_book"),
                "won": _won(pred, key),
            }
            for key, g in groups.items()
        ],
        "_groups": groups,
    }


def _combo(v25: dict[str, Any] | None, v3: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Stesso mercato predetto da entrambi (70+), nessun pattern dei due modelli in contrasto."""
    if not v25 or not v3:
        return []
    by_v3 = {p["market_key"]: p for p in v3["predictions"]}
    patterns = set(v25["_groups"]) | set(v3["_groups"])
    out = []
    for a in v25["predictions"]:
        b = by_v3.get(a["market_key"])
        if b is None:
            continue
        key = a["market_key"]
        if any(markets_conflict(key, other) for other in patterns):
            continue
        quota = b["quota"] if b["quota"] is not None else a["quota"]
        won = b["won"] if b["won"] is not None else a["won"]
        mins = [x for x in (a["min_quota"], b["min_quota"]) if x is not None]
        out.append(
            {
                "market_key": key,
                "family": a["family"],
                "score": round(min(a["score"], b["score"]), 1),
                "score_v25": a["score"],
                "score_v3": b["score"],
                "quota": quota,
                "min_quota": max(mins) if mins else None,
                "playable": quota is not None and float(quota) >= PLAYABLE_MIN_QUOTA,
                "pattern_v25": a["pattern"],
                "pattern_v3": b["pattern"],
                "won": won,
            }
        )
    out.sort(key=lambda p: -p["score"])
    return out


def _fixture_block(today: CecchinoTodayFixture | None, pred: CecchinoLivePrediction) -> dict[str, Any]:
    return {
        "today_fixture_id": int(pred.today_fixture_id),
        "scan_date": pred.scan_date.isoformat(),
        "kickoff": pred.kickoff.isoformat() if pred.kickoff else None,
        "country": pred.country_name,
        "league": pred.league_name,
        "home": {"name": pred.home_team_name, "logo": getattr(today, "home_team_logo_url", None)},
        "away": {"name": pred.away_team_name, "logo": getattr(today, "away_team_logo_url", None)},
        "match_status": normalize_match_status(today) if today is not None else "unknown",
        "score": (
            {"home": today.goals_home, "away": today.goals_away}
            if today is not None and today.goals_home is not None and today.goals_away is not None
            else None
        ),
    }


def bet_builder_v3(db: Session, *, date_from: date, date_to: date) -> dict[str, Any]:
    date_from = max(date_from, AVAILABLE_FROM)
    date_to = max(date_to, date_from)
    rows = db.scalars(
        select(CecchinoLivePrediction).where(
            CecchinoLivePrediction.scan_date >= date_from,
            CecchinoLivePrediction.scan_date <= date_to,
            CecchinoLivePrediction.model.in_(MODELS),
        )
    ).all()
    by_fixture: dict[int, dict[str, CecchinoLivePrediction]] = defaultdict(dict)
    for r in rows:
        by_fixture[int(r.today_fixture_id)][r.model] = r
    todays = {
        int(t.id): t
        for t in db.scalars(select(CecchinoTodayFixture).where(CecchinoTodayFixture.id.in_(list(by_fixture)))).all()
    } if by_fixture else {}

    fixtures = []
    for fid, preds in by_fixture.items():
        blocks = {model: _model_block(db, pred) for model, pred in preds.items()}
        any_pred = next(iter(preds.values()))
        combo = _combo(blocks.get("V2.5"), blocks.get("V3"))
        for b in blocks.values():
            b.pop("_groups", None)
        fixtures.append(
            {
                "fixture": _fixture_block(todays.get(fid), any_pred),
                "models": {model: blocks.get(model) for model in MODELS},
                "combo": combo,
            }
        )
    fixtures.sort(key=lambda f: (f["fixture"]["kickoff"] or "", f["fixture"]["today_fixture_id"]))
    return {
        "date_from": date_from.isoformat(),
        "date_to": date_to.isoformat(),
        "available_from": AVAILABLE_FROM.isoformat(),
        "thresholds": {"index_min_score": INDEX_MIN_SCORE, "playable_min_quota": PLAYABLE_MIN_QUOTA},
        "fixtures": fixtures,
    }
