"""Dataset layer per Pattern Insights (Run V2) — legge le tabelle nuove
(cecchino_run_v2_match_snapshots/market_results), separate da quelle del
Pattern Grid originale (cecchino_lab_historical_*).

Due modalita' di lettura:
- `load_run_v2_market_rows`: mercati con quota storica (i 17 di Run V2),
  stessa forma del Pattern Grid originale (won/profit/quota).
- `load_run_v2_synthetic_rows`: bersagli "senza quota" (tiri, tiri in porta,
  corner, cartellini) calcolati da actuals_json — nessuna quota storica
  esiste per questi, quindi si riporta solo la frequenza (win_rate), non il
  ROI. Utili per capire quali profili di partita producono quali situazioni,
  anche se non sono (ancora) scommettibili.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.cecchino_run_v2 import CecchinoRunV2MarketResult, CecchinoRunV2MatchSnapshot
from app.services.cecchino_data_lab.run_v2_grid_vocabulary import (
    CONTINUOUS_FEATURE_COLUMNS,
    QuantileBinner,
    bin_continuous_features,
)

ELIGIBLE_STATUS = "eligible_core"
OBSERVATION_LAYER = "core_strict"

_STAT_KEYS = ("shots", "sot", "corners", "fouls", "yellow_cards", "red_cards")

# Bersagli sintetici senza quota storica: statistica actuals_json + soglie
# candidate (over N.5) da provare. Non scelte a caso: coprono l'intervallo
# tipico osservato nei dati (vedi analisi preliminare di sessione).
SYNTHETIC_TARGETS: tuple[tuple[str, str, tuple[float, ...]], ...] = (
    ("total_shots", "Tiri totali", (20.5, 24.5, 28.5)),
    ("home_shots", "Tiri squadra 1", (9.5, 11.5, 13.5)),
    ("away_shots", "Tiri squadra 2", (8.5, 10.5, 12.5)),
    ("total_sot", "Tiri in porta totali", (7.5, 8.5, 9.5, 10.5)),
    ("home_sot", "Tiri in porta squadra 1", (3.5, 4.5, 5.5)),
    ("away_sot", "Tiri in porta squadra 2", (3.5, 4.5, 5.5)),
    ("total_corners", "Corner totali", (7.5, 8.5, 9.5, 10.5)),
    ("home_corners", "Corner squadra 1", (4.5, 5.5, 6.5)),
    ("away_corners", "Corner squadra 2", (3.5, 4.5, 5.5)),
    ("total_yellow_cards", "Cartellini gialli totali", (3.5, 4.5, 5.5)),
    ("home_yellow_cards", "Cartellini gialli squadra 1", (1.5, 2.5, 3.5)),
    ("away_yellow_cards", "Cartellini gialli squadra 2", (1.5, 2.5, 3.5)),
)


@dataclass(frozen=True)
class RunV2GridRow:
    lab_match_id: int
    competition: str
    categorical: dict[str, str | None]
    signal_active: bool
    won: bool | None
    profit_1u: float | None
    quota_book: float | None


def _pillar_class(payload: dict[str, Any] | None, pillar: str) -> str | None:
    if not payload:
        return None
    pillars = payload.get("pillars") or {}
    p = pillars.get(pillar)
    if not isinstance(p, dict):
        return None
    v = p.get("class_key")
    return str(v) if v else None


def _goal_final_class(payload: dict[str, Any] | None) -> str | None:
    if not payload:
        return None
    fc = payload.get("final_class")
    if isinstance(fc, dict):
        v = fc.get("key")
        return str(v) if v else None
    return None


def _balance_pillar_class(payload: dict[str, Any] | None, pillar: str) -> str | None:
    if not payload:
        return None
    classes = payload.get("pillar_classes") or {}
    v = classes.get(pillar)
    return str(v) if v else None


def _purchasability_class_for_market(payload: dict[str, Any] | None, market_key: str) -> str | None:
    if not payload:
        return None
    for entry in payload.get("markets") or []:
        if isinstance(entry, dict) and entry.get("market_key") == market_key:
            cls = entry.get("class")
            return str(cls) if cls else None
    return None


def _team_stat_delta(extra_stats: dict[str, Any] | None, side: str, stat: str) -> float | None:
    if not extra_stats:
        return None
    teams = extra_stats.get("teams") or {}
    team = teams.get(side)
    if not isinstance(team, dict):
        return None
    stats = team.get("stats") or {}
    s = stats.get(stat)
    if not isinstance(s, dict):
        return None
    v = s.get("competition_delta_for")
    return float(v) if isinstance(v, (int, float)) else None


def _referee_cards_avg(extra_stats: dict[str, Any] | None) -> float | None:
    if not extra_stats:
        return None
    ref = extra_stats.get("referee") or {}
    if not ref.get("available"):
        return None
    v = ref.get("previous_cards_avg")
    return float(v) if isinstance(v, (int, float)) else None


def _base_categorical(snap: CecchinoRunV2MatchSnapshot) -> dict[str, str | None]:
    gi = snap.goal_intensity_json
    bv = snap.balance_v5_json
    return {
        "goal_offensive_production_class": _pillar_class(gi, "offensive_production"),
        "goal_defensive_solidity_class": _pillar_class(gi, "defensive_solidity"),
        "goal_match_tempo_class": _pillar_class(gi, "match_tempo"),
        "goal_offensive_stability_class": _pillar_class(gi, "offensive_stability"),
        "goal_final_class": _goal_final_class(gi),
        "balance_f36_class": _balance_pillar_class(bv, "f36"),
        "balance_dominance_class": _balance_pillar_class(bv, "dominance"),
        "balance_draw_credibility_class": _balance_pillar_class(bv, "draw_credibility"),
        "balance_gap_coherence_class": _balance_pillar_class(bv, "gap_coherence"),
    }


def _continuous_raw(snap: CecchinoRunV2MatchSnapshot) -> dict[str, float | None]:
    extra = snap.extra_stats_prematch_json
    raw: dict[str, float | None] = {}
    for side in ("home", "away"):
        for stat in _STAT_KEYS:
            raw[f"{side}_{stat}_delta_class"] = _team_stat_delta(extra, side, stat)
    raw["referee_cards_avg_class"] = _referee_cards_avg(extra)
    return raw


def _compute_binners(raw_rows: list[dict[str, float | None]]) -> dict[str, QuantileBinner]:
    by_column: dict[str, list[float]] = {c: [] for c in CONTINUOUS_FEATURE_COLUMNS}
    for raw in raw_rows:
        for col in CONTINUOUS_FEATURE_COLUMNS:
            v = raw.get(col)
            if v is not None:
                by_column[col].append(v)
    return bin_continuous_features(by_column)


def _eligible_snapshots(db: Session, run_id: int) -> list[CecchinoRunV2MatchSnapshot]:
    return list(
        db.scalars(
            select(CecchinoRunV2MatchSnapshot).where(
                CecchinoRunV2MatchSnapshot.run_id == run_id,
                CecchinoRunV2MatchSnapshot.eligibility_status == ELIGIBLE_STATUS,
            )
        ).all()
    )


def load_run_v2_market_rows(db: Session, *, run_id: int, market_key: str) -> list[RunV2GridRow]:
    """Righe per un mercato con quota storica (i 17 mercati di Run V2)."""
    snaps = _eligible_snapshots(db, run_id)
    if not snaps:
        return []
    snap_ids = [int(s.id) for s in snaps]
    results = list(
        db.scalars(
            select(CecchinoRunV2MarketResult).where(
                CecchinoRunV2MarketResult.match_snapshot_id.in_(snap_ids),
                CecchinoRunV2MarketResult.market_key == market_key,
                CecchinoRunV2MarketResult.observation_layer == OBSERVATION_LAYER,
                CecchinoRunV2MarketResult.pre_match_input_safe.is_(True),
            )
        ).all()
    )
    result_by_snap = {int(r.match_snapshot_id): r for r in results}

    raw_continuous = [_continuous_raw(s) for s in snaps]
    binners = _compute_binners(raw_continuous)

    rows: list[RunV2GridRow] = []
    for snap, raw in zip(snaps, raw_continuous):
        result = result_by_snap.get(int(snap.id))
        if result is None or result.won is None:
            continue
        categorical = _base_categorical(snap)
        categorical["purchasability_class"] = _purchasability_class_for_market(
            snap.purchasability_json, market_key
        )
        for col, binner in binners.items():
            v = raw.get(col)
            categorical[col] = binner.label_for(v) if v is not None else None
        profit = float(result.flat_stake_profit) if result.flat_stake_profit is not None else None
        quota = float(result.quota_book) if result.quota_book is not None else None
        rows.append(
            RunV2GridRow(
                lab_match_id=int(snap.lab_match_id),
                competition=snap.competition_name,
                categorical=categorical,
                signal_active=bool(result.signal_active),
                won=bool(result.won),
                profit_1u=profit,
                quota_book=quota,
            )
        )
    return rows


def load_run_v2_synthetic_rows(
    db: Session, *, run_id: int, stat_key: str, threshold: float
) -> list[RunV2GridRow]:
    """Righe per un bersaglio sintetico senza quota (es. 'total_corners' over
    9.5): won=True se il valore reale della partita ha superato la soglia.
    Nessun profit/quota — servono a capire la frequenza, non un ROI."""
    snaps = _eligible_snapshots(db, run_id)
    if not snaps:
        return []

    raw_continuous = [_continuous_raw(s) for s in snaps]
    binners = _compute_binners(raw_continuous)

    rows: list[RunV2GridRow] = []
    for snap, raw in zip(snaps, raw_continuous):
        actuals = snap.actuals_json or {}
        value = actuals.get(stat_key)
        if not isinstance(value, (int, float)):
            continue
        categorical = _base_categorical(snap)
        categorical["purchasability_class"] = None
        for col, binner in binners.items():
            v = raw.get(col)
            categorical[col] = binner.label_for(v) if v is not None else None
        rows.append(
            RunV2GridRow(
                lab_match_id=int(snap.lab_match_id),
                competition=snap.competition_name,
                categorical=categorical,
                signal_active=False,
                won=bool(value > threshold),
                profit_1u=None,
                quota_book=None,
            )
        )
    return rows
