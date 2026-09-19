"""Configurazione del motore statistiche, fissata prima dei risultati (PREREGISTRAZIONE_FASE_2 §2)."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path

from app.services.cecchino_v3.constants import Hyper

from app.services.cecchino_v4.constants import DISPERSION_MIN_ROWS, STATS

ENGINE_VERSION = "cecchino_v4_stats_v1"

# Media a priori della statistica per squadra e partita (scala naturale). Prior debole:
# serve solo come punto di partenza del livello mu di ogni divisione.
PRIOR_MEAN: dict[str, float] = {
    "shots": 12.0,
    "sot": 4.2,
    "corners": 5.0,
    "cards": 2.2,
    "fouls": 12.0,
}

RUNTIME_DIR = Path(__file__).resolve().parents[4] / ".runtime" / "v4" / "engine_stats"


@dataclass(frozen=True)
class StatsConfig:
    """Tutti i gradi di liberta' del motore. Cambiare un valore = nuovo motore, nuovo esame."""

    stats: tuple[str, ...] = tuple(STATS)
    # Griglia iperparametri: la coppia per la stagione S e' quella con la log-verosimiglianza
    # di Poisson media piu' alta sulla stagione S-1 (partite eval_eligible, lati casa e ospite).
    hyper_grid: tuple[Hyper, ...] = tuple(
        Hyper(xi=xi, sigma=sigma) for xi in (0.001, 0.002, 0.004) for sigma in (0.1, 0.2, 0.4)
    )
    default_hyper: Hyper = Hyper(xi=0.002, sigma=0.2)
    prior_log_level: dict[str, float] = field(
        default_factory=lambda: {k: math.log(v) for k, v in PRIOR_MEAN.items()}
    )
    # Dispersione binomiale negativa per (divisione, statistica) sui residui della stagione precedente.
    dispersion_min_rows: int = DISPERSION_MIN_ROWS
    # Intervallo al 90% sulla probabilita' over: quantile normale.
    interval_z: float = 1.6448536269514722
    # Cache degli intermedi (None = nessuna cache) e processi paralleli per le corse walk-forward.
    cache_dir: Path | None = RUNTIME_DIR
    workers: int = 8

    @property
    def version(self) -> str:
        return ENGINE_VERSION

    def fingerprint(self) -> str:
        """Identifica la configurazione del modello nella cache (esclude cache_dir e workers)."""
        parts = [
            self.version,
            ",".join(self.stats),
            "|".join(h.key for h in self.hyper_grid),
            self.default_hyper.key,
            "|".join(f"{k}={v:.6f}" for k, v in sorted(self.prior_log_level.items())),
            str(self.dispersion_min_rows),
            f"{self.interval_z:.6f}",
        ]
        return ";".join(parts)


ADOPTED_CONFIG = StatsConfig()
