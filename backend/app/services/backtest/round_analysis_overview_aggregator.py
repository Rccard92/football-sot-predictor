"""Aggregazione overview modelli da fixture persistite."""

from __future__ import annotations

from typing import Any

from app.schemas.backtest_round_analysis import DEFAULT_ROUND_ANALYSIS_MODELS, MODEL_LABELS
from app.services.backtest.round_analysis_aggregator import _hit_rate, _mean, _round4
from app.services.backtest.round_analysis_mode_stats import (
    count_play_mode,
    reliability_score,
    sample_status,
    trend_direction,
)
from app.services.backtest.round_analysis_preflight import model_block_is_error, model_block_is_no_prediction


def _fixture_row_dict_from_orm(row: Any) -> dict[str, Any]:
    return {
        "status": row.status,
        "actual_total_sot": row.actual_total_sot,
        "models_json": dict(row.models_json or {}),
        "explanation_json": dict(row.explanation_json or {}),
        "fixture_id": int(row.fixture_id),
        "home_team_name": row.home_team_name,
        "away_team_name": row.away_team_name,
    }


def _finalize_mode_simple(wins: int, losses: int) -> dict[str, Any]:
    hr = _hit_rate(wins, losses)
    plays = wins + losses
    display = f"{wins}/{plays} · {hr:.1f}%" if plays > 0 and hr is not None else "0/0 · —"
    return {
        "plays": plays,
        "wins": wins,
        "losses": losses,
        "hit_rate": hr,
        "display": display,
    }


def _empty_mode_acc() -> dict[str, int]:
    return {
        "adv_plays": 0,
        "adv_wins": 0,
        "adv_losses": 0,
        "calc_plays": 0,
        "calc_wins": 0,
        "calc_losses": 0,
        "giocha": 0,
        "non_giocare": 0,
        "borderline": 0,
    }


def _accumulate_mode(acc: dict[str, int], part: dict[str, Any]) -> None:
    advised = part.get("advised") or {}
    calculated = part.get("calculated") or {}
    acc["adv_plays"] += int(advised.get("plays") or 0)
    acc["adv_wins"] += int(advised.get("wins") or 0)
    acc["adv_losses"] += int(advised.get("losses") or 0)
    acc["calc_plays"] += int(calculated.get("plays") or 0)
    acc["calc_wins"] += int(calculated.get("wins") or 0)
    acc["calc_losses"] += int(calculated.get("losses") or 0)
    counts = part.get("advice_counts") or {}
    acc["giocha"] += int(counts.get("GIOCA") or 0)
    acc["non_giocare"] += int(counts.get("NON GIOCARE") or 0)
    acc["borderline"] += int(counts.get("BORDERLINE") or 0)


def _mode_from_acc(acc: dict[str, int]) -> dict[str, Any]:
    adv = _finalize_mode_simple(acc["adv_wins"], acc["adv_losses"])
    calc = _finalize_mode_simple(acc["calc_wins"], acc["calc_losses"])
    return {
        **adv,
        "advised": adv,
        "calculated": calc,
        "advice_counts": {
            "GIOCA": acc["giocha"],
            "NON GIOCARE": acc["non_giocare"],
            "BORDERLINE": acc["borderline"],
        },
    }


