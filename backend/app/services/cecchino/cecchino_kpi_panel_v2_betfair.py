"""Pannello KPI Cecchino Today v2 — Betfair-only con rating 0-100."""

from __future__ import annotations

from typing import Any

from app.services.cecchino.cecchino_constants import CECCHINO_BOOKMAKER, PROVIDER_API_FOOTBALL
from app.services.cecchino.cecchino_selection_keys import (
    MARKET_1X2,
    MARKET_DC,
    MARKET_OU,
    MARKET_OU_FH,
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

KPI_V2_VERSION = "cecchino_kpi_v2_betfair"

KPI_V2_COLUMNS = [
    "segno",
    "quota_book",
    "quota_cecchino",
    "prob_book",
    "prob_cecchino",
    "vantaggio_prob",
    "edge_pct",
    "score_acquisto",
    "rating",
]

KPI_V2_ROW_DEFS: tuple[tuple[str, str], ...] = (
    (SEL_HOME, "1"),
    (SEL_DRAW, "X"),
    (SEL_AWAY, "2"),
    (SEL_ONE_X, "1X"),
    (SEL_X_TWO, "X2"),
    (SEL_ONE_TWO, "12"),
    (SEL_OVER_1_5, "Over 1.5"),
    (SEL_OVER_2_5, "Over 2.5"),
    (SEL_UNDER_2_5, "Under 2.5"),
    (SEL_UNDER_3_5, "Under 3.5"),
    (SEL_UNDER_PT_1_5, "Under PT 1.5"),
    (SEL_OVER_PT_0_5, "Over PT 0.5"),
    (SEL_OVER_PT_1_5, "Over PT 1.5"),
)

_MARKET_FOR_KEY: dict[str, str] = {
    SEL_HOME: MARKET_1X2,
    SEL_DRAW: MARKET_1X2,
    SEL_AWAY: MARKET_1X2,
    SEL_ONE_X: MARKET_DC,
    SEL_X_TWO: MARKET_DC,
    SEL_ONE_TWO: MARKET_DC,
    SEL_OVER_1_5: MARKET_OU,
    SEL_OVER_2_5: MARKET_OU,
    SEL_UNDER_2_5: MARKET_OU,
    SEL_UNDER_3_5: MARKET_OU,
    SEL_UNDER_PT_1_5: MARKET_OU_FH,
    SEL_OVER_PT_0_5: MARKET_OU_FH,
    SEL_OVER_PT_1_5: MARKET_OU_FH,
}

_CECCHINO_1X2_KEYS = {SEL_HOME, SEL_DRAW, SEL_AWAY}
_CECCHINO_DC_KEYS = {SEL_ONE_X, SEL_X_TWO, SEL_ONE_TWO}


def _num(v: Any) -> float | None:
    if v is None or isinstance(v, str):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _prob_from_odd(odd: float | None) -> float | None:
    o = _num(odd)
    if o is None or o <= 0:
        return None
    return round(1.0 / o, 4)


def _edge_pct(book: float | None, cecchino: float | None) -> float | None:
    b, c = _num(book), _num(cecchino)
    if b is None or c is None or c <= 0:
        return None
    return round((b / c - 1.0) * 100.0, 2)


def rating_label(rating: int | None) -> str | None:
    if rating is None:
        return None
    if rating >= 90:
        return "Elite"
    if rating >= 80:
        return "Premium"
    if rating >= 70:
        return "Forte"
    if rating >= 60:
        return "Buona"
    if rating >= 50:
        return "Sufficiente"
    if rating >= 40:
        return "Debole"
    return "Scarto"


def _compute_rating(
    prob_cecchino: float | None,
    vantaggio_prob: float | None,
    edge_pct: float | None,
) -> int | None:
    if prob_cecchino is None or vantaggio_prob is None or edge_pct is None:
        return None
    prob_pct = prob_cecchino * 100.0
    vant_pct = vantaggio_prob * 100.0
    raw = (prob_pct * 0.5) + (vant_pct * 2.0) + edge_pct
    return int(round(max(0.0, min(100.0, raw))))


def _build_metrics_row(
    *,
    market_key: str,
    segno: str,
    quota_book: float | None,
    quota_cecchino: float | None,
    book_source: str,
    cecchino_source: str | None,
) -> dict[str, Any]:
    prob_book = _prob_from_odd(quota_book)
    prob_cecchino = _prob_from_odd(quota_cecchino)

    if quota_book is not None and quota_cecchino is None:
        return {
            "market_key": market_key,
            "segno": segno,
            "label": segno,
            "quota_book": round(quota_book, 2) if quota_book is not None else None,
            "quota_cecchino": None,
            "prob_book": prob_book,
            "prob_cecchino": None,
            "vantaggio_prob": None,
            "edge_pct": None,
            "score_acquisto": None,
            "rating": None,
            "rating_label": None,
            "status": "book_only" if quota_book is not None else "not_available",
            "book_source": book_source,
            "cecchino_source": cecchino_source,
        }

    if quota_book is None or quota_cecchino is None:
        return {
            "market_key": market_key,
            "segno": segno,
            "label": segno,
            "quota_book": round(quota_book, 2) if quota_book is not None else None,
            "quota_cecchino": round(quota_cecchino, 2) if quota_cecchino is not None else None,
            "prob_book": prob_book,
            "prob_cecchino": prob_cecchino,
            "vantaggio_prob": None,
            "edge_pct": None,
            "score_acquisto": None,
            "rating": None,
            "rating_label": None,
            "status": "not_available",
            "book_source": book_source,
            "cecchino_source": cecchino_source,
        }

    vantaggio_prob = None
    if prob_book is not None and prob_cecchino is not None:
        vantaggio_prob = round(prob_cecchino - prob_book, 4)

    edge = _edge_pct(quota_book, quota_cecchino)
    score_acquisto = None
    if prob_cecchino is not None and edge is not None:
        score_acquisto = round(prob_cecchino * edge / 100.0, 3)

    rating = _compute_rating(prob_cecchino, vantaggio_prob, edge)

    return {
        "market_key": market_key,
        "segno": segno,
        "label": segno,
        "quota_book": round(quota_book, 2),
        "quota_cecchino": round(quota_cecchino, 2),
        "prob_book": prob_book,
        "prob_cecchino": prob_cecchino,
        "vantaggio_prob": vantaggio_prob,
        "edge_pct": edge,
        "score_acquisto": score_acquisto,
        "rating": rating,
        "rating_label": rating_label(rating),
        "status": "available",
        "book_source": book_source,
        "cecchino_source": cecchino_source,
    }


def normalize_kpi_panel_rows(kpi_panel: dict[str, Any] | None) -> dict[str, Any] | None:
    """Normalizza segno/label su righe KPI v2 o legacy."""
    if not kpi_panel or not isinstance(kpi_panel, dict):
        return kpi_panel
    rows_out: list[dict[str, Any]] = []
    for raw in kpi_panel.get("rows") or []:
        if not isinstance(raw, dict):
            continue
        row = dict(raw)
        segno = row.get("segno") or row.get("label") or row.get("market_key") or ""
        row["segno"] = segno
        row["label"] = row.get("label") or segno
        rows_out.append(row)
    out = dict(kpi_panel)
    out["rows"] = rows_out
    return out


def _book_source_for_row(
    market_key: str,
    *,
    has_quota: bool,
    betfair_payload: dict[str, Any],
    odds_source: str,
) -> str:
    if not has_quota:
        return "not_available"

    provenance = betfair_payload.get("provenance_by_selection") or {}
    prov = provenance.get(market_key) or {}
    src = prov.get("source")
    if src:
        if odds_source == "cached_betfair_odds" and src.startswith("betfair_raw"):
            return f"cached_{src}"
        return str(src)

    if market_key in _CECCHINO_DC_KEYS:
        for bm in betfair_payload.get("bookmakers") or []:
            dc_derived = (bm or {}).get("dc_derived") or {}
            if dc_derived.get(market_key):
                return "derived_from_betfair_1x2"
    if market_key in _CECCHINO_1X2_KEYS:
        return "betfair_raw_match_winner"
    if market_key in (SEL_OVER_1_5, SEL_OVER_2_5, SEL_UNDER_2_5, SEL_UNDER_3_5):
        return "betfair_raw_over_under"
    if market_key in (SEL_UNDER_PT_1_5, SEL_OVER_PT_0_5, SEL_OVER_PT_1_5):
        return "betfair_raw_over_under_first_half"
    if odds_source == "cached_betfair_odds":
        return "cached_betfair_odds"
    return "betfair"


def _extract_betfair_markets(betfair_payload: dict[str, Any]) -> dict[str, dict[str, float | None]]:
    """Estrae mercati Betfair dal payload bookmaker."""
    out: dict[str, dict[str, float | None]] = {}
    for bm in betfair_payload.get("bookmakers") or []:
        if not isinstance(bm, dict):
            continue
        if bm.get("status") != "available":
            continue
        markets = bm.get("markets") or {}
        for mkt, selections in markets.items():
            if not isinstance(selections, dict):
                continue
            out.setdefault(mkt, {})
            for sk, val in selections.items():
                out[mkt][sk] = _num(val)
    return out


def _cecchino_quota_for_key(
    market_key: str,
    *,
    final_odds: dict[str, Any],
    cec_ok: bool,
    cec_dc: dict[str, float | None],
) -> tuple[float | None, str | None]:
    if not cec_ok:
        return None, None
    if market_key in _CECCHINO_1X2_KEYS:
        key_map = {SEL_HOME: "quota_1", SEL_DRAW: "quota_x", SEL_AWAY: "quota_2"}
        q = _num(final_odds.get(key_map[market_key]))
        return (round(q, 2) if q is not None else None, "final_odds" if q is not None else None)
    if market_key in _CECCHINO_DC_KEYS:
        q = cec_dc.get(market_key)
        return (round(q, 2) if q is not None else None, "derived_from_1x2" if q is not None else None)
    return None, None


def build_cecchino_kpi_panel_v2_betfair(
    *,
    final_odds: dict[str, Any],
    betfair_payload: dict[str, Any],
) -> dict[str, Any]:
    warnings: list[str] = list(betfair_payload.get("warnings") or [])
    bm_status = betfair_payload.get("status") or "not_available"
    odds_source = str(betfair_payload.get("odds_source") or "betfair")
    markets = _extract_betfair_markets(betfair_payload)

    cec_ok = final_odds.get("status") == "available"
    p1 = _num(final_odds.get("prob_1"))
    px = _num(final_odds.get("prob_x"))
    p2 = _num(final_odds.get("prob_2"))

    cec_dc: dict[str, float | None] = {
        SEL_ONE_X: round(1.0 / (p1 + px), 2) if p1 and px and (p1 + px) > 0 else None,
        SEL_X_TWO: round(1.0 / (px + p2), 2) if px and p2 and (px + p2) > 0 else None,
        SEL_ONE_TWO: round(1.0 / (p1 + p2), 2) if p1 and p2 and (p1 + p2) > 0 else None,
    }

    rows: list[dict[str, Any]] = []
    for market_key, segno in KPI_V2_ROW_DEFS:
        mkt = _MARKET_FOR_KEY[market_key]
        provenance_map = betfair_payload.get("provenance_by_selection")
        prov = (provenance_map or {}).get(market_key) or {}
        quota_book = (markets.get(mkt) or {}).get(market_key)
        book_source = _book_source_for_row(
            market_key,
            has_quota=quota_book is not None,
            betfair_payload=betfair_payload,
            odds_source=odds_source,
        )
        if quota_book is not None and book_source == "not_available":
            quota_book = None
        if (
            provenance_map is not None
            and quota_book is not None
            and market_key in _CECCHINO_1X2_KEYS
            and not prov.get("source")
        ):
            warnings.append(f"kpi_{market_key}:provenance_mancante")
            quota_book = None

        quota_cecchino, cecchino_source = _cecchino_quota_for_key(
            market_key,
            final_odds=final_odds,
            cec_ok=cec_ok,
            cec_dc=cec_dc,
        )

        rows.append(
            _build_metrics_row(
                market_key=market_key,
                segno=segno,
                quota_book=quota_book,
                quota_cecchino=quota_cecchino,
                book_source=book_source,
                cecchino_source=cecchino_source,
            ),
        )

    if bm_status == "not_available":
        warnings.append("Quote Betfair non disponibili")

    return {
        "version": KPI_V2_VERSION,
        "bookmaker": {
            "name": CECCHINO_BOOKMAKER["name"],
            "provider_bookmaker_id": int(CECCHINO_BOOKMAKER["provider_bookmaker_id"]),
            "provider_source": PROVIDER_API_FOOTBALL,
        },
        "columns": list(KPI_V2_COLUMNS),
        "bookmaker_status": bm_status,
        "rows": rows,
        "warnings": warnings,
    }
