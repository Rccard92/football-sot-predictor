"""Motore statistiche: previsioni storiche walk-forward e previsioni di partite bersaglio.

Payload `stats` di docs/v4/API.md. Nessuna quota del book entra qui (regola 2).

Uscite per lato (casa, ospite, totale): media, dispersione (None = Poisson), media di divisione
al giorno, posizione fatto/subito nella divisione, squadre nella divisione, partite equivalenti
(evidenza) e probabilita' over per le linee di constants.STAT_LINES con intervallo al 90%
dall'incertezza a posteriori (PREREGISTRAZIONE_FASE_2 §2.4).
"""

from __future__ import annotations

from app.services.cecchino_v4.settings import cap_workers

import hashlib
import json
import math
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Iterable, Sequence

import numpy as np

from app.services.cecchino_v3.constants import Hyper, group_of
from app.services.cecchino_v3.data import MatchRecord

from app.services.cecchino_v4.constants import STAT_LINES
from app.services.cecchino_v4.engine_stats import distribution as dist
from app.services.cecchino_v4.engine_stats.config import ADOPTED_CONFIG, StatsConfig
from app.services.cecchino_v4.engine_stats.counts import stat_pair
from app.services.cecchino_v4.engine_stats.specs import SeasonSpec, build_specs, previous_season
from app.services.cecchino_v4.engine_stats.walkforward import GroupData, Row, RunArrays, build_group, run_group
from app.services.cecchino_v4.history.football_data import History, MatchExtras

_EPOCH = date(2000, 1, 1)
EXAM_RESULT_PATH = Path(__file__).resolve().parents[5] / "docs" / "v4" / "esami" / "E2.json"
EXAM_PENDING = "in_attesa"


@dataclass(frozen=True)
class Target:
    """Partita da prevedere: non ha risultato e non entra mai nelle finestre."""

    key: str
    competition: str
    season_label: str
    match_date: date
    home_team: str
    away_team: str


@dataclass
class StatPredictions:
    """Previsioni di una statistica per un insieme di partite, con distribuzione completa."""

    stat: str
    run: RunArrays  # righe previste
    alpha_h: np.ndarray  # dispersione lato casa (0 = Poisson)
    alpha_a: np.ndarray
    sd_h: np.ndarray  # deviazione a posteriori di log(media)
    sd_a: np.ndarray
    specs: dict[str, SeasonSpec]  # per stagione prevista

    def __len__(self) -> int:
        return len(self.run)

    @property
    def mean_t(self) -> np.ndarray:
        return self.run.mean_h + self.run.mean_a

    @property
    def alpha_t(self) -> np.ndarray:
        return dist.total_dispersion(self.run.mean_h, self.alpha_h, self.run.mean_a, self.alpha_a)

    @property
    def sd_t(self) -> np.ndarray:
        mh, ma = self.run.mean_h, self.run.mean_a
        mt = np.maximum(mh + ma, 1e-9)
        return np.sqrt((mh * mh * self.sd_h**2 + ma * ma * self.sd_a**2)) / mt

    def side(self, side: str) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """(media, dispersione, sd log-media) del lato."""
        if side == "home":
            return self.run.mean_h, self.alpha_h, self.sd_h
        if side == "away":
            return self.run.mean_a, self.alpha_a, self.sd_a
        if side == "total":
            return self.mean_t, self.alpha_t, self.sd_t
        raise ValueError(side)

    def realized(self, side: str) -> np.ndarray:
        if side == "home":
            return self.run.y_h
        if side == "away":
            return self.run.y_a
        return self.run.y_h + self.run.y_a


# --- Righe ---------------------------------------------------------------------------------


def _history_rows(
    matches: Sequence[MatchRecord], extras: dict[int, MatchExtras] | None, stat: str, *, predict: bool
) -> list[Row]:
    rows: list[Row] = []
    for m in matches:
        h, a = stat_pair(m, (extras or {}).get(m.lab_match_id), stat)
        usable = h is not None and a is not None
        rows.append(
            Row(
                key=m.lab_match_id,
                competition=m.competition,
                season_label=m.season_label,
                day=m.day,
                home_team=m.home_team,
                away_team=m.away_team,
                y_home=float(h) if usable else math.nan,
                y_away=float(a) if usable else math.nan,
                usable=usable,
                predict=predict,
                eligible=bool(m.eval_eligible),
            )
        )
    return rows


def _target_rows(targets: Iterable[Target]) -> list[Row]:
    return [
        Row(
            key=t.key,
            competition=t.competition,
            season_label=t.season_label,
            day=(t.match_date - _EPOCH).days,
            home_team=t.home_team,
            away_team=t.away_team,
            y_home=math.nan,
            y_away=math.nan,
            usable=False,
            predict=True,
            eligible=False,
        )
        for t in targets
    ]


