"""
Resolver feature v1.0 da DB (feature registry). Nessuna lettura valori da raw_json v0.4.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models import Fixture
from app.services.predictions_v10.offensive_production_blend import compute_offensive_production_component
from app.services.predictions_v10.v10_prior_context import V10PriorContext, build_prior_context
from app.services.predictions_v10.xg_adjustment_component import compute_xg_adjustment_for_side
from app.services.sot_feature_math import compute_row_features
from app.services.sot_feature_registry import (
    EXPECTED_GOALS_SPEC,
    FORMULA_TERM_SPECS,
    OFFENSIVE_INPUT_LABELS,
    ResolvedFeature,
    WEIGHT_OFFENSIVE,
    formula_term_spec_by_key,
)

DUPLICATE_VALUES_WARNING = "Valori formula sospetti: più termini hanno lo stesso valore"


def _safe_float(x: Any) -> float | None:
    if x is None:
        return None
    try:
        v = float(x)
        return None if v != v else v
    except (TypeError, ValueError):
        return None


def _r4(x: float) -> float:
    return round(float(x), 4)


def _r2(x: float) -> float:
    return round(float(x), 2)


def _term_from_row_features(
    *,
    key: str,
    label: str,
    value: float | None,
    weight: float,
    source_path: str,
    source_field: str,
    sample_count: int,
    fallback_used: bool,
    fallback_reason: str | None,
    formula: str,
) -> ResolvedFeature:
    spec = formula_term_spec_by_key(key)
    if value is not None and not fallback_used:
        contrib = _r4(float(value) * float(weight))
        status = "available"
    else:
        contrib = 0.0
        status = "fallback" if fallback_used else "missing"
    return ResolvedFeature(
        key=key,
        label=label,
        value=_r2(value) if value is not None else None,
        contribution=contrib,
        weight=weight,
        source_table="fixture_team_stats",
        source_field=source_field,
        api_source=spec.api_source if spec else "fixtures/statistics",
        source_path=source_path,
        sample_count=sample_count,
        fallback_used=fallback_used,
        fallback_reason=fallback_reason,
        status=status,
        formula=formula,
    )


def resolve_all_base_terms(ctx: V10PriorContext) -> tuple[list[ResolvedFeature], dict[str, Any]]:
    """6 termini formula da DB + meta row_features."""
    league_fb = ctx.league_avg_sot
    baseline_fb = 3.5
    row = compute_row_features(
        current_kickoff=ctx.cutoff_kickoff,
        team_priors=ctx.team_priors,
        is_home_current=ctx.is_home,
        opponent_priors=ctx.opponent_priors,
        opponent_is_home_current=not ctx.is_home,
        league_fallback=league_fb,
        baseline=baseline_fb,
        actual_sot=None,
    )
    meta = row.get("meta") if isinstance(row.get("meta"), dict) else {}
    fb_map = meta.get("formula_fallbacks") if isinstance(meta.get("formula_fallbacks"), dict) else {}

    off_comp = compute_offensive_production_component(ctx, ctx.team_prior_fixtures)
    off_val = _safe_float(off_comp.get("value"))
    off_fb = bool(off_comp.get("fallbacks_used"))
    off_term = ResolvedFeature(
        key="offensive_production_component",
        label="Produzione offensiva (componente)",
        value=_r2(off_val),
        contribution=_r4(float(off_val or 0) * WEIGHT_OFFENSIVE) if off_val is not None else 0.0,
        weight=WEIGHT_OFFENSIVE,
        source_table="fixture_team_stats",
        source_field="blend_offensive_signals",
        api_source="fixtures/statistics + fixtures.goals",
        source_path="v10:offensive_production_blend",
        sample_count=ctx.team_prior_count,
        fallback_used=off_fb,
        fallback_reason="; ".join(off_comp.get("fallbacks_used") or []) if off_fb else None,
        status="fallback" if off_fb else ("available" if off_val is not None else "missing"),
        formula="blend componente offensiva × 0.30",
        inputs=off_comp.get("inputs") if isinstance(off_comp.get("inputs"), dict) else {},
    )

    mappings: list[tuple[str, str, str, str]] = [
        (
            "opp_avg_sot_conceded",
            "opponent_season_avg_sot_conceded",
            "fixture_team_stats.shots_on_target (concessi avversario, media stagione)",
            "opponent_season_avg_sot_conceded",
        ),
        (
            "team_split_avg_sot_for",
            "home_away_avg_sot_for",
            "fixture_team_stats.shots_on_target (split casa/trasferta)",
            "home_away_avg_sot_for",
        ),
        (
            "opp_split_avg_sot_conceded",
            "opponent_home_away_avg_sot_conceded",
            "fixture_team_stats.shots_on_target (concessi avversario split)",
            "opponent_home_away_avg_sot_conceded",
        ),
        (
            "team_last5_avg_sot_for",
            "last5_avg_sot_for",
            "fixture_team_stats.shots_on_target (ultime 5)",
            "last5_avg_sot_for",
        ),
        (
            "opp_last5_avg_sot_conceded",
            "opponent_last5_avg_sot_conceded",
            "fixture_team_stats.shots_on_target (concessi avversario ultime 5)",
            "opponent_last5_avg_sot_conceded",
        ),
    ]

    terms: list[ResolvedFeature] = [off_term]
    for key, row_key, spath, fb_key in mappings:
        spec = formula_term_spec_by_key(key)
        val = _safe_float(row.get(row_key))
        fb = bool(fb_map.get(fb_key))
        reason = "sample insufficiente o dato non disponibile" if fb else None
        terms.append(
            _term_from_row_features(
                key=key,
                label=spec.label if spec else key,
                value=val,
                weight=spec.default_weight if spec else 0.1,
                source_path=spath,
                source_field="shots_on_target",
                sample_count=ctx.opponent_prior_count if "opp" in key else ctx.team_prior_count,
                fallback_used=fb,
                fallback_reason=reason,
                formula=spec.formula if spec else "",
            ),
        )

    return terms, {"row_features": row, "offensive_component": off_comp}


def resolve_expected_goals_term(
    db: Session,
    ctx: V10PriorContext,
    *,
    base_explicit_sot: float,
) -> tuple[ResolvedFeature, dict[str, Any], float]:
    xg_comp, adj = compute_xg_adjustment_for_side(
        db,
        season_id=ctx.season_id,
        cutoff_kickoff=ctx.cutoff_kickoff,
        cutoff_fixture_id=ctx.cutoff_fixture_id,
        team_id=ctx.team_id,
        opponent_id=ctx.opponent_id,
        base_explicit_sot=float(base_explicit_sot),
    )
    applied = bool(xg_comp.get("xg_adjustment_applied"))
    fb = bool(xg_comp.get("fallback_used")) or not applied
    spec = EXPECTED_GOALS_SPEC
    return (
        ResolvedFeature(
            key="expected_goals",
            label=spec.label,
            value=_r2(_safe_float(xg_comp.get("team_avg_xg_for"))),
            contribution=_r4(float(adj) if applied else 0.0),
            weight=spec.default_weight,
            source_table=spec.source_table,
            source_field=spec.source_field,
            api_source=spec.api_source,
            source_path="fixture_team_stats.expected_goals",
            sample_count=int(xg_comp.get("team_xg_sample_matches") or 0),
            fallback_used=fb,
            fallback_reason=str(xg_comp.get("fallback_reason") or "") or None,
            status="available" if applied else "fallback",
            formula=spec.formula,
        ),
        xg_comp,
        float(adj),
    )


def assess_formula_quality(terms: list[ResolvedFeature]) -> dict[str, Any]:
    warnings: list[str] = []
    base = [t for t in terms if t.key != "expected_goals"]
    by_val: dict[float, list[ResolvedFeature]] = {}
    for t in base:
        if t.value is None:
            continue
        fv = round(float(t.value), 4)
        by_val.setdefault(fv, []).append(t)

    for val, group in by_val.items():
        if len(group) < 4:
            continue
        if all(t.fallback_used for t in group):
            continue
        paths = {t.source_path for t in group}
        if len(paths) > 1:
            warnings.append(
                "Valori coincidenti ma provenienti da fonti diverse.",
            )
        else:
            warnings.append(DUPLICATE_VALUES_WARNING)

    critical = sum(1 for t in base if t.fallback_used and t.key != "offensive_production_component")
    if critical > 0:
        warnings.append(f"{critical} termini base con fallback o valore mancante")

    status = "needs_review" if warnings else "ok"
    if any(t.value is None for t in base):
        status = "needs_review"
    return {"formula_quality_status": status, "formula_quality_warnings": warnings}


def resolve_side_features(
    db: Session,
    fixture: Fixture,
    *,
    team_id: int,
    opponent_id: int,
) -> dict[str, Any]:
    ctx = build_prior_context(db, fixture, team_id=team_id, opponent_id=opponent_id)
    base_terms, meta = resolve_all_base_terms(ctx)
    base_sum = round(sum(t.contribution for t in base_terms), 2)
    xg_term, xg_comp, xg_adj = resolve_expected_goals_term(db, ctx, base_explicit_sot=base_sum)
    all_terms = base_terms + [xg_term]
    quality = assess_formula_quality(all_terms)
    return {
        "context": ctx,
        "base_terms": base_terms,
        "xg_term": xg_term,
        "xg_component": xg_comp,
        "xg_adjustment_sot": xg_adj,
        "base_explicit_sot": base_sum,
        "final_sot": round(base_sum + xg_adj, 2),
        "quality_meta": quality,
        "offensive_component": meta.get("offensive_component"),
        "row_features": meta.get("row_features"),
    }
