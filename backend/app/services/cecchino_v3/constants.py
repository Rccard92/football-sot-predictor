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
ENGINE_VERSION_PHASE9 = "cecchino_v3_final_lockbox_v1"
PHASES: tuple[int, ...] = (1, 2, 3, 4, 5, 6, 7, 8, 9)
# Etichette per l'utente quando il numero interno non coincide con il nome.
PHASE_LABELS: dict[int, str] = {8: "7b", 9: "Finale 2025/26"}


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
    lockbox: bool = False  # include la stagione sotto chiave (solo calcolo finale)


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
    # Calcolo finale: modello di riferimento (Fase 4) identico, stesse regole
    # walk-forward, esteso alla stagione sotto chiave 2025/26. Nessun parametro nuovo.
    9: PhaseFeatures(game=True, form=True, calendar=True, lockbox=True),
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

# --- Passo 2: indici a 360 gradi (dichiarati prima di calcolarli) ------------
# Indici descrittivi letti dal modello di riferimento: non cambiano le probabilita'.
# Posizione rispetto al campionato: percentile tra le partite dei giorni
# precedenti dello stesso campionato, solo con almeno INDEX_MIN_HISTORY valori.
INDEX_MIN_HISTORY = 200
INDEX_CLASS_EDGES: tuple[float, ...] = (20.0, 40.0, 60.0, 80.0)
INDEX_CLASSES: tuple[str, ...] = ("molto_basso", "basso", "medio", "alto", "molto_alto")
# Affidabilita' della stima, versione 2 (la v1 non ha superato C4: misurava
# quanto una partita e' prevedibile, non quanto la stima e' solida).
# Nessuna quota entra nel calcolo. Domanda: "quanto possiamo fidarci delle
# probabilita' che gli agenti hanno prodotto per QUESTA partita?"
# Segnali di incertezza, tutti pre-partita e dai dati degli agenti:
#   poca_conoscenza  = 1 / sqrt(1 + partite equivalenti della squadra meno conosciuta)
#   disaccordo_forza = differenza massima tra specialisti su log(gol casa / gol ospite)
#   disaccordo_gol   = differenza massima tra specialisti su log(gol totali)
#   squadra_nuova    = 1 se una squadra e' neopromossa o nuova nel dataset
#   inizio_stagione  = 1 se una squadra ha meno di 5 partite giocate
#   irregolarita     = scarti quadratici (gol fatti e subiti - attesi) / gol attesi,
#                      ultime 10 partite delle due squadre (1 = regolare come Poisson)
# Quanto pesa ogni segnale lo decidono i dati, walk-forward: per la stagione S
# si stimano pesi >= 0 sulle stagioni precedenti, con obiettivo l'ERRORE IN
# ECCESSO 1X2 = Brier reale - Brier atteso dal modello stesso (1 - somma p^2)/3.
# L'errore in eccesso non dipende da quanto la partita e' prevedibile: una
# partita equilibrata ha errore atteso alto ma, se la stima e' solida, eccesso ~0.
# Valore 0-100 = 100 - percentile del rischio tra le partite delle stagioni di stima.
# Prima stagione (rodaggio): nessun peso stimabile -> affidabilita' non disponibile.
RELIABILITY_COMPONENTS: tuple[str, ...] = (
    "poca_conoscenza",
    "disaccordo_forza",
    "disaccordo_gol",
    "squadra_nuova",
    "inizio_stagione",
    "irregolarita",
)
RELIABILITY_IRREGULARITY_MATCHES = 10
RELIABILITY_IRREGULARITY_MIN_MATCHES = 3
RELIABILITY_HIGH = 70.0  # alta = 30% delle partite piu' solide (rispetto alla stima)
RELIABILITY_MEDIUM = 30.0  # bassa = 30% delle partite meno solide
# Segno sostenuto dagli agenti: il segno piu' probabile del modello e quanti
# specialisti (Forza, tiri in porta, tiri), ognuno da solo, lo vedono come il
# piu' probabile. Forma concorde/contraria se la differenza di forma di gioco
# supera questa soglia (log rapporto) nella direzione del segno.
RELIABILITY_FORM_NEUTRAL = 0.05
# Controlli di coerenza sulle stagioni di giudizio (partite idonee):
# C1 intensita' goal -> gol reali medi sempre crescenti tra le 5 classi
# C2 credibilita' pareggio -> frequenza pareggi sempre crescente tra le 5 classi
# C3 equilibrio -> vittorie del favorito sempre decrescenti tra le 5 classi
# Esame affidabilita' v2 (fissato prima del calcolo):
# R1 errore in eccesso 1X2 sempre decrescente bassa -> media -> alta
# R2 in ognuna delle 3 stagioni di giudizio: eccesso bassa > eccesso alta
# R3 ogni classe contiene almeno il 15% delle partite
# R4 eccesso di fiducia sul segno piu' probabile (prob. - frequenza reale)
#    sempre decrescente bassa -> media -> alta
RELIABILITY_MIN_CLASS_SHARE = 0.15
INDEX_ENGINE_VERSION = "cecchino_v3_indices_v2"

