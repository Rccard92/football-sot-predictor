"""Dalla coppia di gol attesi alla matrice dei punteggi e ai mercati.

- marginali Poisson (identiche a `cecchino_v3.markets`) o binomiale negativa
  con dispersione `alpha` per lato (novita' c);
- correzione Dixon-Coles sui punteggi bassi con lo stesso `rho`;
- 17 mercati classici + handicap asiatico (novita' f) dalla stessa matrice;
- primo tempo come nella V3: Poisson su `lambda * ht_share`, rho = 0.
"""

from __future__ import annotations

import math

import numpy as np

from app.services.cecchino_v3.constants import MAX_GOALS
from app.services.cecchino_v3.markets import poisson_vector, score_matrix

from app.services.cecchino_v4.constants import AH_LINES, CLASSIC_MARKETS

_GOALS = np.arange(MAX_GOALS + 1)
_LOG_FACTORIAL = np.array([math.lgamma(k + 1) for k in range(MAX_GOALS + 1)])
_TOTALS = _GOALS[:, None] + _GOALS[None, :]
_DIFF = _GOALS[:, None] - _GOALS[None, :]  # casa - ospite
_OVER_MASKS: tuple[tuple[str, np.ndarray], ...] = tuple(
    (suffix, (_TOTALS > line).astype(float)) for line, suffix in ((0, "0_5"), (1, "1_5"), (2, "2_5"), (3, "3_5"))
)


def negative_binomial_vector(lam: float, alpha: float) -> np.ndarray:
    """P(k) per k = 0..MAX_GOALS con media lam e varianza lam + alpha*lam^2."""
    lam = max(float(lam), 1e-9)
    if alpha is None or alpha <= 0.0:
        return poisson_vector(lam)
    r = 1.0 / float(alpha)
    log_p = (
        np.array([math.lgamma(k + r) for k in _GOALS])
        - math.lgamma(r)
        - _LOG_FACTORIAL
        + r * (math.log(r) - math.log(r + lam))
        + _GOALS * (math.log(lam) - math.log(r + lam))
    )
    return np.exp(log_p)


def score_matrix_v4(
    lam_home: float, lam_away: float, rho: float, alpha_home: float | None = None, alpha_away: float | None = None
) -> np.ndarray:
    """Matrice dei punteggi (righe: gol casa) con correzione Dixon-Coles.
    Con dispersioni nulle e' identica a `cecchino_v3.markets.score_matrix`."""
    if not alpha_home and not alpha_away:
        return score_matrix(lam_home, lam_away, rho)
    m = np.outer(negative_binomial_vector(lam_home, alpha_home or 0.0), negative_binomial_vector(lam_away, alpha_away or 0.0))
    m[0, 0] *= 1.0 - lam_home * lam_away * rho
    m[0, 1] *= 1.0 + lam_home * rho
    m[1, 0] *= 1.0 + lam_away * rho
    m[1, 1] *= 1.0 - rho
    np.clip(m, 0.0, None, out=m)
    return m / m.sum()


def _one_x_two(m: np.ndarray) -> tuple[float, float, float]:
    return float(np.tril(m, -1).sum()), float(np.trace(m)), float(np.triu(m, 1).sum())


def classic_markets(ft: np.ndarray, lam_home: float, lam_away: float, ht_share: float) -> dict[str, float]:
    """I 17 mercati V3 dalla matrice a tempo pieno (+ primo tempo Poisson come V3)."""
    home, draw, away = _one_x_two(ft)
    out: dict[str, float] = {
        "HOME": home,
        "DRAW": draw,
        "AWAY": away,
        "ONE_X": home + draw,
        "X_TWO": draw + away,
        "ONE_TWO": home + away,
    }
    for suffix, mask in _OVER_MASKS:
        over = float(np.vdot(ft, mask))
        out[f"OVER_{suffix}"] = over
        out[f"UNDER_{suffix}"] = 1.0 - over
    ht = score_matrix(lam_home * ht_share, lam_away * ht_share, 0.0)
    ht_home, ht_draw, ht_away = _one_x_two(ht)
    out["HOME_PT"] = ht_home
    out["DRAW_PT"] = ht_draw
    out["AWAY_PT"] = ht_away
    return out


