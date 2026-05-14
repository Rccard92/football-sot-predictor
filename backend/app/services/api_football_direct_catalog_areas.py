"""Classificazione macro-area per endpoint + json_path."""

from __future__ import annotations


def classify_macro_area(endpoint: str, json_path: str) -> str:
    ep = endpoint.strip().lower()
    jp = json_path.lower()

    if ep in ("fixtures", "fixtures/rounds", "fixtures/headtohead"):
        return "fixtures"
    if ep == "fixtures/statistics":
        return "team_statistics_match"
    if ep == "fixtures/events":
        return "match_events"
    if ep == "fixtures/lineups":
        return "lineups"
    if ep == "fixtures/players":
        return "player_statistics"
    if ep == "teams":
        return "teams"
    if ep == "teams/statistics":
        return "teams_season_stats"
    if ep == "venues":
        return "venues"
    if ep == "standings":
        return "standings"
    if ep in ("injuries", "sidelined"):
        return "injuries_availability"
    if ep.startswith("odds"):
        return "odds"
    if ep == "predictions":
        return "predictions_provider"
    if ep in ("coachs", "coaches"):
        return "coaches_transfers_misc"
    if ep in ("transfers", "trophies"):
        return "coaches_transfers_misc"
    if ep.startswith("players"):
        return "player_statistics"
    if ep in ("status", "timezone", "countries", "leagues", "seasons"):
        return "leagues_seasons_general"

    if "fixture" in jp and ep != "fixtures/players":
        return "fixtures"
    return "other"


AREA_ORDER: list[tuple[str, str]] = [
    ("fixtures", "Partite / fixture"),
    ("teams", "Squadre"),
    ("leagues_seasons_general", "Campionati / stagioni / generali"),
    ("team_statistics_match", "Statistiche squadra (partita)"),
    ("match_events", "Eventi partita"),
    ("lineups", "Formazioni"),
    ("player_statistics", "Statistiche giocatori"),
    ("teams_season_stats", "Statistiche squadra (stagione)"),
    ("venues", "Stadi"),
    ("standings", "Classifiche"),
    ("injuries_availability", "Infortuni / indisponibili"),
    ("odds", "Quote"),
    ("predictions_provider", "Predictions provider"),
    ("coaches_transfers_misc", "Allenatori / trasferimenti / trofei"),
    ("other", "Altro"),
]
