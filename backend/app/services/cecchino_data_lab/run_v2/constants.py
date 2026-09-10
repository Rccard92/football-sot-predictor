"""Costanti e registry mercati RUN V2."""

from __future__ import annotations

from dataclasses import dataclass, field

from app.services.cecchino.cecchino_selection_keys import (
    SEL_AWAY,
    SEL_AWAY_PT,
    SEL_DRAW,
    SEL_DRAW_PT,
    SEL_HOME,
    SEL_HOME_PT,
    SEL_ONE_TWO,
    SEL_ONE_X,
    SEL_OVER_0_5,
    SEL_OVER_1_5,
    SEL_OVER_2_5,
    SEL_OVER_3_5,
    SEL_UNDER_0_5,
    SEL_UNDER_1_5,
    SEL_UNDER_2_5,
    SEL_UNDER_3_5,
    SEL_X_TWO,
)

RUN_V2_VERSION = "cecchino_run_v2"
RUN_V2_CONFIRM_TOKEN = "RUN_CECCHINO_RUN_V2"
RUN_V2_QUOTE_POLICY_VERSION = "bet365_closing_pre_kickoff_strict_v1"
RUN_V2_FEATURE_CONTRACT_VERSION = "cecchino_run_v2_feature_contract_v1"
RUN_V2_EXTRA_STATS_VERSION = "cecchino_run_v2_extra_stats_v1"
RUN_V2_EXPORT_SCHEMA_VERSION = "cecchino_run_v2_export_v2"

# Commit ogni N gruppi kickoff (il gruppo resta comunque atomico).
RUN_V2_COMMIT_EVERY_GROUPS = 40

# Heartbeat: `updated_at` viene rinfrescato a ogni flush di progresso, quindi
# la soglia deve coprire abbondantemente RUN_V2_COMMIT_EVERY_GROUPS gruppi.
RUN_V2_STALE_HEARTBEAT_SECONDS = 900

# Namespace advisory lock PostgreSQL per l'esclusivita del worker (no schema change).
RUN_V2_ADVISORY_LOCK_NAMESPACE = 0xCEC62002

# Timing quote.
QUOTE_SNAPSHOT_PRE_REFERENCE = "pre_closing_reference"
QUOTE_SNAPSHOT_LAST_SEEN = "last_seen"
# Provenienza enrichment: campo source `*_last_seen`, timing closing/pre-kickoff.
QUOTE_SNAPSHOT_CLOSING_PRE_KICKOFF = "closing_pre_kickoff"
TEMPORAL_CLASSIFICATION_CLOSING_PRE_KICKOFF = "closing_pre_kickoff"

# Layer di osservazione.
LAYER_CORE_STRICT = "core_strict"
# Layer legacy: preservato per RUN storiche gia materializzate; le nuove RUN
# non scrivono piu righe economic_observation per le 12 quote enrichment.
LAYER_ECONOMIC = "economic_observation"

# Famiglie mercato.
FAMILY_1X2 = "FT_1X2"
FAMILY_DC = "DOUBLE_CHANCE"
FAMILY_HT_1X2 = "HT_1X2"
FAMILY_OU = "FT_OVER_UNDER"

PERIOD_FT = "FT"
PERIOD_HT = "HT"


@dataclass(frozen=True)
class MarketDef:
    """Definizione di un mercato CORE della RUN V2.

    `strict_quote_columns` elenca le colonne Bet365 ammesse come input pre-match
    del Cecchino (legacy Football-Data oppure enrichment `*_last_seen` con
    temporal_classification=closing_pre_kickoff).

    `economic_quote_column` e deprecato per le nuove RUN (sempre None): le 12
    enrichment sono STRICT. Il campo resta solo per compatibilita di lettura
    di RUN storiche gia materializzate.
    """

    key: str
    export_key: str
    label: str
    family: str
    period: str
    line: str | None = None
    strict_quote_columns: tuple[str, ...] = ()
    strict_quote_derived_from_1x2: bool = False
    economic_quote_column: str | None = None
    # Il mercato entra nel pannello KPI RUN V2 (V1 + append V2-only OU 0.5).
    in_core_kpi_panel: bool = False

    @property
    def has_strict_real_quote(self) -> bool:
        return bool(self.strict_quote_columns)

    @property
    def has_economic_quote(self) -> bool:
        return self.economic_quote_column is not None


