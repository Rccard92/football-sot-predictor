"""Spiegazioni cella-per-cella della matrice Segnali SI/NO — audit diagnostico.

Fonte di verità visualizzata: signals_matrix persistita.
Riesecuzione build_signals_matrix solo in-memory (diagnostic_re_evaluation_only).
"""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any, Callable

from sqlalchemy.orm import Session

from app.models.cecchino_today_fixture import ELIGIBILITY_ELIGIBLE, CecchinoTodayFixture
from app.services.cecchino.cecchino_constants import STATUS_AVAILABLE
from app.services.cecchino.cecchino_signals_matrix import build_signals_matrix
from app.services.cecchino.cecchino_signal_consensus import (
    CURRENT_SIGNAL_FORMULA_VERSION,
    GROUP_AVAILABLE_COLUMNS,
    LEGACY_SIGNAL_FORMULA_VERSION,
    SIGNAL_CONSENSUS_POLICY_VERSION,
    SINGLE_FORMULA_EXEMPT_GROUPS,
    compute_consensus_for_matrix_row,
    normalize_formula_version,
)
from app.services.cecchino.cecchino_signal_decimal import (
    SIGNAL_FORMULA_DECIMAL_QUANTUM,
    canonical_signal_decimal,
    format_canonical_decimal,
)
from app.services.cecchino.cecchino_signal_target_mapping import map_row_key_to_signal_group

AUDIT_VERSION = "cecchino_signal_explanations_v3"

Ctx = dict[str, Any]
Leaf = dict[str, Any]
Logic = dict[str, Any]
EvalFn = Callable[[Ctx], tuple[str, Logic, list[dict[str, Any]]]]


def _num(v: Any) -> float | None:
    if v is None or isinstance(v, bool):
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(f):
        return None
    return f


def _fmt_it(v: float | None, decimals: int = 2) -> str:
    if v is None:
        return "—"
    return f"{v:.{decimals}f}".replace(".", ",")


def _leaf(
    *,
    condition_key: str,
    label: str,
    left_label: str,
    left_value: Any,
    operator: str,
    right_label: str,
    right_value: Any,
    passed: bool,
    source_path: str,
    left_display: str | None = None,
    right_display: str | None = None,
) -> Leaf:
    ld = left_display if left_display is not None else (
        _fmt_it(_num(left_value)) if _num(left_value) is not None else str(left_value if left_value is not None else "—")
    )
    rd = right_display if right_display is not None else (
        _fmt_it(_num(right_value)) if _num(right_value) is not None else str(right_value if right_value is not None else "—")
    )
    return {
        "condition_key": condition_key,
        "label": label,
        "left_label": left_label,
        "left_value": left_value,
        "left_display": ld,
        "operator": operator,
        "right_label": right_label,
        "right_value": right_value,
        "right_display": rd,
        "expression": f"{ld} {operator} {rd}",
        "passed": passed,
        "source_path": source_path,
    }


def _cmp(left: float | None, op: str, right: float | None) -> bool:
    if left is None or right is None:
        return False
    if op == "<":
        return left < right
    if op == "<=":
        return left <= right
    if op == ">":
        return left > right
    if op == ">=":
        return left >= right
    if op == "==":
        return left == right
    return False


def _cmp_dec(left: Any, op: str, right: Any) -> bool:
    """Confronto Decimal (o None) — usato solo dalle formule DRAW."""
    from decimal import Decimal

    if left is None or right is None:
        return False
    if not isinstance(left, Decimal) or not isinstance(right, Decimal):
        return False
    if op == "<":
        return left < right
    if op == "<=":
        return left <= right
    if op == ">":
        return left > right
    if op == ">=":
        return left >= right
    if op == "==":
        return left == right
    return False


def _draw_canonical_ctx(ctx: Ctx) -> dict[str, Any]:
    """Deriva F32/F33/F34/F36 canonici dallo stesso helper del motore."""
    f32 = canonical_signal_decimal(ctx.get("q1"))
    f33 = canonical_signal_decimal(ctx.get("qx"))
    f34 = canonical_signal_decimal(ctx.get("q2"))
    f36 = canonical_signal_decimal(f34 - f32) if f32 is not None and f34 is not None else None
    return {
        "raw_q1": ctx.get("q1"),
        "raw_qx": ctx.get("qx"),
        "raw_q2": ctx.get("q2"),
        "raw_diff_1_2": ctx.get("diff_1_2"),
        "f32": f32,
        "f33": f33,
        "f34": f34,
        "f36": f36,
        "quantum": format_canonical_decimal(SIGNAL_FORMULA_DECIMAL_QUANTUM) or "0.01",
        "rounding": "ROUND_HALF_UP",
    }


def _draw_leaf(
    *,
    condition_key: str,
    label: str,
    left_label: str,
    raw_value: Any,
    canonical_value: Any,
    operator: str,
    right_label: str,
    right_value: Any,
    passed: bool,
    source_path: str,
) -> Leaf:
    from decimal import Decimal

    left_canon_str = format_canonical_decimal(canonical_value) if isinstance(canonical_value, Decimal) else (
        str(canonical_value) if canonical_value is not None else "—"
    )
    right_str = format_canonical_decimal(right_value) if isinstance(right_value, Decimal) else str(right_value)
    leaf = _leaf(
        condition_key=condition_key,
        label=label,
        left_label=left_label,
        left_value=left_canon_str,
        operator=operator,
        right_label=right_label,
        right_value=right_str,
        passed=passed,
        source_path=source_path,
        left_display=left_canon_str.replace(".", ",") if left_canon_str != "—" else "—",
        right_display=right_str.replace(".", ","),
    )
    leaf["raw_value"] = raw_value
    leaf["canonical_value"] = left_canon_str if left_canon_str != "—" else None
    leaf["quantum"] = format_canonical_decimal(SIGNAL_FORMULA_DECIMAL_QUANTUM) or "0.01"
    leaf["rounding"] = "ROUND_HALF_UP"
    leaf["comparison"] = f"{left_canon_str} {operator} {right_str}"
    return leaf


def _and_result(leaves: list[Leaf]) -> str:
    return "SI" if leaves and all(bool(x.get("passed")) for x in leaves) else "NO"


def _or_result(branches: list[Logic]) -> str:
    return "SI" if any(b.get("result") == "SI" for b in branches) else "NO"


def _group_and(key: str, label: str, leaves: list[Leaf]) -> Logic:
    return {
        "operator": "AND",
        "group_key": key,
        "label": label,
        "conditions": leaves,
        "result": _and_result(leaves),
    }


def _group_or(key: str, label: str, branches: list[Logic]) -> Logic:
    return {
        "operator": "OR",
        "group_key": key,
        "label": label,
        "branches": branches,
        "result": _or_result(branches),
    }


def _si_no(cond: bool) -> str:
    return "SI" if cond else "NO"


def _inputs_used(keys: list[str], ctx: Ctx) -> list[dict[str, Any]]:
    mapping = {
        "q1": ("F32", "q1", "Quota Cecchino 1", "cecchino_output_json.signals_matrix.inputs.q1"),
        "qx": ("F33", "qx", "Quota Cecchino X", "cecchino_output_json.signals_matrix.inputs.qx"),
        "q2": ("F34", "q2", "Quota Cecchino 2", "cecchino_output_json.signals_matrix.inputs.q2"),
        "avg_q": ("F35", "avg_q", "Media quote 1/X/2", "cecchino_output_json.signals_matrix.inputs.avg_q"),
        "diff_1_2": ("F36", "diff_1_2", "Differenza F34−F32", "cecchino_output_json.signals_matrix.inputs.diff_1_2"),
        "dominance_pp": (
            "Dominanza",
            "dominance_pp",
            "Dominanza (punti percentuali)",
            "cecchino_output_json.signals_matrix.inputs.dominance_pp",
        ),
        "under_2_5_cecchino_odd": (
            "UNDER2.5",
            "under_2_5_cecchino_odd",
            "Quota Cecchino Under 2.5",
            "cecchino_output_json.signals_matrix.inputs.under_2_5_cecchino_odd",
        ),
        "scala_1x": ("SCALA 1X", "scala_1x", "Scala 1X", "signals_matrix.rows[one_x].signals.scala_1x"),
        "scala_x2": ("SCALA X2", "scala_x2", "Scala X2", "signals_matrix.rows[x_two].signals.scala_x2"),
        "twelve_d": ("D60", "twelve_d", "12 / Excel D", "signals_matrix.rows[twelve].signals.excel_d"),
        "twelve_e": ("E60", "twelve_e", "12 / Excel E", "signals_matrix.rows[twelve].signals.excel_e"),
    }
    out: list[dict[str, Any]] = []
    for k in keys:
        meta = mapping.get(k)
        if not meta:
            continue
        excel_name, internal, label, path = meta
        val = ctx.get(k)
        display = (
            f"{_fmt_it(_num(val))} pp"
            if k == "dominance_pp" and _num(val) is not None
            else (_fmt_it(_num(val)) if _num(val) is not None else (str(val) if val is not None else "—"))
        )
        item: dict[str, Any] = {
            "excel_name": excel_name,
            "key": internal,
            "label": label,
            "value": val,
            "display_value": display,
            "source_path": path,
            "source_type": "persisted_snapshot",
        }
        if k == "avg_q":
            item["derivation"] = "F35 = (F32 + F33 + F34) / 3"
        if k == "diff_1_2":
            item["derivation"] = "F36 = F34 − F32"
        out.append(item)
    return out


