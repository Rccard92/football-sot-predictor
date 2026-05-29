"""Import batch lineups SportAPI scoped per competition_id."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import sportapi_configured
from app.core.constants import FINISHED_STATUSES, fixture_eligible_for_upcoming_sot
from app.models import Competition, Fixture, FixtureProviderMapping, Team
from app.models.fixture_provider_mapping import PROVIDER_SPORTAPI
from app.services.competition_service import CompetitionService
from app.services.next_round_selection import select_next_round_fixtures
from app.services.sportapi.lineup_refresh_impact_orchestrator import LineupRefreshImpactOrchestrator
from app.services.sportapi.lineup_refresh_snapshot_service import build_snapshot
from app.services.sportapi.sportapi_lineup_service import SportApiLineupService
from app.services.sportapi.sportapi_lineup_status import lineup_row_for_fixture
from app.services.sportapi.sportapi_matching_service import SportApiMatchingService

logger = logging.getLogger(__name__)

Scope = Literal["next_round", "upcoming_limit", "fixture_ids"]
SKIP_FETCH_MINUTES = 10.0
AUTO_MAPPING_MIN_CONFIDENCE = 90.0


def _fetched_at_age_minutes(fetched_at: datetime | None) -> float | None:
    if fetched_at is None:
        return None
    now = datetime.now(timezone.utc)
    ft = fetched_at
    if ft.tzinfo is None:
        ft = ft.replace(tzinfo=timezone.utc)
    return (now - ft.astimezone(timezone.utc)).total_seconds() / 60.0


class CompetitionSportApiLineupService:
    def __init__(self) -> None:
        self._comp_svc = CompetitionService()

    def _has_mapping(self, db: Session, fixture_id: int, competition_id: int) -> bool:
        return (
            db.scalar(
                select(FixtureProviderMapping.id)
                .join(Fixture, Fixture.id == FixtureProviderMapping.fixture_id)
                .where(
                    FixtureProviderMapping.fixture_id == int(fixture_id),
                    FixtureProviderMapping.provider_name == PROVIDER_SPORTAPI,
                    Fixture.competition_id == int(competition_id),
                ),
            )
            is not None
        )

    def _resolve_fixtures(
        self,
        db: Session,
        comp: Competition,
        *,
        scope: Scope,
        upcoming_limit: int,
        fixture_ids: list[int] | None,
    ) -> tuple[list[Fixture], str | None, list[str], str | None]:
        cid = int(comp.id)
        warnings: list[str] = []

        if scope == "fixture_ids":
            if not fixture_ids:
                return [], None, warnings, "fixture_ids_required"
            rows = list(
                db.scalars(select(Fixture).where(Fixture.id.in_([int(x) for x in fixture_ids]))).all()
            )
            bad = [int(fx.id) for fx in rows if int(fx.competition_id or 0) != cid]
            if bad:
                return [], None, warnings, "fixture_competition_mismatch"
            missing = set(int(x) for x in fixture_ids) - {int(fx.id) for fx in rows}
            if missing:
                warnings.append(f"Fixture non trovate: {sorted(missing)}")
            rows.sort(key=lambda f: (f.kickoff_at, int(f.id)))
            return rows, None, warnings, None

        all_rows = list(
            db.scalars(
                select(Fixture).where(
                    Fixture.competition_id == cid,
                    ~Fixture.status.in_(FINISHED_STATUSES),
                )
            ).all()
        )

        if scope == "upcoming_limit":
            pool = [
                f
                for f in all_rows
                if fixture_eligible_for_upcoming_sot(f.status, f.kickoff_at)
            ]
            pool.sort(key=lambda f: (f.kickoff_at, int(f.id)))
            cap = max(1, min(int(upcoming_limit), 100))
            return pool[:cap], None, warnings, None

        selection = select_next_round_fixtures(all_rows, limit=100, only_next_round=True)
        warnings.extend(selection.warnings)
        if selection.error_code:
            return [], selection.final_round, warnings, selection.error_code
        return selection.fixtures, selection.final_round, warnings, None

    def ingest(
        self,
        db: Session,
        competition_id: int,
        *,
        scope: Scope = "next_round",
        dry_run: bool = True,
        force: bool = False,
        regenerate_v20: bool = True,
        upcoming_limit: int = 20,
        fixture_ids: list[int] | None = None,
    ) -> dict[str, Any]:
        if not sportapi_configured():
            return {
                "status": "error",
                "code": "sportapi_disabled",
                "message": "SportAPI non configurata sul server",
                "competition_id": int(competition_id),
            }

        comp = self._comp_svc.get_by_id_or_raise(db, int(competition_id))
        fixtures, round_label, pre_warnings, sel_error = self._resolve_fixtures(
            db,
            comp,
            scope=scope,
            upcoming_limit=upcoming_limit,
            fixture_ids=fixture_ids,
        )

        base: dict[str, Any] = {
            "competition_id": int(comp.id),
            "competition_name": comp.name,
            "scope": scope,
            "round": round_label,
            "dry_run": bool(dry_run),
            "force": bool(force),
            "fixtures_checked": len(fixtures),
            "mappings_found": 0,
            "mappings_uncertain": 0,
            "mappings_saved": 0,
            "lineups_would_fetch": 0,
            "lineups_imported": 0,
            "missing_players_imported": 0,
            "predictions_regenerated": 0,
            "estimated_api_calls": 0,
            "skipped_recent": 0,
            "failed": 0,
            "warnings": list(pre_warnings),
            "results": [],
        }

        if sel_error == "no_future_fixtures":
            base["status"] = "error"
            base["code"] = sel_error
            base["message"] = "Nessuna fixture futura per questa competition"
            return base
        if sel_error == "fixture_ids_required":
            base["status"] = "error"
            base["code"] = sel_error
            base["message"] = "scope=fixture_ids richiede fixture_ids non vuoto"
            return base
        if sel_error == "fixture_competition_mismatch":
            base["status"] = "error"
            base["code"] = sel_error
            base["message"] = "Una o più fixture non appartengono alla competition selezionata"
            return base
        if not fixtures:
            base["status"] = "success"
            base["message"] = "Nessuna fixture da processare"
            return base

        match_svc = SportApiMatchingService()
        lineup_svc = SportApiLineupService()
        impact_orch = LineupRefreshImpactOrchestrator()
        results: list[dict[str, Any]] = []
        api_calls = 0
        mappings_found = 0
        mappings_uncertain = 0
        mappings_saved = 0
        lineups_would_fetch = 0
        lineups_imported = 0
        missing_players_imported = 0
        predictions_regenerated = 0
        skipped_recent = 0
        failed = 0

        dates_seen: dict[str, bool] = {}

        for fx in fixtures:
            fid = int(fx.id)
            home_t = db.get(Team, int(fx.home_team_id))
            away_t = db.get(Team, int(fx.away_team_id))
            home_name = home_t.name if home_t else "Casa"
            away_name = away_t.name if away_t else "Trasferta"
            kickoff = fx.kickoff_at
            if kickoff.tzinfo is None:
                kickoff = kickoff.replace(tzinfo=timezone.utc)

            row: dict[str, Any] = {
                "fixture_id": fid,
                "api_fixture_id": int(fx.api_fixture_id),
                "match_api_sports": f"{home_name} – {away_name}",
                "kickoff": kickoff.isoformat(),
                "mapping_ok": self._has_mapping(db, fid, int(comp.id)),
                "lineups_ok": lineup_row_for_fixture(db, fid) is not None,
                "status": "ok",
                "would_save": False,
            }

            try:
                match_date = kickoff.astimezone(timezone.utc).date().isoformat()
                if match_date not in dates_seen:
                    dates_seen[match_date] = True

                debug = match_svc.match_fixture_for_competition(db, fid, comp)
                api_calls += int(debug.get("api_calls") or 1)

                if debug.get("status") != "ok":
                    row["status"] = str(debug.get("status") or "error")
                    row["error"] = str(debug.get("message") or "matching failed")
                    failed += 1
                    results.append(row)
                    continue

                candidates = debug.get("raw_candidates") or debug.get("candidates") or []
                best = debug.get("best_candidate")
                rec = str(debug.get("recommendation") or "NO_MATCH")
                would_save = bool(debug.get("would_save")) or rec == "AUTO_SAFE"

                row["candidates_count"] = len(candidates)
                row["sportapi_candidates"] = [
                    {
                        "sportapi_event_id": c.get("provider_event_id"),
                        "home_team_name": c.get("home_team_name"),
                        "away_team_name": c.get("away_team_name"),
                        "confidence": c.get("confidence_score"),
                        "recommendation": c.get("recommendation"),
                    }
                    for c in candidates[:5]
                ]
                row["best_match"] = debug.get("best_match")
                row["sportapi_event_id"] = debug.get("sportapi_event_id")
                row["confidence"] = debug.get("confidence_score")
                row["reason"] = debug.get("match_reason")
                row["recommendation"] = rec
                row["would_save"] = would_save

                if rec == "AUTO_SAFE":
                    mappings_found += 1
                    if would_save:
                        lineups_would_fetch += 1
                elif rec == "REVIEW":
                    mappings_uncertain += 1

                if dry_run:
                    results.append(row)
                    continue

                mapping_ok = row["mapping_ok"]
                if force or not mapping_ok:
                    if rec == "AUTO_SAFE" and best:
                        conf = float(best.get("confidence_score") or 90)
                        if conf >= AUTO_MAPPING_MIN_CONFIDENCE:
                            raw_ev = best.get("raw_event") if isinstance(best.get("raw_event"), dict) else best
                            out_map = lineup_svc.confirm_mapping(
                                db,
                                fid,
                                provider_event_id=int(best["provider_event_id"]),
                                confidence_score=conf,
                                matched_by="auto_timestamp_teams",
                                raw_payload=raw_ev,
                                expected_competition_id=int(comp.id),
                            )
                            if out_map.get("status") == "success":
                                mapping_ok = True
                                mappings_saved += 1
                                row["mapping_ok"] = True
                    if not mapping_ok:
                        row["status"] = "mapping_failed"
                        row["error"] = str(debug.get("message") or "Nessun mapping AUTO_SAFE")
                        failed += 1
                        results.append(row)
                        continue

                lu = lineup_row_for_fixture(db, fid)
                should_fetch = force or lu is None
                if not should_fetch and lu and lu.fetched_at:
                    age_min = _fetched_at_age_minutes(lu.fetched_at)
                    should_fetch = age_min is None or age_min >= SKIP_FETCH_MINUTES

                if not should_fetch:
                    row["status"] = "skipped_recent"
                    skipped_recent += 1
                    results.append(row)
                    continue

                before_snapshot = build_snapshot(db, fid) if regenerate_v20 else None
                fetch_out = lineup_svc.fetch_and_persist_lineups(db, fid)
                api_calls += 1

                if fetch_out.get("status") != "success":
                    row["status"] = "lineups_failed"
                    row["error"] = str(fetch_out.get("message") or "fetch lineups fallito")
                    failed += 1
                    results.append(row)
                    continue

                lineups_imported += 1
                row["lineups_ok"] = True
                row["confirmed"] = fetch_out.get("confirmed")
                row["fetched_at"] = fetch_out.get("fetched_at")
                row["players_saved"] = fetch_out.get("players_saved")
                row["missing_players_saved"] = fetch_out.get("missing_players_saved")
                missing_players_imported += int(fetch_out.get("missing_players_saved") or 0)
                row["status"] = "updated"

                if regenerate_v20:
                    from app.services.predictions_v20.baseline_v2_0_lineup_impact_service import (
                        SotPredictionV20LineupImpactService,
                    )

                    v20_out = SotPredictionV20LineupImpactService().generate_for_fixture(db, fid)
                    if v20_out.get("status") in ("success", "partial_success"):
                        predictions_regenerated += 1
                        row["v20_regenerated"] = True

                    if before_snapshot is not None:
                        impact_delta = impact_orch.finalize_impact_after_refresh(
                            db,
                            fid,
                            before_snapshot,
                        )
                        if impact_delta:
                            row["lineup_refresh_impact"] = impact_delta

            except Exception as exc:  # noqa: BLE001
                logger.exception("sportapi lineups competition=%s fixture=%s", comp.id, fid)
                row["status"] = "error"
                row["error"] = str(exc)[:300]
                failed += 1

            results.append(row)

        base["mappings_found"] = mappings_found
        base["mappings_uncertain"] = mappings_uncertain
        base["mappings_saved"] = mappings_saved
        base["lineups_would_fetch"] = lineups_would_fetch
        base["lineups_imported"] = lineups_imported
        base["missing_players_imported"] = missing_players_imported
        base["predictions_regenerated"] = predictions_regenerated
        base["estimated_api_calls"] = api_calls
        base["skipped_recent"] = skipped_recent
        base["failed"] = failed
        base["results"] = results

        if dry_run:
            base["status"] = "dry_run"
            base["message"] = "Anteprima mapping/lineups — nessun dato salvato"
        elif failed and (lineups_imported or mappings_saved):
            base["status"] = "partial"
            base["message"] = "Import parziale completato"
        elif failed:
            base["status"] = "error"
            base["message"] = "Import fallito per tutte le fixture processate"
        else:
            base["status"] = "success"
            base["message"] = "Import lineups SportAPI completato"

        if mappings_uncertain:
            base["warnings"].append(
                f"{mappings_uncertain} mapping con confidence REVIEW — verificare manualmente prima del salvataggio"
            )

        return base
