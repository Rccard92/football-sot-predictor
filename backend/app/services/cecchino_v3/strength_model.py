"""Specialista Forza: attacco/difesa per squadra, per piramide nazionale.

Gol attesi (scala logaritmica):
    casa:   mu[d] + home[d] + att(casa)   - def(ospite)
    ospite: mu[d]           + att(ospite) - def(casa)

dove d e' la divisione della partita e, per ogni squadra i,
    att(i) = A[p(i)] + nc_att * nuova(i) + a[i]
    def(i) = D[p(i)] + nc_def * nuova(i) + b[i]

- mu, home: livello gol e vantaggio casa di ogni divisione.
- A, D: livello di attacco/difesa di ogni divisione rispetto alla prima
  (fissata a 0). Si stimano grazie alle squadre promosse e retrocesse.
- p(i): divisione in cui la squadra ha giocato di piu' nella finestra
  (pesata per tempo): una neopromossa parte dal livello da cui arriva.
- nuova(i): squadra entrata nel dataset dopo la prima stagione (arriva da una
  lega che non abbiamo); nc_att/nc_def e' lo scarto medio di queste squadre.
- a, b: scarto della singola squadra, trattenuto verso 0 con deviazione sigma.
- solo con movers=True (dalla Fase 6): nella prima stagione dopo un cambio di
  divisione si aggiungono prom_att/rel_att all'attacco e prom_def/rel_def alla
  difesa della squadra promossa o retrocessa (stimati dai casi passati, a
  priori 0). Con movers=False il modello e' identico alle fasi precedenti.

Stima: massima verosimiglianza di Poisson pesata per tempo (ogni partita pesa
exp(-xi * giorni)), penalizzata, con il metodo di Newton. La funzione e'
convessa: il risultato non dipende dal punto di partenza.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from app.services.cecchino_v3.constants import (
    HT_SHARE_PSEUDO_GOALS,
    PROMOTION_PRIOR_PRECISION,
    PRIOR_HOME_ADVANTAGE,
    PRIOR_HT_SHARE,
    PRIOR_LOG_GOALS,
    RHO_GRID_MAX,
    RHO_GRID_MIN,
    RHO_GRID_STEP,
)

_WIDTH = 8  # colonne non nulle per osservazione
_WIDTH_MOVERS = 12  # con i parametri di promozione/retrocessione
_MAX_NEWTON_ITER = 30
_NEWTON_TOL = 1e-6
_MAX_STEP = 1.0

# precisioni a priori (1 / deviazione^2)
_PREC_MU = 1e-2
_PREC_HOME = 1e-1
_PREC_LEVEL = 1.0
_PREC_NEWCOMER = 4.0


@dataclass(frozen=True)
class ParamLayout:
    n_divisions: int
    n_teams: int
    movers: bool = False

    @property
    def mu(self) -> np.ndarray:
        return np.arange(0, self.n_divisions)

    @property
    def home(self) -> np.ndarray:
        return np.arange(self.n_divisions, 2 * self.n_divisions)

    def level_att(self, division: np.ndarray) -> np.ndarray:
        """Indice del livello attacco; la prima divisione non ha parametro (-1)."""
        return np.where(division > 0, 2 * self.n_divisions + division - 1, -1)

    def level_def(self, division: np.ndarray) -> np.ndarray:
        return np.where(division > 0, 3 * self.n_divisions - 1 + division - 1, -1)

    @property
    def nc_att(self) -> int:
        return 4 * self.n_divisions - 2

    @property
    def nc_def(self) -> int:
        return 4 * self.n_divisions - 1

    @property
    def _mover_block(self) -> int:
        return 4 if self.movers else 0

    @property
    def promoted_att(self) -> int:
        return 4 * self.n_divisions

    @property
    def relegated_att(self) -> int:
        return 4 * self.n_divisions + 1

    @property
    def promoted_def(self) -> int:
        return 4 * self.n_divisions + 2

    @property
    def relegated_def(self) -> int:
        return 4 * self.n_divisions + 3

    def mover_indices(self) -> dict[str, int]:
        if not self.movers:
            return {}
        return {
            "promoted_attack": self.promoted_att,
            "promoted_defence": self.promoted_def,
            "relegated_attack": self.relegated_att,
            "relegated_defence": self.relegated_def,
        }

    def team_att(self, team: np.ndarray) -> np.ndarray:
        return 4 * self.n_divisions + self._mover_block + team

    def team_def(self, team: np.ndarray) -> np.ndarray:
        return 4 * self.n_divisions + self._mover_block + self.n_teams + team

    @property
    def size(self) -> int:
        return 4 * self.n_divisions + self._mover_block + 2 * self.n_teams

    def prior_mean(self, log_level: float = PRIOR_LOG_GOALS) -> np.ndarray:
        m = np.zeros(self.size)
        m[self.mu] = log_level
        m[self.home] = PRIOR_HOME_ADVANTAGE
        return m

    def prior_precision(self, sigma: float) -> np.ndarray:
        p = np.empty(self.size)
        p[self.mu] = _PREC_MU
        p[self.home] = _PREC_HOME
        p[2 * self.n_divisions : 4 * self.n_divisions - 2] = _PREC_LEVEL
        p[self.nc_att] = _PREC_NEWCOMER
        p[self.nc_def] = _PREC_NEWCOMER
        p[4 * self.n_divisions :] = 1.0 / (sigma * sigma)
        if self.movers:
            p[4 * self.n_divisions : 4 * self.n_divisions + 4] = PROMOTION_PRIOR_PRECISION
        return p


@dataclass
class WindowData:
    """Partite della finestra (tutte precedenti al giorno della previsione)."""

    home: np.ndarray  # indice squadra casa
    away: np.ndarray
    division: np.ndarray  # divisione della partita
    home_goals: np.ndarray
    away_goals: np.ndarray
    weight: np.ndarray  # peso temporale
    # (n, 2): [promossa, retrocessa] nella stagione di quella partita (solo movers)
    home_move: np.ndarray | None = None
    away_move: np.ndarray | None = None


def _observation_design(
    layout: ParamLayout,
    *,
    division: np.ndarray,
    attacker: np.ndarray,
    defender: np.ndarray,
    team_division: np.ndarray,
    newcomer: np.ndarray,
    is_home: bool,
    attacker_move: np.ndarray | None = None,
    defender_move: np.ndarray | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """Colonne e coefficienti (n, 8 o 12) del predittore lineare di un lato."""
    n = attacker.shape[0]
    width = _WIDTH_MOVERS if layout.movers else _WIDTH
    cols = np.zeros((n, width), dtype=np.int64)
    coef = np.zeros((n, width))

    cols[:, 0] = layout.mu[division]
    coef[:, 0] = 1.0
    if is_home:
        cols[:, 1] = layout.home[division]
        coef[:, 1] = 1.0

    att_level = layout.level_att(team_division[attacker])
    cols[:, 2] = np.maximum(att_level, 0)
    coef[:, 2] = (att_level >= 0).astype(float)
    cols[:, 3] = layout.nc_att
    coef[:, 3] = newcomer[attacker]
    cols[:, 4] = layout.team_att(attacker)
    coef[:, 4] = 1.0

    def_level = layout.level_def(team_division[defender])
    cols[:, 5] = np.maximum(def_level, 0)
    coef[:, 5] = -(def_level >= 0).astype(float)
    cols[:, 6] = layout.nc_def
    coef[:, 6] = -newcomer[defender]
    cols[:, 7] = layout.team_def(defender)
    coef[:, 7] = -1.0

    if layout.movers:
        if attacker_move is None or defender_move is None:
            raise ValueError("con movers=True servono le indicazioni di promozione/retrocessione")
        cols[:, 8] = layout.promoted_att
        coef[:, 8] = attacker_move[:, 0]
        cols[:, 9] = layout.relegated_att
        coef[:, 9] = attacker_move[:, 1]
        cols[:, 10] = layout.promoted_def
        coef[:, 10] = -defender_move[:, 0]
        cols[:, 11] = layout.relegated_def
        coef[:, 11] = -defender_move[:, 1]
    return cols, coef


def team_divisions(
    window: WindowData, *, n_teams: int, n_divisions: int, fallback: np.ndarray
) -> np.ndarray:
    """Divisione con piu' peso nella finestra per ogni squadra; senza partite
    nella finestra si usa `fallback` (la divisione della partita da prevedere)."""
    acc = np.zeros((n_teams, n_divisions))
    np.add.at(acc, (window.home, window.division), window.weight)
    np.add.at(acc, (window.away, window.division), window.weight)
    has_data = acc.sum(axis=1) > 0
    return np.where(has_data, acc.argmax(axis=1), fallback)


def fit_strength(
    layout: ParamLayout,
    window: WindowData,
    *,
    team_division: np.ndarray,
    newcomer: np.ndarray,
    sigma: float,
    beta_start: np.ndarray | None = None,
    prior_log_level: float = PRIOR_LOG_GOALS,
) -> np.ndarray:
    """Stima penalizzata dei parametri (Newton). Restituisce il vettore beta.
    I conteggi possono essere gol o volumi di gioco (tiri, tiri in porta):
    `prior_log_level` e' il livello medio a priori sulla loro scala."""
    prior_mean = layout.prior_mean(prior_log_level)
    prior_prec = layout.prior_precision(sigma)
    beta = prior_mean.copy() if beta_start is None else beta_start.copy()
    if window.home.size == 0:
        return prior_mean

    cols_h, coef_h = _observation_design(
        layout,
        division=window.division,
        attacker=window.home,
        defender=window.away,
        team_division=team_division,
        newcomer=newcomer,
        is_home=True,
        attacker_move=window.home_move,
        defender_move=window.away_move,
    )
    cols_a, coef_a = _observation_design(
        layout,
        division=window.division,
        attacker=window.away,
        defender=window.home,
        team_division=team_division,
        newcomer=newcomer,
        is_home=False,
        attacker_move=window.away_move,
        defender_move=window.home_move,
    )
    cols = np.vstack([cols_h, cols_a])
    coef = np.vstack([coef_h, coef_a])
    goals = np.concatenate([window.home_goals, window.away_goals])
    weight = np.concatenate([window.weight, window.weight])

    size = layout.size
    flat_pairs = (cols[:, :, None] * size + cols[:, None, :]).ravel()
    coef_outer = coef[:, :, None] * coef[:, None, :]

    for _ in range(_MAX_NEWTON_ITER):
        eta = np.einsum("ij,ij->i", coef, beta[cols])
        lam = np.exp(np.clip(eta, -10.0, 5.0))
        resid = weight * (lam - goals)
        grad = np.bincount(cols.ravel(), weights=(coef * resid[:, None]).ravel(), minlength=size)
        grad += prior_prec * (beta - prior_mean)
        curvature = weight * lam
        hess = np.bincount(
            flat_pairs, weights=(coef_outer * curvature[:, None, None]).ravel(), minlength=size * size
        ).reshape(size, size)
        hess[np.diag_indices(size)] += prior_prec
        step = np.linalg.solve(hess, grad)
        largest = np.max(np.abs(step))
        if largest > _MAX_STEP:
            step *= _MAX_STEP / largest
        beta -= step
        if largest < _NEWTON_TOL:
            break
    return beta


