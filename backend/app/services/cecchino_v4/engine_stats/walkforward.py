"""Walk-forward per piramide nazionale su una statistica (PREREGISTRAZIONE_FASE_2 §2.1-2.2, 2.5).

Per ogni giorno di gara del gruppo: finestra = partite usabili dei giorni strettamente
precedenti, pesate exp(-xi·giorni); stima fatto/subito con lo stimatore V3 (libreria);
previsione delle righe `predict` del giorno. Le righe non usabili (statistica mancante o
partite bersaglio) non entrano mai nella finestra.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
from threadpoolctl import threadpool_limits

from app.services.cecchino_v3.constants import COUNTRY_GROUPS, MIN_TIME_WEIGHT, Hyper
from app.services.cecchino_v3.strength_model import (
    ParamLayout,
    WindowData,
    expected_goals,
    fit_strength,
    team_divisions,
)


@dataclass
class Row:
    """Una partita (storica o bersaglio) vista dal motore statistiche."""

    key: object  # lab_match_id (int) o chiave del bersaglio (str)
    competition: str
    season_label: str
    day: int
    home_team: str
    away_team: str
    y_home: float  # NaN se non usabile
    y_away: float
    usable: bool  # entra nelle finestre
    predict: bool  # va prevista
    eligible: bool  # eval_eligible (solo storico)


@dataclass
class GroupData:
    group: str
    divisions: tuple[str, ...]
    teams: list[str]
    keys: list[object]
    season: list[str]
    day: np.ndarray
    home: np.ndarray
    away: np.ndarray
    division: np.ndarray
    y_home: np.ndarray
    y_away: np.ndarray
    usable: np.ndarray
    predict: np.ndarray
    eligible: np.ndarray
    newcomer: np.ndarray


def divisions_for_group(group: str, rows: list[Row]) -> tuple[str, ...]:
    if group in COUNTRY_GROUPS:
        return COUNTRY_GROUPS[group]
    return tuple(sorted({r.competition for r in rows}))


def build_group(group: str, rows: list[Row]) -> GroupData:
    rows = sorted(rows, key=lambda r: (r.day, r.competition, r.home_team, str(r.key)))
    divisions = divisions_for_group(group, rows)
    div_index = {c: i for i, c in enumerate(divisions)}
    teams = sorted({r.home_team for r in rows} | {r.away_team for r in rows})
    team_index = {t: i for i, t in enumerate(teams)}
    first_season = min(r.season_label for r in rows)
    team_first: dict[str, str] = {}
    for r in rows:
        for t in (r.home_team, r.away_team):
            if t not in team_first or r.season_label < team_first[t]:
                team_first[t] = r.season_label
    return GroupData(
        group=group,
        divisions=divisions,
        teams=teams,
        keys=[r.key for r in rows],
        season=[r.season_label for r in rows],
        day=np.array([r.day for r in rows], dtype=np.int64),
        home=np.array([team_index[r.home_team] for r in rows], dtype=np.int64),
        away=np.array([team_index[r.away_team] for r in rows], dtype=np.int64),
        division=np.array([div_index[r.competition] for r in rows], dtype=np.int64),
        y_home=np.array([r.y_home for r in rows], dtype=float),
        y_away=np.array([r.y_away for r in rows], dtype=float),
        usable=np.array([r.usable for r in rows], dtype=bool),
        predict=np.array([r.predict for r in rows], dtype=bool),
        eligible=np.array([r.eligible for r in rows], dtype=bool),
        newcomer=np.array([1.0 if team_first[t] > first_season else 0.0 for t in teams], dtype=float),
    )


@dataclass
class RunArrays:
    """Previsioni grezze delle righe `predict` di un gruppo, in ordine cronologico."""

    xi: float
    sigma: float
    keys: list[object] = field(default_factory=list)
    season: list[str] = field(default_factory=list)
    competition: list[str] = field(default_factory=list)
    home_team: list[str] = field(default_factory=list)
    away_team: list[str] = field(default_factory=list)
    mean_h: np.ndarray = field(default_factory=lambda: np.zeros(0))
    mean_a: np.ndarray = field(default_factory=lambda: np.zeros(0))
    ev_h: np.ndarray = field(default_factory=lambda: np.zeros(0))
    ev_a: np.ndarray = field(default_factory=lambda: np.zeros(0))
    divmean_h: np.ndarray = field(default_factory=lambda: np.zeros(0))
    divmean_a: np.ndarray = field(default_factory=lambda: np.zeros(0))
    for_h: np.ndarray = field(default_factory=lambda: np.zeros(0))
    ag_h: np.ndarray = field(default_factory=lambda: np.zeros(0))
    for_a: np.ndarray = field(default_factory=lambda: np.zeros(0))
    ag_a: np.ndarray = field(default_factory=lambda: np.zeros(0))
    rank_for_h: np.ndarray = field(default_factory=lambda: np.zeros(0, dtype=np.int64))
    rank_ag_h: np.ndarray = field(default_factory=lambda: np.zeros(0, dtype=np.int64))
    rank_for_a: np.ndarray = field(default_factory=lambda: np.zeros(0, dtype=np.int64))
    rank_ag_a: np.ndarray = field(default_factory=lambda: np.zeros(0, dtype=np.int64))
    n_teams: np.ndarray = field(default_factory=lambda: np.zeros(0, dtype=np.int64))
    y_h: np.ndarray = field(default_factory=lambda: np.zeros(0))
    y_a: np.ndarray = field(default_factory=lambda: np.zeros(0))
    usable: np.ndarray = field(default_factory=lambda: np.zeros(0, dtype=bool))
    eligible: np.ndarray = field(default_factory=lambda: np.zeros(0, dtype=bool))

    _ARRAYS = (
        "mean_h", "mean_a", "ev_h", "ev_a", "divmean_h", "divmean_a", "for_h", "ag_h", "for_a", "ag_a",
        "rank_for_h", "rank_ag_h", "rank_for_a", "rank_ag_a", "n_teams", "y_h", "y_a", "usable", "eligible",
    )
    _LISTS = ("keys", "season", "competition", "home_team", "away_team")

    def __len__(self) -> int:
        return len(self.keys)

    @classmethod
    def concat(cls, parts: list["RunArrays"]) -> "RunArrays":
        if not parts:
            raise ValueError("nessuna corsa da concatenare")
        out = cls(xi=parts[0].xi, sigma=parts[0].sigma)
        for name in cls._LISTS:
            setattr(out, name, [v for p in parts for v in getattr(p, name)])
        for name in cls._ARRAYS:
            setattr(out, name, np.concatenate([getattr(p, name) for p in parts]))
        return out

    def to_npz(self) -> dict[str, np.ndarray]:
        d = {name: getattr(self, name) for name in self._ARRAYS}
        for name in self._LISTS:
            d[name] = np.array([str(v) for v in getattr(self, name)], dtype=object)
        d["xi"] = np.array([self.xi])
        d["sigma"] = np.array([self.sigma])
        d["key_is_int"] = np.array([all(isinstance(k, int) for k in self.keys)])
        return d

    @classmethod
    def from_npz(cls, d) -> "RunArrays":
        out = cls(xi=float(d["xi"][0]), sigma=float(d["sigma"][0]))
        for name in cls._ARRAYS:
            setattr(out, name, np.asarray(d[name]))
        key_is_int = bool(d["key_is_int"][0])
        for name in cls._LISTS:
            vals = [str(v) for v in d[name].tolist()]
            if name == "keys" and key_is_int:
                vals = [int(v) for v in vals]
            setattr(out, name, vals)
        return out


def _ranks(values: np.ndarray, members: list[int]) -> dict[int, int]:
    """Posizione 1-based per valore decrescente fra i membri (a pari merito, ordine stabile)."""
    order = sorted(members, key=lambda t: (-values[t], t))
    return {t: i + 1 for i, t in enumerate(order)}


def run_group(g: GroupData, hyper: Hyper, prior_log_level: float) -> RunArrays:
    with threadpool_limits(limits=1, user_api="blas"):
        return _run_group(g, hyper, prior_log_level)


def _run_group(g: GroupData, hyper: Hyper, prior_log_level: float) -> RunArrays:
    n = len(g.keys)
    nd, nt = len(g.divisions), len(g.teams)
    layout = ParamLayout(n_divisions=nd, n_teams=nt)
    max_age = math.log(1.0 / MIN_TIME_WEIGHT) / hyper.xi
    prior_mean = math.exp(prior_log_level)
    team_ids = np.arange(nt)

    out = RunArrays(xi=hyper.xi, sigma=hyper.sigma)
    cols: dict[str, list] = {name: [] for name in RunArrays._ARRAYS}
    seen: dict[tuple[str, int], set[int]] = {}
    beta: np.ndarray | None = None
    start = 0
    i = 0
    while i < n:
        today = g.day[i]
        j = i
        while j < n and g.day[j] == today:
            j += 1
        while start < i and today - g.day[start] > max_age:
            start += 1
        pred = np.arange(i, j)[g.predict[i:j]]
        if pred.size:
            past = np.arange(start, i)[g.usable[start:i]]
            w = np.exp(-hyper.xi * (today - g.day[past]).astype(float))
            window = WindowData(
                home=g.home[past],
                away=g.away[past],
                division=g.division[past],
                home_goals=g.y_home[past],
                away_goals=g.y_away[past],
                weight=w,
            )
            fallback = np.zeros(nt, dtype=np.int64)
            fallback[g.home[i:j]] = g.division[i:j]
            fallback[g.away[i:j]] = g.division[i:j]
            team_div = team_divisions(window, n_teams=nt, n_divisions=nd, fallback=fallback)
            beta = fit_strength(
                layout,
                window,
                team_division=team_div,
                newcomer=g.newcomer,
                sigma=hyper.sigma,
                beta_start=beta,
                prior_log_level=prior_log_level,
            )
            mh, ma = expected_goals(
                layout,
                beta,
                division=g.division[pred],
                home=g.home[pred],
                away=g.away[pred],
                team_division=team_div,
                newcomer=g.newcomer,
            )
            if past.size:
                evidence = np.bincount(window.home, weights=w, minlength=nt) + np.bincount(
                    window.away, weights=w, minlength=nt
                )
                wsum = np.bincount(window.division, weights=w, minlength=nd)
                dm_h = np.bincount(window.division, weights=w * window.home_goals, minlength=nd)
                dm_a = np.bincount(window.division, weights=w * window.away_goals, minlength=nd)
                with np.errstate(invalid="ignore", divide="ignore"):
                    dm_h = np.where(wsum > 0, dm_h / wsum, prior_mean)
                    dm_a = np.where(wsum > 0, dm_a / wsum, prior_mean)
            else:
                evidence = np.zeros(nt)
                dm_h = np.full(nd, prior_mean)
                dm_a = np.full(nd, prior_mean)

            att_idx = layout.level_att(team_div)
            def_idx = layout.level_def(team_div)
            level_att = np.where(att_idx >= 0, beta[np.maximum(att_idx, 0)], 0.0)
            level_def = np.where(def_idx >= 0, beta[np.maximum(def_idx, 0)], 0.0)
            for_all = level_att + beta[layout.nc_att] * g.newcomer + beta[layout.team_att(team_ids)]
            ag_all = level_def + beta[layout.nc_def] * g.newcomer + beta[layout.team_def(team_ids)]

            rank_cache: dict[tuple[str, int], tuple[dict[int, int], dict[int, int], int]] = {}
            for k in range(i, j):
                sd_key = (g.season[k], int(g.division[k]))
                if sd_key not in rank_cache:
                    members = set(seen.get(sd_key, set()))
                    for kk in range(i, j):
                        if g.season[kk] == sd_key[0] and g.division[kk] == sd_key[1]:
                            members.add(int(g.home[kk]))
                            members.add(int(g.away[kk]))
                    mem = sorted(members)
                    rank_cache[sd_key] = (_ranks(for_all, mem), _ranks(ag_all, mem), len(mem))

            for p, idx in enumerate(pred):
                d = int(g.division[idx])
                h, a = int(g.home[idx]), int(g.away[idx])
                r_for, r_ag, n_mem = rank_cache[(g.season[idx], d)]
                out.keys.append(g.keys[idx])
                out.season.append(g.season[idx])
                out.competition.append(g.divisions[d])
                out.home_team.append(g.teams[h])
                out.away_team.append(g.teams[a])
                cols["mean_h"].append(float(mh[p]))
                cols["mean_a"].append(float(ma[p]))
                cols["ev_h"].append(float(evidence[h]))
                cols["ev_a"].append(float(evidence[a]))
                cols["divmean_h"].append(float(dm_h[d]))
                cols["divmean_a"].append(float(dm_a[d]))
                cols["for_h"].append(float(for_all[h]))
                cols["ag_h"].append(float(ag_all[h]))
                cols["for_a"].append(float(for_all[a]))
                cols["ag_a"].append(float(ag_all[a]))
                cols["rank_for_h"].append(r_for[h])
                cols["rank_ag_h"].append(r_ag[h])
                cols["rank_for_a"].append(r_for[a])
                cols["rank_ag_a"].append(r_ag[a])
                cols["n_teams"].append(n_mem)
                cols["y_h"].append(float(g.y_home[idx]))
                cols["y_a"].append(float(g.y_away[idx]))
                cols["usable"].append(bool(g.usable[idx]))
                cols["eligible"].append(bool(g.eligible[idx]))

        for k in range(i, j):
            seen.setdefault((g.season[k], int(g.division[k])), set()).update((int(g.home[k]), int(g.away[k])))
        i = j

    for name in RunArrays._ARRAYS:
        dtype = np.int64 if name.startswith("rank") or name == "n_teams" else (bool if name in ("usable", "eligible") else float)
        setattr(out, name, np.array(cols[name], dtype=dtype))
    return out
