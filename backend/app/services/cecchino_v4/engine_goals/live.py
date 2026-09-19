"""Previsione live del motore gol V4 per partite non ancora giocate.

Per ogni (piramide, giorno bersaglio) si stima UNA finestra con le sole partite
di giorno strettamente precedente (Forza, tiri in porta, tiri) usando le
funzioni di `strength_params`; poi si applicano orchestratore, Forma,
Calendario e le novita' adottate con gli oggetti stimati sull'ultima stagione
completa (`LiveArtifacts`). Le partite bersaglio non entrano mai in nessuna
finestra: eventuali copie nello storico vengono scartate e un controllo lo
verifica. Le stagioni successive a quella bersaglio non esistono nello storico
live per costruzione, ma vengono comunque escluse.

Squadre mai viste: livello della divisione con la correzione "squadra nuova"
della V3 (parametri di squadra al valore a priori), `new_team = true`,
incertezza `alta`.
"""

from __future__ import annotations

import copy
import math
from collections import defaultdict
from dataclasses import dataclass, replace
from datetime import date
from typing import Any

import numpy as np
from threadpoolctl import threadpool_limits

from app.services.cecchino_v3.calendar_features import compute_calendar
from app.services.cecchino_v3.constants import (
    FINAL_PHASE_MATCHES,
    GAME_STATS,
    PHASE_FINAL,
    PHASE_MID,
    group_of,
)
from app.services.cecchino_v3.data import MatchRecord
from app.services.cecchino_v3.form import Expectation, compute_form
from app.services.cecchino_v3.orchestrator import Opinions, combine

from app.services.cecchino_v4.engine_goals.additions import (
    HomeAdvState,
    HomeAdvantage,
    apply_calibration_bounds_many,
    apply_calibration_many,
    apply_home_advantage,
    home_advantage_kappa,
    uncertainty_level,
    uncertainty_score,
)
from app.services.cecchino_v4.engine_goals.config import (
    INTERVAL_SIGMA_BASE,
    INTERVAL_SIGMA_SLOPE,
    INTERVAL_Z90,
    LEVEL_MEDIUM,
    V4GoalsConfig,
)
from app.services.cecchino_v4.engine_goals.distributions import all_markets, market_intervals
from app.services.cecchino_v4.engine_goals.engine import LiveArtifacts, build_payload, predict_history_full
from app.services.cecchino_v4.engine_goals.strength_params import (
    DayParams,
    GameDayParams,
    GroupIndex,
    fit_day,
    fit_game_day,
    predict_pairs,
    prepare_group,
)
from app.services.cecchino_v4.history.football_data import History

_EPOCH = date(2000, 1, 1)


@dataclass(frozen=True)
class TargetMatch:
    key: str
    competition: str
    season_label: str
    match_date: date
    home_team: str
    away_team: str

    @property
    def day(self) -> int:
        return (self.match_date - _EPOCH).days

    @property
    def group(self) -> str:
        return group_of(self.competition)


def fit_live_artifacts(
    history_matches: list[MatchRecord],
    config: V4GoalsConfig,
    *,
    before_season: str,
    cache_key: str | None = None,
    workers: int | None = None,
) -> LiveArtifacts:
    """Oggetti per la stagione `before_season` stimati SOLO sulle stagioni
    precedenti (walk-forward completo sullo storico, senza intervalli)."""
    past = [m for m in history_matches if m.season_label < before_season]
    if not past:
        raise ValueError(f"nessuna stagione completa prima di {before_season}")
    run = predict_history_full(
        History(matches=past, extras={}), config, cache_key=cache_key, workers=workers, compute_intervals=False
    )
    return run.artifacts


def _target_signature(competition: str, day: int, home: str, away: str) -> tuple[str, int, str, str]:
    return (competition, day, home.strip(), away.strip())


def _synthetic(t: TargetMatch, idx: int) -> MatchRecord:
    return MatchRecord(
        lab_match_id=-(idx + 1),
        competition=t.competition,
        group=t.group,
        season_label=t.season_label,
        match_date=t.match_date,
        kickoff_at=None,
        day=t.day,
        home_team=t.home_team.strip(),
        away_team=t.away_team.strip(),
        ft_home=0,
        ft_away=0,
        ht_home=None,
        ht_away=None,
    )


