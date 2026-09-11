"""Dataset layer per il motore di scoperta Pattern walk-forward.

Non esegue nuove query: riusa `iter_pattern_lab_rows`, che legge live da
`cecchino_lab_historical_match_snapshots` / `_market_results` e produce lo
stesso schema piatto pre_*/target_* già usato dagli export Pattern Lab.
Qui si filtra per market_key e si raggruppa per stagione, mantenendo solo le
feature pre_* ammesse (mai target_*/observational_only_*, stessa garanzia
anti-leakage degli export esistenti).
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.services.cecchino_data_lab.pattern_lab_service import iter_pattern_lab_rows

NUMERIC_FEATURES: tuple[str, ...] = (
    "pre_rating",
    "pre_edge_pct",
    "pre_vantaggio_prob",
    "pre_prob_cecchino",
    "pre_prob_book",
    "pre_prob_book_fair",
    "pre_signal_count",
    "pre_consensus_yes_count",
    "pre_balance_f36_score",
    "pre_balance_dominance_score",
    "pre_balance_draw_credibility_score",
    "pre_balance_gap_coherence_score",
    "pre_goal_v4_compat_final_score",
    "pre_goal_v4_compat_offensive_production_score",
    "pre_goal_v4_compat_defensive_solidity_score",
    "pre_goal_v4_compat_match_tempo_score",
    "pre_goal_v4_compat_offensive_stability_score",
    "pre_purch_v36_score",
    "pre_purch_v36_value_core",
    "pre_purch_v36_structural_factor",
    "pre_purch_v36_quality_factor",
    "pre_purch_v36_acquisition_core",
)

BOOLEAN_FEATURES: tuple[str, ...] = (
    "pre_signal_active",
    "pre_is_real_book_quote",
    "pre_is_derived_quote",
    "pre_value_positive",
    "pre_signal_excel_d",
    "pre_signal_excel_e",
    "pre_signal_excel_f",
    "pre_signal_excel_g",
)

FEATURE_NAMES: tuple[str, ...] = NUMERIC_FEATURES + BOOLEAN_FEATURES

_FORBIDDEN_PREFIXES = ("target_", "observational_only_")


def _assert_no_leakage() -> None:
    for name in FEATURE_NAMES:
        if any(name.startswith(bad) for bad in _FORBIDDEN_PREFIXES):
            raise AssertionError(f"feature non ammessa nel motore di scoperta (leakage): {name}")


_assert_no_leakage()


@dataclass(frozen=True)
class MarketRow:
    season: str
    features: dict[str, float | None]
    won: bool
    profit_1u: float | None
    quota_book: float | None


def load_market_rows_by_season(
    db: Session,
    *,
    run_ids: list[int],
    market_key: str,
) -> dict[str, list[MarketRow]]:
    """Righe eligible_core, non void, del market_key richiesto — raggruppate per stagione.

    Esclude righe senza esito definitivo (target_won is None) o marcate void:
    non portano segnale utilizzabile per la scoperta o la validazione.
    """
    by_season: dict[str, list[MarketRow]] = {}
    for row in iter_pattern_lab_rows(db, run_ids, filters={}, apply_filters=True):
        if row.get("market_key") != market_key:
            continue
        if row.get("eligibility_status") != "eligible_core":
            continue
        if row.get("target_void") is True:
            continue
        won_raw = row.get("target_won")
        if not isinstance(won_raw, bool):
            continue
        season = row.get("season")
        if not season:
            continue

        features: dict[str, float | None] = {}
        for name in NUMERIC_FEATURES:
            v = row.get(name)
            features[name] = float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None
        for name in BOOLEAN_FEATURES:
            v = row.get(name)
            features[name] = 1.0 if v is True else (0.0 if v is False else None)

        profit_raw = row.get("target_profit_1u")
        profit = float(profit_raw) if isinstance(profit_raw, (int, float)) else None
        quota_raw = row.get("pre_quota_bet365")
        quota = float(quota_raw) if isinstance(quota_raw, (int, float)) else None

        by_season.setdefault(season, []).append(
            MarketRow(season=season, features=features, won=won_raw, profit_1u=profit, quota_book=quota)
        )
    return by_season


def build_walk_forward_folds(seasons_sorted: list[str]) -> list[tuple[list[str], str]]:
    """Fold a finestra espandibile: train=[S1..Sk], valida=S(k+1). Nessun numero
    di stagioni è fissato: con N stagioni si ottengono N-1 fold."""
    folds: list[tuple[list[str], str]] = []
    for k in range(1, len(seasons_sorted)):
        folds.append((seasons_sorted[:k], seasons_sorted[k]))
    return folds
