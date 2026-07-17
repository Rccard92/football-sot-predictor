"""Coorte Intensità Goal v5 — solo partite eleggibili Cecchino Today (scan_date).

Fonte canonica: CecchinoTodayFixture.eligibility_status (persistito da
validate_cecchino_today_final_eligibility). Nessuna seconda logica di gate.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.constants import FINISHED_STATUSES
from app.models.cecchino_today_fixture import (
    ELIGIBILITY_DISCOVERED,
    ELIGIBILITY_ELIGIBLE,
    ELIGIBILITY_ERROR,
    ELIGIBILITY_EXCLUDED_CECCHINO_NOT_CALCULABLE,
    ELIGIBILITY_EXCLUDED_COMPETITION,
    ELIGIBILITY_EXCLUDED_CUP,
    ELIGIBILITY_EXCLUDED_FRIENDLY,
    ELIGIBILITY_EXCLUDED_INSUFFICIENT_STATS,
    ELIGIBILITY_EXCLUDED_KPI_NOT_CALCULABLE,
    ELIGIBILITY_EXCLUDED_LEAKAGE_FAILED,
    ELIGIBILITY_EXCLUDED_MAPPING,
    ELIGIBILITY_EXCLUDED_MISSING_1X2,
    ELIGIBILITY_EXCLUDED_MISSING_BOOKMAKER,
    ELIGIBILITY_EXCLUDED_MISSING_PICCHETTO,
    ELIGIBILITY_EXCLUDED_STARTED,
    ELIGIBILITY_EXCLUDED_WOMEN,
    ELIGIBILITY_EXCLUDED_YOUTH,
    ELIGIBILITY_EXCLUDED_ZERO_PROBABILITY,
    CecchinoTodayFixture,
)
from app.models.fixture import Fixture
from app.services.cecchino.cecchino_goal_intensity_v5_audit_common import (
    _snapshot_pre_kickoff_score,
)
from app.services.datetime_utils import ensure_datetime_utc, safe_isoformat

MIN_GOAL_INTENSITY_TODAY_SCAN_DATE = date(2026, 6, 19)
COHORT_BASIS = "cecchino_today_eligible_scan_date"
TARGET_SOURCE = "cecchino_today_eligible_matches"
RESULT_SOURCE = "local_fixture_final_result"
HISTORICAL_FEATURE_SOURCE = "prior_local_fixtures_only"
ELIGIBILITY_SOURCE_PERSISTED = "persisted_today_field"
ELIGIBILITY_SOURCE_UNAVAILABLE = "unavailable"

RANGE_ERROR_MESSAGE = (
    "La ricerca Intensità Goal utilizza le scansioni Cecchino Today disponibili dal 19/06/2026."
)

_KNOWN_INELIGIBLE = frozenset(
    {
        ELIGIBILITY_DISCOVERED,
        ELIGIBILITY_EXCLUDED_COMPETITION,
        ELIGIBILITY_EXCLUDED_WOMEN,
        ELIGIBILITY_EXCLUDED_CUP,
        ELIGIBILITY_EXCLUDED_FRIENDLY,
        ELIGIBILITY_EXCLUDED_YOUTH,
        ELIGIBILITY_EXCLUDED_STARTED,
        ELIGIBILITY_EXCLUDED_MISSING_BOOKMAKER,
        ELIGIBILITY_EXCLUDED_MISSING_1X2,
        ELIGIBILITY_EXCLUDED_INSUFFICIENT_STATS,
        ELIGIBILITY_EXCLUDED_MISSING_PICCHETTO,
        ELIGIBILITY_EXCLUDED_ZERO_PROBABILITY,
        ELIGIBILITY_EXCLUDED_CECCHINO_NOT_CALCULABLE,
        ELIGIBILITY_EXCLUDED_KPI_NOT_CALCULABLE,
        ELIGIBILITY_EXCLUDED_LEAKAGE_FAILED,
        ELIGIBILITY_EXCLUDED_MAPPING,
        ELIGIBILITY_ERROR,
    }
)

_MAX_DIAGNOSTIC_EXAMPLES = 100


@dataclass
class ClassifiedTodayScan:
    row: CecchinoTodayFixture
    eligibility_status: str  # eligible | ineligible | unknown
    eligibility_source: str
    eligibility_reason_codes: list[str]


@dataclass
class GoalIntensityTarget:
    today_row: CecchinoTodayFixture
    local_fixture: Fixture
    eligibility_status: str
    eligibility_source: str
    eligibility_reason_codes: list[str]
    scan_date: date
    selection: dict[str, Any] = field(default_factory=dict)


@dataclass
class GoalIntensityTodayCohort:
    date_from: date
    date_to: date
    date_from_clamped: bool
    warnings: list[str]
    error: str | None
    today_rows_raw: list[CecchinoTodayFixture]
    targets: list[GoalIntensityTarget]
    eligible_pending: list[dict[str, Any]]
    eligible_unresolved: list[dict[str, Any]]
    eligibility_diagnostics: dict[str, Any]
    diagnostic_examples: list[dict[str, Any]]
    # Per preload indici
    local_fixtures: list[Fixture]
    selected_today_rows: list[CecchinoTodayFixture]


def normalize_goal_intensity_scan_range(
    date_from: date,
    date_to: date,
) -> tuple[date, date, bool, str | None, list[str]]:
    """Ritorna (from, to, clamped, error, warnings)."""
    warnings: list[str] = []
    if date_to < MIN_GOAL_INTENSITY_TODAY_SCAN_DATE:
        return date_from, date_to, False, RANGE_ERROR_MESSAGE, warnings
    clamped = False
    effective_from = date_from
    if date_from < MIN_GOAL_INTENSITY_TODAY_SCAN_DATE:
        effective_from = MIN_GOAL_INTENSITY_TODAY_SCAN_DATE
        clamped = True
        warnings.append(
            "date_from_clamped_to_min_today_scan_date_2026_06_19"
        )
    if effective_from > date_to:
        return effective_from, date_to, clamped, RANGE_ERROR_MESSAGE, warnings
    return effective_from, date_to, clamped, None, warnings


def classify_today_eligibility(row: CecchinoTodayFixture) -> ClassifiedTodayScan:
    """Classifica eleggibilità dal campo persistito — nessuna logica gate duplicata."""
    raw = getattr(row, "eligibility_status", None)
    codes: list[str] = []
    reason = getattr(row, "eligibility_reason", None)
    if reason:
        codes.append(str(reason))
    blocking = getattr(row, "blocking_reasons_json", None)
    if isinstance(blocking, list):
        for b in blocking:
            if b is not None and str(b).strip():
                codes.append(str(b))

    if raw is None or (isinstance(raw, str) and not raw.strip()):
        return ClassifiedTodayScan(
            row=row,
            eligibility_status="unknown",
            eligibility_source=ELIGIBILITY_SOURCE_UNAVAILABLE,
            eligibility_reason_codes=codes or ["eligibility_status_missing"],
        )

    status = str(raw).strip()
    if status == ELIGIBILITY_ELIGIBLE:
        return ClassifiedTodayScan(
            row=row,
            eligibility_status="eligible",
            eligibility_source=ELIGIBILITY_SOURCE_PERSISTED,
            eligibility_reason_codes=[],
        )
    if status in _KNOWN_INELIGIBLE:
        if status not in codes:
            codes.insert(0, status)
        return ClassifiedTodayScan(
            row=row,
            eligibility_status="ineligible",
            eligibility_source=ELIGIBILITY_SOURCE_PERSISTED,
            eligibility_reason_codes=codes,
        )
    # Status non riconosciuto → fail-closed unknown
    if status not in codes:
        codes.insert(0, status)
    codes.append("unrecognized_eligibility_status")
    return ClassifiedTodayScan(
        row=row,
        eligibility_status="unknown",
        eligibility_source=ELIGIBILITY_SOURCE_PERSISTED,
        eligibility_reason_codes=codes,
    )


def load_today_scans_for_goal_intensity(
    db: Session,
    *,
    date_from: date,
    date_to: date,
    competition_id: int | None = None,
) -> list[CecchinoTodayFixture]:
    clauses = [
        CecchinoTodayFixture.scan_date >= date_from,
        CecchinoTodayFixture.scan_date <= date_to,
    ]
    if competition_id is not None:
        clauses.append(CecchinoTodayFixture.competition_id == competition_id)
    return list(
        db.scalars(
            select(CecchinoTodayFixture)
            .where(*clauses)
            .order_by(CecchinoTodayFixture.scan_date.asc(), CecchinoTodayFixture.id.asc())
        ).all()
    )


def _match_group_key(row: CecchinoTodayFixture) -> tuple[str, ...]:
    src = str(getattr(row, "provider_source", None) or "")
    pid = getattr(row, "provider_fixture_id", None)
    if src and pid is not None:
        return ("provider", src, str(int(pid)))
    lid = getattr(row, "local_fixture_id", None)
    if lid is not None:
        return ("local", str(int(lid)))
    return ("orphan", str(int(row.id)))


def _diagnostic_example(classified: ClassifiedTodayScan) -> dict[str, Any]:
    row = classified.row
    ko = ensure_datetime_utc(getattr(row, "kickoff", None), field_name="today.kickoff")
    return {
        "today_fixture_id": int(row.id),
        "local_fixture_id": int(row.local_fixture_id) if row.local_fixture_id is not None else None,
        "provider_fixture_id": int(row.provider_fixture_id) if row.provider_fixture_id is not None else None,
        "scan_date": row.scan_date.isoformat() if row.scan_date else None,
        "kickoff": safe_isoformat(ko, field_name="today.kickoff") if ko else None,
        "competition_id": int(row.competition_id) if row.competition_id is not None else None,
        "home_team": row.home_team_name,
        "away_team": row.away_team_name,
        "eligibility_status": classified.eligibility_status,
        "eligibility_reason": row.eligibility_reason,
        "eligibility_reason_codes": list(classified.eligibility_reason_codes),
        "eligibility_source": classified.eligibility_source,
    }


def _fixture_resolution(fx: Fixture | None) -> str:
    """finished | pending | unresolved."""
    if fx is None:
        return "unresolved"
    st = str(getattr(fx, "status", None) or "").upper()
    if st in FINISHED_STATUSES and fx.goals_home is not None and fx.goals_away is not None:
        if fx.home_team_id is not None and fx.away_team_id is not None:
            return "finished"
    if st in FINISHED_STATUSES:
        return "unresolved"
    return "pending"


def select_eligible_match_groups(
    classified: list[ClassifiedTodayScan],
) -> list[dict[str, Any]]:
    """Raggruppa scansioni e seleziona snapshot eligible pre-kickoff più recente."""
    groups: dict[tuple[str, ...], list[ClassifiedTodayScan]] = defaultdict(list)
    for c in classified:
        groups[_match_group_key(c.row)].append(c)

    selected: list[dict[str, Any]] = []
    for key, scans in groups.items():
        n_total = len(scans)
        n_eligible = sum(1 for s in scans if s.eligibility_status == "eligible")
        n_ineligible = sum(1 for s in scans if s.eligibility_status == "ineligible")
        n_unknown = sum(1 for s in scans if s.eligibility_status == "unknown")

        eligible_pre: list[tuple[datetime, ClassifiedTodayScan]] = []
        for s in scans:
            if s.eligibility_status != "eligible":
                continue
            ko = ensure_datetime_utc(getattr(s.row, "kickoff", None), field_name="sel.kickoff")
            if ko is None:
                continue
            score = _snapshot_pre_kickoff_score(s.row, ko)
            if score is None:
                continue
            eligible_pre.append((score, s))

        winner: ClassifiedTodayScan | None = None
        criterion = "no_eligible_pre_kickoff_snapshot"
        if eligible_pre:
            eligible_pre.sort(key=lambda x: (x[0], int(x[1].row.id)), reverse=True)
            winner = eligible_pre[0][1]
            criterion = "latest_eligible_pre_kickoff_snapshot"

        selected.append(
            {
                "group_key": key,
                "scans_total": n_total,
                "scans_eligible": n_eligible,
                "scans_ineligible": n_ineligible,
                "scans_unknown": n_unknown,
                "selected": winner,
                "selection_criterion": criterion,
                "all_scans": scans,
            }
        )
    return selected


def build_goal_intensity_today_cohort(
    db: Session,
    *,
    date_from: date,
    date_to: date,
    competition_id: int | None = None,
) -> GoalIntensityTodayCohort:
    effective_from, effective_to, clamped, error, warnings = normalize_goal_intensity_scan_range(
        date_from, date_to
    )
    empty = GoalIntensityTodayCohort(
        date_from=effective_from,
        date_to=effective_to,
        date_from_clamped=clamped,
        warnings=list(warnings),
        error=error,
        today_rows_raw=[],
        targets=[],
        eligible_pending=[],
        eligible_unresolved=[],
        eligibility_diagnostics={},
        diagnostic_examples=[],
        local_fixtures=[],
        selected_today_rows=[],
    )
    if error:
        empty.eligibility_diagnostics = {
            "today_rows_raw": 0,
            "today_unique_matches": 0,
            "today_eligible_matches": 0,
            "today_ineligible_matches": 0,
            "today_eligibility_unknown": 0,
            "eligible_finished_matches": 0,
            "eligible_pending_matches": 0,
            "eligible_unresolved_matches": 0,
            "eligible_feature_safe_matches": None,
            "eligible_identity_excluded_matches": None,
            "ineligible_by_reason": {},
            "ineligible_by_competition": {},
            "ineligible_by_scan_date": {},
            "range_error": error,
        }
        return empty

    raw = load_today_scans_for_goal_intensity(
        db,
        date_from=effective_from,
        date_to=effective_to,
        competition_id=competition_id,
    )
    classified = [classify_today_eligibility(r) for r in raw]
    groups = select_eligible_match_groups(classified)

    # Resolve local fixtures in batch
    local_ids = {
        int(s.row.local_fixture_id)
        for g in groups
        if (s := g["selected"]) is not None and s.row.local_fixture_id is not None
    }
    # Also for pending eligible with local id but no pre-kickoff selection? Only selected winners.
    fixtures_by_id: dict[int, Fixture] = {}
    if local_ids:
        for fx in db.scalars(select(Fixture).where(Fixture.id.in_(list(local_ids)))).all():
            fixtures_by_id[int(fx.id)] = fx

    targets: list[GoalIntensityTarget] = []
    pending: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []
    seen_local: set[int] = set()

    ineligible_by_reason: Counter[str] = Counter()
    ineligible_by_competition: Counter[str] = Counter()
    ineligible_by_scan_date: Counter[str] = Counter()
    diagnostic_examples: list[dict[str, Any]] = []

    n_eligible_matches = 0
    n_ineligible_matches = 0
    n_unknown_matches = 0
    for g in groups:
        if g["scans_eligible"] > 0:
            n_eligible_matches += 1
        elif g["scans_unknown"] > 0:
            n_unknown_matches += 1
        else:
            n_ineligible_matches += 1

    for c in classified:
        if c.eligibility_status == "ineligible":
            reason = c.eligibility_reason_codes[0] if c.eligibility_reason_codes else "ineligible"
            ineligible_by_reason[reason] += 1
            comp = str(c.row.competition_id if c.row.competition_id is not None else "unknown")
            ineligible_by_competition[comp] += 1
            sd = c.row.scan_date.isoformat() if c.row.scan_date else "unknown"
            ineligible_by_scan_date[sd] += 1
            if len(diagnostic_examples) < _MAX_DIAGNOSTIC_EXAMPLES:
                diagnostic_examples.append(_diagnostic_example(c))
        elif c.eligibility_status == "unknown":
            if len(diagnostic_examples) < _MAX_DIAGNOSTIC_EXAMPLES:
                diagnostic_examples.append(_diagnostic_example(c))

    for g in groups:
        selected: ClassifiedTodayScan | None = g["selected"]
        key = g["group_key"]
        if selected is None:
            # Match senza snapshot eligible pre-kickoff: se ha scansioni eligible
            # ma non pre-kickoff → unresolved/pending diagnostica
            if g["scans_eligible"] > 0:
                any_eligible = next(s for s in g["all_scans"] if s.eligibility_status == "eligible")
                lid = any_eligible.row.local_fixture_id
                fx = fixtures_by_id.get(int(lid)) if lid is not None else None
                # May need to load fixture if not in batch
                if lid is not None and fx is None:
                    fx = db.get(Fixture, int(lid))
                    if fx is not None:
                        fixtures_by_id[int(lid)] = fx
                res = _fixture_resolution(fx)
                payload = {
                    **_diagnostic_example(any_eligible),
                    "selection_criterion": g["selection_criterion"],
                    "scans_total": g["scans_total"],
                    "scans_eligible": g["scans_eligible"],
                    "fixture_resolution": res,
                }
                if res == "pending":
                    pending.append(payload)
                else:
                    unresolved.append(payload)
            continue

        lid = selected.row.local_fixture_id
        if lid is None:
            unresolved.append(
                {
                    **_diagnostic_example(selected),
                    "selection_criterion": g["selection_criterion"],
                    "scans_total": g["scans_total"],
                    "scans_eligible": g["scans_eligible"],
                    "fixture_resolution": "unresolved",
                }
            )
            continue

        lid_i = int(lid)
        fx = fixtures_by_id.get(lid_i)
        if fx is None:
            fx = db.get(Fixture, lid_i)
            if fx is not None:
                fixtures_by_id[lid_i] = fx
        res = _fixture_resolution(fx)
        selection_meta = {
            "scans_total": g["scans_total"],
            "scans_eligible": g["scans_eligible"],
            "scans_ineligible": g["scans_ineligible"],
            "scans_unknown": g["scans_unknown"],
            "selected_today_fixture_id": int(selected.row.id),
            "selection_criterion": g["selection_criterion"],
            "group_key": list(key),
        }
        if res == "finished" and fx is not None:
            if lid_i in seen_local:
                continue
            seen_local.add(lid_i)
            assert selected.row.scan_date is not None
            assert selected.row.scan_date >= MIN_GOAL_INTENSITY_TODAY_SCAN_DATE
            targets.append(
                GoalIntensityTarget(
                    today_row=selected.row,
                    local_fixture=fx,
                    eligibility_status="eligible",
                    eligibility_source=selected.eligibility_source,
                    eligibility_reason_codes=list(selected.eligibility_reason_codes),
                    scan_date=selected.row.scan_date,
                    selection=selection_meta,
                )
            )
        elif res == "pending":
            pending.append(
                {
                    **_diagnostic_example(selected),
                    **selection_meta,
                    "fixture_resolution": "pending",
                }
            )
        else:
            unresolved.append(
                {
                    **_diagnostic_example(selected),
                    **selection_meta,
                    "fixture_resolution": "unresolved",
                }
            )

    unique_matches = len(groups)
    diagnostics = {
        "today_rows_raw": len(raw),
        "today_unique_matches": unique_matches,
        "today_eligible_matches": n_eligible_matches,
        "today_ineligible_matches": n_ineligible_matches,
        "today_eligibility_unknown": n_unknown_matches,
        "eligible_finished_matches": len(targets),
        "eligible_pending_matches": len(pending),
        "eligible_unresolved_matches": len(unresolved),
        "eligible_feature_safe_matches": None,  # filled by caller after feature loop
        "eligible_identity_excluded_matches": None,
        "ineligible_by_reason": dict(sorted(ineligible_by_reason.items(), key=lambda x: (-x[1], x[0]))[:40]),
        "ineligible_by_competition": dict(
            sorted(ineligible_by_competition.items(), key=lambda x: (-x[1], x[0]))[:40]
        ),
        "ineligible_by_scan_date": dict(sorted(ineligible_by_scan_date.items())),
        "date_from_effective": effective_from.isoformat(),
        "date_to_effective": effective_to.isoformat(),
        "date_from_clamped": clamped,
        "min_scan_date": MIN_GOAL_INTENSITY_TODAY_SCAN_DATE.isoformat(),
        "cohort_basis": COHORT_BASIS,
        "target_source": TARGET_SOURCE,
        "result_source": RESULT_SOURCE,
        "historical_feature_source": HISTORICAL_FEATURE_SOURCE,
        "eligibility_source": ELIGIBILITY_SOURCE_PERSISTED,
    }

    return GoalIntensityTodayCohort(
        date_from=effective_from,
        date_to=effective_to,
        date_from_clamped=clamped,
        warnings=list(warnings),
        error=None,
        today_rows_raw=raw,
        targets=targets,
        eligible_pending=pending,
        eligible_unresolved=unresolved,
        eligibility_diagnostics=diagnostics,
        diagnostic_examples=diagnostic_examples,
        local_fixtures=[t.local_fixture for t in targets],
        selected_today_rows=[t.today_row for t in targets],
    )


def build_ineligible_diagnostics_rows(cohort: GoalIntensityTodayCohort) -> list[dict[str, Any]]:
    """Righe CSV diagnostiche (non model-ready)."""
    return list(cohort.diagnostic_examples)