# --- Passo 3: valutatore di mercato (dichiarato prima di calcolare) ----------
# E' l'unico punto in cui entrano le quote. Le probabilita' degli agenti non
# cambiano: il valutatore decide soltanto quali mercati sono giocabili.
#
# A) Probabilita' del valutatore. Per ogni mercato, regressione logistica
#    stimata SOLO sulle stagioni precedenti (partite idonee):
#      logit P(vinto) = a + b * logit(p_book) + c * (logit(p_V3) - logit(p_book))
#    p_book = probabilita' della quota senza margine. c > 0 significa che la
#    V3 sa qualcosa che la quota non contiene. Prima stagione: nessun modello.
# Esame I (informazione oltre il mercato), per 1X2 finale e Over/Under 2.5:
#    I1 log-loss della probabilita' del valutatore < log-loss del book in ognuna
#       delle 3 stagioni di giudizio;
#    I2 c stimato su ogni singola stagione di giudizio > 0 con limite inferiore
#       dell'intervallo al 95% > 0 (errore robusto per partita).
#
# B) Giocate. Candidato = mercato con quota tra 1,30 e 5,00, partita idonea,
#    valore atteso p * quota - 1 >= 5%. Una sola giocata per partita (valore
#    piu' alto), al massimo 15 giocate per giorno di calendario (valore piu' alto).
#    Fase finale (ultime 5 giornate) no-bet per una famiglia nella stagione S se,
#    nelle stagioni precedenti con modello, in fase finale il valutatore non ha
#    migliorato il log-loss del book (nessuno storico: fase finale ammessa).
#    Strategie:
#      VALUTATORE_PRINCIPALI  probabilita' del valutatore, mercati con quota di
#                             chiusura (1, X, 2, Over 2.5, Under 2.5)  -> esame G
#      V3_PURA_PRINCIPALI     probabilita' V3 senza correzione, stessi mercati
#                             (solo confronto)
#      VALUTATORE_TUTTI       probabilita' del valutatore, tutti i 17 mercati
#                             (altri mercati: ultima quota rilevata; solo confronto)
# Esame G (giocabilita' alla chiusura nei 16 campionati), VALUTATORE_PRINCIPALI:
#    G1 ROI > 0 in ognuna delle 3 stagioni di giudizio;
#    G2 ROI complessivo con limite inferiore dell'intervallo al 95% > 0;
#    G3 almeno 300 giocate complessive.
EVALUATOR_ENGINE_VERSION = "cecchino_v3_evaluator_v1"
EVALUATOR_MIN_ODDS = 1.30
EVALUATOR_MAX_ODDS = 5.00
EVALUATOR_MIN_EDGE = 0.05
EVALUATOR_MAX_PLAYS_PER_DAY = 15
EVALUATOR_MIN_TRAIN_ROWS = 500
EVALUATOR_L2 = 1e-3
EVALUATOR_PROB_CLIP = 1e-4
EVALUATOR_MIN_PLAYS = 300
EVALUATOR_PRINCIPAL_MARKETS: tuple[str, ...] = ("HOME", "DRAW", "AWAY", "OVER_2_5", "UNDER_2_5")
EVALUATOR_INFO_FAMILIES: dict[str, tuple[str, ...]] = {
    "FT_1X2": ("HOME", "DRAW", "AWAY"),
    "OU_2_5": ("OVER_2_5",),
}
STRATEGY_MAIN = "VALUTATORE_PRINCIPALI"
STRATEGY_V3_PURE = "V3_PURA_PRINCIPALI"
STRATEGY_ALL = "VALUTATORE_TUTTI"
EVALUATOR_EDGE_GRID: tuple[float, ...] = (0.0, 0.025, 0.05, 0.075, 0.10)  # solo descrittivo

# --- Passo 3b: il mercato si muove verso la V3? (dichiarato prima) -----------
# Mercati con quota di apertura e di chiusura: 1X2 finale e Over/Under 2.5.
#   movimento = logit(p_chiusura) - logit(p_apertura)   (probabilita' senza margine)
#   distanza  = logit(p_V3)       - logit(p_apertura)
#   movimento = alfa + beta * distanza, minimi quadrati, errore robusto per partita.
# Esame M: beta > 0 con limite inferiore dell'intervallo al 95% > 0 in ognuna
#          delle 3 stagioni di giudizio, per 1X2 e per Over/Under 2.5.
# Descrittivo: giocate V3 alla quota di APERTURA (stesse regole del valutatore:
# valore >= 5%, quote 1,30-5,00, 1 per partita, 15 al giorno), ROI all'apertura e
# guadagno di quota rispetto alla chiusura (quota apertura / quota chiusura - 1).
MOVE_MARKETS: dict[str, tuple[str, ...]] = {
    "FT_1X2": ("HOME", "DRAW", "AWAY"),
    "OU_2_5": ("OVER_2_5",),
}

