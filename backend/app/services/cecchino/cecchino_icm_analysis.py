"""Indice di Convergenza Match (ICM) — Cecchino Today Fase 41."""

from __future__ import annotations

from typing import Any, Literal

from app.services.cecchino.cecchino_selection_keys import (
    SEL_AWAY,
    SEL_DRAW,
    SEL_HOME,
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

VERSION = "cecchino_icm_v1"

DRIVER_WEIGHTS: dict[str, int] = {
    "f36": 20,
    "dominance": 20,
    "quota_x": 20,
    "rating": 25,
    "vantaggio_prob": 15,
}

UNDER_MARKETS = (SEL_UNDER_2_5, SEL_UNDER_3_5, SEL_UNDER_PT_1_5)
OVER_MARKETS = (SEL_OVER_1_5, SEL_OVER_2_5, SEL_OVER_PT_0_5, SEL_OVER_PT_1_5)

NARRATIVE_META: dict[str, dict[str, str]] = {
    "balance_under": {
        "label": "Equilibrio + Under",
        "description": (
            "Gli indicatori principali convergono verso una partita equilibrata, "
            "con lettura favorevole ai mercati Under."
        ),
    },
    "balance_draw": {
        "label": "Equilibrio + X",
        "description": (
            "Gli indicatori convergono verso una partita equilibrata "
            "con il pareggio come scenario principale."
        ),
    },
    "imbalance_home": {
        "label": "Squilibrio + Segno 1",
        "description": (
            "Gli indicatori convergono verso uno squilibrio laterale "
            "con tendenza favorevole al segno 1."
        ),
    },
    "imbalance_away": {
        "label": "Squilibrio + Segno 2",
        "description": (
            "Gli indicatori convergono verso uno squilibrio laterale "
            "con tendenza favorevole al segno 2."
        ),
    },
    "imbalance_over": {
        "label": "Squilibrio + Over",
        "description": (
            "Gli indicatori convergono verso una partita sbilanciata "
            "con lettura favorevole ai mercati Over."
        ),
    },
    "contradictory_markets": {
        "label": "Mercati Contraddittori",
        "description": (
            "I segnali del modello non convergono verso una lettura univoca: "
            "i mercati raccontano scenari contrastanti."
        ),
    },
}

DriverStatus = Literal["support", "partial", "conflict"]

_DRIVER_SYMBOL = {"support": "✓", "partial": "~", "conflict": "✗"}

_COMPOSITION = [
    {
        "key": "f36",
        "label": "Equilibrio 1/2",
        "source": "F36",
        "plain_text": (
            "Deriva da F36. Indica se le quote matematiche 1 e 2 sono vicine oppure distanti."
        ),
    },
    {
        "key": "dominance",
        "label": "Convinzione del modello",
        "source": "Dominanza",
        "plain_text": (
            "Deriva dalla Dominanza. Indica se il modello ha uno scenario principale chiaro."
        ),
    },
    {
        "key": "quota_x",
        "label": "Forza del pareggio",
        "source": "Quota X Cecchino",
        "plain_text": (
            "Deriva dalla Quota X Cecchino. Indica se il pareggio è statisticamente vicino."
        ),
    },
    {
        "key": "rating",
        "label": "Mercato più forte",
        "source": "Rating KPI",
        "plain_text": (
            "Deriva dal Rating. Indica quale mercato ha la qualità statistica più alta nel KPI."
        ),
    },
    {
        "key": "vantaggio_prob",
        "label": "Valore probabilistico",
        "source": "Vantaggio Probabilistico",
        "plain_text": (
            "Deriva dal Vantaggio Probabilistico. "
            "Indica se la probabilità Cecchino sostiene o contraddice la narrativa."
        ),
    },
]


def _num(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _clamp(value: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, value))


def _status_points(status: DriverStatus) -> float:
    if status == "support":
        return 1.0
    if status == "partial":
        return 0.5
    return 0.0


def _driver_row(
    key: str,
    label: str,
    status: DriverStatus,
    plain_text: str,
) -> dict[str, Any]:
    return {
        "key": key,
        "label": label,
        "status": status,
        "symbol": _DRIVER_SYMBOL[status],
        "plain_text": plain_text,
    }


def _kpi_rows(kpi_panel: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not kpi_panel or not isinstance(kpi_panel, dict):
        return []
    rows = kpi_panel.get("rows") or []
    return [r for r in rows if isinstance(r, dict)]


def _kpi_row(kpi_panel: dict[str, Any] | None, market_key: str) -> dict[str, Any] | None:
    for row in _kpi_rows(kpi_panel):
        if row.get("market_key") == market_key:
            return row
    return None


def _vantaggio_pp(row: dict[str, Any] | None) -> float | None:
    if not row:
        return None
    v = _num(row.get("vantaggio_prob"))
    if v is None:
        return None
    if abs(v) <= 1.0:
        return v * 100.0
    return v


def _best_rating(rows: list[dict[str, Any]], keys: tuple[str, ...]) -> int | None:
    best: int | None = None
    for key in keys:
        row = next((r for r in rows if r.get("market_key") == key), None)
        if not row:
            continue
        rating = row.get("rating")
        if rating is None:
            continue
        try:
            val = int(rating)
        except (TypeError, ValueError):
            continue
        if best is None or val > best:
            best = val
    return best


def _best_vantaggio_pp(rows: list[dict[str, Any]], keys: tuple[str, ...]) -> float | None:
    vals: list[float] = []
    for key in keys:
        row = next((r for r in rows if r.get("market_key") == key), None)
        v = _vantaggio_pp(row)
        if v is not None:
            vals.append(v)
    if not vals:
        return None
    return max(vals)


def _any_positive_vantaggio(rows: list[dict[str, Any]], keys: tuple[str, ...]) -> bool:
    for key in keys:
        row = next((r for r in rows if r.get("market_key") == key), None)
        v = _vantaggio_pp(row)
        if v is not None and v > 0:
            return True
    return False


def _extract_icm_inputs(
    balance_analysis: dict[str, Any] | None,
    kpi_panel: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if not balance_analysis or balance_analysis.get("status") != "available":
        return None

    f36 = balance_analysis.get("f36") or {}
    dominance = balance_analysis.get("dominance") or {}
    draw = balance_analysis.get("draw") or {}
    inputs = balance_analysis.get("inputs") or {}

    f36_signed = _num(f36.get("signed"))
    f36_abs = _num(f36.get("abs"))
    quota_x = _num(draw.get("quota")) or _num(inputs.get("quota_x"))
    dominance_pp = _num(dominance.get("value"))
    best_side = str(dominance.get("best_side") or "")
    second_side = str(dominance.get("second_side") or "")

    if None in (f36_signed, f36_abs, quota_x, dominance_pp):
        return None

    rows = _kpi_rows(kpi_panel)
    return {
        "f36_signed": f36_signed,
        "f36_abs": f36_abs,
        "quota_x": quota_x,
        "dominance_pp": dominance_pp,
        "best_side": best_side,
        "second_side": second_side,
        "rows": rows,
        "rating_home": _num((_kpi_row(kpi_panel, SEL_HOME) or {}).get("rating")),
        "rating_away": _num((_kpi_row(kpi_panel, SEL_AWAY) or {}).get("rating")),
        "rating_draw": _num((_kpi_row(kpi_panel, SEL_DRAW) or {}).get("rating")),
        "rating_1x": _num((_kpi_row(kpi_panel, SEL_ONE_X) or {}).get("rating")),
        "rating_x2": _num((_kpi_row(kpi_panel, SEL_X_TWO) or {}).get("rating")),
        "vant_home_pp": _vantaggio_pp(_kpi_row(kpi_panel, SEL_HOME)),
        "vant_away_pp": _vantaggio_pp(_kpi_row(kpi_panel, SEL_AWAY)),
        "vant_draw_pp": _vantaggio_pp(_kpi_row(kpi_panel, SEL_DRAW)),
        "best_under_rating": _best_rating(rows, UNDER_MARKETS),
        "best_over_rating": _best_rating(rows, OVER_MARKETS),
        "best_under_vant_pp": _best_vantaggio_pp(rows, UNDER_MARKETS),
        "best_over_vant_pp": _best_vantaggio_pp(rows, OVER_MARKETS),
        "under_positive_vant": _any_positive_vantaggio(rows, UNDER_MARKETS),
        "over_positive_vant": _any_positive_vantaggio(rows, OVER_MARKETS),
    }


def _score_from_statuses(statuses: dict[str, DriverStatus]) -> int:
    total = 0.0
    for key, weight in DRIVER_WEIGHTS.items():
        status = statuses.get(key, "conflict")
        total += weight * _status_points(status)
    return int(round(total))


def _f36_balance_under(f36_abs: float) -> DriverStatus:
    if f36_abs < 0.75:
        return "support"
    if f36_abs <= 1.50:
        return "partial"
    return "conflict"


def _dominance_balance_under(best_side: str, dominance_pp: float) -> DriverStatus:
    if best_side == "DRAW" or dominance_pp <= 5:
        return "support"
    if dominance_pp <= 10:
        return "partial"
    if best_side in ("HOME", "AWAY") and dominance_pp > 10:
        return "conflict"
    return "partial"


def _quota_x_low(quota_x: float) -> DriverStatus:
    if quota_x <= 3.50:
        return "support"
    if quota_x <= 4.20:
        return "partial"
    return "conflict"


def _quota_x_high(quota_x: float) -> DriverStatus:
    if quota_x > 3.50:
        return "support"
    if quota_x >= 3.21:
        return "partial"
    return "conflict"


def _rating_under_driver(best_under: int | None, best_over: int | None) -> DriverStatus:
    if best_under is None:
        return "conflict"
    if best_under >= 60 and (best_over is None or best_under >= best_over):
        return "support"
    if 40 <= best_under <= 59:
        return "partial"
    if best_over is not None and best_over >= best_under + 15:
        return "conflict"
    return "conflict"


def _rating_over_driver(best_over: int | None, best_under: int | None) -> DriverStatus:
    if best_over is None:
        return "conflict"
    if best_over >= 60 and (best_under is None or best_over >= best_under):
        return "support"
    if 40 <= best_over <= 59:
        return "partial"
    if best_under is not None and best_under >= best_over + 15:
        return "conflict"
    return "conflict"


def _vant_under_driver(inp: dict[str, Any]) -> DriverStatus:
    under_v = inp.get("best_under_vant_pp")
    over_v = inp.get("best_over_vant_pp")
    if inp.get("under_positive_vant"):
        return "support"
    if under_v is not None and -3 <= under_v <= 0:
        return "partial"
    if under_v is not None and under_v < -3 and over_v is not None and over_v > 0:
        return "conflict"
    return "partial"


def _vant_over_driver(inp: dict[str, Any]) -> DriverStatus:
    over_v = inp.get("best_over_vant_pp")
    under_v = inp.get("best_under_vant_pp")
    if inp.get("over_positive_vant"):
        return "support"
    if over_v is not None and -3 <= over_v <= 0:
        return "partial"
    if over_v is not None and over_v < -3 and under_v is not None and under_v > 0:
        return "conflict"
    return "partial"


def _vant_draw_driver(vant_draw_pp: float | None) -> DriverStatus:
    if vant_draw_pp is None:
        return "conflict"
    if vant_draw_pp > 0:
        return "support"
    if -3 <= vant_draw_pp <= 0:
        return "partial"
    return "conflict"


def _vant_side_driver(vant_pp: float | None) -> DriverStatus:
    if vant_pp is None:
        return "conflict"
    if vant_pp > 0:
        return "support"
    if -3 <= vant_pp <= 0:
        return "partial"
    return "conflict"


def _rating_draw_driver(rating_draw: float | None, rating_1x: float | None, rating_x2: float | None) -> DriverStatus:
    if rating_draw is not None and rating_draw >= 60:
        return "support"
    if rating_draw is not None and 40 <= rating_draw <= 59:
        return "partial"
    lateral = max(rating_1x or 0, rating_x2 or 0)
    if rating_draw is not None and lateral >= 60 and rating_draw < 40:
        return "partial"
    return "conflict"


def _rating_home_driver(rating_home: float | None, rating_1x: float | None) -> DriverStatus:
    if rating_home is not None and rating_home >= 60:
        return "support"
    if rating_1x is not None and rating_1x >= 60:
        return "partial"
    return "conflict"


def _rating_away_driver(rating_away: float | None, rating_x2: float | None) -> DriverStatus:
    if rating_away is not None and rating_away >= 60:
        return "support"
    if rating_x2 is not None and rating_x2 >= 60:
        return "partial"
    return "conflict"


def _dominance_balance_draw(best_side: str, dominance_pp: float) -> DriverStatus:
    if best_side == "DRAW":
        return "support"
    if dominance_pp <= 5:
        return "partial"
    if best_side in ("HOME", "AWAY") and dominance_pp > 10:
        return "conflict"
    return "partial"


def _dominance_imbalance_home(best_side: str, second_side: str, dominance_pp: float) -> DriverStatus:
    if best_side == "HOME":
        return "support"
    if second_side == "HOME" and dominance_pp <= 8:
        return "partial"
    if best_side in ("DRAW", "AWAY") and dominance_pp > 10:
        return "conflict"
    return "partial"


def _dominance_imbalance_away(best_side: str, second_side: str, dominance_pp: float) -> DriverStatus:
    if best_side == "AWAY":
        return "support"
    if second_side == "AWAY" and dominance_pp <= 8:
        return "partial"
    if best_side in ("DRAW", "HOME") and dominance_pp > 10:
        return "conflict"
    return "partial"


def _dominance_imbalance_over(best_side: str, dominance_pp: float, quota_x: float) -> DriverStatus:
    if best_side in ("HOME", "AWAY") and dominance_pp > 8:
        return "support"
    if 4 <= dominance_pp <= 8:
        return "partial"
    if best_side == "DRAW" and quota_x <= 3.20:
        return "conflict"
    return "partial"


def _f36_imbalance_home(f36_signed: float) -> DriverStatus:
    if f36_signed > 1.50:
        return "support"
    if f36_signed >= 0.75:
        return "partial"
    return "conflict"


def _f36_imbalance_away(f36_signed: float) -> DriverStatus:
    if f36_signed < -1.50:
        return "support"
    if f36_signed <= -0.75:
        return "partial"
    return "conflict"


def _f36_imbalance_over(f36_abs: float) -> DriverStatus:
    if f36_abs > 1.50:
        return "support"
    if f36_abs >= 0.75:
        return "partial"
    return "conflict"


def _plain_f36(status: DriverStatus, narrative: str) -> str:
    if narrative in ("balance_under", "balance_draw"):
        if status == "support":
            return "Le quote 1 e 2 sono vicine: il match è letto come equilibrato."
        if status == "partial":
            return "Le quote 1 e 2 sono in transizione: equilibrio non pienamente confermato."
        return "Le quote 1 e 2 sono distanti: l'equilibrio laterale non è il segnale dominante."
    if narrative == "imbalance_home":
        if status == "support":
            return "F36 positivo alto: la quota 2 è più alta della quota 1, il modello tende verso 1."
        if status == "partial":
            return "F36 positivo moderato: leggera tendenza verso il segno 1."
        return "F36 non conferma uno squilibrio verso il segno 1."
    if narrative == "imbalance_away":
        if status == "support":
            return "F36 negativo alto: la quota 1 è più alta della quota 2, il modello tende verso 2."
        if status == "partial":
            return "F36 negativo moderato: leggera tendenza verso il segno 2."
        return "F36 non conferma uno squilibrio verso il segno 2."
    if status == "support":
        return "F36 indica squilibrio laterale: le quote 1 e 2 sono distanti."
    if status == "partial":
        return "F36 in zona di transizione: squilibrio parziale."
    return "F36 basso: le quote 1 e 2 sono vicine, poco favorevole a una lettura Over laterale."


def _plain_dominance(status: DriverStatus, best_side: str) -> str:
    if status == "support" and best_side == "DRAW":
        return "La X è lo scenario dominante: rafforza la lettura di equilibrio."
    if status == "support":
        return "La Dominanza non spinge contro la narrativa prevalente."
    if status == "partial":
        return "La Dominanza è moderata: il modello resta parzialmente aperto."
    return "La Dominanza spinge in direzione opposta alla narrativa prevalente."


def _plain_quota_x(status: DriverStatus) -> str:
    if status == "support":
        return "La quota X Cecchino è bassa: il pareggio è statisticamente vicino."
    if status == "partial":
        return "La quota X è in zona intermedia: il pareggio non è né vicino né lontano."
    return "La quota X è alta: il pareggio è statisticamente lontano."


def _plain_rating(status: DriverStatus, label: str) -> str:
    if status == "support":
        return f"Il mercato {label} è tra i più forti del KPI."
    if status == "partial":
        return f"Il mercato {label} ha un rating moderato nel KPI."
    return f"Il mercato {label} non è tra i più forti del KPI."


def _plain_vantaggio(status: DriverStatus) -> str:
    if status == "support":
        return "Il vantaggio probabilistico sostiene la narrativa prevalente."
    if status == "partial":
        return "Il vantaggio probabilistico è leggero ma non contrario alla lettura."
    return "Il vantaggio probabilistico contraddice la narrativa prevalente."


def _build_drivers_for_narrative(narrative: str, statuses: dict[str, DriverStatus], inp: dict[str, Any]) -> list[dict[str, Any]]:
    rating_labels = {
        "balance_under": "Under",
        "balance_draw": "DRAW",
        "imbalance_home": "HOME",
        "imbalance_away": "AWAY",
        "imbalance_over": "Over",
        "contradictory_markets": "KPI",
    }
    return [
        _driver_row("f36", "Equilibrio 1/2", statuses["f36"], _plain_f36(statuses["f36"], narrative)),
        _driver_row(
            "dominance",
            "Dominanza",
            statuses["dominance"],
            _plain_dominance(statuses["dominance"], inp["best_side"]),
        ),
        _driver_row("quota_x", "Quota X", statuses["quota_x"], _plain_quota_x(statuses["quota_x"])),
        _driver_row(
            "rating",
            f"Rating {rating_labels.get(narrative, 'KPI')}",
            statuses["rating"],
            _plain_rating(statuses["rating"], rating_labels.get(narrative, "KPI")),
        ),
        _driver_row(
            "vantaggio_prob",
            "Vantaggio Probabilistico",
            statuses["vantaggio_prob"],
            _plain_vantaggio(statuses["vantaggio_prob"]),
        ),
    ]


def _score_balance_under(inp: dict[str, Any]) -> tuple[int, list[dict[str, Any]], dict[str, DriverStatus]]:
    statuses = {
        "f36": _f36_balance_under(inp["f36_abs"]),
        "dominance": _dominance_balance_under(inp["best_side"], inp["dominance_pp"]),
        "quota_x": _quota_x_low(inp["quota_x"]),
        "rating": _rating_under_driver(
            inp.get("best_under_rating"),
            inp.get("best_over_rating"),
        ),
        "vantaggio_prob": _vant_under_driver(inp),
    }
    return _score_from_statuses(statuses), _build_drivers_for_narrative("balance_under", statuses, inp), statuses


def _score_balance_draw(inp: dict[str, Any]) -> tuple[int, list[dict[str, Any]], dict[str, DriverStatus]]:
    statuses = {
        "f36": _f36_balance_under(inp["f36_abs"]),
        "dominance": _dominance_balance_draw(inp["best_side"], inp["dominance_pp"]),
        "quota_x": _quota_x_low(inp["quota_x"]),
        "rating": _rating_draw_driver(inp.get("rating_draw"), inp.get("rating_1x"), inp.get("rating_x2")),
        "vantaggio_prob": _vant_draw_driver(inp.get("vant_draw_pp")),
    }
    return _score_from_statuses(statuses), _build_drivers_for_narrative("balance_draw", statuses, inp), statuses


def _score_imbalance_home(inp: dict[str, Any]) -> tuple[int, list[dict[str, Any]], dict[str, DriverStatus]]:
    statuses = {
        "f36": _f36_imbalance_home(inp["f36_signed"]),
        "dominance": _dominance_imbalance_home(inp["best_side"], inp["second_side"], inp["dominance_pp"]),
        "quota_x": _quota_x_high(inp["quota_x"]),
        "rating": _rating_home_driver(inp.get("rating_home"), inp.get("rating_1x")),
        "vantaggio_prob": _vant_side_driver(inp.get("vant_home_pp")),
    }
    return _score_from_statuses(statuses), _build_drivers_for_narrative("imbalance_home", statuses, inp), statuses


def _score_imbalance_away(inp: dict[str, Any]) -> tuple[int, list[dict[str, Any]], dict[str, DriverStatus]]:
    statuses = {
        "f36": _f36_imbalance_away(inp["f36_signed"]),
        "dominance": _dominance_imbalance_away(inp["best_side"], inp["second_side"], inp["dominance_pp"]),
        "quota_x": _quota_x_high(inp["quota_x"]),
        "rating": _rating_away_driver(inp.get("rating_away"), inp.get("rating_x2")),
        "vantaggio_prob": _vant_side_driver(inp.get("vant_away_pp")),
    }
    return _score_from_statuses(statuses), _build_drivers_for_narrative("imbalance_away", statuses, inp), statuses


def _score_imbalance_over(inp: dict[str, Any]) -> tuple[int, list[dict[str, Any]], dict[str, DriverStatus]]:
    statuses = {
        "f36": _f36_imbalance_over(inp["f36_abs"]),
        "dominance": _dominance_imbalance_over(inp["best_side"], inp["dominance_pp"], inp["quota_x"]),
        "quota_x": _quota_x_high(inp["quota_x"]),
        "rating": _rating_over_driver(inp.get("best_over_rating"), inp.get("best_under_rating")),
        "vantaggio_prob": _vant_over_driver(inp),
    }
    return _score_from_statuses(statuses), _build_drivers_for_narrative("imbalance_over", statuses, inp), statuses


def _score_contradictory(inp: dict[str, Any]) -> tuple[int, list[dict[str, Any]], dict[str, DriverStatus]]:
    statuses = {
        "f36": "conflict",
        "dominance": "conflict",
        "quota_x": "conflict",
        "rating": "conflict",
        "vantaggio_prob": "conflict",
    }
    drivers = [
        _driver_row("f36", "Equilibrio 1/2", "conflict", "I segnali su 1 e 2 non convergono."),
        _driver_row("dominance", "Dominanza", "conflict", "La Dominanza non supporta una lettura univoca."),
        _driver_row("quota_x", "Quota X", "conflict", "La Quota X non allinea i mercati."),
        _driver_row("rating", "Rating KPI", "conflict", "I rating KPI puntano in direzioni diverse."),
        _driver_row(
            "vantaggio_prob",
            "Vantaggio Probabilistico",
            "conflict",
            "Il vantaggio probabilistico contraddice più mercati.",
        ),
    ]
    raw_scores = [
        _score_balance_under(inp)[0],
        _score_balance_draw(inp)[0],
        _score_imbalance_home(inp)[0],
        _score_imbalance_away(inp)[0],
        _score_imbalance_over(inp)[0],
    ]
    score = min(40, max(raw_scores) if raw_scores else 0)
    return score, drivers, statuses


def _detect_opposing_drivers(inp: dict[str, Any]) -> bool:
    f36_low = inp["f36_abs"] < 0.75
    over_strong = (inp.get("best_over_rating") or 0) >= 60
    x_low = inp["quota_x"] <= 3.20
    lateral_high = inp["best_side"] in ("HOME", "AWAY") and inp["dominance_pp"] > 10
    if f36_low and over_strong and lateral_high:
        return True
    if x_low and over_strong:
        return True
    if lateral_high and x_low:
        return True
    best_rating_row = None
    best_rating = -1
    for row in inp["rows"]:
        r = row.get("rating")
        if r is not None and int(r) > best_rating:
            best_rating = int(r)
            best_rating_row = row
    if best_rating_row:
        v = _vantaggio_pp(best_rating_row)
        if v is not None and v < -3:
            return True
    return False


def _ambiguity_penalty(gap: float) -> int:
    if gap >= 20:
        return 0
    if gap >= 10:
        return 5
    if gap >= 5:
        return 10
    return 20


def _classify_icm(score: int) -> dict[str, Any]:
    if score <= 20:
        return {
            "class_key": "contradictory",
            "label": "Partita Contraddittoria",
            "short_label": "Contraddittoria",
            "severity": "negative",
        }
    if score <= 40:
        return {
            "class_key": "weak_convergence",
            "label": "Debole Convergenza",
            "short_label": "Debole",
            "severity": "warning",
        }
    if score <= 60:
        return {
            "class_key": "moderate_convergence",
            "label": "Convergenza Moderata",
            "short_label": "Moderata",
            "severity": "neutral",
        }
    if score <= 80:
        return {
            "class_key": "strong_convergence",
            "label": "Convergenza Forte",
            "short_label": "Forte",
            "severity": "positive",
        }
    return {
        "class_key": "total_convergence",
        "label": "Convergenza Totale",
        "short_label": "Totale",
        "severity": "positive",
    }


def _insufficient_payload(warnings: list[str]) -> dict[str, Any]:
    return {
        "version": VERSION,
        "status": "insufficient_data",
        "score": None,
        "score_pct": None,
        "class_key": None,
        "label": "Dati insufficienti",
        "short_label": None,
        "severity": None,
        "dominant_narrative": None,
        "drivers": [],
        "composition": list(_COMPOSITION),
        "candidate_narratives": [],
        "technical": None,
        "warnings": warnings,
    }


def build_cecchino_icm_analysis(
    *,
    balance_analysis: dict[str, Any] | None,
    kpi_panel: dict[str, Any] | None,
) -> dict[str, Any]:
    """Costruisce l'Indice di Convergenza Match da balance e KPI."""
    inp = _extract_icm_inputs(balance_analysis, kpi_panel)
    if inp is None:
        return _insufficient_payload(["missing_icm_inputs"])

    scorers = {
        "balance_under": _score_balance_under,
        "balance_draw": _score_balance_draw,
        "imbalance_home": _score_imbalance_home,
        "imbalance_away": _score_imbalance_away,
        "imbalance_over": _score_imbalance_over,
    }

    candidates: list[dict[str, Any]] = []
    narrative_data: dict[str, tuple[int, list[dict[str, Any]], dict[str, DriverStatus]]] = {}

    for key, scorer in scorers.items():
        score, drivers, statuses = scorer(inp)
        narrative_data[key] = (score, drivers, statuses)
        candidates.append({"key": key, "label": NARRATIVE_META[key]["label"], "score": score})

    candidates.sort(key=lambda c: c["score"], reverse=True)
    best_key = candidates[0]["key"]
    best_score = candidates[0]["score"]
    second_score = candidates[1]["score"] if len(candidates) > 1 else 0
    gap = best_score - second_score

    force_contradictory = (
        best_score <= 40
        or gap < 5
        or _detect_opposing_drivers(inp)
    )

    if force_contradictory:
        contra_score, contra_drivers, contra_statuses = _score_contradictory(inp)
        best_key = "contradictory_markets"
        best_score = min(contra_score, 40)
        drivers = contra_drivers
        narrative_data["contradictory_markets"] = (best_score, drivers, contra_statuses)
        candidates.append(
            {
                "key": "contradictory_markets",
                "label": NARRATIVE_META["contradictory_markets"]["label"],
                "score": best_score,
            },
        )
    else:
        _, drivers, _ = narrative_data[best_key]

    penalty = _ambiguity_penalty(gap)
    final_score = int(round(_clamp(best_score - penalty, 0, 100)))
    classification = _classify_icm(final_score)
    meta = NARRATIVE_META[best_key]

    return {
        "version": VERSION,
        "status": "available",
        "score": final_score,
        "score_pct": final_score,
        "class_key": classification["class_key"],
        "label": classification["label"],
        "short_label": classification["short_label"],
        "severity": classification["severity"],
        "dominant_narrative": {
            "key": best_key,
            "label": meta["label"],
            "description": meta["description"],
        },
        "drivers": drivers,
        "composition": list(_COMPOSITION),
        "candidate_narratives": candidates,
        "technical": {
            "best_narrative": best_key,
            "best_score": best_score,
            "second_score": second_score,
            "gap": gap,
            "ambiguity_penalty": penalty,
            "final_score": final_score,
            "driver_weights": dict(DRIVER_WEIGHTS),
            "forced_contradictory": force_contradictory,
            "driver_statuses_by_narrative": {
                k: v[2] for k, v in narrative_data.items()
            },
        },
        "warnings": [],
    }
