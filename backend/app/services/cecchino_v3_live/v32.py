"""V3.2: correzioni dei gol della V3 estesa (docs/v3/DIAGNOSI_V25_V3_LIVE.md, esame docs/v3/V32_ESAME_*.md).

- A, livello dei gol del campionato: fattore R dalle sole partite del campionato gia' finite prima del giorno,
  nella stessa stagione, ristretto verso 1 con peso K partite;
- B, forma della distribuzione: rho di Dixon-Coles stimato dal motore oppure 0.
Nessuna quota nel calcolo. Quali correzioni sono accese lo decide l'esame (ADOPTED_*).
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from app.services.cecchino_v3.data import MatchRecord
from app.services.cecchino_v3.markets import market_probabilities

V32_ENGINE_VERSION = "cecchino_v32_v1_20261024"
FACTOR_MIN = 0.75
FACTOR_MAX = 1.33

# Esito dell'esame sulla stagione 2025 (docs/v3/V32_ESAME_RISULTATO.md). None / False = correzione spenta.
ADOPTED_K: float | None = None
ADOPTED_RHO_ZERO: bool = False

# Mercati della giocata in evidenza V3.2 (correzione C): niente doppia chance, niente primo tempo.
EVIDENZA_MARKETS = ("HOME", "DRAW", "AWAY", "OVER_1_5", "UNDER_1_5", "OVER_2_5", "UNDER_2_5", "OVER_3_5", "UNDER_3_5")
EVIDENZA_MIN_QUOTA = 1.41
EVIDENZA_MAX_QUOTA = 2.20


def league_factors(
    records: list[MatchRecord], finals: dict[int, dict[str, Any]], k: float | None, *, targets: set[int] | frozenset = frozenset()
) -> dict[int, float]:
    """Fattore R per ogni partita con previsione: (gol reali + K g) / (gol attesi + K g) sulle partite finite della
    stessa stagione nei giorni precedenti; 1 con K spento o senza partite precedenti."""
    out: dict[int, float] = {}
    if k is None:
        return {mid: 1.0 for mid in finals}
    sums: dict[str, list[float]] = defaultdict(lambda: [0.0, 0.0, 0.0])  # stagione -> reali, attesi, partite
    by_day: dict[int, list[MatchRecord]] = defaultdict(list)
    for m in records:
        by_day[m.day].append(m)
    for day in sorted(by_day):
        todays = by_day[day]
        for m in todays:
            if m.lab_match_id not in finals:
                continue
            actual, expected, n = sums[m.season_label]
            if n <= 0 or expected <= 0:
                out[m.lab_match_id] = 1.0
                continue
            g = expected / n
            r = (actual + k * g) / (expected + k * g)
            out[m.lab_match_id] = min(FACTOR_MAX, max(FACTOR_MIN, r))
        for m in todays:
            fin = finals.get(m.lab_match_id)
            if fin is None or m.lab_match_id in targets:
                continue
            acc = sums[m.season_label]
            acc[0] += m.ft_home + m.ft_away
            acc[1] += float(fin["lambda_home"]) + float(fin["lambda_away"])
            acc[2] += 1
    return out


def corrected(fin: dict[str, Any], factor: float, rho_zero: bool) -> dict[str, Any]:
    """Gol attesi e probabilita' corretti di una previsione V3 (stessi mercati)."""
    lam_h = float(fin["lambda_home"]) * factor
    lam_a = float(fin["lambda_away"]) * factor
    rho = 0.0 if rho_zero else float(fin["rho"])
    return {
        "lambda_home": lam_h,
        "lambda_away": lam_a,
        "rho": rho,
        "league_factor": factor,
        "probabilities": market_probabilities(lam_h, lam_a, rho, float(fin["ht_share"])),
    }


def evidenza_pick(markets: dict[str, Any]) -> dict[str, Any] | None:
    """Correzione C: la piu' probabile tra 1X2 finale e Over/Under 1,5-3,5 con quota Bet365 tra 1,41 e 2,20
    e non sotto la quota minima (1 / probabilita')."""
    best: tuple[float, str, float] | None = None
    for key in EVIDENZA_MARKETS:
        m = markets.get(key) or {}
        p, q = m.get("probability"), m.get("quota_book")
        try:
            p, q = float(p), float(q)
        except (TypeError, ValueError):
            continue
        if p <= 0 or not (EVIDENZA_MIN_QUOTA <= q <= EVIDENZA_MAX_QUOTA) or q < 1.0 / p:
            continue
        if best is None or p > best[0]:
            best = (p, key, q)
    if best is None:
        return None
    return {"market_key": best[1], "probability": round(best[0], 6), "quota": best[2]}
