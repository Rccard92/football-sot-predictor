"""Test storici aggiuntivi sull'Indice di Acquistabilita' (V2.5 e V3), stagioni 2022/23-2024/25.

Solo lettura. Indice sempre stimato in avanti (`walk_forward_scores`). Criteri fissati prima dei risultati:
1. quote del mattino: predizioni 90-100 alle quote di APERTURA (1X2 e Over/Under 2.5) con ROI > 0 nel
   complessivo e in almeno 2 stagioni su 3; confronto con la chiusura sulle stesse giocate;
2. V2.5 e V3 d'accordo: "entrambi 90+ sullo stesso mercato" vince e rende piu' di ciascun modello da
   solo 90+, sulle stesse partite;
3. una giocata per partita: tenere solo la predizione piu' forte della partita migliora vinte e ROI
   rispetto a tutte le predizioni 70+.
"""

from __future__ import annotations

from typing import Any

import numpy as np
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services.cecchino_v25.index_pattern_accord import TEST_SEASONS, SeasonRows
from app.services.cecchino_v25.orchestrator import PLAYABLE_MIN_QUOTA, PREDICTION_MIN_SCORE

CLOSING_COLUMNS = {"HOME": "bet365_closing_home", "DRAW": "bet365_closing_draw", "AWAY": "bet365_closing_away", "OVER_2_5": "bet365_closing_over_25", "UNDER_2_5": "bet365_closing_under_25"}
OPENING_COLUMNS = {"HOME": "bet365_home", "DRAW": "bet365_draw", "AWAY": "bet365_away", "OVER_2_5": "bet365_over_25", "UNDER_2_5": "bet365_under_25"}
BANDS = (("70-80", 70.0, 80.0), ("80-90", 80.0, 90.0), ("90-100", 90.0, 100.01), ("70+", 70.0, 100.01))


def _roi(won: np.ndarray, quota: np.ndarray) -> float | None:
    if quota.size == 0:
        return None
    return round(float(np.sum(np.where(won > 0.5, quota - 1.0, -1.0))) / quota.size * 100.0, 2)


def block(won: np.ndarray, base: np.ndarray, quota: np.ndarray) -> dict[str, Any]:
    """Vinte, frequenza normale e ROI su righe gia' selezionate (quota NaN esclusa dal ROI)."""
    n = int(won.size)
    if n == 0:
        return {"rows": 0}
    priced = ~np.isnan(quota)
    playable = priced & (np.nan_to_num(quota) >= PLAYABLE_MIN_QUOTA)
    return {
        "rows": n,
        "won_pct": round(float(won.mean()) * 100.0, 2),
        "base_pct": round(float(base.mean()) * 100.0, 2),
        "avg_quota": round(float(quota[priced].mean()), 3) if priced.any() else None,
        "roi_pct": _roi(won[priced], quota[priced]),
        "playable": int(playable.sum()),
        "playable_roi_pct": _roi(won[playable], quota[playable]),
    }


def _select(rows: SeasonRows, mask: np.ndarray, quota: np.ndarray | None = None) -> dict[str, Any]:
    q = rows.quota if quota is None else quota
    return block(rows.won[mask], rows.base[mask], q[mask])


# --- test 1: quote di apertura -------------------------------------------------------------------


def lab_quotes(db: Session, match_ids: set[int], columns: dict[str, str]) -> dict[int, dict[str, float]]:
    """Quote Bet365 del Lab per partita: stesse colonne per V2.5 e V3."""
    cols = ", ".join(f"m.{c} AS {k.lower()}" for k, c in columns.items())
    out: dict[int, dict[str, float]] = {}
    ids = sorted(match_ids)
    for start in range(0, len(ids), 5000):
        for r in db.execute(text(f"SELECT m.id, {cols} FROM cecchino_lab_matches m WHERE m.id = ANY(:ids)"), {"ids": ids[start : start + 5000]}):
            data = dict(r._mapping)
            mid = int(data.pop("id"))
            out[mid] = {k.upper(): float(v) for k, v in data.items() if v is not None and float(v) > 1.0}
    return out


def test_opening(
    rows_by_season: dict[str, SeasonRows], opening: dict[int, dict[str, float]], closing: dict[int, dict[str, float]]
) -> dict[str, Any]:
    out: dict[str, Any] = {"stagioni": {}}
    pooled: dict[str, list[np.ndarray]] = {"won": [], "base": [], "close": [], "open": [], "score": []}
    for season, rows in rows_by_season.items():
        open_q = np.fromiter(
            ((opening.get(int(i)) or {}).get(str(m), np.nan) for m, i in zip(rows.market, rows.match_id)), dtype=float, count=rows.won.size
        )
        close_q = np.fromiter(
            ((closing.get(int(i)) or {}).get(str(m), np.nan) for m, i in zip(rows.market, rows.match_id)), dtype=float, count=rows.won.size
        )
        both = ~np.isnan(open_q) & ~np.isnan(close_q)
        season_out = {}
        for label, lo, hi in BANDS:
            sel = both & (rows.score >= lo) & (rows.score < hi)
            season_out[label] = {
                "chiusura": block(rows.won[sel], rows.base[sel], close_q[sel]),
                "apertura": block(rows.won[sel], rows.base[sel], open_q[sel]),
            }
        out["stagioni"][season] = season_out
        pooled["won"].append(rows.won[both])
        pooled["base"].append(rows.base[both])
        pooled["close"].append(close_q[both])
        pooled["open"].append(open_q[both])
        pooled["score"].append(rows.score[both])
    p = {k: np.concatenate(v) for k, v in pooled.items()}
    out["complessivo"] = {}
    for label, lo, hi in BANDS:
        sel = (p["score"] >= lo) & (p["score"] < hi)
        out["complessivo"][label] = {
            "chiusura": block(p["won"][sel], p["base"][sel], p["close"][sel]),
            "apertura": block(p["won"][sel], p["base"][sel], p["open"][sel]),
        }
    seasons_positive = sum(1 for s in out["stagioni"].values() if (s["90-100"]["apertura"].get("roi_pct") or -1.0) > 0)
    out["verdetto"] = {
        "roi_apertura_90_100_complessivo_positivo": (out["complessivo"]["90-100"]["apertura"].get("roi_pct") or -1.0) > 0,
        "stagioni_positive_90_100": seasons_positive,
        "superato": bool((out["complessivo"]["90-100"]["apertura"].get("roi_pct") or -1.0) > 0 and seasons_positive >= 2),
    }
    return out