def _reason_summary(result: str, logic: Logic) -> tuple[str, list[Leaf], list[Leaf]]:
    """Produce frase naturale + liste pass/fail foglie."""
    leaves: list[Leaf] = []

    def collect(node: Logic | Leaf) -> None:
        if "conditions" in node and isinstance(node.get("conditions"), list):
            for c in node["conditions"]:
                if isinstance(c, dict) and "passed" in c and "operator" in c and "left_label" in c:
                    leaves.append(c)
                elif isinstance(c, dict):
                    collect(c)
        if "branches" in node and isinstance(node.get("branches"), list):
            for b in node["branches"]:
                if isinstance(b, dict):
                    collect(b)
        if "passed" in node and "left_label" in node:
            leaves.append(node)  # type: ignore[arg-type]

    collect(logic)
    # dedupe by condition_key+expression
    seen: set[str] = set()
    uniq: list[Leaf] = []
    for leaf in leaves:
        k = f"{leaf.get('condition_key')}:{leaf.get('expression')}"
        if k in seen:
            continue
        seen.add(k)
        uniq.append(leaf)

    passed = [x for x in uniq if x.get("passed")]
    failed = [x for x in uniq if not x.get("passed")]

    if result == "SI":
        if logic.get("operator") == "OR":
            ok_branches = [
                b for b in (logic.get("branches") or []) if isinstance(b, dict) and b.get("result") == "SI"
            ]
            if ok_branches:
                labels = ", ".join(str(b.get("label") or b.get("group_key") or "ramo") for b in ok_branches)
                summary = f"Il segnale è SI perché il/i ramo/i OR soddisfatto/i: {labels}."
            else:
                summary = "Il segnale è SI perché almeno un ramo del gruppo OR è soddisfatto."
        else:
            summary = "Il segnale è SI perché tutte le condizioni del gruppo AND sono soddisfatte."
    else:
        n_fail = len(failed)
        n_tot = len(uniq) or 1
        summary = f"Il segnale è NO perché {n_fail} condizioni su {n_tot} non sono soddisfatte."
        if failed:
            details = []
            for f in failed:
                details.append(
                    f"{f.get('left_label')} = {f.get('left_display')} non soddisfa "
                    f"{f.get('operator')} {f.get('right_label')} = {f.get('right_display')}"
                )
            summary = summary + " " + " · ".join(details)

    return summary, passed, failed


# ---------------------------------------------------------------------------
# Evaluators (26 cells) — operatori identici a cecchino_signals_matrix.py
# ---------------------------------------------------------------------------


def _eval_scala_1x(ctx: Ctx) -> tuple[str, Logic, list[dict[str, Any]]]:
    q1, qx, q2 = _num(ctx["q1"]), _num(ctx["qx"]), _num(ctx["q2"])
    leaves = [
        _leaf(condition_key="q1_lt_qx", label="F32 < F33", left_label="F32", left_value=q1,
              operator="<", right_label="F33", right_value=qx, passed=_cmp(q1, "<", qx),
              source_path="signals_matrix.inputs.q1"),
        _leaf(condition_key="qx_lt_q2", label="F33 < F34", left_label="F33", left_value=qx,
              operator="<", right_label="F34", right_value=q2, passed=_cmp(qx, "<", q2),
              source_path="signals_matrix.inputs.qx"),
        _leaf(condition_key="q1_lt_q2", label="F32 < F34", left_label="F32", left_value=q1,
              operator="<", right_label="F34", right_value=q2, passed=_cmp(q1, "<", q2),
              source_path="signals_matrix.inputs.q1"),
    ]
    logic = _group_and("scala_1x", "SCALA 1X", leaves)
    return logic["result"], logic, _inputs_used(["q1", "qx", "q2"], ctx)


def _eval_scala_x2(ctx: Ctx) -> tuple[str, Logic, list[dict[str, Any]]]:
    q1, qx, q2 = _num(ctx["q1"]), _num(ctx["qx"]), _num(ctx["q2"])
    leaves = [
        _leaf(condition_key="q1_gt_qx", label="F32 > F33", left_label="F32", left_value=q1,
              operator=">", right_label="F33", right_value=qx, passed=_cmp(q1, ">", qx),
              source_path="signals_matrix.inputs.q1"),
        _leaf(condition_key="qx_gt_q2", label="F33 > F34", left_label="F33", left_value=qx,
              operator=">", right_label="F34", right_value=q2, passed=_cmp(qx, ">", q2),
              source_path="signals_matrix.inputs.qx"),
        _leaf(condition_key="q1_gt_q2", label="F32 > F34", left_label="F32", left_value=q1,
              operator=">", right_label="F34", right_value=q2, passed=_cmp(q1, ">", q2),
              source_path="signals_matrix.inputs.q1"),
    ]
    logic = _group_and("scala_x2", "SCALA X2", leaves)
    return logic["result"], logic, _inputs_used(["q1", "qx", "q2"], ctx)


def _eval_twelve_d(ctx: Ctx) -> tuple[str, Logic, list[dict[str, Any]]]:
    q1, qx, q2 = _num(ctx["q1"]), _num(ctx["qx"]), _num(ctx["q2"])
    d = _num(ctx["diff_1_2"])
    branch_a = _group_and(
        "twelve_d_a",
        "Ramo A (favorito casa)",
        [
            _leaf(condition_key="qx_ge_4_8", label="F33 ≥ 4,80", left_label="F33", left_value=qx,
                  operator=">=", right_label="Soglia", right_value=4.8, passed=_cmp(qx, ">=", 4.8),
                  source_path="signals_matrix.inputs.qx"),
            _leaf(condition_key="q1_lt_2_40", label="F32 < 2,40", left_label="F32", left_value=q1,
                  operator="<", right_label="Soglia", right_value=2.40, passed=_cmp(q1, "<", 2.40),
                  source_path="signals_matrix.inputs.q1"),
            _leaf(condition_key="f36_lt_m1_5", label="F36 < −1,50", left_label="F36", left_value=d,
                  operator="<", right_label="Soglia", right_value=-1.5, passed=_cmp(d, "<", -1.5),
                  source_path="signals_matrix.inputs.diff_1_2"),
        ],
    )
    branch_b = _group_and(
        "twelve_d_b",
        "Ramo B (favorito trasferta)",
        [
            _leaf(condition_key="qx_ge_4_8_b", label="F33 ≥ 4,80", left_label="F33", left_value=qx,
                  operator=">=", right_label="Soglia", right_value=4.8, passed=_cmp(qx, ">=", 4.8),
                  source_path="signals_matrix.inputs.qx"),
            _leaf(condition_key="q2_lt_2_40", label="F34 < 2,40", left_label="F34", left_value=q2,
                  operator="<", right_label="Soglia", right_value=2.40, passed=_cmp(q2, "<", 2.40),
                  source_path="signals_matrix.inputs.q2"),
            _leaf(condition_key="f36_gt_1_5", label="F36 > 1,50", left_label="F36", left_value=d,
                  operator=">", right_label="Soglia", right_value=1.5, passed=_cmp(d, ">", 1.5),
                  source_path="signals_matrix.inputs.diff_1_2"),
        ],
    )
    logic = _group_or("twelve_d", "12 / Excel D", [branch_a, branch_b])
    return logic["result"], logic, _inputs_used(["q1", "qx", "q2", "diff_1_2"], ctx)


def _eval_twelve_e(ctx: Ctx) -> tuple[str, Logic, list[dict[str, Any]]]:
    qx, d, dom = _num(ctx["qx"]), _num(ctx["diff_1_2"]), _num(ctx["dominance_pp"])
    abs_d = abs(d) if d is not None else None
    leaves = [
        _leaf(condition_key="qx_ge_4_8", label="F33 ≥ 4,80", left_label="F33", left_value=qx,
              operator=">=", right_label="Soglia", right_value=4.8, passed=_cmp(qx, ">=", 4.8),
              source_path="signals_matrix.inputs.qx"),
        _leaf(condition_key="dom_present", label="Dominanza presente", left_label="Dominanza",
              left_value=dom, left_display=_fmt_it(dom) if dom is not None else "assente",
              operator="!=", right_label="None", right_value=None, right_display="None",
              passed=dom is not None, source_path="signals_matrix.inputs.dominance_pp"),
        _leaf(condition_key="dom_ge_10", label="Dominanza ≥ 10 pp", left_label="Dominanza",
              left_value=dom, left_display=f"{_fmt_it(dom)} pp" if dom is not None else "—",
              operator=">=", right_label="Soglia", right_value=10, right_display="10,00 pp",
              passed=_cmp(dom, ">=", 10.0), source_path="signals_matrix.inputs.dominance_pp"),
        _leaf(condition_key="abs_f36_ge_1_5", label="|F36| ≥ 1,50", left_label="|F36|",
              left_value=abs_d, operator=">=", right_label="Soglia", right_value=1.5,
              passed=_cmp(abs_d, ">=", 1.5), source_path="signals_matrix.inputs.diff_1_2"),
    ]
    logic = _group_and("twelve_e", "12 / Excel E", leaves)
    return logic["result"], logic, _inputs_used(["qx", "diff_1_2", "dominance_pp"], ctx)


def _eval_under_d(ctx: Ctx) -> tuple[str, Logic, list[dict[str, Any]]]:
    q1, q2, d, u = _num(ctx["q1"]), _num(ctx["q2"]), _num(ctx["diff_1_2"]), _num(ctx["under_2_5_cecchino_odd"])
    leaves = [
        _leaf(condition_key="f36_lt_0_9", label="F36 < 0,90", left_label="F36", left_value=d,
              operator="<", right_label="Soglia", right_value=0.9, passed=_cmp(d, "<", 0.9),
              source_path="signals_matrix.inputs.diff_1_2"),
        _leaf(condition_key="f36_gt_m0_8", label="F36 > −0,80", left_label="F36", left_value=d,
              operator=">", right_label="Soglia", right_value=-0.8, passed=_cmp(d, ">", -0.8),
              source_path="signals_matrix.inputs.diff_1_2"),
        _leaf(condition_key="q1_ge_q2", label="F32 ≥ F34", left_label="F32", left_value=q1,
              operator=">=", right_label="F34", right_value=q2, passed=_cmp(q1, ">=", q2),
              source_path="signals_matrix.inputs.q1"),
        _leaf(condition_key="under_present", label="UNDER2.5 presente", left_label="UNDER2.5",
              left_value=u, left_display=_fmt_it(u) if u is not None else "assente",
              operator="!=", right_label="None", right_value=None, right_display="None",
              passed=u is not None, source_path="signals_matrix.inputs.under_2_5_cecchino_odd"),
        _leaf(condition_key="under_le_2", label="UNDER2.5 ≤ 2", left_label="UNDER2.5", left_value=u,
              operator="<=", right_label="Soglia", right_value=2.0, passed=_cmp(u, "<=", 2.0),
              source_path="signals_matrix.inputs.under_2_5_cecchino_odd"),
    ]
    logic = _group_and("under_d", "UNDER / Excel D", leaves)
    return logic["result"], logic, _inputs_used(["q1", "q2", "diff_1_2", "under_2_5_cecchino_odd"], ctx)


