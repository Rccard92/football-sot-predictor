"""Scelta degli iperparametri e della dispersione per stagione, solo dal passato (PREREGISTRAZIONE §2.2-2.3).

Per la stagione S: iperparametro con la log-verosimiglianza di Poisson media piu' alta sulla
stagione precedente S−1 (righe eval_eligible, casa e ospite); dispersione binomiale negativa
per divisione con il metodo dei momenti sui residui di S−1 dello stesso iperparametro.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from app.services.cecchino_v3.constants import Hyper

from app.services.cecchino_v4.engine_stats.config import StatsConfig
from app.services.cecchino_v4.engine_stats.distribution import poisson_loglik
from app.services.cecchino_v4.engine_stats.walkforward import RunArrays


@dataclass
class SeasonSpec:
    season: str
    source_season: str | None  # stagione usata per scegliere (None = default di rodaggio)
    hyper: Hyper
    scores: dict[str, float] = field(default_factory=dict)  # log-verosimiglianza media per iperparametro
    alpha: dict[str, float | None] = field(default_factory=dict)  # per divisione; None = Poisson
    alpha_rows: dict[str, int] = field(default_factory=dict)


def previous_season(season: str, known: list[str]) -> str | None:
    before = [s for s in known if s < season]
    return max(before) if before else None


def _season_mask(run: RunArrays, season: str) -> np.ndarray:
    return np.array([s == season for s in run.season], dtype=bool) & run.usable & run.eligible


def score_run(run: RunArrays, season: str) -> float | None:
    m = _season_mask(run, season)
    if not np.any(m):
        return None
    ll = np.concatenate([poisson_loglik(run.y_h[m], run.mean_h[m]), poisson_loglik(run.y_a[m], run.mean_a[m])])
    return float(np.mean(ll))


def dispersion_by_division(run: RunArrays, season: str, min_rows: int) -> tuple[dict[str, float | None], dict[str, int]]:
    """alpha = Σ[(y − m)² − m] / Σ m² sui residui della stagione indicata; Poisson se ≤ 0 o poche righe."""
    m = _season_mask(run, season)
    comps = np.array(run.competition, dtype=object)
    alpha: dict[str, float | None] = {}
    rows: dict[str, int] = {}
    for comp in sorted(set(comps[m].tolist())):
        sel = m & (comps == comp)
        y = np.concatenate([run.y_h[sel], run.y_a[sel]])
        mu = np.concatenate([run.mean_h[sel], run.mean_a[sel]])
        rows[comp] = int(y.size)
        if y.size < min_rows:
            alpha[comp] = None
            continue
        num = float(np.sum((y - mu) ** 2 - mu))
        den = float(np.sum(mu * mu))
        a = num / den if den > 0 else 0.0
        alpha[comp] = float(a) if a > 0 else None
    return alpha, rows


def build_specs(
    runs: dict[str, RunArrays],
    *,
    history_seasons: list[str],
    seasons_to_predict: list[str],
    config: StatsConfig,
) -> dict[str, SeasonSpec]:
    """runs: chiave iperparametro -> corsa completa sullo storico."""
    specs: dict[str, SeasonSpec] = {}
    for season in seasons_to_predict:
        prev = previous_season(season, history_seasons)
        scores: dict[str, float] = {}
        if prev is not None:
            for h in config.hyper_grid:
                s = score_run(runs[h.key], prev)
                if s is not None:
                    scores[h.key] = s
        if scores:
            best_key = max(scores, key=lambda k: (scores[k], -[h.key for h in config.hyper_grid].index(k)))
            hyper = next(h for h in config.hyper_grid if h.key == best_key)
        else:
            hyper = config.default_hyper
            prev = None
        spec = SeasonSpec(season=season, source_season=prev, hyper=hyper, scores=scores)
        if prev is not None:
            spec.alpha, spec.alpha_rows = dispersion_by_division(runs[hyper.key], prev, config.dispersion_min_rows)
        specs[season] = spec
    return specs
