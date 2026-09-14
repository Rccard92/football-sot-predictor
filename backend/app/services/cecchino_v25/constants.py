"""Costanti Cecchino V2.5."""

from __future__ import annotations

RUN_V25_VERSION = "cecchino_run_v25"
RUN_V25_CONFIRM_TOKEN = "RUN_CECCHINO_RUN_V25"
ENGINE_VERSION = "cecchino_v25_engine_v1"

# --- statistiche di campionato -------------------------------------------------------------
# La stagione precedente dello stesso campionato entra nel riferimento di campionato
# con un peso pari al massimo a questo numero di partite; la stagione in corso pesa
# per intero. Senza nessuna delle due si usa il riferimento globale (tutti i campionati).
LEAGUE_PREVIOUS_SEASON_WEIGHT = 150.0
# Sotto questo numero di partite (pesate) il riferimento di campionato si fonde con
# quello globale.
LEAGUE_MIN_SAMPLE = 60.0

# --- picchetti 1X2 ---------------------------------------------------------------------------
# Partite "virtuali" con le frequenze del campionato aggiunte a ogni picchetto: con
# poche partite la stima resta vicina al campionato e nessun esito vale mai 0.
PICCHETTI_PRIOR_MATCHES = 4.0

# --- gol -------------------------------------------------------------------------------------
BLEND_POISSON = 0.65
BLEND_EMPIRICAL = 0.35
# Partite virtuali verso la media del campionato per gol fatti/subiti e frequenze.
GOAL_RATE_PRIOR_MATCHES = 5.0
GOAL_HIT_PRIOR_MATCHES = 5.0
# Affidabilita' del contesto = n / (n + K): cresce con le partite, non arriva mai a 1.
GOAL_RELIABILITY_PRIOR = 6.0
MIN_PROB = 0.02
MAX_PROB = 0.98

# --- acquistabilita' -----------------------------------------------------------------------
# Calibrazione progressiva (solo partite gia' giocate): minimo di righe per famiglia
# prima di fidarsi del modello; si ristima ogni REFIT_EVERY nuove righe.
PURCHASABILITY_MIN_ROWS = 600
PURCHASABILITY_REFIT_EVERY = 400
# Valore atteso che corrisponde a punteggio 0 e 100.
PURCHASABILITY_EV_FLOOR = -0.12
PURCHASABILITY_EV_CEIL = 0.08

# --- classi a 5 livelli ---------------------------------------------------------------------
FIVE_CLASS_KEYS = ("very_low", "low", "medium", "high", "very_high")
FIVE_CLASS_LABELS = {
    "very_low": "Molto bassa",
    "low": "Bassa",
    "medium": "Media",
    "high": "Alta",
    "very_high": "Molto alta",
}
PURCHASABILITY_CLASS_LABELS = ("Molto Bassa", "Bassa", "Media", "Alta", "Molto Alta")
