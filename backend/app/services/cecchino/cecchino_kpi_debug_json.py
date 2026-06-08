"""Builder JSON debug KPI Betfair per fixture Cecchino Today."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models.cecchino_today_fixture import ELIGIBILITY_ELIGIBLE, CecchinoTodayFixture
from app.services.cecchino.cecchino_betfair_odds_mapping import (
    is_strict_double_chance_market,
    is_strict_match_winner_market,
)
from app.services.cecchino.cecchino_betfair_odds_payload import (
    build_betfair_payload_from_snapshot,
)
from app.services.cecchino.cecchino_constants import CECCHINO_BOOKMAKER, PROVIDER_API_FOOTBALL
from app.services.cecchino.cecchino_selection_keys import (
    SEL_AWAY,
    SEL_DRAW,
    SEL_HOME,
    SEL_ONE_TWO,
    SEL_ONE_X,
    SEL_OVER_1_5,
    SEL_OVER_2_5,
    SEL_OVER_PT_0_5,
    SEL_OVER_PT_1_5,
    SEL_UNDER_2_5,
    SEL_UNDER_3_5,
    SEL_UNDER_PT_1_5,
    SEL_X_TWO,
)

_BETFAIR_ID = int(CECCHINO_BOOKMAKER["provider_bookmaker_id"])

_DEBUG_SELECTIONS = (
    SEL_HOME,
    SEL_DRAW,
    SEL_AWAY,
    SEL_ONE_X,
    SEL_X_TWO,
    SEL_ONE_TWO,
    SEL_OVER_1_5,
    SEL_OVER_2_5,
    SEL_UNDER_2_5,
    SEL_UNDER_3_5,
    SEL_UNDER_PT_1_5,
    SEL_OVER_PT_0_5,
    SEL_OVER_PT_1_5,
)


def _empty_odds_entry() -> dict[str, Any]:
    return {
        "quota_book": None,
        "source": None,
        "raw_market_name": None,
        "bet_id": None,
        "raw_value": None,
        "selection_key": None,
    }


def _extract_raw_markets_used(snapshot: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not snapshot:
        return []
    raw_map = snapshot.get("raw_by_bookmaker_id") or {}
    raw = raw_map.get(str(_BETFAIR_ID)) or raw_map.get(_BETFAIR_ID) or []
    markets_out: list[dict[str, Any]] = []
    seen: set[str] = set()

    for item in raw:
        for bm in item.get("bookmakers") or []:
            for bet in bm.get("bets") or []:
                if not isinstance(bet, dict):
                    continue
                bet_name = str(bet.get("name") or "")
                bet_id = bet.get("id")
                if not (
                    is_strict_match_winner_market(bet_name, bet_id)
                    or is_strict_double_chance_market(bet_name)
                    or bet_name in ("Goals Over/Under", "Goals Over/Under First Half", "Goals Over/Under - First Half")
                ):
                    continue
                key = f"{bet_name}:{bet_id}"
                if key in seen:
                    continue
                seen.add(key)
                values = [
                    {"value": v.get("value"), "odd": v.get("odd")}
                    for v in (bet.get("values") or [])
                    if isinstance(v, dict)
                ]
                markets_out.append(
                    {
                        "raw_market_name": bet_name,
                        "bet_id": bet_id,
                        "values": values,
                    },
                )
    return markets_out


def _cecchino_odds_used(output: dict[str, Any]) -> dict[str, Any]:
    final = output.get("final") or {}
    if final.get("status") != "available":
        return {}
    p1 = final.get("prob_1")
    px = final.get("prob_x")
    p2 = final.get("prob_2")
    out: dict[str, Any] = {
        "HOME": final.get("quota_1"),
        "DRAW": final.get("quota_x"),
        "AWAY": final.get("quota_2"),
    }
    if p1 and px and (p1 + px) > 0:
        out["ONE_X"] = round(1 / (p1 + px), 2)
    if px and p2 and (px + p2) > 0:
        out["X_TWO"] = round(1 / (px + p2), 2)
    if p1 and p2 and (p1 + p2) > 0:
        out["ONE_TWO"] = round(1 / (p1 + p2), 2)
    return out


def build_kpi_debug_json(row: CecchinoTodayFixture, db: Session) -> dict[str, Any]:
    from app.services.cecchino.cecchino_today_service import _resolve_kpi_panel_for_detail

    kpi_panel = _resolve_kpi_panel_for_detail(row, db)
    betfair_payload = build_betfair_payload_from_snapshot(
        row.odds_snapshot_json,
        source="cached_betfair_odds",
        home_team_name=row.home_team_name,
        away_team_name=row.away_team_name,
    )
    provenance = betfair_payload.get("provenance_by_selection") or {}
    kpi_by_key = {r["market_key"]: r for r in (kpi_panel or {}).get("rows") or [] if isinstance(r, dict)}

    betfair_odds_used: dict[str, Any] = {}
    for sk in _DEBUG_SELECTIONS:
        entry = _empty_odds_entry()
        entry["selection_key"] = sk
        kpi_row = kpi_by_key.get(sk) or {}
        prov = provenance.get(sk) or {}
        entry["quota_book"] = kpi_row.get("quota_book")
        entry["source"] = kpi_row.get("book_source") or prov.get("source")
        entry["raw_market_name"] = prov.get("raw_market_name")
        entry["bet_id"] = prov.get("bet_id")
        entry["raw_value"] = prov.get("raw_value")
        if prov.get("derived_formula"):
            entry["derived_formula"] = prov.get("derived_formula")
        betfair_odds_used[sk] = entry

    output = row.cecchino_output_json or {}
    warnings = list(betfair_payload.get("warnings") or [])
    warnings.extend((kpi_panel or {}).get("warnings") or [])

    return {
        "fixture": {
            "today_fixture_id": int(row.id),
            "local_fixture_id": int(row.local_fixture_id) if row.local_fixture_id else None,
            "provider_fixture_id": int(row.provider_fixture_id),
            "home_team": row.home_team_name,
            "away_team": row.away_team_name,
            "kickoff": row.kickoff.isoformat() if row.kickoff else None,
        },
        "bookmaker": {
            "provider_source": PROVIDER_API_FOOTBALL,
            "provider_bookmaker_id": _BETFAIR_ID,
            "name": CECCHINO_BOOKMAKER["name"],
        },
        "kpi_panel": kpi_panel,
        "betfair_odds_used": betfair_odds_used,
        "cecchino_odds_used": _cecchino_odds_used(output if isinstance(output, dict) else {}),
        "raw_betfair_markets_used": _extract_raw_markets_used(row.odds_snapshot_json),
        "warnings": warnings,
    }


def get_kpi_debug_json(db: Session, today_fixture_id: int) -> dict[str, Any] | None:
    row = db.get(CecchinoTodayFixture, today_fixture_id)
    if row is None:
        return None
    if row.eligibility_status != ELIGIBILITY_ELIGIBLE:
        return {
            "status": "error",
            "code": "not_eligible",
            "message": "Fixture non eleggibile",
        }
    return {
        "status": "ok",
        **build_kpi_debug_json(row, db),
    }