def _eval_under_e(ctx: Ctx) -> tuple[str, Logic, list[dict[str, Any]]]:
    q1, qx, q2, avg = _num(ctx["q1"]), _num(ctx["qx"]), _num(ctx["q2"]), _num(ctx["avg_q"])
    if avg is None or avg <= 0:
        leaves = [
            _leaf(condition_key="avg_positive", label="F35 > 0", left_label="F35", left_value=avg,
                  operator=">", right_label="0", right_value=0, passed=False,
                  source_path="signals_matrix.inputs.avg_q"),
        ]
        logic = _group_and("under_e", "UNDER / Excel E", leaves)
        return "NO", logic, _inputs_used(["q1", "qx", "q2", "avg_q"], ctx)
    r1, rx, r2 = q1 / avg if q1 is not None else None, qx / avg if qx is not None else None, q2 / avg if q2 is not None else None
    leaves = [
        _leaf(condition_key="r1_gt", label="F32/F35 > 0,88", left_label="F32/F35", left_value=r1,
              operator=">", right_label="Soglia", right_value=0.88, passed=_cmp(r1, ">", 0.88),
              source_path="signals_matrix.inputs"),
        _leaf(condition_key="rx_gt", label="F33/F35 > 0,88", left_label="F33/F35", left_value=rx,
              operator=">", right_label="Soglia", right_value=0.88, passed=_cmp(rx, ">", 0.88),
              source_path="signals_matrix.inputs"),
        _leaf(condition_key="r2_gt", label="F34/F35 > 0,88", left_label="F34/F35", left_value=r2,
              operator=">", right_label="Soglia", right_value=0.88, passed=_cmp(r2, ">", 0.88),
              source_path="signals_matrix.inputs"),
        _leaf(condition_key="r1_lt", label="F32/F35 < 1,20", left_label="F32/F35", left_value=r1,
              operator="<", right_label="Soglia", right_value=1.2, passed=_cmp(r1, "<", 1.2),
              source_path="signals_matrix.inputs"),
        _leaf(condition_key="rx_lt", label="F33/F35 < 1,20", left_label="F33/F35", left_value=rx,
              operator="<", right_label="Soglia", right_value=1.2, passed=_cmp(rx, "<", 1.2),
              source_path="signals_matrix.inputs"),
        _leaf(condition_key="r2_lt", label="F34/F35 < 1,20", left_label="F34/F35", left_value=r2,
              operator="<", right_label="Soglia", right_value=1.2, passed=_cmp(r2, "<", 1.2),
              source_path="signals_matrix.inputs"),
    ]
    logic = _group_and("under_e", "UNDER / Excel E", leaves)
    return logic["result"], logic, _inputs_used(["q1", "qx", "q2", "avg_q"], ctx)


def _eval_under_f(ctx: Ctx) -> tuple[str, Logic, list[dict[str, Any]]]:
    q1, qx, q2, d, u = _num(ctx["q1"]), _num(ctx["qx"]), _num(ctx["q2"]), _num(ctx["diff_1_2"]), _num(ctx["under_2_5_cecchino_odd"])
    leaves = [
        _leaf(condition_key="f36_le_1_53", label="F36 ≤ 1,53", left_label="F36", left_value=d,
              operator="<=", right_label="Soglia", right_value=1.53, passed=_cmp(d, "<=", 1.53),
              source_path="signals_matrix.inputs.diff_1_2"),
        _leaf(condition_key="f36_ge_m1_5", label="F36 ≥ −1,50", left_label="F36", left_value=d,
              operator=">=", right_label="Soglia", right_value=-1.5, passed=_cmp(d, ">=", -1.5),
              source_path="signals_matrix.inputs.diff_1_2"),
        _leaf(condition_key="qx_le_3", label="F33 ≤ 3", left_label="F33", left_value=qx,
              operator="<=", right_label="Soglia", right_value=3.0, passed=_cmp(qx, "<=", 3.0),
              source_path="signals_matrix.inputs.qx"),
        _leaf(condition_key="q1_ge_q2", label="F32 ≥ F34", left_label="F32", left_value=q1,
              operator=">=", right_label="F34", right_value=q2, passed=_cmp(q1, ">=", q2),
              source_path="signals_matrix.inputs.q1"),
        _leaf(condition_key="under_present", label="UNDER2.5 presente", left_label="UNDER2.5",
              left_value=u, left_display=_fmt_it(u) if u is not None else "assente",
              operator="!=", right_label="None", right_value=None, right_display="None",
              passed=u is not None, source_path="signals_matrix.inputs.under_2_5_cecchino_odd"),
        _leaf(condition_key="under_le_2", label="UNDER2.5 ≤ 2", left_label="UNDER2.5", left_value=u,
              operator="<=", right_label="Soglia", right_value=2.0, passed=_cmp(u, "<=", 2.0),
              source_path="signals_matrix.inputs.under_2_5_cecchino_odd"),
    ]
    logic = _group_and("under_f", "UNDER / Excel F", leaves)
    return logic["result"], logic, _inputs_used(["q1", "qx", "q2", "diff_1_2", "under_2_5_cecchino_odd"], ctx)


def _eval_under_g(ctx: Ctx) -> tuple[str, Logic, list[dict[str, Any]]]:
    q1, qx, q2, d, u = _num(ctx["q1"]), _num(ctx["qx"]), _num(ctx["q2"]), _num(ctx["diff_1_2"]), _num(ctx["under_2_5_cecchino_odd"])
    leaves = [
        _leaf(condition_key="f36_le_1_33", label="F36 ≤ 1,33", left_label="F36", left_value=d,
              operator="<=", right_label="Soglia", right_value=1.33, passed=_cmp(d, "<=", 1.33),
              source_path="signals_matrix.inputs.diff_1_2"),
        _leaf(condition_key="f36_ge_m1_23", label="F36 ≥ −1,23", left_label="F36", left_value=d,
              operator=">=", right_label="Soglia", right_value=-1.23, passed=_cmp(d, ">=", -1.23),
              source_path="signals_matrix.inputs.diff_1_2"),
        _leaf(condition_key="qx_lt_4", label="F33 < 4", left_label="F33", left_value=qx,
              operator="<", right_label="Soglia", right_value=4.0, passed=_cmp(qx, "<", 4.0),
              source_path="signals_matrix.inputs.qx"),
        _leaf(condition_key="q1_ge_q2", label="F32 ≥ F34", left_label="F32", left_value=q1,
              operator=">=", right_label="F34", right_value=q2, passed=_cmp(q1, ">=", q2),
              source_path="signals_matrix.inputs.q1"),
        _leaf(condition_key="under_present", label="UNDER2.5 presente", left_label="UNDER2.5",
              left_value=u, left_display=_fmt_it(u) if u is not None else "assente",
              operator="!=", right_label="None", right_value=None, right_display="None",
              passed=u is not None, source_path="signals_matrix.inputs.under_2_5_cecchino_odd"),
        _leaf(condition_key="under_le_2", label="UNDER2.5 ≤ 2", left_label="UNDER2.5", left_value=u,
              operator="<=", right_label="Soglia", right_value=2.0, passed=_cmp(u, "<=", 2.0),
              source_path="signals_matrix.inputs.under_2_5_cecchino_odd"),
    ]
    logic = _group_and("under_g", "UNDER / Excel G", leaves)
    return logic["result"], logic, _inputs_used(["q1", "qx", "q2", "diff_1_2", "under_2_5_cecchino_odd"], ctx)


def _eval_draw_d(ctx: Ctx) -> tuple[str, Logic, list[dict[str, Any]]]:
    from decimal import Decimal

    c = _draw_canonical_ctx(ctx)
    f32, f34, f36 = c["f32"], c["f34"], c["f36"]
    leaves = [
        _draw_leaf(
            condition_key="f36_lt_0_80",
            label="F36 < 0,80",
            left_label="F36",
            raw_value=c["raw_diff_1_2"],
            canonical_value=f36,
            operator="<",
            right_label="Soglia",
            right_value=Decimal("0.80"),
            passed=_cmp_dec(f36, "<", Decimal("0.80")),
            source_path="signals_matrix.inputs.diff_1_2",
        ),
        _draw_leaf(
            condition_key="f36_gt_m0_80",
            label="F36 > −0,80",
            left_label="F36",
            raw_value=c["raw_diff_1_2"],
            canonical_value=f36,
            operator=">",
            right_label="Soglia",
            right_value=Decimal("-0.80"),
            passed=_cmp_dec(f36, ">", Decimal("-0.80")),
            source_path="signals_matrix.inputs.diff_1_2",
        ),
        _draw_leaf(
            condition_key="q1_ge_q2",
            label="F32 ≥ F34",
            left_label="F32",
            raw_value=c["raw_q1"],
            canonical_value=f32,
            operator=">=",
            right_label="F34",
            right_value=f34 if f34 is not None else Decimal("0"),
            passed=_cmp_dec(f32, ">=", f34),
            source_path="signals_matrix.inputs.q1",
        ),
    ]
    # Fix right_value display when f34 is None
    if f34 is None:
        leaves[-1]["right_value"] = None
        leaves[-1]["right_display"] = "—"
        leaves[-1]["expression"] = f"{leaves[-1]['left_display']} >= —"
        leaves[-1]["comparison"] = f"{leaves[-1].get('canonical_value') or '—'} >= —"
    logic = _group_and("draw_d", "SEGNO X / Excel D", leaves)
    return logic["result"], logic, _inputs_used(["q1", "q2", "diff_1_2"], ctx)


