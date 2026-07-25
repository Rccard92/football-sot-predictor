"""Spiegazioni pilastro-per-pilastro Balance v5 — audit diagnostico read-only.

Fonte di verità visualizzata: stesso builder del dettaglio Today
(`build_cecchino_balance_v5` su snapshot già memorizzati).
Riesecuzione diagnostica solo in memoria (diagnostic_re_evaluation_only).
"""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.models.cecchino_today_fixture import ELIGIBILITY_ELIGIBLE, CecchinoTodayFixture
from app.services.cecchino.cecchino_balance_v5 import (
    PILLAR_ORDER,
    VERSION as BALANCE_VERSION,
    _classify_draw,
    _classify_f36,
    _f36_side_from_signed,
    _normalize_2way_probs,
    _normalize_3way_probs,
    _num,
    _prob_to_percent,
    build_cecchino_balance_v5,
    classify_conviction,
    classify_gap_coherence,
    compute_dominance_pp,
    conviction_index,
    dominant_side_to_market_label,
    gap_coherence_index,
    probability_balance_index,
    probability_gap_1_2_pp,
    x_rank_from_probs,
)
from app.services.cecchino.cecchino_balance_v5_monitoring import BALANCE_MONITORING_KEY

AUDIT_VERSION = "cecchino_balance_explanations_v1"
MODULE = "balance_v5"

# Mapping contratto audit ↔ chiavi canoniche UI/builder
PILLAR_AUDIT_KEYS: list[tuple[str, str, int, str]] = [
    ("geometry", "f36", 1, "Geometria della partita"),
    ("conviction", "dominance", 2, "Convinzione del modello"),
    ("draw_credibility", "draw_credibility", 3, "Credibilità della X"),
    ("coherence_1_2", "gap_coherence", 4, "Coerenza matematica 1/2"),
]

OFFICIAL_PILLARS = ["geometry", "conviction", "coherence_1_2"]
DESCRIPTIVE_PILLARS = ["draw_credibility"]


def _fmt_it(v: float | None, decimals: int = 2) -> str:
    if v is None:
        return "—"
    return f"{v:.{decimals}f}".replace(".", ",")


def _fmt_pct(v: float | None, decimals: int = 2) -> str:
    if v is None:
        return "—"
    return f"{_fmt_it(v, decimals)}%"


def _json_safe(value: Any) -> Any:
    if isinstance(value, float):
        if not math.isfinite(value):
            return None
        return value
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    return value


def _consistency(
    stored: Any,
    audit: Any,
    *,
    abs_tol: float = 1e-6,
    rounding_tol: float = 0.01,
) -> dict[str, Any]:
    if stored is None and audit is None:
        return {"status": "unavailable", "delta": None}
    if stored is None or audit is None:
        return {"status": "not_verifiable", "delta": None}
    try:
        s = float(stored)
        a = float(audit)
    except (TypeError, ValueError):
        if stored == audit:
            return {"status": "match", "delta": 0}
        return {"status": "mismatch", "delta": None}
    if not math.isfinite(s) or not math.isfinite(a):
        return {"status": "not_verifiable", "delta": None}
    delta = a - s
    if abs(delta) <= abs_tol:
        return {"status": "match", "delta": round(delta, 10)}
    if abs(delta) <= rounding_tol:
        return {"status": "rounding_match", "delta": round(delta, 10)}
    return {"status": "mismatch", "delta": round(delta, 10)}


def _consistency_class(displayed: str | None, audit: str | None) -> dict[str, Any]:
    if displayed is None and audit is None:
        return {"status": "unavailable", "delta": None}
    if displayed is None or audit is None:
        return {"status": "not_verifiable", "delta": None}
    if displayed == audit:
        return {"status": "match", "delta": 0}
    return {"status": "mismatch", "delta": None}


def _merge_consistency(*parts: dict[str, Any]) -> dict[str, Any]:
    statuses = [p.get("status") for p in parts if p]
    if not statuses:
        return {"status": "unavailable", "delta": None}
    if "mismatch" in statuses:
        delta = next((p.get("delta") for p in parts if p.get("status") == "mismatch"), None)
        return {"status": "mismatch", "delta": delta}
    if "not_verifiable" in statuses:
        return {"status": "not_verifiable", "delta": None}
    if "unavailable" in statuses and all(s in ("unavailable", "match") for s in statuses):
        if all(s == "unavailable" for s in statuses):
            return {"status": "unavailable", "delta": None}
    if "rounding_match" in statuses:
        delta = next((p.get("delta") for p in parts if p.get("status") == "rounding_match"), 0)
        return {"status": "rounding_match", "delta": delta}
    delta = next((p.get("delta") for p in parts if p.get("delta") is not None), 0)
    return {"status": "match", "delta": delta}


