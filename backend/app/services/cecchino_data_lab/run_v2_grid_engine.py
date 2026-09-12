"""Motore di scoperta Pattern Insights (Run V2) — ricerca esaustiva su
un'unica stagione (per ora solo 2021/22 e' disponibile in Run V2, quindi
non esiste ancora un secondo anno su cui validare fuori campione: ogni
candidato qui e' "scoperto" ma non ancora confermato — a differenza del
Pattern Grid originale che ha gia' 4 stagioni e un verdetto a stadi).

Due criteri di inclusione diversi:
- mercati con quota storica: profitto totale positivo (stesso principio
  del Pattern Grid originale).
- bersagli sintetici senza quota (tiri/corner/cartellini): scarto rilevante
  dalla frequenza media generale (sopra O sotto — entrambe le direzioni
  sono informative, es. "quali match profile producono POCHI corner").
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from typing import Any

from app.services.cecchino_data_lab.run_v2_grid_dataset import RunV2GridRow
from app.services.cecchino_data_lab.run_v2_grid_vocabulary import (
    Atom,
    build_atom_vocabulary,
    combo_holds,
    combo_text,
    combo_to_json,
    enumerate_combos,
)

MIN_SAMPLE = 20
MIN_FREQUENCY_DEVIATION_PCT = 15.0
REFINEMENT_BASES = 15


def _stats(rows: list[RunV2GridRow], combo: tuple[Atom, ...]) -> dict[str, Any]:
    matched = [r for r in rows if combo_holds(r, combo)]
    n = len(matched)
    wins = sum(1 for r in matched if r.won)
    losses = n - wins
    profits = [r.profit_1u for r in matched if r.profit_1u is not None]
    quotes = [r.quota_book for r in matched if r.quota_book is not None]
    win_rate_pct = round(wins / n * 100.0, 3) if n else None
    roi_pct = round(statistics.fmean(profits) * 100.0, 3) if profits else None
    avg_quota = round(statistics.fmean(quotes), 3) if quotes else None
    return {
        "n": n,
        "wins": wins,
        "losses": losses,
        "win_rate_pct": win_rate_pct,
        "roi_pct": roi_pct,
        "avg_quota": avg_quota,
    }


@dataclass
class RunV2Candidate:
    combo: tuple[Atom, ...]
    stats: dict[str, Any]
    refined_from: tuple[Atom, ...] | None = None


def _qualifies(stats: dict[str, Any], *, has_odds: bool, baseline_win_rate: float) -> bool:
    if stats["n"] < MIN_SAMPLE:
        return False
    if has_odds:
        return stats["roi_pct"] is not None and stats["roi_pct"] > 0
    wr = stats["win_rate_pct"]
    return wr is not None and abs(wr - baseline_win_rate) >= MIN_FREQUENCY_DEVIATION_PCT


def _rank_key(candidate: RunV2Candidate, *, has_odds: bool, baseline_win_rate: float) -> float:
    if has_odds:
        return candidate.stats.get("roi_pct") or 0.0
    wr = candidate.stats.get("win_rate_pct") or baseline_win_rate
    return abs(wr - baseline_win_rate)


def discover_patterns(rows: list[RunV2GridRow], *, has_odds: bool) -> list[RunV2Candidate]:
    """Ricerca esaustiva 1-2 atomi + raffinamento a 3 atomi sui migliori
    15 candidati a 2 atomi, sull'unica stagione disponibile."""
    if not rows:
        return []
    baseline_win_rate = round(sum(1 for r in rows if r.won) / len(rows) * 100.0, 3)
    vocab = build_atom_vocabulary(rows)
    found: list[RunV2Candidate] = []
    existing_keys: set[frozenset[tuple[str, str]]] = set()

    for size in (1, 2):
        for combo in enumerate_combos(vocab, size):
            key = frozenset((a.column, a.value) for a in combo)
            if key in existing_keys:
                continue
            s = _stats(rows, combo)
            if _qualifies(s, has_odds=has_odds, baseline_win_rate=baseline_win_rate):
                found.append(RunV2Candidate(combo=combo, stats=s))
                existing_keys.add(key)

    two_atom_bases = [c for c in found if len(c.combo) == 2]
    two_atom_bases.sort(
        key=lambda c: _rank_key(c, has_odds=has_odds, baseline_win_rate=baseline_win_rate),
        reverse=True,
    )
    for base in two_atom_bases[:REFINEMENT_BASES]:
        used_cols = {a.column for a in base.combo}
        for atom in vocab:
            if atom.column in used_cols:
                continue
            combo = tuple(list(base.combo) + [atom])
            key = frozenset((a.column, a.value) for a in combo)
            if key in existing_keys:
                continue
            s = _stats(rows, combo)
            if _qualifies(s, has_odds=has_odds, baseline_win_rate=baseline_win_rate):
                found.append(RunV2Candidate(combo=combo, stats=s, refined_from=base.combo))
                existing_keys.add(key)

    found.sort(
        key=lambda c: _rank_key(c, has_odds=has_odds, baseline_win_rate=baseline_win_rate),
        reverse=True,
    )
    return found


def candidate_to_summary(candidate: RunV2Candidate, *, baseline_win_rate: float) -> dict[str, Any]:
    from app.services.cecchino_data_lab.run_v2_grid_labels import humanize_combo

    return {
        "filters_json": combo_to_json(candidate.combo),
        "filters_text": combo_text(candidate.combo),
        "filters_text_human": humanize_combo(combo_to_json(candidate.combo)),
        "refined_from_text": combo_text(candidate.refined_from) if candidate.refined_from else None,
        "n": candidate.stats["n"],
        "wins": candidate.stats["wins"],
        "losses": candidate.stats["losses"],
        "win_rate_pct": candidate.stats["win_rate_pct"],
        "roi_pct": candidate.stats["roi_pct"],
        "avg_quota": candidate.stats["avg_quota"],
        "baseline_win_rate_pct": baseline_win_rate,
        "deviation_pct": (
            round(candidate.stats["win_rate_pct"] - baseline_win_rate, 3)
            if candidate.stats["win_rate_pct"] is not None
            else None
        ),
    }
