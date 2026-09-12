"""Motore Pattern Grid: ricerca esaustiva + ciclo sequenziale a 4 stadi.

Replica in modo cieco e sistematico il processo "run 1 → proponi pattern →
run 2 → conferma/proponi altri → ... " già seguito manualmente con ChatGPT,
ma esplorando esaustivamente le combinazioni di 1-2 atomi (raffinate a 3 solo
sui candidati già promettenti) invece che a intuito, e tenendo lo storico
completo di ogni candidato stadio per stadio invece di un unico numero
aggregato — è quello storico a distinguere un pattern stabile da uno che sta
decadendo (esattamente come osservato a mano su P08/P09/P12 vs P01/P02/P05).

Nessuna soglia è scelta a mano: gli atomi vengono dai valori realmente
osservati nei dati (vedi pattern_grid_vocabulary.build_atom_vocabulary).
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from typing import Any

from app.services.cecchino_data_lab.pattern_grid_dataset import GridRow
from app.services.cecchino_data_lab.pattern_grid_vocabulary import (
    Atom,
    build_atom_vocabulary,
    combo_holds,
    combo_text,
    combo_to_json,
    enumerate_combos,
)

MIN_SAMPLE = 20

VERDICT_STABLE = "stable"
VERDICT_CONFIRMED_ONCE = "confirmed_once"
VERDICT_WEAKENING = "weakening"
VERDICT_DECAYING = "decaying"
VERDICT_REJECTED = "rejected"
VERDICT_PENDING_FIRST_OOS = "pending_first_oos"

STAGE_STATUS_CONFIRMED = "confirmed"
STAGE_STATUS_REJECTED = "rejected"
STAGE_STATUS_INSUFFICIENT = "insufficient_sample"


def _stats(rows: list[GridRow], combo: tuple[Atom, ...]) -> dict[str, Any]:
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


def _validate(rows: list[GridRow], combo: tuple[Atom, ...]) -> dict[str, Any]:
    s = _stats(rows, combo)
    if s["n"] < MIN_SAMPLE:
        status = STAGE_STATUS_INSUFFICIENT
    elif s["roi_pct"] is not None and s["roi_pct"] > 0:
        status = STAGE_STATUS_CONFIRMED
    else:
        status = STAGE_STATUS_REJECTED
    return {**s, "status": status}


@dataclass
class Candidate:
    combo: tuple[Atom, ...]
    born_stage: int
    refined_from: tuple[Atom, ...] | None = None
    per_stage: dict[int, dict[str, Any]] = field(default_factory=dict)
    total: dict[str, Any] | None = None


def _latest_roi(candidate: Candidate) -> float:
    if not candidate.per_stage:
        return 0.0
    latest_stage = max(candidate.per_stage)
    return candidate.per_stage[latest_stage].get("roi_pct") or 0.0


def discover_candidates(
    rows: list[GridRow],
    *,
    born_stage: int,
    existing_keys: set[frozenset[tuple[str, str]]],
    known_two_atom_bases: list[Candidate],
) -> list[Candidate]:
    """Ricerca esaustiva 1-2 atomi su `rows` (già cumulate fino allo stadio
    corrente), poi raffinamento a 3 atomi. Esclude combinazioni già note
    (`existing_keys`) — non le riscopre come nuove.

    Il raffinamento riprova ad ogni stadio su TUTTE le combinazioni a 2 atomi
    note fino a questo momento (non solo quelle appena scoperte in questo
    stadio): altrimenti un pattern a 2 atomi trovato allo stadio 1 non verrebbe
    mai raffinato a 3 negli stadi successivi, e molti raffinamenti buoni
    comparirebbero solo all'ultimo stadio per un limite dell'algoritmo, non
    per un motivo statistico.
    """
    vocab = build_atom_vocabulary(rows)
    found: list[Candidate] = []

    for size in (1, 2):
        for combo in enumerate_combos(vocab, size):
            key = frozenset((a.column, a.value) for a in combo)
            if key in existing_keys:
                continue
            s = _stats(rows, combo)
            if s["n"] >= MIN_SAMPLE and s["roi_pct"] is not None and s["roi_pct"] > 0:
                c = Candidate(combo=combo, born_stage=born_stage)
                c.per_stage[born_stage] = {**s, "status": STAGE_STATUS_CONFIRMED}
                found.append(c)
                existing_keys.add(key)

    # Raffinamento a 3 atomi: su tutte le basi a 2 atomi note (vecchie + nuove di questo stadio)
    all_two_atom_bases = known_two_atom_bases + [c for c in found if len(c.combo) == 2]
    all_two_atom_bases.sort(key=_latest_roi, reverse=True)
    for base in all_two_atom_bases[:15]:
        used_cols = {a.column for a in base.combo}
        for atom in vocab:
            if atom.column in used_cols:
                continue
            combo = tuple(list(base.combo) + [atom])
            key = frozenset((a.column, a.value) for a in combo)
            if key in existing_keys:
                continue
            s = _stats(rows, combo)
            if s["n"] >= MIN_SAMPLE and s["roi_pct"] is not None and s["roi_pct"] > 0:
                c = Candidate(combo=combo, born_stage=born_stage, refined_from=base.combo)
                c.per_stage[born_stage] = {**s, "status": STAGE_STATUS_CONFIRMED}
                found.append(c)
                existing_keys.add(key)

    return found


def run_pattern_grid(rows_by_stage: list[list[GridRow]]) -> list[Candidate]:
    """`rows_by_stage[i]` = righe della sola stagione allo stadio i+1 (non
    cumulate). Ritorna tutti i candidati con il loro storico completo per
    stadio (nato/confermato/decaduto/mai testato)."""
    candidates: list[Candidate] = []
    existing_keys: set[frozenset[tuple[str, str]]] = set()
    cumulative: list[GridRow] = []

    for stage_idx, stage_rows in enumerate(rows_by_stage, start=1):
        # 1) valida i candidati esistenti sullo stadio corrente da solo (mai visto prima)
        for c in candidates:
            c.per_stage[stage_idx] = _validate(stage_rows, c.combo)

        # 2) scoperta fresca sul cumulato fino a questo stadio incluso
        cumulative = cumulative + stage_rows
        known_two_atom = [c for c in candidates if len(c.combo) == 2]
        new_candidates = discover_candidates(
            cumulative,
            born_stage=stage_idx,
            existing_keys=existing_keys,
            known_two_atom_bases=known_two_atom,
        )
        candidates.extend(new_candidates)

    for c in candidates:
        c.total = _stats(cumulative, c.combo)

    return candidates


def final_verdict(candidate: Candidate, total_stages: int) -> str:
    post_birth = [
        candidate.per_stage[s]["status"]
        for s in range(candidate.born_stage + 1, total_stages + 1)
        if s in candidate.per_stage
    ]
    if not post_birth:
        return VERDICT_PENDING_FIRST_OOS

    confirmed = sum(1 for s in post_birth if s == STAGE_STATUS_CONFIRMED)
    rejected = sum(1 for s in post_birth if s == STAGE_STATUS_REJECTED)

    if rejected == 0 and confirmed >= 2:
        return VERDICT_STABLE
    if rejected == 0 and confirmed == 1:
        return VERDICT_CONFIRMED_ONCE
    if rejected == 0 and confirmed == 0:
        return VERDICT_PENDING_FIRST_OOS
    if confirmed > rejected:
        return VERDICT_WEAKENING
    if confirmed == 0:
        return VERDICT_REJECTED
    return VERDICT_DECAYING


def candidate_to_summary(candidate: Candidate, total_stages: int) -> dict[str, Any]:
    from app.services.cecchino_data_lab.pattern_grid_labels import humanize_combo

    return {
        "filters_json": combo_to_json(candidate.combo),
        "filters_text": combo_text(candidate.combo),
        "filters_text_human": humanize_combo(combo_to_json(candidate.combo)),
        "born_stage": candidate.born_stage,
        "refined_from_text": combo_text(candidate.refined_from) if candidate.refined_from else None,
        "per_stage": {str(k): v for k, v in candidate.per_stage.items()},
        "total": candidate.total,
        "final_verdict": final_verdict(candidate, total_stages),
    }
