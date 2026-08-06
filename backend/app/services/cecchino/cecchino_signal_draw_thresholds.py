"""Soglie Decimal canoniche per formule DRAW (SEGNO X) — motore + registry/audit.

Non alterare valori o operatori: devono restare identici al foglio Excel / V3.
"""

from __future__ import annotations

from decimal import Decimal

DRAW_D_F36_UPPER = Decimal("0.80")
DRAW_D_F36_LOWER = Decimal("-0.80")

DRAW_E_QX_UPPER = Decimal("3.30")
DRAW_E_F36_UPPER = Decimal("1.47")
DRAW_E_F36_LOWER = Decimal("-1.40")

DRAW_F_QX_UPPER = Decimal("2.90")
DRAW_F_F36_UPPER = Decimal("1.70")
DRAW_F_F36_LOWER = Decimal("-1.70")

DRAW_G_QX_UPPER = Decimal("3.50")
DRAW_G_F36_UPPER = Decimal("1.20")
DRAW_G_F36_LOWER = Decimal("-1.20")
