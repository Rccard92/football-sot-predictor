"""Alias Discovery V2: kickoff profile + anchor + bootstrap (zero DB / TEAM_ALIASES)."""

from __future__ import annotations

import csv
import json
import logging
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any

from app.services.cecchino_data_lab.bet365_enrichment.constants import (
    ALIAS_V2_MAX_BOOTSTRAP_ITERATIONS,
    ALIAS_V2_MIN_DISTINCT_DATES,
    ALIAS_V2_MIN_DISTINCT_FIXTURES,
    KICKOFF_CALIBRATED_TOLERANCE_MINUTES,
    KICKOFF_PROFILE_MIN_MODAL_SHARE,
    KICKOFF_PROFILE_MIN_SAMPLES,
    MATCH_STATUS_EXACT,
    MATCH_STATUS_NOT_FOUND,
    MATCH_STATUS_SAFE_ALIAS,
    MATCHED_STATUSES,
    RULE_TEMP_ALIAS,
)
from app.services.cecchino_data_lab.bet365_enrichment.matching import (
    CandidateIndex,
    LabMatchCandidate,
    MatchResult,
    find_schedule_candidates,
)
from app.services.cecchino_data_lab.bet365_enrichment.normalize import (
    _alias_lookup,
    normalize_name,
    team_names_equal,
)
from app.services.cecchino_data_lab.bet365_enrichment.team_aliases import TEAM_ALIASES

logger = logging.getLogger(__name__)

CONF_IDENTITY = "IDENTITY_CONFIRMED"
CONF_ANCHORED_HIGH = "ANCHORED_HIGH_CONFIDENCE"
CONF_SCHEDULE_ONLY = "SCHEDULE_ONLY"
CONF_LOW = "LOW_EVIDENCE"
CONF_CONFLICT = "CONFLICT"
CONF_CONFLICT_STATIC = "CONFLICT_WITH_STATIC_ALIAS"
CONF_NOT_RESOLVED = "NOT_RESOLVED"

SCHEDULE_NONE = "NO_SCHEDULE_CANDIDATE"
SCHEDULE_MULTI = "MULTIPLE_SCHEDULE_CANDIDATES"
SCHEDULE_NO_ANCHOR = "SCHEDULE_NO_ANCHOR"

PROFILE_COLUMNS = [
    "competition_name",
    "season",
    "modal_delta_minutes",
    "sample_count",
    "modal_count",
    "modal_share",
    "trusted",
]

SUGGESTION_COLUMNS = [
    "csv_team_name",
    "db_team_name",
    "evidence_count",
    "distinct_fixture_count",
    "distinct_dates",
    "competitions",
    "seasons",
    "bootstrap_iteration",
    "anchor_side_counts",
    "kickoff_profile_used",
    "confidence_status",
]

UNRESOLVED_COLUMNS = [
    "source_match_id",
    "schedule_status",
    "competition_name",
    "season",
    "csv_home_team",
    "csv_away_team",
    "csv_kickoff_utc",
    "candidate_count",
    "candidate_ids",
    "kickoff_profile_used",
]


@dataclass
class KickoffDeltaProfile:
    competition_name: str
    season: str
    competition_norm: str
    season_key: str
    modal_delta_minutes: int
    sample_count: int
    modal_count: int
    modal_share: float
    trusted: bool


@dataclass
class AnchoredEvidence:
    csv_team_raw: str
    db_team_raw: str
    competition: str
    season: str
    source_match_id: str
    lab_match_id: int
    kickoff_delta_minutes: int | None
    kickoff_sort: datetime | None
    anchor_side: str  # "home" | "away" | "both"
    bootstrap_iteration: int
    kickoff_profile_used: str  # "trusted" | "fallback_120"


@dataclass
class ScheduleUnresolvedRow:
    source_match_id: str
    schedule_status: str
    competition_name: str
    season: str
    csv_home_team: str
    csv_away_team: str
    csv_kickoff_utc: str
    candidate_count: int
    candidate_ids: list[int]
    kickoff_profile_used: str


@dataclass
class AliasDiscoveryV2Result:
    profiles: list[KickoffDeltaProfile] = field(default_factory=list)
    suggestions: list[dict[str, Any]] = field(default_factory=list)
    conflicts: list[dict[str, Any]] = field(default_factory=list)
    schedule_unresolved: list[ScheduleUnresolvedRow] = field(default_factory=list)
    trusted_aliases: dict[str, str] = field(default_factory=dict)  # display csv -> db
    trusted_aliases_norm: dict[str, str] = field(default_factory=dict)  # csv_norm -> db_display
    conflict_with_static: list[dict[str, Any]] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)
    simulation_summary: dict[str, Any] = field(default_factory=dict)
    simulated_results: list[MatchResult] = field(default_factory=list)
    bootstrap_iterations: int = 0


def _display(raw: str | None) -> str:
    return str(raw or "").strip()


def _season_key_from_matched(cand: LabMatchCandidate) -> str:
    if cand.start_year is not None:
        return str(cand.start_year)
    return normalize_name(cand.season_label) or ""


def _season_key_from_csv(row: Any) -> str:
    if getattr(row, "season_start_year", None) is not None:
        return str(row.season_start_year)
    return normalize_name(getattr(row, "season", None)) or ""