# --- Passo 3c: ricerca pattern V3, STESSO protocollo della V2 (dichiarato prima) ---
# Righe: partite idonee x 17 mercati, quota di chiusura (come la ricerca V2).
# Condizioni (atomi) lette dagli agenti V3, mai dal risultato:
#   prob_v3      quintili della probabilita' V3 del mercato
#   v3_vs_book   quintili di (probabilita' V3 - probabilita' book senza margine)
#   quota        quintili della quota
#   equilibrio, pareggio, intensita_goal   classi degli indici (5)
#   segno_agenti specialisti concordi sul segno piu' probabile (3 / 2 / 0-1)
#   forma        quintili di (forma di gioco casa - forma di gioco ospite)
#   riposo       differenza giorni di riposo casa - ospite (< -1 / -1..1 / > 1)
#   fase         stagione / ultime 5 giornate
#   livello      prime divisioni / divisioni inferiori
#   I quintili sono calcolati sulla stagione di scoperta e poi congelati.
# Scoperta sul 2021/22: combinazioni di 1 e 2 condizioni con almeno 20 giocate e
# ROI > 0; raffinamento a 3 condizioni sui 15 migliori pattern a 2 condizioni.
# Verifica su 2022/23, 2023/24, 2024/25, ognuna da sola: almeno 20 giocate,
# confermato se ROI > 0. Riferimento del caso: probabilita' che un gruppo casuale
# di partite della stessa stagione e mercato, grande uguale, abbia ROI > 0
# (400 estrazioni). Tenuta: confermati in tutte e 3 contro il prodotto delle
# probabilita' del caso.
# Test congelato: pattern confermati in 2022/23 E 2023/24 -> giocati sul 2024/25,
# una giocata per partita per mercato.
# Confronto con la V2: stesse misure lette dalle verifiche V2 gia' salvate.
# Esame P (la V3 registra pattern vincenti):
#   P1 tasso di conferma > tasso atteso dal caso in ognuna delle 3 stagioni,
#      con rapporto (lift) complessivo >= 1,10;
#   P2 confermati in tutte e 3 le stagioni > 1,5 volte l'atteso dal caso;
#   P3 test congelato 2024/25: ROI > 0.
PATTERN_ENGINE_VERSION = "cecchino_v3_patterns_v1"
PATTERN_DISCOVERY_SEASON = "2021/2022"
PATTERN_MIN_SAMPLE = 20
PATTERN_REFINEMENT_BASES = 15
PATTERN_NULL_SAMPLES = 400
PATTERN_NULL_SEED = 20260913
PATTERN_QUANTILES = 5
PATTERN_MIN_LIFT = 1.10
PATTERN_MIN_PERSISTENCE_LIFT = 1.5
PATTERN_FROZEN_SEASON = "2024/2025"
PATTERN_FROZEN_FROM: tuple[str, ...] = ("2022/2023", "2023/2024")
V2_INSIGHT_ODDS_MODE = "closing"

# --- Passo 3d: valutatore alla quota di APERTURA (dichiarato prima) ------------
# Motivo: l'esame M e' superato (tra apertura e chiusura il mercato si sposta
# verso la V3 in ogni stagione). Stesso valutatore del Passo 3 (combinazione
# logistica walk-forward, stesse regole di giocata), ma con quota e probabilita'
# del book di APERTURA, solo sui mercati che hanno l'apertura (1, X, 2, Over 2.5,
# Under 2.5). Esami identici al Passo 3: I (peso V3 > 0 in ogni stagione,
# log-loss migliore del book) e G (ROI > 0 ogni stagione, intervallo sopra zero,
# almeno 300 giocate). Unica prova sulle stagioni di giudizio.
EVALUATOR_ODDS_CLOSING = "closing"
EVALUATOR_ODDS_OPENING = "opening"

# --- Passo 4: test finale sulla stagione sotto chiave 2025/26 (dichiarato prima) ---
# Si usa UNA volta, con tutto congelato: modello di riferimento (Fase 4) esteso
# al 2025/26 con le stesse regole, pattern V3 e V2 gia' scoperti e verificati,
# valutatori con pesi stimati solo sulle stagioni precedenti.
# F0 integrita': il calcolo finale riproduce il modello #5 su 2021/22-2024/25
#    (differenza massima di probabilita' < 0,000001).
# F1 precisione 2025/26: errore (Brier) V3 < V2 in tutte e 4 le famiglie di
#    mercato (partite comuni) e distanza dal book sull'1X2 <= +3%.
# F2 pattern V3 sul 2025/26: tasso di conferma > caso con lift >= 1,10 e i
#    pattern confermati in tutte e 3 le stagioni di giudizio, giocati sul 2025/26
#    (una giocata per partita per mercato), con ROI > 0.
# F3 confronto con la V2 sul 2025/26: lift V3 > lift V2 e ROI per giocata dei
#    pattern sempre confermati V3 > quello dei pattern sempre confermati V2.
# Descrittivo: valutatori (chiusura e apertura) e movimento del mercato sul 2025/26.
FINAL_ENGINE_VERSION = "cecchino_v3_final_test_v1"
FINAL_MAX_PROB_DIFF = 1e-6
FINAL_MAX_BOOK_GAP_PCT = 3.0
FINAL_MIN_LIFT = 1.10
