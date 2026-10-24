"""Esame sull'ordinamento della giocata principale del Bet Builder (docs/bet_builder/ESAME_ORDINAMENTO_V1_PREREGISTRAZIONE.md).

Solo lettura: riusa le opportunita' salvate dalla pagina Risultati (stesso insieme per ogni variante, cambia solo
l'ordine) e misura la prima giocata di ogni variante con la quota Bet365, a 1 unita'.
"""

from __future__ import annotations

import math
import threading
import time
from collections import defaultdict
from datetime import date
from functools import cmp_to_key
from typing import Any, Callable

from sqlalchemy.orm import Session

from app.services.cecchino.cecchino_bet_builder_constants import BET_BUILDER_RESULTS_START_DATE
from app.services.cecchino.cecchino_bet_builder_primary_selection import ORIGIN_RANK, _cmp_nullable_number_desc
from app.services.cecchino.cecchino_bet_builder_results import (
    OUTCOME_LOST,
    OUTCOME_WON,
    _fixture_entries_for_range,
    _primary_quota_book,
    quota_band,
    roi_stats,
)

EXAM_VERSION = "bet_builder_sort_exam_v1_20261024"
Z_DECISION = 2.13  # 90% corretto per tre confronti con A
Z_REPORT = 1.645
CACHE_SECONDS = 24 * 3600

Opp = dict[str, Any]
Criterion = Callable[[Opp, Opp], int]


def _origin(a: Opp, b: Opp) -> int:
    return ORIGIN_RANK.get(str(a.get("origin") or ""), 99) - ORIGIN_RANK.get(str(b.get("origin") or ""), 99)


def _score(field: str) -> Criterion:
    def cmp(a: Opp, b: Opp) -> int:
        return _cmp_nullable_number_desc((a.get(field) or {}).get("score"), (b.get(field) or {}).get("score"))

    return cmp


def _signals_passed(a: Opp, b: Opp) -> int:
    pa = (a.get("signals") or {}).get("passed") is True
    pb = (b.get("signals") or {}).get("passed") is True
    return 0 if pa == pb else (-1 if pa else 1)


def _yes_count(a: Opp, b: Opp) -> int:
    return _cmp_nullable_number_desc((a.get("signals") or {}).get("yes_count"), (b.get("signals") or {}).get("yes_count"))


def _context(a: Opp, b: Opp) -> int:
    ca = (a.get("context_support") or {}).get("available") is True
    cb = (b.get("context_support") or {}).get("available") is True
    return 0 if ca == cb else (-1 if ca else 1)


def _price(field: str) -> Criterion:
    def cmp(a: Opp, b: Opp) -> int:
        return _cmp_nullable_number_desc((a.get("price_value") or {}).get(field), (b.get("price_value") or {}).get(field))

    return cmp


def _key(a: Opp, b: Opp) -> int:
    ka, kb = str(a.get("opportunity_key") or ""), str(b.get("opportunity_key") or "")
    return -1 if ka < kb else (1 if ka > kb else 0)


_TAIL: list[Criterion] = [_signals_passed, _yes_count, _context, _price("rating"), _price("edge_pct"), _key]

VARIANTS: dict[str, dict[str, Any]] = {
    "A": {"label": "Attuale: origine → V3.1 → segnali", "criteria": [_origin, _score("purchasability_v31"), *_TAIL]},
    "B": {"label": "Senza V3.1: origine → segnali", "criteria": [_origin, *_TAIL]},
    "C": {"label": "V3.6 al posto di V3.1: origine → V3.6 → segnali", "criteria": [_origin, _score("purchasability_v36"), *_TAIL]},
    "D": {"label": "Solo segnali", "criteria": list(_TAIL)},
}


def _comparator(criteria: list[Criterion]) -> Callable[[Opp, Opp], int]:
    def cmp(a: Opp, b: Opp) -> int:
        for c in criteria:
            r = c(a, b)
            if r != 0:
                return r
        return 0

    return cmp


def _settled(opp: Opp) -> tuple[bool, float] | None:
    q = _primary_quota_book(opp)
    if q is None or q <= 1.0 or opp.get("prediction_outcome") not in (OUTCOME_WON, OUTCOME_LOST):
        return None
    return opp["prediction_outcome"] == OUTCOME_WON, q


def _profit(won: bool, q: float) -> float:
    return q - 1.0 if won else -1.0


