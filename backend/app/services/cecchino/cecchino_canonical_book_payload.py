"""Payload Book canonico Cecchino (Betfair primary → Bet365 fallback)."""

from __future__ import annotations

from typing import Any

from app.services.cecchino.cecchino_api_football_odds import parse_api_football_odds_response
from app.services.cecchino.cecchino_betfair_odds_mapping import (
    parsed_rows_to_markets_and_provenance,
    provenance_source_for,
    validate_betfair_kpi_odds_mapping,
)
from app.services.cecchino.cecchino_bookmaker_derive import derive_double_chance_from_1x2
from app.services.cecchino.cecchino_canonical_book_resolver import (
    GATE_1X2_KEYS,
    resolve_canonical_markets,
    selection_odd_from_markets,
)
from app.services.cecchino.cecchino_constants import (
    CECCHINO_BOOK_POLICY_VERSION,
    CECCHINO_FALLBACK_BOOKMAKER,
    CECCHINO_PRIMARY_BOOKMAKER,
    PROVIDER_API_FOOTBALL,
)
from app.services.cecchino.cecchino_selection_keys import (
    MARKET_1X2,
    MARKET_1X2_FH,
    MARKET_DC,
    MARKET_OU,
    MARKET_OU_FH,
    SEL_AWAY,
    SEL_DRAW,
    SEL_HOME,
    SEL_ONE_TWO,
    SEL_ONE_X,
    SEL_X_TWO,
)

_WANTED_MARKETS = [MARKET_1X2, MARKET_1X2_FH, MARKET_DC, MARKET_OU, MARKET_OU_FH]

_PRIMARY_ID = int(CECCHINO_PRIMARY_BOOKMAKER["provider_bookmaker_id"])
_FALLBACK_ID = int(CECCHINO_FALLBACK_BOOKMAKER["provider_bookmaker_id"])


def _build_markets_from_parsed(
    markets_raw: dict[str, dict[str, float]],
    provenance: dict[str, dict[str, Any]],
    *,
    bookmaker_slug: str,
) -> tuple[dict[str, Any], dict[str, bool], str, dict[str, dict[str, Any]]]:
    """
    Costruisce markets per un singolo bookmaker.
    DC: raw se presente, altrimenti derived da 1X2 dello stesso book.
    Nota: anche con 1X2 parziale si espongono le selection presenti (per fallback selection-by-selection).
    """
    m1 = markets_raw.get(MARKET_1X2, {})
    home = m1.get(SEL_HOME)
    draw = m1.get(SEL_DRAW)
    away = m1.get(SEL_AWAY)

    has_any_1x2 = any(x is not None for x in (home, draw, away))
    complete_1x2 = home is not None and draw is not None and away is not None

    if not has_any_1x2 and not markets_raw:
        return {}, {}, "not_available", provenance

    dc_derived: dict[str, bool] = {}
    dc_out: dict[str, float | None] = {}
    prov_out = dict(provenance)
    dc_raw = markets_raw.get(MARKET_DC, {})
    derived: dict[str, float | None] = {}
    if complete_1x2:
        derived = derive_double_chance_from_1x2(home, draw, away)  # type: ignore[arg-type]

    for sk in (SEL_ONE_X, SEL_X_TWO, SEL_ONE_TWO):
        raw_val = dc_raw.get(sk)
        if raw_val is not None:
            dc_out[sk] = raw_val
            dc_derived[sk] = False
        elif complete_1x2:
            dc_out[sk] = derived.get(sk)
            dc_derived[sk] = True
            if derived.get(sk) is not None:
                prov_out[sk] = {
                    "raw_market_name": "Match Winner",
                    "bet_id": None,
                    "raw_value": None,
                    "selection_key": sk,
                    "source": provenance_source_for(bookmaker_slug, "derived_dc"),
                    "derived_formula": "1/(prob_sum) from 1X2",
                }

    markets: dict[str, Any] = {}
    if has_any_1x2:
        block: dict[str, float] = {}
        if home is not None:
            block[SEL_HOME] = home
        if draw is not None:
            block[SEL_DRAW] = draw
        if away is not None:
            block[SEL_AWAY] = away
        markets[MARKET_1X2] = block

    if dc_out:
        markets[MARKET_DC] = dc_out

    ou = markets_raw.get(MARKET_OU, {})
    if ou:
        markets[MARKET_OU] = dict(ou)
    ou_fh = markets_raw.get(MARKET_OU_FH, {})
    if ou_fh:
        markets[MARKET_OU_FH] = dict(ou_fh)
    fh_1x2 = markets_raw.get(MARKET_1X2_FH, {})
    if fh_1x2:
        markets[MARKET_1X2_FH] = dict(fh_1x2)

    if complete_1x2:
        status = "available"
    elif markets:
        status = "partial"
    else:
        status = "not_available"

    return markets, dc_derived, status, prov_out


