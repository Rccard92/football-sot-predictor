"""Regole della Fase 1, fissate PRIMA di vedere qualsiasi risultato.

Ogni scelta qui e' strutturale: i numeri veri (forze delle squadre, vantaggio
casa, correzione pareggi, quota gol primo tempo) li stima il modello partita
dopo partita usando solo le partite gia' giocate.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.services.cecchino_data_lab.run_v2_scope import LOCKBOX_SEASON

ENGINE_VERSION = "cecchino_v3_phase1_strength_v1"
ENGINE_VERSION_PHASE2 = "cecchino_v3_phase2_game_v1"
ENGINE_VERSION_PHASE3 = "cecchino_v3_phase3_form_v1"
ENGINE_VERSION_PHASE4 = "cecchino_v3_phase4_calendar_v1"
ENGINE_VERSION_PHASE5 = "cecchino_v3_phase5_discipline_v1"
ENGINE_VERSION_PHASE6 = "cecchino_v3_phase6_promotion_v1"
ENGINE_VERSION_PHASE7 = "cecchino_v3_phase7_calibration_v1"
ENGINE_VERSION_PHASE8 = "cecchino_v3_phase7b_calibration_total_v1"
PHASES: tuple[int, ...] = (1, 2, 3, 4, 5, 6, 7, 8)
# Etichette per l'utente quando il numero interno non coincide con il nome.
PHASE_LABELS: dict[int, str] = {8: "7b"}


@dataclass(frozen=True)
class PhaseFeatures:
    """Componenti attive in ogni fase."""

    game: bool = False
    form: bool = False
    calendar: bool = False
    discipline: bool = False
    promotion: bool = False
    calibration: bool = False
    calibration_preserve_total: bool = False


# La Fase 5 (Disciplina) non e' stata adottata: la Fase 6 riparte dalla Fase 4.
# La Fase 6 (neopromosse) non ha superato l'esame rigoroso: prima di vedere
# qualsiasi risultato della calibrazione, la Fase 7 e' ridefinita come
# Fase 4 (modello di riferimento) + calibrazione, confrontata con la Fase 4.
PHASE_FEATURES: dict[int, PhaseFeatures] = {
    1: PhaseFeatures(),
    2: PhaseFeatures(game=True),
    3: PhaseFeatures(game=True, form=True),
    4: PhaseFeatures(game=True, form=True, calendar=True),
    5: PhaseFeatures(game=True, form=True, calendar=True, discipline=True),
    6: PhaseFeatures(game=True, form=True, calendar=True, promotion=True),
    7: PhaseFeatures(game=True, form=True, calendar=True, calibration=True),
    # Fase 7b (numero interno 8): la Fase 7 non ha superato l'esame perche' allargare
    # la differenza di forza a livello medio fisso aumenta i gol totali nelle partite
    # sbilanciate. Seconda e unica prova, approvata dall'utente e fissata prima dei
    # risultati: stessa calibrazione a gol totali invariati (fattore globale gamma),
    # stessa regola d'esame rigorosa, confronto con la Fase 4.
    8: PhaseFeatures(game=True, form=True, calendar=True, calibration=True, calibration_preserve_total=True),
}
# Termine di paragone dell'esame di ogni fase.
PHASE_BASELINE: dict[int, int] = {2: 1, 3: 2, 4: 3, 5: 4, 6: 4, 7: 4, 8: 4}

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

# --- Fase 2: specialista Gioco (dichiarato prima dei risultati) --------------
# Statistiche di gioco usate e tasso di conversione a priori in gol (medie
# tipiche del calcio europeo; i dati le sovrascrivono per ogni divisione).
GAME_STATS: tuple[str, ...] = ("sot", "shots")
PRIOR_GOALS_PER_STAT: dict[str, float] = {"sot": 0.32, "shots": 0.11}
CONVERSION_PSEUDO_COUNT: dict[str, float] = {"sot": 60.0, "shots": 180.0}
# Orchestratore: log(gol attesi) = a + b_forza*log(forza) + b_sot*log(sot) + b_tiri*log(tiri)
# pesi stimati sulla stagione precedente; nel rodaggio vale solo la Forza.
ORCHESTRATOR_INPUTS: tuple[str, ...] = ("forza", "sot", "shots")
ORCHESTRATOR_DEFAULT_WEIGHTS: dict[str, float] = {"intercept": 0.0, "forza": 1.0, "sot": 0.0, "shots": 0.0}
ORCHESTRATOR_PRIOR_PRECISION = 1.0
# Esame Fase 2: con lo specialista Gioco l'errore deve scendere rispetto alla
# sola Forza (calcolo Fase 1) in ogni famiglia e in tutte le stagioni di
# giudizio; calibrazione entro lo stesso limite della Fase 1.
# Esito: 11 controlli migliorati su 12, 1X2 primo tempo 2022/23 in pareggio
# esatto -> formalmente non superato, specialista accettato dall'utente
# (opzione A) con la richiesta di una tolleranza esplicita dalle fasi successive.

# --- Fase 3: specialista Forma (dichiarato prima dei risultati) --------------
# Ultime N partite della squadra nella stagione in corso: scarto tra quanto
# fatto e quanto atteso prima di ciascuna partita (gol e tiri, fatti e
# subiti), trattenuto verso zero con un conteggio a priori.
FORM_MATCHES = 5
FORM_PSEUDO_COUNT: dict[str, float] = {"goals": 5.0, "shots": 30.0}
# Correzioni aggiunte all'orchestratore (peso di partenza 0).
FORM_ADJUSTMENTS: tuple[str, ...] = ("form_goals", "form_shots")

# Esame dalla Fase 3 in poi, rispetto alla fase precedente:
# 1) in ogni famiglia e stagione di giudizio errore non peggiore di +0,1%;
# 2) in ogni famiglia errore piu' basso in media sulle stagioni di giudizio;
# 3) calibrazione entro EXAM_MAX_CALIBRATION_ERROR_PCT.
EXAM_TOLERANCE_PCT = 0.1

# --- Fase 4: specialista Calendario (dichiarato prima dei risultati) ---------
# Giorni di riposo limitati tra 2 e 10 e misurati rispetto a una settimana;
# fase finale = ultime FINAL_PHASE_MATCHES giornate. Stessa regola d'esame
# con tolleranza della Fase 3, rispetto alla Fase 3.
REST_FLOOR_DAYS = 2
REST_CAP_DAYS = 10
REST_REFERENCE_DAYS = 7
CALENDAR_ADJUSTMENTS: tuple[str, ...] = ("rest_attack", "rest_defence", "final_phase")

# --- Fase 5: specialista Disciplina (dichiarato prima dei risultati) ---------
# Falli e cartellini (giallo 1, rosso 2) di squadra nella stagione in corso
# rispetto alla media della divisione, con 5 partite "nella media" a priori;
# arbitro (solo campionati inglesi nei dati): gol nelle sue partite passate
# rispetto ai gol attesi, con 20 gol a priori. Stessa regola d'esame con
# tolleranza, rispetto alla Fase 4.
DISCIPLINE_PSEUDO_MATCHES = 5.0
DISCIPLINE_PRIOR_FOULS = 11.5  # falli per squadra a partita
DISCIPLINE_PRIOR_CARDS = 2.1  # cartellini pesati per squadra a partita
REFEREE_PSEUDO_GOALS = 20.0
DISCIPLINE_ADJUSTMENTS: tuple[str, ...] = ("fouls_attack", "fouls_defence", "cards_defence", "referee_goals")

# --- Passo 1 della rifinitura (dichiarato prima dei risultati) ---------------
# Fase 6 - neopromosse e retrocesse: 4 parametri (attacco/difesa di chi e'
# salito o sceso di divisione rispetto alla stagione precedente), attivi per
# tutta la prima stagione nella nuova divisione, stimati dentro Forza e Gioco
# dalle partite passate; a priori 0 con deviazione 0,5.
PROMOTION_PRIOR_PRECISION = 4.0
# Fase 7 - calibrazione: sui gol attesi dell'orchestratore
#   s = log(casa) - log(ospite)  (differenza di forza)
#   m = (log(casa) + log(ospite)) / 2  (livello gol)
#   s' = alpha * s + beta ;  m' = m + gamma
# stimati sui risultati esatti (verosimiglianza Dixon-Coles) delle previsioni
# fuori campione della stagione precedente, non calibrate; identita' nel rodaggio.
CALIBRATION_ALPHA_BOUNDS = (0.5, 2.0)
CALIBRATION_SHIFT_BOUNDS = (-0.5, 0.5)

# --- Regola d'esame rigorosa (approvata dall'utente, valida dalla Fase 6) ----
# Oltre a tolleranza e calibrazione:
# - su 1X2 finale e Over/Under miglioramento medio di almeno lo 0,05%;
# - parametri stabili: nessun cambio di segno tra le stagioni di giudizio
#   (valori con |v| < 0,01 considerati zero).
EXAM_STRICT_FROM_PHASE = 6
EXAM_MAIN_FAMILIES: tuple[str, ...] = ("FT_1X2", "FT_OVER_UNDER")
EXAM_MIN_MEAN_GAIN_PCT = 0.05
EXAM_STABILITY_NEUTRAL = 0.01
