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

Nota di performance: gli snapshot Run V2 contengono ~350 MB di JSONB per
stagione, ma a noi servono solo una dozzina di valori scalari per riga. Le
estrazioni vengono quindi fatte in SQL (operatori jsonb) e viaggiano come
scalari: caricare gli oggetti ORM interi rendeva ogni lettura decine di
volte piu' lenta senza alcun beneficio.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services.cecchino_data_lab.run_v2_grid_vocabulary import (
    CONTINUOUS_FEATURE_COLUMNS,
    QuantileBinner,
    bin_continuous_features,
)

ELIGIBLE_STATUS = "eligible_core"
OBSERVATION_LAYER = "core_strict"

_STAT_KEYS = ("shots", "sot", "corners", "fouls", "yellow_cards", "red_cards")

# Bersagli sintetici senza quota storica: statistica actuals_json + soglie
# candidate (over N.5) da provare.
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

_ALLOWED_SYNTHETIC_KEYS = frozenset(k for k, _, _ in SYNTHETIC_TARGETS)


@dataclass(frozen=True)
class RunV2GridRow:
    lab_match_id: int
    competition: str
    categorical: dict[str, str | None]
    signal_active: bool
    won: bool | None
    profit_1u: float | None
    quota_book: float | None
    # Solo per il drill-down (quali partite hanno attivato il pattern): non
    # entrano mai nella logica di matching.
    kickoff_at: str | None = None
    home_team: str | None = None
    away_team: str | None = None
    actual_value: float | None = None


# --- proiezioni SQL ---------------------------------------------------------

_GOAL_PILLARS = (
    ("goal_offensive_production_class", "offensive_production"),
    ("goal_defensive_solidity_class", "defensive_solidity"),
    ("goal_match_tempo_class", "match_tempo"),
    ("goal_offensive_stability_class", "offensive_stability"),
)
_BALANCE_PILLARS = (
    ("balance_f36_class", "f36"),
    ("balance_dominance_class", "dominance"),
    ("balance_draw_credibility_class", "draw_credibility"),
    ("balance_gap_coherence_class", "gap_coherence"),
)


def _class_projections() -> str:
    parts = [
        f"s.goal_intensity_json->'pillars'->'{pillar}'->>'class_key' AS {alias}"
        for alias, pillar in _GOAL_PILLARS
    ]
    parts.append("s.goal_intensity_json->'final_class'->>'key' AS goal_final_class")
    parts += [
        f"s.balance_v5_json->'pillar_classes'->>'{pillar}' AS {alias}"
        for alias, pillar in _BALANCE_PILLARS
    ]
    return ",\n       ".join(parts)


def _delta_projections() -> str:
    parts = []
    for side in ("home", "away"):
        for stat in _STAT_KEYS:
            parts.append(
                f"(s.extra_stats_prematch_json->'teams'->'{side}'->'stats'->'{stat}'"
                f"->>'competition_delta_for')::double precision AS {side}_{stat}_delta_class"
            )
    parts.append(
        "(CASE WHEN (s.extra_stats_prematch_json->'referee'->>'available')::boolean "
        "THEN (s.extra_stats_prematch_json->'referee'->>'previous_cards_avg')::double precision "
        "END) AS referee_cards_avg_class"
    )
    return ",\n       ".join(parts)


def _base_select(extra_columns: str) -> str:
    return f"""
        SELECT s.lab_match_id,
               s.competition_name,
               s.kickoff_at,
               s.home_team,
               s.away_team,
               {_class_projections()},
               {_delta_projections()},
               {extra_columns}
        FROM cecchino_run_v2_match_snapshots s
    """


def _binners_from(raw_rows: list[dict[str, float | None]]) -> dict[str, QuantileBinner]:
    by_column: dict[str, list[float]] = {c: [] for c in CONTINUOUS_FEATURE_COLUMNS}
    for raw in raw_rows:
        for col in CONTINUOUS_FEATURE_COLUMNS:
            v = raw.get(col)
            if v is not None:
                by_column[col].append(v)
    return bin_continuous_features(by_column)


def _categorical_from(row: dict, binners: dict[str, QuantileBinner]) -> dict[str, str | None]:
    categorical: dict[str, str | None] = {}
    for alias, _ in _GOAL_PILLARS:
        categorical[alias] = row.get(alias)
    categorical["goal_final_class"] = row.get("goal_final_class")
    for alias, _ in _BALANCE_PILLARS:
        categorical[alias] = row.get(alias)
    for col in CONTINUOUS_FEATURE_COLUMNS:
        v = row.get(col)
        binner = binners.get(col)
        categorical[col] = binner.label_for(v) if (binner and v is not None) else None
    return categorical


