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
    X_MEAN_FULL_EFFECT_DISTANCE,
    X_MEAN_MAX_ADJUSTMENT,
    X_MEAN_THRESHOLD,
    _classify_adjusted_f36_index,
    _classify_draw,
    _classify_f36,
    _compute_x_mean_adjustment,
    _f36_side_from_signed,
    _is_valid_ft_draw_quote,
    _normalize_2way_probs,
    _normalize_3way_probs,
    _num,
    _prob_to_percent,
    build_cecchino_balance_v5,
    classify_conviction,
    classify_gap_coherence,
    clamp_index,
    compute_dominance_pp,
    conviction_index,
    dominant_side_to_market_label,
    gap_coherence_index,
    probability_balance_index,
    probability_gap_1_2_pp,
    x_rank_from_probs,
)
from app.services.cecchino.cecchino_balance_v5_monitoring import BALANCE_MONITORING_KEY

AUDIT_VERSION = "cecchino_balance_explanations_v2"
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
            "stage": "f36_base",
            "class": label,
            "condition": cond,
            "matched": bool(pred(f36_abs)) and (matched_label is None or matched_label == label),
        }
        for label, cond, pred in rules
    ]


def _adjusted_f36_classification_trace(
    index: float | None, matched_label: str | None
) -> list[dict[str, Any]]:
    rules = [
        ("Equilibrio forte", "indice finale >= 90", lambda v: v is not None and v >= 90),
        ("Equilibrio", "70 <= indice finale < 90", lambda v: v is not None and 70 <= v < 90),
        ("Transizione", "50 <= indice finale < 70", lambda v: v is not None and 50 <= v < 70),
        ("Squilibrio", "indice finale < 50", lambda v: v is not None and v < 50),
    ]
    return [
        {
            "stage": "adjusted_index",
            "class": label,
            "condition": cond,
            "matched": bool(pred(index)) and (matched_label is None or matched_label == label),
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
    quota_x_cecchino = _num(final.get("quota_x"))
    if quota_1 is None:
        quota_1 = _num(inputs_block.get("quota_1"))
    if quota_2 is None:
        quota_2 = _num(inputs_block.get("quota_2"))
    if quota_x_cecchino is None:
        quota_x_cecchino = _num(inputs_block.get("quota_x"))

    quota_x_book = _num(displayed.get("quota_x_book"))
    if quota_x_book is None:
        quota_x_book = _num(inputs_block.get("quota_x_book"))
    book_source = displayed.get("x_mean_book_source")
    book_real = displayed.get("x_mean_book_real")
    x_status = displayed.get("x_mean_source_status")

    formula_symbolic = (
        "SEZIONE A — INPUT\n"
        "Quota 1 Cecchino, Quota 2 Cecchino, Quota X Book, Quota X Cecchino\n"
        "\n"
        "SEZIONE B — F36 BASE\n"
        "F36_signed = Quota_2 − Quota_1\n"
        "F36_abs = |F36_signed|\n"
        "Indice F36 base = score discreto da F36_abs "
        "(≤0,50→100; ≤1,00→80; ≤1,50→60; altrimenti→40)\n"
        "\n"
        "SEZIONE C — QUOTA MEDIA X\n"
        "Quota Media X = (Quota Book X + Quota Cecchino X) / 2\n"
        f"delta = {X_MEAN_THRESHOLD} − Quota Media X\n"
        f"forza = clamp(|delta| / {X_MEAN_FULL_EFFECT_DISTANCE}, 0, 1)\n"
        f"correzione = ±{X_MEAN_MAX_ADJUSTMENT} × forza "
        "(sotto 3,60 → equilibrio; >= 3,60 → squilibrio)\n"
        "\n"
        "SEZIONE D — RISULTATO FINALE\n"
        "Indice finale = clamp(Indice F36 base + correzione, 0, 100)\n"
        "Classi finali: >=90 Equilibrio forte; >=70 Equilibrio; >=50 Transizione; <50 Squilibrio"
    )

    inputs = [
        _input(
            key="quota_1",
            label="Quota 1 Cecchino",
            value=quota_1,
            display_value=_fmt_it(quota_1),
            source_path="cecchino_output_json.final.quota_1",
            derivation="Quota Cecchino segno 1",
        ),
        _input(
            key="quota_2",
            label="Quota 2 Cecchino",
            value=quota_2,
            display_value=_fmt_it(quota_2),
            source_path="cecchino_output_json.final.quota_2",
            derivation="Quota Cecchino segno 2",
        ),
        _input(
            key="quota_x_book",
            label="Quota X Book",
            value=quota_x_book,
            display_value=_fmt_it(quota_x_book),
            source_path="kpi_panel_json.rows[SEL_DRAW].quota_book",
            derivation=(
                f"Book FT X (source={book_source or '—'}; "
                f"real={book_real}; status={x_status or '—'})"
            ),
        ),
        _input(
            key="quota_x_cecchino",
            label="Quota X Cecchino",
            value=quota_x_cecchino if _is_valid_ft_draw_quote(quota_x_cecchino) else None,
            display_value=_fmt_it(quota_x_cecchino) if _is_valid_ft_draw_quote(quota_x_cecchino) else "—",
            source_path="cecchino_output_json.final.quota_x",
            derivation="Quota Cecchino segno X (FT)",
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
                "usando F36 base e, quando disponibile, la correzione Quota Media X."
            ),
            "purpose": "Descrivere la geometria 1/2 senza aggregarla agli altri pilastri.",
            "formula_symbolic": formula_symbolic,
            "formula_applied": [],
            "formula_sections": {
                "A_input": "Quote laterali e quote X non disponibili.",
                "B_f36_base": "F36 base non calcolabile.",
                "C_quota_media_x": "Quota Media X non applicata.",
                "D_final": "Risultato finale non disponibile.",
            },
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
            "audit_version": AUDIT_VERSION,
            "source_paths": ["cecchino_output_json.final.quota_1", "cecchino_output_json.final.quota_2"],
            "warnings": list(displayed.get("warnings") or ["f36_unavailable"]),
        }

    f36_signed = float(quota_2) - float(quota_1)
    f36_abs = abs(f36_signed)
    classified = _classify_f36(f36_abs, f36_signed)
    base_index = float(classified.get("score"))
    base_label = classified.get("label")
    base_class_key = classified.get("class_key")
    audit_direction = _f36_side_from_signed(f36_signed)

    # Quota Media X
    cec_ok = _is_valid_ft_draw_quote(quota_x_cecchino)
    book_ok = (
        book_real is not False
        and x_status == "available"
        and _is_valid_ft_draw_quote(quota_x_book)
    )
    # Prefer displayed pillar values when present (already validated by builder)
    if displayed.get("calculation_quality") == "f36_with_x_mean":
        book_ok = _is_valid_ft_draw_quote(displayed.get("quota_x_book") or quota_x_book)
        cec_ok = _is_valid_ft_draw_quote(displayed.get("quota_x_cecchino") or quota_x_cecchino)
        quota_x_book = _num(displayed.get("quota_x_book")) or quota_x_book
        quota_x_cecchino = _num(displayed.get("quota_x_cecchino")) or quota_x_cecchino

    quota_x_media = None
    x_adj = 0.0
    x_strength = None
    x_delta = None
    x_direction = None
    if book_ok and cec_ok:
        quota_x_media = (float(quota_x_book) + float(quota_x_cecchino)) / 2.0
        adj = _compute_x_mean_adjustment(quota_x_media)
        x_delta = adj["x_mean_delta"]
        x_strength = adj["x_mean_strength"]
        x_direction = adj["x_mean_direction"]
        x_adj = float(adj["x_mean_adjustment"])

    adjusted_raw = base_index + x_adj
    adjusted_index = clamp_index(adjusted_raw, 0.0, 100.0)
    if displayed.get("calculation_quality") == "f36_base_only" or quota_x_media is None:
        adjusted_index = base_index
        adjusted_raw = base_index
        x_adj = 0.0
        final_label = base_label
        final_key = base_class_key
    else:
        adj_cls = _classify_adjusted_f36_index(adjusted_index)
        final_label = adj_cls["label"]
        final_key = adj_cls["class_key"]

    # Prefer displayed adjusted values for consistency check against UI
    disp_val = displayed.get("index")
    disp_class = displayed.get("class_label")
    disp_dir = displayed.get("direction")
    if displayed.get("adjusted_index") is not None:
        # Recompute from same inputs as builder when possible
        pass

    formula_applied = [
        "— SEZIONE A: INPUT —",
        f"Quota 1 Cecchino = {_fmt_it(quota_1)}",
        f"Quota 2 Cecchino = {_fmt_it(quota_2)}",
        f"Quota X Book = {_fmt_it(quota_x_book) if book_ok else 'non disponibile / non reale'}",
        f"Quota X Cecchino = {_fmt_it(quota_x_cecchino) if cec_ok else 'non disponibile'}",
        "— SEZIONE B: F36 BASE —",
        "F36_signed = Quota 2 − Quota 1",
        f"F36_signed = {_fmt_it(quota_2)} − {_fmt_it(quota_1)} = {_fmt_it(f36_signed, 4)}",
        f"F36_abs = {_fmt_it(f36_abs, 4)}",
        f"Indice F36 base = {base_index}",
        f"Classe F36 base = {base_label}",
        "— SEZIONE C: QUOTA MEDIA X —",
    ]
    if quota_x_media is not None:
        formula_applied.extend(
            [
                f"Quota Media X = ({_fmt_it(quota_x_book)} + {_fmt_it(quota_x_cecchino)}) / 2",
                f"Quota Media X = {_fmt_it(quota_x_media, 4)}",
                f"delta = {_fmt_it(X_MEAN_THRESHOLD)} − {_fmt_it(quota_x_media, 4)} = {_fmt_it(x_delta, 4)}",
                f"forza = clamp(|{_fmt_it(x_delta, 4)}| / {_fmt_it(X_MEAN_FULL_EFFECT_DISTANCE)}, 0, 1) "
                f"= {_fmt_it(x_strength, 4)}",
                f"direzione = {x_direction}",
                f"correzione = {_fmt_it(x_adj, 2)}",
            ]
        )
    else:
        formula_applied.append(
            "Quota Media X non disponibile: correzione = 0 (F36 base preservato)."
        )
    clamped = adjusted_raw != adjusted_index and quota_x_media is not None
    formula_applied.extend(
        [
            "— SEZIONE D: RISULTATO FINALE —",
            f"Indice grezzo = {base_index} + {_fmt_it(x_adj, 2)} = {_fmt_it(adjusted_raw, 4)}",
            f"Indice finale = clamp(..., 0, 100) = {_fmt_it(adjusted_index)}",
            f"Classe base = {base_label}",
            f"Classe finale = {final_label}",
            f"Cambio classe = {'sì' if base_label != final_label else 'no'}",
            f"Clamp applicato = {'sì' if clamped else 'no'}",
            "Rounding = 2 decimali sull'indice finale",
        ]
    )

    formula_sections = {
        "A_input": (
            f"q1={_fmt_it(quota_1)}; q2={_fmt_it(quota_2)}; "
            f"book_x={_fmt_it(quota_x_book) if book_ok else '—'}; "
            f"cec_x={_fmt_it(quota_x_cecchino) if cec_ok else '—'}"
        ),
        "B_f36_base": (
            f"signed={_fmt_it(f36_signed, 4)}; abs={_fmt_it(f36_abs, 4)}; "
            f"index={base_index}; class={base_label}"
        ),
        "C_quota_media_x": (
            f"media={_fmt_it(quota_x_media, 4)}; threshold={_fmt_it(X_MEAN_THRESHOLD)}; "
            f"strength={_fmt_it(x_strength, 4)}; adj={_fmt_it(x_adj, 2)}; dir={x_direction or '—'}"
            if quota_x_media is not None
            else "non applicata (F36 base preservato)"
        ),
        "D_final": (
            f"raw={_fmt_it(adjusted_raw, 4)}; final={_fmt_it(adjusted_index)}; "
            f"class={final_label}; class_change={base_label != final_label}"
        ),
    }

    consistency = _merge_consistency(
        _consistency(disp_val, adjusted_index, abs_tol=1e-9, rounding_tol=0.01),
        _consistency_class(disp_class, final_label),
        _consistency_class(disp_dir, audit_direction),
    )

    reason = (
        f"F36 base |diff|={_fmt_it(f36_abs, 4)} → classe «{base_label}» (indice {base_index}). "
    )
    if quota_x_media is not None:
        reason += (
            f"Quota Media X={_fmt_it(quota_x_media)} → correzione {_fmt_it(x_adj, 2)}; "
            f"indice finale {_fmt_it(adjusted_index)} («{final_label}»)."
        )
    else:
        reason += "Quota Media X non disponibile: mantenuta la valutazione F36 originaria."

    classification_trace = (
        _f36_classification_trace(f36_abs, base_label)
        + _adjusted_f36_classification_trace(adjusted_index, final_label)
    )

    return {
        "pillar_key": "geometry",
        "pillar_number": 1,
        "title": "Geometria della partita",
        "status": "available" if displayed.get("status") == "official" else "partial",
        "classification_type": "official",
        "badge": "UFFICIALE",
        "question": displayed.get("question") or "Quanto è equilibrata la struttura della partita?",
        "description": (
            "Misura la geometria 1/2 con F36 base (quote laterali Cecchino) e, "
            "quando le quote X Book e Cecchino sono valide, applica una correzione "
            "progressiva da Quota Media X rispetto alla soglia 3,60."
        ),
        "purpose": (
            "Isolare la geometria 1/2 corretta dalla Quota Media X. "
            "Non è convinzione del modello né probabilità di pareggio; "
            "non va confrontata numericamente con gli altri indici."
        ),
        "interpretation": displayed.get("reading"),
        "formula_symbolic": formula_symbolic,
        "formula_applied": formula_applied,
        "formula_sections": formula_sections,
        "inputs": inputs,
        "components": [_component_from_pillar(c) for c in (displayed.get("components") or [])],
        "displayed_result": {
            "value": disp_val,
            "display_value": str(disp_val) if disp_val is not None else None,
            "class": disp_class,
            "direction": disp_dir,
            "base_index": displayed.get("base_index"),
            "base_class": displayed.get("base_class_label"),
            "adjusted_index": displayed.get("adjusted_index"),
            "adjusted_class": displayed.get("adjusted_class_label"),
        },
        "canonical_audit_result": {
            "value": adjusted_index,
            "class": final_label,
            "direction": audit_direction,
            "f36_signed": round(f36_signed, 4),
            "f36_abs": round(f36_abs, 4),
            "base_index": base_index,
            "base_class": base_label,
            "base_class_key": base_class_key,
            "quota_x_media": round(quota_x_media, 4) if quota_x_media is not None else None,
            "x_mean_adjustment": round(x_adj, 4),
            "x_mean_strength": round(x_strength, 4) if x_strength is not None else None,
            "x_mean_direction": x_direction,
            "adjusted_index_raw": round(adjusted_raw, 4),
            "adjusted_index": adjusted_index,
            "adjusted_class": final_label,
            "adjusted_class_key": final_key,
            "class_key": final_key,
            "gap_coherence_f36_input": base_index,
        },
        "consistency": consistency,
        "classification_trace": classification_trace,
        "reason_summary": reason,
        "formula_version": BALANCE_VERSION,
        "audit_version": AUDIT_VERSION,
        "source_paths": [
            "cecchino_output_json.final.quota_1",
            "cecchino_output_json.final.quota_2",
            "cecchino_output_json.final.quota_x",
            "kpi_panel_json.rows[SEL_DRAW].quota_book",
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
        # gap_coherence_f36_input = f36_base_index (NON l'indice corretto del Pilastro 1)
        f36_score = _num(geo_can.get("gap_coherence_f36_input"))
        if f36_score is None:
            f36_score = _num(geo_can.get("base_index"))
        if f36_score is None:
            # Legacy audit V1: value era lo score F36 base
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
        "indice_coerenza = 100 − |f36_base_index − prob_balance|\n"
        "gap_coherence_f36_input = f36_base_index (non l'indice F36 corretto)\n"
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
            label="Indice F36 base (input Coerenza)",
            value=f36_score,
            display_value=_fmt_it(f36_score, 0) if f36_score is not None else "—",
            source_path="balance_v5.pillars.f36.base_index",
            derivation="gap_coherence_f36_input = f36_base_index (non pillars.f36.index corretto)",
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
