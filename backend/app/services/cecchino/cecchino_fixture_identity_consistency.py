"""Controllo read-only identità TodayFixture ↔ Fixture locale ↔ snapshot.

Fase 2A.3 — nessuna scrittura DB, confronto solo su sorgenti raw.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from app.models.cecchino_today_fixture import (
    MATCH_FINISHED,
    MATCH_LIVE,
    MATCH_UPCOMING,
    CecchinoTodayFixture,
)
from app.models.fixture import Fixture
from app.services.datetime_utils import ensure_datetime_utc, safe_isoformat

KICKOFF_TOLERANCE = timedelta(hours=6)

_FINISHED_CODES = frozenset(
    {
        "ft",
        "aet",
        "pen",
        "finished",
        "match finished",
        "after extra time",
        "penalty",
        "awarded",
        "wo",
        "awd",
    }
)
_UPCOMING_CODES = frozenset(
    {
        "ns",
        "tbd",
        "pst",
        "upcoming",
        "not started",
        "scheduled",
        "postponed",
        "canc",
        "abd",
        "susp",
    }
)


def _parse_iso_dt(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return ensure_datetime_utc(value, field_name="kickoff")
    try:
        s = str(value).replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
    except ValueError:
        return None
    return ensure_datetime_utc(dt, field_name="kickoff")


def _names_close(a: str | None, b: str | None) -> bool:
    if not a or not b:
        return False
    return a.strip().casefold() == b.strip().casefold()


def _extract_calculation_target_kickoff(cecchino_output: dict[str, Any] | None) -> str | None:
    if not isinstance(cecchino_output, dict):
        return None
    dq = cecchino_output.get("data_quality") or {}
    if not isinstance(dq, dict):
        return None
    leak = dq.get("leakage_check") or {}
    if not isinstance(leak, dict):
        return None
    raw = leak.get("target_kickoff")
    return str(raw) if raw else None


def _extract_xg_cutoff(expected_goal_diagnostics: dict[str, Any] | None) -> str | None:
    if not isinstance(expected_goal_diagnostics, dict):
        return None
    profiles = expected_goal_diagnostics.get("xg_profiles") or {}
    if not isinstance(profiles, dict):
        return None
    anti = profiles.get("anti_leakage") or {}
    if not isinstance(anti, dict):
        return None
    raw = anti.get("fixture_date_cutoff")
    return str(raw) if raw else None


def _kickoffs_match(a: datetime | None, b: datetime | None) -> bool:
    if a is None or b is None:
        return False
    if a.date() != b.date():
        return False
    return abs(a - b) <= KICKOFF_TOLERANCE


def _norm_status(*parts: str | None) -> str | None:
    for p in parts:
        if p is None:
            continue
        s = str(p).strip()
        if s:
            return s.casefold()
    return None


def _is_finished(status: str | None) -> bool:
    if not status:
        return False
    return status in _FINISHED_CODES or status == MATCH_FINISHED


def _is_upcoming(status: str | None) -> bool:
    if not status:
        return False
    return status in _UPCOMING_CODES or status == MATCH_UPCOMING


def _today_score(today_row: CecchinoTodayFixture) -> tuple[int | None, int | None]:
    home = today_row.goals_home
    away = today_row.goals_away
    if home is None and getattr(today_row, "score_fulltime_home", None) is not None:
        home = today_row.score_fulltime_home
    if away is None and getattr(today_row, "score_fulltime_away", None) is not None:
        away = today_row.score_fulltime_away
    return (
        int(home) if home is not None else None,
        int(away) if away is not None else None,
    )


def _has_score(home: int | None, away: int | None) -> bool:
    return home is not None and away is not None


def _status_bucket(status: str | None) -> str | None:
    if _is_finished(status):
        return "finished"
    if status == MATCH_LIVE or (status and status in {"1h", "2h", "ht", "et", "bt", "p", "live"}):
        return "live"
    if _is_upcoming(status):
        return "upcoming"
    return status


def build_fixture_identity_consistency(
    *,
    today_row: CecchinoTodayFixture,
    local_fixture: Fixture | None,
    cecchino_output: dict[str, Any] | None = None,
    expected_goal_diagnostics: dict[str, Any] | None = None,
    local_home_team_name: str | None = None,
    local_away_team_name: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Confronta solo valori raw: non muta Today né Fixture."""
    warnings: list[str] = []
    now_utc = ensure_datetime_utc(now, field_name="now") if now else datetime.now(timezone.utc)
    if now_utc is None:
        now_utc = datetime.now(timezone.utc)

    today_id = int(today_row.id)
    local_id = int(today_row.local_fixture_id) if today_row.local_fixture_id else None
    provider_id = int(today_row.provider_fixture_id)

    today_ko = ensure_datetime_utc(today_row.kickoff, field_name="today.kickoff") if today_row.kickoff else None
    today_ko_iso = safe_isoformat(today_ko, field_name="today.kickoff") if today_ko else None
    today_status_raw = _norm_status(today_row.match_display_status, today_row.fixture_status)
    today_gh, today_ga = _today_score(today_row)

    calc_target = _extract_calculation_target_kickoff(cecchino_output)
    xg_cutoff = _extract_xg_cutoff(expected_goal_diagnostics)
    calc_dt = _parse_iso_dt(calc_target)
    xg_dt = _parse_iso_dt(xg_cutoff)

    raw_today = {
        "kickoff": today_ko_iso,
        "status": today_row.fixture_status,
        "match_display_status": today_row.match_display_status,
        "score_home": today_gh,
        "score_away": today_ga,
    }
    raw_calc = {
        "target_kickoff": calc_target,
        "xg_cutoff": xg_cutoff,
    }

    base_flags = {
        "provider_match": False,
        "teams_match": False,
        "competition_match": False,
        "kickoff_match": False,
        "status_match": False,
        "score_match": False,
        "snapshot_match": False,
        "chronological_status_valid": False,
    }

    if local_fixture is None:
        warnings.append("missing_local_fixture")
        # Cronologia Today-only
        chrono_ok = True
        if today_ko is not None and today_ko > now_utc:
            if _is_finished(today_status_raw):
                chrono_ok = False
                warnings.append("future_fixture_marked_finished")
            if _has_score(today_gh, today_ga):
                chrono_ok = False
                warnings.append("future_fixture_has_final_score")
        if _is_finished(today_status_raw) and not _has_score(today_gh, today_ga):
            warnings.append("finished_without_score")
        return {
            "status": "unavailable",
            "today_fixture_id": today_id,
            "local_fixture_id": local_id,
            "provider_fixture_id": provider_id,
            "raw_sources": {
                "today": raw_today,
                "local_fixture": None,
                "calculation_snapshot": raw_calc,
            },
            "today_kickoff": today_ko_iso,
            "local_fixture_kickoff": None,
            "calculation_target_kickoff": calc_target,
            "xg_cutoff": xg_cutoff,
            **base_flags,
            "chronological_status_valid": chrono_ok,
            "warnings": warnings,
        }

    local_ko = ensure_datetime_utc(local_fixture.kickoff_at, field_name="fixture.kickoff_at")
    local_ko_iso = safe_isoformat(local_ko, field_name="fixture.kickoff_at") if local_ko else None
    local_status_raw = _norm_status(local_fixture.status, getattr(local_fixture, "status_long", None))
    local_gh = int(local_fixture.goals_home) if local_fixture.goals_home is not None else None
    local_ga = int(local_fixture.goals_away) if local_fixture.goals_away is not None else None

    raw_local = {
        "kickoff": local_ko_iso,
        "status": local_fixture.status,
        "status_long": getattr(local_fixture, "status_long", None),
        "score_home": local_gh,
        "score_away": local_ga,
        "api_fixture_id": int(local_fixture.api_fixture_id),
        "id": int(local_fixture.id),
    }

    provider_match = int(local_fixture.api_fixture_id) == provider_id
    if not provider_match:
        warnings.append("provider_fixture_id_mismatch")

    competition_match = (
        today_row.competition_id is not None
        and local_fixture.competition_id is not None
        and int(today_row.competition_id) == int(local_fixture.competition_id)
    )
    if not competition_match:
        warnings.append("competition_mismatch")

    if local_home_team_name is None and local_away_team_name is None:
        teams_match = True
    else:
        teams_match = _names_close(today_row.home_team_name, local_home_team_name) and _names_close(
            today_row.away_team_name, local_away_team_name
        )
        if not teams_match:
            warnings.append("teams_mismatch")

    kickoff_match = _kickoffs_match(today_ko, local_ko)
    if today_ko and local_ko and not kickoff_match:
        warnings.append("today_local_kickoff_mismatch")
        warnings.append("fixture_kickoff_mismatch")
        if today_ko.date() != local_ko.date():
            warnings.append("fixture_kickoff_calendar_day_mismatch")

    today_bucket = _status_bucket(today_status_raw)
    local_bucket = _status_bucket(local_status_raw)
    status_match = today_bucket is not None and today_bucket == local_bucket
    if not status_match:
        warnings.append("today_local_status_mismatch")
        if today_bucket == "finished" and local_bucket == "upcoming":
            warnings.append("today_finished_local_upcoming")

    score_match = today_gh == local_gh and today_ga == local_ga
    # entrambi senza score = match "vuoto" ok
    if not score_match:
        warnings.append("today_local_score_mismatch")

    if _is_finished(today_status_raw) and not _has_score(today_gh, today_ga):
        warnings.append("finished_without_score")

    snapshot_bits: list[str] = []
    if calc_dt is not None and today_ko is not None and not _kickoffs_match(today_ko, calc_dt):
        snapshot_bits.append("calculation_target_kickoff_mismatch")
    if xg_dt is not None and today_ko is not None and not _kickoffs_match(today_ko, xg_dt):
        snapshot_bits.append("xg_cutoff_mismatch")
    if calc_dt is not None and local_ko is not None and not _kickoffs_match(local_ko, calc_dt):
        snapshot_bits.append("calculation_vs_local_kickoff_mismatch")
    if xg_dt is not None and local_ko is not None and not _kickoffs_match(local_ko, xg_dt):
        snapshot_bits.append("xg_vs_local_kickoff_mismatch")
    snapshot_match = len(snapshot_bits) == 0
    warnings.extend(snapshot_bits)

    chronological_status_valid = True
    for ko, st, gh, ga, label in (
        (today_ko, today_status_raw, today_gh, today_ga, "today"),
        (local_ko, local_status_raw, local_gh, local_ga, "local"),
    ):
        if ko is not None and ko > now_utc:
            if _is_finished(st):
                chronological_status_valid = False
                if "future_fixture_marked_finished" not in warnings:
                    warnings.append("future_fixture_marked_finished")
            if _has_score(gh, ga):
                chronological_status_valid = False
                if "future_fixture_has_final_score" not in warnings:
                    warnings.append("future_fixture_has_final_score")

    identity_ok = (
        provider_match
        and competition_match
        and kickoff_match
        and status_match
        and score_match
        and snapshot_match
        and chronological_status_valid
    )
    if not teams_match and (local_home_team_name or local_away_team_name):
        identity_ok = False

    status = "consistent" if identity_ok else "inconsistent"
    return {
        "status": status,
        "today_fixture_id": today_id,
        "local_fixture_id": int(local_fixture.id),
        "provider_fixture_id": provider_id,
        "local_api_fixture_id": int(local_fixture.api_fixture_id),
        "raw_sources": {
            "today": raw_today,
            "local_fixture": raw_local,
            "calculation_snapshot": raw_calc,
        },
        "today_kickoff": today_ko_iso,
        "local_fixture_kickoff": local_ko_iso,
        "calculation_target_kickoff": calc_target,
        "xg_cutoff": xg_cutoff,
        "provider_match": provider_match,
        "teams_match": teams_match,
        "competition_match": competition_match,
        "kickoff_match": kickoff_match,
        "status_match": status_match,
        "score_match": score_match,
        "snapshot_match": snapshot_match,
        "chronological_status_valid": chronological_status_valid,
        "warnings": warnings,
    }


