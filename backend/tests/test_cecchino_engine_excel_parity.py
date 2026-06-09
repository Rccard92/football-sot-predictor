"""Parità numerica con foglio Excel CECCHINO — San Lorenzo vs Deportivo Riestra."""

from __future__ import annotations

import pytest

from app.services.cecchino.cecchino_constants import (
    PICCHETTO_KEY_HOME_AWAY,
    PICCHETTO_KEY_LAST5_HOME_AWAY,
    PICCHETTO_KEY_LAST6_TOTALS,
    PICCHETTO_KEY_TOTALS,
    STATUS_AVAILABLE,
)
from app.services.cecchino.cecchino_engine import (
    CecchinoCalculationInput,
    WDLRecord,
    build_full_cecchino_output,
    compute_picchetto,
)


def _san_lorenzo_riestra_input() -> CecchinoCalculationInput:
    return CecchinoCalculationInput(
        home_away=(
            WDLRecord(wins=3, draws=2, losses=3),
            WDLRecord(wins=0, draws=3, losses=5),
        ),
        totals=(
            WDLRecord(wins=5, draws=7, losses=4),
            WDLRecord(wins=1, draws=8, losses=7),
        ),
        last5_home_away=(
            WDLRecord(wins=1, draws=2, losses=2),
            WDLRecord(wins=0, draws=2, losses=3),
        ),
        last6_totals=(
            WDLRecord(wins=2, draws=3, losses=1),
            WDLRecord(wins=1, draws=2, losses=3),
        ),
    )


@pytest.mark.parametrize(
    "key,home,away,expected_quotas",
    [
        (
            PICCHETTO_KEY_HOME_AWAY,
            WDLRecord(3, 2, 3),
            WDLRecord(0, 3, 5),
            (2.00, 3.20, 5.33),
        ),
        (
            PICCHETTO_KEY_TOTALS,
            WDLRecord(5, 7, 4),
            WDLRecord(1, 8, 7),
            (2.67, 2.13, 6.40),
        ),
        (
            PICCHETTO_KEY_LAST5_HOME_AWAY,
            WDLRecord(1, 2, 2),
            WDLRecord(0, 2, 3),
            (2.50, 2.50, 5.00),
        ),
        (
            PICCHETTO_KEY_LAST6_TOTALS,
            WDLRecord(2, 3, 1),
            WDLRecord(1, 2, 3),
            (2.40, 2.40, 6.00),
        ),
    ],
)
def test_picchetto_quotas_excel_parity(key, home, away, expected_quotas):
    block = compute_picchetto(key, home, away)
    assert block.status == STATUS_AVAILABLE
    q1, qx, q2 = expected_quotas
    assert block.outcome_1.quota == pytest.approx(q1, abs=0.01)
    assert block.outcome_x.quota == pytest.approx(qx, abs=0.01)
    assert block.outcome_2.quota == pytest.approx(q2, abs=0.01)


def test_final_quotas_and_probs_excel_parity():
    out = build_full_cecchino_output(_san_lorenzo_riestra_input())
    assert out.status == STATUS_AVAILABLE
    assert out.final.quota_1 == pytest.approx(2.381, abs=0.01)
    assert out.final.quota_x == pytest.approx(2.579, abs=0.01)
    assert out.final.quota_2 == pytest.approx(5.719, abs=0.01)
    assert out.final.prob_1 == pytest.approx(0.4200, abs=0.01)
    assert out.final.prob_x == pytest.approx(0.3877, abs=0.01)
    assert out.final.prob_2 == pytest.approx(0.1749, abs=0.01)
