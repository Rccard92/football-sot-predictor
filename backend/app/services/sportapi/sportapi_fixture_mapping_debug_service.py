"""Debug mapping fixture SportAPI per fixture target (Step K.3)."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Competition, Fixture, Team
from app.models.fixture_provider_mapping import PROVIDER_SPORTAPI, FixtureProviderMapping
from app.schemas.sportapi_fixture_mapping_debug import (
    SportApiExistingMappingBrief,
    SportApiFixtureMappingDebugResponse,
    SportApiInternalFixtureBrief,
    SportApiMappingCandidateBrief,
)
from app.services.sportapi.sportapi_fixture_mapping_discovery import SportApiFixtureMappingDiscovery
from app.services.sportapi.sportapi_fixture_mapping_scoring import (
    ScoredMappingCandidate,
    effective_confidence,
)
from app.services.sportapi.sportapi_fixture_resolve import FIXTURE_NOT_FOUND_MSG, resolve_fixture_or_error
from app.services.sportapi.sportapi_lineup_service import SportApiLineupService

MATCHED_BY = "sportapi_fixture_discovery"


def _candidate_brief(c: ScoredMappingCandidate) -> SportApiMappingCandidateBrief:
    return SportApiMappingCandidateBrief(
        provider_event_id=c.provider_event_id,
        score=c.score,
        confidence=c.confidence,
        home_team_name=c.home_team_name,
        away_team_name=c.away_team_name,
        start_timestamp=c.start_timestamp,
        round_number=c.round_number,
        tournament_name=c.tournament_name,
        breakdown=dict(c.breakdown),
    )


class SportApiFixtureMappingDebugService:
    def __init__(
        self,
        discovery: SportApiFixtureMappingDiscovery | None = None,
        lineup_svc: SportApiLineupService | None = None,
    ) -> None:
        self._discovery = discovery or SportApiFixtureMappingDiscovery()
        self._lineup_svc = lineup_svc or SportApiLineupService()

    def debug_fixture(
        self,
        db: Session,
        *,
        fixture_id: int,
        competition_id: int,
        dry_run: bool = True,
        force_refresh: bool = False,
    ) -> SportApiFixtureMappingDebugResponse:
        comp = db.get(Competition, int(competition_id))
        if comp is None:
            return SportApiFixtureMappingDebugResponse(
                status="error",
                dry_run=bool(dry_run),
                internal_fixture=SportApiInternalFixtureBrief(
                    fixture_id=int(fixture_id),
                    competition_id=int(competition_id),
                    competition_name="",
                    kickoff_at=datetime.now(timezone.utc),
                    home_team="",
                    away_team="",
                ),
                existing_mapping=SportApiExistingMappingBrief(found=False),
                warnings=[f"Competition {competition_id} not found"],
            )

        fx, err = resolve_fixture_or_error(db, int(fixture_id))
        if fx is None:
            return SportApiFixtureMappingDebugResponse(
                status="error",
                dry_run=bool(dry_run),
                internal_fixture=SportApiInternalFixtureBrief(
                    fixture_id=int(fixture_id),
                    competition_id=int(competition_id),
                    competition_name=comp.name,
                    kickoff_at=datetime.now(timezone.utc),
                    home_team="",
                    away_team="",
                ),
                existing_mapping=SportApiExistingMappingBrief(found=False),
                warnings=[str((err or {}).get("message") or FIXTURE_NOT_FOUND_MSG)],
            )

        internal_id = int(fx.id)
        if int(fx.competition_id or 0) != int(competition_id):
            home = db.get(Team, int(fx.home_team_id))
            away = db.get(Team, int(fx.away_team_id))
            kickoff = fx.kickoff_at
            if kickoff is None:
                kickoff = datetime.now(timezone.utc)
            return SportApiFixtureMappingDebugResponse(
                status="error",
                dry_run=bool(dry_run),
                internal_fixture=SportApiInternalFixtureBrief(
                    fixture_id=internal_id,
                    competition_id=int(competition_id),
                    competition_name=comp.name,
                    round=fx.round,
                    kickoff_at=kickoff,
                    home_team=home.name if home else str(fx.home_team_id),
                    away_team=away.name if away else str(fx.away_team_id),
                ),
                existing_mapping=SportApiExistingMappingBrief(found=False),
                warnings=[f"Fixture {internal_id} non appartiene a competition {competition_id}"],
            )

        home = db.get(Team, int(fx.home_team_id))
        away = db.get(Team, int(fx.away_team_id))
        kickoff = fx.kickoff_at
        if kickoff is None:
            kickoff = datetime.now(timezone.utc)

        internal_brief = SportApiInternalFixtureBrief(
            fixture_id=internal_id,
            competition_id=int(competition_id),
            competition_name=comp.name,
            round=fx.round,
            kickoff_at=kickoff,
            home_team=home.name if home else str(fx.home_team_id),
            away_team=away.name if away else str(fx.away_team_id),
        )

        mapping = db.scalar(
            select(FixtureProviderMapping).where(
                FixtureProviderMapping.fixture_id == internal_id,
                FixtureProviderMapping.provider_name == PROVIDER_SPORTAPI,
            ),
        )

        if mapping is not None and not force_refresh:
            return SportApiFixtureMappingDebugResponse(
                status="ok",
                dry_run=bool(dry_run),
                internal_fixture=internal_brief,
                existing_mapping=SportApiExistingMappingBrief(
                    found=True,
                    provider_fixture_id=int(mapping.provider_event_id),
                    source=PROVIDER_SPORTAPI,
                    confidence_score=float(mapping.confidence_score)
                    if mapping.confidence_score is not None
                    else None,
                    matched_by=mapping.matched_by,
                ),
                match_confidence="high",
                warnings=["Mapping esistente — usa force_refresh=true per riscoprire"],
                api_calls=0,
            )

        discovery = self._discovery.discover_for_fixture(db, fixture=fx, competition=comp)
        warnings = list(discovery.get("warnings") or [])
        if discovery.get("status") != "ok":
            msg = str(discovery.get("message") or "Discovery fallita")
            return SportApiFixtureMappingDebugResponse(
                status=str(discovery.get("status") or "error"),
                dry_run=bool(dry_run),
                internal_fixture=internal_brief,
                existing_mapping=SportApiExistingMappingBrief(
                    found=mapping is not None,
                    provider_fixture_id=int(mapping.provider_event_id) if mapping else None,
                    source=PROVIDER_SPORTAPI if mapping else None,
                    confidence_score=float(mapping.confidence_score)
                    if mapping and mapping.confidence_score is not None
                    else None,
                    matched_by=mapping.matched_by if mapping else None,
                ),
                warnings=warnings + [msg],
                scheduled_events_count=int(discovery.get("scheduled_events_count") or 0),
                api_calls=int(discovery.get("api_calls") or 0),
            )

        candidates: list[ScoredMappingCandidate] = list(discovery.get("candidates") or [])
        best: ScoredMappingCandidate | None = discovery.get("best")
        ambiguous = bool(discovery.get("ambiguous_high"))
        confidence = effective_confidence(best, ambiguous=ambiguous)

        candidate_briefs = [_candidate_brief(c) for c in candidates[:20]]
        best_brief = _candidate_brief(best) if best else None

        would_write = (
            not dry_run
            and confidence == "high"
            and not ambiguous
            and best is not None
            and (mapping is None or force_refresh)
        )

        if confidence in ("medium", "low"):
            warnings.append(f"Confidence {confidence}: auto-save non consentito (solo high)")

        mapping_written = False
        if would_write and best is not None:
            result = self._lineup_svc.confirm_mapping(
                db,
                internal_id,
                provider_event_id=int(best.provider_event_id),
                confidence_score=float(best.score),
                matched_by=MATCHED_BY,
                raw_payload=best.raw_event,
                expected_competition_id=int(competition_id),
            )
            if result.get("status") == "success":
                mapping_written = True
            else:
                warnings.append(str(result.get("message") or "confirm_mapping fallito"))

        existing = SportApiExistingMappingBrief(found=False)
        if mapping_written or (mapping is not None and not force_refresh):
            row = db.scalar(
                select(FixtureProviderMapping).where(
                    FixtureProviderMapping.fixture_id == internal_id,
                    FixtureProviderMapping.provider_name == PROVIDER_SPORTAPI,
                ),
            )
            if row is not None:
                existing = SportApiExistingMappingBrief(
                    found=True,
                    provider_fixture_id=int(row.provider_event_id),
                    source=PROVIDER_SPORTAPI,
                    confidence_score=float(row.confidence_score) if row.confidence_score is not None else None,
                    matched_by=row.matched_by,
                )
        elif mapping is not None:
            existing = SportApiExistingMappingBrief(
                found=True,
                provider_fixture_id=int(mapping.provider_event_id),
                source=PROVIDER_SPORTAPI,
                confidence_score=float(mapping.confidence_score)
                if mapping.confidence_score is not None
                else None,
                matched_by=mapping.matched_by,
            )

        return SportApiFixtureMappingDebugResponse(
            status="ok",
            dry_run=bool(dry_run),
            internal_fixture=internal_brief,
            existing_mapping=existing,
            sportapi_candidates=candidate_briefs,
            best_candidate=best_brief,
            match_confidence=confidence,
            ambiguous_high_matches=ambiguous,
            would_write_mapping=would_write,
            mapping_written=mapping_written,
            warnings=warnings,
            scheduled_events_count=int(discovery.get("scheduled_events_count") or 0),
            api_calls=int(discovery.get("api_calls") or 0),
        )