def _groups(rows: list[Row]) -> dict[str, list[Row]]:
    out: dict[str, list[Row]] = {}
    for r in rows:
        out.setdefault(group_of(r.competition), []).append(r)
    return out


# --- Corse (con cache e parallelismo) ---------------------------------------------------------


def _rows_fingerprint(rows: list[Row], config: StatsConfig, stat: str) -> str:
    h = hashlib.sha1()
    h.update(config.fingerprint().encode())
    h.update(stat.encode())
    for r in sorted(rows, key=lambda r: (r.day, r.competition, r.home_team, str(r.key))):
        h.update(f"{r.key}|{r.competition}|{r.season_label}|{r.day}|{r.home_team}|{r.away_team}|{r.y_home}|{r.y_away}|{int(r.usable)}|{int(r.predict)}|{int(r.eligible)}\n".encode())
    return h.hexdigest()[:20]


def _cache_path(config: StatsConfig, fp: str, stat: str, hyper: Hyper) -> Path | None:
    if config.cache_dir is None:
        return None
    safe = hyper.key.replace("|", "_").replace("=", "")
    return Path(config.cache_dir) / "runs" / fp / f"{stat}_{safe}.npz"


def _run_task(args: tuple[GroupData, Hyper, float]) -> RunArrays:
    g, hyper, prior = args
    return run_group(g, hyper, prior)


def _run_many(tasks: list[tuple[GroupData, Hyper, float]], workers: int) -> list[RunArrays]:
    workers = cap_workers(workers)
    if workers <= 1 or len(tasks) <= 1:
        return [_run_task(t) for t in tasks]
    with ProcessPoolExecutor(max_workers=min(workers, len(tasks))) as ex:
        return list(ex.map(_run_task, tasks, chunksize=1))


def history_runs(
    matches: Sequence[MatchRecord],
    extras: dict[int, MatchExtras] | None,
    config: StatsConfig,
    *,
    stats: Sequence[str] | None = None,
) -> dict[str, dict[str, RunArrays]]:
    """Per statistica e iperparametro della griglia: corsa walk-forward completa sullo storico."""
    stats = list(stats or config.stats)
    out: dict[str, dict[str, RunArrays]] = {s: {} for s in stats}
    pending: list[tuple[str, Hyper, str]] = []  # (stat, hyper, group)
    groups_by_stat: dict[str, dict[str, GroupData]] = {}
    fps: dict[str, str] = {}
    for stat in stats:
        rows = _history_rows(matches, extras, stat, predict=True)
        fps[stat] = _rows_fingerprint(rows, config, stat)
        groups_by_stat[stat] = {name: build_group(name, rs) for name, rs in _groups(rows).items()}
        for hyper in config.hyper_grid:
            path = _cache_path(config, fps[stat], stat, hyper)
            if path is not None and path.exists():
                with np.load(path, allow_pickle=True) as d:
                    out[stat][hyper.key] = RunArrays.from_npz(d)
                continue
            for name in groups_by_stat[stat]:
                pending.append((stat, hyper, name))
    if pending:
        tasks = [(groups_by_stat[s][g], h, config.prior_log_level[s]) for s, h, g in pending]
        results = _run_many(tasks, config.workers)
        parts: dict[tuple[str, str], list[RunArrays]] = {}
        for (stat, hyper, _), res in zip(pending, results):
            parts.setdefault((stat, hyper.key), []).append(res)
        for (stat, hkey), lst in parts.items():
            run = RunArrays.concat(lst)
            out[stat][hkey] = run
            hyper = next(h for h in config.hyper_grid if h.key == hkey)
            path = _cache_path(config, fps[stat], stat, hyper)
            if path is not None:
                path.parent.mkdir(parents=True, exist_ok=True)
                np.savez(path, **run.to_npz())
    return out


# --- Assemblaggio: scelta per stagione, dispersione, incertezza ----------------------------------


def _log_sd(run: RunArrays, sigma: float) -> tuple[np.ndarray, np.ndarray]:
    """var(for_i) = 1/(1/sigma² + evidenza_i · media_divisione); lato = for(attaccante) + against(difensore)."""
    mdiv = 0.5 * (run.divmean_h + run.divmean_a)
    prec0 = 1.0 / (sigma * sigma)
    var_h_team = 1.0 / (prec0 + run.ev_h * mdiv)
    var_a_team = 1.0 / (prec0 + run.ev_a * mdiv)
    sd_h = np.sqrt(var_h_team + var_a_team)  # for(casa) + against(ospite)
    sd_a = np.sqrt(var_a_team + var_h_team)  # for(ospite) + against(casa)
    return sd_h, sd_a