CORE_MARKETS: tuple[MarketDef, ...] = (
    # --- FT 1X2: quota reale pre-closing reference, input ammesso ---
    MarketDef(
        key=SEL_HOME,
        export_key="HOME",
        label="FT 1",
        family=FAMILY_1X2,
        period=PERIOD_FT,
        strict_quote_columns=("bet365_home",),
        in_core_kpi_panel=True,
    ),
    MarketDef(
        key=SEL_DRAW,
        export_key="DRAW",
        label="FT X",
        family=FAMILY_1X2,
        period=PERIOD_FT,
        strict_quote_columns=("bet365_draw",),
        in_core_kpi_panel=True,
    ),
    MarketDef(
        key=SEL_AWAY,
        export_key="AWAY",
        label="FT 2",
        family=FAMILY_1X2,
        period=PERIOD_FT,
        strict_quote_columns=("bet365_away",),
        in_core_kpi_panel=True,
    ),
    # --- Double Chance: STRICT reale enrichment; fallback derivata 1X2 ---
    MarketDef(
        key=SEL_ONE_X,
        export_key="ONE_X",
        label="Doppia Chance 1X",
        family=FAMILY_DC,
        period=PERIOD_FT,
        strict_quote_columns=("bet365_dc_1x",),
        strict_quote_derived_from_1x2=True,
        in_core_kpi_panel=True,
    ),
    MarketDef(
        key=SEL_ONE_TWO,
        export_key="ONE_TWO",
        label="Doppia Chance 12",
        family=FAMILY_DC,
        period=PERIOD_FT,
        strict_quote_columns=("bet365_dc_12",),
        strict_quote_derived_from_1x2=True,
        in_core_kpi_panel=True,
    ),
    MarketDef(
        key=SEL_X_TWO,
        export_key="X_TWO",
        label="Doppia Chance X2",
        family=FAMILY_DC,
        period=PERIOD_FT,
        strict_quote_columns=("bet365_dc_x2",),
        strict_quote_derived_from_1x2=True,
        in_core_kpi_panel=True,
    ),
    # --- HT 1X2: enrichment closing/pre-kickoff STRICT ---
    MarketDef(
        key=SEL_HOME_PT,
        export_key="HT_HOME",
        label="Primo Tempo 1",
        family=FAMILY_HT_1X2,
        period=PERIOD_HT,
        strict_quote_columns=("bet365_ht_home",),
        in_core_kpi_panel=True,
    ),
    MarketDef(
        key=SEL_DRAW_PT,
        export_key="HT_DRAW",
        label="Primo Tempo X",
        family=FAMILY_HT_1X2,
        period=PERIOD_HT,
        strict_quote_columns=("bet365_ht_draw",),
        in_core_kpi_panel=True,
    ),
    MarketDef(
        key=SEL_AWAY_PT,
        export_key="HT_AWAY",
        label="Primo Tempo 2",
        family=FAMILY_HT_1X2,
        period=PERIOD_HT,
        strict_quote_columns=("bet365_ht_away",),
        in_core_kpi_panel=True,
    ),
    # --- FT Over/Under ---
    MarketDef(
        key=SEL_OVER_0_5,
        export_key="OVER_0_5",
        label="Over 0.5 FT",
        family=FAMILY_OU,
        period=PERIOD_FT,
        line="0.5",
        strict_quote_columns=("bet365_over_05",),
        in_core_kpi_panel=True,
    ),
    MarketDef(
        key=SEL_UNDER_0_5,
        export_key="UNDER_0_5",
        label="Under 0.5 FT",
        family=FAMILY_OU,
        period=PERIOD_FT,
        line="0.5",
        strict_quote_columns=("bet365_under_05",),
        in_core_kpi_panel=True,
    ),
    MarketDef(
        key=SEL_OVER_1_5,
        export_key="OVER_1_5",
        label="Over 1.5 FT",
        family=FAMILY_OU,
        period=PERIOD_FT,
        line="1.5",
        strict_quote_columns=("bet365_over_15",),
        in_core_kpi_panel=True,
    ),
    MarketDef(
        key=SEL_UNDER_1_5,
        export_key="UNDER_1_5",
        label="Under 1.5 FT",
        family=FAMILY_OU,
        period=PERIOD_FT,
        line="1.5",
        strict_quote_columns=("bet365_under_15",),
        in_core_kpi_panel=True,
    ),
    MarketDef(
        key=SEL_OVER_2_5,
        export_key="OVER_2_5",
        label="Over 2.5 FT",
        family=FAMILY_OU,
        period=PERIOD_FT,
        line="2.5",
        strict_quote_columns=("bet365_over_25",),
        in_core_kpi_panel=True,
    ),
    MarketDef(
        key=SEL_UNDER_2_5,
        export_key="UNDER_2_5",
        label="Under 2.5 FT",
        family=FAMILY_OU,
        period=PERIOD_FT,
        line="2.5",
        strict_quote_columns=("bet365_under_25",),
        in_core_kpi_panel=True,
    ),
    MarketDef(
        key=SEL_OVER_3_5,
        export_key="OVER_3_5",
        label="Over 3.5 FT",
        family=FAMILY_OU,
        period=PERIOD_FT,
        line="3.5",
        strict_quote_columns=("bet365_over_35",),
        in_core_kpi_panel=True,
    ),
    MarketDef(
        key=SEL_UNDER_3_5,
        export_key="UNDER_3_5",
        label="Under 3.5 FT",
        family=FAMILY_OU,
        period=PERIOD_FT,
        line="3.5",
        strict_quote_columns=("bet365_under_35",),
        in_core_kpi_panel=True,
    ),
)

