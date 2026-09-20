"""Costanti della V4, fissate prima dei risultati (docs/v4/REGOLE.md, docs/v4/ROADMAP.md).

Unico punto di verita' per campionati, stagioni, mercati, statistiche e soglie.
"""

from __future__ import annotations

from dataclasses import dataclass

MODULE_VERSION = "cecchino_v4_v1"

# --- Stagioni ------------------------------------------------------------------
# 2021/22 rodaggio, 2022/23-2024/25 giudizio, 2025/26 sotto chiave (solo input live).
SEASON_CODES: dict[str, str] = {
    "2122": "2021/2022",
    "2223": "2022/2023",
    "2324": "2023/2024",
    "2425": "2024/2025",
    "2526": "2025/2026",
    "2627": "2026/2027",
}
WARMUP_SEASON = "2021/2022"
JUDGE_SEASONS: tuple[str, ...] = ("2022/2023", "2023/2024", "2024/2025")
LOCKBOX_SEASON = "2025/2026"
# Stagione in corso (live): mai usata per stimare nulla, solo input walk-forward e giudizio prospettico.
CURRENT_SEASON = "2026/2027"
CURRENT_SEASON_API = 2026  # parametro `season` di API-Football
HISTORY_SEASONS: tuple[str, ...] = (WARMUP_SEASON, *JUDGE_SEASONS)  # mai il lockbox negli esami
# Stagioni che il live puo' leggere come input (tutte quelle giocate): storico + lockbox + corrente.
LIVE_INPUT_SEASONS: tuple[str, ...] = (*HISTORY_SEASONS, LOCKBOX_SEASON, CURRENT_SEASON)


def is_lockbox(season_label: str | None) -> bool:
    return bool(season_label) and str(season_label) >= LOCKBOX_SEASON


# --- I 16 campionati -------------------------------------------------------------
@dataclass(frozen=True)
class League:
    code: str  # codice football-data (E0, I1, ...)
    competition: str  # nome come nel Lab / V3 (COUNTRY_GROUPS)
    country: str
    tier: int
    api_football_league_id: int  # id API-Football; verificato al deploy con /leagues


LEAGUES: tuple[League, ...] = (
    League("E0", "Premier League", "england", 1, 39),
    League("E1", "Championship", "england", 2, 40),
    League("E2", "League One", "england", 3, 41),
    League("E3", "League Two", "england", 4, 42),
    League("I1", "Serie A", "italy", 1, 135),
    League("I2", "Serie B", "italy", 2, 136),
    League("SP1", "La Liga", "spain", 1, 140),
    League("SP2", "La Liga 2", "spain", 2, 141),
    League("D1", "Bundesliga", "germany", 1, 78),
    League("D2", "Bundesliga 2", "germany", 2, 79),
    League("F1", "Ligue 1", "france", 1, 61),
    League("F2", "Ligue 2", "france", 2, 62),
    League("N1", "Eredivisie", "netherlands", 1, 88),
    League("B1", "Jupiler Pro League", "belgium", 1, 144),
    League("P1", "Primeira Liga", "portugal", 1, 94),
    League("T1", "Süper Lig", "turkey", 1, 203),
)
LEAGUE_BY_CODE: dict[str, League] = {lg.code: lg for lg in LEAGUES}
LEAGUE_BY_API_ID: dict[int, League] = {lg.api_football_league_id: lg for lg in LEAGUES}
LEAGUE_BY_COMPETITION: dict[str, League] = {lg.competition: lg for lg in LEAGUES}

# --- Mercati classici (stessi 17 della V3) + handicap asiatico ---------------------
CLASSIC_MARKETS: tuple[str, ...] = (
    "HOME",
    "DRAW",
    "AWAY",
    "ONE_X",
    "X_TWO",
    "ONE_TWO",
    "OVER_0_5",
    "UNDER_0_5",
    "OVER_1_5",
    "UNDER_1_5",
    "OVER_2_5",
    "UNDER_2_5",
    "OVER_3_5",
    "UNDER_3_5",
    "HOME_PT",
    "DRAW_PT",
    "AWAY_PT",
)
MARKET_FAMILY: dict[str, str] = {
    **{k: "FT_1X2" for k in ("HOME", "DRAW", "AWAY")},
    **{k: "DOUBLE_CHANCE" for k in ("ONE_X", "X_TWO", "ONE_TWO")},
    **{k: "FT_OVER_UNDER" for k in CLASSIC_MARKETS if k.startswith(("OVER", "UNDER"))},
    **{k: "HT_1X2" for k in ("HOME_PT", "DRAW_PT", "AWAY_PT")},
}
# Handicap asiatico: mercato "AH_HOME"/"AH_AWAY" con linea (es. -0.5, +0.25).
AH_MARKETS: tuple[str, ...] = ("AH_HOME", "AH_AWAY")
# Solo linee a meta' (decisione dell'utente, 20/09/2026): niente quarti, niente interi, niente linea zero.
AH_LINES: tuple[float, ...] = (-2.5, -1.5, -0.5, 0.5, 1.5, 2.5)

