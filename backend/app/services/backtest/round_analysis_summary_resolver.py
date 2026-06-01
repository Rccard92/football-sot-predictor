"""Risoluzione model summary e chip accordion da fixture persistiti."""

from __future__ import annotations

from typing import Any, Literal

from app.services.backtest.round_analysis_aggregator import RoundAnalysisAggregator, _hit_rate
from app.services.backtest.round_analysis_mode_stats import count_play_mode
from app.services.backtest.round_analysis_preflight import model_block_is_error, model_block_is_no_prediction

Completeness = Literal["ok", "stale", "empty"]
SummarySource = Literal["persisted", "rebuilt_from_fixtures"]

STALE_MESSAGE = "Analisi creata con una versione precedente o risultati incompleti."

_COMPLETED = frozenset({"completed", "completed_with_warnings"})


def is_advised_label(raw: str | None) -> bool:
    if not raw:
        return False
    norm = str(raw).strip().upper()
    return norm in {"GIOCA", "PLAY"}


def advice_bucket(raw: str | None) -> str:
    if not raw:
        return ""
    norm = str(raw).strip().upper()
    if norm in {"GIOCA", "PLAY"}:
        return "GIOCA"
    if norm in {"NON GIOCARE", "NO_PLAY", "NO PLAY"}:
        return "NON GIOCARE"
    if norm == "BORDERLINE":
        return "BORDERLINE"
    return norm


