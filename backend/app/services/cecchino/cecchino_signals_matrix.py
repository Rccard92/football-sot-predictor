"""
Matrice segnali SI/NO — parità formule foglio Excel CECCHINO (F32–F60).
Funzione pura: quote finali Cecchino, probabilità 1X2 e sample casa/trasferta.
"""

from __future__ import annotations

import math
from decimal import Decimal
from typing import Any

from app.services.cecchino.cecchino_balance_analysis import compute_dominance_pp
from app.services.cecchino.cecchino_constants import STATUS_AVAILABLE, STATUS_INSUFFICIENT_DATA
from app.services.cecchino.cecchino_signal_consensus import (
    CURRENT_SIGNAL_FORMULA_VERSION,
    LEGACY_SIGNAL_FORMULA_VERSION,
    PREVIOUS_SIGNAL_FORMULA_VERSION,
    SIGNAL_CONSENSUS_POLICY_VERSION,
    attach_consensus_to_matrix_rows,
)
from app.services.cecchino.cecchino_signal_decimal import (
    SIGNAL_FORMULA_DECIMAL_QUANTUM,
    canonical_signal_decimal,
    format_canonical_decimal,
)

EXCEL_SOURCE = "AutomazioneCecchino.xlsm"
WARNING_MISSING_QUOTAS = "signals_matrix:missing_final_quotas"

# Re-export versioning canoniche
__all__ = [
    "LEGACY_SIGNAL_FORMULA_VERSION",
    "PREVIOUS_SIGNAL_FORMULA_VERSION",
    "CURRENT_SIGNAL_FORMULA_VERSION",
    "SIGNAL_CONSENSUS_POLICY_VERSION",
    "build_signals_matrix",
    "EXCEL_SOURCE",
    "WARNING_MISSING_QUOTAS",
]

SiNo = str  # "SI" | "NO"


def _si_no(condition: bool) -> SiNo:
    return "SI" if condition else "NO"


def _valid_quota(q: float | None) -> bool:
    return q is not None and math.isfinite(q) and q > 0


def _compute_reliability(sample_home_away_split: int) -> dict[str, Any]:
    sample = max(0, int(sample_home_away_split))
    index = min(sample / 20.0, 1.0) if sample >= 0 else 0.0
    status = "OK" if index >= 0.5 else "NO BET"
    if index >= 0.75:
        level = "ALTA"
    elif index >= 0.5:
        level = "MEDIA"
    else:
        level = "BASSA"
    return {
        "sample": sample,
        "index": round(index, 4),
        "status": status,
        "level": level,
    }


