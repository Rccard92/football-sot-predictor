"""Configurazione del motore gol V4: interruttori delle novita' e costanti
dichiarate in docs/v4/PREREGISTRAZIONE_FASE_1.md (fissate prima dei risultati).

`ADOPTED_CONFIG` e' la configurazione che ha superato l'esame E1: la scrive
`exams/e1.py` e la usa il live. Finche' l'esame non e' stato eseguito vale
il termine di paragone (tutto spento).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from app.services.cecchino_v3.constants import DEFAULT_HYPER, Hyper

ENGINE_VERSION = "cecchino_v4_goals_v1"

# --- a. vantaggio casa per squadra -------------------------------------------------
HOME_ADV_PRIOR_MATCHES = 20.0  # K: peso a priori in partite (K/2 per lato)
HOME_ADV_DECAY_XI = DEFAULT_HYPER.xi  # decadimento temporale dei residui
HOME_ADV_MAX_LOG = 0.25  # |kappa| massimo in scala logaritmica

# --- b. rho per divisione ---------------------------------------------------------------
DIVISION_RHO_MIN_WEIGHT = 100.0  # partite equivalenti minime nella divisione

# --- c. dispersione binomiale negativa ----------------------------------------------
DISPERSION_POISSON_BELOW = 0.005  # alpha sotto questa soglia = Poisson

# --- d. incertezza ------------------------------------------------------------------------
UNCERTAINTY_WEIGHTS: dict[str, float] = {"knowledge": 0.50, "disagreement": 0.35, "new_team": 0.15}
DISAGREEMENT_FULL = 0.5  # |log rapporto| che vale 1 nel segnale di disaccordo
UNCERTAINTY_WARMUP_CUTS: tuple[float, float] = (0.20, 0.45)  # tagli fissi nel rodaggio
UNCERTAINTY_QUANTILES: tuple[float, float] = (0.30, 0.70)  # percentili sulla stagione precedente
INTERVAL_SIGMA_BASE = 0.05
INTERVAL_SIGMA_SLOPE = 0.20
INTERVAL_Z90 = 1.645
LEVEL_LOW, LEVEL_MEDIUM, LEVEL_HIGH = "bassa", "media", "alta"
LEVELS: tuple[str, ...] = (LEVEL_LOW, LEVEL_MEDIUM, LEVEL_HIGH)


@dataclass(frozen=True)
class V4GoalsConfig:
    """Interruttori delle novita' (docs/v4/PREREGISTRAZIONE_FASE_1.md, sezione 3)."""

    team_home_advantage: bool = False  # a
    division_rho: bool = False  # b
    division_dispersion: bool = False  # c
    uncertainty: bool = False  # d (livelli e intervalli; il punteggio si calcola sempre)
    isotonic_calibration: bool = False  # e
    asian_handicap: bool = True  # f (descrittivo)
    ratings: bool = True  # blocco descrittivo
    # Iperparametro per il live quando non c'e' una scelta sulla stagione precedente.
    live_hyper_xi: float = DEFAULT_HYPER.xi
    live_hyper_sigma: float = DEFAULT_HYPER.sigma

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "V4GoalsConfig":
        keys = {f for f in cls.__dataclass_fields__}  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in data.items() if k in keys})

    @property
    def live_hyper(self) -> Hyper:
        return Hyper(xi=self.live_hyper_xi, sigma=self.live_hyper_sigma)

    def with_(self, **changes: Any) -> "V4GoalsConfig":
        data = self.as_dict()
        data.update(changes)
        return V4GoalsConfig.from_dict(data)


BASELINE_CONFIG = V4GoalsConfig()

# Configurazione adottata dall'esame E1 (scritta da exams/e1.py dopo il verdetto).
# Finche' l'esame non e' stato eseguito: termine di paragone.
ADOPTED_CONFIG: dict[str, Any] = {
    "team_home_advantage": False,
    "division_rho": False,
    "division_dispersion": False,
    "uncertainty": False,
    "isotonic_calibration": False,
    "asian_handicap": True,
    "ratings": True,
    "live_hyper_xi": 0.002,
    "live_hyper_sigma": 0.4
}


def adopted_config() -> V4GoalsConfig:
    return V4GoalsConfig.from_dict(ADOPTED_CONFIG)