def fixture_rows_from_orm(rows: list[Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in rows:
        out.append(
            {
                "status": row.status,
                "actual_total_sot": row.actual_total_sot,
                "models_json": dict(row.models_json or {}),
                "explanation_json": dict(row.explanation_json or {}),
                "fixture_id": int(row.fixture_id),
                "home_team_name": row.home_team_name,
                "away_team_name": row.away_team_name,
            },
        )
    return out


def _count_fixture_predictions(rows: list[dict[str, Any]], model_keys: list[str]) -> int:
    n = 0
    for row in rows:
        if row.get("status") != "ok":
            continue
        for key in model_keys:
            block = (row.get("models_json") or {}).get(key)
            if not isinstance(block, dict):
                continue
            if model_block_is_error(block) or model_block_is_no_prediction(block):
                continue
            if block.get("predicted_total_sot") is not None:
                n += 1
    return n


def _count_decided_outcomes(rows: list[dict[str, Any]], model_keys: list[str]) -> int:
    n = 0
    for row in rows:
        if row.get("status") != "ok":
            continue
        for key in model_keys:
            block = (row.get("models_json") or {}).get(key)
            if not isinstance(block, dict):
                continue
            for mode in ("aggressive", "cautious"):
                if block.get(f"{mode}_outcome") in ("WIN", "LOSS"):
                    n += 1
    return n


def is_summary_usable(
    model_summary: dict[str, Any] | None,
    rows: list[dict[str, Any]],
    model_keys: list[str],
) -> bool:
    ms = model_summary if isinstance(model_summary, dict) else {}
    if not ms:
        return False

    fixture_preds = _count_fixture_predictions(rows, model_keys)
    decided = _count_decided_outcomes(rows, model_keys)

    total_wl = 0
    total_preds = 0
    for key in model_keys:
        block = ms.get(key)
        if not isinstance(block, dict):
            continue
        aw = int(block.get("aggressive_wins") or 0)
        al = int(block.get("aggressive_losses") or 0)
        cw = int(block.get("cautious_wins") or 0)
        cl = int(block.get("cautious_losses") or 0)
        total_wl += aw + al + cw + cl
        total_preds += int(block.get("predictions_available") or 0)

    if decided > 0 and total_wl > 0:
        return True
    if fixture_preds > 0 and total_preds > 0:
        return True
    return False


def resolve_model_summary(
    *,
    model_summary: dict[str, Any] | None,
    rows: list[dict[str, Any]],
    model_keys: list[str],
) -> tuple[dict[str, Any], SummarySource]:
    if is_summary_usable(model_summary, rows, model_keys):
        return dict(model_summary or {}), "persisted"
    agg = RoundAnalysisAggregator()
    rebuilt = agg.build_model_summary(models=model_keys, fixture_results=rows)
    return rebuilt, "rebuilt_from_fixtures"


def build_round_model_chips(
    rows: list[dict[str, Any]],
    model_keys: list[str],
) -> dict[str, dict[str, Any]]:
    chips: dict[str, dict[str, Any]] = {}
    for model_key in model_keys:
        calc_agg = {"wins": 0, "losses": 0}
        calc_caut = {"wins": 0, "losses": 0}
        for row in rows:
            if row.get("status") != "ok":
                continue
            block = (row.get("models_json") or {}).get(model_key)
            if not isinstance(block, dict):
                continue
            if model_block_is_error(block) or model_block_is_no_prediction(block):
                continue
            agg = count_play_mode(block, "aggressive")
            caut = count_play_mode(block, "cautious")
            ca = agg.get("calculated") or {}
            cc = caut.get("calculated") or {}
            calc_agg["wins"] += int(ca.get("wins") or 0)
            calc_agg["losses"] += int(ca.get("losses") or 0)
            calc_caut["wins"] += int(cc.get("wins") or 0)
            calc_caut["losses"] += int(cc.get("losses") or 0)

        cw = calc_caut["wins"]
        cl = calc_caut["losses"]
        aw = calc_agg["wins"]
        al = calc_agg["losses"]
        c_dec = cw + cl
        a_dec = aw + al
        chr_ = _hit_rate(cw, cl)
        ahr = _hit_rate(aw, al)
        chips[model_key] = {
            "cautious_display": f"C {cw}/{c_dec} {chr_:.0f}%" if c_dec and chr_ is not None else "C —",
            "aggressive_display": f"A {aw}/{a_dec} {ahr:.0f}%" if a_dec and ahr is not None else "A —",
            "cautious_hit_rate": chr_,
            "aggressive_hit_rate": ahr,
        }
    return chips


def analysis_completeness(
    *,
    status: str,
    rows: list[dict[str, Any]],
    model_keys: list[str],
    model_summary: dict[str, Any] | None,
) -> Completeness:
    if status not in _COMPLETED:
        return "empty"

    decided = _count_decided_outcomes(rows, model_keys)
    preds = _count_fixture_predictions(rows, model_keys)

    if preds == 0 and decided == 0:
        return "empty"

    resolved, source = resolve_model_summary(
        model_summary=model_summary,
        rows=rows,
        model_keys=model_keys,
    )
    chips = build_round_model_chips(rows, model_keys)
    has_chip = any(
        "—" not in str((chips.get(k) or {}).get("cautious_display", "—"))
        or "—" not in str((chips.get(k) or {}).get("aggressive_display", "—"))
        for k in model_keys
    )

    if has_chip or (preds > 0 and any(
        isinstance(resolved.get(k), dict) and int((resolved.get(k) or {}).get("predictions_available") or 0) > 0
        for k in model_keys
    )):
        return "ok"

    if preds > 0 or decided > 0:
        return "stale"

    if source == "rebuilt_from_fixtures":
        return "stale"

    return "empty"


def resolve_round_display(
    *,
    status: str,
    model_summary: dict[str, Any] | None,
    rows: list[dict[str, Any]],
    model_keys: list[str],
) -> dict[str, Any]:
    summary, source = resolve_model_summary(
        model_summary=model_summary,
        rows=rows,
        model_keys=model_keys,
    )
    completeness = analysis_completeness(
        status=status,
        rows=rows,
        model_keys=model_keys,
        model_summary=model_summary,
    )
    return {
        "model_summary": summary,
        "model_chips": build_round_model_chips(rows, model_keys),
        "summary_source": source,
        "completeness": completeness,
        "stale_message": STALE_MESSAGE if completeness in ("stale", "empty") and status in _COMPLETED else None,
    }