def build_single_bookmaker_payload(
    raw: list[dict[str, Any]] | None,
    bookmaker: dict[str, str | int],
    *,
    home_team_name: str | None = None,
    away_team_name: str | None = None,
) -> dict[str, Any]:
    """Normalizza un singolo bookmaker (stesse regole strict KPI)."""
    slug = str(bookmaker.get("slug") or str(bookmaker.get("name") or "book").lower())
    name = str(bookmaker["name"])
    bid = int(bookmaker["provider_bookmaker_id"])

    if not raw:
        return {
            "bookmaker_name": name,
            "provider_bookmaker_id": bid,
            "status": "not_available",
            "markets": {},
            "dc_derived": {},
            "provenance_by_selection": {},
            "warnings": [f"{name} raw odds mancanti"],
        }

    mapping_warnings: list[str] = []
    parsed, missing = parse_api_football_odds_response(
        raw,
        requested_markets=_WANTED_MARKETS,
        strict_kpi=True,
        bookmaker_slug=slug,
        home_team_name=home_team_name,
        away_team_name=away_team_name,
        mapping_warnings=mapping_warnings,
    )
    markets_raw, provenance = parsed_rows_to_markets_and_provenance(parsed)
    markets, dc_derived, status, provenance = _build_markets_from_parsed(
        markets_raw,
        provenance,
        bookmaker_slug=slug,
    )

    warnings: list[str] = list(mapping_warnings)
    if missing:
        warnings.append(f"mercati_mancanti:{','.join(missing)}")
    if status == "available":
        warnings.extend(validate_betfair_kpi_odds_mapping(markets, provenance, dc_derived))

    return {
        "bookmaker_name": name,
        "provider_bookmaker_id": bid,
        "status": status,
        "markets": markets,
        "dc_derived": dc_derived,
        "provenance_by_selection": provenance,
        "warnings": warnings,
    }


def _raw_for_book(
    odds_by_bookmaker: dict[int, list[dict[str, Any]]] | None,
    book_id: int,
) -> list[dict[str, Any]]:
    if not odds_by_bookmaker:
        return []
    raw = odds_by_bookmaker.get(book_id)
    if raw:
        return list(raw)
    # dual lookup string keys
    raw2 = odds_by_bookmaker.get(str(book_id))  # type: ignore[arg-type]
    return list(raw2) if raw2 else []


def build_canonical_book_payload_from_raw(
    odds_by_bookmaker: dict[int, list[dict[str, Any]]] | None,
    *,
    source: str = "book",
    home_team_name: str | None = None,
    away_team_name: str | None = None,
) -> dict[str, Any]:
    """
    Costruisce payload Book canonico da raw multi-bookmaker.
    Policy: Betfair primary → Bet365 fallback selection-by-selection.
    """
    primary = build_single_bookmaker_payload(
        _raw_for_book(odds_by_bookmaker, _PRIMARY_ID),
        CECCHINO_PRIMARY_BOOKMAKER,
        home_team_name=home_team_name,
        away_team_name=away_team_name,
    )
    fallback = build_single_bookmaker_payload(
        _raw_for_book(odds_by_bookmaker, _FALLBACK_ID),
        CECCHINO_FALLBACK_BOOKMAKER,
        home_team_name=home_team_name,
        away_team_name=away_team_name,
    )

    markets, provenance, stats = resolve_canonical_markets(
        primary_markets=primary.get("markets"),
        primary_provenance=primary.get("provenance_by_selection"),
        fallback_markets=fallback.get("markets"),
        fallback_provenance=fallback.get("provenance_by_selection"),
    )

    # Status: available se 1X2 canonico completo; partial se qualche selection; else N/D
    gate_ok = all(selection_odd_from_markets(markets, sk) is not None for sk in GATE_1X2_KEYS)
    if gate_ok:
        status = "available"
    elif markets:
        status = "partial"
    else:
        status = "not_available"

    warnings: list[str] = []
    warnings.extend(primary.get("warnings") or [])
    warnings.extend(fallback.get("warnings") or [])
    if stats.get("bet365_fallback_selection_count"):
        warnings.append(
            f"bet365_fallback_selections:{stats['bet365_fallback_selection_count']}",
        )

    dc_derived = {
        sk: bool((provenance.get(sk) or {}).get("source", "").startswith("derived_from_"))
        for sk in (SEL_ONE_X, SEL_X_TWO, SEL_ONE_TWO)
        if sk in provenance
    }

    bookmakers_list = [
        {
            "bookmaker_name": "Canonical Book",
            "provider_bookmaker_id": None,
            "status": status,
            "markets": markets,
            "dc_derived": dc_derived,
            "provenance_by_selection": provenance,
            "book_policy_version": CECCHINO_BOOK_POLICY_VERSION,
        },
        primary,
        fallback,
    ]

    return {
        "provider_source": PROVIDER_API_FOOTBALL,
        "bookmakers": bookmakers_list,
        "status": status,
        "warnings": warnings,
        "odds_source": source,
        "provenance_by_selection": provenance,
        "book_policy_version": CECCHINO_BOOK_POLICY_VERSION,
        "book_resolution_stats": stats,
        "primary_bookmaker": {
            "name": CECCHINO_PRIMARY_BOOKMAKER["name"],
            "provider_bookmaker_id": _PRIMARY_ID,
        },
        "fallback_bookmaker": {
            "name": CECCHINO_FALLBACK_BOOKMAKER["name"],
            "provider_bookmaker_id": _FALLBACK_ID,
        },
    }