# --- Statistiche (mercati speciali) ------------------------------------------------
# chiave -> etichetta italiana
STATS: dict[str, str] = {
    "shots": "tiri",
    "sot": "tiri in porta",
    "corners": "corner",
    "cards": "cartellini",
    "fouls": "falli",
}
STAT_SIDES: tuple[str, ...] = ("home", "away", "total")
# Linee mostrate nella tab (probabilita' calcolabile per qualunque mezza linea).
STAT_LINES: dict[str, tuple[float, ...]] = {
    "shots": tuple(x + 0.5 for x in range(5, 35)),
    "sot": tuple(x + 0.5 for x in range(1, 16)),
    "corners": tuple(x + 0.5 for x in range(2, 16)),
    "cards": tuple(x + 0.5 for x in range(0, 10)),
    "fouls": tuple(x + 0.5 for x in range(5, 35)),
}
# Cartellini: giallo 1, rosso 2 (stesso peso di Disciplina V3).
CARD_WEIGHT_YELLOW = 1.0
CARD_WEIGHT_RED = 2.0

# --- Strato 2: probabilita' ------------------------------------------------------
# Incertezza a posteriori: partite equivalenti minime per considerare una squadra "nota".
EVIDENCE_FULL_KNOWLEDGE = 15.0
# Calibrazione isotonica per mercato: stimata sulla stagione precedente, identita' nel rodaggio.
CALIBRATION_MIN_ROWS = 300
# Dispersione binomiale negativa per divisione e statistica: stimata sulla stagione precedente.
DISPERSION_MIN_ROWS = 200

# --- Strato 3: selezione (decisioni dell'utente, 19/09/2026) -----------------------
PROFIT_MARGIN = 0.03  # p_prudente * quota >= 1 + margine
MAX_PLAYS_PER_DAY = 50
TOP_PLAYS = 15
PLAYS_PER_MATCH = 1
MIN_QUOTA = 1.20  # sotto, il profitto atteso non compensa il rischio di quota

VERDICT_PLAYABLE = "giocabile"
VERDICT_FAIR_PRICE = "prezzo_giusto"
VERDICT_UNCERTAIN = "incertezza_alta"
VERDICT_NO_ODDS = "non_quotato"
VERDICT_DESCRIPTIVE = "solo_descrittivo"
VERDICT_LINEUPS_PENDING = "formazioni_non_note"
VERDICT_ANOMALOUS = "quota_anomala"  # quota x probabilita' del modello oltre ANOMALY_RATIO: quasi certamente un errore di lettura
ANOMALY_RATIO = 2.5
VERDICT_LABELS: dict[str, str] = {
    VERDICT_PLAYABLE: "Giocabile",
    VERDICT_FAIR_PRICE: "Prezzo giusto",
    VERDICT_UNCERTAIN: "Incertezza alta",
    VERDICT_NO_ODDS: "Non quotato",
    VERDICT_DESCRIPTIVE: "Solo descrittivo",
    VERDICT_LINEUPS_PENDING: "Formazioni non note",
    VERDICT_ANOMALOUS: "Quota anomala",
}

# Stati della shortlist
SHORTLIST_PROVISIONAL = "provvisoria"
SHORTLIST_CONFIRMED = "confermata"
SHORTLIST_WITHDRAWN = "ritirata"
SHORTLIST_SETTLED = "regolata"

# --- Strato 1: pipeline live / registro quote -------------------------------------
BOOKMAKER_BET365_ID = 8  # id API-Football; verificato al deploy con /odds/bookmakers
BOOKMAKER_BETFAIR_ID = 3
BOOKMAKERS: dict[int, str] = {BOOKMAKER_BET365_ID: "Bet365", BOOKMAKER_BETFAIR_ID: "Betfair"}
ODDS_SNAPSHOT_KINDS: tuple[str, ...] = ("mattina", "pomeriggio", "sera", "chiusura")
CLOSING_MINUTES_BEFORE_KICKOFF = 30
LINEUPS_MINUTES_BEFORE_KICKOFF: tuple[int, ...] = (60, 30)
FIXTURE_HORIZON_DAYS = 7

# Budget API-Football: un solo contatore giornaliero; la V4 si ferma da sola oltre questa soglia.
API_DAILY_STOP = 7000


# --- Risultati degli esami ---------------------------------------------------------
# Railway pubblica solo `backend/`: i JSON degli esami vivono qui (letti da motori, selezione e rotte);
# gli script degli esami ne scrivono una copia leggibile anche in docs/v4/esami/.
from pathlib import Path as _Path  # noqa: E402

_HERE = _Path(__file__).resolve()
BACKEND_DIR = _HERE.parents[3]  # .../backend (su Railway e' /app: non ha una cartella padre del repo)
# Radice del repository se esiste (sviluppo locale), altrimenti la cartella backend stessa (container).
REPO_ROOT = _HERE.parents[4] if len(_HERE.parents) > 4 and (_HERE.parents[4] / "docs").exists() else BACKEND_DIR
EXAMS_DATA_DIR = BACKEND_DIR / "app" / "data" / "v4" / "esami"
EXAMS_DOCS_DIR = REPO_ROOT / "docs" / "v4" / "esami"
