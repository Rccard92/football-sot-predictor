"""RUN V2 Cecchino Lab.

Nuova generazione di run storica: riusa invariata la logica predittiva V1 e vi
aggiunge i mercati mancanti, un layer economico separato sulle quote
near-closing e un layer statistico extra (BLOCCO 2).

CORE FORMULA FREEZE: nessun modulo di questo package puo modificare formule,
pesi, soglie, normalizzazioni o ordine di elaborazione dei moduli V1. Le
funzioni V1 vanno invocate cosi come sono.
"""

from __future__ import annotations