def _profile_key(competition_norm: str, season_key: str) -> tuple[str, str]:
    return (competition_norm, season_key)


def build_kickoff_delta_profiles(
    results: list[MatchResult],
) -> list[KickoffDeltaProfile]:
    """Distribuzione kickoff_delta da MatchResult EXACT + SAFE_ALIAS."""
    buckets: dict[tuple[str, str], list[int]] = defaultdict(list)
    meta: dict[tuple[str, str], tuple[str, str]] = {}

    for result in results:
        if result.match_status not in MATCHED_STATUSES:
            continue
        if result.matched is None or result.kickoff_delta_minutes is None:
            continue
        cand = result.matched
        comp_norm = normalize_name(cand.competition_name)
        season_key = _season_key_from_matched(cand)
        if not comp_norm or not season_key:
            continue
        key = _profile_key(comp_norm, season_key)
        buckets[key].append(int(result.kickoff_delta_minutes))
        if key not in meta:
            meta[key] = (
                _display(cand.competition_name),
                _display(cand.season_label) or season_key,
            )

    profiles: list[KickoffDeltaProfile] = []
    for key, deltas in sorted(buckets.items()):
        counter = Counter(deltas)
        modal_delta, modal_count = counter.most_common(1)[0]
        sample_count = len(deltas)
        modal_share = modal_count / sample_count if sample_count else 0.0
        trusted = (
            sample_count >= KICKOFF_PROFILE_MIN_SAMPLES
            and modal_share >= KICKOFF_PROFILE_MIN_MODAL_SHARE
        )
        comp_name, season_label = meta[key]
        profiles.append(
            KickoffDeltaProfile(
                competition_name=comp_name,
                season=season_label,
                competition_norm=key[0],
                season_key=key[1],
                modal_delta_minutes=int(modal_delta),
                sample_count=sample_count,
                modal_count=modal_count,
                modal_share=round(modal_share, 4),
                trusted=trusted,
            )
        )
    return profiles


def _profiles_by_key(
    profiles: list[KickoffDeltaProfile],
) -> dict[tuple[str, str], KickoffDeltaProfile]:
    return {_profile_key(p.competition_norm, p.season_key): p for p in profiles}


def lookup_kickoff_profile(
    csv_row: Any,
    profiles_by_key: dict[tuple[str, str], KickoffDeltaProfile],
) -> KickoffDeltaProfile | None:
    season_key = _season_key_from_csv(csv_row)
    if not season_key:
        return None
    for raw_comp in (csv_row.competition_name, csv_row.competition_api_name):
        comp_norm = normalize_name(raw_comp)
        if not comp_norm:
            continue
        profile = profiles_by_key.get(_profile_key(comp_norm, season_key))
        if profile is not None:
            return profile
    return None


def delta_window_for_profile(
    profile: KickoffDeltaProfile | None,
) -> tuple[tuple[int, int] | None, str]:
    """Returns (delta_window, profile_used_label).

    Trusted → modal ± 10. Non trusted / assente → None (±120 fallback).
    """
    if profile is not None and profile.trusted:
        tol = KICKOFF_CALIBRATED_TOLERANCE_MINUTES
        modal = profile.modal_delta_minutes
        return (modal - tol, modal + tol), "trusted"
    return None, "fallback_120"


def _side_anchored(
    csv_team: str | None,
    db_team: str | None,
    *,
    extra_aliases: dict[str, str] | None,
) -> bool:
    matched, _, _ = team_names_equal(
        csv_team, db_team, extra_aliases=extra_aliases
    )
    return matched


def _static_alias_target(csv_team: str | None) -> str | None:
    return _alias_lookup(csv_team, TEAM_ALIASES)


def _conflicts_with_static(
    csv_team: str,
    db_team: str,
) -> bool:
    """True se TEAM_ALIASES ha già una chiave per csv con target diverso da db."""
    static = _static_alias_target(csv_team)
    if static is None:
        # Anche match per chiave normalizzata: se csv_norm è chiave statica
        csv_norm = normalize_name(csv_team)
        for key, target in TEAM_ALIASES.items():
            if normalize_name(key) == csv_norm:
                return normalize_name(target) != normalize_name(db_team)
        return False
    return normalize_name(static) != normalize_name(db_team)


def _fixture_date(ko: datetime | None) -> date | None:
    if ko is None:
        return None
    if ko.tzinfo is None:
        return ko.date()
    return ko.date()