def _snapshot_raw_map(odds_snapshot: dict[str, Any]) -> dict[int, list[dict[str, Any]]]:
    raw_map = odds_snapshot.get("raw_by_bookmaker_id") or {}
    out: dict[int, list[dict[str, Any]]] = {}
    for bid in (_PRIMARY_ID, _FALLBACK_ID):
        raw = raw_map.get(str(bid)) or raw_map.get(bid)
        if raw:
            out[bid] = list(raw) if isinstance(raw, list) else []
    return out


def build_canonical_book_payload_from_snapshot(
    odds_snapshot: dict[str, Any] | None,
    *,
    source: str = "cached_book_odds",
    home_team_name: str | None = None,
    away_team_name: str | None = None,
) -> dict[str, Any]:
    """Offline: usa solo raw presenti nello snapshot (nessuna API)."""
    if not odds_snapshot:
        return build_canonical_book_payload_from_raw(None, source=source)

    odds_by_book = _snapshot_raw_map(odds_snapshot)
    if odds_by_book:
        return build_canonical_book_payload_from_raw(
            odds_by_book,
            source=source,
            home_team_name=home_team_name,
            away_team_name=away_team_name,
        )

    # Fallback legacy: solo bookmakers.Betfair 1X2 nello snapshot
    books = odds_snapshot.get("bookmakers") or {}
    bf = books.get(CECCHINO_PRIMARY_BOOKMAKER["name"]) or books.get("Betfair")
    if isinstance(bf, dict) and all(bf.get(k) is not None for k in ("HOME", "DRAW", "AWAY")):
        # Ricostruisci un mini-raw sintetico via markets diretti
        primary_markets = {
            MARKET_1X2: {
                SEL_HOME: float(bf["HOME"]),
                SEL_DRAW: float(bf["DRAW"]),
                SEL_AWAY: float(bf["AWAY"]),
            },
        }
        derived = derive_double_chance_from_1x2(
            primary_markets[MARKET_1X2][SEL_HOME],
            primary_markets[MARKET_1X2][SEL_DRAW],
            primary_markets[MARKET_1X2][SEL_AWAY],
        )
        primary_markets[MARKET_DC] = derived
        slug = "betfair"
        primary_prov = {
            SEL_HOME: {"source": provenance_source_for(slug, "match_winner"), "raw_market_name": "snapshot_1x2"},
            SEL_DRAW: {"source": provenance_source_for(slug, "match_winner"), "raw_market_name": "snapshot_1x2"},
            SEL_AWAY: {"source": provenance_source_for(slug, "match_winner"), "raw_market_name": "snapshot_1x2"},
            SEL_ONE_X: {"source": provenance_source_for(slug, "derived_dc")},
            SEL_X_TWO: {"source": provenance_source_for(slug, "derived_dc")},
            SEL_ONE_TWO: {"source": provenance_source_for(slug, "derived_dc")},
        }
        markets, provenance, stats = resolve_canonical_markets(
            primary_markets=primary_markets,
            primary_provenance=primary_prov,
            fallback_markets=None,
            fallback_provenance=None,
        )
        return {
            "provider_source": PROVIDER_API_FOOTBALL,
            "bookmakers": [
                {
                    "bookmaker_name": "Canonical Book",
                    "provider_bookmaker_id": None,
                    "status": "available",
                    "markets": markets,
                    "dc_derived": {SEL_ONE_X: True, SEL_X_TWO: True, SEL_ONE_TWO: True},
                    "provenance_by_selection": provenance,
                    "book_policy_version": CECCHINO_BOOK_POLICY_VERSION,
                },
            ],
            "status": "available",
            "warnings": ["snapshot_1x2_only_no_ou"],
            "odds_source": source,
            "provenance_by_selection": provenance,
            "book_policy_version": CECCHINO_BOOK_POLICY_VERSION,
            "book_resolution_stats": stats,
            "primary_bookmaker": {
                "name": CECCHINO_PRIMARY_BOOKMAKER["name"],
                "provider_bookmaker_id": _PRIMARY_ID,
            },
            "fallback_bookmaker": {
                "name": CECCHINO_FALLBACK_BOOKMAKER["name"],
                "provider_bookmaker_id": _FALLBACK_ID,
            },
        }

    return build_canonical_book_payload_from_raw(None, source=source)