def build_historical_fixture_identity_consistency(
    *,
    today_row: CecchinoTodayFixture,
    local_fixture: Fixture | None,
    local_home_team_name: str | None = None,
    local_away_team_name: str | None = None,
) -> dict[str, Any]:
    """Identity statica per audit storico: status/score solo diagnostici, non bloccanti.

    Verifica: local_fixture_id, provider/api id, competition_id, home/away, kickoff UTC.
    Today upcoming vs Local FT / Today senza score vs Local con risultato non sono mismatch.
    """
    warnings: list[str] = []
    today_id = int(today_row.id)
    today_local_id = int(today_row.local_fixture_id) if today_row.local_fixture_id else None
    provider_id = int(today_row.provider_fixture_id) if today_row.provider_fixture_id is not None else None

    today_ko = ensure_datetime_utc(today_row.kickoff, field_name="today.kickoff") if today_row.kickoff else None
    today_ko_iso = safe_isoformat(today_ko, field_name="today.kickoff") if today_ko else None
    today_status_raw = _norm_status(today_row.match_display_status, today_row.fixture_status)
    today_gh, today_ga = _today_score(today_row)

    if local_fixture is None:
        warnings.append("missing_local_fixture")
        return {
            "status": "static_identity_unavailable",
            "today_fixture_id": today_id,
            "local_fixture_id": today_local_id,
            "provider_fixture_id": provider_id,
            "local_fixture_id_match": False,
            "provider_match": False,
            "competition_match": False,
            "teams_match": False,
            "kickoff_match": False,
            "status_match": False,
            "score_match": False,
            "today_kickoff": today_ko_iso,
            "local_fixture_kickoff": None,
            "warnings": warnings,
        }

    local_ko = ensure_datetime_utc(local_fixture.kickoff_at, field_name="fixture.kickoff_at")
    local_ko_iso = safe_isoformat(local_ko, field_name="fixture.kickoff_at") if local_ko else None
    local_status_raw = _norm_status(local_fixture.status, getattr(local_fixture, "status_long", None))
    local_gh = int(local_fixture.goals_home) if local_fixture.goals_home is not None else None
    local_ga = int(local_fixture.goals_away) if local_fixture.goals_away is not None else None

    local_fixture_id_match = today_local_id is not None and today_local_id == int(local_fixture.id)
    if today_local_id is None:
        warnings.append("missing_today_local_fixture_id")
    elif not local_fixture_id_match:
        warnings.append("local_fixture_id_mismatch")

    provider_match = (
        provider_id is not None
        and local_fixture.api_fixture_id is not None
        and int(local_fixture.api_fixture_id) == provider_id
    )
    if not provider_match:
        warnings.append("provider_fixture_id_mismatch")

    competition_match = (
        today_row.competition_id is not None
        and local_fixture.competition_id is not None
        and int(today_row.competition_id) == int(local_fixture.competition_id)
    )
    if not competition_match:
        warnings.append("competition_mismatch")

    if local_home_team_name is None and local_away_team_name is None:
        teams_match = True
    elif not today_row.home_team_name and not today_row.away_team_name:
        teams_match = True
        warnings.append("teams_names_unavailable_on_today")
    else:
        teams_match = _names_close(today_row.home_team_name, local_home_team_name) and _names_close(
            today_row.away_team_name, local_away_team_name
        )
        if not teams_match:
            warnings.append("teams_mismatch")

    kickoff_match = _kickoffs_match(today_ko, local_ko)
    if today_ko and local_ko and not kickoff_match:
        warnings.append("today_local_kickoff_mismatch")
        if today_ko.date() != local_ko.date():
            warnings.append("fixture_kickoff_calendar_day_mismatch")
    elif today_ko is None or local_ko is None:
        warnings.append("kickoff_unavailable")
        kickoff_match = False

    # Diagnostici non bloccanti
    today_bucket = _status_bucket(today_status_raw)
    local_bucket = _status_bucket(local_status_raw)
    status_match = today_bucket is not None and today_bucket == local_bucket
    if not status_match:
        warnings.append("today_local_status_mismatch")
        if today_bucket == "upcoming" and local_bucket == "finished":
            warnings.append("today_upcoming_vs_local_ft")

    score_match = today_gh == local_gh and today_ga == local_ga
    if not score_match:
        warnings.append("today_local_score_mismatch")
        if not _has_score(today_gh, today_ga) and _has_score(local_gh, local_ga):
            warnings.append("today_no_score_vs_local_score")

    static_ok = (
        local_fixture_id_match
        and provider_match
        and competition_match
        and kickoff_match
    )
    if not teams_match and (local_home_team_name or local_away_team_name):
        static_ok = False

    # Se Today non ha local_fixture_id ma provider+competition+kickoff+teams ok, ancora fail
    # (piano richiede local_fixture_id). Mantieni fail-closed.

    status = "static_identity_verified" if static_ok else "static_identity_failed"
    return {
        "status": status,
        "today_fixture_id": today_id,
        "local_fixture_id": int(local_fixture.id),
        "provider_fixture_id": provider_id,
        "local_api_fixture_id": int(local_fixture.api_fixture_id) if local_fixture.api_fixture_id is not None else None,
        "today_kickoff": today_ko_iso,
        "local_fixture_kickoff": local_ko_iso,
        "local_fixture_id_match": local_fixture_id_match,
        "provider_match": provider_match,
        "competition_match": competition_match,
        "teams_match": teams_match,
        "kickoff_match": kickoff_match,
        "status_match": status_match,
        "score_match": score_match,
        "warnings": warnings,
    }