def ah_line_key(side: str, line: float) -> str:
    """`AH_HOME:-0.5`, `AH_HOME:+0.25`, `AH_HOME:0.0` (formato di docs/v4/API.md)."""
    if abs(line) < 1e-9:
        text = "0.0"
    else:
        text = f"{line:+g}"
        if "." not in text:
            text += ".0"
    return f"{side}:{text}"


def _ah_masks(line: float, *, home_side: bool) -> tuple[np.ndarray, np.ndarray]:
    """Maschere (vincita, rimborso) di una linea intera o mezza."""
    diff = _DIFF if home_side else -_DIFF
    adjusted = diff + line
    return (adjusted > 1e-9).astype(float), (np.abs(adjusted) <= 1e-9).astype(float)


def _ah_stake_masks(line: float, *, home_side: bool) -> tuple[np.ndarray, np.ndarray]:
    """Frazione di puntata vincente e rimborsata per ogni punteggio; le linee a
    quarto valgono meta' puntata su ciascuna delle due linee adiacenti."""
    quarter = abs(line * 4 - round(line * 4)) < 1e-9 and abs(line * 2 - round(line * 2)) > 1e-9
    if not quarter:
        return _ah_masks(line, home_side=home_side)
    w1, u1 = _ah_masks(line - 0.25, home_side=home_side)
    w2, u2 = _ah_masks(line + 0.25, home_side=home_side)
    return 0.5 * (w1 + w2), 0.5 * (u1 + u2)


_AH_TABLE: tuple[tuple[str, np.ndarray, np.ndarray], ...] = tuple(
    (ah_line_key(side, line), *_ah_stake_masks(line, home_side=home_side))
    for side, home_side in (("AH_HOME", True), ("AH_AWAY", False))
    for line in AH_LINES
)


def asian_handicap(ft: np.ndarray) -> dict[str, float]:
    """Probabilita' `p = vincita attesa / (1 - rimborso attesa)` per le linee `AH_LINES`."""
    out: dict[str, float] = {}
    for key, win_mask, push_mask in _AH_TABLE:
        win = float(np.vdot(ft, win_mask))
        push = float(np.vdot(ft, push_mask))
        denom = 1.0 - push
        out[key] = win / denom if denom > 1e-12 else 0.5
    return out


def all_markets(
    lam_home: float,
    lam_away: float,
    rho: float,
    ht_share: float,
    *,
    alpha_home: float | None = None,
    alpha_away: float | None = None,
    with_ah: bool = True,
) -> dict[str, float]:
    ft = score_matrix_v4(lam_home, lam_away, rho, alpha_home, alpha_away)
    out = classic_markets(ft, lam_home, lam_away, ht_share)
    if with_ah:
        out.update(asian_handicap(ft))
    return out


_DIRECTIONS = np.array(
    [(math.cos(a), math.sin(a)) for a in np.arange(0.0, 2.0 * math.pi - 1e-9, math.pi / 4.0)]
)  # 8 direzioni a 45 gradi nel piano (log lambda_h, log lambda_a)


def market_intervals(
    lam_home: float,
    lam_away: float,
    rho: float,
    ht_share: float,
    sigma: float,
    z: float,
    center: dict[str, float],
    *,
    alpha_home: float | None = None,
    alpha_away: float | None = None,
    with_ah: bool = True,
) -> dict[str, tuple[float, float]]:
    """Intervallo (lo, hi) per mercato: minimo e massimo della probabilita' tra
    il centro e gli 8 punti a distanza z*sigma nelle 8 direzioni a 45 gradi."""
    lo = dict(center)
    hi = dict(center)
    lh, la = math.log(max(lam_home, 1e-9)), math.log(max(lam_away, 1e-9))
    radius = z * sigma
    for dx, dy in _DIRECTIONS:
        probs = all_markets(
            math.exp(lh + radius * dx),
            math.exp(la + radius * dy),
            rho,
            ht_share,
            alpha_home=alpha_home,
            alpha_away=alpha_away,
            with_ah=with_ah,
        )
        for k, v in probs.items():
            if v < lo[k]:
                lo[k] = v
            if v > hi[k]:
                hi[k] = v
    return {k: (lo[k], hi[k]) for k in center}


__all__ = [
    "CLASSIC_MARKETS",
    "ah_line_key",
    "all_markets",
    "asian_handicap",
    "classic_markets",
    "market_intervals",
    "negative_binomial_vector",
    "score_matrix_v4",
]
