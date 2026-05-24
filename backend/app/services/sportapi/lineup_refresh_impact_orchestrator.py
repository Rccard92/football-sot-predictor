"""Orchestrazione refresh SportAPI + confronto impatto v2.0."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.core.constants import BASELINE_SOT_MODEL_VERSION_V20_LINEUP_IMPACT
from app.models import Fixture, FixtureLineupRefreshImpact, Team
from app.models.fixture_lineup_refresh_impact import PROVIDER_SPORTAPI_DEFAULT
from app.services.predictions_v20.baseline_v2_0_lineup_impact_service import SotPredictionV20LineupImpactService
from app.services.sportapi.lineup_refresh_impact_service import LineupRefreshImpactService
from app.services.sportapi.lineup_refresh_snapshot_service import build_snapshot
from app.services.sportapi.sportapi_lineup_service import SportApiLineupService


class LineupRefreshImpactOrchestrator:
    def __init__(self) -> None:
        self._impact_svc = LineupRefreshImpactService()

    def _match_name(self, db: Session, fixture_id: int) -> str:
        fx = db.get(Fixture, int(fixture_id))
        if fx is None:
            return f"Fixture {fixture_id}"
        home = db.get(Team, int(fx.home_team_id))
        away = db.get(Team, int(fx.away_team_id))
        return f"{home.name if home else 'Casa'} – {away.name if away else 'Trasferta'}"

    def save_impact_row(
        self,
        db: Session,
        *,
        fixture_id: int,
        before: dict[str, Any],
        after: dict[str, Any],
        impact: dict[str, Any],
        model_id: str = BASELINE_SOT_MODEL_VERSION_V20_LINEUP_IMPACT,
    ) -> int:
        row = FixtureLineupRefreshImpact(
            fixture_id=int(fixture_id),
            provider_name=PROVIDER_SPORTAPI_DEFAULT,
            model_id=model_id,
            before_payload=before,
            after_payload=after,
            delta_home_sot=impact.get("delta_home_sot"),
            delta_away_sot=impact.get("delta_away_sot"),
            delta_total_sot=impact.get("delta_total_sot"),
            direction_home=impact.get("direction_home"),
            direction_away=impact.get("direction_away"),
            direction_total=impact.get("direction_total"),
            reasons=impact.get("reasons"),
            main_reason=impact.get("main_reason"),
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return int(row.id)

    def refresh_fixture_with_impact(
        self,
        db: Session,
        fixture_id: int,
        *,
        force_fetch: bool = False,
        regenerate_v20: bool = True,
        skip_fetch: bool = False,
        before_snapshot: dict[str, Any] | None = None,
        model_id: str = BASELINE_SOT_MODEL_VERSION_V20_LINEUP_IMPACT,
    ) -> dict[str, Any]:
        before = before_snapshot or build_snapshot(db, int(fixture_id), model_id=model_id)

        refresh_result: dict[str, Any]
        if skip_fetch:
            refresh_result = {"status": "success", "fixture_id": int(fixture_id), "skipped_fetch": True}
        else:
            refresh_result = SportApiLineupService().fetch_and_persist_lineups(db, int(fixture_id))

        out: dict[str, Any] = {
            "status": refresh_result.get("status", "error"),
            "fixture_id": int(fixture_id),
            "refresh_result": refresh_result,
            "impact_delta": None,
            "impact_id": None,
            "match_name": self._match_name(db, int(fixture_id)),
        }

        if refresh_result.get("status") != "success":
            out["status"] = "error"
            out["message"] = str(refresh_result.get("message") or "Refresh lineups fallito")
            return out

        v20_out = None
        if regenerate_v20:
            v20_out = SotPredictionV20LineupImpactService().generate_for_fixture(db, int(fixture_id))
            out["v20_regenerate"] = v20_out

        after = build_snapshot(db, int(fixture_id), model_id=model_id)

        if not before.get("v20_available") or not after.get("v20_available"):
            out["status"] = "partial_success"
            out["message"] = (
                "Refresh completato ma manca predizione v2.0 completa prima o dopo "
                "(genera v1.1 e v2.0 prima del confronto)."
            )
            return out

        impact = self._impact_svc.compare(before, after)
        impact_id = self.save_impact_row(
            db,
            fixture_id=int(fixture_id),
            before=before,
            after=after,
            impact=impact,
            model_id=model_id,
        )
        out["status"] = "success"
        out["impact_id"] = impact_id
        out["impact_delta"] = self._impact_svc.to_public_delta(impact)
        return out

    def finalize_impact_after_refresh(
        self,
        db: Session,
        fixture_id: int,
        before_snapshot: dict[str, Any],
        *,
        model_id: str = BASELINE_SOT_MODEL_VERSION_V20_LINEUP_IMPACT,
    ) -> dict[str, Any] | None:
        """Dopo fetch + rigenera v2.0: confronta con snapshot BEFORE già catturato."""
        after = build_snapshot(db, int(fixture_id), model_id=model_id)
        if not before_snapshot.get("v20_available") or not after.get("v20_available"):
            return None
        impact = self._impact_svc.compare(before_snapshot, after)
        self.save_impact_row(
            db,
            fixture_id=int(fixture_id),
            before=before_snapshot,
            after=after,
            impact=impact,
            model_id=model_id,
        )
        delta = self._impact_svc.to_public_delta(impact)
        delta["match_name"] = self._match_name(db, int(fixture_id))
        return delta

    @staticmethod
    def _impact_row_to_public_delta(row: FixtureLineupRefreshImpact) -> dict[str, Any]:
        svc = LineupRefreshImpactService()
        before = row.before_payload if isinstance(row.before_payload, dict) else {}
        after = row.after_payload if isinstance(row.after_payload, dict) else {}
        delta = svc.to_public_delta(
            {
                "direction_total": row.direction_total,
                "delta_total_sot": row.delta_total_sot,
                "direction_home": row.direction_home,
                "delta_home_sot": row.delta_home_sot,
                "direction_away": row.direction_away,
                "delta_away_sot": row.delta_away_sot,
                "main_reason": row.main_reason,
                "reasons": row.reasons,
                "before_total_sot": before.get("predicted_total_sot"),
                "after_total_sot": after.get("predicted_total_sot"),
                "before_home_sot": before.get("predicted_home_sot"),
                "after_home_sot": after.get("predicted_home_sot"),
                "before_away_sot": before.get("predicted_away_sot"),
                "after_away_sot": after.get("predicted_away_sot"),
            },
        )
        delta["has_comparison"] = True
        delta["created_at"] = row.created_at.isoformat() if row.created_at else None
        delta["before_payload"] = before
        delta["after_payload"] = after
        return delta

    @staticmethod
    def load_latest_impact_by_fixture_ids(
        db: Session,
        fixture_ids: list[int],
        *,
        model_id: str = BASELINE_SOT_MODEL_VERSION_V20_LINEUP_IMPACT,
    ) -> dict[int, dict[str, Any]]:
        snaps = LineupRefreshImpactOrchestrator.load_impact_snapshots_by_fixture_ids(
            db, fixture_ids, model_id=model_id
        )
        return {fid: s["latest"] for fid, s in snaps.items() if s.get("latest")}

    @staticmethod
    def load_impact_snapshots_by_fixture_ids(
        db: Session,
        fixture_ids: list[int],
        *,
        model_id: str = BASELINE_SOT_MODEL_VERSION_V20_LINEUP_IMPACT,
    ) -> dict[int, dict[str, dict[str, Any] | None]]:
        """Per ogni fixture: primo impact (before iniziale) e ultimo (after ufficiale)."""
        if not fixture_ids:
            return {}
        from sqlalchemy import select

        rows = list(
            db.scalars(
                select(FixtureLineupRefreshImpact)
                .where(
                    FixtureLineupRefreshImpact.fixture_id.in_([int(x) for x in fixture_ids]),
                    FixtureLineupRefreshImpact.model_id == model_id,
                )
                .order_by(
                    FixtureLineupRefreshImpact.fixture_id,
                    FixtureLineupRefreshImpact.created_at.asc(),
                ),
            ).all(),
        )
        first_row: dict[int, FixtureLineupRefreshImpact] = {}
        latest_row: dict[int, FixtureLineupRefreshImpact] = {}
        for r in rows:
            fid = int(r.fixture_id)
            if fid not in first_row:
                first_row[fid] = r
            latest_row[fid] = r

        out: dict[int, dict[str, dict[str, Any] | None]] = {}
        for fid in set(first_row) | set(latest_row):
            fr = first_row.get(fid)
            lr = latest_row.get(fid)
            out[fid] = {
                "first": LineupRefreshImpactOrchestrator._impact_row_to_public_delta(fr) if fr else None,
                "latest": LineupRefreshImpactOrchestrator._impact_row_to_public_delta(lr) if lr else None,
            }
        return out
