"""Debug mercati raw API-Football per fixture/bookmaker."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models import Fixture
from app.services.api_football_client import ApiFootballClient, ApiFootballError
from app.services.bookmakers.bookmaker_constants import PROVIDER_SOURCE_API_FOOTBALL
from app.services.bookmakers.market_normalize import (
    MARKET_OVER_UNDER_GOALS,
    normalize_api_football_market,
    normalize_over_under_selection,
    SEL_OVER_1_5,
    SEL_OVER_2_5,
)
from app.services.cecchino.cecchino_constants import CECCHINO_BOOKMAKERS

_DEFAULT_BOOKMAKER_IDS = [int(b["provider_bookmaker_id"]) for b in CECCHINO_BOOKMAKERS]
_BOOKMAKER_NAMES = {int(b["provider_bookmaker_id"]): str(b["name"]) for b in CECCHINO_BOOKMAKERS}


def _parse_odd(raw: Any) -> float | None:
    if raw is None:
        return None
    try:
        v = float(str(raw).replace(",", "."))
        return v if v > 1.0 else None
    except (TypeError, ValueError):
        return None


def _extract_bets(raw_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    bets: list[dict[str, Any]] = []
    for item in raw_items:
        for bm in item.get("bookmakers") or []:
            if not isinstance(bm, dict):
                continue
            for bet in bm.get("bets") or []:
                if isinstance(bet, dict):
                    bets.append(bet)
    return bets


class ApiFootballFixtureMarketsDebugService:
    def __init__(self, client: ApiFootballClient | None = None) -> None:
        self._client = client or ApiFootballClient()

    def run(
        self,
        db: Session,
        *,
        fixture_id: int | None = None,
        provider_fixture_id: int | None = None,
        provider_source: str = PROVIDER_SOURCE_API_FOOTBALL,
        bookmaker_ids: list[int] | None = None,
    ) -> dict[str, Any]:
        if provider_source != PROVIDER_SOURCE_API_FOOTBALL:
            return {
                "status": "error",
                "message": f"provider_source non supportato: {provider_source}",
            }

        api_fid = provider_fixture_id
        internal_fixture_id: int | None = fixture_id
        if api_fid is None and fixture_id is not None:
            fx = db.get(Fixture, int(fixture_id))
            if fx is None:
                return {"status": "error", "message": f"Fixture {fixture_id} non trovata"}
            if not fx.api_fixture_id:
                return {
                    "status": "error",
                    "message": f"Fixture {fixture_id} senza api_fixture_id",
                }
            api_fid = int(fx.api_fixture_id)
        if api_fid is None:
            return {
                "status": "error",
                "message": "Specificare fixture_id o provider_fixture_id",
            }

        wanted_ids = bookmaker_ids if bookmaker_ids else _DEFAULT_BOOKMAKER_IDS
        bookmakers_out: list[dict[str, Any]] = []
        detected_over: list[dict[str, Any]] = []
        errors: list[str] = []

        for bid in wanted_ids:
            name = _BOOKMAKER_NAMES.get(int(bid), f"Bookmaker {bid}")
            try:
                raw_items = self._client.get_fixture_odds(int(api_fid), int(bid))
            except ApiFootballError as exc:
                errors.append(f"{name} ({bid}): {exc}")
                bookmakers_out.append(
                    {
                        "bookmaker_id": int(bid),
                        "bookmaker_name": name,
                        "markets": [],
                        "error": str(exc),
                    },
                )
                continue

            markets: list[dict[str, Any]] = []
            for bet in _extract_bets(raw_items):
                bet_name = str(bet.get("name") or "")
                raw_value_labels = [
                    str(v.get("value") or "")
                    for v in (bet.get("values") or [])
                    if isinstance(v, dict)
                ]
                normalized = normalize_api_football_market(bet_name, raw_value_labels)
                values_out: list[dict[str, Any]] = []
                for val in bet.get("values") or []:
                    if not isinstance(val, dict):
                        continue
                    raw_value = str(val.get("value") or "")
                    odd = _parse_odd(val.get("odd"))
                    sel_norm = normalize_over_under_selection(raw_value)
                    values_out.append(
                        {
                            "raw_value": raw_value,
                            "odd": odd,
                            "normalized_selection": sel_norm,
                        },
                    )
                    if sel_norm in (SEL_OVER_1_5, SEL_OVER_2_5) and odd is not None:
                        detected_over.append(
                            {
                                "bookmaker_id": int(bid),
                                "bookmaker_name": name,
                                "raw_market_name": bet_name,
                                "provider_market_id": str(bet.get("id") or ""),
                                "raw_value": raw_value,
                                "normalized_selection": sel_norm,
                                "odd": odd,
                            },
                        )
                markets.append(
                    {
                        "provider_market_id": str(bet.get("id") or ""),
                        "raw_market_name": bet_name,
                        "normalized_market": normalized,
                        "values": values_out,
                    },
                )

            bookmakers_out.append(
                {
                    "bookmaker_id": int(bid),
                    "bookmaker_name": name,
                    "markets": markets,
                },
            )

        return {
            "status": "ok" if not errors or bookmakers_out else "error",
            "provider_source": provider_source,
            "provider_fixture_id": int(api_fid),
            "fixture_id": internal_fixture_id,
            "bookmakers": bookmakers_out,
            "detected_over_candidates": detected_over,
            "errors": errors,
        }