def predict_targets(
    history_matches: list[MatchRecord],
    targets: list[TargetMatch],
    config: V4GoalsConfig,
    *,
    artifacts: LiveArtifacts | None = None,
    cache_key: str | None = None,
    workers: int | None = None,
) -> dict[str, dict[str, Any]]:
    """Payload "goals" (docs/v4/API.md) per ogni bersaglio, indicizzato per `key`."""
    if not targets:
        return {}
    signatures = {_target_signature(t.competition, t.day, t.home_team, t.away_team) for t in targets}
    target_season = min(t.season_label for t in targets)
    history = [
        m
        for m in history_matches
        if _target_signature(m.competition, m.day, m.home_team, m.away_team) not in signatures
        and m.season_label <= max(t.season_label for t in targets)
    ]
    if artifacts is None:
        artifacts = fit_live_artifacts(history, config, before_season=target_season, cache_key=cache_key, workers=workers)

    by_group: dict[str, list[TargetMatch]] = defaultdict(list)
    for t in targets:
        by_group[t.group].append(t)
    out: dict[str, dict[str, Any]] = {}
    history.sort(key=lambda m: (m.day, m.lab_match_id))
    for group, group_targets in by_group.items():
        gm = [m for m in history if m.group == group]
        if not gm:
            raise ValueError(f"nessuna partita storica per la piramide {group!r}")
        for season in sorted({t.season_label for t in group_targets}):
            season_targets = [t for t in group_targets if t.season_label == season]
            out.update(_predict_group(gm, season_targets, season, artifacts, config))
    return out


# --- una piramide, una stagione ------------------------------------------------------------------


def _phase(played: int, matches_per_team: int | None) -> str:
    if matches_per_team is None:
        return PHASE_MID
    remaining = matches_per_team - played
    return PHASE_FINAL if remaining <= FINAL_PHASE_MATCHES else PHASE_MID