def expected_goals(
    layout: ParamLayout,
    beta: np.ndarray,
    *,
    division: np.ndarray,
    home: np.ndarray,
    away: np.ndarray,
    team_division: np.ndarray,
    newcomer: np.ndarray,
    home_move: np.ndarray | None = None,
    away_move: np.ndarray | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """Gol attesi casa e ospite per le partite indicate."""
    cols_h, coef_h = _observation_design(
        layout,
        division=division,
        attacker=home,
        defender=away,
        team_division=team_division,
        newcomer=newcomer,
        is_home=True,
        attacker_move=home_move,
        defender_move=away_move,
    )
    cols_a, coef_a = _observation_design(
        layout,
        division=division,
        attacker=away,
        defender=home,
        team_division=team_division,
        newcomer=newcomer,
        is_home=False,
        attacker_move=away_move,
        defender_move=home_move,
    )
    eta_h = np.einsum("ij,ij->i", coef_h, beta[cols_h])
    eta_a = np.einsum("ij,ij->i", coef_a, beta[cols_a])
    return np.exp(np.clip(eta_h, -10.0, 5.0)), np.exp(np.clip(eta_a, -10.0, 5.0))


def dixon_coles_tau(
    home_goals: np.ndarray, away_goals: np.ndarray, lam_h: np.ndarray, lam_a: np.ndarray, rho: float
) -> np.ndarray:
    """Fattore di correzione Dixon-Coles per i punteggi 0-0, 1-0, 0-1, 1-1."""
    tau = np.ones_like(lam_h)
    m00 = (home_goals == 0) & (away_goals == 0)
    m01 = (home_goals == 0) & (away_goals == 1)
    m10 = (home_goals == 1) & (away_goals == 0)
    m11 = (home_goals == 1) & (away_goals == 1)
    tau[m00] = 1.0 - lam_h[m00] * lam_a[m00] * rho
    tau[m01] = 1.0 + lam_h[m01] * rho
    tau[m10] = 1.0 + lam_a[m10] * rho
    tau[m11] = 1.0 - rho
    return tau


def fit_rho(
    home_goals: np.ndarray,
    away_goals: np.ndarray,
    lam_h: np.ndarray,
    lam_a: np.ndarray,
    weight: np.ndarray,
) -> float:
    """Correzione pareggi: il valore della griglia ammessa con la
    verosimiglianza pesata piu' alta (a gol attesi fissati)."""
    low = (home_goals <= 1) & (away_goals <= 1)
    if not np.any(low):
        return 0.0
    hg, ag, lh, la, w = home_goals[low], away_goals[low], lam_h[low], lam_a[low], weight[low]
    best_rho, best_ll = 0.0, -np.inf
    for rho in np.arange(RHO_GRID_MIN, RHO_GRID_MAX + RHO_GRID_STEP / 2, RHO_GRID_STEP):
        tau = dixon_coles_tau(hg, ag, lh, la, float(rho))
        if np.any(tau <= 0):
            continue
        ll = float(np.sum(w * np.log(tau)))
        if ll > best_ll:
            best_rho, best_ll = float(round(rho, 4)), ll
    return best_rho


def fit_ht_share(
    division: np.ndarray,
    ft_total: np.ndarray,
    ht_total: np.ndarray,
    weight: np.ndarray,
    *,
    n_divisions: int,
) -> np.ndarray:
    """Quota dei gol segnati nel primo tempo, per divisione, con partenza a priori."""
    has_ht = ~np.isnan(ht_total)
    num = np.bincount(division[has_ht], weights=(weight * ht_total)[has_ht], minlength=n_divisions)
    den = np.bincount(division[has_ht], weights=(weight * ft_total)[has_ht], minlength=n_divisions)
    return (num + PRIOR_HT_SHARE * HT_SHARE_PSEUDO_GOALS) / (den + HT_SHARE_PSEUDO_GOALS)
