"""Regolamento delle giocate V4: da risultato e statistiche reali all'esito di ogni chiave di mercato.

Funzioni pure. Esiti: `vinta`, `persa`, `void`, `mezza_vinta`, `mezza_persa` (handicap a quarti), `None` se il dato manca.
"""

from __future__ import annotations

from typing import Any

from app.services.cecchino_v4.constants import CARD_WEIGHT_RED, CARD_WEIGHT_YELLOW
from app.services.cecchino_v4.selection.labels import KIND_AH, KIND_CLASSIC, KIND_STAT, parse_market_key

WON = "vinta"
LOST = "persa"
VOID = "void"
HALF_WON = "mezza_vinta"
HALF_LOST = "mezza_persa"
OUTCOMES: tuple[str, ...] = (WON, LOST, VOID, HALF_WON, HALF_LOST)

_EPS = 1e-9


def _int_or_none(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _binary(condition: bool) -> str:
    return WON if condition else LOST


def settle_classic(market_key: str, ft_home: int, ft_away: int, ht_home: int | None, ht_away: int | None) -> str | None:
    parsed = parse_market_key(market_key)
    key = parsed.key
    if key.endswith("_PT"):
        if ht_home is None or ht_away is None:
            return None
        if key == "HOME_PT":
            return _binary(ht_home > ht_away)
        if key == "DRAW_PT":
            return _binary(ht_home == ht_away)
        return _binary(ht_home < ht_away)

    if key == "HOME":
        return _binary(ft_home > ft_away)
    if key == "DRAW":
        return _binary(ft_home == ft_away)
    if key == "AWAY":
        return _binary(ft_home < ft_away)
    if key == "ONE_X":
        return _binary(ft_home >= ft_away)
    if key == "X_TWO":
        return _binary(ft_home <= ft_away)
    if key == "ONE_TWO":
        return _binary(ft_home != ft_away)

    total = ft_home + ft_away
    line = parsed.line or 0.0
    if parsed.direction == "over":
        return _binary(total > line)
    return _binary(total < line)


def _half_line_outcome(margin: float) -> str:
    if margin > _EPS:
        return WON
    if margin < -_EPS:
        return LOST
    return VOID


def ah_outcome(side: str, line: float, ft_home: int, ft_away: int) -> str:
    """Esito dell'handicap asiatico. `line` è dal punto di vista della squadra scelta (`side`).

    Linee intere e mezze: una sola puntata (vinta/persa/void). Linee a quarti: metà puntata su
    ciascuna delle due linee adiacenti; la combinazione dà anche `mezza_vinta`/`mezza_persa`.
    """
    diff = (ft_home - ft_away) if side == "home" else (ft_away - ft_home)
    is_quarter = abs(line * 2 - round(line * 2)) > _EPS
    if not is_quarter:
        return _half_line_outcome(diff + line)

    first = _half_line_outcome(diff + line - 0.25)
    second = _half_line_outcome(diff + line + 0.25)
    pair = {first, second}
    if pair == {WON}:
        return WON
    if pair == {LOST}:
        return LOST
    if pair == {WON, VOID}:
        return HALF_WON
    if pair == {LOST, VOID}:
        return HALF_LOST
    return VOID  # non raggiungibile con linee a quarti, tenuto per completezza


def cards_points(team_stats: dict[str, Any]) -> float | None:
    """Cartellini pesati: giallo 1, rosso 2. Se mancano giallo e rosso ma esiste `cards`, usa quello."""
    yellow = team_stats.get("yellow")
    red = team_stats.get("red")
    if yellow is None and red is None:
        raw = team_stats.get("cards")
        return float(raw) if raw is not None else None
    return float(yellow or 0) * CARD_WEIGHT_YELLOW + float(red or 0) * CARD_WEIGHT_RED


def stat_value(stats: dict[str, Any] | None, stat: str, side: str) -> float | None:
    """Valore reale di una statistica per lato (`home|away|total`); None se manca."""
    if not stats:
        return None
    sides = ("home", "away") if side == "total" else (side,)
    total = 0.0
    for s in sides:
        team = stats.get(s)
        if not isinstance(team, dict):
            return None
        value = cards_points(team) if stat == "cards" else team.get(stat)
        if value is None:
            return None
        total += float(value)
    return total


def settle_stat(market_key: str, stats: dict[str, Any] | None) -> str | None:
    parsed = parse_market_key(market_key)
    value = stat_value(stats, parsed.stat or "", parsed.side or "")
    if value is None:
        return None
    line = parsed.line or 0.0
    if abs(value - line) < _EPS:
        return VOID
    if parsed.direction == "over":
        return _binary(value > line)
    return _binary(value < line)


def settle(market_key: str, result: dict[str, Any] | None, stats: dict[str, Any] | None = None) -> str | None:
    """Esito della chiave di mercato dato il risultato `{"ft_home","ft_away","ht_home","ht_away"}` e le statistiche.

    Ritorna None quando il dato necessario manca (risultato assente, primo tempo assente, statistica assente).
    """
    parsed = parse_market_key(market_key)
    if parsed.kind == KIND_STAT:
        return settle_stat(market_key, stats)

    if not result:
        return None
    ft_home = _int_or_none(result.get("ft_home"))
    ft_away = _int_or_none(result.get("ft_away"))
    if ft_home is None or ft_away is None:
        return None
    if parsed.kind == KIND_AH:
        return ah_outcome(parsed.side or "home", parsed.line or 0.0, ft_home, ft_away)
    if parsed.kind == KIND_CLASSIC:
        return settle_classic(market_key, ft_home, ft_away, _int_or_none(result.get("ht_home")), _int_or_none(result.get("ht_away")))
    return None


def profit_units(outcome: str | None, quota: float | None) -> float | None:
    """Profitto in unità di puntata (puntata piatta 1) per l'esito dato."""
    if outcome is None or quota is None:
        return None
    q = float(quota)
    if outcome == WON:
        return q - 1.0
    if outcome == LOST:
        return -1.0
    if outcome == VOID:
        return 0.0
    if outcome == HALF_WON:
        return (q - 1.0) / 2.0
    if outcome == HALF_LOST:
        return -0.5
    raise ValueError(f"esito sconosciuto: {outcome!r}")