def _eval_draw_e(ctx: Ctx) -> tuple[str, Logic, list[dict[str, Any]]]:
    from decimal import Decimal

    c = _draw_canonical_ctx(ctx)
    f32, f33, f34, f36 = c["f32"], c["f33"], c["f34"], c["f36"]
    leaves = [
        _draw_leaf(
            condition_key="qx_lt_3_3",
            label="F33 < 3,30",
            left_label="F33",
            raw_value=c["raw_qx"],
            canonical_value=f33,
            operator="<",
            right_label="Soglia",
            right_value=Decimal("3.30"),
            passed=_cmp_dec(f33, "<", Decimal("3.30")),
            source_path="signals_matrix.inputs.qx",
        ),
        _draw_leaf(
            condition_key="f36_le_1_47",
            label="F36 ≤ 1,47",
            left_label="F36",
            raw_value=c["raw_diff_1_2"],
            canonical_value=f36,
            operator="<=",
            right_label="Soglia",
            right_value=Decimal("1.47"),
            passed=_cmp_dec(f36, "<=", Decimal("1.47")),
            source_path="signals_matrix.inputs.diff_1_2",
        ),
        _draw_leaf(
            condition_key="f36_ge_m1_4",
            label="F36 ≥ −1,40",
            left_label="F36",
            raw_value=c["raw_diff_1_2"],
            canonical_value=f36,
            operator=">=",
            right_label="Soglia",
            right_value=Decimal("-1.40"),
            passed=_cmp_dec(f36, ">=", Decimal("-1.40")),
            source_path="signals_matrix.inputs.diff_1_2",
        ),
        _draw_leaf(
            condition_key="q1_ge_q2",
            label="F32 ≥ F34",
            left_label="F32",
            raw_value=c["raw_q1"],
            canonical_value=f32,
            operator=">=",
            right_label="F34",
            right_value=f34 if f34 is not None else Decimal("0"),
            passed=_cmp_dec(f32, ">=", f34),
            source_path="signals_matrix.inputs.q1",
        ),
    ]
    if f34 is None:
        leaves[-1]["right_value"] = None
        leaves[-1]["right_display"] = "—"
    logic = _group_and("draw_e", "SEGNO X / Excel E", leaves)
    return logic["result"], logic, _inputs_used(["q1", "qx", "q2", "diff_1_2"], ctx)


def _eval_draw_f(ctx: Ctx) -> tuple[str, Logic, list[dict[str, Any]]]:
    from decimal import Decimal

    c = _draw_canonical_ctx(ctx)
    f32, f33, f34, f36 = c["f32"], c["f33"], c["f34"], c["f36"]
    leaves = [
        _draw_leaf(
            condition_key="qx_le_2_90",
            label="F33 ≤ 2,90",
            left_label="F33",
            raw_value=c["raw_qx"],
            canonical_value=f33,
            operator="<=",
            right_label="Soglia",
            right_value=Decimal("2.90"),
            passed=_cmp_dec(f33, "<=", Decimal("2.90")),
            source_path="signals_matrix.inputs.qx",
        ),
        _draw_leaf(
            condition_key="f36_le_1_70",
            label="F36 ≤ 1,70",
            left_label="F36",
            raw_value=c["raw_diff_1_2"],
            canonical_value=f36,
            operator="<=",
            right_label="Soglia",
            right_value=Decimal("1.70"),
            passed=_cmp_dec(f36, "<=", Decimal("1.70")),
            source_path="signals_matrix.inputs.diff_1_2",
        ),
        _draw_leaf(
            condition_key="f36_ge_m1_70",
            label="F36 ≥ −1,70",
            left_label="F36",
            raw_value=c["raw_diff_1_2"],
            canonical_value=f36,
            operator=">=",
            right_label="Soglia",
            right_value=Decimal("-1.70"),
            passed=_cmp_dec(f36, ">=", Decimal("-1.70")),
            source_path="signals_matrix.inputs.diff_1_2",
        ),
        _draw_leaf(
            condition_key="q1_ge_q2",
            label="F32 ≥ F34",
            left_label="F32",
            raw_value=c["raw_q1"],
            canonical_value=f32,
            operator=">=",
            right_label="F34",
            right_value=f34 if f34 is not None else Decimal("0"),
            passed=_cmp_dec(f32, ">=", f34),
            source_path="signals_matrix.inputs.q1",
        ),
    ]
    if f34 is None:
        leaves[-1]["right_value"] = None
        leaves[-1]["right_display"] = "—"
    logic = _group_and("draw_f", "SEGNO X / Excel F", leaves)
    return logic["result"], logic, _inputs_used(["q1", "qx", "q2", "diff_1_2"], ctx)


def _eval_draw_g(ctx: Ctx) -> tuple[str, Logic, list[dict[str, Any]]]:
    from decimal import Decimal

    c = _draw_canonical_ctx(ctx)
    f32, f33, f34, f36 = c["f32"], c["f33"], c["f34"], c["f36"]
    leaves = [
        _draw_leaf(
            condition_key="qx_le_3_50",
            label="F33 ≤ 3,50",
            left_label="F33",
            raw_value=c["raw_qx"],
            canonical_value=f33,
            operator="<=",
            right_label="Soglia",
            right_value=Decimal("3.50"),
            passed=_cmp_dec(f33, "<=", Decimal("3.50")),
            source_path="signals_matrix.inputs.qx",
        ),
        _draw_leaf(
            condition_key="f36_le_1_20",
            label="F36 ≤ 1,20",
            left_label="F36",
            raw_value=c["raw_diff_1_2"],
            canonical_value=f36,
            operator="<=",
            right_label="Soglia",
            right_value=Decimal("1.20"),
            passed=_cmp_dec(f36, "<=", Decimal("1.20")),
            source_path="signals_matrix.inputs.diff_1_2",
        ),
        _draw_leaf(
            condition_key="f36_ge_m1_20",
            label="F36 ≥ −1,20",
            left_label="F36",
            raw_value=c["raw_diff_1_2"],
            canonical_value=f36,
            operator=">=",
            right_label="Soglia",
            right_value=Decimal("-1.20"),
            passed=_cmp_dec(f36, ">=", Decimal("-1.20")),
            source_path="signals_matrix.inputs.diff_1_2",
        ),
        _draw_leaf(
            condition_key="q1_ge_q2",
            label="F32 ≥ F34",
            left_label="F32",
            raw_value=c["raw_q1"],
            canonical_value=f32,
            operator=">=",
            right_label="F34",
            right_value=f34 if f34 is not None else Decimal("0"),
            passed=_cmp_dec(f32, ">=", f34),
            source_path="signals_matrix.inputs.q1",
        ),
    ]
    if f34 is None:
        leaves[-1]["right_value"] = None
        leaves[-1]["right_display"] = "—"
    logic = _group_and("draw_g", "SEGNO X / Excel G", leaves)
    return logic["result"], logic, _inputs_used(["q1", "qx", "q2", "diff_1_2"], ctx)


def _eval_over_d(ctx: Ctx) -> tuple[str, Logic, list[dict[str, Any]]]:
    qx, d = _num(ctx["qx"]), _num(ctx["diff_1_2"])
    branch_spread = _group_or(
        "over_d_spread",
        "Spread F36",
        [
            _group_and("over_d_hi", "F36 > 1,70", [
                _leaf(condition_key="f36_gt_1_7", label="F36 > 1,70", left_label="F36", left_value=d,
                      operator=">", right_label="Soglia", right_value=1.7, passed=_cmp(d, ">", 1.7),
                      source_path="signals_matrix.inputs.diff_1_2"),
            ]),
            _group_and("over_d_lo", "F36 < −1,50", [
                _leaf(condition_key="f36_lt_m1_5", label="F36 < −1,50", left_label="F36", left_value=d,
                      operator="<", right_label="Soglia", right_value=-1.5, passed=_cmp(d, "<", -1.5),
                      source_path="signals_matrix.inputs.diff_1_2"),
            ]),
        ],
    )
    # Combine: (spread) AND qx >= 6 — flatten as AND of OR result leaf + qx
    spread_ok = branch_spread["result"] == "SI"
    qx_leaf = _leaf(condition_key="qx_ge_6", label="F33 ≥ 6", left_label="F33", left_value=qx,
                    operator=">=", right_label="Soglia", right_value=6.0, passed=_cmp(qx, ">=", 6.0),
                    source_path="signals_matrix.inputs.qx")
    logic = {
        "operator": "AND",
        "group_key": "over_d",
        "label": "OVER / Excel D",
        "branches": [branch_spread],
        "conditions": [
            _leaf(condition_key="spread_ok", label="(F36 > 1,70 OR F36 < −1,50)", left_label="Spread",
                  left_value=spread_ok, left_display="SI" if spread_ok else "NO",
                  operator="==", right_label="SI", right_value="SI", right_display="SI",
                  passed=spread_ok, source_path="signals_matrix.inputs.diff_1_2"),
            qx_leaf,
        ],
        "result": _si_no(spread_ok and bool(qx_leaf["passed"])),
    }
    return logic["result"], logic, _inputs_used(["qx", "diff_1_2"], ctx)


def _eval_over_e(ctx: Ctx) -> tuple[str, Logic, list[dict[str, Any]]]:
    # Dipende da twelve_d / twelve_e già nel ctx (precomputati)
    td, te = ctx.get("twelve_d"), ctx.get("twelve_e")
    leaves = [
        _leaf(condition_key="twelve_d_si", label="12 / Excel D = SI", left_label="D60",
              left_value=td, left_display=str(td or "—"), operator="==", right_label="SI",
              right_value="SI", right_display="SI", passed=td == "SI",
              source_path="signals_matrix.rows[twelve].signals.excel_d"),
        _leaf(condition_key="twelve_e_si", label="12 / Excel E = SI", left_label="E60",
              left_value=te, left_display=str(te or "—"), operator="==", right_label="SI",
              right_value="SI", right_display="SI", passed=te == "SI",
              source_path="signals_matrix.rows[twelve].signals.excel_e"),
    ]
    # OR of the two
    branch_d = _group_and("dep_d", "Dipendenza D60", [leaves[0]])
    branch_e = _group_and("dep_e", "Dipendenza E60", [leaves[1]])
    logic = _group_or("over_e", "OVER / Excel E (dipende da 12)", [branch_d, branch_e])
    return logic["result"], logic, _inputs_used(["twelve_d", "twelve_e", "q1", "qx", "q2", "diff_1_2", "dominance_pp"], ctx)


