"""Spiegazioni cella-per-cella del Pannello KPI — audit snapshot-only.

Nessun ricalcolo operativo del modello Cecchino: legge solo dati persistiti
e produce audit_result diagnostici in-memory.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.models.cecchino_today_fixture import ELIGIBILITY_ELIGIBLE, CecchinoTodayFixture
from app.services.cecchino.cecchino_constants import (
    CECCHINO_1X2_WEIGHTS_VERSION,
    FINAL_QUOTA_WEIGHTS,
)
from app.services.cecchino.cecchino_goal_formulas import build_goal_market_debug
from app.services.cecchino.cecchino_kpi_panel_v2_betfair import (
    KPI_V2_VERSION,
    _compute_rating,
    _edge_pct,
    _prob_from_odd,
    normalize_kpi_panel_rows,
    rating_label,
)
from app.services.cecchino.cecchino_picchetti_debug import build_cecchino_picchetti_debug
from app.services.cecchino.cecchino_purchasability_snapshot import (
    build_candidate_and_compact_snapshot,
    index_purchasability_snapshot_by_market,
)
from app.services.cecchino.cecchino_purchasability_v2_snapshot import (
    build_candidate_and_compact_snapshot_v2,
    build_purchasability_comparison,
    index_purchasability_v2_snapshot_by_market,
)
from app.services.cecchino.cecchino_selection_keys import (
    SEL_AWAY,
    SEL_DRAW,
    SEL_DRAW_PT,
    SEL_HOME,
    SEL_ONE_TWO,
    SEL_ONE_X,
    SEL_OVER_1_5,
    SEL_OVER_2_5,
    SEL_OVER_PT_0_5,
    SEL_OVER_PT_1_5,
    SEL_UNDER_2_5,
    SEL_UNDER_3_5,
    SEL_UNDER_PT_1_5,
    SEL_X_TWO,
)

AUDIT_VERSION = "cecchino_kpi_explanations_v1"

EXCLUDED_METRICS = ("segno", "quota_book")

ANALYZABLE_METRICS = (
    "quota_cecchino",
    "prob_book",
    "prob_cecchino",
    "vantaggio_prob",
    "edge_pct",
    "score_acquisto",
    "rating",
    "historical_reliability",
    "purchasability",
    "purchasability_v1_1",
    "purchasability_v2",
    "purchasability_delta",
)

_METRIC_LABELS: dict[str, str] = {
    "quota_cecchino": "Quota Cecchino",
    "prob_book": "Probabilità Book",
    "prob_cecchino": "Probabilità Cecchino",
    "vantaggio_prob": "Vantaggio Probabilistico",
    "edge_pct": "Edge",
    "score_acquisto": "Score",
    "rating": "Rating",
    "historical_reliability": "Affidabilità",
    "purchasability": "Acquistabilità v1.1",
    "purchasability_v1_1": "Acquistabilità v1.1",
    "purchasability_v2": "Acquistabilità v2",
    "purchasability_delta": "Differenza V2−V1.1",
}

_1X2_KEYS = {SEL_HOME, SEL_DRAW, SEL_AWAY}
_DC_KEYS = {SEL_ONE_X, SEL_X_TWO, SEL_ONE_TWO}
_GOAL_KEYS = {
    SEL_OVER_1_5,
    SEL_OVER_2_5,
    SEL_UNDER_2_5,
    SEL_UNDER_3_5,
    SEL_UNDER_PT_1_5,
    SEL_OVER_PT_0_5,
    SEL_OVER_PT_1_5,
    SEL_DRAW_PT,
}

_DC_FORMULAS: dict[str, tuple[str, tuple[str, str], tuple[str, str]]] = {
    SEL_ONE_X: (
        "Quota 1X = 1 / (Probabilità 1 + Probabilità X)",
        ("prob_1", "prob_x"),
        ("quota_1", "quota_x"),
    ),
    SEL_X_TWO: (
        "Quota X2 = 1 / (Probabilità X + Probabilità 2)",
        ("prob_x", "prob_2"),
        ("quota_x", "quota_2"),
    ),
    SEL_ONE_TWO: (
        "Quota 12 = 1 / (Probabilità 1 + Probabilità 2)",
        ("prob_1", "prob_2"),
        ("quota_1", "quota_2"),
    ),
}


def _num(v: Any) -> float | None:
    if v is None or isinstance(v, bool):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _fmt_it(v: float | None, decimals: int = 2) -> str:
    if v is None:
        return "—"
    s = f"{v:.{decimals}f}"
    return s.replace(".", ",")


def _fmt_pct(v: float | None, *, from_decimal: bool = True, decimals: int = 2) -> str:
    if v is None:
        return "—"
    pct = v * 100.0 if from_decimal else v
    return f"{_fmt_it(pct, decimals)}%"


def _input(
    *,
    key: str,
    label: str,
    value: Any,
    display_value: str | None = None,
    source_path: str,
    source_type: str = "persisted_snapshot",
    timestamp: str | None = None,
) -> dict[str, Any]:
    out: dict[str, Any] = {
        "key": key,
        "label": label,
        "value": value,
        "display_value": display_value if display_value is not None else (
            _fmt_it(_num(value)) if _num(value) is not None else (
                str(value) if value is not None else "—"
            )
        ),
        "source_path": source_path,
        "source_type": source_type,
    }
    if timestamp:
        out["timestamp"] = timestamp
    return out


def _consistency(
    stored: Any,
    audit: Any,
    *,
    abs_tol: float,
    rounding_tol: float | None = None,
) -> dict[str, Any]:
    if stored is None and audit is None:
        return {"status": "unavailable", "delta": None}
    if stored is None or audit is None:
        return {"status": "not_verifiable", "delta": None}
    try:
        s = float(stored)
        a = float(audit)
    except (TypeError, ValueError):
        return {"status": "not_verifiable", "delta": None}
    delta = a - s
    if abs(delta) <= abs_tol:
        return {"status": "match", "delta": round(delta, 10)}
    rt = rounding_tol if rounding_tol is not None else abs_tol * 5
    if abs(delta) <= rt:
        return {"status": "rounding_match", "delta": round(delta, 10)}
    return {"status": "mismatch", "delta": round(delta, 10)}


def _base_explanation(
    *,
    market_key: str,
    market_label: str,
    metric_key: str,
    status: str,
    calculation_type: str,
    description: str,
    purpose: str,
    formula_symbolic: str,
    formula_applied: list[str],
    inputs: list[dict[str, Any]],
    stored_result: Any,
    stored_result_display: str | None,
    audit_result: Any,
    consistency: dict[str, Any],
    rounding: dict[str, Any],
    formula_version: str,
    warnings: list[str] | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    out: dict[str, Any] = {
        "module": "kpi",
        "market_key": market_key,
        "market_label": market_label,
        "metric_key": metric_key,
        "metric_label": _METRIC_LABELS.get(metric_key, metric_key),
        "status": status,
        "calculation_type": calculation_type,
        "description": description,
        "purpose": purpose,
        "formula_symbolic": formula_symbolic,
        "formula_applied": formula_applied,
        "inputs": inputs,
        "stored_result": stored_result,
        "stored_result_display": stored_result_display,
        "audit_result": audit_result,
        "consistency": consistency,
        "rounding": rounding,
        "formula_version": formula_version,
        "warnings": list(warnings or []),
    }
    if extra:
        out.update(extra)
    return out


def _unavailable(
    *,
    market_key: str,
    market_label: str,
    metric_key: str,
    formula_symbolic: str,
    inputs: list[dict[str, Any]],
    reason: str,
    formula_version: str = KPI_V2_VERSION,
    description: str = "",
    purpose: str = "",
) -> dict[str, Any]:
    return _base_explanation(
        market_key=market_key,
        market_label=market_label,
        metric_key=metric_key,
        status="unavailable",
        calculation_type="derived",
        description=description or f"{_METRIC_LABELS.get(metric_key, metric_key)} non disponibile.",
        purpose=purpose or "Diagnostica del mancato calcolo.",
        formula_symbolic=formula_symbolic,
        formula_applied=[f"Risultato non disponibile: {reason}"],
        inputs=inputs,
        stored_result=None,
        stored_result_display="—",
        audit_result=None,
        consistency={"status": "unavailable", "delta": None},
        rounding={"policy": "n/a", "precision": None, "display_precision": None},
        formula_version=formula_version,
        warnings=[reason],
        extra={"unavailable_reason": reason},
    )


# ---------------------------------------------------------------------------
# Metric builders
# ---------------------------------------------------------------------------


def _explain_prob_book(row: dict[str, Any], market_label: str) -> dict[str, Any]:
    mk = str(row.get("market_key") or "")
    qb = _num(row.get("quota_book"))
    stored = _num(row.get("prob_book"))
    formula = "P_book = 1 / Q_book"
    inputs = [
        _input(
            key="quota_book",
            label="Quota Book",
            value=qb,
            display_value=_fmt_it(qb),
            source_path=f"kpi_panel_json.rows[{mk}].quota_book",
        ),
    ]
    if qb is None or qb <= 0:
        return _unavailable(
            market_key=mk,
            market_label=market_label,
            metric_key="prob_book",
            formula_symbolic=formula,
            inputs=inputs,
            reason="Quota Book assente o non valida",
            description=(
                "Probabilità implicita grezza della Quota Book (1/quota), "
                "senza rimozione del margine bookmaker."
            ),
            purpose="Confrontare la probabilità implicita del book con quella Cecchino.",
        )
    audit = _prob_from_odd(qb)
    applied = [
        f"P_book = 1 / {_fmt_it(qb)}",
        f"P_book = {_fmt_it(audit, 4)}",
        f"P_book = {_fmt_pct(audit)}",
    ]
    return _base_explanation(
        market_key=mk,
        market_label=market_label,
        metric_key="prob_book",
        status="available",
        calculation_type="derived",
        description=(
            "Probabilità implicita grezza della Quota Book (1/quota). "
            "Non è una probabilità normalizzata eliminando il margine bookmaker."
        ),
        purpose="Misura la probabilità implicita del book per confrontarla con Cecchino.",
        formula_symbolic=formula,
        formula_applied=applied,
        inputs=inputs,
        stored_result=stored,
        stored_result_display=_fmt_pct(stored),
        audit_result=audit,
        consistency=_consistency(stored, audit, abs_tol=1e-4, rounding_tol=5e-4),
        rounding={"policy": "round", "precision": 4, "display_precision": 2},
        formula_version=KPI_V2_VERSION,
    )


def _explain_prob_cecchino(row: dict[str, Any], market_label: str) -> dict[str, Any]:
    mk = str(row.get("market_key") or "")
    qc = _num(row.get("quota_cecchino"))
    stored = _num(row.get("prob_cecchino"))
    formula = "P_cecchino = 1 / Q_cecchino"
    inputs = [
        _input(
            key="quota_cecchino",
            label="Quota Cecchino",
            value=qc,
            display_value=_fmt_it(qc),
            source_path=f"kpi_panel_json.rows[{mk}].quota_cecchino",
        ),
    ]
    if qc is None or qc <= 0:
        return _unavailable(
            market_key=mk,
            market_label=market_label,
            metric_key="prob_cecchino",
            formula_symbolic=formula,
            inputs=inputs,
            reason="Quota Cecchino assente o non valida",
            description="Probabilità implicita della Quota Cecchino (1/quota).",
            purpose="Base per Vantaggio Prob., Score, Rating e confronti con il book.",
        )
    audit = _prob_from_odd(qc)
    applied = [
        f"P_cecchino = 1 / {_fmt_it(qc)}",
        f"P_cecchino = {_fmt_it(audit, 4)}",
        f"P_cecchino = {_fmt_pct(audit)}",
    ]
    return _base_explanation(
        market_key=mk,
        market_label=market_label,
        metric_key="prob_cecchino",
        status="available",
        calculation_type="derived",
        description="Probabilità implicita della Quota Cecchino (1/quota).",
        purpose="Base per Vantaggio Prob., Score, Rating e confronti con il book.",
        formula_symbolic=formula,
        formula_applied=applied,
        inputs=inputs,
        stored_result=stored,
        stored_result_display=_fmt_pct(stored),
        audit_result=audit,
        consistency=_consistency(stored, audit, abs_tol=1e-4, rounding_tol=5e-4),
        rounding={"policy": "round", "precision": 4, "display_precision": 2},
        formula_version=KPI_V2_VERSION,
    )


def _explain_vantaggio(row: dict[str, Any], market_label: str) -> dict[str, Any]:
    mk = str(row.get("market_key") or "")
    pc = _num(row.get("prob_cecchino"))
    pb = _num(row.get("prob_book"))
    stored = _num(row.get("vantaggio_prob"))
    formula = "Vantaggio Prob. = Probabilità Cecchino − Probabilità Book"
    inputs = [
        _input(
            key="prob_cecchino",
            label="Probabilità Cecchino",
            value=pc,
            display_value=_fmt_pct(pc),
            source_path=f"kpi_panel_json.rows[{mk}].prob_cecchino",
        ),
        _input(
            key="prob_book",
            label="Probabilità Book",
            value=pb,
            display_value=_fmt_pct(pb),
            source_path=f"kpi_panel_json.rows[{mk}].prob_book",
        ),
    ]
    if pc is None or pb is None:
        return _unavailable(
            market_key=mk,
            market_label=market_label,
            metric_key="vantaggio_prob",
            formula_symbolic=formula,
            inputs=inputs,
            reason="Probabilità Cecchino o Book mancante",
            description="Differenza tra probabilità Cecchino e probabilità Book.",
            purpose="Indica quanto il modello vede più (o meno) probabilità del book.",
        )
    audit = round(pc - pb, 4)
    applied = [
        f"Vantaggio = {_fmt_pct(pc)} − {_fmt_pct(pb)}",
        f"Vantaggio = {_fmt_it(audit, 4)} ({_fmt_pct(audit)} punti percentuali)",
    ]
    return _base_explanation(
        market_key=mk,
        market_label=market_label,
        metric_key="vantaggio_prob",
        status="available",
        calculation_type="derived",
        description="Differenza tra probabilità Cecchino e probabilità Book.",
        purpose="Indica quanto il modello vede più (o meno) probabilità del book.",
        formula_symbolic=formula,
        formula_applied=applied,
        inputs=inputs,
        stored_result=stored,
        stored_result_display=_fmt_pct(stored),
        audit_result=audit,
        consistency=_consistency(stored, audit, abs_tol=1e-4, rounding_tol=5e-4),
        rounding={"policy": "round", "precision": 4, "display_precision": 2},
        formula_version=KPI_V2_VERSION,
    )


def _explain_edge(row: dict[str, Any], market_label: str) -> dict[str, Any]:
    mk = str(row.get("market_key") or "")
    qb = _num(row.get("quota_book"))
    qc = _num(row.get("quota_cecchino"))
    stored = _num(row.get("edge_pct"))
    formula = "Edge % = (Quota Book / Quota Cecchino − 1) × 100"
    inputs = [
        _input(
            key="quota_book",
            label="Quota Book",
            value=qb,
            display_value=_fmt_it(qb),
            source_path=f"kpi_panel_json.rows[{mk}].quota_book",
        ),
        _input(
            key="quota_cecchino",
            label="Quota Cecchino",
            value=qc,
            display_value=_fmt_it(qc),
            source_path=f"kpi_panel_json.rows[{mk}].quota_cecchino",
        ),
    ]
    if qb is None or qc is None or qc <= 0:
        return _unavailable(
            market_key=mk,
            market_label=market_label,
            metric_key="edge_pct",
            formula_symbolic=formula,
            inputs=inputs,
            reason="Quota Book o Quota Cecchino mancante/non valida",
            description="Vantaggio percentuale della Quota Book rispetto alla Quota Cecchino.",
            purpose="Misura se la quota book è 'alta' rispetto alla stima Cecchino.",
        )
    audit = _edge_pct(qb, qc)
    ratio = qb / qc
    applied = [
        f"Rapporto = {_fmt_it(qb)} / {_fmt_it(qc)} = {_fmt_it(ratio, 4)}",
        f"Edge % = ({_fmt_it(ratio, 4)} − 1) × 100 = {_fmt_it(audit)}",
    ]
    return _base_explanation(
        market_key=mk,
        market_label=market_label,
        metric_key="edge_pct",
        status="available",
        calculation_type="derived",
        description="Vantaggio percentuale della Quota Book rispetto alla Quota Cecchino.",
        purpose="Misura se la quota book è 'alta' rispetto alla stima Cecchino.",
        formula_symbolic=formula,
        formula_applied=applied,
        inputs=inputs,
        stored_result=stored,
        stored_result_display=f"{_fmt_it(stored)}%",
        audit_result=audit,
        consistency=_consistency(stored, audit, abs_tol=0.01, rounding_tol=0.05),
        rounding={"policy": "round", "precision": 2, "display_precision": 2},
        formula_version=KPI_V2_VERSION,
    )


def _explain_score(row: dict[str, Any], market_label: str) -> dict[str, Any]:
    mk = str(row.get("market_key") or "")
    pc = _num(row.get("prob_cecchino"))
    edge = _num(row.get("edge_pct"))
    stored = _num(row.get("score_acquisto"))
    formula = "Score = Probabilità Cecchino × Edge % / 100"
    inputs = [
        _input(
            key="prob_cecchino",
            label="Probabilità Cecchino",
            value=pc,
            display_value=_fmt_pct(pc),
            source_path=f"kpi_panel_json.rows[{mk}].prob_cecchino",
        ),
        _input(
            key="edge_pct",
            label="Edge %",
            value=edge,
            display_value=f"{_fmt_it(edge)}%",
            source_path=f"kpi_panel_json.rows[{mk}].edge_pct",
        ),
    ]
    if pc is None or edge is None:
        return _unavailable(
            market_key=mk,
            market_label=market_label,
            metric_key="score_acquisto",
            formula_symbolic=formula,
            inputs=inputs,
            reason="Probabilità Cecchino o Edge mancante",
            description="Score di acquisto derivato da probabilità Cecchino e Edge.",
            purpose="Sintetizza probabilità e edge in un unico indicatore numerico.",
        )
    raw = pc * edge / 100.0
    audit = round(raw, 3)
    applied = [
        f"Score raw = {_fmt_it(pc, 4)} × {_fmt_it(edge)} / 100 = {_fmt_it(raw, 6)}",
        f"Score = {_fmt_it(audit, 3)}",
    ]
    return _base_explanation(
        market_key=mk,
        market_label=market_label,
        metric_key="score_acquisto",
        status="available",
        calculation_type="derived",
        description="Score di acquisto derivato da probabilità Cecchino e Edge.",
        purpose="Sintetizza probabilità e edge in un unico indicatore numerico.",
        formula_symbolic=formula,
        formula_applied=applied,
        inputs=inputs,
        stored_result=stored,
        stored_result_display=_fmt_it(stored, 3),
        audit_result=audit,
        consistency=_consistency(stored, audit, abs_tol=0.001, rounding_tol=0.005),
        rounding={"policy": "round", "precision": 3, "display_precision": 3},
        formula_version=KPI_V2_VERSION,
        extra={"raw_before_round": raw},
    )


def _explain_rating(row: dict[str, Any], market_label: str) -> dict[str, Any]:
    mk = str(row.get("market_key") or "")
    pc = _num(row.get("prob_cecchino"))
    vant = _num(row.get("vantaggio_prob"))
    edge = _num(row.get("edge_pct"))
    stored = row.get("rating")
    stored_n = _num(stored)
    formula = (
        "Rating grezzo = Probabilità Cecchino % × 0,5 "
        "+ Vantaggio Prob. (pp) × 2 + Edge %; poi clamp 0–100 e arrotondamento"
    )
    inputs = [
        _input(
            key="prob_cecchino",
            label="Probabilità Cecchino",
            value=pc,
            display_value=_fmt_pct(pc),
            source_path=f"kpi_panel_json.rows[{mk}].prob_cecchino",
        ),
        _input(
            key="vantaggio_prob",
            label="Vantaggio Prob.",
            value=vant,
            display_value=_fmt_pct(vant),
            source_path=f"kpi_panel_json.rows[{mk}].vantaggio_prob",
        ),
        _input(
            key="edge_pct",
            label="Edge %",
            value=edge,
            display_value=f"{_fmt_it(edge)}%",
            source_path=f"kpi_panel_json.rows[{mk}].edge_pct",
        ),
    ]
    if pc is None or vant is None or edge is None:
        return _unavailable(
            market_key=mk,
            market_label=market_label,
            metric_key="rating",
            formula_symbolic=formula,
            inputs=inputs,
            reason="Input Rating incompleti (prob, vantaggio o edge)",
            description="Rating 0–100 sintetico del mercato KPI.",
            purpose="Classificare rapidamente la qualità della selezione.",
        )
    prob_pct = pc * 100.0
    vant_pct = vant * 100.0
    comp_prob = prob_pct * 0.5
    comp_vant = vant_pct * 2.0
    comp_edge = edge
    raw = comp_prob + comp_vant + comp_edge
    clamped = max(0.0, min(100.0, raw))
    audit = _compute_rating(pc, vant, edge)
    klass = rating_label(audit)
    applied = [
        f"Componente probabilità = {_fmt_it(prob_pct)} × 0,5 = {_fmt_it(comp_prob)}",
        f"Componente vantaggio = {_fmt_it(vant_pct)} × 2 = {_fmt_it(comp_vant)}",
        f"Componente edge = {_fmt_it(comp_edge)}",
        f"Somma raw = {_fmt_it(raw)}",
        f"Clamp 0–100 = {_fmt_it(clamped)}",
        f"Rating arrotondato = {audit}",
        f"Classe = {klass}",
    ]
    return _base_explanation(
        market_key=mk,
        market_label=market_label,
        metric_key="rating",
        status="available",
        calculation_type="derived",
        description="Rating 0–100 sintetico del mercato KPI, con classe testuale.",
        purpose="Classificare rapidamente la qualità della selezione.",
        formula_symbolic=formula,
        formula_applied=applied,
        inputs=inputs,
        stored_result=int(stored_n) if stored_n is not None else stored,
        stored_result_display=(
            f"{int(stored_n)} ({row.get('rating_label') or rating_label(int(stored_n) if stored_n is not None else None) or '—'})"
            if stored_n is not None
            else "—"
        ),
        audit_result=audit,
        consistency=_consistency(stored_n, audit, abs_tol=0.0, rounding_tol=1.0),
        rounding={"policy": "round_int_clamp_0_100", "precision": 0, "display_precision": 0},
        formula_version=KPI_V2_VERSION,
        extra={
            "components": {
                "probability": round(comp_prob, 4),
                "vantaggio": round(comp_vant, 4),
                "edge": round(comp_edge, 4),
                "raw": round(raw, 4),
                "clamped": round(clamped, 4),
            },
            "rating_label": klass,
            "stored_rating_label": row.get("rating_label"),
        },
    )


def _explain_quota_cecchino_1x2(
    row: dict[str, Any],
    market_label: str,
    picchetti_debug: dict[str, Any],
) -> dict[str, Any]:
    mk = str(row.get("market_key") or "")
    stored = _num(row.get("quota_cecchino"))
    mkt = (picchetti_debug.get("markets") or {}).get(mk) or {}
    pics = mkt.get("picchetti") or []
    formula = (
        "Quota Cecchino =\n"
        "Quota Picchetto 1 × Peso 1\n"
        "+ Quota Picchetto 2 × Peso 2\n"
        "+ Quota Picchetto 3 × Peso 3\n"
        "+ Quota Picchetto 4 × Peso 4"
    )
    inputs: list[dict[str, Any]] = []
    applied: list[str] = []
    warnings: list[str] = []
    total = 0.0
    ok = True
    for i, p in enumerate(pics, start=1):
        if not isinstance(p, dict):
            ok = False
            continue
        name = str(p.get("name") or f"picchetto_{i}")
        odd = _num(p.get("odd"))
        weight = _num(p.get("weight")) or FINAL_QUOTA_WEIGHTS.get(name, 0.0)
        contrib = _num(p.get("weighted_contribution"))
        if contrib is None and odd is not None:
            contrib = round(odd * weight, 4)
        inputs.append(
            _input(
                key=f"picchetto_{name}",
                label=f"Picchetto {name}",
                value={
                    "odd": odd,
                    "weight": weight,
                    "probability": p.get("probability"),
                    "record_home": p.get("record_home"),
                    "record_away": p.get("record_away"),
                    "sample_home": p.get("sample_home"),
                    "sample_away": p.get("sample_away"),
                    "weighted_contribution": contrib,
                    "status": p.get("status"),
                },
                display_value=(
                    f"{_fmt_it(odd)} × {_fmt_it(weight * 100 if weight is not None else None, 0)}%"
                    if odd is not None and weight is not None
                    else "—"
                ),
                source_path=f"cecchino_output_json.picchetti[{name}]",
            )
        )
        if odd is None or weight is None or contrib is None:
            ok = False
            warnings.append(f"picchetto_incompleto:{name}")
            applied.append(f"{name}: dato incompleto")
            continue
        total += contrib
        applied.append(
            f"{_fmt_it(odd)} × {_fmt_it(weight * 100, 0)}% = {_fmt_it(contrib, 4)}"
        )
        for w in p.get("picchetto_warnings") or []:
            if isinstance(w, str):
                warnings.append(w)

    if not ok or not pics:
        return _unavailable(
            market_key=mk,
            market_label=market_label,
            metric_key="quota_cecchino",
            formula_symbolic=formula,
            inputs=inputs,
            reason="Picchetti incompleti o assenti per il calcolo Quota Cecchino 1/X/2",
            formula_version=CECCHINO_1X2_WEIGHTS_VERSION,
            description="Quota Cecchino 1/X/2 come media ponderata dei quattro picchetti.",
            purpose="Quota modello usata per probabilità, edge e rating.",
        )

    audit = round(total, 2)
    applied.append(f"Somma = {_fmt_it(total, 4)}")
    applied.append(f"Arrotondamento → {_fmt_it(audit)}")
    return _base_explanation(
        market_key=mk,
        market_label=market_label,
        metric_key="quota_cecchino",
        status="available",
        calculation_type="weighted_picchetti",
        description="Quota Cecchino 1/X/2 come media ponderata dei quattro picchetti.",
        purpose="Quota modello usata per probabilità, edge e rating.",
        formula_symbolic=formula,
        formula_applied=applied,
        inputs=inputs,
        stored_result=stored,
        stored_result_display=_fmt_it(stored),
        audit_result=audit,
        consistency=_consistency(stored, audit, abs_tol=0.01, rounding_tol=0.05),
        rounding={"policy": "round", "precision": 2, "display_precision": 2},
        formula_version=CECCHINO_1X2_WEIGHTS_VERSION,
        warnings=warnings,
        extra={
            "picchetti": pics,
            "weights_version": CECCHINO_1X2_WEIGHTS_VERSION,
            "final_odd_from_debug": mkt.get("final_odd"),
        },
    )


def _explain_quota_cecchino_dc(
    row: dict[str, Any],
    market_label: str,
    output: dict[str, Any],
) -> dict[str, Any]:
    mk = str(row.get("market_key") or "")
    stored = _num(row.get("quota_cecchino"))
    final = output.get("final") if isinstance(output.get("final"), dict) else {}
    formula, prob_keys, _quota_keys = _DC_FORMULAS[mk]
    p_a = _num(final.get(prob_keys[0]))
    p_b = _num(final.get(prob_keys[1]))
    inputs = [
        _input(
            key=prob_keys[0],
            label=prob_keys[0],
            value=p_a,
            display_value=_fmt_pct(p_a),
            source_path=f"cecchino_output_json.final.{prob_keys[0]}",
        ),
        _input(
            key=prob_keys[1],
            label=prob_keys[1],
            value=p_b,
            display_value=_fmt_pct(p_b),
            source_path=f"cecchino_output_json.final.{prob_keys[1]}",
        ),
    ]
    if p_a is None or p_b is None or (p_a + p_b) <= 0:
        return _unavailable(
            market_key=mk,
            market_label=market_label,
            metric_key="quota_cecchino",
            formula_symbolic=formula,
            inputs=inputs,
            reason="Probabilità 1X2 persistite incomplete per doppia chance",
            description="Quota Cecchino doppia chance derivata dalle probabilità 1/X/2.",
            purpose="Esporre le doppie chance coerenti con le probabilità finali 1X2.",
        )
    s = p_a + p_b
    audit = round(1.0 / s, 2)
    applied = [
        f"Somma probabilità = {_fmt_it(p_a, 4)} + {_fmt_it(p_b, 4)} = {_fmt_it(s, 4)}",
        f"Quota = 1 / {_fmt_it(s, 4)} = {_fmt_it(audit)}",
    ]
    return _base_explanation(
        market_key=mk,
        market_label=market_label,
        metric_key="quota_cecchino",
        status="available",
        calculation_type="derived_from_1x2",
        description="Quota Cecchino doppia chance derivata dalle probabilità 1/X/2 persistite.",
        purpose="Esporre le doppie chance coerenti con le probabilità finali 1X2.",
        formula_symbolic=formula,
        formula_applied=applied,
        inputs=inputs,
        stored_result=stored,
        stored_result_display=_fmt_it(stored),
        audit_result=audit,
        consistency=_consistency(stored, audit, abs_tol=0.01, rounding_tol=0.05),
        rounding={"policy": "round", "precision": 2, "display_precision": 2},
        formula_version=KPI_V2_VERSION,
    )


def _explain_quota_cecchino_goal(
    row: dict[str, Any],
    market_label: str,
    output: dict[str, Any],
) -> dict[str, Any]:
    mk = str(row.get("market_key") or "")
    stored = _num(row.get("quota_cecchino"))
    gm = output.get("goal_markets") if isinstance(output.get("goal_markets"), dict) else {}
    block = gm.get(mk) if isinstance(gm.get(mk), dict) else None
    formula = (
        "Quota goal da goal_markets persistiti: "
        "λ → Poisson → empirico → blend → shrink lega → clamp → odd = 1/p"
    )
    if not block:
        return _unavailable(
            market_key=mk,
            market_label=market_label,
            metric_key="quota_cecchino",
            formula_symbolic=formula,
            inputs=[],
            reason="Blocco goal_markets assente nello snapshot",
            description="Quota Cecchino mercati goal / X PT da calcolo Poisson-empirico persistito.",
            purpose="Quota modello goal senza ricostruire lo storico.",
        )
    dbg = build_goal_market_debug(block)
    summary = block.get("summary") if isinstance(block.get("summary"), dict) else {}
    final_odd = _num(block.get("final_odd"))
    final_p = _num(summary.get("final_probability") or summary.get("final_probability_raw"))
    formula_version = str(block.get("formula_version") or "goal_market_persisted")
    inputs = [
        _input(
            key="final_odd",
            label="Quota finale persistita",
            value=final_odd,
            display_value=_fmt_it(final_odd),
            source_path=f"cecchino_output_json.goal_markets[{mk}].final_odd",
        ),
        _input(
            key="final_probability",
            label="Probabilità finale",
            value=final_p,
            display_value=_fmt_pct(final_p),
            source_path=f"cecchino_output_json.goal_markets[{mk}].summary",
        ),
        _input(
            key="lambda",
            label="Lambda",
            value=summary.get("lambda"),
            display_value=str(summary.get("lambda")) if summary.get("lambda") is not None else "—",
            source_path=f"cecchino_output_json.goal_markets[{mk}].summary.lambda",
        ),
        _input(
            key="weights",
            label="Pesi",
            value=block.get("weights"),
            display_value="vedi dettaglio",
            source_path=f"cecchino_output_json.goal_markets[{mk}].weights",
        ),
    ]
    applied = [
        f"formula_version = {formula_version}",
        f"status campione = {block.get('status')}",
        f"probabilità finale = {_fmt_pct(final_p)}" if final_p is not None else "probabilità finale = —",
        f"quota finale = {_fmt_it(final_odd)}" if final_odd is not None else "quota finale = —",
    ]
    if final_odd is None:
        return _unavailable(
            market_key=mk,
            market_label=market_label,
            metric_key="quota_cecchino",
            formula_symbolic=formula,
            inputs=inputs,
            reason=f"Quota goal non disponibile (status={block.get('status')})",
            formula_version=formula_version,
            description="Quota Cecchino mercati goal / X PT da calcolo Poisson-empirico persistito.",
            purpose="Quota modello goal senza ricostruire lo storico.",
        )
    # Audit: se abbiamo probabilità, ripeti odd = 1/p arrotondato; altrimenti not_verifiable.
    audit = round(1.0 / final_p, 2) if final_p is not None and final_p > 0 else None
    cons = (
        _consistency(stored, audit, abs_tol=0.01, rounding_tol=0.05)
        if audit is not None
        else _consistency(stored, final_odd, abs_tol=0.01, rounding_tol=0.05)
    )
    if audit is None:
        cons = {"status": "not_verifiable", "delta": None}
        audit_result = final_odd
    else:
        audit_result = audit
        applied.append(f"audit odd = 1 / {_fmt_it(final_p, 4)} → {_fmt_it(audit)}")

    return _base_explanation(
        market_key=mk,
        market_label=market_label,
        metric_key="quota_cecchino",
        status="available" if stored is not None else "partial",
        calculation_type="goal_market_persisted",
        description="Quota Cecchino mercati goal / X PT dal blocco goal_markets persistito.",
        purpose="Quota modello goal senza ricostruire lo storico.",
        formula_symbolic=formula,
        formula_applied=applied,
        inputs=inputs,
        stored_result=stored,
        stored_result_display=_fmt_it(stored),
        audit_result=audit_result,
        consistency=cons if stored is not None else {"status": "not_verifiable", "delta": None},
        rounding={"policy": "round", "precision": 2, "display_precision": 2},
        formula_version=formula_version,
        warnings=list(block.get("warnings") or []),
        extra={
            "goal_market_debug": dbg,
            "summary": summary,
            "contexts": block.get("contexts"),
            "technical": block.get("technical"),
            "weights": block.get("weights"),
            "market_status": block.get("status"),
        },
    )


def _explain_quota_cecchino(
    row: dict[str, Any],
    market_label: str,
    output: dict[str, Any],
    picchetti_debug: dict[str, Any],
) -> dict[str, Any]:
    mk = str(row.get("market_key") or "")
    if mk in _1X2_KEYS:
        return _explain_quota_cecchino_1x2(row, market_label, picchetti_debug)
    if mk in _DC_KEYS:
        return _explain_quota_cecchino_dc(row, market_label, output)
    if mk in _GOAL_KEYS or mk == SEL_DRAW_PT:
        return _explain_quota_cecchino_goal(row, market_label, output)
    # Generico: solo valore persistito
    stored = _num(row.get("quota_cecchino"))
    if stored is None:
        return _unavailable(
            market_key=mk,
            market_label=market_label,
            metric_key="quota_cecchino",
            formula_symbolic="Quota Cecchino (fonte di mercato non classificata)",
            inputs=[],
            reason="Quota Cecchino assente e formula di mercato non mappata",
        )
    return _base_explanation(
        market_key=mk,
        market_label=market_label,
        metric_key="quota_cecchino",
        status="available",
        calculation_type="persisted_only",
        description="Quota Cecchino persistita nel pannello KPI.",
        purpose="Quota modello per il mercato.",
        formula_symbolic="Valore persistito in kpi_panel_json (formula di mercato non mappata in audit)",
        formula_applied=[f"Quota persistita = {_fmt_it(stored)}"],
        inputs=[
            _input(
                key="quota_cecchino",
                label="Quota Cecchino",
                value=stored,
                display_value=_fmt_it(stored),
                source_path=f"kpi_panel_json.rows[{mk}].quota_cecchino",
            ),
        ],
        stored_result=stored,
        stored_result_display=_fmt_it(stored),
        audit_result=None,
        consistency={"status": "not_verifiable", "delta": None},
        rounding={"policy": "round", "precision": 2, "display_precision": 2},
        formula_version=KPI_V2_VERSION,
        warnings=["formula_market_not_mapped"],
    )


def _explain_historical_reliability(
    row: dict[str, Any],
    market_label: str,
    hr_by_market: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    mk = str(row.get("market_key") or "")
    item = hr_by_market.get(mk) or hr_by_market.get(str(row.get("segno") or "")) or {}
    formula = (
        "score = clamp(50 + min(1, n/100) * ((roi_c + margin_c + stab_c)/3 − 50)); "
        "roi_c = clamp(50 + roi×500); margin_c = clamp(50 + margin×500); "
        "stab_c = stability×100 (default 50)"
    )
    if not item:
        return _unavailable(
            market_key=mk,
            market_label=market_label,
            metric_key="historical_reliability",
            formula_symbolic=formula,
            inputs=[],
            reason="Affidabilità non calcolata per questo mercato",
            formula_version="historical_reliability_v1.1",
            description="Affidabilità storica della fascia Rating sulla coorte selezionata.",
            purpose="Indicare quanto storicamente le selezioni simili hanno performato.",
        )

    score = item.get("score")
    status = str(item.get("status") or "unavailable")
    inputs = [
        _input(key="rating_band", label="Fascia Rating", value=item.get("rating_band"),
               display_value=str((item.get("rating_band") or {}).get("label") or item.get("rating_band") or "—"),
               source_path="historical_reliability.rating_band", source_type="canonical_service"),
        _input(key="cohort_scope", label="Ambito coorte", value=item.get("cohort_scope"),
               display_value=str(item.get("cohort_scope") or "—"),
               source_path="historical_reliability.cohort_scope", source_type="canonical_service"),
        _input(key="local_sample_size", label="Campione locale", value=item.get("local_sample_size"),
               display_value=str(item.get("local_sample_size") if item.get("local_sample_size") is not None else "—"),
               source_path="historical_reliability.local_sample_size", source_type="canonical_service"),
        _input(key="global_sample_size", label="Campione globale", value=item.get("global_sample_size"),
               display_value=str(item.get("global_sample_size") if item.get("global_sample_size") is not None else "—"),
               source_path="historical_reliability.global_sample_size", source_type="canonical_service"),
        _input(key="selected_sample_size", label="Campione selezionato", value=item.get("selected_sample_size"),
               display_value=str(item.get("selected_sample_size") if item.get("selected_sample_size") is not None else "—"),
               source_path="historical_reliability.selected_sample_size", source_type="canonical_service"),
        _input(key="wins", label="Wins", value=item.get("wins"), display_value=str(item.get("wins")),
               source_path="historical_reliability.wins", source_type="canonical_service"),
        _input(key="losses", label="Losses", value=item.get("losses"), display_value=str(item.get("losses")),
               source_path="historical_reliability.losses", source_type="canonical_service"),
        _input(key="voids", label="Voids", value=item.get("voids"), display_value=str(item.get("voids")),
               source_path="historical_reliability.voids", source_type="canonical_service"),
        _input(key="average_odds", label="Quota media", value=item.get("average_odds"),
               display_value=_fmt_it(_num(item.get("average_odds"))),
               source_path="historical_reliability.average_odds", source_type="canonical_service"),
        _input(key="win_rate", label="Win rate", value=item.get("win_rate"),
               display_value=_fmt_pct(_num(item.get("win_rate"))),
               source_path="historical_reliability.win_rate", source_type="canonical_service"),
        _input(key="realized_margin", label="Margine realizzato", value=item.get("realized_margin"),
               display_value=_fmt_it(_num(item.get("realized_margin")), 4),
               source_path="historical_reliability.realized_margin", source_type="canonical_service"),
        _input(key="roi", label="ROI", value=item.get("roi"),
               display_value=_fmt_pct(_num(item.get("roi")), from_decimal=True),
               source_path="historical_reliability.roi", source_type="canonical_service"),
        _input(key="positive_periods", label="Periodi positivi", value=item.get("positive_periods"),
               display_value=str(item.get("positive_periods") if item.get("positive_periods") is not None else "—"),
               source_path="historical_reliability.positive_periods", source_type="canonical_service"),
        _input(key="roi_component", label="roi_c", value=item.get("roi_component"),
               display_value=_fmt_it(_num(item.get("roi_component"))),
               source_path="historical_reliability.roi_component", source_type="canonical_service"),
        _input(key="margin_component", label="margin_c", value=item.get("margin_component"),
               display_value=_fmt_it(_num(item.get("margin_component"))),
               source_path="historical_reliability.margin_component", source_type="canonical_service"),
        _input(key="stability_component", label="stab_c", value=item.get("stability_component"),
               display_value=_fmt_it(_num(item.get("stability_component"))),
               source_path="historical_reliability.stability_component", source_type="canonical_service"),
    ]

    applied: list[str] = []
    audit = None
    roi_c = _num(item.get("roi_component"))
    margin_c = _num(item.get("margin_component"))
    stab_c = _num(item.get("stability_component"))
    raw = _num(item.get("raw_evidence_score"))
    n = int(item.get("selected_sample_size") or item.get("sample_size") or 0)
    if roi_c is not None and margin_c is not None and stab_c is not None:
        if raw is None:
            raw = (roi_c + margin_c + stab_c) / 3.0
        conf = min(1.0, n / 100.0) if n else 0.0
        score_f = max(0.0, min(100.0, 50.0 + conf * (raw - 50.0)))
        audit = int(round(score_f))
        applied = [
            f"roi_c = {_fmt_it(roi_c)}",
            f"margin_c = {_fmt_it(margin_c)}",
            f"stab_c = {_fmt_it(stab_c)}",
            f"raw = (roi_c + margin_c + stab_c) / 3 = {_fmt_it(raw)}",
            f"confidence = min(1, {n}/100) = {_fmt_it(conf, 4)}",
            f"score = clamp(50 + confidence × (raw − 50)) → {audit}",
        ]
        if "negative_roi_and_margin_cap" in (item.get("reason_codes") or []):
            applied.append("Cap negativo ROI/margine → score ≤ 49")
            audit = min(audit, 49)

    if status != "ok" or score is None:
        return _base_explanation(
            market_key=mk,
            market_label=market_label,
            metric_key="historical_reliability",
            status="unavailable" if status in ("unavailable", "unsupported_market", "rating_below_scope") else status,
            calculation_type="historical_reliability",
            description=str(item.get("explanation") or "Affidabilità storica non disponibile."),
            purpose="Indicare quanto storicamente le selezioni simili hanno performato.",
            formula_symbolic=formula,
            formula_applied=applied or [f"Status = {status}", str(item.get("explanation") or "")],
            inputs=inputs,
            stored_result=score,
            stored_result_display="—" if score is None else f"{score} ({item.get('class') or '—'})",
            audit_result=audit,
            consistency=(
                _consistency(score, audit, abs_tol=0.0, rounding_tol=1.0)
                if score is not None and audit is not None
                else {"status": "unavailable" if score is None else "not_verifiable", "delta": None}
            ),
            rounding={"policy": "round_int", "precision": 0, "display_precision": 0},
            formula_version=str(item.get("version") or "historical_reliability_v1.1"),
            warnings=list(item.get("reason_codes") or []),
            extra={
                "historical_reliability": item,
                "fallback_used": item.get("fallback_used"),
                "historical_date_from": item.get("historical_date_from"),
                "historical_date_to": item.get("historical_date_to"),
            },
        )

    return _base_explanation(
        market_key=mk,
        market_label=market_label,
        metric_key="historical_reliability",
        status="available",
        calculation_type="historical_reliability",
        description=str(item.get("explanation") or "Affidabilità storica della fascia Rating."),
        purpose="Indicare quanto storicamente le selezioni simili hanno performato.",
        formula_symbolic=str(item.get("formula_symbolic") or formula),
        formula_applied=applied,
        inputs=inputs,
        stored_result=score,
        stored_result_display=f"{score} ({item.get('class') or '—'})",
        audit_result=audit,
        consistency=(
            _consistency(score, audit, abs_tol=0.0, rounding_tol=1.0)
            if audit is not None
            else {"status": "not_verifiable", "delta": None}
        ),
        rounding={"policy": "round_int", "precision": 0, "display_precision": 0},
        formula_version=str(item.get("version") or "historical_reliability_v1.1"),
        warnings=list(item.get("reason_codes") or []),
        extra={
            "historical_reliability": item,
            "fallback_used": item.get("fallback_used"),
            "historical_date_from": item.get("historical_date_from"),
            "historical_date_to": item.get("historical_date_to"),
            "class": item.get("class"),
        },
    )


def _explain_purchasability(
    row: dict[str, Any],
    market_label: str,
    preview_item: dict[str, Any] | None,
    candidate_item: dict[str, Any] | None,
    preview_meta: dict[str, Any],
    *,
    metric_key: str = "purchasability",
) -> dict[str, Any]:
    mk = str(row.get("market_key") or "")
    formula = "Acquistabilità raw = √(Fase 1 × Fase 2)"
    snap = preview_item or {}
    cand = candidate_item or {}

    if not snap and not cand:
        return _unavailable(
            market_key=mk,
            market_label=market_label,
            metric_key=metric_key,
            formula_symbolic=formula,
            inputs=[],
            reason="Snapshot Acquistabilità v1.1 assente",
            formula_version=str(preview_meta.get("candidate_version") or "purchasability"),
            description="Score di Acquistabilità v1.1 a due fasi (valore × qualità).",
            purpose="Sintetizzare valore e contesto qualitativo del mercato (baseline v1.1).",
        )

    phase1 = _num(snap.get("phase_1_score"))
    phase2 = _num(snap.get("phase_2_score"))
    if phase1 is None and isinstance(cand.get("phase_1_value"), dict):
        phase1 = _num(cand["phase_1_value"].get("score"))
    if phase2 is None and isinstance(cand.get("phase_2_quality"), dict):
        phase2 = _num(cand["phase_2_quality"].get("score"))

    stored_score = _num(snap.get("score") if snap else cand.get("score"))
    stored_raw = _num(snap.get("raw_score") if snap else cand.get("raw_score"))

    inputs = [
        _input(
            key="phase_1_score",
            label="Fase 1",
            value=phase1,
            display_value=_fmt_it(phase1),
            source_path="cecchino_output_json.purchasability_preview.items[].phase_1_score",
        ),
        _input(
            key="phase_2_score",
            label="Fase 2",
            value=phase2,
            display_value=_fmt_it(phase2),
            source_path="cecchino_output_json.purchasability_preview.items[].phase_2_score",
        ),
        _input(
            key="candidate_version",
            label="Candidate version",
            value=preview_meta.get("candidate_version") or cand.get("candidate_version"),
            display_value=str(preview_meta.get("candidate_version") or cand.get("candidate_version") or "—"),
            source_path="purchasability_preview.candidate_version",
        ),
        _input(
            key="candidate_name",
            label="Candidate name",
            value=preview_meta.get("candidate_name") or cand.get("candidate_name"),
            display_value=str(preview_meta.get("candidate_name") or cand.get("candidate_name") or "—"),
            source_path="purchasability_preview.candidate_name",
        ),
    ]

    applied: list[str] = []
    audit_raw = None
    if phase1 is not None and phase2 is not None:
        audit_raw = math.sqrt(phase1 * phase2)
        applied = [
            f"√({_fmt_it(phase1)} × {_fmt_it(phase2)}) = {_fmt_it(audit_raw, 4)}",
            f"raw_score persistito = {_fmt_it(stored_raw, 4)}" if stored_raw is not None else "raw_score persistito = —",
            f"score finale persistito = {int(stored_score) if stored_score is not None else '—'}",
        ]
    else:
        applied = ["Fase 1 o Fase 2 assente: verifica geometrica non completa"]

    phase1_detail = cand.get("phase_1_value") if isinstance(cand.get("phase_1_value"), dict) else None
    phase2_detail = cand.get("phase_2_quality") if isinstance(cand.get("phase_2_quality"), dict) else None

    status = str(snap.get("status") or cand.get("status") or "unavailable")
    if stored_score is None and status != "available":
        return _base_explanation(
            market_key=mk,
            market_label=market_label,
            metric_key=metric_key,
            status="unavailable",
            calculation_type="purchasability_candidate",
            description="Acquistabilità v1.1 non disponibile per questo mercato.",
            purpose="Sintetizzare valore e contesto qualitativo del mercato (baseline v1.1).",
            formula_symbolic=formula,
            formula_applied=applied + [f"status = {status}"],
            inputs=inputs,
            stored_result=None,
            stored_result_display="—",
            audit_result=audit_raw,
            consistency={"status": "unavailable", "delta": None},
            rounding={"policy": "ROUND_HALF_UP", "precision": 0, "display_precision": 0},
            formula_version=str(preview_meta.get("candidate_version") or "purchasability"),
            warnings=list(snap.get("reason_codes") or cand.get("reason_codes") or []),
            extra={
                "phase_1": phase1_detail,
                "phase_2": phase2_detail,
                "reading": snap.get("reading") or cand.get("reading"),
                "class": snap.get("class") or cand.get("class"),
                "reason_codes": snap.get("reason_codes") or cand.get("reason_codes"),
                "audit_badges": ["V1.1 baseline", "Pre-match"],
            },
        )

    cons = (
        _consistency(stored_raw, audit_raw, abs_tol=0.01, rounding_tol=0.05)
        if audit_raw is not None and stored_raw is not None
        else {"status": "not_verifiable", "delta": None}
    )

    return _base_explanation(
        market_key=mk,
        market_label=market_label,
        metric_key=metric_key,
        status="available" if stored_score is not None else "partial",
        calculation_type="purchasability_candidate",
        description="Score di Acquistabilità v1.1 a due fasi (valore × qualità) con media geometrica.",
        purpose="Sintetizzare valore e contesto qualitativo del mercato (baseline v1.1).",
        formula_symbolic=formula,
        formula_applied=applied,
        inputs=inputs,
        stored_result=int(stored_score) if stored_score is not None else None,
        stored_result_display=(
            f"{int(stored_score)} ({snap.get('class') or cand.get('class') or '—'})"
            if stored_score is not None
            else "—"
        ),
        audit_result=round(audit_raw, 4) if audit_raw is not None else None,
        consistency=cons,
        rounding={"policy": "ROUND_HALF_UP", "precision": 0, "display_precision": 0},
        formula_version=str(preview_meta.get("candidate_version") or "purchasability"),
        warnings=list(snap.get("reason_codes") or cand.get("reason_codes") or []),
        extra={
            "phase_1_score": phase1,
            "phase_2_score": phase2,
            "raw_score": stored_raw,
            "phase_1": phase1_detail,
            "phase_2": phase2_detail,
            "reading": snap.get("reading") or cand.get("reading"),
            "class": snap.get("class") or cand.get("class"),
            "calculation_quality": snap.get("calculation_quality") or cand.get("calculation_quality"),
            "reason_codes": snap.get("reason_codes") or cand.get("reason_codes"),
            "active_inputs": (phase1_detail or {}).get("active_inputs") if phase1_detail else None,
            "diagnostic_only_inputs": (phase1_detail or {}).get("diagnostic_only_inputs") if phase1_detail else None,
            "rating_used_as_weight": False,
            "historical_reliability_used": False,
            "audit_badges": ["V1.1 baseline", "Pre-match"],
        },
    )


def _explain_purchasability_v2(
    row: dict[str, Any],
    market_label: str,
    preview_item: dict[str, Any] | None,
    candidate_item: dict[str, Any] | None,
    preview_meta: dict[str, Any],
    comparison_item: dict[str, Any] | None = None,
) -> dict[str, Any]:
    mk = str(row.get("market_key") or "")
    formula = (
        "raw_pre_gate = √(Fase 1 × Fase 2); "
        "score ufficiale = gate ? raw_pre_gate : 0 (ROUND_HALF_UP)"
    )
    snap = preview_item or {}
    cand = candidate_item or {}

    if not snap and not cand:
        return _unavailable(
            market_key=mk,
            market_label=market_label,
            metric_key="purchasability_v2",
            formula_symbolic=formula,
            inputs=[],
            reason="Snapshot Acquistabilità v2 assente",
            formula_version=str(
                preview_meta.get("candidate_version") or "purchasability_v2"
            ),
            description=(
                "Misura se questo mercato rappresenta la migliore opportunità "
                "decisionale della partita, combinando valore rispetto al Book, "
                "superiorità rispetto ai concorrenti e contrasto con il mercato opposto."
            ),
            purpose="Indice decisionale parallelo (v2) — non sostituisce la v1.1.",
        )

    phase1 = _num(snap.get("phase_1_score"))
    phase2 = _num(snap.get("phase_2_score"))
    p1_detail = cand.get("phase_1_value") if isinstance(cand.get("phase_1_value"), dict) else (
        None
    )
    p2_detail = cand.get("phase_2_quality") if isinstance(cand.get("phase_2_quality"), dict) else (
        None
    )
    if phase1 is None and isinstance(p1_detail, dict):
        phase1 = _num(p1_detail.get("score"))
    if phase2 is None and isinstance(p2_detail, dict):
        phase2 = _num(p2_detail.get("score"))

    stored_score = _num(snap.get("score") if snap else cand.get("score"))
    stored_raw = _num(snap.get("raw_score") if snap else cand.get("raw_score"))
    raw_pre_gate = _num(
        snap.get("raw_pre_gate_score") if snap else cand.get("raw_pre_gate_score")
    )
    gate = cand.get("positive_value_gate") if isinstance(cand.get("positive_value_gate"), dict) else (
        snap.get("positive_value_gate") if isinstance(snap.get("positive_value_gate"), dict) else {}
    )
    norm_meta = cand.get("normalization_profile") if isinstance(cand.get("normalization_profile"), dict) else {
        "version": preview_meta.get("normalization_profile_version") or snap.get("normalization_profile_version"),
        "hash": preview_meta.get("normalization_profile_hash") or snap.get("normalization_profile_hash"),
        "cutoff": preview_meta.get("normalization_profile_cutoff") or snap.get("normalization_profile_cutoff"),
    }

    inputs = [
        _input(
            key="phase_1_score",
            label="Fase 1 (valore assoluto)",
            value=phase1,
            display_value=_fmt_it(phase1),
            source_path="purchasability_preview_v2.items[].phase_1_score",
        ),
        _input(
            key="phase_2_score",
            label="Fase 2 (qualità decisione)",
            value=phase2,
            display_value=_fmt_it(phase2),
            source_path="purchasability_preview_v2.items[].phase_2_score",
        ),
        _input(
            key="raw_pre_gate_score",
            label="Raw pre-gate",
            value=raw_pre_gate,
            display_value=_fmt_it(raw_pre_gate, 4),
            source_path="purchasability_preview_v2.items[].raw_pre_gate_score",
        ),
        _input(
            key="positive_value_gate",
            label="Positive value gate",
            value=gate.get("status"),
            display_value=str(gate.get("status") or "—"),
            source_path="purchasability_preview_v2.items[].positive_value_gate",
        ),
        _input(
            key="normalization_profile_version",
            label="Profilo normalizzazione",
            value=norm_meta.get("version"),
            display_value=str(norm_meta.get("version") or "—"),
            source_path="purchasability_preview_v2.normalization_profile_version",
        ),
        _input(
            key="candidate_version",
            label="Candidate version",
            value=preview_meta.get("candidate_version") or cand.get("candidate_version"),
            display_value=str(
                preview_meta.get("candidate_version")
                or cand.get("candidate_version")
                or "—"
            ),
            source_path="purchasability_preview_v2.candidate_version",
        ),
    ]

    applied: list[str] = []
    audit_raw = None
    if phase1 is not None and phase2 is not None:
        audit_raw = math.sqrt(phase1 * phase2)
        applied = [
            f"raw_pre_gate = √({_fmt_it(phase1)} × {_fmt_it(phase2)}) = {_fmt_it(audit_raw, 4)}",
            f"gate = {gate.get('status') or '—'}",
            (
                f"score ufficiale = 0 (gate failed); pre-gate = {_fmt_it(raw_pre_gate, 4)}"
                if gate.get("status") == "failed"
                else f"score ufficiale = ROUND_HALF_UP({_fmt_it(stored_raw, 4)}) = {int(stored_score) if stored_score is not None else '—'}"
            ),
        ]
    else:
        applied = ["Fase 1 o Fase 2 assente: formula geometrica non completa"]

    cmp_block = comparison_item or {}
    extra = {
        "what_it_measures": (
            "Misura se questo mercato rappresenta la migliore opportunità "
            "decisionale della partita, combinando valore rispetto al Book, "
            "superiorità rispetto ai concorrenti e contrasto con il mercato opposto."
        ),
        "audit_badges": [
            "V2 parallela",
            "Profilo storico congelato",
            "Pre-match",
        ],
        "phase_1_score": phase1,
        "phase_2_score": phase2,
        "raw_score": stored_raw,
        "raw_pre_gate_score": raw_pre_gate,
        "phase_1": p1_detail,
        "phase_2": p2_detail,
        "positive_value_gate": gate,
        "normalization_profile": norm_meta,
        "competitor_trace": (p2_detail or {}).get("competitor_trace") if p2_detail else (
            {
                "best_competitor_keys": snap.get("best_competitor_keys"),
                "opposite_selection": snap.get("opposite_selection"),
                "decision_group": snap.get("decision_group"),
                "probability_subgroup": snap.get("probability_subgroup"),
            }
        ),
        "raw_components": snap.get("raw_components"),
        "normalized_components": snap.get("normalized_components"),
        "reading": snap.get("reading") or cand.get("reading"),
        "class": snap.get("class") or cand.get("class"),
        "calculation_quality": snap.get("calculation_quality") or cand.get("calculation_quality"),
        "reason_codes": snap.get("reason_codes") or cand.get("reason_codes"),
        "comparison_v1_1": {
            "v1_1_score": cmp_block.get("v1_1_score"),
            "v2_score": cmp_block.get("v2_score"),
            "delta_v2_minus_v1_1": cmp_block.get("delta_v2_minus_v1_1"),
            "note": (
                "Il delta è descrittivo e non costituisce validazione empirica "
                "di superiorità della v2."
            ),
        },
        "score_acquisto_used": False,
        "historical_reliability_used": False,
        "balance_used": "available_not_used",
        "goal_intensity_used": "available_not_used",
    }

    status = str(snap.get("status") or cand.get("status") or "unavailable")
    if stored_score is None and status == "unavailable":
        return _base_explanation(
            market_key=mk,
            market_label=market_label,
            metric_key="purchasability_v2",
            status="unavailable",
            calculation_type="purchasability_v2_candidate",
            description="Acquistabilità v2 non disponibile per questo mercato.",
            purpose="Indice decisionale parallelo (v2).",
            formula_symbolic=formula,
            formula_applied=applied + [f"status = {status}"],
            inputs=inputs,
            stored_result=None,
            stored_result_display="—",
            audit_result=audit_raw,
            consistency={"status": "unavailable", "delta": None},
            rounding={"policy": "ROUND_HALF_UP", "precision": 0, "display_precision": 0},
            formula_version=str(
                preview_meta.get("candidate_version") or "purchasability_v2"
            ),
            warnings=list(snap.get("reason_codes") or cand.get("reason_codes") or []),
            extra=extra,
        )

    cons = (
        _consistency(raw_pre_gate or stored_raw, audit_raw, abs_tol=0.01, rounding_tol=0.05)
        if audit_raw is not None and (raw_pre_gate is not None or stored_raw is not None)
        else {"status": "not_verifiable", "delta": None}
    )

    return _base_explanation(
        market_key=mk,
        market_label=market_label,
        metric_key="purchasability_v2",
        status="available" if stored_score is not None else "partial",
        calculation_type="purchasability_v2_candidate",
        description=(
            "Misura se questo mercato rappresenta la migliore opportunità "
            "decisionale della partita, combinando valore rispetto al Book, "
            "superiorità rispetto ai concorrenti e contrasto con il mercato opposto."
        ),
        purpose="Indice decisionale parallelo (v2) — non sostituisce la v1.1.",
        formula_symbolic=formula,
        formula_applied=applied,
        inputs=inputs,
        stored_result=int(stored_score) if stored_score is not None else None,
        stored_result_display=(
            f"{int(stored_score)} ({snap.get('class') or cand.get('class') or '—'})"
            if stored_score is not None
            else "—"
        ),
        audit_result=round(audit_raw, 4) if audit_raw is not None else None,
        consistency=cons,
        rounding={"policy": "ROUND_HALF_UP", "precision": 0, "display_precision": 0},
        formula_version=str(
            preview_meta.get("candidate_version") or "purchasability_v2"
        ),
        warnings=list(snap.get("reason_codes") or cand.get("reason_codes") or []),
        extra=extra,
    )


def _explain_purchasability_delta(
    row: dict[str, Any],
    market_label: str,
    comparison_item: dict[str, Any] | None,
    *,
    v1_meta: dict[str, Any] | None = None,
    v2_meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    mk = str(row.get("market_key") or "")
    formula = "Delta = Acquistabilità v2 − Acquistabilità v1.1"
    cmp = comparison_item or {}
    s1 = cmp.get("v1_1_score")
    s2 = cmp.get("v2_score")
    delta = cmp.get("delta_v2_minus_v1_1")
    status = str(cmp.get("comparison_status") or "unavailable")

    inputs = [
        _input(
            key="v1_1_score",
            label="Acquistabilità v1.1",
            value=s1,
            display_value=str(s1) if s1 is not None else "—",
            source_path="purchasability_preview.items[].score",
        ),
        _input(
            key="v2_score",
            label="Acquistabilità v2",
            value=s2,
            display_value=str(s2) if s2 is not None else "—",
            source_path="purchasability_preview_v2.items[].score",
        ),
        _input(
            key="candidate_v1_1",
            label="Candidate v1.1",
            value=(v1_meta or {}).get("candidate_version"),
            display_value=str((v1_meta or {}).get("candidate_version") or "—"),
            source_path="purchasability_preview.candidate_version",
        ),
        _input(
            key="candidate_v2",
            label="Candidate v2",
            value=(v2_meta or {}).get("candidate_version"),
            display_value=str((v2_meta or {}).get("candidate_version") or "—"),
            source_path="purchasability_preview_v2.candidate_version",
        ),
    ]

    if delta is None:
        reason = "Uno o entrambi gli score non sono disponibili"
        return _base_explanation(
            market_key=mk,
            market_label=market_label,
            metric_key="purchasability_delta",
            status="unavailable" if status == "unavailable" else "partial",
            calculation_type="purchasability_comparison",
            description="Confronto diagnostico tra due architetture di Acquistabilità.",
            purpose=(
                "Confronto diagnostico tra due architetture. "
                "Non stabilisce quale modello sia empiricamente migliore."
            ),
            formula_symbolic=formula,
            formula_applied=[
                f"v1.1 = {s1 if s1 is not None else '—'}",
                f"v2 = {s2 if s2 is not None else '—'}",
                "delta unavailable",
                reason,
            ],
            inputs=inputs,
            stored_result=None,
            stored_result_display="—",
            audit_result=None,
            consistency={"status": status, "delta": None},
            rounding={"policy": "n/a", "precision": 0, "display_precision": 0},
            formula_version="purchasability_delta_v1",
            warnings=[reason],
            extra={
                "unavailable_reason": reason,
                "comparison_status": status,
                "audit_badges": ["Confronto diagnostico"],
            },
        )

    sign = "+" if int(delta) > 0 else ""
    return _base_explanation(
        market_key=mk,
        market_label=market_label,
        metric_key="purchasability_delta",
        status="available",
        calculation_type="purchasability_comparison",
        description="Differenza numerica V2 meno V1.1.",
        purpose=(
            "Confronto diagnostico tra due architetture. "
            "Non stabilisce quale modello sia empiricamente migliore."
        ),
        formula_symbolic=formula,
        formula_applied=[
            f"{s2} − {s1} = {sign}{int(delta)}",
        ],
        inputs=inputs,
        stored_result=int(delta),
        stored_result_display=f"{sign}{int(delta)}",
        audit_result=int(delta),
        consistency={"status": "match", "delta": 0},
        rounding={"policy": "integer_scores", "precision": 0, "display_precision": 0},
        formula_version="purchasability_delta_v1",
        warnings=[],
        extra={
            "v1_1_score": s1,
            "v2_score": s2,
            "delta_v2_minus_v1_1": int(delta),
            "comparison_status": status,
            "audit_badges": ["Confronto diagnostico", "Non validazione empirica"],
        },
    )


def _build_hr_index_for_fixture(
    db: Session,
    row: CecchinoTodayFixture,
    kpi_panel: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    """Affidabilità canonica per una sola fixture (nessuna scrittura)."""
    from app.services.cecchino.cecchino_historical_reliability import (
        build_historical_reliability_for_panel,
        iter_current_kpi_panel_rows,
        panel_item_key,
    )

    current_rows = iter_current_kpi_panel_rows([row])
    if not current_rows:
        # Fallback: costruisci rows minimi dal panel persistito
        current_rows = []
        for r in kpi_panel.get("rows") or []:
            if not isinstance(r, dict):
                continue
            current_rows.append(
                {
                    **r,
                    "today_fixture_id": int(row.id),
                    "competition_id": row.competition_id,
                    "kickoff": row.kickoff.isoformat() if row.kickoff else None,
                }
            )

    scan_d = row.scan_date
    try:
        payload = build_historical_reliability_for_panel(
            db,
            date_from=scan_d,
            date_to=scan_d,
            competition_id=row.competition_id,
            current_rows=current_rows,
            fixtures=[row],
        )
    except Exception as exc:  # noqa: BLE001 — audit fail-soft
        return {"__error__": {"status": "unavailable", "explanation": str(exc)}}

    items = payload.get("items") if isinstance(payload, dict) else {}
    by_market: dict[str, dict[str, Any]] = {}
    if not isinstance(items, dict):
        return by_market
    for _key, item in items.items():
        if not isinstance(item, dict):
            continue
        mk = str(item.get("market_key") or item.get("selection") or "")
        if mk:
            by_market[mk] = item
        # anche via panel_item_key parsing
        raw_mk = item.get("raw_market_key")
        if raw_mk:
            by_market[str(raw_mk)] = item
    # Garantisce lookup diretto
    for r in current_rows:
        mk = str(r.get("market_key") or "")
        if not mk:
            continue
        k = panel_item_key(today_fixture_id=row.id, market_key=mk)
        if k in items and mk not in by_market:
            by_market[mk] = items[k]
    return by_market


def _rebuild_purchasability_candidate(
    row: CecchinoTodayFixture,
    kpi_panel: dict[str, Any],
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    """Rebuild in-memory del candidate (nessuna scrittura DB)."""
    preview = {}
    output = row.cecchino_output_json if isinstance(row.cecchino_output_json, dict) else {}
    if isinstance(output.get("purchasability_preview"), dict):
        preview = output["purchasability_preview"]

    fixture_meta = {
        "today_fixture_id": int(row.id),
        "local_fixture_id": int(row.local_fixture_id) if row.local_fixture_id else None,
        "provider_fixture_id": int(row.provider_fixture_id) if row.provider_fixture_id else None,
        "home_team": row.home_team_name,
        "away_team": row.away_team_name,
        "kickoff": row.kickoff.isoformat() if row.kickoff else None,
        "competition_id": row.competition_id,
        "scan_date": row.scan_date.isoformat() if row.scan_date else None,
    }
    snapshot_info = None
    odds = row.odds_snapshot_json if isinstance(row.odds_snapshot_json, dict) else {}
    meta = odds.get("odds_meta") if isinstance(odds.get("odds_meta"), dict) else {}
    if meta:
        snapshot_info = {
            "snapshot_at": meta.get("odds_fetched_at") or meta.get("snapshot_at"),
            "snapshot_timestamp_verified": True,
            "snapshot_before_kickoff": True,
        }

    try:
        candidate, _snap = build_candidate_and_compact_snapshot(
            kpi_panel=kpi_panel,
            fixture_meta=fixture_meta,
            snapshot_info=snapshot_info,
            source_mode="kpi_explanations_audit",
        )
        return candidate, preview
    except Exception:  # noqa: BLE001
        return None, preview


def _rebuild_purchasability_v2_candidate(
    row: CecchinoTodayFixture,
    kpi_panel: dict[str, Any],
    db: Session | None = None,
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    """Rebuild in-memory v2 (nessuna scrittura DB). Preferisce snapshot persistito."""
    preview: dict[str, Any] = {}
    output = row.cecchino_output_json if isinstance(row.cecchino_output_json, dict) else {}
    if isinstance(output.get("purchasability_preview_v2"), dict):
        preview = output["purchasability_preview_v2"]

    fixture_meta = {
        "today_fixture_id": int(row.id),
        "local_fixture_id": int(row.local_fixture_id) if row.local_fixture_id else None,
        "provider_fixture_id": int(row.provider_fixture_id) if row.provider_fixture_id else None,
        "home_team": row.home_team_name,
        "away_team": row.away_team_name,
        "kickoff": row.kickoff.isoformat() if row.kickoff else None,
        "competition_id": row.competition_id,
        "scan_date": row.scan_date.isoformat() if row.scan_date else None,
    }
    snapshot_info = None
    odds = row.odds_snapshot_json if isinstance(row.odds_snapshot_json, dict) else {}
    meta = odds.get("odds_meta") if isinstance(odds.get("odds_meta"), dict) else {}
    if meta:
        snapshot_info = {
            "snapshot_at": meta.get("odds_fetched_at") or meta.get("snapshot_at"),
            "snapshot_timestamp_verified": True,
            "snapshot_before_kickoff": True,
        }

    try:
        candidate, derived_snap = build_candidate_and_compact_snapshot_v2(
            kpi_panel=kpi_panel,
            fixture_meta=fixture_meta,
            snapshot_info=snapshot_info,
            db=db,
            source_mode="kpi_explanations_audit",
        )
        if not preview:
            preview = derived_snap
        return candidate, preview
    except Exception:  # noqa: BLE001
        return None, preview


def build_kpi_explanations(row: CecchinoTodayFixture, db: Session) -> dict[str, Any]:
    """Assembla il payload audit per una fixture eleggibile."""
    raw_panel = row.kpi_panel_json
    if not isinstance(raw_panel, dict) or not isinstance(raw_panel.get("rows"), list):
        return {
            "status": "error",
            "code": "kpi_not_available",
            "message": "Pannello KPI non disponibile",
        }

    kpi_panel = normalize_kpi_panel_rows(dict(raw_panel)) or raw_panel
    output = row.cecchino_output_json if isinstance(row.cecchino_output_json, dict) else {}
    warnings: list[str] = []
    partial = False

    picchetti_debug = build_cecchino_picchetti_debug(
        cecchino_output=output,
        kpi_panel=kpi_panel,
    )

    hr_by_market = _build_hr_index_for_fixture(db, row, kpi_panel)
    if "__error__" in hr_by_market:
        warnings.append(f"historical_reliability_error:{hr_by_market['__error__'].get('explanation')}")
        hr_by_market = {}
        partial = True

    candidate, preview = _rebuild_purchasability_candidate(row, kpi_panel)
    preview_index = index_purchasability_snapshot_by_market(preview) if preview else {}
    candidate_index: dict[str, dict[str, Any]] = {}
    if isinstance(candidate, dict):
        for it in candidate.get("items") or []:
            if isinstance(it, dict) and it.get("market_key"):
                candidate_index[str(it["market_key"])] = it

    preview_meta = {
        "candidate_version": preview.get("candidate_version") if preview else None,
        "candidate_name": preview.get("candidate_name") if preview else None,
        "snapshot_version": preview.get("snapshot_version") if preview else None,
    }
    if candidate and not preview_meta.get("candidate_version"):
        preview_meta["candidate_version"] = candidate.get("candidate_version")
        preview_meta["candidate_name"] = candidate.get("candidate_name")

    candidate_v2, preview_v2 = _rebuild_purchasability_v2_candidate(row, kpi_panel, db)
    preview_v2_index = (
        index_purchasability_v2_snapshot_by_market(preview_v2) if preview_v2 else {}
    )
    candidate_v2_index: dict[str, dict[str, Any]] = {}
    if isinstance(candidate_v2, dict):
        for it in candidate_v2.get("items") or []:
            if isinstance(it, dict) and it.get("market_key"):
                candidate_v2_index[str(it["market_key"])] = it

    preview_v2_meta = {
        "candidate_version": preview_v2.get("candidate_version") if preview_v2 else None,
        "candidate_name": preview_v2.get("candidate_name") if preview_v2 else None,
        "snapshot_version": preview_v2.get("snapshot_version") if preview_v2 else None,
        "normalization_profile_version": (
            preview_v2.get("normalization_profile_version") if preview_v2 else None
        ),
        "normalization_profile_hash": (
            preview_v2.get("normalization_profile_hash") if preview_v2 else None
        ),
        "normalization_profile_cutoff": (
            preview_v2.get("normalization_profile_cutoff") if preview_v2 else None
        ),
    }
    if candidate_v2 and not preview_v2_meta.get("candidate_version"):
        preview_v2_meta["candidate_version"] = candidate_v2.get("candidate_version")
        preview_v2_meta["candidate_name"] = candidate_v2.get("candidate_name")
        preview_v2_meta["normalization_profile_version"] = candidate_v2.get(
            "normalization_profile_version"
        )
        preview_v2_meta["normalization_profile_hash"] = candidate_v2.get(
            "normalization_profile_hash"
        )
        preview_v2_meta["normalization_profile_cutoff"] = candidate_v2.get(
            "normalization_profile_cutoff"
        )

    comparison = build_purchasability_comparison(
        preview if isinstance(preview, dict) else None,
        preview_v2 if isinstance(preview_v2, dict) else None,
    )
    comparison_items = (
        comparison.get("items") if isinstance(comparison.get("items"), dict) else {}
    )

    markets: dict[str, dict[str, Any]] = {}
    for r in kpi_panel.get("rows") or []:
        if not isinstance(r, dict):
            continue
        mk = str(r.get("market_key") or "")
        if not mk:
            continue
        label = str(r.get("segno") or r.get("label") or mk)
        market_explanations: dict[str, Any] = {}
        try:
            market_explanations["quota_cecchino"] = _explain_quota_cecchino(
                r, label, output, picchetti_debug
            )
            market_explanations["prob_book"] = _explain_prob_book(r, label)
            market_explanations["prob_cecchino"] = _explain_prob_cecchino(r, label)
            market_explanations["vantaggio_prob"] = _explain_vantaggio(r, label)
            market_explanations["edge_pct"] = _explain_edge(r, label)
            market_explanations["score_acquisto"] = _explain_score(r, label)
            market_explanations["rating"] = _explain_rating(r, label)
            market_explanations["historical_reliability"] = _explain_historical_reliability(
                r, label, hr_by_market
            )
            purch_v11 = _explain_purchasability(
                r,
                label,
                preview_index.get(mk),
                candidate_index.get(mk),
                preview_meta,
                metric_key="purchasability",
            )
            market_explanations["purchasability"] = purch_v11
            market_explanations["purchasability_v1_1"] = _explain_purchasability(
                r,
                label,
                preview_index.get(mk),
                candidate_index.get(mk),
                preview_meta,
                metric_key="purchasability_v1_1",
            )
            market_explanations["purchasability_v2"] = _explain_purchasability_v2(
                r,
                label,
                preview_v2_index.get(mk),
                candidate_v2_index.get(mk),
                preview_v2_meta,
                comparison_item=comparison_items.get(mk),
            )
            market_explanations["purchasability_delta"] = _explain_purchasability_delta(
                r,
                label,
                comparison_items.get(mk),
                v1_meta=preview_meta,
                v2_meta=preview_v2_meta,
            )
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"market_{mk}_explain_error:{type(exc).__name__}")
            partial = True
            continue
        markets[mk] = market_explanations

        for metric_key, expl in market_explanations.items():
            if expl.get("status") == "partial":
                partial = True
            if expl.get("consistency", {}).get("status") == "mismatch":
                warnings.append(f"consistency_mismatch:{mk}:{metric_key}")
                partial = True

    status = "partial" if partial else "ok"
    return {
        "status": status,
        "audit_version": AUDIT_VERSION,
        "no_model_recalculation": True,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "fixture": {
            "today_fixture_id": int(row.id),
            "local_fixture_id": int(row.local_fixture_id) if row.local_fixture_id else None,
            "provider_fixture_id": int(row.provider_fixture_id) if row.provider_fixture_id else None,
            "home_team": row.home_team_name,
            "away_team": row.away_team_name,
            "kickoff": row.kickoff.isoformat() if row.kickoff else None,
            "scan_date": row.scan_date.isoformat() if row.scan_date else None,
            "competition_id": row.competition_id,
        },
        "panel_version": str(kpi_panel.get("version") or KPI_V2_VERSION),
        "excluded_metrics": list(EXCLUDED_METRICS),
        "analyzable_metrics": list(ANALYZABLE_METRICS),
        "markets": markets,
        "warnings": warnings,
        "metadata": {
            "snapshot_only": True,
            "kpi_panel_source": "kpi_panel_json",
            "cecchino_output_source": "cecchino_output_json",
            "purchasability_preview_present": bool(preview),
            "purchasability_preview_v2_present": bool(preview_v2),
            "historical_reliability_markets": len(hr_by_market),
            "read_only": True,
            "db_writes": False,
            "external_api_calls": False,
        },
    }


def get_kpi_explanations(db: Session, today_fixture_id: int) -> dict[str, Any] | None:
    row = db.get(CecchinoTodayFixture, today_fixture_id)
    if row is None:
        return None
    if row.eligibility_status != ELIGIBILITY_ELIGIBLE:
        return {
            "status": "error",
            "code": "not_eligible",
            "message": "Fixture non eleggibile",
        }
    raw_panel = row.kpi_panel_json
    if not isinstance(raw_panel, dict) or not isinstance(raw_panel.get("rows"), list):
        return {
            "status": "error",
            "code": "kpi_not_available",
            "message": "Pannello KPI non disponibile",
        }
    return build_kpi_explanations(row, db)
