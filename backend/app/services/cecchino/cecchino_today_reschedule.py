"""Riconciliazione sicura fixture riprogrammate (stesso api_fixture_id, kickoff diverso)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.core.constants import FINISHED_STATUSES
from app.models import Fixture, League, Season, Team
from app.models.cecchino_today_fixture import (
    MATCH_POSTPONED,
    MATCH_UNKNOWN,
    MATCH_UPCOMING,
    CecchinoTodayFixture,
)
from app.services.datetime_utils import ensure_datetime_utc

logger = logging.getLogger(__name__)

CLASSIFICATION_RESCHEDULED = "FIXTURE_RESCHEDULED"
REASON_FINISHED = "reschedule_conflict_finished_fixture"
REASON_IDENTITY = "reschedule_identity_conflict"
REASON_NOT_RECONCILED = "local_fixture_kickoff_not_reconciled"
REASON_PROVIDER_ID_MISMATCH = "reschedule_provider_fixture_id_mismatch"

WARNING_FIXTURE_RESCHEDULED = "fixture_rescheduled"


@dataclass(frozen=True)
class RescheduleOutcome:
    ok: bool
    reason: str | None = None
    rescheduled: bool = False
    classification: str | None = None
    old_kickoff: datetime | None = None
    new_kickoff: datetime | None = None


def is_terminal_finished_status(status: str | None) -> bool:
    """True solo con evidenza terminale reale (FT/AET/PEN). Goals non sono criterio autonomo."""
    return (status or "").strip().upper() in FINISHED_STATUSES


def normalize_kickoff(value: Any) -> datetime | None:
    return ensure_datetime_utc(value, field_name="kickoff")


def kickoffs_equal(a: Any, b: Any) -> bool:
    na = normalize_kickoff(a)
    nb = normalize_kickoff(b)
    if na is None or nb is None:
        return False
    return na.replace(microsecond=0) == nb.replace(microsecond=0)


def parse_provider_kickoff(api_item: dict[str, Any]) -> datetime | None:
    fx = api_item.get("fixture") or {}
    return normalize_kickoff(fx.get("date"))


def parse_provider_fixture_id(api_item: dict[str, Any]) -> int | None:
    fx = api_item.get("fixture") or {}
    raw = fx.get("id")
    if raw is None:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def parse_provider_status_short(api_item: dict[str, Any]) -> str:
    fx = api_item.get("fixture") or {}
    status_obj = fx.get("status") or {}
    return str(status_obj.get("short") or "NS").strip().upper() or "NS"


def _provider_team_api_ids(api_item: dict[str, Any]) -> tuple[int | None, int | None]:
    teams = api_item.get("teams") or {}
    home = teams.get("home") or {}
    away = teams.get("away") or {}

    def _id(block: dict[str, Any]) -> int | None:
        raw = block.get("id")
        if raw is None:
            return None
        try:
            return int(raw)
        except (TypeError, ValueError):
            return None

    return _id(home), _id(away)


def _local_team_api_ids(db: Session, local_fx: Fixture) -> tuple[int | None, int | None]:
    home = getattr(local_fx, "home_team", None)
    away = getattr(local_fx, "away_team", None)
    if home is None and getattr(local_fx, "home_team_id", None) is not None:
        home = db.get(Team, int(local_fx.home_team_id))
    if away is None and getattr(local_fx, "away_team_id", None) is not None:
        away = db.get(Team, int(local_fx.away_team_id))
    home_api = int(home.api_team_id) if home is not None and home.api_team_id is not None else None
    away_api = int(away.api_team_id) if away is not None and away.api_team_id is not None else None
    return home_api, away_api


def _local_league_season(db: Session, local_fx: Fixture) -> tuple[int | None, int | None]:
    league = getattr(local_fx, "league", None)
    season = getattr(local_fx, "season", None)
    if league is None and getattr(local_fx, "league_id", None) is not None:
        league = db.get(League, int(local_fx.league_id))
    if season is None and getattr(local_fx, "season_id", None) is not None:
        season = db.get(Season, int(local_fx.season_id))
    league_api = int(league.api_league_id) if league is not None and league.api_league_id is not None else None
    season_year = int(season.year) if season is not None and season.year is not None else None
    return league_api, season_year


def check_reschedule_identity(db: Session, local_fx: Fixture, api_item: dict[str, Any]) -> str | None:
    """None se coerente; altrimenti REASON_IDENTITY."""
    provider_id = parse_provider_fixture_id(api_item)
    if provider_id is None or int(local_fx.api_fixture_id) != provider_id:
        return REASON_PROVIDER_ID_MISMATCH

    p_home, p_away = _provider_team_api_ids(api_item)
    l_home, l_away = _local_team_api_ids(db, local_fx)
    if p_home is not None and l_home is not None and p_home != l_home:
        return REASON_IDENTITY
    if p_away is not None and l_away is not None and p_away != l_away:
        return REASON_IDENTITY

    league_meta = api_item.get("league") or {}
    p_league = league_meta.get("id")
    p_season = league_meta.get("season")
    l_league, l_season = _local_league_season(db, local_fx)
    try:
        p_league_i = int(p_league) if p_league is not None else None
    except (TypeError, ValueError):
        p_league_i = None
    try:
        p_season_i = int(p_season) if p_season is not None else None
    except (TypeError, ValueError):
        p_season_i = None

    if p_league_i is not None and l_league is not None and p_league_i != l_league:
        return REASON_IDENTITY
    if p_season_i is not None and l_season is not None and p_season_i != l_season:
        return REASON_IDENTITY
    return None


def detect_kickoff_reschedule(
    local_fx: Fixture,
    api_item: dict[str, Any],
) -> tuple[bool, datetime | None, datetime | None]:
    """True se stesso provider id implicito e kickoff provider != local."""
    provider_ko = parse_provider_kickoff(api_item)
    local_ko = normalize_kickoff(getattr(local_fx, "kickoff_at", None))
    if provider_ko is None or local_ko is None:
        return False, local_ko, provider_ko
    if kickoffs_equal(local_ko, provider_ko):
        return False, local_ko, provider_ko
    return True, local_ko, provider_ko


def reconcile_canonical_fixture_from_api(
    db: Session,
    local_fx: Fixture,
    api_item: dict[str, Any],
) -> RescheduleOutcome:
    """
    Allinea Fixture.kickoff_at al provider se reschedule sicuro.
    FAIL CLOSED su finished terminale o identity mismatch.
    """
    identity_reason = check_reschedule_identity(db, local_fx, api_item)
    if identity_reason is not None:
        return RescheduleOutcome(ok=False, reason=identity_reason)

    changed, old_ko, new_ko = detect_kickoff_reschedule(local_fx, api_item)
    if not changed:
        return RescheduleOutcome(ok=True, old_kickoff=old_ko, new_kickoff=new_ko)

    if is_terminal_finished_status(getattr(local_fx, "status", None)):
        return RescheduleOutcome(
            ok=False,
            reason=REASON_FINISHED,
            old_kickoff=old_ko,
            new_kickoff=new_ko,
        )

    assert new_ko is not None
    fx = api_item.get("fixture") or {}
    status_obj = fx.get("status") or {}
    status_short = parse_provider_status_short(api_item)
    status_long_raw = status_obj.get("long")
    status_long = str(status_long_raw)[:128] if status_long_raw else None
    elapsed_raw = status_obj.get("elapsed")
    try:
        elapsed = int(elapsed_raw) if elapsed_raw is not None else None
    except (TypeError, ValueError):
        elapsed = None

    local_fx.kickoff_at = new_ko
    local_fx.status = status_short
    local_fx.status_long = status_long
    local_fx.elapsed = elapsed
    local_fx.raw_json = api_item

    db.flush()
    try:
        db.refresh(local_fx)
    except Exception:
        # sessioni test / oggetti transienti
        pass

    if not kickoffs_equal(local_fx.kickoff_at, new_ko):
        return RescheduleOutcome(
            ok=False,
            reason=REASON_NOT_RECONCILED,
            rescheduled=True,
            classification=CLASSIFICATION_RESCHEDULED,
            old_kickoff=old_ko,
            new_kickoff=new_ko,
        )

    logger.info(
        "%s provider_fixture_id=%s old_kickoff=%s new_kickoff=%s",
        CLASSIFICATION_RESCHEDULED,
        local_fx.api_fixture_id,
        old_ko.isoformat() if old_ko else None,
        new_ko.isoformat(),
    )
    return RescheduleOutcome(
        ok=True,
        rescheduled=True,
        classification=CLASSIFICATION_RESCHEDULED,
        old_kickoff=old_ko,
        new_kickoff=new_ko,
    )


def assert_post_upsert_invariant(
    db: Session,
    local_fx: Fixture,
    api_item: dict[str, Any],
) -> RescheduleOutcome:
    """Safety net obbligatorio prima di calc/xG/KPI/Balance/snapshot."""
    identity_reason = check_reschedule_identity(db, local_fx, api_item)
    if identity_reason is not None:
        return RescheduleOutcome(ok=False, reason=identity_reason)

    provider_ko = parse_provider_kickoff(api_item)
    if provider_ko is None or not kickoffs_equal(local_fx.kickoff_at, provider_ko):
        return RescheduleOutcome(
            ok=False,
            reason=REASON_NOT_RECONCILED,
            old_kickoff=normalize_kickoff(local_fx.kickoff_at),
            new_kickoff=provider_ko,
        )
    return RescheduleOutcome(
        ok=True,
        old_kickoff=normalize_kickoff(local_fx.kickoff_at),
        new_kickoff=provider_ko,
    )


def append_reschedule_warnings(
    warnings: list[Any] | None,
    *,
    old_kickoff: datetime | None,
    new_kickoff: datetime | None,
) -> list[Any]:
    out: list[Any] = list(warnings or [])
    markers = {
        WARNING_FIXTURE_RESCHEDULED,
        f"rescheduled_from={old_kickoff.isoformat() if old_kickoff else ''}",
        f"rescheduled_to={new_kickoff.isoformat() if new_kickoff else ''}",
    }
    for m in markers:
        if m not in out:
            out.append(m)
    return out


def provider_kickoff_moved_to_other_day(
    *,
    provider_kickoff: datetime | None,
    scan_date: Any,
    timezone_str: str,
) -> bool:
    """
    True se il kickoff provider, nella timezone dello scan, cade in un giorno
    diverso da scan_date. Semantica allineata a get_fixture_local_date().
    NON confrontare mai .date() UTC con scan_date locale.
    """
    p_ko = normalize_kickoff(provider_kickoff)
    if p_ko is None or scan_date is None:
        return False
    try:
        local_date = p_ko.astimezone(ZoneInfo(timezone_str)).date()
    except Exception:
        return False
    try:
        return local_date != scan_date
    except TypeError:
        return False


def apply_old_today_rescheduled_postponed(
    row: CecchinoTodayFixture,
    *,
    provider_kickoff: datetime,
) -> None:
    """
    Marca la vecchia CecchinoTodayFixture come rinviata/rescheduled.
    NON muta scan_date, kickoff, goals, score, raw_fixture_json.
    """
    old_ko = normalize_kickoff(row.kickoff)
    row.match_display_status = MATCH_POSTPONED
    row.warnings_json = append_reschedule_warnings(
        row.warnings_json,
        old_kickoff=old_ko,
        new_kickoff=provider_kickoff,
    )


def today_row_needs_past_kickoff_id_reconciliation(
    row: CecchinoTodayFixture,
    *,
    now: datetime,
) -> bool:
    st = row.match_display_status
    if st not in (MATCH_UPCOMING, MATCH_UNKNOWN, None):
        return False
    ko = normalize_kickoff(row.kickoff)
    if ko is None:
        return False
    return ko < now