def _predict_group(
    gm: list[MatchRecord],
    targets: list[TargetMatch],
    season: str,
    art: LiveArtifacts,
    config: V4GoalsConfig,
) -> dict[str, dict[str, Any]]:
    target_days = {t.day for t in targets}
    extra_teams = {t.home_team.strip() for t in targets} | {t.away_team.strip() for t in targets}
    g = prepare_group(gm, extra_teams=extra_teams)
    synthetic = {t.key: _synthetic(t, i) for i, t in enumerate(targets)}
    key_of = {rec.lab_match_id: k for k, rec in synthetic.items()}

    season_matches = [m for m in gm if m.season_label == season]
    days = sorted({m.day for m in season_matches} | target_days)
    max_target_day = max(target_days)

    expectations: dict[int, Expectation] = {}  # attese di base delle partite gia' giocate (forma)
    final_lam: dict[int, tuple[float, float]] = {}  # gol attesi finali (residui vantaggio casa)
    ha_states: dict[tuple[str, str], HomeAdvState] = copy.deepcopy(art.home_adv_states)
    played: dict[tuple[str, str], int] = defaultdict(int)
    seen: dict[str, set[str]] = defaultdict(set)
    beta_f: np.ndarray | None = None
    beta_g: dict[str, np.ndarray | None] = {s: None for s in GAME_STATS}
    out: dict[str, dict[str, Any]] = {}

    with threadpool_limits(limits=1, user_api="blas"):
        for today in days:
            if today > max_target_day:
                break
            real_today = [m for m in season_matches if m.day == today]
            targets_today = [synthetic[t.key] for t in targets if t.day == today]
            items: list[MatchRecord] = []
            for m in real_today + targets_today:
                ph = _phase(played[(m.competition, m.home_team)], art.matches_per_team.get(m.competition))
                pa = _phase(played[(m.competition, m.away_team)], art.matches_per_team.get(m.competition))
                items.append(replace(m, phase=PHASE_FINAL if PHASE_FINAL in (ph, pa) else PHASE_MID))
            # controllo: nessun bersaglio (id negativo) nello storico che alimenta le finestre;
            # `window_rows` usa per costruzione solo giorni strettamente precedenti a `today`
            if any(m.lab_match_id < 0 for m in gm):
                raise RuntimeError("una partita bersaglio e' finita nello storico")

            fallback = np.zeros(g.layout.n_teams, dtype=np.int64)
            for m in items:
                fallback[g.team_index[m.home_team]] = g.div_index[m.competition]
                fallback[g.team_index[m.away_team]] = g.div_index[m.competition]
            fp: DayParams = fit_day(g, today, art.hyper_forza, fallback=fallback, beta_start=beta_f)
            beta_f = fp.beta
            gp: dict[str, GameDayParams] = {}
            for stat in GAME_STATS:
                gp[stat] = fit_game_day(g, today, art.hyper_game[stat], stat, fallback=fallback, beta_start=beta_g[stat])
                beta_g[stat] = gp[stat].beta

            div = np.array([g.div_index[m.competition] for m in items], dtype=np.int64)
            home = np.array([g.team_index[m.home_team] for m in items], dtype=np.int64)
            away = np.array([g.team_index[m.away_team] for m in items], dtype=np.int64)
            lam_f = predict_pairs(g, fp.beta, fp.team_division, division=div, home=home, away=away)
            vols = {
                stat: predict_pairs(g, gp[stat].beta, gp[stat].team_division, division=div, home=home, away=away)
                for stat in GAME_STATS
            }

            # forma e calendario del giorno: storia dei giorni precedenti + partite del giorno
            past_season = [m for m in season_matches if m.day < today]
            form = compute_form(past_season + items, expectations)
            calendar = compute_calendar([m for m in gm if m.day < today] + items)

            centers: list[dict[str, float]] = []
            metas: list[dict[str, Any]] = []
            for k, m in enumerate(items):
                d = int(div[k])
                conv = {stat: float(gp[stat].conversion[d]) for stat in GAME_STATS}
                ops_home = {"forza": float(lam_f[0][k]), **{s: float(vols[s][0][k]) * conv[s] for s in GAME_STATS}}
                ops_away = {"forza": float(lam_f[1][k]), **{s: float(vols[s][1][k]) * conv[s] for s in GAME_STATS}}
                fm = form[m.lab_match_id]
                cal = calendar[m.lab_match_id]
                adj_home = {"form_goals": fm.goals_home, "form_shots": fm.shots_home, **cal.adjust_home}
                adj_away = {"form_goals": fm.goals_away, "form_shots": fm.shots_away, **cal.adjust_away}
                base_h, base_a = combine(Opinions(home=ops_home, away=ops_away), art.base_weights)
                lh, la = combine(
                    Opinions(home=ops_home, away=ops_away, adjust_home=adj_home, adjust_away=adj_away), art.final_weights
                )
                if m.lab_match_id > 0:
                    expectations[m.lab_match_id] = Expectation(
                        goals_home=base_h,
                        goals_away=base_a,
                        shots_home=float(vols["shots"][0][k]),
                        shots_away=float(vols["shots"][1][k]),
                    )
                    final_lam[m.lab_match_id] = (lh, la)
                    continue
                # solo bersagli da qui in avanti
                ha: HomeAdvantage | None = None
                if config.team_home_advantage:
                    hh = ha_states.get((m.group, m.home_team), HomeAdvState()).deviation(today)
                    hv = ha_states.get((m.group, m.away_team), HomeAdvState()).deviation(today)
                    ha = HomeAdvantage(kappa=home_advantage_kappa(hh, hv, lh, la), hdev_home=hh, hdev_away=hv)
                    lh, la = apply_home_advantage(lh, la, ha.kappa)
                rho = fp.rho_for(d) if config.division_rho else fp.rho_group
                alphas = art.dispersion.get(m.competition, (None, None)) if config.division_dispersion else (None, None)
                ht_share = float(fp.ht_share[d])
                probs = all_markets(lh, la, rho, ht_share, alpha_home=alphas[0], alpha_away=alphas[1], with_ah=config.asian_handicap)
                ev_h, ev_a = float(fp.evidence[home[k]]), float(fp.evidence[away[k]])
                opinions = {name: (ops_home[name], ops_away[name]) for name in ops_home}
                unc = uncertainty_score(ev_h, ev_a, opinions)
                specialists: dict[str, Any] = {
                    "forza": {"home": round(ops_home["forza"], 5), "away": round(ops_away["forza"], 5)},
                    "weights": dict(art.final_weights),
                    "form": {
                        "goals_home": round(fm.goals_home, 5),
                        "goals_away": round(fm.goals_away, 5),
                        "shots_home": round(fm.shots_home, 5),
                        "shots_away": round(fm.shots_away, 5),
                        "matches_home": fm.matches_home,
                        "matches_away": fm.matches_away,
                        **fm.detail,
                    },
                    "calendar": {
                        "rest_days_home": cal.rest_days_home,
                        "rest_days_away": cal.rest_days_away,
                        "final_phase": cal.final_phase,
                    },
                }
                for stat in GAME_STATS:
                    specialists[stat] = {
                        "home": round(ops_home[stat], 5),
                        "away": round(ops_away[stat], 5),
                        "volume_home": round(float(vols[stat][0][k]), 3),
                        "volume_away": round(float(vols[stat][1][k]), 3),
                    }
                ratings: dict[str, Any] | None = None
                if config.ratings:
                    peers = set(seen[m.competition]) | {m.home_team, m.away_team}
                    ratings = {
                        "home": _ratings(g, fp, m.competition, m.home_team, peers, ha.hdev_home if ha else 0.0),
                        "away": _ratings(g, fp, m.competition, m.away_team, peers, ha.hdev_away if ha else 0.0),
                    }
                centers.append(probs)
                metas.append(
                    {
                        "key": key_of[m.lab_match_id],
                        "lam": (lh, la),
                        "rho": rho,
                        "ht_share": ht_share,
                        "alphas": alphas,
                        "unc": unc,
                        "ev": (ev_h, ev_a),
                        "ratings": ratings,
                        "specialists": specialists,
                        "ha": ha,
                    }
                )

            # aggiornamento stato dopo il giorno (solo partite giocate)
            for m in real_today:
                played[(m.competition, m.home_team)] += 1
                played[(m.competition, m.away_team)] += 1
                seen[m.competition].update((m.home_team, m.away_team))
                exp = final_lam.get(m.lab_match_id)
                if exp is not None:
                    resid = (m.ft_home - m.ft_away) - (exp[0] - exp[1])
                    ha_states.setdefault((m.group, m.home_team), HomeAdvState()).add(today, resid, at_home=True)
                    ha_states.setdefault((m.group, m.away_team), HomeAdvState()).add(today, -resid, at_home=False)

            if not centers:
                continue
            applied = config.isotonic_calibration and art.calibration_applied
            finals = apply_calibration_many(centers, art.calibration) if applied else centers
            los: list[dict[str, float]] = []
            his: list[dict[str, float]] = []
            if config.uncertainty:
                for c, meta in zip(centers, metas):
                    sigma = INTERVAL_SIGMA_BASE + INTERVAL_SIGMA_SLOPE * meta["unc"].score
                    iv = market_intervals(
                        meta["lam"][0], meta["lam"][1], meta["rho"], meta["ht_share"], sigma, INTERVAL_Z90, c,
                        alpha_home=meta["alphas"][0], alpha_away=meta["alphas"][1], with_ah=config.asian_handicap,
                    )
                    los.append({k: v[0] for k, v in iv.items()})
                    his.append({k: v[1] for k, v in iv.items()})
                if applied:
                    los, his = apply_calibration_bounds_many(los, his, art.calibration)
            else:
                los, his = list(finals), list(finals)
            for meta, probs, lo, hi in zip(metas, finals, los, his):
                unc = meta["unc"]
                new_team = unc.new_team_home or unc.new_team_away
                level = uncertainty_level(unc.score, art.uncertainty_cuts, new_team=new_team) if config.uncertainty else LEVEL_MEDIUM
                if new_team:
                    level = uncertainty_level(unc.score, art.uncertainty_cuts, new_team=True)
                out[meta["key"]] = build_payload(
                    lam=meta["lam"],
                    rho=meta["rho"],
                    ht_share=meta["ht_share"],
                    alphas=meta["alphas"],
                    uncertainty=unc,
                    level=level,
                    home_evidence=meta["ev"][0],
                    away_evidence=meta["ev"][1],
                    probs=probs,
                    lo=lo,
                    hi=hi,
                    ratings=meta["ratings"],
                    specialists=meta["specialists"],
                    calibration_applied=applied,
                    calibration_season=art.fitted_on if applied else None,
                    home_advantage=meta["ha"],
                )
    return out


def _ratings(g: GroupIndex, dp: DayParams, competition: str, team: str, peers: set[str], hdev: float) -> dict[str, Any]:
    layout = g.layout
    d = g.div_index[competition]
    t = g.team_index[team]
    attack, defence = dp.attack(layout, t), dp.defence(layout, t)
    ids = [g.team_index[p] for p in peers if p in g.team_index]
    att_all = [dp.attack(layout, p) for p in ids]
    def_all = [dp.defence(layout, p) for p in ids]
    mu, home = dp.division_mu(layout, d), dp.division_home(layout, d)
    return {
        "attack": round(attack, 4),
        "defence": round(defence, 4),
        "attack_rank": 1 + sum(1 for v in att_all if v > attack + 1e-12),
        "defence_rank": 1 + sum(1 for v in def_all if v > defence + 1e-12),
        "teams_in_division": len(ids),
        "home_advantage": round(home + 0.5 * hdev / math.exp(mu + home / 2.0), 4),
    }


__all__ = ["TargetMatch", "fit_live_artifacts", "predict_targets"]
