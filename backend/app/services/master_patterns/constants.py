"""Regole della pagina Master Pattern (Step 1 della roadmap), fissate prima dei calcoli.

Pattern vincente (uguale per ogni modello):
- stagione di scoperta 2021/22 (li' il pattern e' in utile per costruzione);
- stagioni di verifica 2022/23, 2023/24, 2024/25, 2025/26, ognuna con almeno
  20 partite;
- mercati con quota: ROI > 0 in tutte e 4 le stagioni di verifica;
- mercati senza quota (tiri, tiri in porta, corner, gialli sopra/sotto una soglia):
  frequenza lontana dalla media della stagione di almeno 5 punti, nella stessa
  direzione della scoperta, in tutte e 4 le stagioni di verifica.
Riferimento del caso: somma, sui pattern verificati in tutte e 4 le stagioni,
del prodotto delle probabilita' che un gruppo casuale di partite passi la verifica.

Ricerca V3 senza quota (stesse regole della ricerca V2 senza quota):
- bersagli e soglie identici alla V2 (tiri, tiri in porta, corner, gialli; totali e per squadra);
- condizioni lette dagli agenti V3: equilibrio, pareggio, intensita' goal,
  specialisti concordi, forma, riposo, fase, livello, volume atteso dello
  specialista Gioco per tiri e tiri in porta (quintili congelati sul 2021/22);
- scoperta sul 2021/22: 1-2 condizioni con almeno 20 partite e frequenza lontana
  dalla media di almeno 15 punti; raffinamento a 3 condizioni sui 15 migliori a 2.
"""

from __future__ import annotations

MODEL_V2 = "V2"
MODEL_V25 = "V2.5"
MODEL_V3 = "V3"
MODELS: tuple[str, ...] = (MODEL_V2, MODEL_V25, MODEL_V3)
BUILDABLE_MODELS: tuple[str, ...] = (MODEL_V2, MODEL_V3)

TARGET_MARKET = "market"
TARGET_SYNTHETIC = "synthetic"

DISCOVERY_SEASON = "2021/2022"
VERIFY_SEASONS: tuple[str, ...] = ("2022/2023", "2023/2024", "2024/2025", "2025/2026")
ALL_SEASONS: tuple[str, ...] = (DISCOVERY_SEASON, *VERIFY_SEASONS)

MIN_SAMPLE = 20
SYNTHETIC_DISCOVERY_DEVIATION_PCT = 15.0
SYNTHETIC_CONFIRM_DEVIATION_PCT = 5.0
REFINEMENT_BASES = 15
NULL_SAMPLES = 400
NULL_SEED = 20260914

MASTER_ENGINE_VERSION = "master_pattern_v1"

VERDICT_CONFIRMED = "confirmed"
VERDICT_ATTENUATED = "attenuated"
VERDICT_REJECTED = "rejected"
VERDICT_INSUFFICIENT = "insufficient_sample"

# Bersagli senza quota: stessi della ricerca V2 (run_v2_grid_dataset.SYNTHETIC_TARGETS).
SYNTHETIC_TARGETS: tuple[tuple[str, str, tuple[float, ...]], ...] = (
    ("total_shots", "Tiri totali", (20.5, 24.5, 28.5)),
    ("home_shots", "Tiri squadra 1", (9.5, 11.5, 13.5)),
    ("away_shots", "Tiri squadra 2", (8.5, 10.5, 12.5)),
    ("total_sot", "Tiri in porta totali", (7.5, 8.5, 9.5, 10.5)),
    ("home_sot", "Tiri in porta squadra 1", (3.5, 4.5, 5.5)),
    ("away_sot", "Tiri in porta squadra 2", (3.5, 4.5, 5.5)),
    ("total_corners", "Corner totali", (7.5, 8.5, 9.5, 10.5)),
    ("home_corners", "Corner squadra 1", (4.5, 5.5, 6.5)),
    ("away_corners", "Corner squadra 2", (3.5, 4.5, 5.5)),
    ("total_yellow_cards", "Cartellini gialli totali", (3.5, 4.5, 5.5)),
    ("home_yellow_cards", "Cartellini gialli squadra 1", (1.5, 2.5, 3.5)),
    ("away_yellow_cards", "Cartellini gialli squadra 2", (1.5, 2.5, 3.5)),
)

MARKET_LABELS: dict[str, str] = {
    "HOME": "1",
    "DRAW": "X",
    "AWAY": "2",
    "ONE_X": "1X",
    "X_TWO": "X2",
    "ONE_TWO": "12",
    "OVER_0_5": "Over 0.5",
    "UNDER_0_5": "Under 0.5",
    "OVER_1_5": "Over 1.5",
    "UNDER_1_5": "Under 1.5",
    "OVER_2_5": "Over 2.5",
    "UNDER_2_5": "Under 2.5",
    "OVER_3_5": "Over 3.5",
    "UNDER_3_5": "Under 3.5",
    "HOME_PT": "1 primo tempo",
    "DRAW_PT": "X primo tempo",
    "AWAY_PT": "2 primo tempo",
}
