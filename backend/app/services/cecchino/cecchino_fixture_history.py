"""Recupero fixture finite PIT per Cecchino — anti-leakage, competition-scoped."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.constants import FINISHED_STATUSES, LIVE_STATUSES, SCHEDULED_STATUSES
from app.models import Fixture
from app.services.cecchino.cecchino_constants import (
    CONTEXT_SLICE_LABELS,
    KEY_AWAY_CONTEXT,
    KEY_AWAY_RECENT_CONTEXT_5,
    KEY_AWAY_RECENT_TOTAL_6,
    KEY_AWAY_TOTAL,
    KEY_HOME_CONTEXT,
    KEY_HOME_RECENT_CONTEXT_5,
    KEY_HOME_RECENT_TOTAL_6,
    KEY_HOME_TOTAL,
    LEAKAGE_FAILED,
    LEAKAGE_PASSED,
    LEAKAGE_UNDEFINED,
    STATUS_AVAILABLE,
    STATUS_INSUFFICIENT_DATA,
    STATUS_PARTIAL_LOW_SAMPLE,
    TARGET_RECENT_CONTEXT,
    TARGET_RECENT_TOTAL,
    WARNING_LOW_SAMPLE,
)
from app.services.cecchino.cecchino_engine import CecchinoCalculationInput, WDLRecord
from app.services.cecchino.cecchino_datetime import (
    fixture_key_before_safe,
    safe_isoformat,
    utc_now,
    ensure_datetime_utc,
)
from app.services.predictions_v10.v10_prior_context import (
    _prior_fixtures_for_team,
    _resolve_fixture_season_id,
)
from app.services.predictions_v11.split_fixtures import team_split_fixtures
from app.services.predictions_v11.v11_shared import last_n

logger = logging.getLogger(__name__)


def _slice_status(sample_count: int, target_sample: int | None) -> str:
    if sample_count <= 0:
        return STATUS_INSUFFICIENT_DATA
    if target_sample is not None and sample_count < target_sample:
        return STATUS_PARTIAL_LOW_SAMPLE
    return STATUS_AVAILABLE


@dataclass
class WDLContextSlice:
    """Singolo contesto W/D/L con metadati campione."""

    key: str
    wdl: WDLRecord
    sample_count: int
    target_sample: int | None
    fixture_ids: list[int] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "label": CONTEXT_SLICE_LABELS.get(self.key, self.key),
            "wdl": self.wdl.to_dict(),
            "sample_count": self.sample_count,
            "target_sample": self.target_sample,
            "status": _slice_status(self.sample_count, self.target_sample),
            "fixture_ids": list(self.fixture_ids),
        }


@dataclass
class CecchinoFixtureContexts:
    """8 contesti + liste fixture sorgente per audit."""

    home_context: WDLContextSlice
    away_context: WDLContextSlice
    home_total: WDLContextSlice
    away_total: WDLContextSlice
    home_recent_context_5: WDLContextSlice
    away_recent_context_5: WDLContextSlice
    home_recent_total_6: WDLContextSlice
    away_recent_total_6: WDLContextSlice
    all_fixture_ids: list[int] = field(default_factory=list)

    def slices_by_key(self) -> dict[str, WDLContextSlice]:
        return {
            KEY_HOME_CONTEXT: self.home_context,
            KEY_AWAY_CONTEXT: self.away_context,
            KEY_HOME_TOTAL: self.home_total,
            KEY_AWAY_TOTAL: self.away_total,
            KEY_HOME_RECENT_CONTEXT_5: self.home_recent_context_5,
            KEY_AWAY_RECENT_CONTEXT_5: self.away_recent_context_5,
            KEY_HOME_RECENT_TOTAL_6: self.home_recent_total_6,
            KEY_AWAY_RECENT_TOTAL_6: self.away_recent_total_6,
        }

    def to_input_snapshot(self) -> dict[str, Any]:
        return {k: v.to_dict() for k, v in self.slices_by_key().items()}


def wdl_from_fixtures(fixtures: list[Fixture], team_id: int) -> WDLRecord:
    """Aggrega V/X/S da partite finite con gol disponibili."""
    wins = draws = losses = 0
    tid = int(team_id)
    for f in fixtures:
        if int(f.home_team_id) == tid:
            gf, ga = f.goals_home, f.goals_away
        elif int(f.away_team_id) == tid:
            gf, ga = f.goals_away, f.goals_home
        else:
            continue
        if gf is None or ga is None:
            continue
        if int(gf) > int(ga):
            wins += 1
        elif int(gf) < int(ga):
            losses += 1
        else:
            draws += 1
    return WDLRecord(wins=wins, draws=draws, losses=losses)


def load_finished_fixtures_for_team(
    db: Session,
    target_fixture: Fixture,
    team_id: int,
) -> list[Fixture]:
    """Partite finite della squadra prima del kickoff target, scoped per competition."""
    season_id = _resolve_fixture_season_id(db, target_fixture)
    comp_id = int(target_fixture.competition_id) if target_fixture.competition_id is not None else None
    cutoff_ko = ensure_datetime_utc(target_fixture.kickoff_at, field_name="target.kickoff_at")
    if cutoff_ko is None and target_fixture.kickoff_at is not None:
        logger.warning(
            "load_finished_fixtures_for_team target_kickoff_invalid fixture_id=%s",
            target_fixture.id,
        )
        return []
    return _prior_fixtures_for_team(
        db,
        season_id=season_id,
        cutoff_kickoff=cutoff_ko,
        cutoff_fixture_id=int(target_fixture.id),
        team_id=int(team_id),
        competition_id=comp_id,
        competition_scoped_only=comp_id is not None,
    )


def split_home_away(
    fixtures: list[Fixture],
    team_id: int,
    *,
    is_home: bool,
) -> list[Fixture]:
    return team_split_fixtures(fixtures, int(team_id), is_home_context=is_home)


def take_last_n(fixtures: list[Fixture], n: int) -> list[Fixture]:
    return last_n(fixtures, n)


def _fixture_ids(fixtures: list[Fixture]) -> list[int]:
    return [int(f.id) for f in fixtures]


def audit_leakage(
    fixtures: list[Fixture],
    target: Fixture,
) -> tuple[dict[str, Any], list[str]]:
    """Verifica PIT/competition scope; restituisce oggetto leakage_check + motivi."""
    reasons: list[str] = []
    target_comp = int(target.competition_id or 0)
    cutoff_ko = ensure_datetime_utc(target.kickoff_at, field_name="target.kickoff_at")
    cutoff_id = int(target.id)
    target_kickoff = safe_isoformat(cutoff_ko, field_name="target.kickoff_at")
    checked_at = utc_now().isoformat()

    if target.kickoff_at is None:
        return (
            {
                "status": LEAKAGE_UNDEFINED,
                "target_kickoff": None,
                "max_source_fixture_date": None,
                "checked_at": checked_at,
            },
            ["target:missing_kickoff"],
        )

    if cutoff_ko is None:
        return (
            {
                "status": LEAKAGE_UNDEFINED,
                "target_kickoff": None,
                "max_source_fixture_date": None,
                "checked_at": checked_at,
            },
            ["target:target_kickoff_invalid"],
        )

    max_ko: datetime | None = None
    for f in fixtures:
        fid = int(f.id)
        st = (f.status or "").strip().upper()
        if st not in FINISHED_STATUSES:
            reasons.append(f"fixture_{fid}:status_not_finished:{st}")
        if int(f.competition_id or 0) != target_comp:
            reasons.append(f"fixture_{fid}:competition_mismatch")
        if f.kickoff_at is None:
            reasons.append(f"fixture_{fid}:missing_kickoff")
            continue
        prior_ko = ensure_datetime_utc(f.kickoff_at, field_name=f"prior_fixture_{fid}.kickoff_at")
        if prior_ko is None:
            reasons.append(f"prior_fixture_kickoff_invalid:{fid}")
            logger.warning("audit_leakage skip prior fixture_id=%s invalid kickoff", fid)
            continue
        prior_before = fixture_key_before_safe(
            prior_ko,
            fid,
            cutoff_ko,
            cutoff_id,
            field_name_a=f"prior_fixture_{fid}.kickoff_at",
            field_name_b="target.kickoff_at",
        )
        if prior_before is None:
            reasons.append(f"prior_fixture_kickoff_invalid:{fid}")
            continue
        if not prior_before:
            reasons.append(f"fixture_{fid}:kickoff_not_before_target")
        if st in LIVE_STATUSES or st in SCHEDULED_STATUSES:
            reasons.append(f"fixture_{fid}:live_or_scheduled:{st}")
        if max_ko is None or prior_ko > max_ko:
            max_ko = prior_ko

    max_source = max_ko.isoformat() if max_ko is not None else None

    if reasons:
        return (
            {
                "status": LEAKAGE_FAILED,
                "target_kickoff": target_kickoff,
                "max_source_fixture_date": max_source,
                "checked_at": checked_at,
            },
            reasons,
        )

    if not fixtures:
        return (
            {
                "status": LEAKAGE_UNDEFINED,
                "target_kickoff": target_kickoff,
                "max_source_fixture_date": None,
                "checked_at": checked_at,
            },
            [],
        )

    return (
        {
            "status": LEAKAGE_PASSED,
            "target_kickoff": target_kickoff,
            "max_source_fixture_date": max_source,
            "checked_at": checked_at,
        },
        [],
    )


def _slice(
    key: str,
    fixtures: list[Fixture],
    team_id: int,
    *,
    target_sample: int | None,
) -> WDLContextSlice:
    return WDLContextSlice(
        key=key,
        wdl=wdl_from_fixtures(fixtures, team_id),
        sample_count=len(fixtures),
        target_sample=target_sample,
        fixture_ids=_fixture_ids(fixtures),
    )


def build_fixture_contexts(
    db: Session,
    target_fixture: Fixture,
) -> CecchinoFixtureContexts:
    """Costruisce gli 8 contesti W/D/L da fixture DB."""
    hid = int(target_fixture.home_team_id)
    aid = int(target_fixture.away_team_id)

    home_prior = load_finished_fixtures_for_team(db, target_fixture, hid)
    away_prior = load_finished_fixtures_for_team(db, target_fixture, aid)

    home_split = split_home_away(home_prior, hid, is_home=True)
    away_split = split_home_away(away_prior, aid, is_home=False)

    home_last5 = take_last_n(home_split, TARGET_RECENT_CONTEXT)
    away_last5 = take_last_n(away_split, TARGET_RECENT_CONTEXT)
    home_last6 = take_last_n(home_prior, TARGET_RECENT_TOTAL)
    away_last6 = take_last_n(away_prior, TARGET_RECENT_TOTAL)

    all_ids = sorted(
        {
            *_fixture_ids(home_prior),
            *_fixture_ids(away_prior),
        },
    )

    return CecchinoFixtureContexts(
        home_context=_slice(KEY_HOME_CONTEXT, home_split, hid, target_sample=None),
        away_context=_slice(KEY_AWAY_CONTEXT, away_split, aid, target_sample=None),
        home_total=_slice(KEY_HOME_TOTAL, home_prior, hid, target_sample=None),
        away_total=_slice(KEY_AWAY_TOTAL, away_prior, aid, target_sample=None),
        home_recent_context_5=_slice(
            KEY_HOME_RECENT_CONTEXT_5,
            home_last5,
            hid,
            target_sample=TARGET_RECENT_CONTEXT,
        ),
        away_recent_context_5=_slice(
            KEY_AWAY_RECENT_CONTEXT_5,
            away_last5,
            aid,
            target_sample=TARGET_RECENT_CONTEXT,
        ),
        home_recent_total_6=_slice(
            KEY_HOME_RECENT_TOTAL_6,
            home_last6,
            hid,
            target_sample=TARGET_RECENT_TOTAL,
        ),
        away_recent_total_6=_slice(
            KEY_AWAY_RECENT_TOTAL_6,
            away_last6,
            aid,
            target_sample=TARGET_RECENT_TOTAL,
        ),
        all_fixture_ids=all_ids,
    )


def collect_low_sample_warnings(ctx: CecchinoFixtureContexts) -> list[str]:
    warnings: list[str] = []
    for sl in ctx.slices_by_key().values():
        if sl.target_sample is None:
            continue
        if sl.sample_count < sl.target_sample:
            warnings.append(f"{WARNING_LOW_SAMPLE}:{sl.key}")
    return warnings


def build_data_quality(
    ctx: CecchinoFixtureContexts,
    *,
    leakage_check: dict[str, Any],
    leakage_reasons: list[str],
    extra_warnings: list[str] | None = None,
) -> dict[str, Any]:
    warnings = collect_low_sample_warnings(ctx)
    if extra_warnings:
        for w in extra_warnings:
            if w not in warnings:
                warnings.append(w)
    if leakage_reasons:
        for r in leakage_reasons:
            warnings.append(f"leakage:{r}")

    return {
        "sample_home_context": ctx.home_context.sample_count,
        "sample_away_context": ctx.away_context.sample_count,
        "sample_home_total": ctx.home_total.sample_count,
        "sample_away_total": ctx.away_total.sample_count,
        "sample_home_recent_context": ctx.home_recent_context_5.sample_count,
        "sample_away_recent_context": ctx.away_recent_context_5.sample_count,
        "sample_home_recent_total": ctx.home_recent_total_6.sample_count,
        "sample_away_recent_total": ctx.away_recent_total_6.sample_count,
        "leakage_check": leakage_check,
        "warnings": warnings,
        "fixture_ids_used": {
            k: v.fixture_ids for k, v in ctx.slices_by_key().items()
        },
    }


def contexts_to_calculation_input(ctx: CecchinoFixtureContexts) -> CecchinoCalculationInput:
    return CecchinoCalculationInput(
        home_away=(ctx.home_context.wdl, ctx.away_context.wdl),
        totals=(ctx.home_total.wdl, ctx.away_total.wdl),
        last5_home_away=(ctx.home_recent_context_5.wdl, ctx.away_recent_context_5.wdl),
        last6_totals=(ctx.home_recent_total_6.wdl, ctx.away_recent_total_6.wdl),
    )


TARGET_GOAL_HOME_AWAY = 5
TARGET_GOAL_TOTAL = 10
TARGET_GOAL_HT = 5
MIN_GOAL_HOME_AWAY = 3
MIN_GOAL_TOTAL = 6
MIN_GOAL_HT = 3
MIN_GOAL_LAST6 = 5

CONTEXT_KEY_TOTALS = "totals"
CONTEXT_KEY_HOME_AWAY = "home_away"
CONTEXT_KEY_LAST6_TOTALS = "last6_totals"
CONTEXT_KEY_LAST5_HOME_AWAY = "last5_home_away"

CONTEXT_LABELS: dict[str, str] = {
    CONTEXT_KEY_TOTALS: "Totali stagione",
    CONTEXT_KEY_HOME_AWAY: "Casa/Fuori",
    CONTEXT_KEY_LAST6_TOTALS: "Ultime 6 totali",
    CONTEXT_KEY_LAST5_HOME_AWAY: "Ultime 5 casa/fuori",
}

CONTEXT_TARGETS: dict[str, tuple[int, int]] = {
    CONTEXT_KEY_TOTALS: (10, MIN_GOAL_TOTAL),
    CONTEXT_KEY_HOME_AWAY: (5, MIN_GOAL_HOME_AWAY),
    CONTEXT_KEY_LAST6_TOTALS: (6, MIN_GOAL_LAST6),
    CONTEXT_KEY_LAST5_HOME_AWAY: (5, MIN_GOAL_HOME_AWAY),
}


@dataclass
class GoalTotals:
    """Aggregati goal da lista fixture dal POV di una squadra."""

    sample: int
    goals_for: int
    goals_against: int
    total_goals: int
    over_1_5_hits: int
    over_2_5_hits: int
    under_2_5_hits: int
    under_3_5_hits: int
    over_pt_0_5_hits: int
    over_pt_1_5_hits: int
    under_pt_1_5_hits: int
    fixture_ids: list[int] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "sample": self.sample,
            "goals_for": self.goals_for,
            "goals_against": self.goals_against,
            "total_goals": self.total_goals,
            "over_1_5_hits": self.over_1_5_hits,
            "over_2_5_hits": self.over_2_5_hits,
            "under_2_5_hits": self.under_2_5_hits,
            "under_3_5_hits": self.under_3_5_hits,
            "over_pt_0_5_hits": self.over_pt_0_5_hits,
            "over_pt_1_5_hits": self.over_pt_1_5_hits,
            "under_pt_1_5_hits": self.under_pt_1_5_hits,
            "fixture_ids": list(self.fixture_ids),
        }


@dataclass
class GoalFixtureSlices:
    """Slice storico goal per formule Over/Under Cecchino."""

    home_home_5: GoalTotals
    away_away_5: GoalTotals
    home_total_10: GoalTotals
    away_total_10: GoalTotals
    home_home_ht_5: GoalTotals
    away_away_ht_5: GoalTotals
    skipped_missing_halftime_score: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "home_home_5": self.home_home_5.to_dict(),
            "away_away_5": self.away_away_5.to_dict(),
            "home_total_10": self.home_total_10.to_dict(),
            "away_total_10": self.away_total_10.to_dict(),
            "home_home_ht_5": self.home_home_ht_5.to_dict(),
            "away_away_ht_5": self.away_away_ht_5.to_dict(),
            "skipped_missing_halftime_score": self.skipped_missing_halftime_score,
        }


def team_goals_in_fixture(fixture: Fixture, team_id: int) -> tuple[int | None, int | None]:
    """Restituisce (goals_for, goals_against) dal POV della squadra."""
    tid = int(team_id)
    if fixture.goals_home is None or fixture.goals_away is None:
        return None, None
    gh, ga = int(fixture.goals_home), int(fixture.goals_away)
    if int(fixture.home_team_id) == tid:
        return gh, ga
    if int(fixture.away_team_id) == tid:
        return ga, gh
    return None, None


def halftime_total_goals(fixture: Fixture) -> int | None:
    """Totale gol primo tempo da raw_json.score.halftime; None se assente."""
    raw = fixture.raw_json if isinstance(fixture.raw_json, dict) else {}
    score = raw.get("score") if isinstance(raw.get("score"), dict) else {}
    ht = score.get("halftime") if isinstance(score.get("halftime"), dict) else {}
    h, a = ht.get("home"), ht.get("away")
    if h is None or a is None:
        return None
    try:
        return int(h) + int(a)
    except (TypeError, ValueError):
        return None


def aggregate_goal_totals(fixtures: list[Fixture], team_id: int) -> GoalTotals:
    """Aggrega metriche goal da fixture finite con score FT valido."""
    gf = ga = tg = 0
    o15 = o25 = u25 = u35 = 0
    pt05 = pt15 = upt15 = 0
    ids: list[int] = []
    sample = 0

    for f in fixtures:
        goals_for, goals_against = team_goals_in_fixture(f, team_id)
        if goals_for is None or goals_against is None:
            continue
        sample += 1
        ids.append(int(f.id))
        gf += goals_for
        ga += goals_against
        match_total = goals_for + goals_against
        tg += match_total
        if match_total >= 2:
            o15 += 1
        if match_total >= 3:
            o25 += 1
        if match_total <= 2:
            u25 += 1
        if match_total <= 3:
            u35 += 1

        ht_total = halftime_total_goals(f)
        if ht_total is not None:
            if ht_total >= 1:
                pt05 += 1
            if ht_total >= 2:
                pt15 += 1
            if ht_total <= 1:
                upt15 += 1

    return GoalTotals(
        sample=sample,
        goals_for=gf,
        goals_against=ga,
        total_goals=tg,
        over_1_5_hits=o15,
        over_2_5_hits=o25,
        under_2_5_hits=u25,
        under_3_5_hits=u35,
        over_pt_0_5_hits=pt05,
        over_pt_1_5_hits=pt15,
        under_pt_1_5_hits=upt15,
        fixture_ids=ids,
    )


def _take_last_n_with_halftime(
    fixtures: list[Fixture],
    n: int,
) -> tuple[list[Fixture], int]:
    """Ultime n fixture con HT valido; restituisce anche il conteggio escluse."""
    valid: list[Fixture] = []
    skipped = 0
    for f in reversed(fixtures):
        if halftime_total_goals(f) is None:
            skipped += 1
            continue
        valid.insert(0, f)
        if len(valid) >= n:
            break
    return valid, skipped


@dataclass
class GoalContextSlice:
    """Singolo contesto goal allineato ai picchetti Cecchino."""

    name: str
    label: str
    home_fixtures: list[Fixture]
    away_fixtures: list[Fixture]
    home_totals: GoalTotals
    away_totals: GoalTotals
    target_sample: int
    min_sample: int

    @property
    def sample_home(self) -> int:
        return self.home_totals.sample

    @property
    def sample_away(self) -> int:
        return self.away_totals.sample


@dataclass
class GoalMarketContexts:
    """4 contesti FT + 4 contesti HT per modello Poisson v2."""

    totals: GoalContextSlice
    home_away: GoalContextSlice
    last6_totals: GoalContextSlice
    last5_home_away: GoalContextSlice
    ht_totals: GoalContextSlice
    ht_home_away: GoalContextSlice
    ht_last6_totals: GoalContextSlice
    ht_last5_home_away: GoalContextSlice
    skipped_missing_halftime_score: int = 0
    home_team_id: int = 0
    away_team_id: int = 0

    def ft_slices(self) -> list[GoalContextSlice]:
        return [self.totals, self.home_away, self.last6_totals, self.last5_home_away]

    def ht_slices(self) -> list[GoalContextSlice]:
        return [
            self.ht_totals,
            self.ht_home_away,
            self.ht_last6_totals,
            self.ht_last5_home_away,
        ]


def team_halftime_goals_in_fixture(
    fixture: Fixture,
    team_id: int,
) -> tuple[int | None, int | None]:
    """Restituisce (ht_goals_for, ht_goals_against) dal POV squadra."""
    raw = fixture.raw_json if isinstance(fixture.raw_json, dict) else {}
    score = raw.get("score") if isinstance(raw.get("score"), dict) else {}
    ht = score.get("halftime") if isinstance(score.get("halftime"), dict) else {}
    h, a = ht.get("home"), ht.get("away")
    if h is None or a is None:
        return None, None
    try:
        gh, ga = int(h), int(a)
    except (TypeError, ValueError):
        return None, None
    tid = int(team_id)
    if int(fixture.home_team_id) == tid:
        return gh, ga
    if int(fixture.away_team_id) == tid:
        return ga, gh
    return None, None


def _filter_halftime_fixtures(fixtures: list[Fixture]) -> tuple[list[Fixture], int]:
    valid: list[Fixture] = []
    skipped = 0
    for f in fixtures:
        if halftime_total_goals(f) is None:
            skipped += 1
        else:
            valid.append(f)
    return valid, skipped


def aggregate_halftime_goal_totals(
    fixtures: list[Fixture],
    team_id: int,
) -> GoalTotals:
    """Aggrega goal HT da fixture con score primo tempo valido."""
    gf = ga = tg = 0
    o15 = o25 = u25 = u35 = 0
    pt05 = pt15 = upt15 = 0
    ids: list[int] = []
    sample = 0

    for f in fixtures:
        goals_for, goals_against = team_halftime_goals_in_fixture(f, team_id)
        if goals_for is None or goals_against is None:
            continue
        sample += 1
        ids.append(int(f.id))
        gf += goals_for
        ga += goals_against
        match_total = goals_for + goals_against
        tg += match_total
        if match_total >= 2:
            o15 += 1
        if match_total >= 3:
            o25 += 1
        if match_total <= 2:
            u25 += 1
        if match_total <= 3:
            u35 += 1
        if match_total >= 1:
            pt05 += 1
        if match_total >= 2:
            pt15 += 1
        if match_total <= 1:
            upt15 += 1

    return GoalTotals(
        sample=sample,
        goals_for=gf,
        goals_against=ga,
        total_goals=tg,
        over_1_5_hits=o15,
        over_2_5_hits=o25,
        under_2_5_hits=u25,
        under_3_5_hits=u35,
        over_pt_0_5_hits=pt05,
        over_pt_1_5_hits=pt15,
        under_pt_1_5_hits=upt15,
        fixture_ids=ids,
    )


def _make_context_slice(
    *,
    name: str,
    home_fixtures: list[Fixture],
    away_fixtures: list[Fixture],
    home_team_id: int,
    away_team_id: int,
    use_halftime: bool = False,
) -> GoalContextSlice:
    target, min_s = CONTEXT_TARGETS[name]
    agg = aggregate_halftime_goal_totals if use_halftime else aggregate_goal_totals
    return GoalContextSlice(
        name=name,
        label=CONTEXT_LABELS[name],
        home_fixtures=home_fixtures,
        away_fixtures=away_fixtures,
        home_totals=agg(home_fixtures, home_team_id),
        away_totals=agg(away_fixtures, away_team_id),
        target_sample=target,
        min_sample=min_s,
    )


def load_league_finished_fixtures_before(
    db: Session,
    target_fixture: Fixture,
) -> list[Fixture]:
    """Fixture finite della competizione prima del kickoff target (PIT)."""
    comp_id = int(target_fixture.competition_id or 0)
    if comp_id <= 0:
        return []
    cutoff_ko = ensure_datetime_utc(target_fixture.kickoff_at, field_name="target.kickoff_at")
    cutoff_id = int(target_fixture.id)
    if cutoff_ko is None:
        return []

    rows = db.scalars(
        select(Fixture)
        .where(
            Fixture.competition_id == comp_id,
            Fixture.status.in_(FINISHED_STATUSES),
        )
        .order_by(Fixture.kickoff_at.asc(), Fixture.id.asc()),
    ).all()
    out: list[Fixture] = []
    for f in rows:
        if f.kickoff_at is None or f.goals_home is None or f.goals_away is None:
            continue
        prior_before = fixture_key_before_safe(
            f.kickoff_at,
            int(f.id),
            cutoff_ko,
            cutoff_id,
            field_name_a=f"prior_fixture_{f.id}.kickoff_at",
            field_name_b="target.kickoff_at",
        )
        if prior_before is True:
            out.append(f)
        elif prior_before is None:
            logger.warning(
                "load_league_finished_fixtures_before skip fixture_id=%s invalid kickoff",
                f.id,
            )
    return out


def build_goal_market_contexts(db: Session, target_fixture: Fixture) -> GoalMarketContexts:
    """Costruisce 4 contesti goal allineati ai picchetti + varianti HT."""
    hid = int(target_fixture.home_team_id)
    aid = int(target_fixture.away_team_id)

    home_prior = load_finished_fixtures_for_team(db, target_fixture, hid)
    away_prior = load_finished_fixtures_for_team(db, target_fixture, aid)
    home_split = split_home_away(home_prior, hid, is_home=True)
    away_split = split_home_away(away_prior, aid, is_home=False)

    home_last6 = take_last_n(home_prior, TARGET_RECENT_TOTAL)
    away_last6 = take_last_n(away_prior, TARGET_RECENT_TOTAL)
    home_last5 = take_last_n(home_split, TARGET_RECENT_CONTEXT)
    away_last5 = take_last_n(away_split, TARGET_RECENT_CONTEXT)

    ht_skip = 0
    ht_home_prior, s1 = _filter_halftime_fixtures(home_prior)
    ht_away_prior, s2 = _filter_halftime_fixtures(away_prior)
    ht_home_split, s3 = _filter_halftime_fixtures(home_split)
    ht_away_split, s4 = _filter_halftime_fixtures(away_split)
    ht_home_last6, s5 = _filter_halftime_fixtures(home_last6)
    ht_away_last6, s6 = _filter_halftime_fixtures(away_last6)
    ht_home_last5, s7 = _filter_halftime_fixtures(home_last5)
    ht_away_last5, s8 = _filter_halftime_fixtures(away_last5)
    ht_skip = s1 + s2 + s3 + s4 + s5 + s6 + s7 + s8

    return GoalMarketContexts(
        totals=_make_context_slice(
            name=CONTEXT_KEY_TOTALS,
            home_fixtures=home_prior,
            away_fixtures=away_prior,
            home_team_id=hid,
            away_team_id=aid,
        ),
        home_away=_make_context_slice(
            name=CONTEXT_KEY_HOME_AWAY,
            home_fixtures=home_split,
            away_fixtures=away_split,
            home_team_id=hid,
            away_team_id=aid,
        ),
        last6_totals=_make_context_slice(
            name=CONTEXT_KEY_LAST6_TOTALS,
            home_fixtures=home_last6,
            away_fixtures=away_last6,
            home_team_id=hid,
            away_team_id=aid,
        ),
        last5_home_away=_make_context_slice(
            name=CONTEXT_KEY_LAST5_HOME_AWAY,
            home_fixtures=home_last5,
            away_fixtures=away_last5,
            home_team_id=hid,
            away_team_id=aid,
        ),
        ht_totals=_make_context_slice(
            name=CONTEXT_KEY_TOTALS,
            home_fixtures=ht_home_prior,
            away_fixtures=ht_away_prior,
            home_team_id=hid,
            away_team_id=aid,
            use_halftime=True,
        ),
        ht_home_away=_make_context_slice(
            name=CONTEXT_KEY_HOME_AWAY,
            home_fixtures=ht_home_split,
            away_fixtures=ht_away_split,
            home_team_id=hid,
            away_team_id=aid,
            use_halftime=True,
        ),
        ht_last6_totals=_make_context_slice(
            name=CONTEXT_KEY_LAST6_TOTALS,
            home_fixtures=ht_home_last6,
            away_fixtures=ht_away_last6,
            home_team_id=hid,
            away_team_id=aid,
            use_halftime=True,
        ),
        ht_last5_home_away=_make_context_slice(
            name=CONTEXT_KEY_LAST5_HOME_AWAY,
            home_fixtures=ht_home_last5,
            away_fixtures=ht_away_last5,
            home_team_id=hid,
            away_team_id=aid,
            use_halftime=True,
        ),
        skipped_missing_halftime_score=ht_skip,
        home_team_id=hid,
        away_team_id=aid,
    )


def build_goal_fixture_slices(db: Session, target_fixture: Fixture) -> GoalFixtureSlices:
    """Costruisce slice goal PIT per formule Over/Under."""
    hid = int(target_fixture.home_team_id)
    aid = int(target_fixture.away_team_id)

    home_prior = load_finished_fixtures_for_team(db, target_fixture, hid)
    away_prior = load_finished_fixtures_for_team(db, target_fixture, aid)

    home_split = split_home_away(home_prior, hid, is_home=True)
    away_split = split_home_away(away_prior, aid, is_home=False)

    home_home_5 = take_last_n(home_split, TARGET_GOAL_HOME_AWAY)
    away_away_5 = take_last_n(away_split, TARGET_GOAL_HOME_AWAY)
    home_total_10 = take_last_n(home_prior, TARGET_GOAL_TOTAL)
    away_total_10 = take_last_n(away_prior, TARGET_GOAL_TOTAL)

    home_ht_fx, home_ht_skip = _take_last_n_with_halftime(home_split, TARGET_GOAL_HT)
    away_ht_fx, away_ht_skip = _take_last_n_with_halftime(away_split, TARGET_GOAL_HT)

    return GoalFixtureSlices(
        home_home_5=aggregate_goal_totals(home_home_5, hid),
        away_away_5=aggregate_goal_totals(away_away_5, aid),
        home_total_10=aggregate_goal_totals(home_total_10, hid),
        away_total_10=aggregate_goal_totals(away_total_10, aid),
        home_home_ht_5=aggregate_goal_totals(home_ht_fx, hid),
        away_away_ht_5=aggregate_goal_totals(away_ht_fx, aid),
        skipped_missing_halftime_score=home_ht_skip + away_ht_skip,
    )


def picchetto_sample_meta(ctx: CecchinoFixtureContexts) -> dict[str, dict[str, int | None]]:
    """Metadati sample per i 4 picchetti dell'engine."""
    from app.services.cecchino.cecchino_constants import (
        PICCHETTO_KEY_HOME_AWAY,
        PICCHETTO_KEY_LAST5_HOME_AWAY,
        PICCHETTO_KEY_LAST6_TOTALS,
        PICCHETTO_KEY_TOTALS,
    )

    return {
        PICCHETTO_KEY_HOME_AWAY: {
            "home_sample_count": ctx.home_context.sample_count,
            "away_sample_count": ctx.away_context.sample_count,
            "home_target_sample": None,
            "away_target_sample": None,
        },
        PICCHETTO_KEY_TOTALS: {
            "home_sample_count": ctx.home_total.sample_count,
            "away_sample_count": ctx.away_total.sample_count,
            "home_target_sample": None,
            "away_target_sample": None,
        },
        PICCHETTO_KEY_LAST5_HOME_AWAY: {
            "home_sample_count": ctx.home_recent_context_5.sample_count,
            "away_sample_count": ctx.away_recent_context_5.sample_count,
            "home_target_sample": TARGET_RECENT_CONTEXT,
            "away_target_sample": TARGET_RECENT_CONTEXT,
        },
        PICCHETTO_KEY_LAST6_TOTALS: {
            "home_sample_count": ctx.home_recent_total_6.sample_count,
            "away_sample_count": ctx.away_recent_total_6.sample_count,
            "home_target_sample": TARGET_RECENT_TOTAL,
            "away_target_sample": TARGET_RECENT_TOTAL,
        },
    }
