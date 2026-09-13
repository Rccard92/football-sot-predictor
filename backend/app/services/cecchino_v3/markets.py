"""Da gol attesi a probabilita' dei 17 mercati, tutte dalla stessa
distribuzione dei risultati (quindi coerenti tra loro)."""

from __future__ import annotations

import math

import numpy as np

from app.services.cecchino_v3.constants import MAX_GOALS

_GOALS = np.arange(MAX_GOALS + 1)
_LOG_FACTORIAL = np.array([math.lgamma(k + 1) for k in range(MAX_GOALS + 1)])


def poisson_vector(lam: float) -> np.ndarray:
    lam = max(float(lam), 1e-9)
    return np.exp(_GOALS * math.log(lam) - lam - _LOG_FACTORIAL)


def score_matrix(lam_home: float, lam_away: float, rho: float) -> np.ndarray:
    """Probabilita' di ogni risultato (righe: gol casa, colonne: gol ospite),
    con correzione Dixon-Coles sui punteggi bassi, normalizzata a 1."""
    m = np.outer(poisson_vector(lam_home), poisson_vector(lam_away))
    m[0, 0] *= 1.0 - lam_home * lam_away * rho
    m[0, 1] *= 1.0 + lam_home * rho
    m[1, 0] *= 1.0 + lam_away * rho
    m[1, 1] *= 1.0 - rho
    np.clip(m, 0.0, None, out=m)
    return m / m.sum()


def _one_x_two(m: np.ndarray) -> tuple[float, float, float]:
    home = float(np.tril(m, -1).sum())
    draw = float(np.trace(m))
    away = float(np.triu(m, 1).sum())
    return home, draw, away


def market_probabilities(
    lam_home: float, lam_away: float, rho: float, ht_share: float
) -> dict[str, float]:
    ft = score_matrix(lam_home, lam_away, rho)
    home, draw, away = _one_x_two(ft)

    totals = _GOALS[:, None] + _GOALS[None, :]
    out: dict[str, float] = {
        "HOME": home,
        "DRAW": draw,
        "AWAY": away,
        "ONE_X": home + draw,
        "X_TWO": draw + away,
        "ONE_TWO": home + away,
    }
    for line, suffix in ((0, "0_5"), (1, "1_5"), (2, "2_5"), (3, "3_5")):
        over = float(ft[totals > line].sum())
        out[f"OVER_{suffix}"] = over
        out[f"UNDER_{suffix}"] = 1.0 - over

    # Primo tempo: stessi gol attesi riscalati sulla quota del primo tempo.
    ht = score_matrix(lam_home * ht_share, lam_away * ht_share, 0.0)
    ht_home, ht_draw, ht_away = _one_x_two(ht)
    out["HOME_PT"] = ht_home
    out["DRAW_PT"] = ht_draw
    out["AWAY_PT"] = ht_away
    return out


def market_outcomes(
    ft_home: int, ft_away: int, ht_home: int | None, ht_away: int | None
) -> dict[str, bool | None]:
    """Esito reale dei 17 mercati (solo per la valutazione, mai per prevedere)."""
    total = ft_home + ft_away
    out: dict[str, bool | None] = {
        "HOME": ft_home > ft_away,
        "DRAW": ft_home == ft_away,
        "AWAY": ft_home < ft_away,
        "ONE_X": ft_home >= ft_away,
        "X_TWO": ft_home <= ft_away,
        "ONE_TWO": ft_home != ft_away,
    }
    for line, suffix in ((0, "0_5"), (1, "1_5"), (2, "2_5"), (3, "3_5")):
        out[f"OVER_{suffix}"] = total > line
        out[f"UNDER_{suffix}"] = total <= line
    if ht_home is None or ht_away is None:
        out["HOME_PT"] = out["DRAW_PT"] = out["AWAY_PT"] = None
    else:
        out["HOME_PT"] = ht_home > ht_away
        out["DRAW_PT"] = ht_home == ht_away
        out["AWAY_PT"] = ht_home < ht_away
    return out
