"""Definizioni dichiarative macro/micro v2.1 (PDF Variabili progetto Tiri in porta)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

V21InitialStatus = Literal["available", "missing", "fallback", "not_tracked_yet"]


@dataclass(frozen=True)
class V21MicroSpec:
    key: str
    label: str
    source_path: str
    micro_weight: int | None = None
    initial_status: V21InitialStatus = "not_tracked_yet"


@dataclass(frozen=True)
class V21MacroAreaSpec:
    key: str
    label: str
    macro_weight: int
    micros: tuple[V21MicroSpec, ...]
    is_quality_only: bool = False


def _micro(key: str, label: str, weight: int, source_path: str) -> V21MicroSpec:
    return V21MicroSpec(
        key=key,
        label=label,
        micro_weight=weight,
        source_path=source_path,
        initial_status="not_tracked_yet",
    )


def _quality_micro(key: str, label: str, source_path: str) -> V21MicroSpec:
    return V21MicroSpec(
        key=key,
        label=label,
        micro_weight=None,
        source_path=source_path,
        initial_status="not_tracked_yet",
    )


V21_MANIFEST_DEFINITIONS: tuple[V21MacroAreaSpec, ...] = (
    V21MacroAreaSpec(
        key="offensive_production",
        label="Produzione offensiva composita",
        macro_weight=16,
        micros=(
            _micro("avg_sot_for", "Media tiri in porta fatti", 25, "team_stats.season_avg_sot_for"),
            _micro("avg_total_shots_for", "Media tiri totali fatti", 20, "team_stats.season_avg_shots_for"),
            _micro("shot_accuracy", "Precisione tiro: SOT / tiri totali", 18, "team_stats.shot_accuracy_for"),
            _micro("avg_inside_box_shots", "Media tiri dentro area", 16, "team_stats.season_avg_inside_box_shots_for"),
            _micro("avg_outside_box_shots", "Media tiri fuori area", 3, "team_stats.season_avg_outside_box_shots_for"),
            _micro("avg_blocked_shots", "Media tiri bloccati", 2, "team_stats.season_avg_blocked_shots_for"),
            _micro("avg_off_target_shots", "Media tiri fuori dallo specchio", 1, "team_stats.season_avg_off_target_shots_for"),
            _micro("avg_goals_for", "Media goal fatti", 5, "team_stats.season_avg_goals_for"),
            _micro("offensive_trend", "Trend offensivo recente", 10, "team_stats.offensive_trend_recent"),
        ),
    ),
    V21MacroAreaSpec(
        key="opponent_defensive_resistance",
        label="Resistenza difensiva avversaria",
        macro_weight=14,
        micros=(
            _micro("opp_sot_conceded", "SOT concessi avversario stagione", 30, "opponent_stats.season_avg_sot_conceded"),
            _micro("opp_total_shots_conceded", "Tiri totali concessi avversario", 20, "opponent_stats.season_avg_shots_conceded"),
            _micro("opp_inside_box_conceded", "Tiri dentro area concessi avversario", 25, "opponent_stats.season_avg_inside_box_conceded"),
            _micro("opp_outside_box_conceded", "Tiri fuori area concessi avversario", 2, "opponent_stats.season_avg_outside_box_conceded"),
            _micro("opp_blocked_shots", "Tiri bloccati/concessi", 3, "opponent_stats.season_avg_blocked_shots_conceded"),
            _micro("opp_defensive_trend", "Trend difensivo recente avversario", 20, "opponent_stats.defensive_trend_recent"),
        ),
    ),
    V21MacroAreaSpec(
        key="home_away_split",
        label="Split casa/trasferta",
        macro_weight=10,
        micros=(
            _micro("split_sot_for", "SOT fatti casa/fuori", 25, "team_stats.split_avg_sot_for"),
            _micro("split_opp_sot_conceded", "SOT concessi avversario casa/fuori", 25, "opponent_stats.split_avg_sot_conceded"),
            _micro("split_shots_for", "Tiri totali fatti casa/fuori", 15, "team_stats.split_avg_shots_for"),
            _micro("split_shots_conceded", "Tiri totali concessi casa/fuori", 15, "opponent_stats.split_avg_shots_conceded"),
            _micro("split_performance_delta", "Differenza rendimento casa/fuori", 20, "team_stats.home_away_performance_delta"),
        ),
    ),
    V21MacroAreaSpec(
        key="recent_form",
        label="Forma recente",
        macro_weight=15,
        micros=(
            _micro("last5_sot_for", "SOT fatti ultime 5", 20, "team_stats.last5_avg_sot_for"),
            _micro("last5_opp_sot_conceded", "SOT concessi avversario ultime 5", 20, "opponent_stats.last5_avg_sot_conceded"),
            _micro("last5_shots_for", "Tiri totali fatti ultime 5", 15, "team_stats.last5_avg_shots_for"),
            _micro("last5_shots_conceded", "Tiri totali concessi ultime 5", 15, "opponent_stats.last5_avg_shots_conceded"),
            _micro("last5_goals_for", "Goal fatti ultime 5", 10, "team_stats.last5_avg_goals_for"),
            _micro("form_trend_vs_season", "Trend rispetto alla media stagionale", 20, "team_stats.form_trend_vs_season_avg"),
        ),
    ),
    V21MacroAreaSpec(
        key="chance_quality",
        label="Qualità occasioni",
        macro_weight=17,
        micros=(
            _micro("xg_produced", "xG prodotti", 30, "team_stats.season_avg_xg_for"),
            _micro("xg_conceded_by_opponent", "xG concessi dall'avversario", 30, "opponent_stats.season_avg_xg_conceded"),
            _micro("xg_delta_vs_league", "Delta xG squadra vs media lega", 15, "team_stats.xg_delta_vs_league_avg"),
            _micro("opp_xg_conceded_delta", "Delta xG concesso avversario vs media lega", 15, "opponent_stats.xg_conceded_delta_vs_league"),
            _micro("xg_prudent_adjustment", "xG adjustment prudente", 10, "team_stats.xg_prudent_adjustment_signal"),
        ),
    ),
    V21MacroAreaSpec(
        key="player_layer",
        label="Player layer",
        macro_weight=9,
        micros=(
            _micro("top_sot_per90", "Tiri in porta per 90 dei top player", 20, "player_season_profiles.top_shooters_sot_per90"),
            _micro("top_shots_per90", "Tiri totali per 90 dei top player", 10, "player_season_profiles.top_shooters_shots_per90"),
            _micro("top_sot_share", "Quota SOT squadra prodotta dai top player", 15, "player_season_profiles.top_shooters_sot_share"),
            _micro("top_shots_share", "Quota tiri squadra prodotta dai top player", 8, "player_season_profiles.top_shooters_shots_share"),
            _micro("offensive_recent_minutes", "Minuti recenti dei giocatori offensivi", 8, "player_season_profiles.offensive_recent_minutes"),
            _micro("offensive_avg_rating", "Rating medio giocatori offensivi", 7, "player_season_profiles.offensive_avg_rating"),
            _micro("top_profile_reliability", "Affidabilità profili top player", 6, "player_season_profiles.top_profile_reliability"),
            _micro("top_shooter_presence", "Presenza dei top shooter", 8, "lineup_impact.top_shooter_presence"),
            _micro("player_layer_top_shooter_absence", "Assenza dei top shooter", 18, "lineup_impact.top_shooter_absence"),
        ),
    ),
    V21MacroAreaSpec(
        key="lineups",
        label="Lineups / formazioni",
        macro_weight=5,
        micros=(
            _micro("official_lineup", "Formazione ufficiale", 29, "sportapi_lineups.official"),
            _micro("confirmed_starters", "Titolari confermati", 10, "sportapi_lineups.confirmed_starters"),
            _micro("bench", "Panchina", 1, "sportapi_lineups.bench"),
            _micro("tactical_module", "Modulo tattico", 15, "sportapi_lineups.formation"),
            _micro("module_change_vs_avg", "Cambio modulo rispetto alla media", 5, "sportapi_lineups.module_change_vs_avg"),
            _micro("attackers_starters", "Presenza attaccanti/trequartisti titolari", 25, "sportapi_lineups.attackers_in_starters"),
            _micro("offensive_defensive_turnover", "Turnover offensivo/difensivo", 15, "sportapi_lineups.turnover_offensive_defensive"),
        ),
    ),
    V21MacroAreaSpec(
        key="injuries_unavailable",
        label="Infortuni / indisponibili",
        macro_weight=5,
        micros=(
            _micro("injured", "Infortunati", 14, "sportapi_lineups.injured_players"),
            _micro("suspended", "Squalificati", 10, "sportapi_lineups.suspended_players"),
            _micro("unavailable", "Indisponibili", 5, "sportapi_lineups.unavailable_players"),
            _micro("absent_player_weight", "Peso del giocatore assente", 17, "lineup_impact.absent_player_weight"),
            _micro("starter_vs_bench_absence", "Assenza titolare vs panchinaro", 14, "lineup_impact.starter_vs_bench_absence"),
            _micro("injuries_top_shooter_absence", "Assenza top shooter", 16, "lineup_impact.top_shooter_absence"),
            _micro("key_defender_absence_opp", "Assenza difensore chiave avversario", 14, "lineup_impact.opponent_key_defender_absence"),
            _micro("important_returns", "Rientri importanti", 10, "sportapi_lineups.important_returns"),
        ),
    ),
    V21MacroAreaSpec(
        key="pace_control",
        label="Ritmo e controllo partita",
        macro_weight=5,
        micros=(
            _micro("avg_possession", "Possesso palla medio", 15, "team_stats.season_avg_possession"),
            _micro("total_passes", "Passaggi totali", 5, "team_stats.season_avg_passes"),
            _micro("passes_completed", "Passaggi riusciti", 5, "team_stats.season_avg_passes_completed"),
            _micro("pass_accuracy", "Precisione passaggi", 15, "team_stats.season_pass_accuracy"),
            _micro("territorial_control", "Controllo territoriale", 25, "team_stats.territorial_control_index"),
            _micro("estimated_pace", "Ritmo stimato della squadra", 35, "team_stats.estimated_pace"),
        ),
    ),
    V21MacroAreaSpec(
        key="model_quality_controls",
        label="Controlli qualità / sicurezza modello",
        macro_weight=4,
        is_quality_only=True,
        micros=(
            _quality_micro("sample_count", "Sample count per ogni variabile", "quality.sample_count_by_variable"),
            _quality_micro("fallbacks_used", "Fallback usati", "quality.fallbacks_used"),
            _quality_micro("missing_data", "Dati mancanti", "quality.missing_data_flags"),
            _quality_micro("no_data_leakage", "No data leakage", "quality.no_data_leakage_check"),
            _quality_micro("source_path_audit", "Source path per ogni variabile", "quality.source_path_audit"),
            _quality_micro("formula_quality_status", "Formula quality status", "quality.formula_quality_status"),
            _quality_micro("suspicious_value_warnings", "Warning su valori sospetti", "quality.suspicious_value_warnings"),
        ),
    ),
)