# --- test 2: V2.5 e V3 d'accordo --------------------------------------------------------------------


def test_agreement(v25: dict[str, SeasonRows], v3: dict[str, SeasonRows]) -> dict[str, Any]:
    won, base, quota, s25, s3 = [], [], [], [], []
    for season in TEST_SEASONS:
        a, b = v25.get(season), v3.get(season)
        if a is None or b is None:
            continue
        index_b = {(str(m), int(i)): k for k, (m, i) in enumerate(zip(b.market, b.match_id))}
        pairs = [(k, index_b[(str(m), int(i))]) for k, (m, i) in enumerate(zip(a.market, a.match_id)) if (str(m), int(i)) in index_b]
        if not pairs:
            continue
        ia = np.asarray([p[0] for p in pairs])
        ib = np.asarray([p[1] for p in pairs])
        won.append(b.won[ib])
        base.append(b.base[ib])
        quota.append(b.quota[ib])  # stessa quota di chiusura Bet365 per entrambi
        s25.append(a.score[ia])
        s3.append(b.score[ib])
    w, bs, q, x, y = (np.concatenate(v) for v in (won, base, quota, s25, s3))

    def sel(mask: np.ndarray) -> dict[str, Any]:
        return block(w[mask], bs[mask], q[mask])

    return {
        "righe_in_comune": int(w.size),
        "V2.5_90+": sel(x >= 90),
        "V3_90+": sel(y >= 90),
        "entrambi_90+": sel((x >= 90) & (y >= 90)),
        "V2.5_70+": sel(x >= PREDICTION_MIN_SCORE),
        "V3_70+": sel(y >= PREDICTION_MIN_SCORE),
        "entrambi_70+": sel((x >= PREDICTION_MIN_SCORE) & (y >= PREDICTION_MIN_SCORE)),
        "V3_90+_e_V2.5_sotto_50": sel((y >= 90) & (x < 50)),
        "V2.5_90+_e_V3_sotto_50": sel((x >= 90) & (y < 50)),
    }


# --- test 3: una giocata per partita ------------------------------------------------------------------

FAMILY = {
    "HOME": "esito", "DRAW": "esito", "AWAY": "esito", "ONE_X": "esito", "X_TWO": "esito", "ONE_TWO": "esito",
    "HOME_PT": "primo_tempo", "DRAW_PT": "primo_tempo", "AWAY_PT": "primo_tempo",
}


def _best_mask(rows: SeasonRows, group_by_family: bool) -> np.ndarray:
    pred = rows.score >= PREDICTION_MIN_SCORE
    best: dict[tuple, int] = {}
    for k in np.flatnonzero(pred):
        family = FAMILY.get(str(rows.market[k]), "gol") if group_by_family else ""
        key = (int(rows.match_id[k]), family)
        j = best.get(key)
        if j is None or rows.score[k] > rows.score[j]:
            best[key] = k
    mask = np.zeros(rows.won.size, dtype=bool)
    mask[list(best.values())] = True
    return mask


def test_one_per_match(rows_by_season: dict[str, SeasonRows]) -> dict[str, Any]:
    out: dict[str, Any] = {"stagioni": {}}
    agg: dict[str, list] = {"all": [], "best": [], "best_family": []}
    for season, rows in rows_by_season.items():
        masks = {
            "all": rows.score >= PREDICTION_MIN_SCORE,
            "best": _best_mask(rows, group_by_family=False),
            "best_family": _best_mask(rows, group_by_family=True),
        }
        out["stagioni"][season] = {
            "tutte_le_predizioni_70+": _select(rows, masks["all"]),
            "solo_la_piu_forte_per_partita": _select(rows, masks["best"]),
            "la_piu_forte_per_famiglia": _select(rows, masks["best_family"]),
        }
        for name, m in masks.items():
            agg[name].append((rows.won[m], rows.base[m], rows.quota[m], rows.score[m]))
    out["complessivo"] = {}
    labels = {"all": "tutte_le_predizioni_70+", "best": "solo_la_piu_forte_per_partita", "best_family": "la_piu_forte_per_famiglia"}
    for name, parts in agg.items():
        w = np.concatenate([p[0] for p in parts])
        b = np.concatenate([p[1] for p in parts])
        q = np.concatenate([p[2] for p in parts])
        s = np.concatenate([p[3] for p in parts])
        out["complessivo"][labels[name]] = {
            "totale": block(w, b, q),
            **{label: block(w[(s >= lo) & (s < hi)], b[(s >= lo) & (s < hi)], q[(s >= lo) & (s < hi)]) for label, lo, hi in BANDS[:3]},
        }
    return out
