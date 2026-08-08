"""Gate quote bookmaker Cecchino Today — Book canonico (Betfair → Bet365)."""

from __future__ import annotations

from typing import Any

from app.services.cecchino.cecchino_canonical_book_payload import build_single_bookmaker_payload
from app.services.cecchino.cecchino_canonical_book_resolver import (
    GATE_1X2_KEYS,
    resolve_selection_book_odd,
)
from app.services.cecchino.cecchino_constants import (
    CECCHINO_BOOK_POLICY_VERSION,
    CECCHINO_FALLBACK_BOOKMAKER,
    CECCHINO_PRIMARY_BOOKMAKER,
)
from app.services.cecchino.cecchino_selection_keys import MARKET_1X2, SEL_AWAY, SEL_DRAW, SEL_HOME

_PRIMARY_ID = int(CECCHINO_PRIMARY_BOOKMAKER["provider_bookmaker_id"])
_FALLBACK_ID = int(CECCHINO_FALLBACK_BOOKMAKER["provider_bookmaker_id"])
_PRIMARY_NAME = str(CECCHINO_PRIMARY_BOOKMAKER["name"])
_FALLBACK_NAME = str(CECCHINO_FALLBACK_BOOKMAKER["name"])


def _raw_for(odds_by_bookmaker: dict[int, list[dict[str, Any]]], bid: int) -> list[dict[str, Any]]:
    raw = odds_by_bookmaker.get(bid)
    return list(raw) if raw else []


def _selection_odd_present(markets: dict[str, Any] | None, selection_key: str) -> bool:
    if not markets:
        return False
    m1 = markets.get(MARKET_1X2) or {}
    return m1.get(selection_key) is not None


def verify_complete_1x2_odds(
    odds_by_bookmaker: dict[int, list[dict[str, Any]]],
) -> tuple[bool, dict[str, Any], str | None, list[str]]:
    """
    Verifica 1X2 canonico completo (HOME/DRAW/AWAY) dopo Betfair primary + Bet365 fallback.
    Ritorna (ok, snapshot, reason_code, blocking_reasons).
    """
    blocking_reasons: list[str] = []
    book_snapshots: dict[str, dict[str, float | None]] = {}
    attempts: dict[str, dict[str, Any]] = {}

    primary_raw = _raw_for(odds_by_bookmaker, _PRIMARY_ID)
    fallback_raw = _raw_for(odds_by_bookmaker, _FALLBACK_ID)

    primary_bm = build_single_bookmaker_payload(primary_raw, CECCHINO_PRIMARY_BOOKMAKER)
    fallback_bm = build_single_bookmaker_payload(fallback_raw, CECCHINO_FALLBACK_BOOKMAKER)

    primary_markets = primary_bm.get("markets") or {}
    fallback_markets = fallback_bm.get("markets") or {}
    primary_prov = primary_bm.get("provenance_by_selection") or {}
    fallback_prov = fallback_bm.get("provenance_by_selection") or {}

    for name, markets in ((_PRIMARY_NAME, primary_markets), (_FALLBACK_NAME, fallback_markets)):
        m1 = (markets or {}).get(MARKET_1X2) or {}
        if m1:
            book_snapshots[name] = {
                "HOME": m1.get(SEL_HOME),
                "DRAW": m1.get(SEL_DRAW),
                "AWAY": m1.get(SEL_AWAY),
            }

    if not primary_raw and not fallback_raw:
        blocking_reasons.append(f"missing_bookmaker:{_PRIMARY_NAME}")
        return (
            False,
            {
                "bookmakers": book_snapshots,
                "missing": [_PRIMARY_NAME],
                "book_policy_version": CECCHINO_BOOK_POLICY_VERSION,
                "attempts": attempts,
            },
            "missing_bookmaker",
            blocking_reasons,
        )

    canonical: dict[str, float] = {}
    selection_sources: dict[str, str] = {}
    selection_provenance: dict[str, dict[str, Any]] = {}

    for sk in GATE_1X2_KEYS:
        odd, prov = resolve_selection_book_odd(
            selection_key=sk,
            primary_markets=primary_markets,
            primary_provenance=primary_prov,
            fallback_markets=fallback_markets,
            fallback_provenance=fallback_prov,
        )
        primary_present = _selection_odd_present(primary_markets, sk)
        fallback_present = _selection_odd_present(fallback_markets, sk)
        attempts[sk] = {
            "primary_present": primary_present,
            "fallback_present": fallback_present,
            "resolved": odd is not None,
            "bookmaker_name": (prov or {}).get("bookmaker_name"),
            "book_fallback_used": (prov or {}).get("book_fallback_used"),
        }
        if odd is None:
            blocking_reasons.append(f"missing_selection:canonical:{sk}")
            if not primary_present:
                blocking_reasons.append(f"missing_selection:{_PRIMARY_NAME}:{sk}")
            if fallback_raw and not fallback_present:
                blocking_reasons.append(f"missing_selection:{_FALLBACK_NAME}:{sk}")
            continue
        canonical[sk] = odd
        selection_sources[sk] = str((prov or {}).get("bookmaker_name") or "Book")
        if prov:
            selection_provenance[sk] = prov

    if len(canonical) < 3:
        if not primary_raw and not any(
            _selection_odd_present(fallback_markets, sk) for sk in GATE_1X2_KEYS
        ):
            reason = "missing_bookmaker"
            if f"missing_bookmaker:{_PRIMARY_NAME}" not in blocking_reasons:
                blocking_reasons.insert(0, f"missing_bookmaker:{_PRIMARY_NAME}")
        else:
            reason = "missing_1x2_market"
            if not any(b.startswith("missing_1x2:") for b in blocking_reasons):
                blocking_reasons.insert(0, "missing_1x2:canonical")
        return (
            False,
            {
                "bookmakers": book_snapshots,
                "missing": [k for k in GATE_1X2_KEYS if k not in canonical],
                "selection_sources": selection_sources,
                "book_policy_version": CECCHINO_BOOK_POLICY_VERSION,
                "attempts": attempts,
                "raw_by_bookmaker_id": {str(k): v for k, v in odds_by_bookmaker.items()},
            },
            reason,
            blocking_reasons,
        )

    # Canonical = 1X2 risolto (Betfair → Bet365). Betfair/Bet365 restano
    # esclusivamente quote del rispettivo book (mai mescolate).
    book_snapshots["Canonical"] = {
        "HOME": canonical[SEL_HOME],
        "DRAW": canonical[SEL_DRAW],
        "AWAY": canonical[SEL_AWAY],
    }

    snapshot = {
        "bookmakers": book_snapshots,
        "status": "available",
        "raw_by_bookmaker_id": {str(k): v for k, v in odds_by_bookmaker.items()},
        "selection_sources": selection_sources,
        "selection_provenance": selection_provenance,
        "book_policy_version": CECCHINO_BOOK_POLICY_VERSION,
        "attempts": attempts,
    }
    return True, snapshot, None, []
