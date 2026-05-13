"""
Costanti numeriche condivise tra moduli SOT (nessuna dipendenza da altri service).

Evita import circolari tra prediction, trace e explanation.
"""

from __future__ import annotations

# Pesi baseline v0.1 (mix lineare expected_sot) — stessi valori storici di produzione
WEIGHTS_BASELINE_V0_1: dict[str, float] = {
    "season_avg_sot_for": 0.30,
    "opponent_season_avg_sot_conceded": 0.25,
    "home_away_avg_sot_for": 0.15,
    "opponent_home_away_avg_sot_conceded": 0.10,
    "last5_avg_sot_for": 0.10,
    "opponent_last5_avg_sot_conceded": 0.10,
}
