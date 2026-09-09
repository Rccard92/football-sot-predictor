"""Registry colonne export RUN V2.

Sorgente unica sia delle colonne dei CSV sia del DATA_DICTIONARY.json: le due
cose non possono divergere perche sono generate dalla stessa lista.

Ogni colonna dichiara il proprio layer e, soprattutto, se e ammessa come input
di una prediction. E questa dichiarazione a rendere il dataset utilizzabile da
un'altra AI senza che scambi una statistica post-match per una feature.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from app.services.cecchino_data_lab.run_v2.constants import (
    CORE_MARKETS,
    EXTRA_STAT_NAMES,
    EXTRA_STATS_RECENT_WINDOWS,
    LAYER_CORE_STRICT,
    LAYER_ECONOMIC,
    RUN_V2_EXPORT_SCHEMA_VERSION,
)

# Layer dichiarati nel data dictionary.
LAYER_IDENTITY = "identity"
LAYER_AUDIT = "leakage_audit"
LAYER_PRE_MATCH_FEATURE = "pre_match_feature"
LAYER_EXTRA_PRE_MATCH_FEATURE = "extra_prematch_feature"
LAYER_CORE_STRICT_QUOTE = "core_strict_quote"
LAYER_ECONOMIC_QUOTE = "economic_observation_quote"
LAYER_CORE_OUTPUT = "core_output"
LAYER_ECONOMIC_OUTPUT = "economic_observation_output"
LAYER_POST_MATCH_LABEL = "post_match_label"
LAYER_RAW_SOURCE = "raw_source"

# Valori di `available_at_prediction_time`.
AVAILABLE_YES = True
AVAILABLE_NO = False
AVAILABLE_NOT_CERTIFIED = "not_certified"

WDL_FIELDS = ("wins", "draws", "losses")
CONTEXT_KEYS = (
    "home_context",
    "away_context",
    "home_total",
    "away_total",
    "home_recent_context_5",
    "away_recent_context_5",
    "home_recent_total_6",
    "away_recent_total_6",
)

EXTRA_STAT_METRICS: tuple[str, ...] = (
    "season_avg_for",
    "season_avg_against",
    "season_sample",
    "home_away_split_avg_for",
    "home_away_split_avg_against",
    "home_away_split_sample",
    *[
        f"recent{w}_{suffix}"
        for w in EXTRA_STATS_RECENT_WINDOWS
        for suffix in ("avg_for", "avg_against", "sample")
    ],
    "competition_avg_for",
    "competition_delta_for",
    "trend_recent5_vs_season",
)


@dataclass(frozen=True)
class ColumnSpec:
    column: str
    layer: str
    allowed_as_prediction_input: bool
    available_at_prediction_time: Any
    source: str
    description: str
    getter: Callable[[dict[str, Any]], Any]

    def to_dictionary_entry(self) -> dict[str, Any]:
        return {
            "column": self.column,
            "layer": self.layer,
            "allowed_as_prediction_input": self.allowed_as_prediction_input,
            "available_at_prediction_time": self.available_at_prediction_time,
            "source": self.source,
            "description": self.description,
        }


def _get(path: tuple[str, ...], default: Any = None) -> Callable[[dict[str, Any]], Any]:
    def getter(ctx: dict[str, Any]) -> Any:
        node: Any = ctx
        for key in path:
            if isinstance(node, dict):
                node = node.get(key)
            else:
                return default
            if node is None:
                return default
        return node

    return getter


def _iso(path: tuple[str, ...]) -> Callable[[dict[str, Any]], Any]:
    inner = _get(path)

    def getter(ctx: dict[str, Any]) -> Any:
        value = inner(ctx)
        return value.isoformat() if hasattr(value, "isoformat") else value

    return getter


def _market_field(
    layer_key: str, market_key: str, field: str
) -> Callable[[dict[str, Any]], Any]:
    def getter(ctx: dict[str, Any]) -> Any:
        row = ((ctx.get("markets") or {}).get(layer_key) or {}).get(market_key) or {}
        return row.get(field)

    return getter


def _identity_columns() -> list[ColumnSpec]:
    def spec(column: str, path: tuple[str, ...], description: str, iso: bool = False):
        return ColumnSpec(
            column=column,
            layer=LAYER_IDENTITY,
            allowed_as_prediction_input=False,
            available_at_prediction_time=AVAILABLE_YES,
            source="cecchino_run_v2_match_snapshots",
            description=description,
            getter=_iso(path) if iso else _get(path),
        )

    return [
        spec("run_id", ("snapshot", "run_id"), "Identificativo della RUN V2"),
        spec("run_version", ("run_version",), "Versione del motore di run"),
        spec("lab_match_id", ("snapshot", "lab_match_id"), "ID partita nel Cecchino Lab"),
        spec("dataset_id", ("snapshot", "dataset_id"), "Dataset di provenienza"),
        spec("competition", ("snapshot", "competition_name"), "Nome competizione"),
        spec("competition_id", ("snapshot", "competition_id"), "ID stabile competizione+stagione"),
        spec("division_code", ("snapshot", "division_code"), "Codice divisione Football-Data"),
        spec("season", ("snapshot", "season_label"), "Etichetta stagione"),
        spec("season_start_year", ("snapshot", "season_start_year"), "Anno di inizio stagione"),
        spec("kickoff", ("snapshot", "kickoff_at"), "Orario di inizio partita", iso=True),
        spec("home_team", ("snapshot", "home_team"), "Squadra di casa"),
        spec("away_team", ("snapshot", "away_team"), "Squadra ospite"),
        spec("referee", ("snapshot", "referee"), "Arbitro designato"),
        spec(
            "chronological_order",
            ("snapshot", "chronological_order"),
            "Posizione nel walk-forward globale della run",
        ),
        spec("eligibility_status", ("snapshot", "eligibility_status"), "Esito eligibility V1"),
    ]


def _audit_columns() -> list[ColumnSpec]:
    def spec(column: str, path: tuple[str, ...], description: str, iso: bool = False):
        return ColumnSpec(
            column=column,
            layer=LAYER_AUDIT,
            allowed_as_prediction_input=False,
            available_at_prediction_time=AVAILABLE_YES,
            source="cecchino_run_v2_match_snapshots",
            description=description,
            getter=_iso(path) if iso else _get(path),
        )

    return [
        spec("history_count", ("snapshot", "history_count"), "Partite precedenti usate"),
        spec(
            "latest_history_kickoff_used",
            ("snapshot", "latest_history_kickoff_used"),
            "Kickoff piu recente nello storico usato: deve precedere strettamente il target",
            iso=True,
        ),
        spec(
            "pre_match_cutoff_ok",
            ("snapshot", "pre_match_cutoff_ok"),
            "True se nessuna violazione temporale e stata rilevata",
        ),
        spec(
            "pre_match_payload_sha256",
            ("snapshot", "pre_match_payload_sha256"),
            "Hash del payload pre-match congelato",
        ),
        spec(
            "pre_match_locked_at",
            ("snapshot", "pre_match_locked_at"),
            "Istante di freeze della prediction",
            iso=True,
        ),
    ]


def _prematch_context_columns() -> list[ColumnSpec]:
    """Feature WDL gia usate dal CORE V1."""
    cols: list[ColumnSpec] = []
    for ctx_key in CONTEXT_KEYS:
        for field in WDL_FIELDS:
            cols.append(
                ColumnSpec(
                    column=f"prematch_{ctx_key}_{field}",
                    layer=LAYER_PRE_MATCH_FEATURE,
                    allowed_as_prediction_input=True,
                    available_at_prediction_time=AVAILABLE_YES,
                    source="input_snapshot (contesti V1)",
                    description=f"{field} nel contesto {ctx_key}, da sole partite precedenti",
                    getter=_get(("snapshot", "input_snapshot_json", ctx_key, "wdl", field)),
                )
            )
        cols.append(
            ColumnSpec(
                column=f"prematch_{ctx_key}_sample",
                layer=LAYER_PRE_MATCH_FEATURE,
                allowed_as_prediction_input=True,
                available_at_prediction_time=AVAILABLE_YES,
                source="input_snapshot (contesti V1)",
                description=f"Numerosita campione del contesto {ctx_key}",
                getter=_get(("snapshot", "input_snapshot_json", ctx_key, "sample")),
            )
        )
    cols.append(
        ColumnSpec(
            column="prematch_prior_count",
            layer=LAYER_PRE_MATCH_FEATURE,
            allowed_as_prediction_input=True,
            available_at_prediction_time=AVAILABLE_YES,
            source="input_snapshot (contesti V1)",
            description="Numero di partite precedenti disponibili nella competizione/stagione",
            getter=_get(("snapshot", "input_snapshot_json", "prior_count")),
        )
    )
    return cols


def _extra_stats_columns() -> list[ColumnSpec]:
    """BLOCCO 2: rolling su shots, SOT, corner, falli, cartellini, arbitro."""
    cols: list[ColumnSpec] = []
    for side in ("home", "away"):
        for family in EXTRA_STAT_NAMES:
            for metric in EXTRA_STAT_METRICS:
                cols.append(
                    ColumnSpec(
                        column=f"prematch_{side}_{family}_{metric}",
                        layer=LAYER_EXTRA_PRE_MATCH_FEATURE,
                        allowed_as_prediction_input=True,
                        available_at_prediction_time=AVAILABLE_YES,
                        source="extra_stats_prematch_json (BLOCCO 2)",
                        description=(
                            f"{metric} di {family} per la squadra {side}, calcolato "
                            "solo su partite precedenti al kickoff"
                        ),
                        getter=_get(
                            (
                                "snapshot",
                                "extra_stats_prematch_json",
                                "teams",
                                side,
                                "stats",
                                family,
                                metric,
                            )
                        ),
                    )
                )
        cols.append(
            ColumnSpec(
                column=f"prematch_{side}_extra_stats_sample_count",
                layer=LAYER_EXTRA_PRE_MATCH_FEATURE,
                allowed_as_prediction_input=True,
                available_at_prediction_time=AVAILABLE_YES,
                source="extra_stats_prematch_json (BLOCCO 2)",
                description=f"Partite precedenti disponibili per la squadra {side}",
                getter=_get(
                    ("snapshot", "extra_stats_prematch_json", "teams", side, "sample_count")
                ),
            )
        )

    referee_fields = (
        ("previous_matches", "Partite arbitrate in precedenza"),
        ("previous_yellow_cards_avg", "Media gialli nelle partite precedenti"),
        ("previous_red_cards_avg", "Media rossi nelle partite precedenti"),
        ("previous_cards_avg", "Media cartellini nelle partite precedenti"),
        ("previous_fouls_avg", "Media falli nelle partite precedenti"),
        ("available", "True se esiste storico per questo arbitro"),
    )
    for field, description in referee_fields:
        cols.append(
            ColumnSpec(
                column=f"prematch_referee_{field}",
                layer=LAYER_EXTRA_PRE_MATCH_FEATURE,
                allowed_as_prediction_input=True,
                available_at_prediction_time=AVAILABLE_YES,
                source="extra_stats_prematch_json (BLOCCO 2)",
                description=f"{description}. Missing-safe: vuoto se arbitro assente",
                getter=_get(("snapshot", "extra_stats_prematch_json", "referee", field)),
            )
        )

    cols.append(
        ColumnSpec(
            column="prematch_extra_stats_status",
            layer=LAYER_EXTRA_PRE_MATCH_FEATURE,
            allowed_as_prediction_input=False,
            available_at_prediction_time=AVAILABLE_YES,
            source="extra_stats_prematch_json (BLOCCO 2)",
            description="Stato di disponibilita delle feature BLOCCO 2",
            getter=_get(("snapshot", "extra_stats_prematch_json", "availability", "status")),
        )
    )
    return cols


def _quote_columns() -> list[ColumnSpec]:
    cols: list[ColumnSpec] = []
    for market in CORE_MARKETS:
        base = f"bet365_strict_{market.export_key.lower()}"
        strict_fields = (
            ("value", "Quota pre-closing reference"),
            ("is_real_quote", "True se quota reale di book, non derivata"),
            ("is_derived", "True se derivata dall'1X2"),
            ("quote_source", "Tipo sorgente della quota"),
            ("source_column", "Colonna DB di provenienza"),
        )
        for field, description in strict_fields:
            cols.append(
                ColumnSpec(
                    column=f"{base}_{field}",
                    layer=LAYER_CORE_STRICT_QUOTE,
                    allowed_as_prediction_input=True,
                    available_at_prediction_time=AVAILABLE_YES,
                    source="quote_bundle_json.strict_by_market",
                    description=f"{description} per {market.label}",
                    getter=_get(
                        ("snapshot", "quote_bundle_json", "strict_by_market", market.key, field)
                    ),
                )
            )

        if not market.has_economic_quote:
            continue

        econ_base = f"bet365_last_seen_{market.export_key.lower()}"
        econ_fields = (
            ("value", "Quota near-closing"),
            ("is_real_quote", "True se la colonna last_seen e valorizzata"),
            ("prob_fair", "Probabilita implicita depurata dall'overround"),
        )
        for field, description in econ_fields:
            cols.append(
                ColumnSpec(
                    column=f"{econ_base}_{field}",
                    layer=LAYER_ECONOMIC_QUOTE,
                    allowed_as_prediction_input=False,
                    available_at_prediction_time=AVAILABLE_NOT_CERTIFIED,
                    source="quote_bundle_json.economic.quotes",
                    description=(
                        f"{description} per {market.label}. Quota near-closing: non "
                        "certificabile come disponibile a T-1, quindi mai input di prediction"
                    ),
                    getter=_get(
                        (
                            "snapshot",
                            "quote_bundle_json",
                            "economic",
                            "quotes",
                            market.key,
                            field,
                        )
                    ),
                )
            )
    return cols


def _core_output_columns() -> list[ColumnSpec]:
    cols: list[ColumnSpec] = []
    core_fields = (
        ("prediction", "Selezione a probabilita massima nella famiglia"),
        ("probability", "Probabilita Cecchino della selezione"),
        ("quota_cecchino", "Quota Cecchino della selezione"),
        ("confidence", "Reliability complessiva del modello sulla selezione"),
        ("kpi_rating", "Rating KPI"),
        ("edge_pct", "Edge percentuale contro la quota STRICT"),
        ("vantaggio_prob", "Vantaggio in probabilita contro la quota STRICT"),
        ("buyability_score", "Indice di acquistabilita"),
        ("buyability_class", "Classe di acquistabilita"),
        ("market_available", "True se il modello ha prodotto una prediction"),
        ("market_quote_available", "True se esiste una quota STRICT"),
        ("quota_book", "Quota STRICT usata per edge e profitto"),
    )
    for market in CORE_MARKETS:
        prefix = f"core_{market.export_key.lower()}"
        for field, description in core_fields:
            cols.append(
                ColumnSpec(
                    column=f"{prefix}_{field}",
                    layer=LAYER_CORE_OUTPUT,
                    allowed_as_prediction_input=False,
                    available_at_prediction_time=AVAILABLE_YES,
                    source="cecchino_run_v2_market_results (core_strict)",
                    description=f"{description} — {market.label}",
                    getter=_market_field(LAYER_CORE_STRICT, market.key, field),
                )
            )
        for field, description in (
            ("outcome", "Esito reale del mercato"),
            ("won", "True se la selezione si e verificata"),
            ("flat_stake_profit", "Profitto a puntata piatta sulla quota STRICT"),
        ):
            cols.append(
                ColumnSpec(
                    column=f"{prefix}_{field}",
                    layer=LAYER_POST_MATCH_LABEL,
                    allowed_as_prediction_input=False,
                    available_at_prediction_time=AVAILABLE_NO,
                    source="cecchino_run_v2_market_results (core_strict)",
                    description=f"{description} — {market.label}. Disponibile solo a partita conclusa",
                    getter=_market_field(LAYER_CORE_STRICT, market.key, field),
                )
            )
    return cols


def _economic_output_columns() -> list[ColumnSpec]:
    cols: list[ColumnSpec] = []
    fields = (
        ("quota_book", "Quota near-closing usata nel benchmark"),
        ("economic_benchmark_value", "Valore atteso della prediction congelata a quella quota"),
        ("economic_benchmark_profit", "Profitto a puntata piatta nel benchmark"),
        ("economic_benchmark_roi", "ROI della singola giocata nel benchmark"),
    )
    for market in CORE_MARKETS:
        if not market.has_economic_quote:
            continue
        prefix = f"econ_{market.export_key.lower()}"
        for field, description in fields:
            cols.append(
                ColumnSpec(
                    column=f"{prefix}_{field}",
                    layer=LAYER_ECONOMIC_OUTPUT,
                    allowed_as_prediction_input=False,
                    available_at_prediction_time=AVAILABLE_NO,
                    source="cecchino_run_v2_market_results (economic_observation)",
                    description=(
                        f"{description} — {market.label}. Benchmark economico su quota "
                        "near-closing: non e la performance di un sistema deployabile"
                    ),
                    getter=_market_field(LAYER_ECONOMIC, market.key, field),
                )
            )
    return cols


def _match_level_core_columns() -> list[ColumnSpec]:
    return [
        ColumnSpec(
            column="core_equilibrium_state",
            layer=LAYER_CORE_OUTPUT,
            allowed_as_prediction_input=False,
            available_at_prediction_time=AVAILABLE_YES,
            source="balance_v5_json",
            description="Stato di equilibrio/squilibrio strutturale del match",
            getter=_get(("equilibrium_state",)),
        ),
        ColumnSpec(
            column="core_goal_intensity_score",
            layer=LAYER_CORE_OUTPUT,
            allowed_as_prediction_input=False,
            available_at_prediction_time=AVAILABLE_YES,
            source="goal_intensity_json",
            description="Punteggio di intensita goal",
            getter=_get(("goal_intensity_score",)),
        ),
        ColumnSpec(
            column="core_balance_observation_status",
            layer=LAYER_CORE_OUTPUT,
            allowed_as_prediction_input=False,
            available_at_prediction_time=AVAILABLE_YES,
            source="balance_v5_json",
            description="Stato di esecuzione del modulo Balance V5",
            getter=_get(("snapshot", "balance_v5_json", "observation_status")),
        ),
        ColumnSpec(
            column="core_goal_intensity_execution",
            layer=LAYER_CORE_OUTPUT,
            allowed_as_prediction_input=False,
            available_at_prediction_time=AVAILABLE_YES,
            source="goal_intensity_json",
            description="Stato di esecuzione del modulo Goal Intensity",
            getter=_get(("snapshot", "goal_intensity_json", "execution_status")),
        ),
        ColumnSpec(
            column="core_purchasability_execution",
            layer=LAYER_CORE_OUTPUT,
            allowed_as_prediction_input=False,
            available_at_prediction_time=AVAILABLE_YES,
            source="purchasability_json",
            description="Stato di esecuzione del modulo Acquistabilita",
            getter=_get(("snapshot", "purchasability_json", "execution_status")),
        ),
    ]


def _actual_columns() -> list[ColumnSpec]:
    """Tutte le statistiche canoniche reali, mai ammesse come input."""
    cols: list[ColumnSpec] = []
    for family in EXTRA_STAT_NAMES:
        for side in ("home", "away", "total"):
            cols.append(
                ColumnSpec(
                    column=f"actual_{side}_{family}",
                    layer=LAYER_POST_MATCH_LABEL,
                    allowed_as_prediction_input=False,
                    available_at_prediction_time=AVAILABLE_NO,
                    source="actuals_json",
                    description=f"{family} realmente registrati ({side}) nella partita",
                    getter=_get(("snapshot", "actuals_json", f"{side}_{family}")),
                )
            )

    goal_fields = (
        ("ft_home_goals", "Gol casa a fine partita"),
        ("ft_away_goals", "Gol trasferta a fine partita"),
        ("ft_total_goals", "Gol totali a fine partita"),
        ("ft_result", "Segno finale"),
        ("ht_home_goals", "Gol casa al primo tempo"),
        ("ht_away_goals", "Gol trasferta al primo tempo"),
        ("ht_total_goals", "Gol totali al primo tempo"),
        ("ht_result", "Segno primo tempo"),
    )
    for field, description in goal_fields:
        cols.append(
            ColumnSpec(
                column=f"actual_{field}",
                layer=LAYER_POST_MATCH_LABEL,
                allowed_as_prediction_input=False,
                available_at_prediction_time=AVAILABLE_NO,
                source="actuals_json",
                description=description,
                getter=_get(("snapshot", "actuals_json", field)),
            )
        )
    return cols


def full_export_columns() -> list[ColumnSpec]:
    """Colonne di `FULL.csv`, in ordine stabile e raggruppate per layer."""
    return [
        *_identity_columns(),
        *_audit_columns(),
        *_prematch_context_columns(),
        *_extra_stats_columns(),
        *_quote_columns(),
        *_match_level_core_columns(),
        *_core_output_columns(),
        *_economic_output_columns(),
        *_actual_columns(),
    ]


CORE_MARKETS_LONG_COLUMNS: tuple[tuple[str, str, bool, Any, str], ...] = (
    ("run_id", LAYER_IDENTITY, False, AVAILABLE_YES, "Identificativo run"),
    ("lab_match_id", LAYER_IDENTITY, False, AVAILABLE_YES, "ID partita"),
    ("competition", LAYER_IDENTITY, False, AVAILABLE_YES, "Competizione"),
    ("season", LAYER_IDENTITY, False, AVAILABLE_YES, "Stagione"),
    ("season_start_year", LAYER_IDENTITY, False, AVAILABLE_YES, "Anno inizio stagione"),
    ("kickoff", LAYER_IDENTITY, False, AVAILABLE_YES, "Kickoff"),
    ("home_team", LAYER_IDENTITY, False, AVAILABLE_YES, "Squadra di casa"),
    ("away_team", LAYER_IDENTITY, False, AVAILABLE_YES, "Squadra ospite"),
    ("history_count", LAYER_AUDIT, False, AVAILABLE_YES, "Partite precedenti usate"),
    ("market_key", LAYER_IDENTITY, False, AVAILABLE_YES, "Chiave mercato"),
    ("market_label", LAYER_IDENTITY, False, AVAILABLE_YES, "Etichetta mercato"),
    ("market_family", LAYER_IDENTITY, False, AVAILABLE_YES, "Famiglia mercato"),
    ("period", LAYER_IDENTITY, False, AVAILABLE_YES, "Periodo"),
    ("line", LAYER_IDENTITY, False, AVAILABLE_YES, "Linea"),
    (
        "observation_layer",
        LAYER_IDENTITY,
        False,
        AVAILABLE_YES,
        "core_strict oppure economic_observation",
    ),
    ("prediction", LAYER_CORE_OUTPUT, False, AVAILABLE_YES, "Selezione predetta nella famiglia"),
    ("probability", LAYER_CORE_OUTPUT, False, AVAILABLE_YES, "Probabilita Cecchino"),
    ("quota_cecchino", LAYER_CORE_OUTPUT, False, AVAILABLE_YES, "Quota Cecchino"),
    ("confidence", LAYER_CORE_OUTPUT, False, AVAILABLE_YES, "Reliability"),
    ("kpi_rating", LAYER_CORE_OUTPUT, False, AVAILABLE_YES, "Rating KPI"),
    ("edge_pct", LAYER_CORE_OUTPUT, False, AVAILABLE_YES, "Edge percentuale"),
    ("vantaggio_prob", LAYER_CORE_OUTPUT, False, AVAILABLE_YES, "Vantaggio in probabilita"),
    ("buyability_score", LAYER_CORE_OUTPUT, False, AVAILABLE_YES, "Indice di acquistabilita"),
    ("buyability_class", LAYER_CORE_OUTPUT, False, AVAILABLE_YES, "Classe di acquistabilita"),
    ("equilibrium_state", LAYER_CORE_OUTPUT, False, AVAILABLE_YES, "Stato di equilibrio"),
    ("goal_intensity_score", LAYER_CORE_OUTPUT, False, AVAILABLE_YES, "Intensita goal"),
    ("market_available", LAYER_CORE_OUTPUT, False, AVAILABLE_YES, "Prediction disponibile"),
    ("market_quote_available", LAYER_CORE_OUTPUT, False, AVAILABLE_YES, "Quota disponibile"),
    ("quota_book", LAYER_CORE_STRICT_QUOTE, False, AVAILABLE_YES, "Quota di book del layer"),
    ("prob_book_raw", LAYER_CORE_STRICT_QUOTE, False, AVAILABLE_YES, "Probabilita implicita"),
    ("prob_book_fair", LAYER_CORE_STRICT_QUOTE, False, AVAILABLE_YES, "Probabilita depurata"),
    ("is_real_quote", LAYER_CORE_STRICT_QUOTE, False, AVAILABLE_YES, "Quota reale"),
    ("is_derived_quote", LAYER_CORE_STRICT_QUOTE, False, AVAILABLE_YES, "Quota derivata"),
    ("derivation_method", LAYER_CORE_STRICT_QUOTE, False, AVAILABLE_YES, "Metodo di derivazione"),
    ("quote_source", LAYER_CORE_STRICT_QUOTE, False, AVAILABLE_YES, "Sorgente quota"),
    ("source_column", LAYER_CORE_STRICT_QUOTE, False, AVAILABLE_YES, "Colonna DB di origine"),
    (
        "quote_snapshot_type",
        LAYER_CORE_STRICT_QUOTE,
        False,
        AVAILABLE_YES,
        "pre_closing_reference oppure last_seen",
    ),
    (
        "pre_match_input_safe",
        LAYER_AUDIT,
        False,
        AVAILABLE_YES,
        "True solo per le quote ammesse come input",
    ),
    (
        "used_for_prediction",
        LAYER_AUDIT,
        False,
        AVAILABLE_YES,
        "True solo se la quota ha alimentato la prediction",
    ),
    ("outcome", LAYER_POST_MATCH_LABEL, False, AVAILABLE_NO, "Esito reale"),
    ("won", LAYER_POST_MATCH_LABEL, False, AVAILABLE_NO, "Selezione vincente"),
    ("flat_stake_profit", LAYER_POST_MATCH_LABEL, False, AVAILABLE_NO, "Profitto puntata piatta"),
    (
        "economic_benchmark_value",
        LAYER_ECONOMIC_OUTPUT,
        False,
        AVAILABLE_NO,
        "Valore atteso nel benchmark economico",
    ),
    (
        "economic_benchmark_profit",
        LAYER_ECONOMIC_OUTPUT,
        False,
        AVAILABLE_NO,
        "Profitto nel benchmark economico",
    ),
    (
        "economic_benchmark_roi",
        LAYER_ECONOMIC_OUTPUT,
        False,
        AVAILABLE_NO,
        "ROI nel benchmark economico",
    ),
)


def core_markets_long_dictionary() -> list[dict[str, Any]]:
    return [
        {
            "column": column,
            "layer": layer,
            "allowed_as_prediction_input": allowed,
            "available_at_prediction_time": available,
            "source": "cecchino_run_v2_market_results",
            "description": description,
        }
        for column, layer, allowed, available, description in CORE_MARKETS_LONG_COLUMNS
    ]


def source_raw_dictionary_entry(column: str) -> dict[str, Any]:
    """Voce di dizionario per una colonna scoperta in `raw_json`."""
    return {
        "column": column,
        "layer": LAYER_RAW_SOURCE,
        "allowed_as_prediction_input": False,
        "available_at_prediction_time": AVAILABLE_NOT_CERTIFIED,
        "source": "cecchino_lab_matches.raw_json (Football-Data)",
        "description": (
            "Colonna grezza della sorgente, esportata per completezza. Molte di "
            "queste (HST, HC, HY, closing odds) sono dati di fine partita: non "
            "vanno usate come feature pre-match senza verifica esplicita."
        ),
    }


def build_data_dictionary(
    *,
    run_id: int,
    source_raw_columns: list[str],
) -> dict[str, Any]:
    """Dizionario dati completo dei tre CSV della run."""
    return {
        "export_schema_version": RUN_V2_EXPORT_SCHEMA_VERSION,
        "run_id": run_id,
        "layers": {
            LAYER_IDENTITY: "Identita della partita e della run",
            LAYER_AUDIT: "Tracce dell'audit anti-leakage",
            LAYER_PRE_MATCH_FEATURE: "Feature CORE note prima del kickoff",
            LAYER_EXTRA_PRE_MATCH_FEATURE: "Feature BLOCCO 2 note prima del kickoff",
            LAYER_CORE_STRICT_QUOTE: "Quote pre-closing reference, unico input ammesso",
            LAYER_ECONOMIC_QUOTE: "Quote near-closing, mai input",
            LAYER_CORE_OUTPUT: "Output dei moduli CORE a prediction congelata",
            LAYER_ECONOMIC_OUTPUT: "Benchmark economico, mai una prediction",
            LAYER_POST_MATCH_LABEL: "Dati noti solo a partita conclusa",
            LAYER_RAW_SOURCE: "Colonne grezze della sorgente Football-Data",
        },
        "files": {
            "FULL.csv": [c.to_dictionary_entry() for c in full_export_columns()],
            "core_markets_long.csv": core_markets_long_dictionary(),
            "SOURCE_RAW.csv": [
                {
                    "column": "lab_match_id",
                    "layer": LAYER_IDENTITY,
                    "allowed_as_prediction_input": False,
                    "available_at_prediction_time": AVAILABLE_YES,
                    "source": "cecchino_lab_matches",
                    "description": "Chiave di join con gli altri file",
                },
                *[source_raw_dictionary_entry(c) for c in source_raw_columns],
            ],
        },
    }
