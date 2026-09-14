"""Riepilogo del registro live per motore: precisione (Brier) e rendimento per mercato.

Il confronto tra motori e' onesto solo sulle stesse partite: le metriche "comuni" usano
le partite registrate e chiuse per tutti i motori presenti.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.cecchino_live_prediction import LIVE_STATUS_SETTLED, CecchinoLivePrediction

_FAMILIES = {
    "1X2": ("HOME", "DRAW", "AWAY"),
    "Doppia chance": ("ONE_X", "X_TWO", "ONE_TWO"),
    "1X2 primo tempo": ("HOME_PT", "DRAW_PT", "AWAY_PT"),
    "Over/Under": ("OVER_0_5", "UNDER_0_5", "OVER_1_5", "UNDER_1_5", "OVER_2_5", "UNDER_2_5", "OVER_3_5", "UNDER_3_5"),
}


def live_summary(db: Session) -> dict[str, Any]:
    rows = db.scalars(
        select(CecchinoLivePrediction).where(CecchinoLivePrediction.status == LIVE_STATUS_SETTLED)
    ).all()
    by_fixture: dict[int, dict[str, CecchinoLivePrediction]] = defaultdict(dict)
    for r in rows:
        by_fixture[int(r.today_fixture_id)][r.model] = r
    models = sorted({r.model for r in rows})
    common = [f for f in by_fixture.values() if all(m in f for m in models)]

    def metrics(preds: list[CecchinoLivePrediction]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for fam, keys in _FAMILIES.items():
            n = 0
            brier = 0.0
            profit = 0.0
            priced = 0
            for p in preds:
                res = ((p.result_json or {}).get("markets")) or {}
                for k in keys:
                    m = (p.markets_json or {}).get(k) or {}
                    r = res.get(k) or {}
                    if m.get("probability") is None or r.get("won") is None:
                        continue
                    n += 1
                    brier += (float(m["probability"]) - (1.0 if r["won"] else 0.0)) ** 2
                    if r.get("profit") is not None:
                        priced += 1
                        profit += float(r["profit"])
            out[fam] = {
                "rows": n,
                "brier": round(brier / n, 5) if n else None,
                "roi_pct_all_selections": round(100.0 * profit / priced, 2) if priced else None,
            }
        return out

    return {
        "models": models,
        "settled_by_model": {m: sum(1 for r in rows if r.model == m) for m in models},
        "common_fixtures": len(common),
        "common": {m: metrics([f[m] for f in common]) for m in models},
    }