def _eval_over_f(ctx: Ctx) -> tuple[str, Logic, list[dict[str, Any]]]:
    qx, d = _num(ctx["qx"]), _num(ctx["diff_1_2"])
    b1 = _group_and("over_f_a", "Ramo A", [
        _leaf(condition_key="qx_ge_5", label="F33 ≥ 5", left_label="F33", left_value=qx,
              operator=">=", right_label="Soglia", right_value=5.0, passed=_cmp(qx, ">=", 5.0),
              source_path="signals_matrix.inputs.qx"),
        _leaf(condition_key="f36_gt_2", label="F36 > 2", left_label="F36", left_value=d,
              operator=">", right_label="Soglia", right_value=2.0, passed=_cmp(d, ">", 2.0),
              source_path="signals_matrix.inputs.diff_1_2"),
    ])
    b2 = _group_and("over_f_b", "Ramo B", [
        _leaf(condition_key="qx_ge_5_b", label="F33 ≥ 5", left_label="F33", left_value=qx,
              operator=">=", right_label="Soglia", right_value=5.0, passed=_cmp(qx, ">=", 5.0),
              source_path="signals_matrix.inputs.qx"),
        _leaf(condition_key="f36_lt_m2_1", label="F36 < −2,10", left_label="F36", left_value=d,
              operator="<", right_label="Soglia", right_value=-2.1, passed=_cmp(d, "<", -2.1),
              source_path="signals_matrix.inputs.diff_1_2"),
    ])
    logic = _group_or("over_f", "OVER / Excel F", [b1, b2])
    return logic["result"], logic, _inputs_used(["qx", "diff_1_2"], ctx)


def _eval_over_g(ctx: Ctx) -> tuple[str, Logic, list[dict[str, Any]]]:
    qx, d = _num(ctx["qx"]), _num(ctx["diff_1_2"])
    b1 = _group_and("over_g_a", "Ramo A", [
        _leaf(condition_key="qx_ge_4", label="F33 ≥ 4", left_label="F33", left_value=qx,
              operator=">=", right_label="Soglia", right_value=4.0, passed=_cmp(qx, ">=", 4.0),
              source_path="signals_matrix.inputs.qx"),
        _leaf(condition_key="f36_gt_2_55", label="F36 > 2,55", left_label="F36", left_value=d,
              operator=">", right_label="Soglia", right_value=2.55, passed=_cmp(d, ">", 2.55),
              source_path="signals_matrix.inputs.diff_1_2"),
    ])
    b2 = _group_and("over_g_b", "Ramo B", [
        _leaf(condition_key="qx_ge_4_b", label="F33 ≥ 4", left_label="F33", left_value=qx,
              operator=">=", right_label="Soglia", right_value=4.0, passed=_cmp(qx, ">=", 4.0),
              source_path="signals_matrix.inputs.qx"),
        _leaf(condition_key="f36_lt_m2_4", label="F36 < −2,40", left_label="F36", left_value=d,
              operator="<", right_label="Soglia", right_value=-2.4, passed=_cmp(d, "<", -2.4),
              source_path="signals_matrix.inputs.diff_1_2"),
    ])
    logic = _group_or("over_g", "OVER / Excel G", [b1, b2])
    return logic["result"], logic, _inputs_used(["qx", "diff_1_2"], ctx)


def _eval_one_d(ctx: Ctx) -> tuple[str, Logic, list[dict[str, Any]]]:
    d, dom = _num(ctx["diff_1_2"]), _num(ctx["dominance_pp"])
    s1x = ctx.get("scala_1x")
    leaves = [
        _leaf(condition_key="scala_1x_si", label="Scala 1X = SI", left_label="SCALA 1X",
              left_value=s1x, left_display=str(s1x or "—"), operator="==", right_label="SI",
              right_value="SI", right_display="SI", passed=s1x == "SI",
              source_path="signals_matrix.rows[one_x].signals.scala_1x"),
        _leaf(condition_key="f36_gt_2", label="F36 > 2", left_label="F36", left_value=d,
              operator=">", right_label="Soglia", right_value=2.0, passed=_cmp(d, ">", 2.0),
              source_path="signals_matrix.inputs.diff_1_2"),
        _leaf(condition_key="dom_present", label="Dominanza presente", left_label="Dominanza",
              left_value=dom, left_display=_fmt_it(dom) if dom is not None else "assente",
              operator="!=", right_label="None", right_value=None, right_display="None",
              passed=dom is not None, source_path="signals_matrix.inputs.dominance_pp"),
        _leaf(condition_key="dom_gt_10", label="Dominanza > 10 pp", left_label="Dominanza",
              left_value=dom, left_display=f"{_fmt_it(dom)} pp" if dom is not None else "—",
              operator=">", right_label="Soglia", right_value=10, right_display="10,00 pp",
              passed=_cmp(dom, ">", 10.0), source_path="signals_matrix.inputs.dominance_pp"),
    ]
    logic = _group_and("one_d", "Segnale 1 / Excel D", leaves)
    return logic["result"], logic, _inputs_used(["scala_1x", "diff_1_2", "dominance_pp", "q1", "qx", "q2"], ctx)


def _eval_two_d(ctx: Ctx) -> tuple[str, Logic, list[dict[str, Any]]]:
    d, dom = _num(ctx["diff_1_2"]), _num(ctx["dominance_pp"])
    sx2 = ctx.get("scala_x2")
    leaves = [
        _leaf(condition_key="scala_x2_si", label="Scala X2 = SI", left_label="SCALA X2",
              left_value=sx2, left_display=str(sx2 or "—"), operator="==", right_label="SI",
              right_value="SI", right_display="SI", passed=sx2 == "SI",
              source_path="signals_matrix.rows[x_two].signals.scala_x2"),
        _leaf(condition_key="f36_lt_m2_3", label="F36 < −2,30", left_label="F36", left_value=d,
              operator="<", right_label="Soglia", right_value=-2.3, passed=_cmp(d, "<", -2.3),
              source_path="signals_matrix.inputs.diff_1_2"),
        _leaf(condition_key="dom_present", label="Dominanza presente", left_label="Dominanza",
              left_value=dom, left_display=_fmt_it(dom) if dom is not None else "assente",
              operator="!=", right_label="None", right_value=None, right_display="None",
              passed=dom is not None, source_path="signals_matrix.inputs.dominance_pp"),
        _leaf(condition_key="dom_gt_10", label="Dominanza > 10 pp", left_label="Dominanza",
              left_value=dom, left_display=f"{_fmt_it(dom)} pp" if dom is not None else "—",
              operator=">", right_label="Soglia", right_value=10, right_display="10,00 pp",
              passed=_cmp(dom, ">", 10.0), source_path="signals_matrix.inputs.dominance_pp"),
    ]
    logic = _group_and("two_d", "Segnale 2 / Excel D", leaves)
    return logic["result"], logic, _inputs_used(["scala_x2", "diff_1_2", "dominance_pp", "q1", "qx", "q2"], ctx)


def _eval_one_x_d(ctx: Ctx) -> tuple[str, Logic, list[dict[str, Any]]]:
    q1, qx, avg = _num(ctx["q1"]), _num(ctx["qx"]), _num(ctx["avg_q"])
    leaves = [
        _leaf(condition_key="q1_lt_2_8", label="F32 < 2,80", left_label="F32", left_value=q1,
              operator="<", right_label="Soglia", right_value=2.8, passed=_cmp(q1, "<", 2.8),
              source_path="signals_matrix.inputs.q1"),
        _leaf(condition_key="qx_le_4", label="F33 ≤ 4", left_label="F33", left_value=qx,
              operator="<=", right_label="Soglia", right_value=4.0, passed=_cmp(qx, "<=", 4.0),
              source_path="signals_matrix.inputs.qx"),
        _leaf(condition_key="avg_gt_4", label="F35 > 4", left_label="F35", left_value=avg,
              operator=">", right_label="Soglia", right_value=4.0, passed=_cmp(avg, ">", 4.0),
              source_path="signals_matrix.inputs.avg_q"),
    ]
    logic = _group_and("one_x_d", "1X / Excel D", leaves)
    return logic["result"], logic, _inputs_used(["q1", "qx", "avg_q"], ctx)


def _eval_one_x_e(ctx: Ctx) -> tuple[str, Logic, list[dict[str, Any]]]:
    q1, qx, q2 = _num(ctx["q1"]), _num(ctx["qx"]), _num(ctx["q2"])
    leaves = [
        _leaf(condition_key="gap1", label="F32+0,40 < F33", left_label="F32+0,40",
              left_value=(q1 + 0.4) if q1 is not None else None,
              operator="<", right_label="F33", right_value=qx,
              passed=q1 is not None and qx is not None and (q1 + 0.4) < qx,
              source_path="signals_matrix.inputs"),
        _leaf(condition_key="gap2", label="F33+0,50 < F34", left_label="F33+0,50",
              left_value=(qx + 0.5) if qx is not None else None,
              operator="<", right_label="F34", right_value=q2,
              passed=qx is not None and q2 is not None and (qx + 0.5) < q2,
              source_path="signals_matrix.inputs"),
        _leaf(condition_key="gap3", label="F32+0,60 < F34", left_label="F32+0,60",
              left_value=(q1 + 0.6) if q1 is not None else None,
              operator="<", right_label="F34", right_value=q2,
              passed=q1 is not None and q2 is not None and (q1 + 0.6) < q2,
              source_path="signals_matrix.inputs"),
    ]
    logic = _group_and("one_x_e", "1X / Excel E", leaves)
    return logic["result"], logic, _inputs_used(["q1", "qx", "q2"], ctx)


def _eval_one_x_f(ctx: Ctx) -> tuple[str, Logic, list[dict[str, Any]]]:
    q1, qx, q2, d = _num(ctx["q1"]), _num(ctx["qx"]), _num(ctx["q2"]), _num(ctx["diff_1_2"])
    leaves = [
        _leaf(condition_key="q1_le_1_8", label="F32 ≤ 1,80", left_label="F32", left_value=q1,
              operator="<=", right_label="Soglia", right_value=1.8, passed=_cmp(q1, "<=", 1.8),
              source_path="signals_matrix.inputs.q1"),
        _leaf(condition_key="f36_ge_2_5", label="F36 ≥ 2,50", left_label="F36", left_value=d,
              operator=">=", right_label="Soglia", right_value=2.5, passed=_cmp(d, ">=", 2.5),
              source_path="signals_matrix.inputs.diff_1_2"),
        _leaf(condition_key="q2_gt_qx", label="F34 > F33", left_label="F34", left_value=q2,
              operator=">", right_label="F33", right_value=qx, passed=_cmp(q2, ">", qx),
              source_path="signals_matrix.inputs.q2"),
    ]
    logic = _group_and("one_x_f", "1X / Excel F", leaves)
    return logic["result"], logic, _inputs_used(["q1", "qx", "q2", "diff_1_2"], ctx)