def _select_rows(run: RunArrays, mask: np.ndarray) -> RunArrays:
    out = RunArrays(xi=run.xi, sigma=run.sigma)
    idx = np.flatnonzero(mask)
    for name in RunArrays._LISTS:
        vals = getattr(run, name)
        setattr(out, name, [vals[i] for i in idx])
    for name in RunArrays._ARRAYS:
        setattr(out, name, getattr(run, name)[idx])
    return out


def _assemble(
    stat: str,
    runs_by_hyper: dict[str, RunArrays],
    specs: dict[str, SeasonSpec],
    *,
    row_runs: dict[str, RunArrays] | None = None,
) -> StatPredictions:
    """Per ogni stagione prevista prende la corsa dell'iperparametro scelto e applica la dispersione.

    row_runs: corse alternative (bersagli) per iperparametro; se None si usano le corse storiche.
    """
    source = row_runs if row_runs is not None else runs_by_hyper
    parts: list[RunArrays] = []
    alphas_h: list[np.ndarray] = []
    alphas_a: list[np.ndarray] = []
    sds_h: list[np.ndarray] = []
    sds_a: list[np.ndarray] = []
    for season, spec in specs.items():
        run = source[spec.hyper.key]
        mask = np.array([s == season for s in run.season], dtype=bool)
        if not np.any(mask):
            continue
        sel = _select_rows(run, mask)
        a = np.array([spec.alpha.get(c) or 0.0 for c in sel.competition], dtype=float)
        sd_h, sd_a = _log_sd(sel, spec.hyper.sigma)
        parts.append(sel)
        alphas_h.append(a)
        alphas_a.append(a)
        sds_h.append(sd_h)
        sds_a.append(sd_a)
    if not parts:
        empty = RunArrays(xi=0.0, sigma=0.0)
        return StatPredictions(stat, empty, np.zeros(0), np.zeros(0), np.zeros(0), np.zeros(0), specs)
    run = RunArrays.concat(parts)
    return StatPredictions(
        stat=stat,
        run=run,
        alpha_h=np.concatenate(alphas_h),
        alpha_a=np.concatenate(alphas_a),
        sd_h=np.concatenate(sds_h),
        sd_a=np.concatenate(sds_a),
        specs=specs,
    )


def fit_history(history: History, config: StatsConfig = ADOPTED_CONFIG) -> dict[str, StatPredictions]:
    """Previsioni walk-forward di tutte le partite dello storico, per statistica."""
    seasons = sorted({m.season_label for m in history.matches})
    runs = history_runs(history.matches, history.extras, config)
    out: dict[str, StatPredictions] = {}
    for stat in config.stats:
        specs = build_specs(runs[stat], history_seasons=seasons, seasons_to_predict=seasons, config=config)
        out[stat] = _assemble(stat, runs[stat], specs)
    return out


def fit_targets(
    history: History | Sequence[MatchRecord],
    targets: Sequence[Target],
    config: StatsConfig = ADOPTED_CONFIG,
    *,
    extras: dict[int, MatchExtras] | None = None,
) -> dict[str, StatPredictions]:
    """Previsioni dei bersagli: una stima per gruppo e giorno bersaglio, solo con partite precedenti."""
    if isinstance(history, History):
        matches, extras = history.matches, history.extras
    else:
        matches = list(history)
    seasons = sorted({m.season_label for m in matches})
    target_seasons = sorted({t.season_label for t in targets})
    runs = history_runs(matches, extras, config)
    out: dict[str, StatPredictions] = {}
    for stat in config.stats:
        specs = build_specs(runs[stat], history_seasons=seasons, seasons_to_predict=target_seasons, config=config)
        needed = {spec.hyper for spec in specs.values()}
        rows = _history_rows(matches, extras, stat, predict=False) + _target_rows(targets)
        groups = {name: build_group(name, rs) for name, rs in _groups(rows).items()}
        target_groups = {group_of(t.competition) for t in targets}
        tasks = [(groups[g], h, config.prior_log_level[stat]) for h in needed for g in sorted(target_groups) if g in groups]
        results = _run_many(tasks, config.workers)
        by_hyper: dict[str, list[RunArrays]] = {}
        for (g, h, _), res in zip(tasks, results):
            by_hyper.setdefault(h.key, []).append(res)
        row_runs = {k: RunArrays.concat(v) for k, v in by_hyper.items()}
        out[stat] = _assemble(stat, runs[stat], specs, row_runs=row_runs)
    return out


# --- Payload ----------------------------------------------------------------------------------


