"""Regole della Fase 1, fissate PRIMA di vedere qualsiasi risultato.

Ogni scelta qui e' strutturale: i numeri veri (forze delle squadre, vantaggio
casa, correzione pareggi, quota gol primo tempo) li stima il modello partita
dopo partita usando solo le partite gia' giocate.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.services.cecchino_data_lab.run_v2_scope import LOCKBOX_SEASON

ENGINE_VERSION = "cecchino_v3_phase1_strength_v1"

# --- Stagioni -----------------------------------------------------------------
# 2021/22: rodaggio (il modello impara, non entra nel giudizio).
# 2022/23 – 2024/25: giudizio. 2025/26: sotto chiave, mai caricata.
WARMUP_SEASON = "2021/2022"
JUDGE_SEASONS: tuple[str, ...] = ("2022/2023", "2023/2024", "2024/2025")
LOCKBOX = LOCKBOX_SEASON

# --- Regole partita (decise con l'utente) ---------------------------------------
MIN_MATCHES_PLAYED = 5  # entrambe le squadre, stessa stagione e campionato
FINAL_PHASE_MATCHES = 5  # ultime 5 giornate = fase finale

PHASE_EARLY = "early"
PHASE_MID = "mid"
PHASE_FINAL = "final"

# --- Piramidi nazionali ------------------------------------------------------
# Le divisioni dello stesso paese stanno in un unico modello: le squadre
# promosse e retrocesse si portano dietro la forza stimata. Ordine = livello.
COUNTRY_GROUPS: dict[str, tuple[str, ...]] = {
    "england": ("Premier League", "Championship", "League One", "League Two"),
    "italy": ("Serie A", "Serie B"),
    "spain": ("La Liga", "La Liga 2"),
    "germany": ("Bundesliga", "Bundesliga 2"),
    "france": ("Ligue 1", "Ligue 2"),
    "netherlands": ("Eredivisie",),
    "belgium": ("Jupiler Pro League",),
    "portugal": ("Primeira Liga",),
    "turkey": ("Süper Lig",),
}


def group_of(competition: str) -> str:
    for group, divisions in COUNTRY_GROUPS.items():
        if competition in divisions:
            return group
    return f"single:{competition}"


# --- Iperparametri --------------------------------------------------------------
@dataclass(frozen=True)
class Hyper:
    """xi: velocita' con cui una partita "invecchia" (per giorno).
    sigma: quanto una squadra puo' allontanarsi a priori dalla media della
    sua divisione (scala logaritmica dei gol)."""

    xi: float
    sigma: float

    @property
    def key(self) -> str:
        return f"xi={self.xi:g}|sigma={self.sigma:g}"


# Intervalli ammessi. La scelta per la stagione S e' quella che ha previsto
# meglio la stagione S-1 (solo passato). Nel rodaggio si usa il default.
HYPER_GRID: tuple[Hyper, ...] = tuple(
    Hyper(xi=xi, sigma=sigma) for xi in (0.001, 0.002, 0.004) for sigma in (0.2, 0.4)
)
DEFAULT_HYPER = Hyper(xi=0.002, sigma=0.2)

# Pesi sotto questa soglia escono dalla finestra (partite troppo vecchie).
MIN_TIME_WEIGHT = 1e-3

# Valori di partenza a priori (deboli: i dati li sovrascrivono in poche giornate).
PRIOR_LOG_GOALS = 0.26  # ~1,3 gol per squadra
PRIOR_HOME_ADVANTAGE = 0.2
PRIOR_HT_SHARE = 0.45  # quota dei gol nel primo tempo
HT_SHARE_PSEUDO_GOALS = 20.0

# Correzione pareggi Dixon-Coles: intervallo ammesso.
RHO_GRID_MIN = -0.2
RHO_GRID_MAX = 0.2
RHO_GRID_STEP = 0.01

MAX_GOALS = 10

MARKET_KEYS: tuple[str, ...] = (
    "HOME",
    "DRAW",
    "AWAY",
    "HOME_PT",
    "DRAW_PT",
    "AWAY_PT",
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
)

MARKET_FAMILY: dict[str, str] = {
    "HOME": "FT_1X2",
    "DRAW": "FT_1X2",
    "AWAY": "FT_1X2",
    "ONE_X": "DOUBLE_CHANCE",
    "X_TWO": "DOUBLE_CHANCE",
    "ONE_TWO": "DOUBLE_CHANCE",
    "OVER_0_5": "FT_OVER_UNDER",
    "UNDER_0_5": "FT_OVER_UNDER",
    "OVER_1_5": "FT_OVER_UNDER",
    "UNDER_1_5": "FT_OVER_UNDER",
    "OVER_2_5": "FT_OVER_UNDER",
    "UNDER_2_5": "FT_OVER_UNDER",
    "OVER_3_5": "FT_OVER_UNDER",
    "UNDER_3_5": "FT_OVER_UNDER",
    "HOME_PT": "HT_1X2",
    "DRAW_PT": "HT_1X2",
    "AWAY_PT": "HT_1X2",
}

# --- Esame della Fase 1 (dichiarato prima dei risultati) ----------------------
# 1) In ogni famiglia di mercato la V3 deve avere un errore (Brier) piu' basso
#    della V2 in TUTTE le stagioni di giudizio, sulle stesse partite.
# 2) Calibrazione: errore medio di calibrazione <= 2 punti percentuali su
#    1X2 finale e Over/Under (stagioni di giudizio insieme).
EXAM_FAMILIES: tuple[str, ...] = ("FT_1X2", "DOUBLE_CHANCE", "FT_OVER_UNDER", "HT_1X2")
EXAM_CALIBRATION_FAMILIES: tuple[str, ...] = ("FT_1X2", "FT_OVER_UNDER")
EXAM_MAX_CALIBRATION_ERROR_PCT = 2.0
CALIBRATION_BINS = 10