def _eval_one_x_g(ctx: Ctx) -> tuple[str, Logic, list[dict[str, Any]]]:
    q1, q2 = _num(ctx["q1"]), _num(ctx["q2"])
    leaves = [
        _leaf(condition_key="q1_le_2", label="F32 ≤ 2", left_label="F32", left_value=q1,
              operator="<=", right_label="Soglia", right_value=2.0, passed=_cmp(q1, "<=", 2.0),
              source_path="signals_matrix.inputs.q1"),
        _leaf(condition_key="q2_ge_4", label="F34 ≥ 4", left_label="F34", left_value=q2,
              operator=">=", right_label="Soglia", right_value=4.0, passed=_cmp(q2, ">=", 4.0),
              source_path="signals_matrix.inputs.q2"),
    ]
    logic = _group_and("one_x_g", "1X / Excel G", leaves)
    return logic["result"], logic, _inputs_used(["q1", "q2"], ctx)


def _eval_x_two_d(ctx: Ctx) -> tuple[str, Logic, list[dict[str, Any]]]:
    q1, qx, q2 = _num(ctx["q1"]), _num(ctx["qx"]), _num(ctx["q2"])
    leaves = [
        _leaf(condition_key="q2_le_1_8", label="F34 ≤ 1,80", left_label="F34", left_value=q2,
              operator="<=", right_label="Soglia", right_value=1.8, passed=_cmp(q2, "<=", 1.8),
              source_path="signals_matrix.inputs.q2"),
        _leaf(condition_key="q1_ge_3_5", label="F32 ≥ 3,50", left_label="F32", left_value=q1,
              operator=">=", right_label="Soglia", right_value=3.5, passed=_cmp(q1, ">=", 3.5),
              source_path="signals_matrix.inputs.q1"),
        _leaf(condition_key="q2_lt_qx", label="F34 < F33", left_label="F34", left_value=q2,
              operator="<", right_label="F33", right_value=qx, passed=_cmp(q2, "<", qx),
              source_path="signals_matrix.inputs.q2"),
    ]
    logic = _group_and("x_two_d", "X2 / Excel D", leaves)
    return logic["result"], logic, _inputs_used(["q1", "qx", "q2"], ctx)


def _eval_x_two_e(ctx: Ctx) -> tuple[str, Logic, list[dict[str, Any]]]:
    q1, qx, q2 = _num(ctx["q1"]), _num(ctx["qx"]), _num(ctx["q2"])
    leaves = [
        _leaf(condition_key="q2_plus_3_lt_q1", label="F34+3 < F32", left_label="F34+3",
              left_value=(q2 + 3) if q2 is not None else None, operator="<", right_label="F32",
              right_value=q1, passed=q2 is not None and q1 is not None and (q2 + 3) < q1,
              source_path="signals_matrix.inputs"),
        _leaf(condition_key="q2_lt_qx", label="F34 < F33", left_label="F34", left_value=q2,
              operator="<", right_label="F33", right_value=qx, passed=_cmp(q2, "<", qx),
              source_path="signals_matrix.inputs.q2"),
        _leaf(condition_key="qx_lt_q1", label="F33 < F32", left_label="F33", left_value=qx,
              operator="<", right_label="F32", right_value=q1, passed=_cmp(qx, "<", q1),
              source_path="signals_matrix.inputs.qx"),
        _leaf(condition_key="qx_lt_4", label="F33 < 4", left_label="F33", left_value=qx,
              operator="<", right_label="Soglia", right_value=4.0, passed=_cmp(qx, "<", 4.0),
              source_path="signals_matrix.inputs.qx"),
    ]
    logic = _group_and("x_two_e", "X2 / Excel E", leaves)
    return logic["result"], logic, _inputs_used(["q1", "qx", "q2"], ctx)


def _eval_x_two_f(ctx: Ctx) -> tuple[str, Logic, list[dict[str, Any]]]:
    q1, q2 = _num(ctx["q1"]), _num(ctx["q2"])
    leaves = [
        _leaf(condition_key="q2_le_2", label="F34 ≤ 2", left_label="F34", left_value=q2,
              operator="<=", right_label="Soglia", right_value=2.0, passed=_cmp(q2, "<=", 2.0),
              source_path="signals_matrix.inputs.q2"),
        _leaf(condition_key="q1_ge_4", label="F32 ≥ 4", left_label="F32", left_value=q1,
              operator=">=", right_label="Soglia", right_value=4.0, passed=_cmp(q1, ">=", 4.0),
              source_path="signals_matrix.inputs.q1"),
    ]
    logic = _group_and("x_two_f", "X2 / Excel F", leaves)
    return logic["result"], logic, _inputs_used(["q1", "q2"], ctx)


def _eval_x_two_g(ctx: Ctx) -> tuple[str, Logic, list[dict[str, Any]]]:
    q1, qx, q2 = _num(ctx["q1"]), _num(ctx["qx"]), _num(ctx["q2"])
    leaves = [
        _leaf(condition_key="gap1", label="F32+0,50 > F33", left_label="F32+0,50",
              left_value=(q1 + 0.5) if q1 is not None else None, operator=">", right_label="F33",
              right_value=qx, passed=q1 is not None and qx is not None and (q1 + 0.5) > qx,
              source_path="signals_matrix.inputs"),
        _leaf(condition_key="gap2", label="F33+0,60 > F34", left_label="F33+0,60",
              left_value=(qx + 0.6) if qx is not None else None, operator=">", right_label="F34",
              right_value=q2, passed=qx is not None and q2 is not None and (qx + 0.6) > q2,
              source_path="signals_matrix.inputs"),
        _leaf(condition_key="gap3", label="F32+0,70 > F34", left_label="F32+0,70",
              left_value=(q1 + 0.7) if q1 is not None else None, operator=">", right_label="F34",
              right_value=q2, passed=q1 is not None and q2 is not None and (q1 + 0.7) > q2,
              source_path="signals_matrix.inputs"),
    ]
    logic = _group_and("x_two_g", "X2 / Excel G", leaves)
    return logic["result"], logic, _inputs_used(["q1", "qx", "q2"], ctx)


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

COLUMN_LABELS = {
    "excel_d": "Excel D",
    "excel_e": "Excel E",
    "excel_f": "Excel F",
    "excel_g": "Excel G",
    "scala_1x": "SCALA",
    "scala_x2": "SCALA",
}

ROW_LABELS = {
    "under_under_pt": "UNDER / UNDER PT",
    "draw": "SEGNO X",
    "over_over_pt": "OVER / OVER PT",
    "one": "1",
    "one_x": "1X",
    "two": "2",
    "x_two": "X2",
    "twelve": "12",
}


def _rule(
    row_key: str,
    column_key: str,
    source_cell: str,
    excel_formula: str,
    formula_symbolic: str,
    description: str,
    purpose: str,
    target_market: str,
    evaluate: EvalFn,
    operator: str = "AND",
) -> dict[str, Any]:
    return {
        "row_key": row_key,
        "row_label": ROW_LABELS[row_key],
        "column_key": column_key,
        "column_label": COLUMN_LABELS[column_key],
        "source_cell": source_cell,
        "excel_formula": excel_formula,
        "formula_symbolic": formula_symbolic,
        "description": description,
        "purpose": purpose,
        "target_market": target_market,
        "operator": operator,
        "evaluate": evaluate,
        "cell_key": f"{row_key}:{column_key}",
    }


