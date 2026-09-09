"""Settlement RUN V2: esito reale dei mercati CORE.

Delega a `evaluate_market_selection` (V1, invariata) per tutti i mercati gia
supportati e gestisce localmente solo FT O/U 0.5, che la V1 non conosce. In
questo modo il modulo di valutazione segnali live non viene toccato.

Nulla di qui viene mai letto prima del freeze della prediction.
"""

from __future__ import annotations

from typing import Any

from app.models.cecchino_signal_activation import (
    EVAL_LOST,
    EVAL_NOT_EVALUABLE,
    EVAL_RESULT_MISSING,
    EVAL_WON,
)
from app.services.cecchino.cecchino_selection_keys import SEL_OVER_0_5, SEL_UNDER_0_5
from app.services.cecchino.cecchino_signal_evaluation import evaluate_market_selection

OUTCOME_WIN = "WIN"
OUTCOME_LOSS = "LOSS"
OUTCOME_PUSH = "PUSH"
OUTCOME_UNKNOWN = "UNKNOWN"

# Linee intere (che ammettono il rimborso) non sono in uso nella RUN V2: tutte
# le linee O/U configurate sono a mezzo goal, quindi PUSH non si verifica.
_V2_ONLY_MARKETS = frozenset({SEL_OVER_0_5, SEL_UNDER_0_5})


def match_result_from_lab_match(match: Any) -> dict[str, Any]:
    return {
        "fulltime": {"home": match.ft_home_goals, "away": match.ft_away_goals},
        "halftime": {"home": match.ht_home_goals, "away": match.ht_away_goals},
    }


def _evaluate_ou_05(market_key: str, match_result: dict[str, Any]) -> dict[str, Any]:
    ft = match_result.get("fulltime") or {}
    home, away = ft.get("home"), ft.get("away")
    if home is None or away is None:
        return {
            "evaluation_status": EVAL_RESULT_MISSING,
            "evaluation_reason": "fulltime_result_missing",
        }
    total = int(home) + int(away)
    won = total >= 1 if market_key == SEL_OVER_0_5 else total == 0
    return {
        "evaluation_status": EVAL_WON if won else EVAL_LOST,
        "evaluation_reason": None,
    }


def evaluate_market_outcome_v2(market_key: str, match_result: dict[str, Any]) -> dict[str, Any]:
    """Esito di un mercato CORE V2 come outcome normalizzato."""
    if market_key in _V2_ONLY_MARKETS:
        res = _evaluate_ou_05(market_key, match_result)
    else:
        res = evaluate_market_selection(market_key, match_result)

    status = res.get("evaluation_status")
    if status == EVAL_WON:
        outcome, won = OUTCOME_WIN, True
    elif status == EVAL_LOST:
        outcome, won = OUTCOME_LOSS, False
    else:
        outcome, won = OUTCOME_UNKNOWN, None

    return {
        "market_key": market_key,
        "evaluation_status": status,
        "outcome": outcome,
        "won": won,
        "result_reason": res.get("evaluation_reason"),
        "evaluable": won is not None,
        "not_evaluable": status == EVAL_NOT_EVALUABLE,
    }


def flat_stake_profit(*, won: bool | None, quota: float | None) -> float | None:
    """Profitto a puntata piatta di 1 unita. None se non calcolabile."""
    if won is None or quota is None:
        return None
    try:
        q = float(quota)
    except (TypeError, ValueError):
        return None
    if q <= 1.0:
        return None
    return round(q - 1.0, 4) if won else -1.0
