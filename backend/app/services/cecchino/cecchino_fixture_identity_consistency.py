"""Controllo read-only identità TodayFixture ↔ Fixture locale ↔ snapshot calcolati.

Fase 2A.2 — nessuna scrittura DB, nessuna formula predittiva.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from app.models.cecchino_today_fixture import CecchinoTodayFixture
from app.models.fixture import Fixture
from app.services.datetime_utils import ensure_datetime_utc, safe_isoformat

KICKOFF_TOLERANCE = timedelta(hours=6)


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


def build_fixture_identity_consistency(
    *,
    today_row: CecchinoTodayFixture,
    local_fixture: Fixture | None,
    cecchino_output: dict[str, Any] | None = None,
    expected_goal_diagnostics: dict[str, Any] | None = None,
    local_home_team_name: str | None = None,
    local_away_team_name: str | None = None,
) -> dict[str, Any]:
    warnings: list[str] = []
    today_id = int(today_row.id)
    local_id = int(today_row.local_fixture_id) if today_row.local_fixture_id else None
    provider_id = int(today_row.provider_fixture_id)
    today_ko = ensure_datetime_utc(today_row.kickoff, field_name="today.kickoff") if today_row.kickoff else None
    today_ko_iso = safe_isoformat(today_ko, field_name="today.kickoff") if today_ko else None

    calc_target = _extract_calculation_target_kickoff(cecchino_output)
    xg_cutoff = _extract_xg_cutoff(expected_goal_diagnostics)
    calc_dt = _parse_iso_dt(calc_target)
    xg_dt = _parse_iso_dt(xg_cutoff)

    if local_fixture is None:
        warnings.append("missing_local_fixture")
        return {
            "status": "unavailable",
            "today_fixture_id": today_id,
            "local_fixture_id": local_id,
            "provider_fixture_id": provider_id,
            "today_kickoff": today_ko_iso,
            "local_fixture_kickoff": None,
            "calculation_target_kickoff": calc_target,
            "xg_cutoff": xg_cutoff,
            "provider_match": False,
            "teams_match": False,
            "competition_match": False,
            "kickoff_match": False,
            "snapshot_match": False,
            "warnings": warnings,
        }

    local_ko = ensure_datetime_utc(local_fixture.kickoff_at, field_name="fixture.kickoff_at")
    local_ko_iso = safe_isoformat(local_ko, field_name="fixture.kickoff_at") if local_ko else None

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

    # Team match: prefer names when ids not on Today row
    home_ok = _names_close(today_row.home_team_name, local_home_team_name)
    away_ok = _names_close(today_row.away_team_name, local_away_team_name)
    if local_home_team_name is None and local_away_team_name is None:
        # senza nomi locali: non fallire solo per team (provider è chiave primaria)
        teams_match = True
    else:
        teams_match = home_ok and away_ok
        if not teams_match:
            warnings.append("teams_mismatch")

    kickoff_match = _kickoffs_match(today_ko, local_ko)
    if today_ko and local_ko and not kickoff_match:
        warnings.append("fixture_kickoff_mismatch")
        # giorni di calendario diversi → esplicito
        if today_ko.date() != local_ko.date():
            warnings.append("fixture_kickoff_calendar_day_mismatch")

    snapshot_bits = []
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

    # Stesse squadre non salvano se provider o kickoff divergono
    identity_ok = provider_match and competition_match and kickoff_match and snapshot_match
    if not teams_match and (local_home_team_name or local_away_team_name):
        identity_ok = False

    status = "consistent" if identity_ok else "inconsistent"
    return {
        "status": status,
        "today_fixture_id": today_id,
        "local_fixture_id": int(local_fixture.id),
        "provider_fixture_id": provider_id,
        "local_api_fixture_id": int(local_fixture.api_fixture_id),
        "today_kickoff": today_ko_iso,
        "local_fixture_kickoff": local_ko_iso,
        "calculation_target_kickoff": calc_target,
        "xg_cutoff": xg_cutoff,
        "provider_match": provider_match,
        "teams_match": teams_match,
        "competition_match": competition_match,
        "kickoff_match": kickoff_match,
        "snapshot_match": snapshot_match,
        "warnings": warnings,
    }


def apply_minimal_kickoff_realignment(
    today_row: CecchinoTodayFixture,
    local_fixture: Fixture,
    consistency: dict[str, Any],
) -> dict[str, Any]:
    """Correzione minima: se provider coincide ma kickoff diverge, allinea Today → Fixture.

    Scrive solo kickoff + warning esplicito. Nessun refresh massivo.
    Ritorna metadati dell'azione (caller decide commit).
    """
    result = {
        "applied": False,
        "reason": None,
        "warning": "kickoff_rescheduled_realigned",
    }
    if consistency.get("status") != "inconsistent":
        result["reason"] = "not_inconsistent"
        return result
    if not consistency.get("provider_match"):
        result["reason"] = "provider_mismatch_requires_mapping_fix"
        return result
    if consistency.get("kickoff_match"):
        result["reason"] = "kickoff_already_matched"
        return result
    if local_fixture.kickoff_at is None:
        result["reason"] = "local_kickoff_missing"
        return result

    old = today_row.kickoff
    today_row.kickoff = local_fixture.kickoff_at
    warnings = list(today_row.warnings_json or [])
    msg = (
        f"kickoff_rescheduled_realigned:"
        f"from={safe_isoformat(old, field_name='today.kickoff') if old else None}"
        f":to={safe_isoformat(local_fixture.kickoff_at, field_name='fixture.kickoff_at')}"
    )
    if msg not in warnings:
        warnings.append(msg)
    today_row.warnings_json = warnings
    result["applied"] = True
    result["reason"] = "aligned_today_kickoff_to_local_fixture"
    result["from"] = safe_isoformat(old, field_name="today.kickoff") if old else None
    result["to"] = safe_isoformat(local_fixture.kickoff_at, field_name="fixture.kickoff_at")
    return result


def flag_stale_calculation_snapshot(
    today_row: CecchinoTodayFixture,
    consistency: dict[str, Any],
) -> dict[str, Any]:
    """Flag read-only: Today↔Fixture allineati ma snapshot calc/xG su kickoff diverso.

    Non cancella output storici; aggiunge warning esplicito per ricalcolo single-fixture.
    """
    result = {
        "applied": False,
        "reason": None,
        "warning": "stale_calculation_snapshot_requires_recalc",
    }
    if consistency.get("status") != "inconsistent":
        result["reason"] = "not_inconsistent"
        return result
    if not consistency.get("provider_match"):
        result["reason"] = "provider_mismatch_requires_mapping_fix"
        return result
    if not consistency.get("kickoff_match"):
        result["reason"] = "kickoff_still_mismatched"
        return result
    if consistency.get("snapshot_match"):
        result["reason"] = "snapshot_already_matched"
        return result

    warnings = list(today_row.warnings_json or [])
    msg = "stale_calculation_snapshot_requires_recalc"
    if msg not in warnings:
        warnings.append(msg)
    today_row.warnings_json = warnings
    result["applied"] = True
    result["reason"] = "flagged_stale_calculation_snapshot"
    return result
