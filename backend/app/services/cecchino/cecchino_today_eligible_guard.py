"""Policy centralizzata: monotonicità eligible Cecchino Today sulle riscansioni."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.models.cecchino_today_fixture import (
    ELIGIBILITY_DISCOVERED,
    ELIGIBILITY_ELIGIBLE,
    ELIGIBILITY_ERROR,
    ELIGIBILITY_EXCLUDED_CECCHINO_NOT_CALCULABLE,
    ELIGIBILITY_EXCLUDED_INSUFFICIENT_STATS,
    ELIGIBILITY_EXCLUDED_KPI_NOT_CALCULABLE,
    ELIGIBILITY_EXCLUDED_LEAKAGE_FAILED,
    ELIGIBILITY_EXCLUDED_MAPPING,
    ELIGIBILITY_EXCLUDED_MISSING_1X2,
    ELIGIBILITY_EXCLUDED_MISSING_BOOKMAKER,
    ELIGIBILITY_EXCLUDED_MISSING_PICCHETTO,
    ELIGIBILITY_EXCLUDED_STARTED,
    ELIGIBILITY_EXCLUDED_ZERO_PROBABILITY,
    MATCH_CANCELLED,
    MATCH_FINISHED,
    MATCH_LIVE,
    MATCH_POSTPONED,
    CecchinoTodayFixture,
)
from app.services.cecchino.cecchino_today_display import (
    apply_display_from_api,
    extract_display_assets,
    map_fixture_display_status,
)

# --- Transition codes (report / metrics) ---
TRANSITION_NEW_ELIGIBLE = "new_eligible"
TRANSITION_PROMOTED_TO_ELIGIBLE = "promoted_to_eligible"
TRANSITION_ELIGIBLE_REFRESHED = "eligible_refreshed"
TRANSITION_ELIGIBLE_PRESERVED_REFRESH_FAILED = "eligible_preserved_refresh_failed"
TRANSITION_ELIGIBLE_FROZEN_AFTER_KICKOFF = "eligible_frozen_after_kickoff"
TRANSITION_ELIGIBLE_PRESERVED_TERMINAL_STATUS = "eligible_preserved_terminal_status"
TRANSITION_STARTED_NEVER_ELIGIBLE = "started_never_eligible"
TRANSITION_NORMAL_EXCLUDED = "normal_excluded"

ELIGIBILITY_TRANSITION_KEYS: tuple[str, ...] = (
    TRANSITION_NEW_ELIGIBLE,
    TRANSITION_PROMOTED_TO_ELIGIBLE,
    TRANSITION_ELIGIBLE_REFRESHED,
    TRANSITION_ELIGIBLE_PRESERVED_REFRESH_FAILED,
    TRANSITION_ELIGIBLE_FROZEN_AFTER_KICKOFF,
    TRANSITION_ELIGIBLE_PRESERVED_TERMINAL_STATUS,
    TRANSITION_STARTED_NEVER_ELIGIBLE,
)

WARNING_PREFIX = "rescan_preserved_previous_eligible:"

WARNING_STARTED_OR_FINISHED = f"{WARNING_PREFIX}started_or_finished"
WARNING_POSTPONED_OR_CANCELLED = f"{WARNING_PREFIX}postponed_or_cancelled"
WARNING_MISSING_BOOKMAKER = f"{WARNING_PREFIX}missing_bookmaker"
WARNING_MISSING_1X2 = f"{WARNING_PREFIX}missing_1x2"
WARNING_INSUFFICIENT_STATS = f"{WARNING_PREFIX}insufficient_stats"
WARNING_CALCULATION_ERROR = f"{WARNING_PREFIX}calculation_error"
WARNING_KPI_NOT_CALCULABLE = f"{WARNING_PREFIX}kpi_not_calculable"
WARNING_UNEXPECTED_ERROR = f"{WARNING_PREFIX}unexpected_error"

PROTECTED_SNAPSHOT_FIELDS: tuple[str, ...] = (
    "eligibility_status",
    "eligibility_reason",
    "bookmaker_status",
    "stats_status",
    "cecchino_status",
    "odds_snapshot_json",
    "stats_snapshot_json",
    "cecchino_output_json",
    "kpi_panel_json",
    "xg_profiles_json",
    "blocking_reasons_json",
    "odds_check_status",
    "odds_checked_at",
    "negative_cache_until",
    "local_fixture_id",
    "competition_id",
)

MATCH_STATE_UPDATABLE_FIELDS: tuple[str, ...] = (
    "provider_league_id",
    "provider_season",
    "country_name",
    "league_name",
    "home_team_name",
    "away_team_name",
    "kickoff",
    "fixture_status",
    "match_display_status",
    "country_flag_url",
    "league_logo_url",
    "home_team_logo_url",
    "away_team_logo_url",
    "goals_home",
    "goals_away",
    "score_fulltime_home",
    "score_fulltime_away",
    "score_halftime_home",
    "score_halftime_away",
    "elapsed_minutes",
    "raw_fixture_json",
)

_STATUS_TO_WARNING: dict[str, str] = {
    ELIGIBILITY_EXCLUDED_STARTED: WARNING_STARTED_OR_FINISHED,
    ELIGIBILITY_EXCLUDED_MISSING_BOOKMAKER: WARNING_MISSING_BOOKMAKER,
    ELIGIBILITY_EXCLUDED_MISSING_1X2: WARNING_MISSING_1X2,
    ELIGIBILITY_EXCLUDED_INSUFFICIENT_STATS: WARNING_INSUFFICIENT_STATS,
    ELIGIBILITY_EXCLUDED_LEAKAGE_FAILED: WARNING_INSUFFICIENT_STATS,
    ELIGIBILITY_EXCLUDED_MAPPING: WARNING_CALCULATION_ERROR,
    ELIGIBILITY_EXCLUDED_CECCHINO_NOT_CALCULABLE: WARNING_CALCULATION_ERROR,
    ELIGIBILITY_EXCLUDED_MISSING_PICCHETTO: WARNING_CALCULATION_ERROR,
    ELIGIBILITY_EXCLUDED_ZERO_PROBABILITY: WARNING_CALCULATION_ERROR,
    ELIGIBILITY_ERROR: WARNING_UNEXPECTED_ERROR,
    ELIGIBILITY_EXCLUDED_KPI_NOT_CALCULABLE: WARNING_KPI_NOT_CALCULABLE,
    ELIGIBILITY_DISCOVERED: WARNING_UNEXPECTED_ERROR,
}


@dataclass
class EligiblePersistenceOutcome:
    row: CecchinoTodayFixture
    effective_status: str
    transition: str
    previous_status: str | None
    incoming_status: str
    preserved: bool


def empty_eligibility_transitions() -> dict[str, int]:
    return {key: 0 for key in ELIGIBILITY_TRANSITION_KEYS}


def is_protected_eligible(row: CecchinoTodayFixture | None) -> bool:
    if row is None:
        return False
    return str(row.eligibility_status or "") == ELIGIBILITY_ELIGIBLE


def append_preservation_warning(warnings: list[Any] | None, code: str) -> list[Any]:
    """Aggiunge un warning di preservation una sola volta (dedup)."""
    current = list(warnings or [])
    if code not in current:
        current.append(code)
    return current


def warning_code_for_incoming_status(incoming_status: str) -> str:
    return _STATUS_TO_WARNING.get(incoming_status, WARNING_UNEXPECTED_ERROR)


def classify_non_upcoming_transition(api_item: dict[str, Any]) -> str:
    """Distingue freeze post-kickoff vs preservazione stato terminale."""
    assets = extract_display_assets(api_item)
    display = str(assets.get("match_display_status") or "")
    if display in (MATCH_POSTPONED, MATCH_CANCELLED):
        return TRANSITION_ELIGIBLE_PRESERVED_TERMINAL_STATUS
    fx = api_item.get("fixture") or {}
    short = str((fx.get("status") or {}).get("short") or "NS")
    mapped, _ = map_fixture_display_status(short, assets.get("elapsed_minutes"))
    if mapped in (MATCH_POSTPONED, MATCH_CANCELLED):
        return TRANSITION_ELIGIBLE_PRESERVED_TERMINAL_STATUS
    return TRANSITION_ELIGIBLE_FROZEN_AFTER_KICKOFF


def warning_for_non_upcoming_transition(transition: str) -> str:
    if transition == TRANSITION_ELIGIBLE_PRESERVED_TERMINAL_STATUS:
        return WARNING_POSTPONED_OR_CANCELLED
    return WARNING_STARTED_OR_FINISHED


def classify_eligible_success_transition(previous_status: str | None) -> str:
    if previous_status == ELIGIBILITY_ELIGIBLE:
        return TRANSITION_ELIGIBLE_REFRESHED
    if previous_status is None:
        return TRANSITION_NEW_ELIGIBLE
    return TRANSITION_PROMOTED_TO_ELIGIBLE


def apply_match_state_only(
    row: CecchinoTodayFixture,
    api_item: dict[str, Any],
    *,
    brief: dict[str, Any],
) -> CecchinoTodayFixture:
    """Aggiorna soltanto metadati/stato partita consentiti (freeze / census eligible)."""
    row.provider_league_id = brief.get("provider_league_id") or None
    season = brief.get("provider_season")
    row.provider_season = int(season) if season else None
    row.country_name = brief.get("country_name") or None
    row.league_name = brief.get("league_name") or None
    row.home_team_name = brief.get("home_team_name") or None
    row.away_team_name = brief.get("away_team_name") or None
    row.kickoff = brief.get("kickoff")
    row.fixture_status = brief.get("fixture_status")
    row.raw_fixture_json = api_item
    apply_display_from_api(row, api_item)
    return row


def preserve_eligible_snapshot(
    row: CecchinoTodayFixture,
    *,
    reason_code: str,
    incoming_status: str,
    api_item: dict[str, Any] | None = None,
    brief: dict[str, Any] | None = None,
) -> EligiblePersistenceOutcome:
    """Mantiene eligibility=eligible e lo snapshot pre-match; opzionalmente aggiorna match state."""
    previous = str(row.eligibility_status or ELIGIBILITY_ELIGIBLE)
    if api_item is not None and brief is not None:
        apply_match_state_only(row, api_item, brief=brief)
    row.warnings_json = append_preservation_warning(row.warnings_json, reason_code)
    # Garantisce monotonicità
    row.eligibility_status = ELIGIBILITY_ELIGIBLE
    return EligiblePersistenceOutcome(
        row=row,
        effective_status=ELIGIBILITY_ELIGIBLE,
        transition=TRANSITION_ELIGIBLE_PRESERVED_REFRESH_FAILED,
        previous_status=previous,
        incoming_status=incoming_status,
        preserved=True,
    )


def freeze_eligible_after_kickoff(
    row: CecchinoTodayFixture,
    api_item: dict[str, Any],
    *,
    brief: dict[str, Any],
) -> EligiblePersistenceOutcome:
    """Eligible già calcolata: aggiorna solo stato/risultato, congela snapshot pre-match."""
    previous = str(row.eligibility_status or ELIGIBILITY_ELIGIBLE)
    transition = classify_non_upcoming_transition(api_item)
    apply_match_state_only(row, api_item, brief=brief)
    warn = warning_for_non_upcoming_transition(transition)
    row.warnings_json = append_preservation_warning(row.warnings_json, warn)
    row.eligibility_status = ELIGIBILITY_ELIGIBLE
    return EligiblePersistenceOutcome(
        row=row,
        effective_status=ELIGIBILITY_ELIGIBLE,
        transition=transition,
        previous_status=previous,
        incoming_status=ELIGIBILITY_EXCLUDED_STARTED,
        preserved=True,
    )


def resolve_persistence(
    *,
    row: CecchinoTodayFixture,
    previous_status: str | None,
    incoming_status: str,
    would_write_non_eligible: bool,
) -> EligiblePersistenceOutcome | None:
    """
    Se la riga è protetta e l'incoming non è eligible, restituisce outcome di preserve.
    Altrimenti None (il chiamante può procedere con la scrittura normale).
    """
    if not is_protected_eligible(row) and previous_status != ELIGIBILITY_ELIGIBLE:
        return None
    if incoming_status == ELIGIBILITY_ELIGIBLE:
        return None
    if not would_write_non_eligible:
        return None
    # Riga già eligible in DB, oppure era eligible pre-census
    protected_row = row if is_protected_eligible(row) else row
    if previous_status == ELIGIBILITY_ELIGIBLE or is_protected_eligible(protected_row):
        return EligiblePersistenceOutcome(
            row=protected_row,
            effective_status=ELIGIBILITY_ELIGIBLE,
            transition=TRANSITION_ELIGIBLE_PRESERVED_REFRESH_FAILED,
            previous_status=previous_status or ELIGIBILITY_ELIGIBLE,
            incoming_status=incoming_status,
            preserved=True,
        )
    return None
