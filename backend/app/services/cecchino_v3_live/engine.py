"""Calcolo V3 estesa sulle partite del giorno.

Stesso modello di riferimento del Lab, stessi passaggi walk-forward, parametri congelati
(vedi params.py). Cambia solo la fonte dei dati: le partite e le statistiche squadra
scaricate da API-Football per il campionato (stagione in corso + precedente).

- ogni campionato API-Football e' una piramide a divisione unica: le squadre si
  riconoscono per id, quindi non serve abbinare nomi al Lab;
- le partite da prevedere entrano in coda con il risultato a 0: sono sempre nel giorno
  piu' recente, quindi non entrano mai nella finestra delle altre previsioni;
- giocate e rimanenti vengono dal calendario completo della stagione (fase finale corretta);
- senza statistiche di tiri e tiri in porta nel campionato la V3 non si calcola.
"""

from __future__ import annotations

import logging
import time
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.constants import FINISHED_STATUSES
from app.models import Competition, Fixture
from app.models.fixture_team_stat import FixtureTeamStat
from app.services.cecchino_v3.calendar_features import compute_calendar
from app.services.cecchino_v3.constants import (
    FINAL_PHASE_MATCHES,
    MIN_MATCHES_PLAYED,
    PHASE_EARLY,
    PHASE_FINAL,
    PHASE_MID,
)
from app.services.cecchino_v3.data import MatchRecord
from app.services.cecchino_v3.form import Expectation, compute_form
from app.services.cecchino_v3.indices import IndexInput, compute_indices
from app.services.cecchino_v3.markets import market_probabilities
from app.services.cecchino_v3.orchestrator import Opinions, combine
from app.services.cecchino_v3.service import build_adjustments
from app.services.cecchino_v3.walkforward import run_game_group, run_group
from app.services.cecchino_v3_live.params import ENGINE_VERSION, V3Params, load_params

logger = logging.getLogger(__name__)

_EPOCH = date(2000, 1, 1)
_EXCLUDED_CALENDAR_STATUSES = frozenset({"CANC", "ABD", "AWD", "WO"})

# Qualita' minima dei dati di gioco (stagione in corso): partite del campionato con tiri e
# tiri in porta, e partite con statistiche di ciascuna delle due squadre.
MIN_MATCHES_WITH_STATS = 30
MIN_TEAM_MATCHES_WITH_STATS = 3

STATUS_OK = "ok"
STATUS_NO_STATS = "no_statistics"
STATUS_NO_COMPETITION = "no_competition"
STATUS_NOT_UPCOMING = "not_upcoming"


@dataclass
class _Built:
    records: list[MatchRecord]
    targets: set[int]
    current_season: str
    stats_current: int
    finished_current: int
    finished_previous: int
    team_stats: dict[str, int]


def _utc_day(dt: datetime | None) -> date | None:
    if dt is None:
        return None
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc)
    return dt.date()


def _ht(fixture: Fixture) -> tuple[int | None, int | None]:
    raw = fixture.raw_json if isinstance(fixture.raw_json, dict) else {}
    ht = ((raw.get("score") or {}).get("halftime") or {}) if isinstance(raw.get("score"), dict) else {}
    try:
        h, a = ht.get("home"), ht.get("away")
        return (int(h), int(a)) if h is not None and a is not None else (None, None)
    except (TypeError, ValueError):
        return None, None


def _stat_value(row: FixtureTeamStat | None, name: str) -> int | None:
    if row is None:
        return None
    if name == "shots":
        v = row.total_shots if row.total_shots is not None else row.shots
    elif name == "sot":
        v = row.shots_on_target
    elif name == "fouls":
        v = row.fouls
    elif name == "yellow":
        v = row.yellow_cards
    else:
        v = row.red_cards
    return int(v) if v is not None else None


def competitions_for(db: Session, comp: Competition) -> list[Competition]:
    prev = db.scalar(
        select(Competition).where(
            Competition.provider_league_id == comp.provider_league_id, Competition.season == int(comp.season) - 1
        )
    )
    return [c for c in (prev, comp) if c is not None]