def build_signals_matrix(
    *,
    q1: float | None,
    qx: float | None,
    q2: float | None,
    sample_home_away_split: int,
    prob_1: float | None = None,
    prob_x: float | None = None,
    prob_2: float | None = None,
    under_2_5_cecchino_odd: float | None = None,
) -> dict[str, Any]:
    """
    Calcola matrice segnali SI/NO e indice affidabilità.
    Ordine: scala_1x, scala_x2, twelve_d/e, poi righe mercato (over_e dipende da 12).
    """
    warnings: list[str] = []

    if not (_valid_quota(q1) and _valid_quota(qx) and _valid_quota(q2)):
        warnings.append(WARNING_MISSING_QUOTAS)
        return {
            "status": STATUS_INSUFFICIENT_DATA,
            "source": EXCEL_SOURCE,
            "formula_version": CURRENT_SIGNAL_FORMULA_VERSION,
            "consensus_policy_version": SIGNAL_CONSENSUS_POLICY_VERSION,
            "excel_mapping": {
                "q1": "F32",
                "qx": "F33",
                "q2": "F34",
                "avg_q": "F35",
                "diff_1_2": "F36",
            },
            "inputs": {
                "q1": q1,
                "qx": qx,
                "q2": q2,
                "avg_q": None,
                "diff_1_2": None,
                "dominance_pp": None,
            },
            "rows": [],
            "reliability": _compute_reliability(sample_home_away_split),
            "warnings": warnings,
        }

    assert q1 is not None and qx is not None and q2 is not None
    avg_q = (q1 + qx + q2) / 3.0
    diff_1_2 = q2 - q1
    dominance_pp = compute_dominance_pp(prob_1, prob_x, prob_2)

    # --- Scalari (dipendenze) ---
    scala_1x = _si_no(q1 < qx and qx < q2 and q1 < q2)
    scala_x2 = _si_no(q1 > qx and qx > q2 and q1 > q2)

    # 12 (prima di over_e) — Fase 45
    twelve_d = _si_no(
        (qx >= 4.8 and q1 < 2.40 and diff_1_2 < -1.5)
        or (qx >= 4.8 and q2 < 2.40 and diff_1_2 > 1.5),
    )
    twelve_e = _si_no(
        qx >= 4.8
        and dominance_pp is not None
        and dominance_pp >= 10
        and abs(diff_1_2) >= 1.5,
    )

    # UNDER / UNDER PT — D39: F36 range + F32>=F34 + UNDER2.5<=2
    under_d = _si_no(
        diff_1_2 < 0.9
        and diff_1_2 > -0.8
        and q1 >= q2
        and under_2_5_cecchino_odd is not None
        and under_2_5_cecchino_odd <= 2,
    )
    if avg_q > 0:
        under_e = _si_no(
            q1 / avg_q > 0.88
            and qx / avg_q > 0.88
            and q2 / avg_q > 0.88
            and q1 / avg_q < 1.2
            and qx / avg_q < 1.2
            and q2 / avg_q < 1.2,
        )
    else:
        under_e = "NO"
    under_f = _si_no(
        diff_1_2 <= 1.53
        and diff_1_2 >= -1.5
        and qx <= 3
        and q1 >= q2
        and under_2_5_cecchino_odd is not None
        and under_2_5_cecchino_odd <= 2,
    )
    under_g = _si_no(
        diff_1_2 <= 1.33
        and diff_1_2 >= -1.23
        and qx < 4
        and q1 >= q2
        and under_2_5_cecchino_odd is not None
        and under_2_5_cecchino_odd <= 2,
    )

    # SEGNO X (V3: Decimal canonici a 2 cifre; logica D/E/F/G invariata)
    f32_x = canonical_signal_decimal(q1)
    f33_x = canonical_signal_decimal(qx)
    f34_x = canonical_signal_decimal(q2)
    f36_x = (
        canonical_signal_decimal(f34_x - f32_x)
        if f32_x is not None and f34_x is not None
        else None
    )
    draw_inputs_ok = f32_x is not None and f33_x is not None and f34_x is not None and f36_x is not None
    if draw_inputs_ok:
        x_d = _si_no(
            f36_x < Decimal("0.80")
            and f36_x > Decimal("-0.80")
            and f32_x >= f34_x,
        )
        x_e = _si_no(
            f33_x < Decimal("3.30")
            and f36_x <= Decimal("1.47")
            and f36_x >= Decimal("-1.40")
            and f32_x >= f34_x,
        )
        x_f = _si_no(
            f33_x <= Decimal("2.90")
            and f36_x <= Decimal("1.70")
            and f36_x >= Decimal("-1.70")
            and f32_x >= f34_x,
        )
        x_g = _si_no(
            f33_x <= Decimal("3.50")
            and f36_x <= Decimal("1.20")
            and f36_x >= Decimal("-1.20")
            and f32_x >= f34_x,
        )
    else:
        x_d = x_e = x_f = x_g = "NO"

    decimal_policy = {
        "scope": "draw_formulas_only",
        "quantum": format_canonical_decimal(SIGNAL_FORMULA_DECIMAL_QUANTUM) or "0.01",
        "rounding": "ROUND_HALF_UP",
        "canonical_q1": format_canonical_decimal(f32_x),
        "canonical_qx": format_canonical_decimal(f33_x),
        "canonical_q2": format_canonical_decimal(f34_x),
        "canonical_f36": format_canonical_decimal(f36_x),
    }

    # OVER / OVER PT
    over_d = _si_no((diff_1_2 > 1.7 or diff_1_2 < -1.5) and qx >= 6)
    over_e = _si_no(twelve_d == "SI" or twelve_e == "SI")
    over_f = _si_no((qx >= 5 and diff_1_2 > 2) or (qx >= 5 and diff_1_2 < -2.1))
    over_g = _si_no((qx >= 4 and diff_1_2 > 2.55) or (qx >= 4 and diff_1_2 < -2.4))

    # 1 — Fase 45 D48
    one_d = _si_no(
        scala_1x == "SI"
        and diff_1_2 > 2
        and dominance_pp is not None
        and dominance_pp > 10,
    )

    # 1X — Fase 45 E51
    one_x_d = _si_no(q1 < 2.8 and qx <= 4 and avg_q > 4)
    one_x_e = _si_no(q1 + 0.4 < qx and qx + 0.5 < q2 and q1 + 0.6 < q2)
    one_x_f = _si_no(q1 <= 1.8 and diff_1_2 >= 2.5 and q2 > qx)
    one_x_g = _si_no(q1 <= 2 and q2 >= 4)

    # 2 — Fase 45 D54
    two_d = _si_no(
        scala_x2 == "SI"
        and diff_1_2 < -2.3
        and dominance_pp is not None
        and dominance_pp > 10,
    )

    # X2 — Fase 45 G57
    x_two_d = _si_no(q2 <= 1.8 and q1 >= 3.5 and q2 < qx)
    x_two_e = _si_no(q2 + 3 < q1 and q2 < qx and qx < q1 and qx < 4)
    x_two_f = _si_no(q2 <= 2 and q1 >= 4)
    x_two_g = _si_no(q1 + 0.5 > qx and qx + 0.6 > q2 and q1 + 0.7 > q2)

    rows: list[dict[str, Any]] = [
        {
            "key": "under_under_pt",
            "label": "UNDER / UNDER PT",
            "signals": {
                "excel_d": under_d,
                "excel_e": under_e,
                "excel_f": under_f,
                "excel_g": under_g,
            },
        },
        {
            "key": "draw",
            "label": "SEGNO X",
            "signals": {
                "excel_d": x_d,
                "excel_e": x_e,
                "excel_f": x_f,
                "excel_g": x_g,
            },
        },
        {
            "key": "over_over_pt",
            "label": "OVER / OVER PT",
            "signals": {
                "excel_d": over_d,
                "excel_e": over_e,
                "excel_f": over_f,
                "excel_g": over_g,
            },
        },
        {
            "key": "one",
            "label": "1",
            "signals": {"excel_d": one_d},
            "excel_cells": {"excel_d": "D48"},
        },
        {
            "key": "one_x",
            "label": "1X",
            "signals": {
                "excel_d": one_x_d,
                "excel_e": one_x_e,
                "excel_f": one_x_f,
                "excel_g": one_x_g,
                "scala_1x": scala_1x,
            },
            "excel_cells": {
                "excel_d": "D51",
                "excel_e": "E51",
                "excel_f": "F51",
                "excel_g": "G51",
                "scala_1x": "G48",
            },
        },
        {
            "key": "two",
            "label": "2",
            "signals": {"excel_d": two_d},
            "excel_cells": {"excel_d": "D54"},
        },
        {
            "key": "x_two",
            "label": "X2",
            "signals": {
                "excel_d": x_two_d,
                "excel_e": x_two_e,
                "excel_f": x_two_f,
                "excel_g": x_two_g,
                "scala_x2": scala_x2,
            },
            "excel_cells": {
                "excel_d": "D57",
                "excel_e": "E57",
                "excel_f": "F57",
                "excel_g": "G57",
                "scala_x2": "G54",
            },
        },
        {
            "key": "twelve",
            "label": "12",
            "signals": {"excel_d": twelve_d, "excel_e": twelve_e},
            "excel_cells": {"excel_d": "D60", "excel_e": "E60"},
        },
    ]

    attach_consensus_to_matrix_rows(rows)

    return {
        "status": STATUS_AVAILABLE,
        "source": EXCEL_SOURCE,
        "formula_version": CURRENT_SIGNAL_FORMULA_VERSION,
        "consensus_policy_version": SIGNAL_CONSENSUS_POLICY_VERSION,
        "excel_mapping": {
            "q1": "F32",
            "qx": "F33",
            "q2": "F34",
            "avg_q": "F35",
            "diff_1_2": "F36",
            "under_2_5_cecchino_odd": "UNDER2.5",
        },
        "inputs": {
            "q1": q1,
            "qx": qx,
            "q2": q2,
            "avg_q": avg_q,
            "diff_1_2": diff_1_2,
            "dominance_pp": dominance_pp,
            "prob_1": prob_1,
            "prob_x": prob_x,
            "prob_2": prob_2,
            "under_2_5_cecchino_odd": under_2_5_cecchino_odd,
        },
        "decimal_policy": decimal_policy,
        "rows": rows,
        "reliability": _compute_reliability(sample_home_away_split),
        "warnings": warnings,
    }
