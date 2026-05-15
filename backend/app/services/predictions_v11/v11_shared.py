"""Utility conmotione v1.1 strict (nessun fallback)."""

from __future__ import annotations

from typing import Any

from app.core.constants import BASELINE_SOT_MODEL_VERSION_V11_SOT
from app.models import Fixture
from app.services.sot_feature_registry import (
    V11_ARCHITECTURE,
    V11_FORMULA_DEFENSIVE_WEIGHT,
    V11_FORMULA_OFFENSIVE_WEIGHT,
    V11_FORMULA_SPLIT_WEIGHT,
    V11_MODEL_STAGE,
)

MISSING_DATA_MSG = "Dato obbligatorio non disponibile per il modello v1.1"

FORMULA_OFFENSIVE_WEIGHT = V11_FORMULA_OFFENSIVE_WEIGHT
FORMULA_DEFENSIVE_WEIGHT = V11_FORMULA_DEFENSIVE_WEIGHT
FORMULA_SPLIT_WEIGHT = V11_FORMULA_SPLIT_WEIGHT


def safe_float(x: Any) -> float | None:
    if x is None:
        return None
    try:
        v = float(x)
        return None if v != v else v
    except (TypeError, ValueError):
        return None


def round2(x: float | None) -> float | None:
    if x is None:
        return None
    return round(float(x), 2)


def round4(x: float) -> float:
    return round(float(x), 4)


def clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, float(x)))


def last_n(fixtures: list[Fixture], n: int) -> list[Fixture]:
    xs = sorted(fixtures, key=lambda f: (f.kickoff_at, f.id), reverse=True)[:n]
    return sorted(xs, key=lambda f: (f.kickoff_at, f.id))


def missing_field(
    feature_key: str,
    *,
    api_sources: dict[str, str],
    db_fields: dict[str, str],
    source_paths: dict[str, str],
) -> dict[str, Any]:
    return {
        "feature_key": feature_key,
        "api_source": api_sources.get(feature_key, ""),
        "db_field": db_fields.get(feature_key, ""),
        "source_path": source_paths.get(feature_key, ""),
        "message": MISSING_DATA_MSG,
    }


def incomplete_raw_json(
    *,
    missing: list[dict[str, Any]],
    formula_quality_status: str,
    sample_count: int,
    league_error: list[str] | None = None,
) -> dict[str, Any]:
    if league_error:
        for key in league_error:
            missing.append(
                {
                    "feature_key": key,
                    "api_source": "league_baseline",
                    "db_field": f"league.{key}",
                    "message": "Media lega obbligatoria mancante o non valida per v1.1",
                },
            )
    return {
        "model_version": BASELINE_SOT_MODEL_VERSION_V11_SOT,
        "architecture": V11_ARCHITECTURE,
        "model_stage": V11_MODEL_STAGE,
        "status": "incomplete",
        "prediction_valid": False,
        "expected_sot": None,
        "formula_quality_status": formula_quality_status,
        "missing_required_fields": missing,
        "sample_count": sample_count,
        "warnings": [],
    }