def build_records(db: Session, comp: Competition, target_ids: set[int]) -> _Built:
    comps = competitions_for(db, comp)
    comp_ids = [int(c.id) for c in comps]
    season_of = {int(c.id): str(int(c.season)) for c in comps}
    label = f"api:{int(comp.provider_league_id)}"
    fixtures = list(db.scalars(select(Fixture).where(Fixture.competition_id.in_(comp_ids))).all())
    finished = [
        f for f in fixtures if f.status in FINISHED_STATUSES and f.goals_home is not None and f.goals_away is not None
    ]
    targets = [f for f in fixtures if int(f.id) in target_ids and f.status not in FINISHED_STATUSES]

    stats: dict[tuple[int, str], FixtureTeamStat] = {}
    ids = [int(f.id) for f in finished]
    for start in range(0, len(ids), 2000):
        for row in db.scalars(
            select(FixtureTeamStat).where(FixtureTeamStat.fixture_id.in_(ids[start : start + 2000]))
        ).all():
            stats[(int(row.fixture_id), str(row.team_id))] = row

    records: list[MatchRecord] = []
    current_season = str(int(comp.season))
    stats_current = 0
    team_stats: dict[str, int] = defaultdict(int)
    for f in finished + targets:
        day = _utc_day(f.kickoff_at)
        if day is None:
            continue
        is_target = int(f.id) in target_ids and f.status not in FINISHED_STATUSES
        home_stat = stats.get((int(f.id), str(f.home_team_id)))
        away_stat = stats.get((int(f.id), str(f.away_team_id)))
        ht_home, ht_away = _ht(f) if not is_target else (None, None)
        rec = MatchRecord(
            lab_match_id=int(f.id),
            competition=label,
            group=label,
            season_label=season_of[int(f.competition_id)],
            match_date=day,
            kickoff_at=f.kickoff_at,
            day=(day - _EPOCH).days,
            home_team=str(f.home_team_id),
            away_team=str(f.away_team_id),
            ft_home=0 if is_target else int(f.goals_home),
            ft_away=0 if is_target else int(f.goals_away),
            ht_home=ht_home,
            ht_away=ht_away,
            home_shots=None if is_target else _stat_value(home_stat, "shots"),
            away_shots=None if is_target else _stat_value(away_stat, "shots"),
            home_sot=None if is_target else _stat_value(home_stat, "sot"),
            away_sot=None if is_target else _stat_value(away_stat, "sot"),
            home_fouls=None if is_target else _stat_value(home_stat, "fouls"),
            away_fouls=None if is_target else _stat_value(away_stat, "fouls"),
            home_yellow=None if is_target else _stat_value(home_stat, "yellow"),
            away_yellow=None if is_target else _stat_value(away_stat, "yellow"),
            home_red=None if is_target else _stat_value(home_stat, "red"),
            away_red=None if is_target else _stat_value(away_stat, "red"),
            referee=(f.referee or "").strip() or None,
        )
        if (
            not is_target
            and rec.season_label == current_season
            and None not in (rec.home_shots, rec.away_shots, rec.home_sot, rec.away_sot)
        ):
            stats_current += 1
            team_stats[rec.home_team] += 1
            team_stats[rec.away_team] += 1
        records.append(rec)

    # le partite da prevedere dopo tutte quelle giocate dello stesso giorno
    records.sort(key=lambda m: (m.day, int(m.lab_match_id) in target_ids, m.kickoff_at or datetime.min, m.lab_match_id))
    _annotate_context(records, fixtures, season_of)
    finished_current = sum(1 for f in finished if season_of[int(f.competition_id)] == current_season)
    return _Built(
        records=records,
        targets={int(f.id) for f in targets},
        current_season=current_season,
        stats_current=stats_current,
        finished_current=finished_current,
        finished_previous=len(finished) - finished_current,
        team_stats=dict(team_stats),
    )


