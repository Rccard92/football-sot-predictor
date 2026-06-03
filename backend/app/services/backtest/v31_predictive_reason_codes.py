"""Reason codes analitici deterministici per diagnosi fixture."""

from __future__ import annotations

from typing import Any


def _trace(row: dict[str, Any]) -> dict[str, Any]:
    t = row.get("trace")
    return t if isinstance(t, dict) else {}


def _trace_float(trace: dict[str, Any], key: str, default: float = 0.0) -> float:
    v = trace.get(key)
    if v is None:
        return default
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _code(
    code: str,
    label_it: str,
    evidence: str,
    suggested_action: str,
) -> dict[str, str]:
    return {
        "code": code,
        "label_it": label_it,
        "evidence": evidence,
        "suggested_action": suggested_action,
    }


def derive_outcome_type(row: dict[str, Any], reason_codes: list[dict[str, Any]]) -> str | None:
    """Mappa win_quality + reason codes al filtro UI outcome_type."""
    codes = {c.get("code") for c in reason_codes}
    wq = row.get("win_quality")
    if isinstance(wq, str) and wq:
        base = wq.lower()
        if "HIGH_TOTAL_MISSED" in codes:
            return "high_missed"
        if "FALSE_HIGH_PREDICTION" in codes:
            return "false_high_prediction"
        if "LOW_TOTAL_MISSED" in codes:
            return "low_missed"
        if wq == "HEALTHY_WIN":
            return "healthy_win"
        if wq == "UNDERSTATED_WIN":
            return "understated_win"
        if wq == "BAD_LOSS_OVERESTIMATION":
            return "bad_loss_overestimation"
        if wq == "EXTREME_WIN_OUTLIER":
            return "extreme_win_outlier"
        return base
    if "HIGH_TOTAL_MISSED" in codes:
        return "high_missed"
    if "FALSE_HIGH_PREDICTION" in codes:
        return "false_high_prediction"
    return None


def build_reason_codes(
    row: dict[str, Any],
    *,
    pattern_context: dict[str, Any] | None = None,
) -> list[dict[str, str]]:
    """Genera reason codes analitici (no AI)."""
    _ = pattern_context
    out: list[dict[str, str]] = []
    pred = row.get("predicted_total_sot")
    actual = row.get("actual_total_sot")
    if pred is None or actual is None:
        return out

    pred_f = float(pred)
    act_f = float(actual)
    err = float(row.get("error") if row.get("error") is not None else pred_f - act_f)
    abs_err = float(row.get("abs_error") if row.get("abs_error") is not None else abs(err))
    pb = row.get("predicted_bucket")
    ab = row.get("actual_bucket")
    abd = row.get("actual_bucket_dynamic")
    wq = row.get("win_quality")
    trace = _trace(row)
    boost = _trace_float(trace, "boost_applied")
    high_signal = _trace_float(trace, "high_total_signal")
    boost_reason = str(trace.get("boost_reason") or "")

    if wq == "EXTREME_WIN_OUTLIER" or abd == "extreme_total":
        out.append(
            _code(
                "OUTLIER_DO_NOT_CALIBRATE",
                "Outlier estremo",
                f"Actual bucket dinamico {abd}; errore {abs_err:.1f}.",
                "Escludere dalla calibrazione pesi; usare solo diagnostica.",
            ),
        )

    if err < -2.5 and ab in ("high_total", "very_high_total") and pb in ("normal_total", "low_total"):
        out.append(
            _code(
                "HIGH_TOTAL_MISSED",
                "High total non previsto",
                f"Pred {pred_f:.1f} ({pb}) vs actual {act_f:.1f} ({ab}).",
                "Rafforzare segnali high-total o boost dinamico selettivo.",
            ),
        )

    if err > 2.5 and pb in ("high_total", "very_high_total") and ab in ("normal_total", "low_total"):
        out.append(
            _code(
                "FALSE_HIGH_PREDICTION",
                "Falso positivo high",
                f"Sovrastima {err:.1f}; bucket pred {pb} vs actual {ab}.",
                "Stringere guardrail chaos/high guard.",
            ),
        )

    if err < -2.0 and pb in ("low_total", "normal_total") and ab in ("low_total",):
        out.append(
            _code(
                "LOW_TOTAL_MISSED",
                "Low total sottostimato",
                f"Actual basso ({act_f:.1f}) non catturato.",
                "Verificare cap difensivo e segnali ritmo.",
            ),
        )

    if err < -2.0 and boost < 0.3 and high_signal >= 55:
        out.append(
            _code(
                "BOOST_TOO_WEAK",
                "Boost insufficiente",
                f"high_total_signal={high_signal:.0f}, boost_applied={boost:.2f}.",
                "Aumentare tier boost o abbassare soglia attivazione.",
            ),
        )

    if err > 2.0 and (boost_reason.startswith("chaos") or boost > 0.8):
        out.append(
            _code(
                "CHAOS_FALSE_POSITIVE",
                "Chaos/ boost eccessivo",
                f"boost_reason={boost_reason or 'n/d'}, boost={boost:.2f}.",
                "Ridurre aggressività chaos_game o hybrid guard.",
            ),
        )

    if abs_err <= 1.0 and wq in ("HEALTHY_WIN", "CLOSE_LOSS", None):
        out.append(
            _code(
                "MODEL_OK",
                "Predizione solida",
                f"Errore assoluto {abs_err:.1f}.",
                "Nessuna azione; mantenere traccia come riferimento.",
            ),
        )

    if abs_err > 1.5 and abs(pred_f - act_f) > 0 and high_signal < 35 and pb == ab:
        out.append(
            _code(
                "MODEL_TOO_FLAT",
                "Modello troppo piatto",
                f"Segnale pre-match basso ({high_signal:.0f}) ma errore {abs_err:.1f}.",
                "Valutare variance_unlocked o feature ritmo.",
            ),
        )

    if wq == "BAD_LOSS_OVERESTIMATION":
        out.append(
            _code(
                "OVERESTIMATION_LOSS",
                "Perdita coverage per sovrastima",
                f"Errore {err:.1f}, win_quality={wq}.",
                "Ridurre bias positivo o cap totale.",
            ),
        )

    if wq == "UNDERSTATED_WIN":
        out.append(
            _code(
                "UNDERSTATED_WIN",
                "Vittoria coverage sottostimata",
                f"Actual {act_f:.1f} > pred {pred_f:.1f} di {act_f - pred_f:.1f}.",
                "Analizzare macro offensive non catturate.",
            ),
        )

    return out


def build_feature_snapshot(row: dict[str, Any]) -> dict[str, Any]:
    """Subset trace/macro per diagnosi (no leakage)."""
    trace = _trace(row)
    forbidden = {"actual_total_sot", "actual_home_sot", "actual_away_sot", "target", "decision"}
    snap: dict[str, Any] = {}
    for k in (
        "high_total_signal",
        "boost_applied",
        "boost_reason",
        "guardrail_blocked",
        "bias_offset_applied",
        "strategy_family",
    ):
        if k in trace:
            snap[k] = trace[k]
    macros = trace.get("macro_summary")
    if isinstance(macros, dict):
        snap["macro_summary"] = {k: v for k, v in macros.items() if k not in forbidden}
    return snap