def _input(
    *,
    key: str,
    label: str,
    value: Any,
    display_value: str | None = None,
    source_path: str,
    source_type: str = "persisted_snapshot",
    derivation: str | None = None,
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
    if derivation:
        out["derivation"] = derivation
    return out


def _component_from_pillar(c: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {
        "key": c.get("key"),
        "label": c.get("label"),
        "value": c.get("value"),
        "unit": c.get("unit"),
    }
    if c.get("weight") is not None:
        out["weight"] = c.get("weight")
    if c.get("contribution") is not None:
        out["contribution"] = c.get("contribution")
    if c.get("source") is not None:
        out["source"] = c.get("source")
    return out


def _f36_classification_trace(f36_abs: float | None, matched_label: str | None) -> list[dict[str, Any]]:
    rules = [
        ("Equilibrio forte", "indice abs <= 0.50 → score 100", lambda a: a is not None and a <= 0.50),
        ("Equilibrio", "0.50 < abs <= 1.00 → score 80", lambda a: a is not None and 0.50 < a <= 1.00),
        ("Transizione", "1.00 < abs <= 1.50 → score 60", lambda a: a is not None and 1.00 < a <= 1.50),
        ("Squilibrio", "abs > 1.50 → score 40", lambda a: a is not None and a > 1.50),
    ]
    return [
        {
            "class": label,
            "condition": cond,
            "matched": bool(pred(f36_abs)) and (matched_label is None or matched_label == label),
        }
        for label, cond, pred in rules
    ]


def _conviction_classification_trace(index: float | None, matched: str | None) -> list[dict[str, Any]]:
    rules = [
        ("Molto Debole", "indice < 20", lambda v: v is not None and v < 20),
        ("Debole", "20 <= indice < 40", lambda v: v is not None and 20 <= v < 40),
        ("Moderata", "40 <= indice < 60", lambda v: v is not None and 40 <= v < 60),
        ("Forte", "60 <= indice < 80", lambda v: v is not None and 60 <= v < 80),
        ("Molto Forte", "indice >= 80", lambda v: v is not None and v >= 80),
    ]
    return [
        {
            "class": label,
            "condition": cond,
            "matched": bool(pred(index)) and (matched is None or matched == label),
        }
        for label, cond, pred in rules
    ]


def _draw_classification_trace(quota_x: float | None, matched: str | None) -> list[dict[str, Any]]:
    rules = [
        ("Pareggio forte", "quota_x <= 3.20", lambda q: q is not None and q <= 3.20),
        ("Pareggio possibile", "3.20 < quota_x <= 3.60", lambda q: q is not None and 3.20 < q <= 3.60),
        ("Pareggio debole", "3.60 < quota_x <= 4.20", lambda q: q is not None and 3.60 < q <= 4.20),
        ("Pareggio poco probabile", "quota_x > 4.20", lambda q: q is not None and q > 4.20),
    ]
    return [
        {
            "class": label,
            "condition": cond,
            "matched": bool(pred(quota_x)) and (matched is None or matched == label),
        }
        for label, cond, pred in rules
    ]


def _gap_classification_trace(index: float | None, matched: str | None) -> list[dict[str, Any]]:
    rules = [
        ("Non Confermato", "indice < 20", lambda v: v is not None and v < 20),
        ("Debole", "20 <= indice < 40", lambda v: v is not None and 20 <= v < 40),
        ("Parziale", "40 <= indice < 60", lambda v: v is not None and 40 <= v < 60),
        ("Confermato", "60 <= indice < 80", lambda v: v is not None and 60 <= v < 80),
        ("Fortemente Confermato", "indice >= 80", lambda v: v is not None and v >= 80),
    ]
    return [
        {
            "class": label,
            "condition": cond,
            "matched": bool(pred(index)) and (matched is None or matched == label),
        }
        for label, cond, pred in rules
    ]


def _resolve_source_mode(output: dict[str, Any]) -> str:
    persisted = output.get(BALANCE_MONITORING_KEY)
    if isinstance(persisted, dict) and persisted:
        status = str(persisted.get("status") or "").strip().lower()
        if status != "unavailable" and (
            persisted.get("f36_index") is not None
            or persisted.get("prob_1_norm") is not None
            or persisted.get("pillars")
        ):
            return "persisted_balance_v5_monitoring"
    final = output.get("final")
    if isinstance(final, dict) and final.get("status") == "available":
        return "derived_read_only_from_stored_snapshot"
    return "unavailable"


def _extract_norm_probs(final: dict[str, Any]) -> tuple[float | None, float | None, float | None]:
    p1 = _prob_to_percent(_num(final.get("prob_1")), _num(final.get("prob_1_pct")))
    px = _prob_to_percent(_num(final.get("prob_x")), _num(final.get("prob_x_pct")))
    p2 = _prob_to_percent(_num(final.get("prob_2")), _num(final.get("prob_2_pct")))
    return _normalize_3way_probs(p1, px, p2)


def _goal_ou_from_output(output: dict[str, Any]) -> tuple[float | None, float | None, float | None, float | None]:
    from app.services.cecchino.cecchino_balance_v5 import (
        _goal_odds_from_markets,
        _goal_probs_from_odds,
    )

    gm = output.get("goal_markets") if isinstance(output.get("goal_markets"), dict) else {}
    under_odd, over_odd = _goal_odds_from_markets(gm)
    under_pct, over_pct = _goal_probs_from_odds(under_odd, over_odd)
    if under_pct is not None and over_pct is not None:
        under_pct, over_pct = _normalize_2way_probs(under_pct, over_pct)
    return under_odd, over_odd, under_pct, over_pct


def _pillar_dict(balance: dict[str, Any], canonical_key: str) -> dict[str, Any]:
    pillars = balance.get("pillars")
    if isinstance(pillars, dict):
        p = pillars.get(canonical_key)
        return p if isinstance(p, dict) else {}
    if isinstance(pillars, list):
        for item in pillars:
            if isinstance(item, dict) and item.get("key") == canonical_key:
                return item
    return {}


def _explain_geometry(
    *,
    displayed: dict[str, Any],
    final: dict[str, Any],
    inputs_block: dict[str, Any],
) -> dict[str, Any]:
    quota_1 = _num(final.get("quota_1"))
    quota_2 = _num(final.get("quota_2"))
    if quota_1 is None:
        quota_1 = _num(inputs_block.get("quota_1"))
    if quota_2 is None:
        quota_2 = _num(inputs_block.get("quota_2"))

    formula_symbolic = (
        "F36_signed = Quota_2 − Quota_1\n"
        "F36_abs = |F36_signed|\n"
        "Indice geometria = score discreto da F36_abs "
        "(≤0,50→100; ≤1,00→80; ≤1,50→60; altrimenti→40)\n"
        "Direzione: signed > 0 → lato 1; signed < 0 → lato 2"
    )

    inputs = [
        _input(
            key="quota_1",
            label="Quota 1",
            value=quota_1,
            display_value=_fmt_it(quota_1),
            source_path="cecchino_output_json.final.quota_1",
            derivation="Quota Cecchino segno 1",
        ),
        _input(
            key="quota_2",
            label="Quota 2",
            value=quota_2,
            display_value=_fmt_it(quota_2),
            source_path="cecchino_output_json.final.quota_2",
            derivation="Quota Cecchino segno 2",
        ),
    ]

    if None in (quota_1, quota_2):
        return {
            "pillar_key": "geometry",
            "pillar_number": 1,
            "title": "Geometria della partita",
            "status": "unavailable",
            "classification_type": "official",
            "badge": "UFFICIALE",
            "question": displayed.get("question") or "Quanto è equilibrata la struttura della partita?",
            "description": (
                "Misura quanto la struttura della partita è equilibrata o sbilanciata "
                "usando la distanza tra le quote laterali Cecchino (F36)."
            ),
            "purpose": "Descrivere la geometria 1/2 senza aggregarla agli altri pilastri.",
            "formula_symbolic": formula_symbolic,
            "formula_applied": [],
            "inputs": inputs,
            "components": [_component_from_pillar(c) for c in (displayed.get("components") or [])],
            "displayed_result": {
                "value": displayed.get("index"),
                "display_value": None,
                "class": displayed.get("class_label"),
                "direction": displayed.get("direction"),
            },
            "canonical_audit_result": {
                "value": None,
                "class": None,
                "direction": None,
            },
            "consistency": {"status": "unavailable", "delta": None},
            "classification_trace": [],
            "reason_summary": "Dati F36 non disponibili.",
            "formula_version": BALANCE_VERSION,
            "source_paths": ["cecchino_output_json.final.quota_1", "cecchino_output_json.final.quota_2"],
            "warnings": list(displayed.get("warnings") or ["f36_unavailable"]),
        }

    f36_signed = float(quota_2) - float(quota_1)
    f36_abs = abs(f36_signed)
    classified = _classify_f36(f36_abs, f36_signed)
    audit_score = classified.get("score")
    audit_label = classified.get("label")
    audit_direction = _f36_side_from_signed(f36_signed)

    inputs.extend(
        [
            _input(
                key="f36_signed",
                label="F36",
                value=round(f36_signed, 4),
                display_value=_fmt_it(f36_signed, 4),
                source_path="derived:quota_2-quota_1",
                derivation="Quota 2 − Quota 1",
            ),
            _input(
                key="f36_abs",
                label="|F36|",
                value=round(f36_abs, 4),
                display_value=_fmt_it(f36_abs, 4),
                source_path="derived:abs(f36_signed)",
                derivation="Valore assoluto di F36",
            ),
        ]
    )

    formula_applied = [
        f"F36 = Quota 2 − Quota 1",
        f"F36 = {_fmt_it(quota_2)} − {_fmt_it(quota_1)}",
        f"F36 = {_fmt_it(f36_signed, 4)}",
        f"|F36| = {_fmt_it(f36_abs, 4)}",
        f"Indice geometria = {audit_score}",
        f"Classe = {audit_label}",
        f"Direzione = lato {audit_direction}" if audit_direction else "Direzione = equilibrio (F36 = 0)",
    ]

    disp_val = displayed.get("index")
    disp_class = displayed.get("class_label")
    disp_dir = displayed.get("direction")
    consistency = _merge_consistency(
        _consistency(disp_val, audit_score, abs_tol=1e-9, rounding_tol=0.01),
        _consistency_class(disp_class, audit_label),
        _consistency_class(disp_dir, audit_direction),
    )

    reason = (
        f"Con |F36| = {_fmt_it(f36_abs, 4)} la geometria rientra nella classe «{audit_label}» "
        f"(indice {audit_score})"
    )
    if audit_direction:
        reason += f", con inclinazione strutturale verso il lato {audit_direction}."
    else:
        reason += "."

    return {
        "pillar_key": "geometry",
        "pillar_number": 1,
        "title": "Geometria della partita",
        "status": "available" if displayed.get("status") == "official" else "partial",
        "classification_type": "official",
        "badge": "UFFICIALE",
        "question": displayed.get("question") or "Quanto è equilibrata la struttura della partita?",
        "description": (
            "Misura quanto la struttura della partita è equilibrata o sbilanciata "
            "usando la distanza tra le quote laterali Cecchino (F36 = Quota 2 − Quota 1)."
        ),
        "purpose": (
            "Isolare la geometria 1/2. Non è convinzione del modello né probabilità di pareggio; "
            "non va confrontata numericamente con gli altri indici."
        ),
        "interpretation": displayed.get("reading"),
        "formula_symbolic": formula_symbolic,
        "formula_applied": formula_applied,
        "inputs": inputs,
        "components": [_component_from_pillar(c) for c in (displayed.get("components") or [])],
        "displayed_result": {
            "value": disp_val,
            "display_value": str(disp_val) if disp_val is not None else None,
            "class": disp_class,
            "direction": disp_dir,
        },
        "canonical_audit_result": {
            "value": audit_score,
            "class": audit_label,
            "direction": audit_direction,
            "f36_signed": round(f36_signed, 4),
            "f36_abs": round(f36_abs, 4),
            "class_key": classified.get("class_key"),
        },
        "consistency": consistency,
        "classification_trace": _f36_classification_trace(f36_abs, audit_label),
        "reason_summary": reason,
        "formula_version": BALANCE_VERSION,
        "source_paths": [
            "cecchino_output_json.final.quota_1",
            "cecchino_output_json.final.quota_2",
            "balance_v5.pillars.f36",
        ],
        "warnings": list(displayed.get("warnings") or []),
    }


def _explain_conviction(
    *,
    displayed: dict[str, Any],
    final: dict[str, Any],
    inputs_block: dict[str, Any],
) -> dict[str, Any]:
    p1, px, p2 = (
        _num(inputs_block.get("prob_1_norm")),
        _num(inputs_block.get("prob_x_norm")),
        _num(inputs_block.get("prob_2_norm")),
    )
    if None in (p1, px, p2):
        p1, px, p2 = _extract_norm_probs(final)

    formula_symbolic = (
        "Gap_pp = max(P1, PX, P2) − second(P1, PX, P2)\n"
        "Indice convinzione = 100 × (max − second) / max\n"
        "Classi: <20 Molto Debole; <40 Debole; <60 Moderata; <80 Forte; ≥80 Molto Forte"
    )

    inputs = [
        _input(
            key="prob_1_norm",
            label="Probabilità 1 normalizzata",
            value=p1,
            display_value=_fmt_pct(p1),
            source_path="cecchino_output_json.final → normalize_3way",
            derivation="Probabilità 1/X/2 normalizzate a somma 100",
        ),
        _input(
            key="prob_x_norm",
            label="Probabilità X normalizzata",
            value=px,
            display_value=_fmt_pct(px),
            source_path="cecchino_output_json.final → normalize_3way",
        ),
        _input(
            key="prob_2_norm",
            label="Probabilità 2 normalizzata",
            value=p2,
            display_value=_fmt_pct(p2),
            source_path="cecchino_output_json.final → normalize_3way",
        ),
    ]

    audit_index = conviction_index(p1, px, p2)
    audit_class = classify_conviction(audit_index)
    dominance_pp = compute_dominance_pp(p1, px, p2)

    ordered: list[tuple[str, float]] = []
    if None not in (p1, px, p2):
        ordered = sorted(
            [("1", float(p1)), ("X", float(px)), ("2", float(p2))],
            key=lambda t: t[1],
            reverse=True,
        )
    top = ordered[0] if ordered else (None, None)
    second = ordered[1] if len(ordered) > 1 else (None, None)
    audit_direction = top[0]

    formula_applied: list[str] = []
    if top[0] is not None and second[0] is not None:
        formula_applied = [
            f"Probabilità scenario principale ({top[0]}) = {_fmt_pct(top[1])}",
            f"Probabilità secondo scenario ({second[0]}) = {_fmt_pct(second[1])}",
            "Gap = P1 − P2 (in punti percentuali sul dominio 1/X/2)",
            f"Gap = {_fmt_pct(top[1])} − {_fmt_pct(second[1])}",
            f"Gap = {_fmt_it(dominance_pp)} pp",
            f"Indice convinzione = 100 × ({_fmt_it(top[1])} − {_fmt_it(second[1])}) / {_fmt_it(top[1])}",
            f"Indice convinzione = {_fmt_it(audit_index)}",
            f"Classe = {audit_class}",
            f"Scenario dominante = {audit_direction}",
        ]

    disp_val = displayed.get("index")
    disp_class = displayed.get("class_label")
    disp_dir = displayed.get("direction")
    consistency = _merge_consistency(
        _consistency(disp_val, audit_index, abs_tol=1e-9, rounding_tol=0.01),
        _consistency_class(disp_class, audit_class),
        _consistency_class(str(disp_dir) if disp_dir is not None else None, audit_direction),
    )

    if audit_index is None:
        reason = "Probabilità normalizzate insufficienti per calcolare la convinzione."
        status = "unavailable"
    else:
        reason = (
            f"Lo scenario dominante è {audit_direction} con gap {_fmt_it(dominance_pp)} pp "
            f"e indice convinzione {_fmt_it(audit_index)} → classe «{audit_class}»."
        )
        status = "available" if displayed.get("status") == "official" else "partial"

    return {
        "pillar_key": "conviction",
        "pillar_number": 2,
        "title": "Convinzione del modello",
        "status": status,
        "classification_type": "official",
        "badge": "UFFICIALE",
        "question": displayed.get("question") or "Quanto il modello è convinto dello scenario principale?",
        "description": (
            "Misura quanto il modello è convinto dello scenario principale rispetto al secondo, "
            "sulle probabilità normalizzate 1/X/2."
        ),
        "purpose": (
            "Separare l’intensità della preferenza probabilistica dalla geometria delle quote. "
            "Non confondere probabilità, gap in pp e indice 0–100."
        ),
        "interpretation": displayed.get("reading"),
        "formula_symbolic": formula_symbolic,
        "formula_applied": formula_applied,
        "inputs": inputs,
        "components": [_component_from_pillar(c) for c in (displayed.get("components") or [])],
        "displayed_result": {
            "value": disp_val,
            "display_value": _fmt_it(_num(disp_val)) if disp_val is not None else None,
            "class": disp_class,
            "direction": disp_dir,
        },
        "canonical_audit_result": {
            "value": audit_index,
            "class": audit_class,
            "direction": audit_direction,
            "dominance_pp": dominance_pp,
            "top_prob": top[1],
            "second_prob": second[1],
        },
        "consistency": consistency,
        "classification_trace": _conviction_classification_trace(audit_index, audit_class),
        "reason_summary": reason,
        "formula_version": BALANCE_VERSION,
        "source_paths": [
            "cecchino_output_json.final.prob_1",
            "cecchino_output_json.final.prob_x",
            "cecchino_output_json.final.prob_2",
            "balance_v5.pillars.dominance",
        ],
        "warnings": list(displayed.get("warnings") or []),
    }


def _explain_draw_credibility(
    *,
    displayed: dict[str, Any],
    final: dict[str, Any],
    inputs_block: dict[str, Any],
    output: dict[str, Any],
) -> dict[str, Any]:
    p1, px, p2 = (
        _num(inputs_block.get("prob_1_norm")),
        _num(inputs_block.get("prob_x_norm")),
        _num(inputs_block.get("prob_2_norm")),
    )
    if None in (p1, px, p2):
        p1, px, p2 = _extract_norm_probs(final)
    quota_x = _num(final.get("quota_x"))
    if quota_x is None:
        quota_x = _num(inputs_block.get("quota_x"))

    x_rank, _tied = x_rank_from_probs(p1, px, p2)
    under_odd, over_odd, under_norm, over_norm = _goal_ou_from_output(output)

    ordered: list[tuple[str, float]] = []
    if None not in (p1, px, p2):
        ordered = sorted(
            [("1", float(p1)), ("X", float(px)), ("2", float(p2))],
            key=lambda t: t[1],
            reverse=True,
        )
    dominant = ordered[0][0] if ordered else None

    formula_symbolic = (
        "Indice = P(X) normalizzata (0–100)\n"
        "Classe da Quota X: ≤3,20 forte; ≤3,60 possibile; ≤4,20 debole; altrimenti poco probabile\n"
        "Pilastro DESCITTIVO: non è probabilità calibrata sull’esito reale"
    )

    inputs = [
        _input(
            key="prob_x_norm",
            label="Probabilità X normalizzata",
            value=px,
            display_value=_fmt_pct(px),
            source_path="cecchino_output_json.final → normalize_3way",
        ),
        _input(
            key="quota_x",
            label="Quota X",
            value=quota_x,
            display_value=_fmt_it(quota_x),
            source_path="cecchino_output_json.final.quota_x",
        ),
        _input(
            key="prob_1_norm",
            label="Probabilità 1 normalizzata",
            value=p1,
            display_value=_fmt_pct(p1),
            source_path="cecchino_output_json.final → normalize_3way",
        ),
        _input(
            key="prob_2_norm",
            label="Probabilità 2 normalizzata",
            value=p2,
            display_value=_fmt_pct(p2),
            source_path="cecchino_output_json.final → normalize_3way",
        ),
        _input(
            key="x_rank",
            label="Rank X",
            value=x_rank,
            display_value=str(x_rank) if x_rank is not None else "—",
            source_path="derived:x_rank_from_probs",
            derivation="Posizione della X nel ranking 1/X/2",
        ),
        _input(
            key="dominant_sign",
            label="Segno dominante",
            value=dominant,
            display_value=str(dominant) if dominant else "—",
            source_path="derived:argmax(prob_1,prob_x,prob_2)",
        ),
    ]
    if under_norm is not None:
        inputs.append(
            _input(
                key="prob_under_2_5_norm",
                label="Prob. Under 2.5 (norm)",
                value=under_norm,
                display_value=_fmt_pct(under_norm),
                source_path="cecchino_output_json.goal_markets.under_2_5",
            )
        )
    if over_norm is not None:
        inputs.append(
            _input(
                key="prob_over_2_5_norm",
                label="Prob. Over 2.5 (norm)",
                value=over_norm,
                display_value=_fmt_pct(over_norm),
                source_path="cecchino_output_json.goal_markets.over_2_5",
            )
        )

    draw_class = _classify_draw(quota_x) if quota_x is not None else {}
    audit_label = draw_class.get("label")
    audit_index = px

    rank_txt = {1: "prima", 2: "seconda", 3: "terza"}.get(x_rank or 0, str(x_rank))
    formula_applied = [
        f"P(X) normalizzata = {_fmt_pct(px)}",
        f"Rank X = {rank_txt} probabilità" if x_rank else "Rank X = n/d",
        f"Segno dominante = {dominant}" if dominant else "Segno dominante = n/d",
    ]
    if under_norm is not None and over_norm is not None:
        formula_applied.append(f"Under 2.5 = {_fmt_pct(under_norm)}")
        formula_applied.append(f"Over 2.5 = {_fmt_pct(over_norm)}")
    if audit_label:
        formula_applied.append(f"Classe quota X = {audit_label}")
    formula_applied.append(
        "Indice descrittivo, non ancora probabilità calibrata sull’esito reale."
    )

    disp_val = displayed.get("index")
    disp_class = displayed.get("class_label")
    consistency = _merge_consistency(
        _consistency(disp_val, audit_index, abs_tol=1e-9, rounding_tol=0.01),
        _consistency_class(disp_class, audit_label),
    )

    if px is None or quota_x is None:
        reason = "Dati X insufficienti."
        status = "unavailable"
    else:
        reason = (
            f"P(X) = {_fmt_pct(px)} (rank {rank_txt}); Quota X = {_fmt_it(quota_x)} → "
            f"classe «{audit_label}». Indice descrittivo, non probabilità calibrata."
        )
        status = (
            "available"
            if displayed.get("status") in ("descriptive_official", "official")
            else "partial"
        )

    return {
        "pillar_key": "draw_credibility",
        "pillar_number": 3,
        "title": "Credibilità della X",
        "status": status,
        "classification_type": "descriptive",
        "badge": "DESCRITTIVO",
        "question": displayed.get("question")
        or "Quanto il pareggio è credibile secondo il modello Cecchino?",
        "description": (
            "Indice descrittivo interno basato sulla probabilità X normalizzata e sulla classe "
            "derivata dalla Quota X. Non è probabilità calibrata sull’esito reale."
        ),
        "purpose": (
            "Offrire una lettura descrittiva della credibilità del pareggio. "
            "Non confrontare questo indice con geometria, convinzione o coerenza."
        ),
        "methodological_caution": (
            "Indice descrittivo, non ancora probabilità calibrata sull’esito reale."
        ),
        "interpretation": displayed.get("reading") or displayed.get("informational_note"),
        "formula_symbolic": formula_symbolic,
        "formula_applied": formula_applied,
        "inputs": inputs,
        "components": [_component_from_pillar(c) for c in (displayed.get("components") or [])],
        "displayed_result": {
            "value": disp_val,
            "display_value": _fmt_pct(_num(disp_val)) if disp_val is not None else None,
            "class": disp_class,
            "direction": displayed.get("direction"),
        },
        "canonical_audit_result": {
            "value": audit_index,
            "class": audit_label,
            "direction": None,
            "x_rank": x_rank,
            "dominant_sign": dominant,
            "under_2_5_norm": under_norm,
            "over_2_5_norm": over_norm,
            "quota_x": quota_x,
            "under_odd": under_odd,
            "over_odd": over_odd,
        },
        "consistency": consistency,
        "classification_trace": _draw_classification_trace(quota_x, audit_label),
        "reason_summary": reason,
        "formula_version": BALANCE_VERSION,
        "source_paths": [
            "cecchino_output_json.final.prob_x",
            "cecchino_output_json.final.quota_x",
            "cecchino_output_json.goal_markets",
            "balance_v5.pillars.draw_credibility",
        ],
        "warnings": list(displayed.get("warnings") or []),
    }


def _explain_coherence(
    *,
    displayed: dict[str, Any],
    final: dict[str, Any],
    inputs_block: dict[str, Any],
    geometry_audit: dict[str, Any],
) -> dict[str, Any]:
    p1, px, p2 = (
        _num(inputs_block.get("prob_1_norm")),
        _num(inputs_block.get("prob_x_norm")),
        _num(inputs_block.get("prob_2_norm")),
    )
    if None in (p1, px, p2):
        p1, px, p2 = _extract_norm_probs(final)

    f36_score = None
    geo_can = geometry_audit.get("canonical_audit_result") or {}
    if isinstance(geo_can, dict):
        f36_score = _num(geo_can.get("value"))
    f36_direction = geo_can.get("direction") if isinstance(geo_can, dict) else None

    gap_pp = probability_gap_1_2_pp(p1, p2)
    prob_bal = probability_balance_index(p1, p2)
    audit_index = gap_coherence_index(f36_score, prob_bal)
    audit_class = classify_gap_coherence(audit_index)

    ordered: list[tuple[str, float]] = []
    if None not in (p1, p2):
        # Dominanza laterale 1/2 (senza X) per contesto narrativo
        ordered = sorted([("1", float(p1)), ("2", float(p2))], key=lambda t: t[1], reverse=True)
    dominant_12 = ordered[0][0] if ordered else None

    formula_symbolic = (
        "gap_pp = |P1 − P2|\n"
        "prob_balance = 100 × (1 − |P1 − P2| / (P1 + P2))\n"
        "indice_coerenza = 100 − |f36_score − prob_balance|\n"
        "Classi: <20 Non Confermato; <40 Debole; <60 Parziale; <80 Confermato; ≥80 Fortemente Confermato"
    )

    inputs = [
        _input(
            key="prob_1_norm",
            label="Probabilità 1 normalizzata",
            value=p1,
            display_value=_fmt_pct(p1),
            source_path="cecchino_output_json.final → normalize_3way",
        ),
        _input(
            key="prob_2_norm",
            label="Probabilità 2 normalizzata",
            value=p2,
            display_value=_fmt_pct(p2),
            source_path="cecchino_output_json.final → normalize_3way",
        ),
        _input(
            key="f36_score",
            label="Indice geometria (F36 score)",
            value=f36_score,
            display_value=_fmt_it(f36_score, 0) if f36_score is not None else "—",
            source_path="balance_v5.pillars.f36.index",
            derivation="Score discreto del pilastro Geometria",
        ),
        _input(
            key="probability_gap_1_2_pp",
            label="Gap probabilistico 1/2",
            value=gap_pp,
            display_value=f"{_fmt_it(gap_pp)} pp" if gap_pp is not None else "—",
            source_path="derived:|prob_1_norm-prob_2_norm|",
            derivation="|P1 − P2|",
        ),
        _input(
            key="probability_balance_index",
            label="Indice equilibrio probabilistico",
            value=prob_bal,
            display_value=_fmt_it(prob_bal),
            source_path="derived:probability_balance_index",
            derivation="100 × (1 − |P1−P2|/(P1+P2))",
        ),
    ]
    if px is not None:
        inputs.append(
            _input(
                key="prob_x_norm",
                label="Probabilità X normalizzata",
                value=px,
                display_value=_fmt_pct(px),
                source_path="cecchino_output_json.final → normalize_3way",
            )
        )

    formula_applied: list[str] = []
    if f36_direction:
        formula_applied.append(f"Direzione strutturale F36 = lato {f36_direction}")
    if dominant_12:
        formula_applied.append(f"Scenario probabilistico dominante (1/2) = {dominant_12}")
    if p1 is not None and p2 is not None:
        top_p, sec_p = (p1, p2) if float(p1) >= float(p2) else (p2, p1)
        formula_applied.extend(
            [
                "Gap probabilistico = |Probabilità 1 − Probabilità 2|",
                f"Gap = {_fmt_pct(p1)} − {_fmt_pct(p2)} (in valore assoluto)",
                f"Gap = {_fmt_it(gap_pp)} pp",
                f"prob_balance = {_fmt_it(prob_bal)}",
                f"Indice coerenza = 100 − |{_fmt_it(f36_score)} − {_fmt_it(prob_bal)}|",
                f"Indice coerenza = {_fmt_it(audit_index)}",
                f"Classe = {audit_class}",
            ]
        )
        if f36_direction and dominant_12:
            aligned = f36_direction == dominant_12
            formula_applied.append(
                f"Contesto direzionale F36 vs 1/2 = {'allineato' if aligned else 'non allineato'} "
                "(informativo; non entra nella formula dell’indice)"
            )

    disp_val = displayed.get("index")
    disp_class = displayed.get("class_label")
    consistency = _merge_consistency(
        _consistency(disp_val, audit_index, abs_tol=1e-9, rounding_tol=0.01),
        _consistency_class(disp_class, audit_class),
    )

    if audit_index is None:
        reason = "Dati insufficienti per la coerenza matematica 1/2."
        status = "unavailable"
    else:
        reason = (
            f"Con gap {_fmt_it(gap_pp)} pp e F36 score {_fmt_it(f36_score)}, "
            f"l’indice di coerenza è {_fmt_it(audit_index)} → classe «{audit_class}»."
        )
        status = "available" if displayed.get("status") == "official" else "partial"

    return {
        "pillar_key": "coherence_1_2",
        "pillar_number": 4,
        "title": "Coerenza matematica 1/2",
        "status": status,
        "classification_type": "official",
        "badge": "UFFICIALE",
        "question": displayed.get("question")
        or "Le probabilità confermano la geometria descritta da F36?",
        "description": (
            "Confronta lo score di geometria F36 con l’equilibrio probabilistico tra 1 e 2 "
            "per verificare se probabilità e geometria sono coerenti."
        ),
        "purpose": (
            "Misurare la coerenza tra geometria e probabilità laterali. "
            "Non è un verdetto sul risultato né un aggregato dei quattro pilastri."
        ),
        "interpretation": displayed.get("reading"),
        "formula_symbolic": formula_symbolic,
        "formula_applied": formula_applied,
        "inputs": inputs,
        "components": [_component_from_pillar(c) for c in (displayed.get("components") or [])],
        "displayed_result": {
            "value": disp_val,
            "display_value": _fmt_it(_num(disp_val)) if disp_val is not None else None,
            "class": disp_class,
            "direction": displayed.get("direction"),
        },
        "canonical_audit_result": {
            "value": audit_index,
            "class": audit_class,
            "direction": None,
            "gap_pp": gap_pp,
            "prob_balance": prob_bal,
            "f36_score": f36_score,
            "dominant_1_2": dominant_12,
            "f36_direction": f36_direction,
        },
        "consistency": consistency,
        "classification_trace": _gap_classification_trace(audit_index, audit_class),
        "reason_summary": reason,
        "formula_version": BALANCE_VERSION,
        "source_paths": [
            "cecchino_output_json.final.prob_1",
            "cecchino_output_json.final.prob_2",
            "balance_v5.pillars.f36",
            "balance_v5.pillars.gap_coherence",
        ],
        "warnings": list(displayed.get("warnings") or []),
    }


def build_balance_explanations(row: CecchinoTodayFixture) -> dict[str, Any]:
    """Costruisce l’audit Balance v5 per una fixture (solo lettura snapshot)."""
    output = row.cecchino_output_json if isinstance(row.cecchino_output_json, dict) else {}
    final = output.get("final") if isinstance(output.get("final"), dict) else {}
    source_mode = _resolve_source_mode(output)

    if source_mode == "unavailable" or final.get("status") != "available":
        return {
            "status": "error",
            "code": "balance_not_available",
            "message": "Balance v5 non disponibile per questa fixture",
            "source_mode": "unavailable",
            "no_operational_recalculation": True,
            "diagnostic_re_evaluation_only": True,
        }

    kpi_panel = row.kpi_panel_json if isinstance(row.kpi_panel_json, dict) else None
    balance = build_cecchino_balance_v5(
        cecchino_final=final,
        goal_markets=output.get("goal_markets") if isinstance(output.get("goal_markets"), dict) else None,
        kpi_panel=kpi_panel,
        identity_consistency=None,
    )

    if balance.get("status") == "unavailable":
        return {
            "status": "error",
            "code": "balance_not_available",
            "message": "Balance v5 non disponibile per questa fixture",
            "source_mode": source_mode,
            "no_operational_recalculation": True,
            "diagnostic_re_evaluation_only": True,
        }

    inputs_block = balance.get("inputs") if isinstance(balance.get("inputs"), dict) else {}
    warnings: list[str] = []
    partial = False

    geo_disp = _pillar_dict(balance, "f36")
    conv_disp = _pillar_dict(balance, "dominance")
    draw_disp = _pillar_dict(balance, "draw_credibility")
    gap_disp = _pillar_dict(balance, "gap_coherence")

    geometry = _explain_geometry(displayed=geo_disp, final=final, inputs_block=inputs_block)
    conviction = _explain_conviction(displayed=conv_disp, final=final, inputs_block=inputs_block)
    draw = _explain_draw_credibility(
        displayed=draw_disp,
        final=final,
        inputs_block=inputs_block,
        output=output,
    )
    coherence = _explain_coherence(
        displayed=gap_disp,
        final=final,
        inputs_block=inputs_block,
        geometry_audit=geometry,
    )

    pillars = {
        "geometry": geometry,
        "conviction": conviction,
        "draw_credibility": draw,
        "coherence_1_2": coherence,
    }

    for key, pillar in pillars.items():
        if pillar.get("status") in ("unavailable", "partial"):
            partial = True
        if pillar.get("consistency", {}).get("status") == "mismatch":
            warnings.append(f"consistency_mismatch:{key}")
            partial = True
        warnings.extend(pillar.get("warnings") or [])

    # Dedup warnings
    warnings = list(dict.fromkeys(warnings))

    payload = {
        "status": "partial" if partial else "ok",
        "audit_version": AUDIT_VERSION,
        "module": MODULE,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "no_operational_recalculation": True,
        "diagnostic_re_evaluation_only": True,
        "source_mode": source_mode,
        "fixture": {
            "today_fixture_id": int(row.id),
            "local_fixture_id": int(row.local_fixture_id) if row.local_fixture_id else None,
            "provider_fixture_id": int(row.provider_fixture_id) if row.provider_fixture_id else None,
            "home_team": row.home_team_name,
            "away_team": row.away_team_name,
            "kickoff": row.kickoff.isoformat() if row.kickoff else None,
            "scan_date": row.scan_date.isoformat() if row.scan_date else None,
        },
        "overview": {
            "version": BALANCE_VERSION,
            "pre_match_only": True,
            "official_pillars": list(OFFICIAL_PILLARS),
            "descriptive_pillars": list(DESCRIPTIVE_PILLARS),
            "canonical_pillar_order": list(PILLAR_ORDER),
            "audit_pillar_order": [k for k, *_ in PILLAR_AUDIT_KEYS],
        },
        "pillars": pillars,
        "warnings": warnings,
        "metadata": {
            "displayed_source": "build_cecchino_balance_v5_from_stored_snapshot",
            "balance_status": balance.get("status"),
        },
    }
    return _json_safe(payload)


def get_balance_explanations(db: Session, today_fixture_id: int) -> dict[str, Any] | None:
    row = db.get(CecchinoTodayFixture, today_fixture_id)
    if row is None:
        return None
    if row.eligibility_status != ELIGIBILITY_ELIGIBLE:
        return {
            "status": "error",
            "code": "not_eligible",
            "message": "Fixture non eleggibile",
            "no_operational_recalculation": True,
            "diagnostic_re_evaluation_only": True,
        }
    return build_balance_explanations(row)