def load_exam_verdicts(path: Path = EXAM_RESULT_PATH) -> dict[str, str]:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    out: dict[str, str] = {}
    for stat, block in (data.get("stats") or {}).items():
        v = block.get("verdict") if isinstance(block, dict) else None
        if v in ("superato", "non_superato"):
            out[stat] = v
    return out


def _round(x: float, nd: int) -> float:
    return float(round(float(x), nd))


def _side_payload(
    *,
    stat: str,
    mean: float,
    alpha: float,
    sd_log: float,
    division_mean: float,
    rank_for: int | None,
    rank_against: int | None,
    teams_in_division: int | None,
    evidence: float,
    z: float,
) -> dict:
    lines = np.array(STAT_LINES[stat], dtype=float)
    p = dist.prob_over(lines, mean, alpha)
    p_lo = dist.prob_over(lines, mean * math.exp(-z * sd_log), alpha)
    p_hi = dist.prob_over(lines, mean * math.exp(z * sd_log), alpha)
    lo = np.minimum(p_lo, p_hi)
    hi = np.maximum(p_lo, p_hi)
    return {
        "mean": _round(mean, 3),
        "dispersion": (_round(alpha, 4) if alpha > 0 else None),
        "division_mean": _round(division_mean, 3),
        "rank_for": rank_for,
        "rank_against": rank_against,
        "teams_in_division": teams_in_division,
        "evidence": _round(evidence, 2),
        "lines": {
            f"{line:g}": {"over": _round(p[i], 4), "lo": _round(lo[i], 4), "hi": _round(hi[i], 4)}
            for i, line in enumerate(lines)
        },
    }


def build_payloads(
    preds: dict[str, StatPredictions], config: StatsConfig, exam: dict[str, str] | None
) -> dict[object, dict]:
    exam = exam if exam is not None else load_exam_verdicts()
    out: dict[object, dict] = {}
    for stat, sp in preds.items():
        run = sp.run
        mt, at, st = sp.side("total")
        for i, key in enumerate(run.keys):
            payload = out.setdefault(key, {"engine_version": config.version, "stats": {}})
            n_teams = int(run.n_teams[i])
            payload["stats"][stat] = {
                "exam": exam.get(stat, EXAM_PENDING),
                "home": _side_payload(
                    stat=stat,
                    mean=run.mean_h[i],
                    alpha=sp.alpha_h[i],
                    sd_log=sp.sd_h[i],
                    division_mean=run.divmean_h[i],
                    rank_for=int(run.rank_for_h[i]),
                    rank_against=int(run.rank_ag_h[i]),
                    teams_in_division=n_teams,
                    evidence=run.ev_h[i],
                    z=config.interval_z,
                ),
                "away": _side_payload(
                    stat=stat,
                    mean=run.mean_a[i],
                    alpha=sp.alpha_a[i],
                    sd_log=sp.sd_a[i],
                    division_mean=run.divmean_a[i],
                    rank_for=int(run.rank_for_a[i]),
                    rank_against=int(run.rank_ag_a[i]),
                    teams_in_division=n_teams,
                    evidence=run.ev_a[i],
                    z=config.interval_z,
                ),
                "total": _side_payload(
                    stat=stat,
                    mean=mt[i],
                    alpha=at[i],
                    sd_log=st[i],
                    division_mean=run.divmean_h[i] + run.divmean_a[i],
                    rank_for=None,
                    rank_against=None,
                    teams_in_division=None,
                    evidence=min(run.ev_h[i], run.ev_a[i]),
                    z=config.interval_z,
                ),
            }
    return out


def predict_history(
    history: History, config: StatsConfig = ADOPTED_CONFIG, *, exam: dict[str, str] | None = None
) -> dict[int, dict]:
    """Payload `stats` per ogni partita dello storico (chiave lab_match_id), walk-forward."""
    return build_payloads(fit_history(history, config), config, exam)  # type: ignore[return-value]


def predict_targets(
    history_matches: History | Sequence[MatchRecord],
    targets: Sequence[Target],
    config: StatsConfig = ADOPTED_CONFIG,
    *,
    extras: dict[int, MatchExtras] | None = None,
    exam: dict[str, str] | None = None,
) -> dict[str, dict]:
    """Payload `stats` per ogni bersaglio (chiave Target.key). I bersagli non entrano mai nelle finestre.

    Con una lista di MatchRecord senza `extras` i corner non sono disponibili: quella statistica
    parte dal solo a priori.
    """
    if not targets:
        return {}
    return build_payloads(fit_targets(history_matches, targets, config, extras=extras), config, exam)  # type: ignore[return-value]


__all__ = [
    "Target",
    "StatPredictions",
    "fit_history",
    "fit_targets",
    "history_runs",
    "predict_history",
    "predict_targets",
    "load_exam_verdicts",
    "build_payloads",
    "previous_season",
]
