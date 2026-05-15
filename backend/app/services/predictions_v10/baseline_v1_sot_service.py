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
from app.services.predictions_v10.explicit_terms_from_v04 import alignment_status
from app.services.predictions_v10.v10_formula_builder import build_v10_side_formula
from app.services.sot_feature_registry import V10_ARCHITECTURE


def _round2(x: float | None) -> float | None:
    if x is None:
        return None
    return round(float(x), 2)


class SotPredictionV10BaselineSotService:
    """v1.0: 6 termini da feature registry DB + correzione additiva expected_goals (xG)."""

    model_version = BASELINE_SOT_MODEL_VERSION_V10_SOT
    base_model_version = BASELINE_SOT_MODEL_VERSION_V04_OFFENSIVE_CORE_SOT
    architecture = V10_ARCHITECTURE

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
        xg_applied = 0
        xg_fallback = 0
        created = 0
        formula_terms_ok = 0
        formula_terms_bad = 0
        all_quality_warnings: list[str] = []
        errors: list[dict[str, Any]] = []

        for fx in upcoming:
            opp_by_team = {
                int(fx.home_team_id): int(fx.away_team_id),
                int(fx.away_team_id): int(fx.home_team_id),
            }
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
                            "message": "Prediction v0.4 mancante: genera v0.4 prima di v1.0 (solo confronto alignment).",
                        },
                    )
                    continue

                try:
                    built = build_v10_side_formula(
                        db,
                        fx,
                        team_id=int(team_id),
                        opponent_id=int(opp_by_team[int(team_id)]),
                    )
                except Exception as exc:  # noqa: BLE001
                    errors.append(
                        {
                            "fixture_id": int(fx.id),
                            "team_id": int(team_id),
                            "error": "feature_resolution_failed",
                            "message": str(exc)[:500],
                        },
                    )
                    continue

                base_explicit_sot = float(built["base_explicit_sot"])
                final_sot = float(built["final_sot"])
                xg_comp = built["xg_component"] if isinstance(built["xg_component"], dict) else {}
                formula_payload = built["formula_payload"]
                quality_meta = built["quality_meta"] if isinstance(built["quality_meta"], dict) else {}
                off_comp = built.get("offensive_production_component") if isinstance(built.get("offensive_production_component"), dict) else {}

                if xg_comp.get("xg_adjustment_applied"):
                    xg_applied += 1
                else:
                    xg_fallback += 1

                diff_base = round(final_sot - base_explicit_sot, 2)
                v04_ref = float(pred_v04.predicted_sot)
                delta_base = round(base_explicit_sot - v04_ref, 2)
                align_st = alignment_status(delta_base)
                fq_status = str(quality_meta.get("formula_quality_status") or "ok")
                fq_warnings = list(quality_meta.get("formula_quality_warnings") or [])
                if fq_status == "needs_review":
                    align_st = "needs_review"
                if align_st == "aligned_with_v04":
                    aligned_n += 1
                elif align_st == "minor_rounding_difference":
                    minor_n += 1
                else:
                    review_n += 1

                terms_n = len(formula_payload.get("terms") or [])
                if terms_n == 7:
                    formula_terms_ok += 1
                else:
                    formula_terms_bad += 1
                    fq_warnings.append(f"formula_terms_count={terms_n} (atteso 7)")
                for w in fq_warnings:
                    if w and w not in all_quality_warnings:
                        all_quality_warnings.append(w)

                merged: dict[str, Any] = {
                    "model_version": self.model_version,
                    "architecture": self.architecture,
                    "feature_registry_version": built.get("feature_registry_version"),
                    "base_terms_source": "feature_registry",
                    "base_model_version": self.base_model_version,
                    "does_not_use_v04_as_black_box": True,
                    "base_explicit_sot_before_xg": float(base_explicit_sot),
                    "expected_sot": float(final_sot),
                    "difference_from_explicit_base": float(diff_base),
                    "v04_expected_sot_reference": _round2(v04_ref),
                    "difference_from_v04": float(delta_base),
                    "formula": formula_payload,
                    "xg_component": xg_comp,
                    "offensive_production_component": off_comp,
                    "formula_quality_status": fq_status,
                    "formula_quality_warnings": fq_warnings,
                    "formula_terms_count": terms_n,
                    "v04_alignment": {
                        "v04_expected_sot": _round2(v04_ref),
                        "v10_expected_sot": float(base_explicit_sot),
                        "delta": float(delta_base),
                        "status": align_st,
                    },
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
                existing.predicted_sot = float(final_sot)
                existing.raw_json = merged
                existing.explanation = (
                    "v1.0: 6 termini da feature registry (DB) + xG additivo; "
                    "v0.4 predicted_sot solo in v04_alignment."
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

        aligned_base_terms_count = int(aligned_n) + int(minor_n)
        global_warnings: list[str] = list(dict.fromkeys(all_quality_warnings))
        if formula_terms_bad > 0:
            global_warnings.append(
                f"{formula_terms_bad} predizioni con formula_terms_count != 7",
            )
        return {
            "status": "success",
            "season": int(season_year),
            "model_version": self.model_version,
            "base_model_version": self.base_model_version,
            "architecture": self.architecture,
            "upcoming_fixtures": len(upcoming),
            "predictions_created_or_updated": int(created),
            "formula_terms_count": 7,
            "formula_terms_ok_count": int(formula_terms_ok),
            "formula_terms_bad_count": int(formula_terms_bad),
            "formula_quality_warnings": global_warnings,
            "xg_applied_count": int(xg_applied),
            "xg_fallback_count": int(xg_fallback),
            "aligned_base_terms_count": aligned_base_terms_count,
            "aligned_with_v04": int(aligned_n),
            "minor_rounding_difference": int(minor_n),
            "needs_review": int(review_n),
            "errors": errors,
        }
