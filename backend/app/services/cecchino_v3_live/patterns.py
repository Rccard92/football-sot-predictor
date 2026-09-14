"""Pattern Master V3 accesi sulle partite live (V3 estesa).

Stesse condizioni della ricerca V3 nel Lab, con le soglie salvate nella Master V3:
- quintili per mercato (probabilita' V3, V3 rispetto al book, quota, forma) dalla ricerca pattern;
- quintili dei volumi attesi (tiri, tiri in porta) dei pattern senza quota;
- classi degli indici V3 (equilibrio, pareggio, intensita' goal) dello stesso campionato;
- specialisti concordi sul segno, riposo, fase della stagione.

"Livello" (campionati top o minori) esiste solo per i 16 campionati del Lab: in live non e'
verificabile, quindi i pattern che lo usano restano non verificabili (mai accesi per ipotesi).
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.cecchino_master_pattern import MASTER_STATUS_COMPLETED, CecchinoMasterPatternBuild
from app.services.cecchino_live.pattern_signals import load_winners
from app.services.cecchino_v3.indices import IndexInput
from app.services.cecchino_v3.patterns import agents_value, quintile_value, rest_value
from app.services.cecchino_v3.reliability import sign_support
from app.services.cecchino_v3.synthetic_patterns import VOLUME_SOURCE

MODEL_V3 = "V3"


def _edges(db: Session, build_id: int) -> tuple[dict[str, Any], dict[str, Any]]:
    build = db.get(CecchinoMasterPatternBuild, int(build_id))
    summary = (build.summary_json or {}) if build is not None else {}
    market = ((summary.get("source") or {}).get("market_edges")) or {}
    synthetic = summary.get("synthetic_edges") or {}
    return market, synthetic


def _base_features(result: dict[str, Any]) -> dict[str, Any]:
    idx = result.get("indices") or {}
    probs = result.get("probabilities") or {}
    specialists = result.get("specialists") or {}
    forma = idx.get("forma") or {}
    home, away = forma.get("home") or {}, forma.get("away") or {}
    form_diff = (
        float(home["gioco"]) - float(away["gioco"])
        if home.get("gioco") is not None and away.get("gioco") is not None
        else None
    )
    agree = None
    if probs.get("HOME") is not None:
        support = sign_support(
            IndexInput(
                match=None,  # type: ignore[arg-type]
                prob_home=float(probs["HOME"]),
                prob_draw=float(probs["DRAW"]),
                prob_away=float(probs["AWAY"]),
                prob_over_2_5=float(probs.get("OVER_2_5") or 0.0),
                lambda_home=float(result.get("lambda_home") or 0.0),
                lambda_away=float(result.get("lambda_away") or 0.0),
                home_evidence=0.0,
                away_evidence=0.0,
                specialists=specialists,
                rho=float(result.get("rho") or 0.0),
            )
        )
        agree = support.get("agents_agree")
    rest_diff = (idx.get("calendario") or {}).get("rest_diff")
    return {
        "form_diff": form_diff,
        "categories": {
            "equilibrio": (idx.get("equilibrio") or {}).get("class"),
            "pareggio": (idx.get("pareggio") or {}).get("class"),
            "intensita_goal": (idx.get("intensita_goal") or {}).get("class"),
            "segno_agenti": agents_value(agree),
            "riposo": rest_value(rest_diff),
            "fase": "finale" if result.get("phase") == "final" else "stagione",
            "livello": None,
        },
        "volumes": {
            "shots_home": (specialists.get("shots") or {}).get("volume_home"),
            "shots_away": (specialists.get("shots") or {}).get("volume_away"),
            "sot_home": (specialists.get("sot") or {}).get("volume_home"),
            "sot_away": (specialists.get("sot") or {}).get("volume_away"),
        },
    }


def _volume(volumes: dict[str, Any], stat_key: str) -> float | None:
    source = VOLUME_SOURCE.get(stat_key)
    if source is None:
        return None
    stat, side = source
    home, away = volumes.get(f"{stat}_home"), volumes.get(f"{stat}_away")
    if side == "home":
        return home
    if side == "away":
        return away
    return home + away if home is not None and away is not None else None


def condition_values(
    pattern: dict[str, Any],
    base: dict[str, Any],
    markets: dict[str, dict[str, Any]],
    market_edges: dict[str, Any],
    synthetic_edges: dict[str, Any],
) -> dict[str, str | None]:
    values: dict[str, str | None] = dict(base["categories"])
    key = str(pattern["target_key"])
    if pattern["target_type"] == "market":
        m = markets.get(key) or {}
        e = market_edges.get(key) or {}
        p_v3, p_book, odds = m.get("probability"), m.get("prob_book_fair"), m.get("quota_book")
        values["prob_v3"] = quintile_value(p_v3, e.get("prob_v3") or [])
        values["v3_vs_book"] = (
            quintile_value(float(p_v3) - float(p_book), e.get("v3_vs_book") or []) if p_v3 is not None and p_book is not None else None
        )
        values["quota"] = quintile_value(odds, e.get("quota") or [])
        values["forma"] = quintile_value(base["form_diff"], e.get("forma") or [])
    else:
        e = synthetic_edges.get(key) or {}
        values["volume_atteso"] = quintile_value(_volume(base["volumes"], key), e.get("volume_atteso") or [])
        values["forma"] = quintile_value(base["form_diff"], e.get("forma") or [])
    return values


def v3_pattern_signals(db: Session, result: dict[str, Any], markets: dict[str, dict[str, Any]]) -> dict[str, Any]:
    build_id, patterns, _ = load_winners(db, MODEL_V3)
    if build_id is None:
        return {"status": "master_pattern_missing"}
    market_edges, synthetic_edges = _edges(db, build_id)
    base = _base_features(result)
    active: list[dict[str, Any]] = []
    unverifiable = 0
    for p in patterns:
        values = condition_values(p, base, markets, market_edges, synthetic_edges)
        checks = [
            None if values.get(str(c["column"])) is None else values[str(c["column"])] == str(c["value"])
            for c in p["conditions"]
        ]
        if any(r is False for r in checks):
            continue
        if any(r is None for r in checks):
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
    return {
        "status": "ok",
        "master_build_id": build_id,
        "active": active,
        "active_count": len(active),
        "unverifiable_count": unverifiable,
        "patterns_total": len(patterns),
    }


def latest_v3_build_id(db: Session) -> int | None:
    return db.scalar(
        select(CecchinoMasterPatternBuild.id)
        .where(CecchinoMasterPatternBuild.model == MODEL_V3, CecchinoMasterPatternBuild.status == MASTER_STATUS_COMPLETED)
        .order_by(CecchinoMasterPatternBuild.completed_at.desc())
    )