CORE_MARKET_BY_KEY: dict[str, MarketDef] = {m.key: m for m in CORE_MARKETS}
CORE_MARKET_KEYS: tuple[str, ...] = tuple(m.key for m in CORE_MARKETS)

# Vuoto per le nuove RUN: le enrichment sono STRICT. Mantenuto per API/test.
ECONOMIC_QUOTE_COLUMNS: tuple[str, ...] = tuple(
    m.economic_quote_column for m in CORE_MARKETS if m.economic_quote_column
)
# Colonne STRICT ammesse come input (legacy + enrichment closing/pre-kickoff).
STRICT_QUOTE_COLUMNS: tuple[str, ...] = tuple(
    col for m in CORE_MARKETS for col in m.strict_quote_columns
)

# Colonne enrichment (source field `*_last_seen`) promosse a STRICT pre-match.
ENRICHMENT_STRICT_QUOTE_COLUMNS: frozenset[str] = frozenset(
    {
        "bet365_dc_1x",
        "bet365_dc_12",
        "bet365_dc_x2",
        "bet365_ht_home",
        "bet365_ht_draw",
        "bet365_ht_away",
        "bet365_over_05",
        "bet365_under_05",
        "bet365_over_15",
        "bet365_under_15",
        "bet365_over_35",
        "bet365_under_35",
    }
)


# --- BLOCCO 2: statistiche extra ---------------------------------------------

# (nome famiglia, colonna casa, colonna trasferta)
EXTRA_STAT_FAMILIES: tuple[tuple[str, str, str], ...] = (
    ("shots", "home_shots", "away_shots"),
    ("sot", "home_shots_on_target", "away_shots_on_target"),
    ("corners", "home_corners", "away_corners"),
    ("fouls", "home_fouls", "away_fouls"),
    ("yellow_cards", "home_yellow_cards", "away_yellow_cards"),
    ("red_cards", "home_red_cards", "away_red_cards"),
)

EXTRA_STAT_NAMES: tuple[str, ...] = tuple(f[0] for f in EXTRA_STAT_FAMILIES)

# Finestre rolling delle feature pre-match BLOCCO 2.
EXTRA_STATS_RECENT_WINDOWS: tuple[int, ...] = (5, 10)

# Linee virtuali statistiche: `statistical_target`, NON mercati bookmaker.
# Configurabili qui, mai hardcoded altrove. Non ottimizzate in questo task.
STATISTICAL_TARGET_KIND = "statistical_target"

STATISTICAL_TARGET_LINES: dict[str, tuple[float, ...]] = {
    "HOME_SHOTS": (8.5, 10.5, 12.5, 14.5),
    "AWAY_SHOTS": (8.5, 10.5, 12.5, 14.5),
    "TOTAL_SHOTS": (18.5, 20.5, 22.5, 24.5, 26.5),
    "HOME_SOT": (2.5, 3.5, 4.5, 5.5),
    "AWAY_SOT": (2.5, 3.5, 4.5, 5.5),
    "TOTAL_SOT": (6.5, 7.5, 8.5, 9.5, 10.5),
    "HOME_CORNERS": (3.5, 4.5, 5.5, 6.5),
    "AWAY_CORNERS": (3.5, 4.5, 5.5, 6.5),
    "TOTAL_CORNERS": (8.5, 9.5, 10.5, 11.5, 12.5),
    "HOME_CARDS": (1.5, 2.5, 3.5),
    "AWAY_CARDS": (1.5, 2.5, 3.5),
    "TOTAL_CARDS": (2.5, 3.5, 4.5, 5.5),
}