SIGNAL_RULE_REGISTRY: list[dict[str, Any]] = [
    _rule("under_under_pt", "excel_d", "D39",
          '=IF(AND(F36<0.9,F36>-0.8,F32>=F34,UNDER2.5<=2),"SI","NO")',
          "F36 < 0,90 AND F36 > −0,80 AND F32 ≥ F34 AND UNDER2.5 ≤ 2",
          "Segnale Under quando le quote 1/2 sono equilibrate e Under 2.5 Cecchino è basso.",
          "Individuare scenari Under 2.5 con equilibrio 1–2 e quota Under conveniente.",
          "Under 2.5 FT", _eval_under_d),
    _rule("under_under_pt", "excel_e", "E39",
          '=IFERROR(IF(AND(F32/F35>0.88,F33/F35>0.88,F34/F35>0.88,F32/F35<1.2,F33/F35<1.2,F34/F35<1.2),"SI","NO"),"NO")',
          "F32/F35, F33/F35, F34/F35 tutti in (0,88 ; 1,20)",
          "Segnale Under su partita molto equilibrata sui tre esiti rispetto alla media.",
          "Catturare equilibrio 1X2 vicino a F35.",
          "Under 2.5 FT", _eval_under_e),
    _rule("under_under_pt", "excel_f", "F39",
          '=IF(AND(F36<=1.53,F36>=-1.5,F33<=3,F32>=F34,UNDER2.5<=2),"SI","NO")',
          "F36 ≤ 1,53 AND F36 ≥ −1,50 AND F33 ≤ 3 AND F32 ≥ F34 AND UNDER2.5 ≤ 2",
          "Under con range F36 più ampio, X non alta e Under Cecchino ≤ 2.",
          "Variante Under più permissiva su F36.",
          "Under 2.5 FT", _eval_under_f),
    _rule("under_under_pt", "excel_g", "G39",
          '=IF(AND(F36<=1.33,F36>=-1.23,F33<4,F32>=F34,UNDER2.5<=2),"SI","NO")',
          "F36 ≤ 1,33 AND F36 ≥ −1,23 AND F33 < 4 AND F32 ≥ F34 AND UNDER2.5 ≤ 2",
          "Under con range F36 stretto e X sotto 4.",
          "Variante Under più selettiva.",
          "Under 2.5 FT", _eval_under_g),
    _rule("draw", "excel_d", "D42",
          '=IF(AND(F36<0.80,F36>-0.80,F32>=F34),"SI","NO")',
          "F36 < 0,80 AND F36 > −0,80 AND F32 ≥ F34",
          "Pareggio quando F36 è entro ±0,80 (stretti) e quota 1 ≥ quota 2.",
          "Intercettare equilibri da pareggio (formula V2).",
          "Segno X FT", _eval_draw_d),
    _rule("draw", "excel_e", "E42",
          '=IF(AND(F33<3.3,F36<=1.47,F36>=-1.4,F32>=F34),"SI","NO")',
          "F33 < 3,30 AND F36 ≤ 1,47 AND F36 ≥ −1,40 AND F32 ≥ F34",
          "Pareggio con X non cara e F36 in range.",
          "Variante X con tetto su F33 (invariata rispetto a V1).",
          "Segno X FT", _eval_draw_e),
    _rule("draw", "excel_f", "F42",
          '=IF(AND(F33<=2.90,F36<=1.70,F36>=-1.70,F32>=F34),"SI","NO")',
          "F33 ≤ 2,90 AND F36 ≤ 1,70 AND F36 ≥ −1,70 AND F32 ≥ F34",
          "Pareggio con X ≤ 2,90 e F36 entro ±1,70 inclusivi.",
          "Segnale X V2 su quota X e banda F36.",
          "Segno X FT", _eval_draw_f),
    _rule("draw", "excel_g", "G42",
          '=IF(AND(F33<=3.50,F36<=1.20,F36>=-1.20,F32>=F34),"SI","NO")',
          "F33 ≤ 3,50 AND F36 ≤ 1,20 AND F36 ≥ −1,20 AND F32 ≥ F34",
          "Pareggio con X ≤ 3,50 e F36 entro ±1,20 inclusivi.",
          "Variante X V2 intermedia.",
          "Segno X FT", _eval_draw_g),
    _rule("over_over_pt", "excel_d", "D45",
          '=IF(AND(OR(F36>1.7,F36<-1.5),F33>=6),"SI","NO")',
          "(F36 > 1,70 OR F36 < −1,50) AND F33 ≥ 6",
          "Over con forte squilibrio 1–2 e X molto alta.",
          "Cercare partite sbilanciate con X cara.",
          "Over 2.5 FT", _eval_over_d, "AND"),
    _rule("over_over_pt", "excel_e", "E45",
          '=IF(OR(D60="SI",E60="SI"),"SI","NO")',
          "12 / Excel D = SI OR 12 / Excel E = SI",
          "Over dipendente dai segnali 12 della stessa matrice.",
          "Riutilizzare lo squilibrio già catturato da 12.",
          "Over 2.5 FT", _eval_over_e, "OR"),
    _rule("over_over_pt", "excel_f", "F45",
          '=IF(OR(AND(F33>=5,F36>2),AND(F33>=5,F36<-2.1)),"SI","NO")',
          "(F33 ≥ 5 AND F36 > 2) OR (F33 ≥ 5 AND F36 < −2,10)",
          "Over con X ≥ 5 e spread F36 elevato.",
          "Variante Over su spread.",
          "Over 2.5 FT", _eval_over_f, "OR"),
    _rule("over_over_pt", "excel_g", "G45",
          '=IF(OR(AND(F33>=4,F36>2.55),AND(F33>=4,F36<-2.4)),"SI","NO")',
          "(F33 ≥ 4 AND F36 > 2,55) OR (F33 ≥ 4 AND F36 < −2,40)",
          "Over con soglie X/F36 diverse.",
          "Variante Over più permissiva su X.",
          "Over 2.5 FT", _eval_over_g, "OR"),
    _rule("one", "excel_d", "D48",
          '=IF(AND(G48="SI",F36>2,Dominanza>10),"SI","NO")',
          "Scala 1X = SI AND F36 > 2 AND Dominanza > 10",
          "Segnale 1: scala 1X, forte favorito trasferta su F36 e dominanza stretta (>10).",
          "Attivare 1 solo con scala e dominanza convincente.",
          "1 FT", _eval_one_d),
    _rule("one_x", "excel_d", "D51",
          '=IF(AND(F32<2.8,F33<=4,F35>4),"SI","NO")',
          "F32 < 2,80 AND F33 ≤ 4 AND F35 > 4",
          "1X con casa non carissima, X contenuta e media alta.",
          "Doppio 1X su quote medie elevate.",
          "1X FT", _eval_one_x_d),
    _rule("one_x", "excel_e", "E51",
          '=IF(AND(F32+0.4<F33,F33+0.5<F34,F32+0.6<F34),"SI","NO")',
          "F32+0,40 < F33 AND F33+0,50 < F34 AND F32+0,60 < F34",
          "1X con gap crescenti tra le quote (scala crescente).",
          "Catturare scala 1 < X < 2 con margini fissi.",
          "1X FT", _eval_one_x_e),
    _rule("one_x", "excel_f", "F51",
          '=IF(AND(F32<=1.8,F36>=2.5,F34>F33),"SI","NO")',
          "F32 ≤ 1,80 AND F36 ≥ 2,50 AND F34 > F33",
          "1X con casa fortissima e spread ampio.",
          "1X aggressivo su favorito casa.",
          "1X FT", _eval_one_x_f),
    _rule("one_x", "excel_g", "G51",
          '=IF(AND(F32<=2,F34>=4),"SI","NO")',
          "F32 ≤ 2 AND F34 ≥ 4",
          "1X con casa ≤ 2 e trasferta ≥ 4.",
          "1X semplice su favorito casa.",
          "1X FT", _eval_one_x_g),
    _rule("one_x", "scala_1x", "G48",
          '=IF(AND(F32<F33,F33<F34,F32<F34),"SI","NO")',
          "F32 < F33 AND F33 < F34 AND F32 < F34",
          "Scala crescente 1 < X < 2.",
          "Prerequisito per alcuni segnali (es. Segnale 1).",
          "Scala 1X", _eval_scala_1x),
    _rule("two", "excel_d", "D54",
          '=IF(AND(G54="SI",F36<-2.3,Dominanza>10),"SI","NO")',
          "Scala X2 = SI AND F36 < −2,30 AND Dominanza > 10",
          "Segnale 2: scala X2, forte favorito casa su F36 e dominanza > 10.",
          "Attivare 2 solo con scala e dominanza.",
          "2 FT", _eval_two_d),
    _rule("x_two", "excel_d", "D57",
          '=IF(AND(F34<=1.8,F32>=3.5,F34<F33),"SI","NO")',
          "F34 ≤ 1,80 AND F32 ≥ 3,50 AND F34 < F33",
          "X2 con trasferta fortissima.",
          "Doppio X2 aggressivo.",
          "X2 FT", _eval_x_two_d),
    _rule("x_two", "excel_e", "E57",
          '=IF(AND(F34+3<F32,F34<F33,F33<F32,F33<4),"SI","NO")',
          "F34+3 < F32 AND F34 < F33 AND F33 < F32 AND F33 < 4",
          "X2 con gap ampio casa–trasferta.",
          "X2 su squilibrio forte.",
          "X2 FT", _eval_x_two_e),
    _rule("x_two", "excel_f", "F57",
          '=IF(AND(F34<=2,F32>=4),"SI","NO")',
          "F34 ≤ 2 AND F32 ≥ 4",
          "X2 con trasferta ≤ 2 e casa ≥ 4.",
          "X2 semplice.",
          "X2 FT", _eval_x_two_f),
    _rule("x_two", "excel_g", "G57",
          '=IF(AND(F32+0.5>F33,F33+0.6>F34,F32+0.7>F34),"SI","NO")',
          "F32+0,50 > F33 AND F33+0,60 > F34 AND F32+0,70 > F34",
          "X2 con scala decrescente 1 > X > 2 (con margini).",
          "Catturare scala inversa.",
          "X2 FT", _eval_x_two_g),
    _rule("x_two", "scala_x2", "G54",
          '=IF(AND(F32>F33,F33>F34,F32>F34),"SI","NO")',
          "F32 > F33 AND F33 > F34 AND F32 > F34",
          "Scala decrescente 1 > X > 2.",
          "Prerequisito per Segnale 2.",
          "Scala X2", _eval_scala_x2),
    _rule("twelve", "excel_d", "D60",
          '=IF(OR(AND(F33>=4.8,F32<2.4,F36<-1.5),AND(F33>=4.8,F34<2.4,F36>1.5)),"SI","NO")',
          "(F33 ≥ 4,80 AND F32 < 2,40 AND F36 < −1,50) OR (F33 ≥ 4,80 AND F34 < 2,40 AND F36 > 1,50)",
          "12 con X cara e forte favorito su un lato.",
          "Escludere il pareggio con squilibrio netto.",
          "12 FT", _eval_twelve_d, "OR"),
    _rule("twelve", "excel_e", "E60",
          '=IF(AND(F33>=4.8,Dominanza>=10,ABS(F36)>=1.5),"SI","NO")',
          "F33 ≥ 4,80 AND Dominanza ≥ 10 AND |F36| ≥ 1,50",
          "12 con X cara, dominanza inclusiva (≥10) e spread.",
          "12 con conferma di dominanza.",
          "12 FT", _eval_twelve_e),
]

assert len(SIGNAL_RULE_REGISTRY) == 26, len(SIGNAL_RULE_REGISTRY)


def cell_key(row_key: str, column_key: str) -> str:
    return f"{row_key}:{column_key}"


def _index_stored(matrix: dict[str, Any]) -> dict[str, str]:
    out: dict[str, str] = {}
    for row in matrix.get("rows") or []:
        if not isinstance(row, dict):
            continue
        rk = str(row.get("key") or "")
        sig = row.get("signals") if isinstance(row.get("signals"), dict) else {}
        for ck, val in sig.items():
            if val in ("SI", "NO"):
                out[cell_key(rk, str(ck))] = val
    return out


def _index_canonical(matrix: dict[str, Any]) -> dict[str, str]:
    return _index_stored(matrix)


def _build_ctx(inputs: dict[str, Any], deps: dict[str, str]) -> Ctx:
    ctx: Ctx = {
        "q1": inputs.get("q1"),
        "qx": inputs.get("qx"),
        "q2": inputs.get("q2"),
        "avg_q": inputs.get("avg_q"),
        "diff_1_2": inputs.get("diff_1_2"),
        "dominance_pp": inputs.get("dominance_pp"),
        "under_2_5_cecchino_odd": inputs.get("under_2_5_cecchino_odd"),
        "prob_1": inputs.get("prob_1"),
        "prob_x": inputs.get("prob_x"),
        "prob_2": inputs.get("prob_2"),
    }
    ctx.update(deps)
    return ctx