def summarize_model_from_fixtures(
    model_key: str,
    fixture_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    agg_acc = _empty_mode_acc()
    caut_acc = _empty_mode_acc()
    abs_errors: list[float] = []
    errors_signed: list[float] = []
    fixtures_ok = 0

    for row in fixture_rows:
        if row.get("status") != "ok":
            continue
        block = (row.get("models_json") or {}).get(model_key)
        if not isinstance(block, dict):
            continue
        if model_block_is_error(block) or model_block_is_no_prediction(block):
            continue
        fixtures_ok += 1
        _accumulate_mode(agg_acc, count_play_mode(block, "aggressive"))
        _accumulate_mode(caut_acc, count_play_mode(block, "cautious"))
        pt = block.get("predicted_total_sot")
        at = row.get("actual_total_sot")
        if pt is not None and at is not None:
            err = float(pt) - float(at)
            errors_signed.append(err)
            abs_errors.append(abs(err))

    aggressive = _mode_from_acc(agg_acc)
    cautious = _mode_from_acc(caut_acc)
    advised_total = int(agg_acc["giocha"]) + int(caut_acc["giocha"])
    rel = reliability_score(cautious.get("hit_rate"), aggressive.get("hit_rate"))

    return {
        "model_key": model_key,
        "label": MODEL_LABELS.get(model_key, model_key),
        "fixtures_analyzed": fixtures_ok,
        "aggressive": aggressive,
        "cautious": cautious,
        "reliability_score": rel,
        "sample_status": sample_status(advised_total),
        "mae": _mean(abs_errors),
        "bias": _mean(errors_signed),
        "advised_plays_total": advised_total,
    }


def round_model_chips_from_summary(model_summary: dict[str, Any]) -> dict[str, dict[str, Any]]:
    chips: dict[str, dict[str, Any]] = {}
    for key, block in (model_summary or {}).items():
        if not isinstance(block, dict):
            continue
        cw = int(block.get("cautious_wins") or 0)
        cl = int(block.get("cautious_losses") or 0)
        aw = int(block.get("aggressive_wins") or 0)
        al = int(block.get("aggressive_losses") or 0)
        c_dec = cw + cl
        a_dec = aw + al
        chr_ = _hit_rate(cw, cl)
        ahr = _hit_rate(aw, al)
        chips[key] = {
            "cautious_display": f"C {cw}/{c_dec} {chr_:.0f}%" if c_dec and chr_ is not None else "C —",
            "aggressive_display": f"A {aw}/{a_dec} {ahr:.0f}%" if a_dec and ahr is not None else "A —",
            "cautious_hit_rate": chr_,
            "aggressive_hit_rate": ahr,
        }
    return chips


def compute_ranking(models: dict[str, dict[str, Any]]) -> dict[str, Any]:
    items = list(models.values())
    if not items:
        return {}

    def _cautious_hit(m: dict[str, Any]) -> float:
        return float((m.get("cautious") or {}).get("hit_rate") or -1.0)

    def _aggressive_hit(m: dict[str, Any]) -> float:
        return float((m.get("aggressive") or {}).get("hit_rate") or -1.0)

    def _mae(m: dict[str, Any]) -> float:
        v = m.get("mae")
        return float(v) if v is not None else 999.0

    def _bias_abs(m: dict[str, Any]) -> float:
        v = m.get("bias")
        return abs(float(v)) if v is not None else 999.0

    best_cautious = max(items, key=_cautious_hit)
    best_aggressive = max(items, key=_aggressive_hit)
    best_mae = min(items, key=_mae)
    best_bias = min(items, key=_bias_abs)
    best_reliability = max(items, key=lambda m: float(m.get("reliability_score") or -1.0))

    return {
        "label": "provvisorio",
        "best_cautious": best_cautious.get("model_key"),
        "best_aggressive": best_aggressive.get("model_key"),
        "best_mae": best_mae.get("model_key"),
        "best_bias": best_bias.get("model_key"),
        "best_reliability": best_reliability.get("model_key"),
    }


def compute_trend_last_5(
    model_key: str,
    analyses_with_fixtures: list[tuple[Any, list[dict[str, Any]]]],
) -> dict[str, Any]:
    """analyses_with_fixtures: [(analysis, fixture_rows)], sorted by round_number asc."""
    if not analyses_with_fixtures:
        return {"hit_rate": None, "direction": "flat", "rounds": []}

    sorted_items = sorted(analyses_with_fixtures, key=lambda x: int(x[0].round_number))
    last5 = sorted_items[-5:]
    round_hits: list[tuple[int, float | None]] = []

    for analysis, rows in last5:
        summary = summarize_model_from_fixtures(model_key, rows)
        caut = summary.get("cautious") or {}
        advised = caut.get("advised") or {}
        agg_adv = (summary.get("aggressive") or {}).get("advised") or {}
        cw = int(advised.get("wins") or 0)
        cl = int(advised.get("losses") or 0)
        aw = int(agg_adv.get("wins") or 0)
        al = int(agg_adv.get("losses") or 0)
        total_w = cw + aw
        total_l = cl + al
        hr = _hit_rate(total_w, total_l)
        round_hits.append((int(analysis.round_number), hr))

    rounds = [r for r, _ in round_hits]
    current = round_hits[-1][1] if round_hits else None
    previous = round_hits[-2][1] if len(round_hits) >= 2 else None
    return {
        "hit_rate": current,
        "direction": trend_direction(current, previous),
        "rounds": rounds,
    }


def build_overview_payload(
    *,
    competition_id: int,
    season_year: int,
    season_label: str,
    use_latest_version_per_round: bool,
    model_keys: list[str],
    analyses: list[Any],
    fixtures_by_analysis_id: dict[int, list[Any]],
) -> dict[str, Any]:
    all_fixture_rows: list[dict[str, Any]] = []
    analyses_with_fixtures: list[tuple[Any, list[dict[str, Any]]]] = []

    for analysis in analyses:
        rows = [
            _fixture_row_dict_from_orm(r)
            for r in fixtures_by_analysis_id.get(int(analysis.id), [])
        ]
        analyses_with_fixtures.append((analysis, rows))
        all_fixture_rows.extend(rows)

    models_out: dict[str, Any] = {}
    for model_key in model_keys:
        summary = summarize_model_from_fixtures(model_key, all_fixture_rows)
        summary["rounds_count"] = len(analyses)
        summary["trend_last_5_rounds"] = compute_trend_last_5(
            model_key,
            analyses_with_fixtures,
        )
        models_out[model_key] = summary

    rounds_out: list[dict[str, Any]] = []
    for analysis in sorted(analyses, key=lambda a: int(a.round_number), reverse=True):
        ms = dict(analysis.model_summary_json or {})
        dq = analysis.data_quality_summary_json if isinstance(
            analysis.data_quality_summary_json,
            dict,
        ) else {}
        rounds_out.append(
            {
                "analysis_id": int(analysis.id),
                "round_number": int(analysis.round_number),
                "analysis_version": int(analysis.analysis_version),
                "status": str(analysis.status),
                "total_fixtures": int(analysis.total_fixtures),
                "processed_fixtures": int(analysis.processed_fixtures),
                "data_quality_badge": dq.get("badge"),
                "models": round_model_chips_from_summary(ms),
            },
        )

    return {
        "competition_id": competition_id,
        "season_year": season_year,
        "season_label": season_label,
        "use_latest_version_per_round": use_latest_version_per_round,
        "rounds_analyzed": len(analyses),
        "fixtures_analyzed": len([r for r in all_fixture_rows if r.get("status") == "ok"]),
        "models": models_out,
        "rounds": rounds_out,
        "ranking": compute_ranking(models_out),
    }