def _expected_matches_per_team(calendar: dict[tuple[str, str], list[Any]], season: str, seasons: list[str]) -> int:
    """Partite a squadra nella stagione: il database ha solo le prossime partite gia' scaricate,
    quindi la lunghezza viene dalla stagione precedente dello stesso campionato (conclusa) o, se
    manca, dal girone di andata e ritorno."""
    idx = seasons.index(season)
    if idx > 0:
        previous = [len(v) for (s, _), v in calendar.items() if s == seasons[idx - 1]]
        if previous:
            previous.sort()
            return previous[len(previous) // 2]
    teams = sum(1 for (s, _) in calendar if s == season)
    return max(2 * (teams - 1), 1)


def _annotate_context(records: list[MatchRecord], fixtures: list[Fixture], season_of: dict[int, str]) -> None:
    """Giocate prima (partite finite) e rimanenti (questa inclusa) sulla lunghezza attesa della stagione."""
    calendar: dict[tuple[str, str], list[tuple[datetime, int, bool]]] = defaultdict(list)
    for f in fixtures:
        if f.status in _EXCLUDED_CALENDAR_STATUSES or f.kickoff_at is None:
            continue
        season = season_of[int(f.competition_id)]
        done = f.status in FINISHED_STATUSES
        for team in (str(f.home_team_id), str(f.away_team_id)):
            calendar[(season, team)].append((f.kickoff_at, int(f.id), done))
    seasons = sorted(set(season_of.values()))
    expected = {s: _expected_matches_per_team(calendar, s, seasons) for s in seasons}
    position: dict[tuple[str, str], dict[int, tuple[int, int]]] = {}
    for key, items in calendar.items():
        items.sort()
        played = 0
        total = max(len(items), expected[key[0]])
        per: dict[int, tuple[int, int]] = {}
        for idx, (_, fid, done) in enumerate(items):
            per[fid] = (played, max(total - idx, 1))
            if done:
                played += 1
        position[key] = per
    for m in records:
        hp, hr = position.get((m.season_label, m.home_team), {}).get(m.lab_match_id, (0, 1))
        ap, ar = position.get((m.season_label, m.away_team), {}).get(m.lab_match_id, (0, 1))
        m.home_played, m.home_remaining, m.away_played, m.away_remaining = hp, hr, ap, ar
        m.eval_eligible = min(hp, ap) >= MIN_MATCHES_PLAYED
        if not m.eval_eligible:
            m.phase = PHASE_EARLY
        elif min(hr, ar) <= FINAL_PHASE_MATCHES:
            m.phase = PHASE_FINAL
        else:
            m.phase = PHASE_MID


def _round(v: float | None, places: int = 5) -> float | None:
    return round(float(v), places) if v is not None else None


def predict_records(records: list[MatchRecord], params: V3Params) -> dict[int, dict[str, Any]]:
    """Il calcolo V3 vero e proprio su una piramide in ordine cronologico (stesso codice per
    dati live e Lab): gol attesi finali, probabilita', specialisti e indici per ogni partita."""
    forza = run_group(records, params.hyper_forza)
    sot = run_game_group(records, params.hyper_sot, "sot")
    shots = run_game_group(records, params.hyper_shots, "shots")

    def opinions(mid: int, adjust: tuple[dict[str, float], dict[str, float]] | None = None) -> Opinions | None:
        f, s, t = forza.get(mid), sot.get(mid), shots.get(mid)
        if f is None or s is None or t is None:
            return None
        home = {"forza": f.lambda_home, "sot": s.lambda_home, "shots": t.lambda_home}
        away = {"forza": f.lambda_away, "sot": s.lambda_away, "shots": t.lambda_away}
        if adjust is None:
            return Opinions(home=home, away=away)
        return Opinions(home=home, away=away, adjust_home=adjust[0], adjust_away=adjust[1])

    expectations: dict[int, Expectation] = {}
    for m in records:
        ops = opinions(m.lab_match_id)
        if ops is None:
            continue
        gh, ga = combine(ops, params.base_weights)
        t = shots[m.lab_match_id]
        expectations[m.lab_match_id] = Expectation(goals_home=gh, goals_away=ga, shots_home=t.stat_home, shots_away=t.stat_away)
    form = compute_form(records, expectations)
    calendar = compute_calendar(records)
    adjustments = build_adjustments(form, calendar)

    finals: dict[int, dict[str, Any]] = {}
    index_inputs: list[IndexInput] = []
    for m in records:
        mid = m.lab_match_id
        adj = (adjustments.home.get(mid), adjustments.away.get(mid)) if adjustments else None
        if adj is None or adj[0] is None or adj[1] is None:
            continue
        ops = opinions(mid, adj)  # type: ignore[arg-type]
        if ops is None:
            continue
        lam_h, lam_a = combine(ops, params.weights)
        f = forza[mid]
        probs = market_probabilities(lam_h, lam_a, f.rho, f.ht_share)
        s, t = sot[mid], shots[mid]
        fm, cal = form.get(mid), calendar.get(mid)
        specialists = {
            "forza": {"home": _round(f.lambda_home), "away": _round(f.lambda_away)},
            "sot": {"home": _round(s.lambda_home), "away": _round(s.lambda_away), "volume_home": _round(s.stat_home, 3), "volume_away": _round(s.stat_away, 3)},
            "shots": {"home": _round(t.lambda_home), "away": _round(t.lambda_away), "volume_home": _round(t.stat_home, 3), "volume_away": _round(t.stat_away, 3)},
            "weights": params.weights,
        }
        if fm is not None:
            specialists["form"] = {
                "goals_home": _round(fm.goals_home), "goals_away": _round(fm.goals_away),
                "shots_home": _round(fm.shots_home), "shots_away": _round(fm.shots_away),
                "matches_home": fm.matches_home, "matches_away": fm.matches_away, **fm.detail,
            }
        if cal is not None:
            specialists["calendar"] = {
                "rest_days_home": cal.rest_days_home, "rest_days_away": cal.rest_days_away, "final_phase": cal.final_phase,
            }
        finals[mid] = {
            "lambda_home": lam_h, "lambda_away": lam_a, "rho": f.rho, "ht_share": f.ht_share,
            "home_evidence": f.home_evidence, "away_evidence": f.away_evidence,
            "probabilities": probs, "specialists": specialists, "match": m,
        }
        index_inputs.append(
            IndexInput(
                match=m, prob_home=probs["HOME"], prob_draw=probs["DRAW"], prob_away=probs["AWAY"],
                prob_over_2_5=probs["OVER_2_5"], lambda_home=lam_h, lambda_away=lam_a,
                home_evidence=f.home_evidence, away_evidence=f.away_evidence, specialists=specialists, rho=f.rho,
            )
        )
    indices = compute_indices(index_inputs, reliability={i.match.lab_match_id: None for i in index_inputs})
    for mid, fin in finals.items():
        fin["indices"] = indices.get(mid) or {}
    return finals


def compute_competition(db: Session, comp: Competition, target_ids: set[int], params: V3Params | None = None) -> dict[int, dict[str, Any]]:
    """Previsioni V3 estesa per le partite indicate di un campionato: {fixture_id: risultato}."""
    params = params or load_params(db)
    t0 = time.monotonic()
    built = build_records(db, comp, target_ids)
    base_info = {
        "matches_current_season": built.finished_current,
        "matches_previous_season": built.finished_previous,
        "matches_with_statistics": built.stats_current,
    }
    share = built.stats_current / built.finished_current if built.finished_current else 0.0
    if built.stats_current < MIN_MATCHES_WITH_STATS:
        return {
            fid: {"status": STATUS_NO_STATS, "history": {**base_info, "statistics_share": round(share, 3)}}
            for fid in target_ids
        }
    if not built.targets:
        return {fid: {"status": STATUS_NOT_UPCOMING} for fid in target_ids}

    finals = predict_records(built.records, params)
    elapsed = round(time.monotonic() - t0, 2)

    out: dict[int, dict[str, Any]] = {}
    for fid in target_ids:
        fin = finals.get(fid)
        if fin is None:
            out[fid] = {"status": STATUS_NOT_UPCOMING if fid not in built.targets else "not_computable", "history": base_info}
            continue
        m: MatchRecord = fin.pop("match")
        stats_home = built.team_stats.get(m.home_team, 0)
        stats_away = built.team_stats.get(m.away_team, 0)
        if min(stats_home, stats_away) < MIN_TEAM_MATCHES_WITH_STATS:
            out[fid] = {
                "status": STATUS_NO_STATS,
                "history": {**base_info, "statistics_share": round(share, 3), "team_matches_with_statistics": [stats_home, stats_away]},
            }
            continue
        idx = fin.get("indices") or {}
        idx.pop("affidabilita", None)
        idx.pop("disciplina", None)
        out[fid] = {
            "status": STATUS_OK,
            "engine_version": ENGINE_VERSION,
            "eligible": bool(m.eval_eligible),
            "played_home": m.home_played,
            "played_away": m.away_played,
            "phase": m.phase,
            "lambda_home": _round(fin["lambda_home"], 4),
            "lambda_away": _round(fin["lambda_away"], 4),
            "rho": _round(fin["rho"], 4),
            "ht_share": _round(fin["ht_share"], 4),
            "home_evidence": _round(fin["home_evidence"], 2),
            "away_evidence": _round(fin["away_evidence"], 2),
            "probabilities": {k: round(float(v), 6) for k, v in fin["probabilities"].items()},
            "specialists": fin["specialists"],
            "indices": idx,
            "history": {
                **base_info,
                "statistics_share": round(share, 3),
                "team_matches_with_statistics": [stats_home, stats_away],
                "elapsed_seconds": elapsed,
            },
            "params": params.as_dict(),
        }
    return out


def compute_for_fixtures(db: Session, fixtures: list[Fixture]) -> dict[int, dict[str, Any]]:
    """Raggruppa per campionato e calcola; un campionato che fallisce non blocca gli altri."""
    params = load_params(db)
    by_comp: dict[int, set[int]] = defaultdict(set)
    out: dict[int, dict[str, Any]] = {}
    for f in fixtures:
        if f.competition_id is None:
            out[int(f.id)] = {"status": STATUS_NO_COMPETITION}
            continue
        by_comp[int(f.competition_id)].add(int(f.id))
    for comp_id, ids in by_comp.items():
        comp = db.get(Competition, comp_id)
        if comp is None:
            out.update({fid: {"status": STATUS_NO_COMPETITION} for fid in ids})
            continue
        try:
            out.update(compute_competition(db, comp, ids, params))
        except Exception as exc:  # noqa: BLE001
            logger.exception("V3 estesa fallita competition=%s", comp_id)
            out.update({fid: {"status": "error", "error": str(exc)[:300]} for fid in ids})
    return out
