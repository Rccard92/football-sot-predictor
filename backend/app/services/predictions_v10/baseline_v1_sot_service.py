from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.constants import (
    BASELINE_SOT_MODEL_VERSION_V04_OFFENSIVE_CORE_SOT,
    BASELINE_SOT_MODEL_VERSION_V10_SOT,
    FINISHED_STATUSES,
)
from app.models import Fixture, League, Season, Team, TeamSotPrediction
from app.services.model_applied_variable_trace import append_trace_to_raw_json, compute_hours_to_kickoff
from app.services.predictions_v10.explicit_terms_from_v04 import (
    alignment_status,
    build_explicit_v04_terms_from_saved_raw,
    build_formula_strings,
)


def _round2(x: float | None) -> float | None:
    if x is None:
        return None
    return round(float(x), 2)


class SotPredictionV10BaselineSotService:
    """v1.0: somma pesata esplicita dei 6 termini esterni v0.4 da `raw_json` v0.4 persistito (nessun xG)."""

    model_version = BASELINE_SOT_MODEL_VERSION_V10_SOT
    base_model_version = BASELINE_SOT_MODEL_VERSION_V04_OFFENSIVE_CORE_SOT

    def _season_row(self, db: Session, season_year: int) -> tuple[League, Season]:
        from app.core.config import get_settings
        from app.services.ingestion_service import IngestionService

        league = db.scalar(select(League).where(League.name == IngestionService.SERIE_A_LEAGUE_NAME))
        if league is None:
            settings = get_settings()
            league = db.scalar(select(League).where(League.api_league_id == settings.default_league_id))
        if league is None:
            raise ValueError("league_not_found")

        season = db.scalar(select(Season).where(Season.league_id == league.id, Season.year == int(season_year)))
        if season is None:
            raise ValueError("season_not_found")
        return league, season

    def generate_for_upcoming_season(self, db: Session, season_year: int, *, limit: int = 200) -> dict[str, Any]:
        try:
            _league, season = self._season_row(db, season_year)
        except Exception as exc:
            return {
                "status": "error",
                "failed_step": "load_season",
                "message": "Impossibile caricare league/season.",
                "details": str(exc),
                "partial_result": {"upcoming_fixtures_found": 0, "predictions_created_or_updated": 0, "errors": []},
            }

        fixtures = db.scalars(
            select(Fixture).where(Fixture.season_id == season.id).order_by(Fixture.kickoff_at.asc(), Fixture.id.asc()),
        ).all()
        upcoming = [f for f in fixtures if (f.status or "").upper() not in FINISHED_STATUSES][:limit]

        if not upcoming:
            return {
                "status": "error",
                "failed_step": "no_upcoming_fixtures",
                "message": "Nessuna fixture upcoming trovata per la stagione richiesta.",
                "details": f"season={int(season_year)}",
                "partial_result": {"upcoming_fixtures_found": 0, "predictions_created_or_updated": 0, "errors": []},
            }

        aligned_n = 0
        minor_n = 0
        review_n = 0
        created = 0
        errors: list[dict[str, Any]] = []

        for fx in upcoming:
            for team_id in (int(fx.home_team_id), int(fx.away_team_id)):
                pred_v04 = db.scalar(
                    select(TeamSotPrediction).where(
                        TeamSotPrediction.fixture_id == fx.id,
                        TeamSotPrediction.team_id == int(team_id),
                        TeamSotPrediction.model_version == BASELINE_SOT_MODEL_VERSION_V04_OFFENSIVE_CORE_SOT,
                    ),
                )
                if pred_v04 is None or pred_v04.predicted_sot is None:
                    errors.append(
                        {
                            "fixture_id": int(fx.id),
                            "team_id": int(team_id),
                            "error": "missing_v04_prediction",
                            "message": "Prediction v0.4 mancante: genera v0.4 prima di v1.0.",
                        },
                    )
                    continue

                base_raw = pred_v04.raw_json if isinstance(pred_v04.raw_json, dict) else {}
                try:
                    terms, expected = build_explicit_v04_terms_from_saved_raw(base_raw)
                except ValueError as exc:
                    errors.append(
                        {
                            "fixture_id": int(fx.id),
                            "team_id": int(team_id),
                            "error": "invalid_v04_raw_json",
                            "message": f"raw_json v0.4 incompleto per ricostruire i 6 termini: {exc}",
                        },
                    )
                    continue

                v04_ref = float(pred_v04.predicted_sot)
                delta = round(float(expected) - v04_ref, 2)
                align_st = alignment_status(delta)
                if align_st == "aligned_with_v04":
                    aligned_n += 1
                elif align_st == "minor_rounding_difference":
                    minor_n += 1
                else:
                    review_n += 1

                symbolic, numeric = build_formula_strings(terms, expected)

                merged: dict[str, Any] = {
                    k: v
                    for k, v in base_raw.items()
                    if k not in ("model_version", "applied_variable_trace", "xg_component", "baseline_v04_expected_sot")
                }
                merged["model_version"] = self.model_version
                merged["architecture"] = "explicit_terms_from_v04"
                merged["base_model_version"] = self.base_model_version
                merged["does_not_use_v04_as_black_box"] = True
                merged["expected_sot"] = float(expected)
                merged["v04_expected_sot_reference"] = _round2(v04_ref)
                merged["difference_from_v04"] = float(delta)
                merged["formula"] = {
                    "type": "weighted_sum",
                    "terms": terms,
                    "symbolic": symbolic,
                    "numeric": numeric,
                }
                merged["v04_alignment"] = {
                    "v04_expected_sot": _round2(v04_ref),
                    "v10_expected_sot": float(expected),
                    "delta": float(delta),
                    "status": align_st,
                }

                team_row = db.get(Team, int(team_id))
                tname = team_row.name if team_row is not None else str(team_id)
                merged = append_trace_to_raw_json(
                    merged,
                    model_version=self.model_version,
                    team_id=int(team_id),
                    team_name=tname,
                    audit_map={},
                    hours_to_kickoff=compute_hours_to_kickoff(fx.kickoff_at),
                    prediction_confidence=None,
                )

                existing = db.scalar(
                    select(TeamSotPrediction).where(
                        TeamSotPrediction.fixture_id == fx.id,
                        TeamSotPrediction.team_id == int(team_id),
                        TeamSotPrediction.model_version == self.model_version,
                    ),
                )
                if existing is None:
                    existing = TeamSotPrediction(
                        fixture_id=int(fx.id),
                        team_id=int(team_id),
                        model_version=self.model_version,
                    )
                    db.add(existing)
                existing.predicted_sot = float(expected)
                existing.raw_json = merged
                existing.explanation = (
                    "v1.0: somma pesata esplicita dei 6 termini esterni della formula v0.4 ricostruiti da raw_json v0.4; "
                    "predicted_sot v0.4 usato solo in v04_alignment."
                )
                created += 1
                try:
                    db.commit()
                except Exception as exc:  # noqa: BLE001
                    db.rollback()
                    errors.append(
                        {
                            "fixture_id": int(fx.id),
                            "team_id": int(team_id),
                            "error": "persist_failed",
                            "message": str(exc),
                        },
                    )
                    continue

        return {
            "status": "success",
            "season": int(season_year),
            "model_version": self.model_version,
            "base_model_version": self.base_model_version,
            "architecture": "explicit_terms_from_v04",
            "upcoming_fixtures": len(upcoming),
            "predictions_created_or_updated": int(created),
            "aligned_with_v04": int(aligned_n),
            "minor_rounding_difference": int(minor_n),
            "needs_review": int(review_n),
            "errors": errors,
        }