def collect_anchored_pass(
    not_found: list[MatchResult],
    *,
    index: CandidateIndex,
    profiles_by_key: dict[tuple[str, str], KickoffDeltaProfile],
    extra_aliases: dict[str, str],
    bootstrap_iteration: int,
) -> tuple[
    list[AnchoredEvidence],
    list[dict[str, Any]],
    list[ScheduleUnresolvedRow],
    set[str],
]:
    """Un pass bootstrap: evidence anchored + schedule-only + unresolved.

    ``identity_anchor_norms``: csv norms con identity pura sulla *unica*
    fixture anchored selezionata (len==1). Mai da 0/>1 anchored o unresolved.
    """
    evidences: list[AnchoredEvidence] = []
    schedule_only_pairs: list[dict[str, Any]] = []
    unresolved: list[ScheduleUnresolvedRow] = []
    identity_anchor_norms: set[str] = set()

    for result in not_found:
        row = result.csv_row
        profile = lookup_kickoff_profile(row, profiles_by_key)
        delta_window, profile_used = delta_window_for_profile(profile)
        pool = index.lookup(row)
        schedule = find_schedule_candidates(row, pool, delta_window=delta_window)

        if len(schedule) == 0:
            unresolved.append(
                ScheduleUnresolvedRow(
                    source_match_id=row.source_match_id,
                    schedule_status=SCHEDULE_NONE,
                    competition_name=_display(row.competition_name),
                    season=_display(row.season),
                    csv_home_team=_display(row.home_team),
                    csv_away_team=_display(row.away_team),
                    csv_kickoff_utc=(
                        row.kickoff_utc.isoformat() if row.kickoff_utc else ""
                    ),
                    candidate_count=0,
                    candidate_ids=[],
                    kickoff_profile_used=profile_used,
                )
            )
            continue

        anchored = [
            (cand, delta)
            for cand, delta in schedule
            if _side_anchored(
                row.home_team, cand.home_team, extra_aliases=extra_aliases
            )
            or _side_anchored(
                row.away_team, cand.away_team, extra_aliases=extra_aliases
            )
        ]

        if len(anchored) == 0:
            if len(schedule) == 1:
                cand, delta = schedule[0]
                competition = cand.competition_name or _display(row.competition_name)
                season = cand.season_label or _display(row.season)
                schedule_only_pairs.append(
                    {
                        "csv_home": _display(row.home_team),
                        "db_home": _display(cand.home_team),
                        "csv_away": _display(row.away_team),
                        "db_away": _display(cand.away_team),
                        "competition": competition,
                        "season": season,
                        "source_match_id": row.source_match_id,
                        "lab_match_id": cand.id,
                        "kickoff_delta_minutes": delta,
                        "kickoff_sort": row.kickoff_utc,
                        "kickoff_profile_used": profile_used,
                        "bootstrap_iteration": bootstrap_iteration,
                    }
                )
                unresolved.append(
                    ScheduleUnresolvedRow(
                        source_match_id=row.source_match_id,
                        schedule_status=SCHEDULE_NO_ANCHOR,
                        competition_name=_display(row.competition_name),
                        season=_display(row.season),
                        csv_home_team=_display(row.home_team),
                        csv_away_team=_display(row.away_team),
                        csv_kickoff_utc=(
                            row.kickoff_utc.isoformat() if row.kickoff_utc else ""
                        ),
                        candidate_count=1,
                        candidate_ids=[cand.id],
                        kickoff_profile_used=profile_used,
                    )
                )
            else:
                unresolved.append(
                    ScheduleUnresolvedRow(
                        source_match_id=row.source_match_id,
                        schedule_status=SCHEDULE_MULTI,
                        competition_name=_display(row.competition_name),
                        season=_display(row.season),
                        csv_home_team=_display(row.home_team),
                        csv_away_team=_display(row.away_team),
                        csv_kickoff_utc=(
                            row.kickoff_utc.isoformat() if row.kickoff_utc else ""
                        ),
                        candidate_count=len(schedule),
                        candidate_ids=[c.id for c, _ in schedule[:20]],
                        kickoff_profile_used=profile_used,
                    )
                )
            continue

        if len(anchored) > 1:
            unresolved.append(
                ScheduleUnresolvedRow(
                    source_match_id=row.source_match_id,
                    schedule_status=SCHEDULE_MULTI,
                    competition_name=_display(row.competition_name),
                    season=_display(row.season),
                    csv_home_team=_display(row.home_team),
                    csv_away_team=_display(row.away_team),
                    csv_kickoff_utc=(
                        row.kickoff_utc.isoformat() if row.kickoff_utc else ""
                    ),
                    candidate_count=len(schedule),
                    candidate_ids=[c.id for c, _ in schedule[:20]],
                    kickoff_profile_used=profile_used,
                )
            )
            continue

        # Esattamente una fixture anchored selezionata
        cand, delta = anchored[0]
        for csv_t, db_t in (
            (_display(row.home_team), _display(cand.home_team)),
            (_display(row.away_team), _display(cand.away_team)),
        ):
            csv_norm = normalize_name(csv_t)
            if csv_norm and csv_norm == normalize_name(db_t):
                identity_anchor_norms.add(csv_norm)

        home_anchor = _side_anchored(
            row.home_team, cand.home_team, extra_aliases=extra_aliases
        )
        away_anchor = _side_anchored(
            row.away_team, cand.away_team, extra_aliases=extra_aliases
        )

        competition = cand.competition_name or _display(row.competition_name)
        season = cand.season_label or _display(row.season)

        if home_anchor and away_anchor:
            anchor_side = "both"
        elif home_anchor:
            anchor_side = "home"
        else:
            anchor_side = "away"

        pairs: list[tuple[str, str, str]] = []
        if home_anchor and not away_anchor:
            pairs.append((_display(row.away_team), _display(cand.away_team), "home"))
        elif away_anchor and not home_anchor:
            pairs.append((_display(row.home_team), _display(cand.home_team), "away"))
        else:
            for csv_t, db_t, side in (
                (_display(row.home_team), _display(cand.home_team), "home"),
                (_display(row.away_team), _display(cand.away_team), "away"),
            ):
                if csv_t and normalize_name(csv_t) != normalize_name(db_t):
                    pairs.append((csv_t, db_t, side))

        if not pairs and (home_anchor or away_anchor):
            for csv_t, db_t in (
                (_display(row.home_team), _display(cand.home_team)),
                (_display(row.away_team), _display(cand.away_team)),
            ):
                if csv_t and normalize_name(csv_t) == normalize_name(db_t):
                    evidences.append(
                        AnchoredEvidence(
                            csv_team_raw=csv_t,
                            db_team_raw=db_t,
                            competition=competition,
                            season=season,
                            source_match_id=row.source_match_id,
                            lab_match_id=cand.id,
                            kickoff_delta_minutes=delta,
                            kickoff_sort=row.kickoff_utc,
                            anchor_side=anchor_side,
                            bootstrap_iteration=bootstrap_iteration,
                            kickoff_profile_used=profile_used,
                        )
                    )

        for csv_t, db_t, _side in pairs:
            if not csv_t or not db_t:
                continue
            evidences.append(
                AnchoredEvidence(
                    csv_team_raw=csv_t,
                    db_team_raw=db_t,
                    competition=competition,
                    season=season,
                    source_match_id=row.source_match_id,
                    lab_match_id=cand.id,
                    kickoff_delta_minutes=delta,
                    kickoff_sort=row.kickoff_utc,
                    anchor_side=anchor_side,
                    bootstrap_iteration=bootstrap_iteration,
                    kickoff_profile_used=profile_used,
                )
            )

    return evidences, schedule_only_pairs, unresolved, identity_anchor_norms