def _consistency(stored: str | None, canonical: str | None, trace: str | None) -> dict[str, Any]:
    if stored is None and canonical is None and trace is None:
        return {"status": "unavailable"}
    if stored is None or canonical is None or trace is None:
        return {"status": "not_verifiable", "stored": stored, "canonical": canonical, "trace": trace}
    if canonical != trace:
        return {"status": "trace_mismatch", "stored": stored, "canonical": canonical, "trace": trace}
    if stored != canonical:
        return {"status": "mismatch", "stored": stored, "canonical": canonical, "trace": trace}
    return {"status": "match", "stored": stored, "canonical": canonical, "trace": trace}


def explain_all_cells_from_inputs(
    *,
    q1: float | None,
    qx: float | None,
    q2: float | None,
    sample_home_away_split: int,
    prob_1: float | None = None,
    prob_x: float | None = None,
    prob_2: float | None = None,
    under_2_5_cecchino_odd: float | None = None,
    stored_matrix: dict[str, Any] | None = None,
) -> dict[str, dict[str, Any]]:
    """Valuta tutte le 26 celle (usato anche dai test di parity/fuzz)."""
    canonical = build_signals_matrix(
        q1=q1,
        qx=qx,
        q2=q2,
        sample_home_away_split=sample_home_away_split,
        prob_1=prob_1,
        prob_x=prob_x,
        prob_2=prob_2,
        under_2_5_cecchino_odd=under_2_5_cecchino_odd,
    )
    inputs = canonical.get("inputs") if isinstance(canonical.get("inputs"), dict) else {}
    can_idx = _index_canonical(canonical)
    stored_idx = _index_stored(stored_matrix) if stored_matrix else can_idx

    # Dipendenze da canonical (stesso ordine del builder)
    deps = {
        "scala_1x": can_idx.get("one_x:scala_1x", "NO"),
        "scala_x2": can_idx.get("x_two:scala_x2", "NO"),
        "twelve_d": can_idx.get("twelve:excel_d", "NO"),
        "twelve_e": can_idx.get("twelve:excel_e", "NO"),
    }
    ctx = _build_ctx(inputs, deps)

    cells: dict[str, dict[str, Any]] = {}
    for rule in SIGNAL_RULE_REGISTRY:
        ck = rule["cell_key"]
        trace_result, logic, used_inputs = rule["evaluate"](ctx)
        stored = stored_idx.get(ck)
        canonical_r = can_idx.get(ck)
        summary, passed, failed = _reason_summary(trace_result, logic)
        formula_applied = [
            f"{'✓' if c.get('passed') else '✗'} {c.get('expression')}"
            for c in (passed + failed)
        ]
        cells[ck] = {
            "row_key": rule["row_key"],
            "row_label": rule["row_label"],
            "column_key": rule["column_key"],
            "column_label": rule["column_label"],
            "source_cell": rule["source_cell"],
            "stored_result": stored,
            "canonical_audit_result": canonical_r,
            "condition_trace_result": trace_result,
            "consistency": _consistency(stored, canonical_r, trace_result),
            "description": rule["description"],
            "purpose": rule["purpose"],
            "target_market": rule["target_market"],
            "excel_formula": rule["excel_formula"],
            "formula_symbolic": rule["formula_symbolic"],
            "formula_applied": formula_applied,
            "logic": logic,
            "passed_conditions": passed,
            "failed_conditions": failed,
            "reason_summary": summary,
            "inputs": used_inputs,
            "warnings": [],
            "si_meaning": f"SI indica che le condizioni del segnale {rule['row_label']} / {rule['column_label']} sono soddisfatte.",
            "no_meaning": f"NO indica che almeno una condizione richiesta non è soddisfatta.",
        }
    return cells


def build_signal_explanations(row: CecchinoTodayFixture) -> dict[str, Any]:
    output = row.cecchino_output_json if isinstance(row.cecchino_output_json, dict) else {}
    matrix = output.get("signals_matrix")
    if not isinstance(matrix, dict):
        return {
            "status": "error",
            "code": "signals_matrix_not_available",
            "message": "Matrice segnali non disponibile",
        }
    rows = matrix.get("rows")
    if not isinstance(rows, list) or not rows:
        return {
            "status": "error",
            "code": "signals_matrix_not_available",
            "message": "Matrice segnali non disponibile",
        }
    stored_si_no = _index_stored(matrix)
    if not stored_si_no and matrix.get("status") != STATUS_AVAILABLE:
        return {
            "status": "error",
            "code": "signals_matrix_not_available",
            "message": "Matrice segnali non disponibile",
        }

    inputs = matrix.get("inputs") if isinstance(matrix.get("inputs"), dict) else {}
    rel = matrix.get("reliability") if isinstance(matrix.get("reliability"), dict) else {}
    sample = int(rel.get("sample") or 0)

    cells = explain_all_cells_from_inputs(
        q1=_num(inputs.get("q1")),
        qx=_num(inputs.get("qx")),
        q2=_num(inputs.get("q2")),
        sample_home_away_split=sample,
        prob_1=_num(inputs.get("prob_1")),
        prob_x=_num(inputs.get("prob_x")),
        prob_2=_num(inputs.get("prob_2")),
        under_2_5_cecchino_odd=_num(inputs.get("under_2_5_cecchino_odd")),
        stored_matrix=matrix,
    )

    warnings = list(matrix.get("warnings") or [])
    partial = False
    for expl in cells.values():
        st = expl.get("consistency", {}).get("status")
        if st in ("mismatch", "trace_mismatch", "not_verifiable"):
            partial = True
            warnings.append(f"consistency:{expl['row_key']}:{expl['column_key']}:{st}")

    reliability_block = {
        "sample": rel.get("sample", 0),
        "index": rel.get("index", 0),
        "status": rel.get("status", "NO BET"),
        "level": rel.get("level", "BASSA"),
        "formula_symbolic": "index = min(sample / 20, 1)",
        "status_rule": "OK se index >= 0.5, altrimenti NO BET",
        "level_rule": "ALTA >= 0.75; MEDIA >= 0.5; BASSA < 0.5",
    }

    stored_formula_version = normalize_formula_version(
        matrix.get("formula_version") if isinstance(matrix.get("formula_version"), str) else None,
    )
    if stored_formula_version != CURRENT_SIGNAL_FORMULA_VERSION:
        warnings.append(
            f"formula_version_mismatch:stored={stored_formula_version};"
            f"audit_canonical={CURRENT_SIGNAL_FORMULA_VERSION}",
        )
        partial = True

    consensus_sections: list[dict[str, Any]] = []
    matrix_rows = matrix.get("rows") if isinstance(matrix.get("rows"), list) else []
    for mrow in matrix_rows:
        if not isinstance(mrow, dict):
            continue
        group = map_row_key_to_signal_group(str(mrow.get("key") or ""))
        if not group:
            continue
        consensus = mrow.get("consensus") if isinstance(mrow.get("consensus"), dict) else None
        if consensus is None:
            consensus = compute_consensus_for_matrix_row(mrow)
        available = list(GROUP_AVAILABLE_COLUMNS.get(group, ()))
        consensus_sections.append(
            {
                "title": "CONSENSO DEL SEGNO",
                "signal_group": group,
                "row_key": mrow.get("key"),
                "row_label": mrow.get("label"),
                "available_formulas": available,
                "yes_columns": consensus.get("consensus_yes_columns") or [],
                "yes_count": consensus.get("consensus_yes_count"),
                "required_count": consensus.get("consensus_required_count"),
                "exempt": group in SINGLE_FORMULA_EXEMPT_GROUPS,
                "consensus_passed": consensus.get("consensus_passed"),
                "acquisition_status": consensus.get("acquisition_status"),
                "is_acquired": consensus.get("is_acquired"),
                "policy_version": consensus.get("consensus_policy_version")
                or SIGNAL_CONSENSUS_POLICY_VERSION,
                "reason": (
                    "Segno acquisito per consenso minimo"
                    if consensus.get("acquisition_status") == "acquired_consensus"
                    else (
                        "Segno acquisito per esenzione 1/2 (unica formula)"
                        if consensus.get("acquisition_status") == "acquired_single_formula_exempt"
                        else (
                            "Conferme insufficienti: SI grezzi non acquisiti"
                            if consensus.get("acquisition_status")
                            == "rejected_insufficient_consensus"
                            else "Nessuna formula SI"
                        )
                    )
                ),
            },
        )

    return {
        "status": "partial" if partial else "ok",
        "audit_version": AUDIT_VERSION,
        "module": "cecchino_signals",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "no_operational_recalculation": True,
        "diagnostic_re_evaluation_only": True,
        "formula_version": CURRENT_SIGNAL_FORMULA_VERSION,
        "stored_formula_version": stored_formula_version,
        "legacy_formula_version": LEGACY_SIGNAL_FORMULA_VERSION,
        "consensus_policy_version": SIGNAL_CONSENSUS_POLICY_VERSION,
        "fixture": {
            "today_fixture_id": int(row.id),
            "local_fixture_id": int(row.local_fixture_id) if row.local_fixture_id else None,
            "provider_fixture_id": int(row.provider_fixture_id) if row.provider_fixture_id else None,
            "home_team": row.home_team_name,
            "away_team": row.away_team_name,
            "kickoff": row.kickoff.isoformat() if row.kickoff else None,
            "scan_date": row.scan_date.isoformat() if row.scan_date else None,
        },
        "matrix": {
            "source": matrix.get("source"),
            "status": matrix.get("status"),
            "formula_version": matrix.get("formula_version") or stored_formula_version,
            "consensus_policy_version": matrix.get("consensus_policy_version")
            or SIGNAL_CONSENSUS_POLICY_VERSION,
            "inputs": inputs,
            "reliability": reliability_block,
            "excel_mapping": matrix.get("excel_mapping"),
            "warnings": list(matrix.get("warnings") or []),
        },
        "signal_consensus": consensus_sections,
        "active_cell_count": len(cells),
        "excluded_cells": "cells_without_SI_NO",
        "cells": cells,
        "warnings": warnings,
    }


def get_signal_explanations(db: Session, today_fixture_id: int) -> dict[str, Any] | None:
    row = db.get(CecchinoTodayFixture, today_fixture_id)
    if row is None:
        return None
    if row.eligibility_status != ELIGIBILITY_ELIGIBLE:
        return {
            "status": "error",
            "code": "not_eligible",
            "message": "Fixture non eleggibile",
        }
    return build_signal_explanations(row)
