"""Recupero fixture finite PIT per Cecchino — anti-leakage, competition-scoped."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

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
from app.services.predictions_v10.v10_prior_context import (
    _prior_fixtures_for_team,
    _resolve_fixture_season_id,
)
from app.services.predictions_v11.split_fixtures import team_split_fixtures
from app.services.predictions_v11.v11_shared import last_n
from app.services.sot_feature_math import fixture_key_before


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
    return _prior_fixtures_for_team(
        db,
        season_id=season_id,
        cutoff_kickoff=target_fixture.kickoff_at,
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
    cutoff_ko = target.kickoff_at
    cutoff_id = int(target.id)
    target_kickoff = cutoff_ko.isoformat() if cutoff_ko is not None else None
    checked_at = datetime.now(timezone.utc).isoformat()

    if cutoff_ko is None:
        return (
            {
                "status": LEAKAGE_UNDEFINED,
                "target_kickoff": None,
                "max_source_fixture_date": None,
                "checked_at": checked_at,
            },
            ["target:missing_kickoff"],
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
        if not fixture_key_before(f.kickoff_at, fid, cutoff_ko, cutoff_id):
            reasons.append(f"fixture_{fid}:kickoff_not_before_target")
        if st in LIVE_STATUSES or st in SCHEDULED_STATUSES:
            reasons.append(f"fixture_{fid}:live_or_scheduled:{st}")
        if f.kickoff_at is not None and (max_ko is None or f.kickoff_at > max_ko):
            max_ko = f.kickoff_at

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
