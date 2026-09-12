"""Dataset layer per il motore Pattern Grid — righe raw (classi come stringhe,
non convertite in numeri) raggruppate per stagione, opzionalmente per un solo
campionato.

Riusa `iter_pattern_lab_rows` (stessa fonte, stesso schema pre_*/target_* già
verificato identico ai 4 export ZIP) e lo stesso filtro `market_informative`
già usato da `pattern_lab_presets.py` — omesso nel primo motore (ad albero) e
rivelatosi necessario per combaciare con i numeri già discussi con l'utente.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.services.cecchino_data_lab.pattern_lab_filters import is_market_informative
from app.services.cecchino_data_lab.pattern_lab_service import iter_pattern_lab_rows


@dataclass(frozen=True)
class GridRow:
    season: str
    competition: str
    categorical: dict[str, str | None]
    signal_active: bool
    won: bool
    profit_1u: float | None
    quota_book: float | None


def load_grid_rows_by_season(
    db: Session,
    *,
    run_ids: list[int],
    market_key: str,
    competition: str | None = None,
) -> dict[str, list[GridRow]]:
    from app.services.cecchino_data_lab.pattern_grid_vocabulary import CATEGORICAL_COLUMNS

    by_season: dict[str, list[GridRow]] = {}
    for row in iter_pattern_lab_rows(db, run_ids, filters={}, apply_filters=True):
        if row.get("market_key") != market_key:
            continue
        if competition and row.get("competition") != competition:
            continue
        if row.get("eligibility_status") != "eligible_core":
            continue
        if not is_market_informative(row):
            continue
        if row.get("target_void") is True:
            continue
        won_raw = row.get("target_won")
        if not isinstance(won_raw, bool):
            continue
        season = row.get("season")
        comp = row.get("competition")
        if not season or not comp:
            continue

        categorical = {col: (str(row[col]) if row.get(col) else None) for col in CATEGORICAL_COLUMNS}
        profit_raw = row.get("target_profit_1u")
        profit = float(profit_raw) if isinstance(profit_raw, (int, float)) else None
        quota_raw = row.get("pre_quota_bet365")
        quota = float(quota_raw) if isinstance(quota_raw, (int, float)) else None

        by_season.setdefault(season, []).append(
            GridRow(
                season=season,
                competition=comp,
                categorical=categorical,
                signal_active=row.get("pre_signal_active") is True,
                won=won_raw,
                profit_1u=profit,
                quota_book=quota,
            )
        )
    return by_season
