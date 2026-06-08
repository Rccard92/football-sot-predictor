"""Gate quote bookmaker strict Cecchino Today (Betfair-only)."""

from __future__ import annotations

from typing import Any

from app.services.cecchino.cecchino_api_football_odds import parse_api_football_odds_response
from app.services.cecchino.cecchino_constants import CECCHINO_BOOKMAKER
from app.services.cecchino.cecchino_selection_keys import MARKET_1X2, SEL_AWAY, SEL_DRAW, SEL_HOME

_BETFAIR_ID = int(CECCHINO_BOOKMAKER["provider_bookmaker_id"])
_BETFAIR_NAME = str(CECCHINO_BOOKMAKER["name"])


def verify_complete_1x2_odds(
    odds_by_bookmaker: dict[int, list[dict[str, Any]]],
) -> tuple[bool, dict[str, Any], str | None, list[str]]:
    """
    Verifica Betfair con 1X2 completo (HOME/DRAW/AWAY).
    odds_by_bookmaker: bookmaker_id -> raw API response list
    Ritorna (ok, snapshot, reason_code, blocking_reasons).
    """
    blocking_reasons: list[str] = []
    book_snapshots: dict[str, dict[str, float | None]] = {}

    raw = odds_by_bookmaker.get(_BETFAIR_ID)
    if not raw:
        blocking_reasons.append(f"missing_bookmaker:{_BETFAIR_NAME}")
        return (
            False,
            {"bookmakers": book_snapshots, "missing": [_BETFAIR_NAME]},
            "missing_bookmaker",
            blocking_reasons,
        )

    rows, _ = parse_api_football_odds_response(raw, requested_markets=[MARKET_1X2])
    home = draw = away = None
    for r in rows:
        if r["normalized_market"] != MARKET_1X2:
            continue
        if r["selection_key"] == SEL_HOME:
            home = r["odds_value"]
        elif r["selection_key"] == SEL_DRAW:
            draw = r["odds_value"]
        elif r["selection_key"] == SEL_AWAY:
            away = r["odds_value"]

    if home is None or draw is None or away is None:
        if home is None and draw is None and away is None:
            blocking_reasons.append(f"missing_1x2:{_BETFAIR_NAME}")
        if home is None:
            blocking_reasons.append(f"missing_selection:{_BETFAIR_NAME}:HOME")
        if draw is None:
            blocking_reasons.append(f"missing_selection:{_BETFAIR_NAME}:DRAW")
        if away is None:
            blocking_reasons.append(f"missing_selection:{_BETFAIR_NAME}:AWAY")
        return (
            False,
            {"bookmakers": book_snapshots, "missing": [_BETFAIR_NAME]},
            "missing_1x2_market",
            blocking_reasons,
        )

    book_snapshots[_BETFAIR_NAME] = {"HOME": home, "DRAW": draw, "AWAY": away}

    snapshot = {
        "bookmakers": book_snapshots,
        "status": "available",
        "raw_by_bookmaker_id": {str(k): v for k, v in odds_by_bookmaker.items()},
    }
    return True, snapshot, None, []
