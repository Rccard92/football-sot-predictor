"""Chiavi di mercato V4: analisi, famiglia ed etichetta italiana (docs/v4/API.md, "Chiavi di mercato").

Funzioni pure, nessuna quota, nessun database.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.services.cecchino_v4.constants import AH_MARKETS, MARKET_FAMILY, STAT_SIDES, STATS

KIND_CLASSIC = "classic"
KIND_AH = "ah"
KIND_STAT = "stat"

MINUS = "−"  # segno meno tipografico, come nella tab

_CLASSIC_LABELS: dict[str, str] = {
    "HOME": "1",
    "DRAW": "X",
    "AWAY": "2",
    "ONE_X": "1X",
    "X_TWO": "X2",
    "ONE_TWO": "12",
    "HOME_PT": "1 primo tempo",
    "DRAW_PT": "X primo tempo",
    "AWAY_PT": "2 primo tempo",
}


@dataclass(frozen=True)
class ParsedMarket:
    key: str
    kind: str  # classic | ah | stat
    family: str
    side: str | None = None  # ah: home|away ; stat: home|away|total
    line: float | None = None  # ah: linea dal punto di vista della casa ; stat: linea
    stat: str | None = None  # shots|sot|corners|cards|fouls
    direction: str | None = None  # stat: over|under ; classici over/under: over|under


def format_line(line: float) -> str:
    """Linea con la virgola e senza zeri inutili: 6.5 -> '6,5', 1.0 -> '1', 0.25 -> '0,25'."""
    if float(line) == int(line):
        return str(int(line))
    text = f"{line:.2f}".rstrip("0").rstrip(".")
    return text.replace(".", ",")


def parse_market_key(market_key: str) -> ParsedMarket:
    """Scompone una chiave di mercato. Solleva ValueError se la chiave non è nel contratto."""
    key = str(market_key).strip()
    if key in MARKET_FAMILY:
        direction = None
        line = None
        if key.startswith(("OVER_", "UNDER_")):
            direction = "over" if key.startswith("OVER_") else "under"
            line = float(key.split("_", 1)[1].replace("_", "."))
        return ParsedMarket(key=key, kind=KIND_CLASSIC, family=MARKET_FAMILY[key], line=line, direction=direction)

    if key.startswith("AH_"):
        try:
            market, raw_line = key.split(":", 1)
            line = float(raw_line)
        except ValueError as exc:
            raise ValueError(f"chiave handicap non valida: {market_key!r}") from exc
        if market not in AH_MARKETS:
            raise ValueError(f"mercato handicap sconosciuto: {market_key!r}")
        if abs(line * 4 - round(line * 4)) > 1e-9:
            raise ValueError(f"linea handicap non a quarti: {market_key!r}")
        side = "home" if market == "AH_HOME" else "away"
        return ParsedMarket(key=key, kind=KIND_AH, family="AH", side=side, line=line)

    if key.startswith("STAT:"):
        parts = key.split(":")
        if len(parts) != 5:
            raise ValueError(f"chiave statistica non valida: {market_key!r}")
        _, stat, side, direction, raw_line = parts
        if stat not in STATS or side not in STAT_SIDES or direction not in ("over", "under"):
            raise ValueError(f"chiave statistica non valida: {market_key!r}")
        try:
            line = float(raw_line)
        except ValueError as exc:
            raise ValueError(f"linea statistica non valida: {market_key!r}") from exc
        return ParsedMarket(
            key=key, kind=KIND_STAT, family=f"STAT_{stat}", side=side, line=line, stat=stat, direction=direction
        )

    raise ValueError(f"chiave di mercato sconosciuta: {market_key!r}")


def market_family(market_key: str) -> str:
    """FT_1X2, DOUBLE_CHANCE, FT_OVER_UNDER, HT_1X2, AH, STAT_shots, STAT_sot, STAT_corners, STAT_cards, STAT_fouls."""
    return parse_market_key(market_key).family


def stat_market_key(stat: str, side: str, direction: str, line: float) -> str:
    """Costruisce la chiave `STAT:<stat>:<lato>:<verso>:<linea>` con la linea in formato `6.5`."""
    return f"STAT:{stat}:{side}:{direction}:{float(line):.1f}"


def ah_line_text(line: float) -> str:
    """Linea handicap nel formato del contratto: `-0.5`, `+0.25`, `-1.0`, `0.0`."""
    if line == 0:
        return "0.0"
    text = f"{line:+.2f}"
    if text.endswith("0"):
        text = text[:-1]
    return text


def ah_market_key(side: str, line: float) -> str:
    """Costruisce `AH_HOME:<linea>` / `AH_AWAY:<linea>` con segno esplicito (`-0.5`, `+0.25`, `0.0`)."""
    market = "AH_HOME" if side == "home" else "AH_AWAY"
    return f"{market}:{ah_line_text(float(line))}"


def _signed_line(line: float) -> str:
    if line == 0:
        return "0"
    sign = MINUS if line < 0 else "+"
    return f"{sign}{format_line(abs(line))}"


def market_label(market_key: str, home_team: str, away_team: str) -> str:
    """Etichetta italiana della riga di mercato, con virgola decimale.

    Esempi: "1", "X2", "Over 2,5", "1 primo tempo", "Casa −0,5 (handicap asiatico)",
    "Inter over 6,5 tiri in porta", "Corner totali under 9,5".
    """
    parsed = parse_market_key(market_key)
    if parsed.kind == KIND_CLASSIC:
        if parsed.key in _CLASSIC_LABELS:
            return _CLASSIC_LABELS[parsed.key]
        word = "Over" if parsed.direction == "over" else "Under"
        return f"{word} {format_line(parsed.line or 0.0)}"

    if parsed.kind == KIND_AH:
        who = "Casa" if parsed.side == "home" else "Ospite"
        return f"{who} {_signed_line(parsed.line or 0.0)} (handicap asiatico)"

    stat_label = STATS[parsed.stat or ""]
    line_text = format_line(parsed.line or 0.0)
    if parsed.side == "total":
        return f"{stat_label[0].upper()}{stat_label[1:]} totali {parsed.direction} {line_text}"
    team = home_team if parsed.side == "home" else away_team
    return f"{team} {parsed.direction} {line_text} {stat_label}"


def family_label(family: str) -> str:
    """Nome italiano della famiglia di mercato, per la vista Misura."""
    names = {
        "FT_1X2": "Esito finale",
        "DOUBLE_CHANCE": "Doppia chance",
        "FT_OVER_UNDER": "Over/Under gol",
        "HT_1X2": "Esito primo tempo",
        "AH": "Handicap asiatico",
    }
    if family in names:
        return names[family]
    if family.startswith("STAT_"):
        stat = family[len("STAT_"):]
        label = STATS.get(stat, stat)
        return f"{label[0].upper()}{label[1:]}"
    return family
