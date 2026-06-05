"""Gate quote bookmaker strict Cecchino Today."""

from __future__ import annotations

from typing import Any

from app.services.cecchino.cecchino_api_football_odds import parse_api_football_odds_response
from app.services.cecchino.cecchino_bookmaker_derive import build_bookmaker_structures
from app.services.cecchino.cecchino_constants import CECCHINO_BOOKMAKERS
from app.services.cecchino.cecchino_selection_keys import MARKET_1X2, SEL_AWAY, SEL_DRAW, SEL_HOME


def verify_complete_1x2_odds(
    odds_by_bookmaker: dict[int, list[dict[str, Any]]],
) -> tuple[bool, dict[str, Any], str | None, list[str]]:
    """
    Verifica Bet365/Betfair/Pinnacle con 1X2 completo.
    odds_by_bookmaker: bookmaker_id -> raw API response list
    Ritorna (ok, snapshot, reason_code, blocking_reasons).
    """
    parsed_rows: list[dict[str, Any]] = []
    book_snapshots: dict[str, dict[str, float | None]] = {}
    blocking_reasons: list[str] = []
    missing_bookmakers: list[str] = []

    for bm in CECCHINO_BOOKMAKERS:
        bid = int(bm["provider_bookmaker_id"])
        name = bm["name"]
        raw = odds_by_bookmaker.get(bid)
        if not raw:
            missing_bookmakers.append(name)
            blocking_reasons.append(f"missing_bookmaker:{name}")
            continue
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
            if home is None:
                blocking_reasons.append(f"missing_selection:{name}:HOME")
            if draw is None:
                blocking_reasons.append(f"missing_selection:{name}:DRAW")
            if away is None:
                blocking_reasons.append(f"missing_selection:{name}:AWAY")
            if home is None and draw is None and away is None:
                blocking_reasons.append(f"missing_1x2:{name}")
            missing_bookmakers.append(name)
            continue
        book_snapshots[name] = {"HOME": home, "DRAW": draw, "AWAY": away}
        for r in rows:
            parsed_rows.append({**r, "bookmaker_name": name, "provider_bookmaker_id": str(bid)})

    if blocking_reasons:
        any_raw = any(odds_by_bookmaker.get(int(bm["provider_bookmaker_id"])) for bm in CECCHINO_BOOKMAKERS)
        if any(m.startswith("missing_bookmaker:") for m in blocking_reasons) and not any_raw:
            reason = "missing_bookmaker"
        elif any(m.startswith("missing_bookmaker:") for m in blocking_reasons):
            reason = "missing_bookmaker"
        else:
            reason = "missing_1x2_market"
        return False, {"bookmakers": book_snapshots, "missing": missing_bookmakers}, reason, blocking_reasons

    class _Row:
        def __init__(self, d: dict[str, Any]) -> None:
            self.provider_bookmaker_id = d["provider_bookmaker_id"]
            self.bookmaker_name = d["bookmaker_name"]
            self.normalized_market = d["normalized_market"]
            self.selection_key = d["selection_key"]
            self.odds_value = d["odds_value"]

    fake_rows = [_Row(r) for r in parsed_rows if r.get("normalized_market") == MARKET_1X2]
    _, avg, _, status = build_bookmaker_structures(fake_rows, bookmaker_defs=CECCHINO_BOOKMAKERS)

    snapshot = {
        "bookmakers": book_snapshots,
        "bookmaker_average": avg.get(MARKET_1X2),
        "status": status,
        "raw_by_bookmaker_id": {str(k): v for k, v in odds_by_bookmaker.items()},
    }
    return True, snapshot, None, []
