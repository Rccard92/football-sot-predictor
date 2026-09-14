"""Scale congelate V2.5: da un valore grezzo a punteggio 0-100 e classe a 5 livelli.

Le soglie sono i percentili dei valori PRE-PARTITA della stagione 2021/22 (nessun
risultato usato), calcolati una sola volta e salvati in `frozen_scales.json`. Cosi' le
classi hanno lo stesso significato in ogni stagione e dal primo giorno, a differenza
della V2 che ricalcolava i percentili durante la stagione mescolando campionati.
"""

from __future__ import annotations

import json
from bisect import bisect_left
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.services.cecchino_v25.constants import FIVE_CLASS_KEYS, FIVE_CLASS_LABELS

_SCALES_FILE = Path(__file__).with_name("frozen_scales.json")


@lru_cache(maxsize=1)
def _load() -> dict[str, Any]:
    if not _SCALES_FILE.exists():
        return {}
    return json.loads(_SCALES_FILE.read_text(encoding="utf-8"))


def reload_scales() -> None:
    _load.cache_clear()


def scales_version() -> str | None:
    return _load().get("version")


def percentile_score(value: float | None, knots: list[float] | None) -> float | None:
    """Percentile 0-100 per interpolazione lineare sui nodi (nodi equispaziati in percentile)."""
    if value is None or not knots:
        return None
    n = len(knots) - 1
    if value <= knots[0]:
        return 0.0
    if value >= knots[-1]:
        return 100.0
    i = bisect_left(knots, value)
    lo, hi = knots[i - 1], knots[i]
    frac = 0.5 if hi == lo else (value - lo) / (hi - lo)
    return round(100.0 * (i - 1 + frac) / n, 3)


def value_at_percentile(pct: float, knots: list[float]) -> float:
    n = len(knots) - 1
    pos = max(0.0, min(float(n), pct / 100.0 * n))
    i = int(pos)
    if i >= n:
        return knots[-1]
    return knots[i] + (knots[i + 1] - knots[i]) * (pos - i)


def knots(name: str) -> list[float] | None:
    table = (_load().get("scales") or {}).get(name)
    return list(table) if table else None


def score(name: str, value: float | None) -> float | None:
    return percentile_score(value, knots(name))


def five_class(score_value: float | None) -> tuple[str | None, str | None]:
    if score_value is None:
        return None, None
    idx = min(4, int(score_value // 20))
    key = FIVE_CLASS_KEYS[idx]
    return key, FIVE_CLASS_LABELS[key]


def map_distribution(value: float | None, source: str, target: str) -> float | None:
    """Stesso percentile nella distribuzione `target` (es. quota V2.5 -> scala V2)."""
    src, dst = knots(source), knots(target)
    if value is None or not src or not dst:
        return None
    return value_at_percentile(percentile_score(value, src) or 0.0, dst)


def quantile_knots(values: list[float], points: int = 20) -> list[float]:
    """Nodi a percentili equispaziati (0, 100/points, ..., 100)."""
    data = sorted(v for v in values if v is not None)
    if not data:
        return []
    out = []
    for j in range(points + 1):
        pos = j / points * (len(data) - 1)
        i = int(pos)
        frac = pos - i
        nxt = data[min(i + 1, len(data) - 1)]
        out.append(round(data[i] + (nxt - data[i]) * frac, 6))
    # nodi strettamente non decrescenti: evita divisioni per zero nell'interpolazione
    for j in range(1, len(out)):
        if out[j] < out[j - 1]:
            out[j] = out[j - 1]
    return out
