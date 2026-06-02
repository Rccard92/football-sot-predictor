"""Selezione della versione \"visibile\" per giornata (una sola card per round)."""

from __future__ import annotations

from typing import Iterable

from app.models.backtest_round_analysis import BacktestRoundAnalysis


COMPLETED_STATUSES = frozenset({"completed", "completed_with_warnings"})


def pick_visible_latest_per_round(rows: Iterable[BacktestRoundAnalysis]) -> list[BacktestRoundAnalysis]:
    """Ritorna una sola analysis per round_number, scegliendo la più recente valida.

    Criterio:
    - considera solo status completed/completed_with_warnings
    - per round_number: max(analysis_version), tie-break max(created_at)
    - ordina per round_number asc (coerente con overview), la lista la ri-ordina come preferisce
    """
    by_round: dict[int, BacktestRoundAnalysis] = {}
    for row in rows:
        if str(row.status) not in COMPLETED_STATUSES:
            continue
        rn = int(row.round_number)
        prev = by_round.get(rn)
        if prev is None:
            by_round[rn] = row
            continue
        if int(row.analysis_version) > int(prev.analysis_version):
            by_round[rn] = row
            continue
        if int(row.analysis_version) == int(prev.analysis_version) and row.created_at and prev.created_at:
            if row.created_at > prev.created_at:
                by_round[rn] = row
    return sorted(by_round.values(), key=lambda r: int(r.round_number))

