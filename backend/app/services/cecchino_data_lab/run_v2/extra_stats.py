"""BLOCCO 2 — feature pre-match su statistiche extra (RUN V2).

Rolling incrementali su shots, SOT, corners, fouls, cartellini e storico
arbitro, costruiti esclusivamente da partite precedenti.

Vincoli:
- nessun valore della partita target entra nelle sue feature;
- gli aggiornamenti sono differiti a dopo il commit del gruppo kickoff, cosi
  due partite con lo stesso kickoff non si contaminano a vicenda;
- tutto e missing-safe: una statistica assente riduce il sample, non produce
  errori e non blocca la prediction;
- nulla di questo modulo entra nei moduli CORE.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from app.services.cecchino_data_lab.run_v2.constants import (
    EXTRA_STAT_FAMILIES,
    EXTRA_STAT_NAMES,
    EXTRA_STATS_RECENT_WINDOWS,
    RUN_V2_EXTRA_STATS_VERSION,
)

_MAX_RECENT = max(EXTRA_STATS_RECENT_WINDOWS)


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    if f != f:
        return None
    return f


def _mean(values: list[float]) -> float | None:
    if not values:
        return None
    return round(sum(values) / len(values), 4)


def _round(value: float | None) -> float | None:
    return None if value is None else round(value, 4)


@dataclass
class _Accumulator:
    """Somma e conteggio separati per for/against, robusti ai valori mancanti."""

    for_sum: float = 0.0
    for_n: int = 0
    against_sum: float = 0.0
    against_n: int = 0

    def add(self, value_for: float | None, value_against: float | None) -> None:
        if value_for is not None:
            self.for_sum += value_for
            self.for_n += 1
        if value_against is not None:
            self.against_sum += value_against
            self.against_n += 1

    @property
    def avg_for(self) -> float | None:
        return round(self.for_sum / self.for_n, 4) if self.for_n else None

    @property
    def avg_against(self) -> float | None:
        return round(self.against_sum / self.against_n, 4) if self.against_n else None


@dataclass
class _TeamSeasonState:
    """Stato per (squadra, stagione): totali, split casa/trasferta, recenti."""

    matches: int = 0
    totals: dict[str, _Accumulator] = field(default_factory=dict)
    home: dict[str, _Accumulator] = field(default_factory=dict)
    away: dict[str, _Accumulator] = field(default_factory=dict)
    recent: deque = field(default_factory=lambda: deque(maxlen=_MAX_RECENT))

    def _acc(self, bucket: dict[str, _Accumulator], family: str) -> _Accumulator:
        acc = bucket.get(family)
        if acc is None:
            acc = _Accumulator()
            bucket[family] = acc
        return acc

    def ingest(self, *, is_home: bool, values: dict[str, tuple[float | None, float | None]]) -> None:
        self.matches += 1
        side = self.home if is_home else self.away
        for family, (v_for, v_against) in values.items():
            self._acc(self.totals, family).add(v_for, v_against)
            self._acc(side, family).add(v_for, v_against)
        self.recent.append(values)

    def recent_avg(self, family: str, window: int, *, side: str) -> float | None:
        idx = 0 if side == "for" else 1
        vals: list[float] = []
        for entry in list(self.recent)[-window:]:
            pair = entry.get(family)
            if not pair:
                continue
            v = pair[idx]
            if v is not None:
                vals.append(v)
        return _mean(vals)

    def recent_sample(self, family: str, window: int) -> int:
        n = 0
        for entry in list(self.recent)[-window:]:
            pair = entry.get(family)
            if pair and pair[0] is not None:
                n += 1
        return n


@dataclass
class _CompetitionSeasonState:
    """Media di competizione/stagione, usata per il delta di squadra."""

    team_matches: int = 0
    totals: dict[str, _Accumulator] = field(default_factory=dict)

    def ingest(self, values: dict[str, tuple[float | None, float | None]]) -> None:
        self.team_matches += 1
        for family, (v_for, v_against) in values.items():
            acc = self.totals.get(family)
            if acc is None:
                acc = _Accumulator()
                self.totals[family] = acc
            acc.add(v_for, v_against)

    def avg_for(self, family: str) -> float | None:
        acc = self.totals.get(family)
        return acc.avg_for if acc else None


@dataclass
class _RefereeState:
    """Storico arbitro: solo partite gia disputate, sempre opzionale."""

    matches: int = 0
    yellow_sum: float = 0.0
    yellow_n: int = 0
    red_sum: float = 0.0
    red_n: int = 0
    fouls_sum: float = 0.0
    fouls_n: int = 0

    def ingest(
        self,
        *,
        yellow_total: float | None,
        red_total: float | None,
        fouls_total: float | None,
    ) -> None:
        self.matches += 1
        if yellow_total is not None:
            self.yellow_sum += yellow_total
            self.yellow_n += 1
        if red_total is not None:
            self.red_sum += red_total
            self.red_n += 1
        if fouls_total is not None:
            self.fouls_sum += fouls_total
            self.fouls_n += 1


def match_stat_values(match: Any) -> dict[str, dict[str, tuple[float | None, float | None]]]:
    """Valori (for, against) per squadra di casa e trasferta.

    Usato sia per l'ingest storico sia per costruire le label post-match: qui
    non c'e alcuna lettura anticipata, e il chiamante che decide quando usarlo.
    """
    home_values: dict[str, tuple[float | None, float | None]] = {}
    away_values: dict[str, tuple[float | None, float | None]] = {}
    for family, home_col, away_col in EXTRA_STAT_FAMILIES:
        h = _to_float(getattr(match, home_col, None))
        a = _to_float(getattr(match, away_col, None))
        home_values[family] = (h, a)
        away_values[family] = (a, h)
    return {"home": home_values, "away": away_values}


class ExtraStatsRegistry:
    """Registro rolling BLOCCO 2, alimentato solo da partite gia concluse."""

    version = RUN_V2_EXTRA_STATS_VERSION

    def __init__(self) -> None:
        self._teams: dict[tuple[str, str, str], _TeamSeasonState] = {}
        self._competitions: dict[tuple[str, str], _CompetitionSeasonState] = {}
        self._referees: dict[str, _RefereeState] = {}
        self._ingested_match_ids: set[int] = set()

    # --- ingest ---------------------------------------------------------

    def ingest_match(
        self,
        match: Any,
        *,
        competition: str,
        season_label: str,
    ) -> None:
        """Registra una partita conclusa nello storico rolling."""
        match_id = int(getattr(match, "id", 0) or 0)
        if match_id and match_id in self._ingested_match_ids:
            return
        if match_id:
            self._ingested_match_ids.add(match_id)

        values = match_stat_values(match)
        home_team = (getattr(match, "home_team", None) or "").strip()
        away_team = (getattr(match, "away_team", None) or "").strip()

        if home_team:
            self._team_state(competition, season_label, home_team).ingest(
                is_home=True, values=values["home"]
            )
        if away_team:
            self._team_state(competition, season_label, away_team).ingest(
                is_home=False, values=values["away"]
            )

        comp_state = self._competition_state(competition, season_label)
        comp_state.ingest(values["home"])
        comp_state.ingest(values["away"])

        referee = (getattr(match, "referee", None) or "").strip()
        if referee:
            yellow = _sum_optional(
                _to_float(getattr(match, "home_yellow_cards", None)),
                _to_float(getattr(match, "away_yellow_cards", None)),
            )
            red = _sum_optional(
                _to_float(getattr(match, "home_red_cards", None)),
                _to_float(getattr(match, "away_red_cards", None)),
            )
            fouls = _sum_optional(
                _to_float(getattr(match, "home_fouls", None)),
                _to_float(getattr(match, "away_fouls", None)),
            )
            self._referee_state(referee).ingest(
                yellow_total=yellow, red_total=red, fouls_total=fouls
            )

    def _team_state(self, competition: str, season: str, team: str) -> _TeamSeasonState:
        key = (competition, season, team)
        state = self._teams.get(key)
        if state is None:
            state = _TeamSeasonState()
            self._teams[key] = state
        return state

    def _competition_state(self, competition: str, season: str) -> _CompetitionSeasonState:
        key = (competition, season)
        state = self._competitions.get(key)
        if state is None:
            state = _CompetitionSeasonState()
            self._competitions[key] = state
        return state

    def _referee_state(self, referee: str) -> _RefereeState:
        state = self._referees.get(referee)
        if state is None:
            state = _RefereeState()
            self._referees[referee] = state
        return state

    # --- lettura feature pre-match ---------------------------------------

    def build_prematch_features(
        self,
        *,
        competition: str,
        season_label: str,
        home_team: str | None,
        away_team: str | None,
        referee: str | None,
        target_kickoff: datetime | None = None,
    ) -> dict[str, Any]:
        """Feature BLOCCO 2 per la partita target, dal solo storico gia ingerito."""
        features: dict[str, Any] = {
            "version": self.version,
            "competition": competition,
            "season_label": season_label,
            "target_kickoff": target_kickoff.isoformat() if target_kickoff else None,
            "teams": {},
            "referee": self._referee_features(referee),
            "availability": {},
            "warnings": [],
        }

        comp_state = self._competitions.get((competition, season_label))

        for side, team in (("home", home_team), ("away", away_team)):
            team_name = (team or "").strip()
            state = (
                self._teams.get((competition, season_label, team_name))
                if team_name
                else None
            )
            features["teams"][side] = self._team_features(
                state, comp_state, side=side, team=team_name
            )

        total_sample = sum(
            int(features["teams"][s].get("sample_count") or 0) for s in ("home", "away")
        )
        features["availability"] = {
            "home_sample_count": features["teams"]["home"].get("sample_count"),
            "away_sample_count": features["teams"]["away"].get("sample_count"),
            "referee_sample_count": features["referee"].get("previous_matches"),
            "status": "available" if total_sample > 0 else "no_history",
        }
        if total_sample == 0:
            features["warnings"].append("extra_stats_no_prior_history")
        if not (referee or "").strip():
            features["warnings"].append("referee_missing")

        return features

    def _team_features(
        self,
        state: _TeamSeasonState | None,
        comp_state: _CompetitionSeasonState | None,
        *,
        side: str,
        team: str,
    ) -> dict[str, Any]:
        out: dict[str, Any] = {
            "team": team or None,
            "sample_count": state.matches if state else 0,
            "stats": {},
        }
        side_bucket = "home" if side == "home" else "away"

        for family in EXTRA_STAT_NAMES:
            entry: dict[str, Any] = {
                "season_avg_for": None,
                "season_avg_against": None,
                "season_sample": 0,
                "home_away_split_avg_for": None,
                "home_away_split_avg_against": None,
                "home_away_split_sample": 0,
                "competition_avg_for": None,
                "competition_delta_for": None,
                "trend_recent5_vs_season": None,
            }
            for window in EXTRA_STATS_RECENT_WINDOWS:
                entry[f"recent{window}_avg_for"] = None
                entry[f"recent{window}_avg_against"] = None
                entry[f"recent{window}_sample"] = 0

            if state is not None:
                totals = state.totals.get(family)
                if totals is not None:
                    entry["season_avg_for"] = totals.avg_for
                    entry["season_avg_against"] = totals.avg_against
                    entry["season_sample"] = totals.for_n

                split = (state.home if side_bucket == "home" else state.away).get(family)
                if split is not None:
                    entry["home_away_split_avg_for"] = split.avg_for
                    entry["home_away_split_avg_against"] = split.avg_against
                    entry["home_away_split_sample"] = split.for_n

                for window in EXTRA_STATS_RECENT_WINDOWS:
                    entry[f"recent{window}_avg_for"] = state.recent_avg(
                        family, window, side="for"
                    )
                    entry[f"recent{window}_avg_against"] = state.recent_avg(
                        family, window, side="against"
                    )
                    entry[f"recent{window}_sample"] = state.recent_sample(family, window)

                r5 = entry.get("recent5_avg_for")
                season_avg = entry.get("season_avg_for")
                if r5 is not None and season_avg is not None:
                    entry["trend_recent5_vs_season"] = _round(r5 - season_avg)

            if comp_state is not None:
                comp_avg = comp_state.avg_for(family)
                entry["competition_avg_for"] = comp_avg
                season_avg = entry.get("season_avg_for")
                if comp_avg is not None and season_avg is not None:
                    entry["competition_delta_for"] = _round(season_avg - comp_avg)

            out["stats"][family] = entry

        return out

    def _referee_features(self, referee: str | None) -> dict[str, Any]:
        name = (referee or "").strip()
        out: dict[str, Any] = {
            "name": name or None,
            "available": False,
            "previous_matches": 0,
            "previous_yellow_cards_avg": None,
            "previous_red_cards_avg": None,
            "previous_cards_avg": None,
            "previous_fouls_avg": None,
        }
        if not name:
            return out

        state = self._referees.get(name)
        if state is None or state.matches == 0:
            return out

        out["available"] = True
        out["previous_matches"] = state.matches
        if state.yellow_n:
            out["previous_yellow_cards_avg"] = round(state.yellow_sum / state.yellow_n, 4)
        if state.red_n:
            out["previous_red_cards_avg"] = round(state.red_sum / state.red_n, 4)
        if state.fouls_n:
            out["previous_fouls_avg"] = round(state.fouls_sum / state.fouls_n, 4)
        if state.yellow_n and state.red_n:
            out["previous_cards_avg"] = round(
                state.yellow_sum / state.yellow_n + state.red_sum / state.red_n, 4
            )
        elif state.yellow_n:
            out["previous_cards_avg"] = round(state.yellow_sum / state.yellow_n, 4)

        return out


def _sum_optional(a: float | None, b: float | None) -> float | None:
    if a is None and b is None:
        return None
    return (a or 0.0) + (b or 0.0)


def build_actual_stats(match: Any) -> dict[str, Any]:
    """Label post-match. Da usare solo dopo il freeze della prediction."""
    actuals: dict[str, Any] = {}

    for family, home_col, away_col in EXTRA_STAT_FAMILIES:
        h = _to_float(getattr(match, home_col, None))
        a = _to_float(getattr(match, away_col, None))
        actuals[f"home_{family}"] = h
        actuals[f"away_{family}"] = a
        actuals[f"total_{family}"] = _sum_optional(h, a) if (h is not None or a is not None) else None

    ft_home = getattr(match, "ft_home_goals", None)
    ft_away = getattr(match, "ft_away_goals", None)
    ht_home = getattr(match, "ht_home_goals", None)
    ht_away = getattr(match, "ht_away_goals", None)

    actuals["ft_home_goals"] = ft_home
    actuals["ft_away_goals"] = ft_away
    actuals["ft_total_goals"] = (
        int(ft_home) + int(ft_away) if ft_home is not None and ft_away is not None else None
    )
    actuals["ft_result"] = getattr(match, "ft_result", None)
    actuals["ht_home_goals"] = ht_home
    actuals["ht_away_goals"] = ht_away
    actuals["ht_total_goals"] = (
        int(ht_home) + int(ht_away) if ht_home is not None and ht_away is not None else None
    )
    actuals["ht_result"] = getattr(match, "ht_result", None)
    actuals["referee"] = getattr(match, "referee", None)

    return actuals
