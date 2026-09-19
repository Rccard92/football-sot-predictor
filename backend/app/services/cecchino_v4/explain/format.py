"""Formattazione italiana per le frasi della V4: virgola decimale, percentuali intere, ordinali."""

from __future__ import annotations

MINUS = "−"

_ORDINALS_M: tuple[str, ...] = (
    "primo",
    "secondo",
    "terzo",
    "quarto",
    "quinto",
    "sesto",
    "settimo",
    "ottavo",
    "nono",
    "decimo",
    "undicesimo",
    "dodicesimo",
    "tredicesimo",
    "quattordicesimo",
    "quindicesimo",
    "sedicesimo",
    "diciassettesimo",
    "diciottesimo",
    "diciannovesimo",
    "ventesimo",
    "ventunesimo",
    "ventiduesimo",
    "ventitreesimo",
    "ventiquattresimo",
    "venticinquesimo",
    "ventiseiesimo",
)


def fmt_num(value: float | int | None, decimals: int = 1, signed: bool = False) -> str:
    """1.85 -> '1,85' (decimals=2); 6.8 -> '6,8'; -0.5 -> '−0,5'; None -> 'n.d.'."""
    if value is None:
        return "n.d."
    text = f"{abs(float(value)):.{decimals}f}".replace(".", ",")
    if float(value) < 0 and text.strip("0,") != "":
        return f"{MINUS}{text}"
    if signed and float(value) > 0:
        return f"+{text}"
    return text


def fmt_quota(value: float | None) -> str:
    return fmt_num(value, decimals=2)


def fmt_pct(p: float | None, signed: bool = False) -> str:
    """0.613 -> '61%'; 0.13 con signed -> '+13%'; -0.02 -> '−2%'."""
    if p is None:
        return "n.d."
    value = round(float(p) * 100)
    if value < 0:
        return f"{MINUS}{abs(value)}%"
    if signed and value > 0:
        return f"+{value}%"
    return f"{value}%"


def fmt_interval(lo: float | None, hi: float | None) -> str:
    """(0.55, 0.66) -> '55-66'."""
    if lo is None or hi is None:
        return "n.d."
    return f"{round(float(lo) * 100)}-{round(float(hi) * 100)}"


def ordinal(n: int | None, feminine: bool = False) -> str:
    """3 -> 'terzo' / 'terza'. Oltre la tabella: '27°'."""
    if n is None or int(n) < 1:
        return "n.d."
    n = int(n)
    if n > len(_ORDINALS_M):
        return f"{n}°"
    word = _ORDINALS_M[n - 1]
    return word[:-1] + "a" if feminine else word


def fmt_days(n: int | float | None) -> str:
    if n is None:
        return "n.d."
    n = int(round(float(n)))
    return "1 giorno" if n == 1 else f"{n} giorni"


def join_it(parts: list[str]) -> str:
    """['a', 'b', 'c'] -> 'a, b e c'."""
    parts = [p for p in parts if p]
    if not parts:
        return ""
    if len(parts) == 1:
        return parts[0]
    return ", ".join(parts[:-1]) + " e " + parts[-1]
