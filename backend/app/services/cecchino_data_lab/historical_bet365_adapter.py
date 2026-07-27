"""Adapter quote Bet365 per replay storico Cecchino Lab (isolato dal Today/Betfair)."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from decimal import Decimal
from typing import Any

from app.services.cecchino.cecchino_selection_keys import (
    MARKET_1X2,
    MARKET_DC,
    MARKET_OU,
    SEL_AWAY,
    SEL_DRAW,
    SEL_HOME,
    SEL_ONE_TWO,
    SEL_ONE_X,
    SEL_OVER_2_5,
    SEL_UNDER_2_5,
    SEL_X_TWO,
)
from app.services.cecchino_data_lab.constants import (
    HISTORICAL_DERIVATION_METHOD,
    HISTORICAL_QUOTE_POLICY_VERSION,
)

PROVIDER = "Bet365"
PROVIDER_SOURCE = "football-data.co.uk CSV"

SOURCE_CLOSING = "bet365_closing"
SOURCE_PRE_FALLBACK = "bet365_pre_fallback"
SOURCE_DERIVED_CLOSING = "derived_from_bet365_1x2_closing"
SOURCE_DERIVED_PRE = "derived_from_bet365_1x2_pre"
SOURCE_NOT_AVAILABLE = "not_available"

# Mercati con quota book reale da CSV Bet365 (trio/coppia completa).
REAL_BOOK_MARKETS = frozenset({SEL_HOME, SEL_DRAW, SEL_AWAY, SEL_OVER_2_5, SEL_UNDER_2_5})
# Mercati derivabili da 1X2 fair normalizzato.
DERIVABLE_MARKETS = frozenset({SEL_ONE_X, SEL_X_TWO, SEL_ONE_TWO})
# Mercati panel senza quota book storica derivabile.
NON_DERIVABLE_MARKETS = frozenset(
    {
        "DRAW_PT",
        "OVER_1_5",
        "UNDER_3_5",
        "UNDER_PT_1_5",
        "OVER_PT_0_5",
        "OVER_PT_1_5",
    }
)


@dataclass
class QuoteValue:
    value: float | None
    source_type: str
    provider: str = PROVIDER
    source_columns: list[str] = field(default_factory=list)
    is_real_book_quote: bool = False
    is_derived: bool = False
    derivation_method: str | None = None
    family_snapshot_type: str | None = None  # closing | pre | None
    warnings: list[str] = field(default_factory=list)
    prob_raw: float | None = None
    prob_fair: float | None = None
    overround: float | None = None
    source_trio_type: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _num(v: Any) -> float | None:
    if v is None:
        return None
    if isinstance(v, Decimal):
        v = float(v)
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if f != f or f <= 1.0:  # NaN or invalid odds
        return None
    return f


def _valid_trio(h: float | None, d: float | None, a: float | None) -> bool:
    return h is not None and d is not None and a is not None


def _valid_pair(o: float | None, u: float | None) -> bool:
    return o is not None and u is not None


def _normalize_1x2(
    h: float, d: float, a: float
) -> tuple[dict[str, float], dict[str, float], float]:
    raw = {"HOME": 1.0 / h, "DRAW": 1.0 / d, "AWAY": 1.0 / a}
    overround = sum(raw.values())
    fair = {k: v / overround for k, v in raw.items()} if overround > 0 else raw
    return raw, fair, overround


def _quote(
    *,
    value: float | None,
    source_type: str,
    source_columns: list[str] | None = None,
    is_real: bool = False,
    is_derived: bool = False,
    derivation_method: str | None = None,
    family_snapshot_type: str | None = None,
    warnings: list[str] | None = None,
    prob_raw: float | None = None,
    prob_fair: float | None = None,
    overround: float | None = None,
    source_trio_type: str | None = None,
) -> QuoteValue:
    return QuoteValue(
        value=round(value, 3) if value is not None else None,
        source_type=source_type,
        source_columns=list(source_columns or []),
        is_real_book_quote=is_real,
        is_derived=is_derived,
        derivation_method=derivation_method,
        family_snapshot_type=family_snapshot_type,
        warnings=list(warnings or []),
        prob_raw=round(prob_raw, 6) if prob_raw is not None else None,
        prob_fair=round(prob_fair, 6) if prob_fair is not None else None,
        overround=round(overround, 6) if overround is not None else None,
        source_trio_type=source_trio_type,
    )


def _na(reason: str = "incomplete_family") -> QuoteValue:
    return _quote(value=None, source_type=SOURCE_NOT_AVAILABLE, warnings=[reason])


def select_1x2_family(match: Any) -> dict[str, Any]:
    """Seleziona trio closing o pre senza mix; deriva DC fair."""
    ch = _num(getattr(match, "bet365_closing_home", None))
    cd = _num(getattr(match, "bet365_closing_draw", None))
    ca = _num(getattr(match, "bet365_closing_away", None))
    ph = _num(getattr(match, "bet365_home", None))
    pd = _num(getattr(match, "bet365_draw", None))
    pa = _num(getattr(match, "bet365_away", None))

    if _valid_trio(ch, cd, ca):
        assert ch is not None and cd is not None and ca is not None
        snap = "closing"
        src = SOURCE_CLOSING
        cols = {"HOME": ["B365CH"], "DRAW": ["B365CD"], "AWAY": ["B365CA"]}
        trio = (ch, cd, ca)
        derived_src = SOURCE_DERIVED_CLOSING
    elif _valid_trio(ph, pd, pa):
        assert ph is not None and pd is not None and pa is not None
        snap = "pre"
        src = SOURCE_PRE_FALLBACK
        cols = {"HOME": ["B365H"], "DRAW": ["B365D"], "AWAY": ["B365A"]}
        trio = (ph, pd, pa)
        derived_src = SOURCE_DERIVED_PRE
    else:
        return {
            "available": False,
            "family_snapshot_type": None,
            "quotes": {
                SEL_HOME: _na(),
                SEL_DRAW: _na(),
                SEL_AWAY: _na(),
                SEL_ONE_X: _na("no_complete_1x2_trio"),
                SEL_X_TWO: _na("no_complete_1x2_trio"),
                SEL_ONE_TWO: _na("no_complete_1x2_trio"),
            },
            "raw_probs": None,
            "fair_probs": None,
            "overround": None,
        }

    h, d, a = trio
    raw, fair, overround = _normalize_1x2(h, d, a)
    quotes = {
        SEL_HOME: _quote(
            value=h,
            source_type=src,
            source_columns=cols["HOME"],
            is_real=True,
            family_snapshot_type=snap,
            prob_raw=raw["HOME"],
            prob_fair=fair["HOME"],
            overround=overround,
            source_trio_type=snap,
        ),
        SEL_DRAW: _quote(
            value=d,
            source_type=src,
            source_columns=cols["DRAW"],
            is_real=True,
            family_snapshot_type=snap,
            prob_raw=raw["DRAW"],
            prob_fair=fair["DRAW"],
            overround=overround,
            source_trio_type=snap,
        ),
        SEL_AWAY: _quote(
            value=a,
            source_type=src,
            source_columns=cols["AWAY"],
            is_real=True,
            family_snapshot_type=snap,
            prob_raw=raw["AWAY"],
            prob_fair=fair["AWAY"],
            overround=overround,
            source_trio_type=snap,
        ),
    }

    p_1x = fair["HOME"] + fair["DRAW"]
    p_x2 = fair["DRAW"] + fair["AWAY"]
    p_12 = fair["HOME"] + fair["AWAY"]
    dc_map = {
        SEL_ONE_X: (p_1x, ["B365CH", "B365CD"] if snap == "closing" else ["B365H", "B365D"]),
        SEL_X_TWO: (p_x2, ["B365CD", "B365CA"] if snap == "closing" else ["B365D", "B365A"]),
        SEL_ONE_TWO: (p_12, ["B365CH", "B365CA"] if snap == "closing" else ["B365H", "B365A"]),
    }
    for sk, (p_fair, scol) in dc_map.items():
        q = (1.0 / p_fair) if p_fair > 0 else None
        quotes[sk] = _quote(
            value=q,
            source_type=derived_src,
            source_columns=scol,
            is_real=False,
            is_derived=True,
            derivation_method=HISTORICAL_DERIVATION_METHOD,
            family_snapshot_type=snap,
            prob_raw=None,
            prob_fair=p_fair,
            overround=overround,
            source_trio_type=snap,
        )

    return {
        "available": True,
        "family_snapshot_type": snap,
        "quotes": quotes,
        "raw_probs": raw,
        "fair_probs": fair,
        "overround": overround,
    }


def select_ou25_family(match: Any) -> dict[str, Any]:
    """Seleziona coppia O/U 2.5 closing o pre senza mix."""
    co = _num(getattr(match, "bet365_closing_over_25", None))
    cu = _num(getattr(match, "bet365_closing_under_25", None))
    po = _num(getattr(match, "bet365_over_25", None))
    pu = _num(getattr(match, "bet365_under_25", None))

    if _valid_pair(co, cu):
        assert co is not None and cu is not None
        snap, src = "closing", SOURCE_CLOSING
        over, under = co, cu
        cols_o, cols_u = ["B365C>2.5"], ["B365C<2.5"]
    elif _valid_pair(po, pu):
        assert po is not None and pu is not None
        snap, src = "pre", SOURCE_PRE_FALLBACK
        over, under = po, pu
        cols_o, cols_u = ["B365>2.5"], ["B365<2.5"]
    else:
        return {
            "available": False,
            "family_snapshot_type": None,
            "quotes": {SEL_OVER_2_5: _na(), SEL_UNDER_2_5: _na()},
            "raw_probs": None,
            "fair_probs": None,
            "overround": None,
        }

    raw_o, raw_u = 1.0 / over, 1.0 / under
    overround = raw_o + raw_u
    fair_o = raw_o / overround if overround > 0 else raw_o
    fair_u = raw_u / overround if overround > 0 else raw_u

    return {
        "available": True,
        "family_snapshot_type": snap,
        "quotes": {
            SEL_OVER_2_5: _quote(
                value=over,
                source_type=src,
                source_columns=cols_o,
                is_real=True,
                family_snapshot_type=snap,
                prob_raw=raw_o,
                prob_fair=fair_o,
                overround=overround,
                source_trio_type=snap,
            ),
            SEL_UNDER_2_5: _quote(
                value=under,
                source_type=src,
                source_columns=cols_u,
                is_real=True,
                family_snapshot_type=snap,
                prob_raw=raw_u,
                prob_fair=fair_u,
                overround=overround,
                source_trio_type=snap,
            ),
        },
        "raw_probs": {"OVER_2_5": raw_o, "UNDER_2_5": raw_u},
        "fair_probs": {"OVER_2_5": fair_o, "UNDER_2_5": fair_u},
        "overround": overround,
    }


def build_match_quote_bundle(match: Any) -> dict[str, Any]:
    """Bundle completo quote Bet365 per una partita Lab."""
    fam_1x2 = select_1x2_family(match)
    fam_ou = select_ou25_family(match)
    quotes: dict[str, QuoteValue] = {}
    quotes.update(fam_1x2["quotes"])
    quotes.update(fam_ou["quotes"])

    for mk in NON_DERIVABLE_MARKETS:
        quotes[mk] = _na("not_derivable_from_bet365_csv")

    real_n = sum(1 for q in quotes.values() if q.is_real_book_quote)
    derived_n = sum(1 for q in quotes.values() if q.is_derived)
    unavailable_n = sum(1 for q in quotes.values() if q.value is None)

    return {
        "quote_policy_version": HISTORICAL_QUOTE_POLICY_VERSION,
        "provider": PROVIDER,
        "provider_source": PROVIDER_SOURCE,
        "family_1x2": {
            "available": fam_1x2["available"],
            "family_snapshot_type": fam_1x2["family_snapshot_type"],
            "overround": fam_1x2["overround"],
            "raw_probs": fam_1x2["raw_probs"],
            "fair_probs": fam_1x2["fair_probs"],
        },
        "family_ou25": {
            "available": fam_ou["available"],
            "family_snapshot_type": fam_ou["family_snapshot_type"],
            "overround": fam_ou["overround"],
            "raw_probs": fam_ou["raw_probs"],
            "fair_probs": fam_ou["fair_probs"],
        },
        "quotes": {k: v.to_dict() for k, v in quotes.items()},
        "counts": {
            "real_quote_markets_count": real_n,
            "derived_quote_markets_count": derived_n,
            "unavailable_quote_markets_count": unavailable_n,
        },
        "kpi_1x2_real_available": fam_1x2["available"],
        "kpi_ou25_real_available": fam_ou["available"],
    }


def build_kpi_compatible_payload(quote_bundle: dict[str, Any]) -> dict[str, Any]:
    """Payload shape-compatibile con build_cecchino_kpi_panel_v2_betfair (solo Lab)."""
    quotes = quote_bundle.get("quotes") or {}
    fam_1x2_ok = bool(quote_bundle.get("kpi_1x2_real_available"))
    fam_ou_ok = bool(quote_bundle.get("kpi_ou25_real_available"))

    markets: dict[str, dict[str, float]] = {}
    provenance: dict[str, dict[str, Any]] = {}
    dc_derived: dict[str, bool] = {}
    warnings: list[str] = []

    if fam_1x2_ok:
        m1: dict[str, float] = {}
        for sk in (SEL_HOME, SEL_DRAW, SEL_AWAY):
            q = quotes.get(sk) or {}
            if q.get("value") is not None:
                m1[sk] = float(q["value"])
                provenance[sk] = {
                    "source": q.get("source_type"),
                    "raw_market_name": "Bet365 1X2",
                    "selection_key": sk,
                }
        markets[MARKET_1X2] = m1

        dc: dict[str, float] = {}
        for sk in (SEL_ONE_X, SEL_X_TWO, SEL_ONE_TWO):
            q = quotes.get(sk) or {}
            if q.get("value") is not None:
                dc[sk] = float(q["value"])
                dc_derived[sk] = True
                provenance[sk] = {
                    "source": q.get("source_type"),
                    "derived_formula": HISTORICAL_DERIVATION_METHOD,
                    "selection_key": sk,
                }
        markets[MARKET_DC] = dc
    else:
        warnings.append("Bet365 1X2 family incomplete")

    if fam_ou_ok:
        ou: dict[str, float] = {}
        for sk in (SEL_OVER_2_5, SEL_UNDER_2_5):
            q = quotes.get(sk) or {}
            if q.get("value") is not None:
                ou[sk] = float(q["value"])
                provenance[sk] = {
                    "source": q.get("source_type"),
                    "raw_market_name": "Bet365 O/U 2.5",
                    "selection_key": sk,
                }
        markets[MARKET_OU] = ou
    else:
        warnings.append("Bet365 O/U 2.5 family incomplete")

    status = "available" if fam_1x2_ok else ("partial" if fam_ou_ok else "not_available")

    return {
        "provider_source": PROVIDER_SOURCE,
        "bookmakers": [
            {
                "bookmaker_name": PROVIDER,
                "provider_bookmaker_id": 0,
                "status": "available" if markets else "not_available",
                "markets": markets,
                "dc_derived": dc_derived,
                "provenance_by_selection": provenance,
            }
        ],
        "status": status,
        "warnings": warnings,
        "odds_source": "bet365_historical_csv",
        "provenance_by_selection": provenance,
        "historical_only": True,
        "quote_policy_version": HISTORICAL_QUOTE_POLICY_VERSION,
    }
