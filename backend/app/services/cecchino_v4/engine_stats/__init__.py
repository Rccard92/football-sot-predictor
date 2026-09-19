"""Motore statistiche V4: tiri, tiri in porta, corner, cartellini, falli per squadra e totali.

Modello log-lineare fatto/subito con effetto casa e decadimento temporale (stesso stimatore
della V3, importato come libreria), walk-forward per piramide nazionale, distribuzione di
Poisson o binomiale negativa per (divisione, statistica), probabilita' per qualunque linea
con intervallo al 90% dall'incertezza a posteriori. Nessuna quota del book entra qui.

Pre-registrazione: docs/v4/PREREGISTRAZIONE_FASE_2.md.
"""

from app.services.cecchino_v4.engine_stats.config import ADOPTED_CONFIG, StatsConfig
from app.services.cecchino_v4.engine_stats.engine import Target, predict_history, predict_targets

__all__ = ["ADOPTED_CONFIG", "StatsConfig", "Target", "predict_history", "predict_targets"]
