"""Consiglio giocata SOT — trasforma previsioni in linee Over statistiche/caute (solo descrittivo)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Literal

from app.services.sot_model_registry import label_for_model

MarketType = Literal["match_total_sot", "home_team_sot", "away_team_sot"]

MATCH_TOTAL_LINES: list[float] = [
    3.5,
    4.5,
    5.5,
    6.5,
    7.5,
    8.5,
    9.5,
    10.5,
    11.5,
    12.5,
]

TEAM_SOT_LINES: list[float] = [1.5, 2.5, 3.5, 4.5, 5.5, 6.5, 7.5]

CAUTIOUS_MARGIN = 0.75


@dataclass
class AdviceContext:
    model_version: str | None = None
    lineup_confidence_label: str | None = None
    sportapi_confirmed: bool | None = None
    sportapi_fetched_at: str | None = None
    profiles_missing: bool = False
    statistical_margin: float | None = None


def lines_for_market(market_type: MarketType) -> list[float]:
    if market_type == "match_total_sot":
        return list(MATCH_TOTAL_LINES)
    return list(TEAM_SOT_LINES)


def statistical_line(predicted: float, lines: list[float]) -> float | None:
    """Linea più alta strettamente inferiore alla previsione."""
    valid = [ln for ln in lines if ln < predicted]
    return max(valid) if valid else None


def cautious_line(predicted: float, lines: list[float], margin: float = CAUTIOUS_MARGIN) -> float | None:
    """Linea più alta con predicted - line >= margin."""
    valid = [ln for ln in lines if predicted - ln >= margin]
    return max(valid) if valid else None


def risk_label(margin: float | None) -> str | None:
    if margin is None:
        return None
    if margin < 0.25:
        return "Molto tirata"
    if margin < 0.50:
        return "Aggressiva"
    if margin < 0.75:
        return "Moderata"
    if margin < 1.25:
        return "Buon margine"
    return "Forte margine"


def _round_margin(v: float | None) -> float | None:
    if v is None:
        return None
    return round(v, 2)


def format_over_pick(line: float | None) -> str | None:
    if line is None:
        return None
    return f"Over {line} SOT"


def advice_confidence_label(ctx: AdviceContext) -> str:
    score = 50.0

    sm = ctx.statistical_margin
    if sm is not None:
        if sm >= 1.0:
            score += 18
        elif sm >= 0.75:
            score += 12
        elif sm >= 0.5:
            score += 6
        elif sm < 0.25:
            score -= 12

    lc = (ctx.lineup_confidence_label or "").lower()
    if lc == "alta":
        score += 14
    elif lc == "media":
        score += 4
    elif lc == "bassa":
        score -= 14

    if ctx.sportapi_confirmed is True:
        score += 10
    elif ctx.sportapi_confirmed is False:
        score -= 6

    if ctx.profiles_missing:
        score -= 12

    if ctx.sportapi_fetched_at:
        try:
            fetched = datetime.fromisoformat(ctx.sportapi_fetched_at.replace("Z", "+00:00"))
            if fetched.tzinfo is None:
                fetched = fetched.replace(tzinfo=timezone.utc)
            age_h = (datetime.now(timezone.utc) - fetched.astimezone(timezone.utc)).total_seconds() / 3600
            if age_h > 48:
                score -= 10
            elif age_h > 24:
                score -= 5
            elif age_h < 6:
                score += 5
        except (ValueError, TypeError):
            pass

    score = max(0.0, min(100.0, score))
    if score >= 70:
        return "Alta"
    if score >= 45:
        return "Media"
    return "Bassa"


def model_display_label(model_version: str | None) -> str:
    if not model_version:
        return "Modello automatico"
    return label_for_model(model_version)


def build_market_advice(
    market_type: MarketType,
    predicted_value: float | None,
    *,
    model_version: str | None = None,
    context: AdviceContext | None = None,
) -> dict[str, Any]:
    ctx = context or AdviceContext(model_version=model_version)
    lines = lines_for_market(market_type)

    if predicted_value is None or predicted_value <= 0:
        return {
            "market_type": market_type,
            "predicted_value": predicted_value,
            "lines": lines,
            "statistical_pick": None,
            "statistical_line": None,
            "statistical_margin": None,
            "statistical_risk": None,
            "cautious_pick": None,
            "cautious_line": None,
            "cautious_margin": None,
            "cautious_note": None,
            "confidence_label": "Bassa",
            "reasons": ["Previsione SOT non disponibile per questo mercato."],
        }

    pred = float(predicted_value)
    stat_ln = statistical_line(pred, lines)
    caut_ln = cautious_line(pred, lines)

    stat_margin = _round_margin(pred - stat_ln) if stat_ln is not None else None
    caut_margin = _round_margin(pred - caut_ln) if caut_ln is not None else None

    ctx.statistical_margin = stat_margin
    conf = advice_confidence_label(ctx)

    stat_pick = format_over_pick(stat_ln)
    caut_pick = format_over_pick(caut_ln)
    caut_note: str | None = None
    if stat_ln is not None and caut_ln is not None and stat_ln == caut_ln:
        caut_note = f"{caut_pick} — già con margine sufficiente"

    reasons: list[str] = []
    if stat_pick:
        reasons.append(f"Previsione {pred:.2f} SOT: giocata statistica sulla linea più vicina sotto la previsione.")
    else:
        reasons.append("Nessuna linea Over disponibile sotto la previsione per una giocata statistica.")
    if caut_pick and caut_ln != stat_ln:
        reasons.append(f"Giocata cauta con margine minimo di almeno {CAUTIOUS_MARGIN:.2f} SOT rispetto alla linea.")
    elif not caut_pick:
        reasons.append("Nessuna giocata cauta: margine di sicurezza insufficiente sulle linee disponibili.")

    return {
        "market_type": market_type,
        "predicted_value": round(pred, 2),
        "lines": lines,
        "statistical_pick": stat_pick,
        "statistical_line": stat_ln,
        "statistical_margin": stat_margin,
        "statistical_risk": risk_label(stat_margin) if stat_pick else None,
        "cautious_pick": caut_pick,
        "cautious_line": caut_ln,
        "cautious_margin": caut_margin,
        "cautious_note": caut_note,
        "confidence_label": conf,
        "reasons": reasons[:3],
    }


def build_fixture_betting_advice(
    home_sot: float | None,
    away_sot: float | None,
    *,
    model_version: str | None = None,
    context: AdviceContext | None = None,
    home_team_name: str | None = None,
    away_team_name: str | None = None,
) -> dict[str, Any]:
    ctx = context or AdviceContext(model_version=model_version)
    total: float | None = None
    if home_sot is not None and away_sot is not None:
        total = round(float(home_sot) + float(away_sot), 2)

    match_ctx = AdviceContext(
        model_version=ctx.model_version,
        lineup_confidence_label=ctx.lineup_confidence_label,
        sportapi_confirmed=ctx.sportapi_confirmed,
        sportapi_fetched_at=ctx.sportapi_fetched_at,
        profiles_missing=ctx.profiles_missing,
    )
    match_advice = build_market_advice("match_total_sot", total, model_version=model_version, context=match_ctx)
    if match_advice.get("statistical_margin") is not None:
        ctx.statistical_margin = match_advice["statistical_margin"]

    return {
        "model_version": model_version,
        "model_label": model_display_label(model_version),
        "home_team_name": home_team_name,
        "away_team_name": away_team_name,
        "match_total": match_advice,
        "home_team_sot": build_market_advice(
            "home_team_sot",
            home_sot,
            model_version=model_version,
            context=ctx,
        ),
        "away_team_sot": build_market_advice(
            "away_team_sot",
            away_sot,
            model_version=model_version,
            context=ctx,
        ),
    }


def build_betting_advice_compact(
    home_sot: float | None,
    away_sot: float | None,
    *,
    model_version: str | None = None,
    context: AdviceContext | None = None,
) -> dict[str, Any] | None:
    full = build_fixture_betting_advice(home_sot, away_sot, model_version=model_version, context=context)
    match = full.get("match_total") or {}
    if match.get("predicted_value") is None:
        return None
    return {
        "total_expected_sot": match.get("predicted_value"),
        "statistical_pick": match.get("statistical_pick"),
        "cautious_pick": match.get("cautious_pick"),
        "statistical_margin": match.get("statistical_margin"),
        "cautious_margin": match.get("cautious_margin"),
        "statistical_risk": match.get("statistical_risk"),
        "model_label": full.get("model_label"),
    }


def advice_context_from_explanation_payload(
    lineup_impact: dict[str, Any] | None,
    sportapi_lineups: dict[str, Any] | None,
) -> AdviceContext:
    li = lineup_impact or {}
    sa = sportapi_lineups or {}
    return AdviceContext(
        lineup_confidence_label=li.get("confidence_label"),
        sportapi_confirmed=sa.get("confirmed"),
        sportapi_fetched_at=sa.get("fetched_at"),
        profiles_missing=bool(li.get("profiles_missing")),
    )
