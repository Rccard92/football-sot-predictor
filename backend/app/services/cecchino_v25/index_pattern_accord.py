"""Test storico: Indice di Acquistabilita' da solo e insieme ai pattern (V2.5 e V3), 2022/23-2024/25.

Solo lettura. Per ogni stagione di prova l'indice e' stimato solo in avanti (allenato sulle
stagioni precedenti, come nell'esame). Due insiemi di pattern:
- "scoperta": pattern trovati sul solo 2021/22 -> sulle stagioni di prova il test e' pulito;
- "master": Master Pattern 4/4 -> scelti anche guardando queste stagioni: risultati gonfiati
  per costruzione, riportati solo per confronto.
In entrambi restano fuori i pattern con condizioni sulla quota del bookmaker (acquistabilita',
distanza dal book, fascia di quota) e, per la V3, il "livello" (non verificabile dal vivo).
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Any

import numpy as np
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services.cecchino_data_lab.run_v2_grid_dataset import load_market_raw, load_season_binners, market_rows_from_raw
from app.services.cecchino_data_lab.run_v2_grid_matrix import RowMatrix
from app.services.cecchino_data_lab.run_v2_grid_vocabulary import Atom
from app.services.cecchino_live.observation import markets_conflict
from app.services.cecchino_v25.orchestrator import PLAYABLE_MIN_QUOTA, PREDICTION_MIN_SCORE, fit_market_matrix, scores_array
from app.services.cecchino_v25.orchestrator_data import MarketData

BOOK_COLUMNS = frozenset({"purchasability_class", "v3_vs_book", "quota"})
V3_EXCLUDED_COLUMNS = BOOK_COLUMNS | {"livello"}
TEST_SEASONS = ("2022/2023", "2023/2024", "2024/2025")


@dataclass
class SeasonRows:
    """Righe di prova di una stagione (tutti i mercati concatenati)."""

    market: np.ndarray
    match_id: np.ndarray
    score: np.ndarray
    won: np.ndarray
    base: np.ndarray
    quota: np.ndarray


def walk_forward_scores(
    data: dict[str, dict[str, MarketData]], *, features: tuple[str, ...], data_features: tuple[str, ...]
) -> dict[str, SeasonRows]:
    cols = [data_features.index(f) for f in features]
    seasons = sorted(data)
    out: dict[str, SeasonRows] = {}
    for target in TEST_SEASONS:
        if target not in data:
            continue
        parts: dict[str, list[np.ndarray]] = defaultdict(list)
        for key, test in sorted(data[target].items()):
            train = [data[s][key] for s in seasons if s < target and key in data[s]]
            if not train:
                continue
            x = np.vstack([t.x for t in train])[:, cols]
            y = np.concatenate([t.won for t in train])
            model = fit_market_matrix(key, x, y, features=features)
            p = model.predict_raw(test.x[:, cols])
            base = np.full(p.size, model.base_rate)
            parts["market"].append(np.full(p.size, key, dtype=object))
            parts["match_id"].append(test.match_id)
            parts["score"].append(scores_array(p, base))
            parts["won"].append(test.won)
            parts["base"].append(base)
            parts["quota"].append(test.quota)
        out[target] = SeasonRows(**{k: np.concatenate(v) for k, v in parts.items()})
    return out


# --- pattern accesi, partita per partita ------------------------------------------------------


def _clean(conditions: list[dict[str, Any]], excluded: frozenset[str]) -> list[tuple[str, str]] | None:
    pairs = [(str(c["column"]), str(c["value"])) for c in conditions]
    return None if any(col in excluded for col, _ in pairs) else pairs


def v25_pattern_sets(db: Session, *, master_build_id: int, insight_run_id: int) -> dict[str, dict[str, list[list[tuple[str, str]]]]]:
    sets: dict[str, dict[str, list[list[tuple[str, str]]]]] = {"scoperta": defaultdict(list), "master": defaultdict(list)}
    for filters, key in db.execute(
        text("SELECT filters_json, target_key FROM cecchino_run_v2_pattern_insight_candidates WHERE insight_run_id = :r AND target_type = 'market'"),
        {"r": insight_run_id},
    ):
        pairs = _clean(filters, BOOK_COLUMNS)
        if pairs:
            sets["scoperta"][str(key)].append(pairs)
    for conditions, key in db.execute(
        text("SELECT conditions_json, target_key FROM cecchino_master_patterns WHERE build_id = :b AND target_type = 'market'"),
        {"b": master_build_id},
    ):
        pairs = _clean(conditions, BOOK_COLUMNS)
        if pairs:
            sets["master"][str(key)].append(pairs)
    return sets


def v25_fired(
    db: Session, *, run_ids: dict[str, int], discovery_run_id: int, sets: dict[str, dict[str, list[list[tuple[str, str]]]]]
) -> dict[str, dict[str, dict[tuple[str, int], int]]]:
    """set -> stagione -> (mercato, partita) -> numero di pattern accesi."""
    binners = load_season_binners(db, run_id=discovery_run_id)
    out: dict[str, dict[str, dict[tuple[str, int], int]]] = {name: {} for name in sets}
    for season in TEST_SEASONS:
        for name in sets:
            out[name][season] = {}
        markets = sorted({k for s in sets.values() for k in s})
        for market in markets:
            rows = market_rows_from_raw(load_market_raw(db, run_id=run_ids[season], market_key=market), binners)
            if not rows:
                continue
            matrix = RowMatrix(rows)
            ids = np.asarray([r.lab_match_id for r in rows])
            for name, patterns in sets.items():
                counts = np.zeros(len(rows), dtype=int)
                for pairs in patterns.get(market, []):
                    counts += matrix.combo_mask(tuple(Atom(c, v) for c, v in pairs))
                for mid, n in zip(ids[counts > 0], counts[counts > 0]):
                    out[name][season][(market, int(mid))] = int(n)
    return out


def v3_pattern_sets(db: Session, *, master_build_id: int, pattern_run_id: int) -> dict[str, dict[str, list[list[tuple[str, str]]]]]:
    sets: dict[str, dict[str, list[list[tuple[str, str]]]]] = {"scoperta": defaultdict(list), "master": defaultdict(list)}
    for conditions, key in db.execute(
        text("SELECT conditions_json, market_key FROM cecchino_v3_patterns WHERE pattern_run_id = :r"), {"r": pattern_run_id}
    ):
        pairs = _clean(conditions, V3_EXCLUDED_COLUMNS)
        if pairs:
            sets["scoperta"][str(key)].append(pairs)
    for conditions, key in db.execute(
        text("SELECT conditions_json, target_key FROM cecchino_master_patterns WHERE build_id = :b AND target_type = 'market'"),
        {"b": master_build_id},
    ):
        pairs = _clean(conditions, V3_EXCLUDED_COLUMNS)
        if pairs:
            sets["master"][str(key)].append(pairs)
    return sets


def v3_fired(
    db: Session, *, run_id: int, index_run_id: int, master_build_id: int, sets: dict[str, dict[str, list[list[tuple[str, str]]]]]
) -> dict[str, dict[str, dict[tuple[str, int], int]]]:
    from app.models.cecchino_master_pattern import CecchinoMasterPatternBuild
    from app.services.cecchino_v3.market_data import load_market_rows
    from app.services.cecchino_v3.pattern_service import load_contexts
    from app.services.cecchino_v3.patterns import PATTERN_COLUMNS, build_matrices

    build = db.get(CecchinoMasterPatternBuild, master_build_id)
    edges = (((build.summary_json or {}).get("source") or {}).get("market_edges")) or {}
    rows = load_market_rows(db, run_id, include_lockbox=False)
    matrices = build_matrices(rows, load_contexts(db, index_run_id), edges)
    out: dict[str, dict[str, dict[tuple[str, int], int]]] = {name: {s: {} for s in TEST_SEASONS} for name in sets}
    for market, matrix in matrices.items():
        for name, patterns in sets.items():
            counts = np.zeros(matrix.profit.size, dtype=int)
            for pairs in patterns.get(market, []):
                combo = []
                for col, value in pairs:
                    c = PATTERN_COLUMNS.index(col)
                    if value not in matrix.values[c]:
                        combo = None
                        break
                    combo.append((c, matrix.values[c].index(value)))
                if combo:
                    counts += matrix.combo_mask(combo)
            for i in np.flatnonzero(counts):
                season = str(matrix.seasons[i])
                if season in out[name]:
                    out[name][season][(market, int(matrix.match_ids[i]))] = int(counts[i])
    return out


# --- metriche ------------------------------------------------------------------------------------


def _block(rows: SeasonRows, mask: np.ndarray) -> dict[str, Any]:
    n = int(mask.sum())
    if n == 0:
        return {"rows": 0}
    won, base, quota = rows.won[mask], rows.base[mask], rows.quota[mask]
    priced = ~np.isnan(quota)
    playable = priced & (np.nan_to_num(quota) >= PLAYABLE_MIN_QUOTA)

    def roi(sel: np.ndarray) -> float | None:
        if not sel.any():
            return None
        return round(float(np.sum(np.where(won[sel] > 0.5, quota[sel] - 1.0, -1.0))) / int(sel.sum()) * 100.0, 2)

    return {
        "rows": n,
        "won_pct": round(float(won.mean()) * 100.0, 2),
        "base_pct": round(float(base.mean()) * 100.0, 2),
        "lift_pt": round(float(won.mean() - base.mean()) * 100.0, 2),
        "avg_quota": round(float(quota[priced].mean()), 3) if priced.any() else None,
        "roi_pct": roi(priced),
        "playable": int(playable.sum()),
        "playable_roi_pct": roi(playable),
    }


BANDS10 = tuple((f"{lo}-{lo + 10}", float(lo), float(lo + 10) if lo < 90 else 100.01) for lo in range(0, 100, 10))


def season_accord(rows: SeasonRows, fired: dict[tuple[str, int], int]) -> dict[str, Any]:
    n = rows.won.size
    fired_count = np.fromiter((fired.get((str(m), int(i)), 0) for m, i in zip(rows.market, rows.match_id)), dtype=int, count=n)
    by_match: dict[int, set[str]] = defaultdict(set)
    for (market, mid) in fired:
        by_match[mid].add(market)
    conflict = np.fromiter(
        (any(markets_conflict(str(m), other) for other in by_match.get(int(i), ())) for m, i in zip(rows.market, rows.match_id)),
        dtype=bool,
        count=n,
    )
    has = fired_count > 0
    pred = rows.score >= PREDICTION_MIN_SCORE
    return {
        "pattern_acceso": {
            "tutti": _block(rows, has),
            "indice_d_accordo_70+": _block(rows, has & pred),
            "indice_neutro_50-70": _block(rows, has & (rows.score >= 50) & ~pred),
            "indice_contro_sotto_50": _block(rows, has & (rows.score < 50)),
            "indice_d_accordo_e_2+_pattern": _block(rows, has & pred & (fired_count >= 2)),
        },
        "predizioni_indice_70+": {
            "tutte": _block(rows, pred),
            "confermate_dal_pattern": _block(rows, pred & has),
            "in_contrasto_col_pattern": _block(rows, pred & ~has & conflict),
            "senza_pattern": _block(rows, pred & ~has & ~conflict),
        },
        "confermate_per_fascia": {
            label: _block(rows, pred & has & (rows.score >= lo) & (rows.score < hi)) for label, lo, hi in BANDS10 if lo >= 70
        },
    }


def index_bands(rows: SeasonRows) -> dict[str, Any]:
    return {label: _block(rows, (rows.score >= lo) & (rows.score < hi)) for label, lo, hi in BANDS10}


def concat(parts: list[SeasonRows]) -> SeasonRows:
    return SeasonRows(**{f: np.concatenate([getattr(p, f) for p in parts]) for f in SeasonRows.__dataclass_fields__})


def report(scores: dict[str, SeasonRows], fired: dict[str, dict[str, dict[tuple[str, int], int]]]) -> dict[str, Any]:
    seasons = [s for s in TEST_SEASONS if s in scores]
    pooled_rows = concat([scores[s] for s in seasons])
    out: dict[str, Any] = {
        "indice_da_solo": {"stagioni": {s: index_bands(scores[s]) for s in seasons}, "complessivo": index_bands(pooled_rows)},
        "indice_e_pattern": {},
    }
    for name, by_season in fired.items():
        pooled_fired: dict[tuple[str, int], int] = {}
        for s in seasons:
            pooled_fired.update(by_season.get(s, {}))
        out["indice_e_pattern"][name] = {
            "stagioni": {s: season_accord(scores[s], by_season.get(s, {})) for s in seasons},
            # le partite sono diverse tra stagioni: l'unione delle chiavi resta corretta
            "complessivo": season_accord(pooled_rows, pooled_fired),
        }
    return out