def _aggregate_for_promotion(
    evidences: list[AnchoredEvidence],
) -> dict[str, dict[str, Any]]:
    """csv_norm -> aggregation stats (solo evidence non-identity)."""
    by_csv: dict[str, list[AnchoredEvidence]] = defaultdict(list)
    for ev in evidences:
        csv_norm = normalize_name(ev.csv_team_raw)
        db_norm = normalize_name(ev.db_team_raw)
        if not csv_norm or not db_norm:
            continue
        if csv_norm == db_norm:
            continue
        by_csv[csv_norm].append(ev)

    out: dict[str, dict[str, Any]] = {}
    for csv_norm, evs in by_csv.items():
        by_db: dict[str, list[AnchoredEvidence]] = defaultdict(list)
        for ev in evs:
            by_db[normalize_name(ev.db_team_raw)].append(ev)
        out[csv_norm] = {
            "by_db": by_db,
            "evs": evs,
            "csv_display": evs[0].csv_team_raw,
        }
    return out


def _promote_trusted(
    agg: dict[str, dict[str, Any]],
    *,
    existing_norm: dict[str, str],
    iteration: int,
) -> tuple[dict[str, str], list[dict[str, Any]], list[dict[str, Any]]]:
    """Promuove alias TRUSTED; segnala CONFLICT_WITH_STATIC.

    Returns:
        new_aliases (display csv -> db), conflict_static rows, suggestion rows for this pass
    """
    new_aliases: dict[str, str] = {}
    conflict_static: list[dict[str, Any]] = []
    rows: list[dict[str, Any]] = []

    for csv_norm, payload in sorted(agg.items()):
        by_db: dict[str, list[AnchoredEvidence]] = payload["by_db"]
        csv_display = payload["csv_display"]
        distinct_targets = len(by_db)

        for db_norm, db_evs in sorted(by_db.items(), key=lambda x: (-len(x[1]), x[0])):
            fixtures = {e.lab_match_id for e in db_evs}
            dates = {
                d
                for e in db_evs
                if (d := _fixture_date(e.kickoff_sort)) is not None
            }
            competitions = sorted({e.competition for e in db_evs if e.competition})
            seasons = sorted({e.season for e in db_evs if e.season})
            side_counts = Counter(e.anchor_side for e in db_evs)
            profile_used = Counter(e.kickoff_profile_used for e in db_evs).most_common(1)[
                0
            ][0]
            db_display = db_evs[0].db_team_raw
            evidence_count = len(db_evs)
            distinct_fixture_count = len(fixtures)
            distinct_dates = len(dates)
            min_iter = min(e.bootstrap_iteration for e in db_evs)

            if _conflicts_with_static(csv_display, db_display):
                status = CONF_CONFLICT_STATIC
                conflict_static.append(
                    {
                        "csv_team_name": csv_norm,
                        "db_team_name": db_display,
                        "static_target": _static_alias_target(csv_display)
                        or next(
                            (
                                TEAM_ALIASES[k]
                                for k in TEAM_ALIASES
                                if normalize_name(k) == csv_norm
                            ),
                            "",
                        ),
                        "evidence_count": evidence_count,
                        "confidence_status": status,
                    }
                )
            elif distinct_targets > 1:
                status = CONF_CONFLICT
            elif (
                distinct_fixture_count >= ALIAS_V2_MIN_DISTINCT_FIXTURES
                and distinct_dates >= ALIAS_V2_MIN_DISTINCT_DATES
            ):
                status = CONF_ANCHORED_HIGH
            else:
                status = CONF_LOW

            row = {
                "csv_team_name": csv_norm,
                "db_team_name": db_display,
                "evidence_count": evidence_count,
                "distinct_fixture_count": distinct_fixture_count,
                "distinct_dates": distinct_dates,
                "competitions": "|".join(competitions),
                "seasons": "|".join(seasons),
                "bootstrap_iteration": min_iter if status != CONF_ANCHORED_HIGH else iteration,
                "anchor_side_counts": dict(side_counts),
                "kickoff_profile_used": profile_used,
                "confidence_status": status,
            }
            # Preferisci iteration di prima promozione HIGH
            if status == CONF_ANCHORED_HIGH:
                row["bootstrap_iteration"] = iteration

            rows.append(row)

            if status == CONF_ANCHORED_HIGH and csv_norm not in existing_norm:
                # Overlay keyed by display name (come TEAM_ALIASES)
                new_aliases[csv_display] = db_display

    return new_aliases, conflict_static, rows