def load_run_v2_market_rows(db: Session, *, run_id: int, market_key: str) -> list[RunV2GridRow]:
    """Righe per un mercato con quota storica (i 17 mercati di Run V2)."""
    sql = (
        _base_select(
            """
               (SELECT pm->>'class'
                  FROM jsonb_array_elements(
                         coalesce(s.purchasability_json->'markets', '[]'::jsonb)) pm
                 WHERE pm->>'market_key' = :market_key
                 LIMIT 1) AS purchasability_class,
               r.won                AS won,
               r.flat_stake_profit  AS profit_1u,
               r.quota_book         AS quota_book,
               r.signal_active      AS signal_active
            """
        )
        + """
        JOIN cecchino_run_v2_market_results r
          ON r.match_snapshot_id = s.id
         AND r.market_key = :market_key
         AND r.observation_layer = :layer
         AND r.pre_match_input_safe IS TRUE
        WHERE s.run_id = :run_id
          AND s.eligibility_status = :eligible
          AND r.won IS NOT NULL
        """
    )
    result = db.execute(
        text(sql),
        {
            "run_id": run_id,
            "market_key": market_key,
            "layer": OBSERVATION_LAYER,
            "eligible": ELIGIBLE_STATUS,
        },
    )
    raw = [dict(r._mapping) for r in result]
    binners = _binners_from(raw)

    rows: list[RunV2GridRow] = []
    for r in raw:
        categorical = _categorical_from(r, binners)
        categorical["purchasability_class"] = r.get("purchasability_class")
        rows.append(
            RunV2GridRow(
                lab_match_id=int(r["lab_match_id"]),
                competition=r["competition_name"],
                categorical=categorical,
                signal_active=bool(r["signal_active"]),
                won=bool(r["won"]),
                profit_1u=float(r["profit_1u"]) if r["profit_1u"] is not None else None,
                quota_book=float(r["quota_book"]) if r["quota_book"] is not None else None,
                kickoff_at=r["kickoff_at"].isoformat() if r["kickoff_at"] else None,
                home_team=r["home_team"],
                away_team=r["away_team"],
            )
        )
    return rows


def load_run_v2_synthetic_rows(
    db: Session, *, run_id: int, stat_key: str, threshold: float
) -> list[RunV2GridRow]:
    """Righe per un bersaglio sintetico senza quota (es. 'total_corners' over
    9.5): won=True se il valore reale della partita ha superato la soglia.
    Nessun profit/quota — servono a capire la frequenza, non un ROI."""
    if stat_key not in _ALLOWED_SYNTHETIC_KEYS:
        raise ValueError(f"stat_key non riconosciuto: {stat_key!r}")

    sql = (
        _base_select(
            f"(s.actuals_json->>'{stat_key}')::double precision AS actual_value"
        )
        # `stat_key` e' validato contro l'allowlist sopra: nessun input libero
        # finisce nella query. Si evita l'operatore jsonb `?` (ambiguo con i
        # placeholder dei driver) usando un semplice IS NOT NULL.
        + f"""
        WHERE s.run_id = :run_id
          AND s.eligibility_status = :eligible
          AND s.actuals_json->>'{stat_key}' IS NOT NULL
        """
    )
    result = db.execute(text(sql), {"run_id": run_id, "eligible": ELIGIBLE_STATUS})
    raw = [dict(r._mapping) for r in result]
    binners = _binners_from(raw)

    rows: list[RunV2GridRow] = []
    for r in raw:
        value = r.get("actual_value")
        if value is None:
            continue
        categorical = _categorical_from(r, binners)
        categorical["purchasability_class"] = None
        rows.append(
            RunV2GridRow(
                lab_match_id=int(r["lab_match_id"]),
                competition=r["competition_name"],
                categorical=categorical,
                signal_active=False,
                won=bool(value > threshold),
                profit_1u=None,
                quota_book=None,
                kickoff_at=r["kickoff_at"].isoformat() if r["kickoff_at"] else None,
                home_team=r["home_team"],
                away_team=r["away_team"],
                actual_value=float(value),
            )
        )
    return rows