def _mean_ci(values: list[float], z: float) -> dict[str, Any]:
    n = len(values)
    if n == 0:
        return {"n": 0, "mean_pct": None, "low_pct": None, "high_pct": None}
    mean = sum(values) / n
    sd = math.sqrt(sum((v - mean) ** 2 for v in values) / (n - 1)) if n > 1 else 0.0
    half = z * sd / math.sqrt(n) if n > 1 else 0.0
    return {"n": n, "mean_pct": round(100 * mean, 2), "low_pct": round(100 * (mean - half), 2), "high_pct": round(100 * (mean + half), 2)}


def run_exam(db: Session, *, date_from: date, date_to: date) -> dict[str, Any]:
    d_from = max(date_from, BET_BUILDER_RESULTS_START_DATE)
    entries = _fixture_entries_for_range(db, d_from=d_from, d_to=date_to, start=BET_BUILDER_RESULTS_START_DATE)
    picks: dict[str, dict[int, tuple[Opp, tuple[bool, float]]]] = {k: {} for k in VARIANTS}
    reference: list[float] = []
    fixtures_with_opps = 0
    for idx, entry in enumerate(entries):
        opps = [o for o in entry.get("ranked") or [] if (_primary_quota_book(o) or 0) > 1.0]
        if not opps:
            continue
        fixtures_with_opps += 1
        settled_all = [s for s in (_settled(o) for o in opps) if s is not None]
        if settled_all:
            reference.append(sum(_profit(w, q) for w, q in settled_all) / len(settled_all))
        for name, spec in VARIANTS.items():
            first = sorted(opps, key=cmp_to_key(_comparator(spec["criteria"])))[0]
            s = _settled(first)
            if s is not None:
                picks[name][idx] = (first, s)

    variants_out = []
    for name, spec in VARIANTS.items():
        plays = list(picks[name].values())
        stats = roi_stats([s for _, s in plays])
        by_band: dict[str, list[tuple[bool, float]]] = defaultdict(list)
        by_origin: dict[str, list[tuple[bool, float]]] = defaultdict(list)
        for opp, s in plays:
            by_band[quota_band(s[1])].append(s)
            by_origin[str(opp.get("origin") or "?")].append(s)
        row: dict[str, Any] = {
            "variant": name,
            "label": spec["label"],
            **stats,
            "by_quota_band": {k: roi_stats(v) for k, v in sorted(by_band.items())},
            "by_origin": {k: roi_stats(v) for k, v in sorted(by_origin.items())},
        }
        if name != "A":
            common = [i for i in picks[name] if i in picks["A"]]
            diffs = [_profit(*picks[name][i][1]) - _profit(*picks["A"][i][1]) for i in common]
            same = sum(
                1 for i in common if picks[name][i][0].get("opportunity_key") == picks["A"][i][0].get("opportunity_key")
            )
            paired = _mean_ci(diffs, Z_DECISION)
            ref = _mean_ci(reference, Z_REPORT)
            beats_a = paired["low_pct"] is not None and paired["low_pct"] > 0
            not_below_ref = stats["roi_pct"] is not None and ref["mean_pct"] is not None and stats["roi_pct"] >= ref["mean_pct"]
            row["paired_vs_A"] = {**paired, "z": Z_DECISION, "same_pick_as_A": same, "common_fixtures": len(common)}
            row["passes"] = bool(beats_a and not_below_ref)
        variants_out.append(row)

    passing = [v for v in variants_out if v.get("passes")]
    best = max(passing, key=lambda v: v["paired_vs_A"]["mean_pct"])["variant"] if passing else None
    return {
        "exam": EXAM_VERSION,
        "preregistration": "docs/bet_builder/ESAME_ORDINAMENTO_V1_PREREGISTRAZIONE.md",
        "date_from": d_from.isoformat(),
        "date_to": date_to.isoformat(),
        "fixtures": len(entries),
        "fixtures_with_opportunities": fixtures_with_opps,
        "reference_random": _mean_ci(reference, Z_REPORT),
        "variants": variants_out,
        "proposed_variant": best,
    }


_cache: dict[tuple[str, str], tuple[float, dict[str, Any]]] = {}
_lock = threading.Lock()


def cached_exam(db: Session, *, date_from: date, date_to: date) -> dict[str, Any]:
    key = (date_from.isoformat(), date_to.isoformat())
    with _lock:
        hit = _cache.get(key)
    if hit and time.time() - hit[0] < CACHE_SECONDS:
        return hit[1]
    out = run_exam(db, date_from=date_from, date_to=date_to)
    with _lock:
        _cache[key] = (time.time(), out)
    return out