def _schedule_only_suggestions(
    schedule_only_pairs: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Aggrega pair schedule-only (senza anchor) → SCHEDULE_ONLY / identity."""
    by_csv: dict[str, list[tuple[str, dict[str, Any]]]] = defaultdict(list)
    for pair in schedule_only_pairs:
        for csv_t, db_t in (
            (pair["csv_home"], pair["db_home"]),
            (pair["csv_away"], pair["db_away"]),
        ):
            csv_norm = normalize_name(csv_t)
            db_norm = normalize_name(db_t)
            if not csv_norm or not db_norm or csv_norm == db_norm:
                continue
            by_csv[csv_norm].append((db_t, pair))

    rows: list[dict[str, Any]] = []
    for csv_norm, items in sorted(by_csv.items()):
        by_db: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for db_t, pair in items:
            by_db[normalize_name(db_t)].append(pair)
        for db_norm, pairs in sorted(by_db.items(), key=lambda x: (-len(x[1]), x[0])):
            fixtures = {p["lab_match_id"] for p in pairs}
            dates = {
                d
                for p in pairs
                if (d := _fixture_date(p.get("kickoff_sort"))) is not None
            }
            competitions = sorted({p["competition"] for p in pairs if p["competition"]})
            seasons = sorted({p["season"] for p in pairs if p["season"]})
            db_display = next(
                db_t for db_t, p in items if normalize_name(db_t) == db_norm
            )
            csv_display = next(
                (p["csv_home"] if normalize_name(p["csv_home"]) == csv_norm else p["csv_away"])
                for p in pairs
            )
            rows.append(
                {
                    "csv_team_name": csv_norm,
                    "db_team_name": db_display,
                    "evidence_count": len(pairs),
                    "distinct_fixture_count": len(fixtures),
                    "distinct_dates": len(dates),
                    "competitions": "|".join(competitions),
                    "seasons": "|".join(seasons),
                    "bootstrap_iteration": 0,
                    "anchor_side_counts": {},
                    "kickoff_profile_used": pairs[0]["kickoff_profile_used"],
                    "confidence_status": CONF_SCHEDULE_ONLY,
                }
            )
    return rows


def run_bootstrap(
    results: list[MatchResult],
    *,
    index: CandidateIndex,
    profiles: list[KickoffDeltaProfile],
) -> tuple[
    dict[str, str],
    dict[str, str],
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[ScheduleUnresolvedRow],
    list[dict[str, Any]],
    int,
    set[str],
]:
    """Bootstrap iterativo.

    Returns:
        trusted_display, trusted_norm, suggestions, conflicts, unresolved,
        conflict_static, iterations_run, identity_anchor_norms
    """
    profiles_by_key = _profiles_by_key(profiles)
    not_found = [r for r in results if r.match_status == MATCH_STATUS_NOT_FOUND]

    trusted_display: dict[str, str] = {}  # csv display -> db display
    trusted_norm: dict[str, str] = {}  # csv_norm -> db display
    all_anchored_evs: list[AnchoredEvidence] = []
    all_schedule_only: list[dict[str, Any]] = []
    last_unresolved: list[ScheduleUnresolvedRow] = []
    all_conflict_static: list[dict[str, Any]] = []
    suggestion_by_key: dict[tuple[str, str], dict[str, Any]] = {}
    identity_anchor_norms: set[str] = set()

    iterations_run = 0
    for iteration in range(1, ALIAS_V2_MAX_BOOTSTRAP_ITERATIONS + 1):
        iterations_run = iteration
        evidences, schedule_only, unresolved, pass_identity = collect_anchored_pass(
            not_found,
            index=index,
            profiles_by_key=profiles_by_key,
            extra_aliases=trusted_display,
            bootstrap_iteration=iteration,
        )
        identity_anchor_norms |= pass_identity
        last_unresolved = unresolved
        if iteration == 1:
            all_schedule_only = schedule_only
        all_anchored_evs.extend(evidences)

        agg = _aggregate_for_promotion(evidences)
        new_aliases, conflict_static, rows = _promote_trusted(
            agg, existing_norm=trusted_norm, iteration=iteration
        )
        all_conflict_static.extend(conflict_static)

        for row in rows:
            key = (row["csv_team_name"], normalize_name(row["db_team_name"]))
            prev = suggestion_by_key.get(key)
            if prev is None:
                suggestion_by_key[key] = row
            else:
                # Conserva ANCHORED_HIGH se già raggiunto; aggiorna counts
                if prev["confidence_status"] != CONF_ANCHORED_HIGH:
                    suggestion_by_key[key] = row
                elif row["confidence_status"] == CONF_ANCHORED_HIGH:
                    # merge counts upward
                    suggestion_by_key[key] = {
                        **row,
                        "bootstrap_iteration": prev["bootstrap_iteration"],
                    }

        added = 0
        for csv_disp, db_disp in new_aliases.items():
            csv_norm = normalize_name(csv_disp)
            if csv_norm in trusted_norm:
                continue
            if _conflicts_with_static(csv_disp, db_disp):
                continue
            trusted_display[csv_disp] = db_disp
            trusted_norm[csv_norm] = db_disp
            added += 1

        logger.info(
            "alias-v2 bootstrap iter=%d evidence=%d new_trusted=%d total_trusted=%d",
            iteration,
            len(evidences),
            added,
            len(trusted_norm),
        )
        if added == 0:
            break

    # Re-aggregate ALL anchored evidence for final suggestion rows
    final_agg = _aggregate_for_promotion(all_anchored_evs)
    _, final_static, final_rows = _promote_trusted(
        final_agg, existing_norm={}, iteration=iterations_run
    )
    # Mark HIGH only if in trusted_norm
    for row in final_rows:
        csv_norm = row["csv_team_name"]
        db_norm = normalize_name(row["db_team_name"])
        if row["confidence_status"] == CONF_CONFLICT_STATIC:
            continue
        if csv_norm in trusted_norm and normalize_name(trusted_norm[csv_norm]) == db_norm:
            row["confidence_status"] = CONF_ANCHORED_HIGH
            # preserve first promotion iteration if known
            key = (csv_norm, db_norm)
            if key in suggestion_by_key:
                row["bootstrap_iteration"] = suggestion_by_key[key].get(
                    "bootstrap_iteration", row["bootstrap_iteration"]
                )
        elif row["confidence_status"] == CONF_ANCHORED_HIGH:
            # Should be in trusted — if filtered by static, demote
            if _conflicts_with_static(row["csv_team_name"], row["db_team_name"]):
                row["confidence_status"] = CONF_CONFLICT_STATIC

    schedule_rows = _schedule_only_suggestions(all_schedule_only)

    # Identity confirmed from anchored evidence
    identity_rows: list[dict[str, Any]] = []
    identity_norms: set[str] = set()
    for ev in all_anchored_evs:
        if normalize_name(ev.csv_team_raw) == normalize_name(ev.db_team_raw):
            n = normalize_name(ev.csv_team_raw)
            if n and n not in identity_norms:
                identity_norms.add(n)
                identity_rows.append(
                    {
                        "csv_team_name": n,
                        "db_team_name": ev.db_team_raw,
                        "evidence_count": 1,
                        "distinct_fixture_count": 1,
                        "distinct_dates": 1,
                        "competitions": ev.competition,
                        "seasons": ev.season,
                        "bootstrap_iteration": ev.bootstrap_iteration,
                        "anchor_side_counts": {ev.anchor_side: 1},
                        "kickoff_profile_used": ev.kickoff_profile_used,
                        "confidence_status": CONF_IDENTITY,
                    }
                )

    suggestions = final_rows + schedule_rows + identity_rows
    # Deduplicate: prefer ANCHORED_HIGH > CONFLICT* > LOW > SCHEDULE > IDENTITY
    rank = {
        CONF_ANCHORED_HIGH: 0,
        CONF_CONFLICT: 1,
        CONF_CONFLICT_STATIC: 1,
        CONF_LOW: 2,
        CONF_SCHEDULE_ONLY: 3,
        CONF_IDENTITY: 4,
    }
    best: dict[tuple[str, str], dict[str, Any]] = {}
    for row in suggestions:
        key = (row["csv_team_name"], normalize_name(row["db_team_name"]))
        prev = best.get(key)
        if prev is None or rank.get(row["confidence_status"], 9) < rank.get(
            prev["confidence_status"], 9
        ):
            best[key] = row
        elif (
            prev is not None
            and row["confidence_status"] == prev["confidence_status"]
            and int(row["evidence_count"]) > int(prev["evidence_count"])
        ):
            best[key] = row

    suggestions = list(best.values())
    suggestions.sort(
        key=lambda r: (
            rank.get(r["confidence_status"], 9),
            -int(r["evidence_count"]),
            r["csv_team_name"],
        )
    )
    conflicts = [
        r
        for r in suggestions
        if r["confidence_status"] in (CONF_CONFLICT, CONF_CONFLICT_STATIC)
    ]
    # Merge static conflicts from promote
    for cs in final_static + all_conflict_static:
        key = (cs["csv_team_name"], normalize_name(cs.get("db_team_name", "")))
        if not any(
            c["csv_team_name"] == key[0]
            and normalize_name(c["db_team_name"]) == key[1]
            for c in conflicts
        ):
            # Normalize to suggestion schema if needed
            if "distinct_fixture_count" not in cs:
                cs = {
                    "csv_team_name": cs["csv_team_name"],
                    "db_team_name": cs["db_team_name"],
                    "evidence_count": cs.get("evidence_count", 0),
                    "distinct_fixture_count": 0,
                    "distinct_dates": 0,
                    "competitions": "",
                    "seasons": "",
                    "bootstrap_iteration": 0,
                    "anchor_side_counts": {},
                    "kickoff_profile_used": "",
                    "confidence_status": CONF_CONFLICT_STATIC,
                }
            conflicts.append(cs)
            suggestions.append(cs)

    return (
        trusted_display,
        trusted_norm,
        suggestions,
        conflicts,
        last_unresolved,
        [c for c in conflicts if c["confidence_status"] == CONF_CONFLICT_STATIC],
        iterations_run,
        identity_anchor_norms,
    )


def build_audit_summary_v2(
    *,
    results: list[MatchResult],
    suggestions: list[dict[str, Any]],
    profiles: list[KickoffDeltaProfile],
    trusted_norm: dict[str, str],
    bootstrap_iterations: int,
    unresolved: list[ScheduleUnresolvedRow],
    identity_anchor_norms: set[str] | None = None,
) -> dict[str, Any]:
    analyzed: set[str] = set()
    for r in results:
        if r.match_status != MATCH_STATUS_NOT_FOUND:
            continue
        for name in (r.csv_row.home_team, r.csv_row.away_team):
            n = normalize_name(name)
            if n:
                analyzed.add(n)

    status_by_csv: dict[str, str] = {}
    for row in suggestions:
        csv_norm = row["csv_team_name"]
        st = row["confidence_status"]
        prev = status_by_csv.get(csv_norm)
        if prev is None:
            status_by_csv[csv_norm] = st
        elif st == CONF_ANCHORED_HIGH:
            status_by_csv[csv_norm] = CONF_ANCHORED_HIGH
        elif prev == CONF_ANCHORED_HIGH:
            continue
        elif st in (CONF_CONFLICT, CONF_CONFLICT_STATIC):
            status_by_csv[csv_norm] = st

    counts = Counter(status_by_csv.values())
    suggested = set(status_by_csv.keys())
    not_resolved = analyzed - suggested
    identity_norms = identity_anchor_norms or set()

    return {
        "unique_csv_team_names_analyzed": len(analyzed),
        "IDENTITY_CONFIRMED": len(identity_norms),
        "IDENTITY_CONFIRMED_means": (
            "unique_csv_team_norms_used_as_identity_anchors_on_selected_anchored_fixtures"
        ),
        "ANCHORED_HIGH_CONFIDENCE": counts.get(CONF_ANCHORED_HIGH, 0),
        "SCHEDULE_ONLY": counts.get(CONF_SCHEDULE_ONLY, 0),
        "LOW_EVIDENCE": counts.get(CONF_LOW, 0),
        "CONFLICT": counts.get(CONF_CONFLICT, 0),
        "CONFLICT_WITH_STATIC_ALIAS": counts.get(CONF_CONFLICT_STATIC, 0),
        "NOT_RESOLVED": len(not_resolved),
        "trusted_alias_count": len(trusted_norm),
        "bootstrap_iterations": bootstrap_iterations,
        "kickoff_profiles_total": len(profiles),
        "kickoff_profiles_trusted": sum(1 for p in profiles if p.trusted),
        "schedule_unresolved_rows": len(unresolved),
        "not_found_total": sum(
            1 for r in results if r.match_status == MATCH_STATUS_NOT_FOUND
        ),
        "db_writes": False,
        "team_aliases_modified": False,
        "discover_aliases": True,
        "alias_discovery_version": 2,
    }


def simulate_matching_with_temp_aliases(
    results: list[MatchResult],
    candidates: list[LabMatchCandidate],
    *,
    index: CandidateIndex,
    trusted_display: dict[str, str],
) -> tuple[dict[str, Any], list[MatchResult]]:
    """Riesegue matching in-memory con overlay V2. Non modifica TEAM_ALIASES.

    Restituisce (summary, simulated_results) per audit reporting side-effect-free.
    """
    from app.services.cecchino_data_lab.bet365_enrichment.dry_run import run_matching

    original_matched = sum(1 for r in results if r.match_status in MATCHED_STATUSES)
    csv_rows = [r.csv_row for r in results]

    sim_results, _ = run_matching(
        csv_rows,
        candidates,
        index=index,
        fuzzy_suggestions=False,
        extra_aliases=trusted_display or None,
    )

    exact = safe = ambiguous = not_found = temp_alias = 0
    for r in sim_results:
        if r.match_status == MATCH_STATUS_EXACT:
            exact += 1
        elif r.match_status == MATCH_STATUS_SAFE_ALIAS:
            safe += 1
            if r.matching_rule == RULE_TEMP_ALIAS or r.used_temp_alias:
                temp_alias += 1
        elif r.match_status == MATCH_STATUS_NOT_FOUND:
            not_found += 1
        else:
            ambiguous += 1

    simulated_matched = exact + safe
    total = len(results) or 1
    summary = {
        "original_matched": original_matched,
        "simulated_matched": simulated_matched,
        "simulated_matched_pct": round(100.0 * simulated_matched / total, 4),
        "recovered_matches": max(0, simulated_matched - original_matched),
        "EXACT": exact,
        "SAFE_ALIAS": safe,
        "TEMP_ALIAS": temp_alias,
        "AMBIGUOUS": ambiguous,
        "NOT_FOUND": not_found,
        "bet365_rows": len(results),
        "db_writes": False,
        "team_aliases_modified": False,
        "temp_aliases_applied": len(trusted_display),
    }
    return summary, sim_results


def run_alias_discovery_v2(
    results: list[MatchResult],
    candidates: list[LabMatchCandidate],
    *,
    index: CandidateIndex | None = None,
) -> AliasDiscoveryV2Result:
    idx = index if index is not None else CandidateIndex.build(candidates)
    profiles = build_kickoff_delta_profiles(results)

    (
        trusted_display,
        trusted_norm,
        suggestions,
        conflicts,
        unresolved,
        conflict_static,
        iterations,
        identity_anchor_norms,
    ) = run_bootstrap(results, index=idx, profiles=profiles)

    summary = build_audit_summary_v2(
        results=results,
        suggestions=suggestions,
        profiles=profiles,
        trusted_norm=trusted_norm,
        bootstrap_iterations=iterations,
        unresolved=unresolved,
        identity_anchor_norms=identity_anchor_norms,
    )
    simulation, sim_results = simulate_matching_with_temp_aliases(
        results,
        candidates,
        index=idx,
        trusted_display=trusted_display,
    )
    summary["simulation"] = {
        "recovered_matches": simulation["recovered_matches"],
        "simulated_matched_pct": simulation["simulated_matched_pct"],
    }

    return AliasDiscoveryV2Result(
        profiles=profiles,
        suggestions=suggestions,
        conflicts=conflicts,
        schedule_unresolved=unresolved,
        trusted_aliases=trusted_display,
        trusted_aliases_norm=trusted_norm,
        conflict_with_static=conflict_static,
        summary=summary,
        simulation_summary=simulation,
        simulated_results=sim_results,
        bootstrap_iterations=iterations,
    )


def write_alias_discovery_v2_reports(
    output_dir: str | Path,
    discovery: AliasDiscoveryV2Result,
) -> dict[str, str]:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    profiles_path = out / "kickoff_delta_profiles.csv"
    suggestions_path = out / "alias_suggestions_v2.csv"
    conflicts_path = out / "alias_conflicts_v2.csv"
    unresolved_path = out / "schedule_unresolved_v2.csv"
    audit_path = out / "alias_audit_summary_v2.json"
    sim_path = out / "alias_v2_simulation_summary.json"

    with profiles_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=PROFILE_COLUMNS)
        writer.writeheader()
        for p in discovery.profiles:
            writer.writerow(
                {
                    "competition_name": p.competition_name,
                    "season": p.season,
                    "modal_delta_minutes": p.modal_delta_minutes,
                    "sample_count": p.sample_count,
                    "modal_count": p.modal_count,
                    "modal_share": p.modal_share,
                    "trusted": str(p.trusted).lower(),
                }
            )

    def _row_out(row: dict[str, Any]) -> dict[str, Any]:
        out_row = {k: row.get(k, "") for k in SUGGESTION_COLUMNS}
        asc = out_row.get("anchor_side_counts")
        if isinstance(asc, dict):
            out_row["anchor_side_counts"] = "|".join(
                f"{k}:{v}" for k, v in sorted(asc.items())
            )
        return out_row

    with suggestions_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=SUGGESTION_COLUMNS)
        writer.writeheader()
        for row in discovery.suggestions:
            writer.writerow(_row_out(row))

    with conflicts_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=SUGGESTION_COLUMNS)
        writer.writeheader()
        for row in discovery.conflicts:
            writer.writerow(_row_out(row))

    with unresolved_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=UNRESOLVED_COLUMNS)
        writer.writeheader()
        for row in discovery.schedule_unresolved:
            writer.writerow(
                {
                    "source_match_id": row.source_match_id,
                    "schedule_status": row.schedule_status,
                    "competition_name": row.competition_name,
                    "season": row.season,
                    "csv_home_team": row.csv_home_team,
                    "csv_away_team": row.csv_away_team,
                    "csv_kickoff_utc": row.csv_kickoff_utc,
                    "candidate_count": row.candidate_count,
                    "candidate_ids": "|".join(str(i) for i in row.candidate_ids),
                    "kickoff_profile_used": row.kickoff_profile_used,
                }
            )

    audit_path.write_text(
        json.dumps(discovery.summary, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    sim_path.write_text(
        json.dumps(discovery.simulation_summary, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    from app.services.cecchino_data_lab.bet365_enrichment.team_mapping_audit_v2 import (
        write_team_mapping_audit_v2_reports,
    )

    audit_paths = write_team_mapping_audit_v2_reports(out, discovery)

    return {
        "kickoff_delta_profiles_csv": str(profiles_path),
        "alias_suggestions_v2_csv": str(suggestions_path),
        "alias_conflicts_v2_csv": str(conflicts_path),
        "schedule_unresolved_v2_csv": str(unresolved_path),
        "alias_audit_summary_v2_json": str(audit_path),
        "alias_v2_simulation_summary_json": str(sim_path),
        "team_mapping_audit_v2_csv": audit_paths["team_mapping_audit_v2_csv"],
        "team_mapping_audit_v2_html": audit_paths["team_mapping_audit_v2_html"],
    }
