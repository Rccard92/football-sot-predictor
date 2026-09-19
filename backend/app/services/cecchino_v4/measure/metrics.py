"""Metriche V4 (funzioni pure): ROI, intervallo bootstrap a blocchi, CLV, CUSUM, riepilogo per campionato e mercato.

Convenzioni:
- ogni "voce" è un dict o un oggetto con `profit_units` (None se non regolata), `day` (o `match_date`) per il blocco,
  `league_code`, `family` (o `market_family`), `quota_used` (o `quota`), `closing_quota`, `clv`;
- CLV = quota presa / quota di chiusura - 1: positivo quando abbiamo preso un prezzo migliore della chiusura;
- ROI = profitto in unità / numero di giocate (puntata piatta 1).
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Iterable, Sequence

import numpy as np

from app.services.cecchino_v4.constants import PROFIT_MARGIN
from app.services.cecchino_v4.explain.format import fmt_num, fmt_pct
from app.services.cecchino_v4.selection.labels import family_label

# Giocate minime per un allarme CUSUM su un gruppo (campionato o famiglia di mercato).
CUSUM_MIN_PLAYS = 30
# Parametri CUSUM pre-registrati: tolleranza k (perdita media per giocata tollerata prima di accumulare)
# e soglia h in unità. k = margine richiesto: si accumula quando la giocata rende meno del margine.
CUSUM_K = PROFIT_MARGIN
CUSUM_H = 6.0
BOOTSTRAP_DEFAULT_N = 2000
BOOTSTRAP_ALPHA = 0.10  # intervallo al 90%


def _get(item: Any, *names: str, default: Any = None) -> Any:
    for name in names:
        if isinstance(item, dict):
            if name in item and item[name] is not None:
                return item[name]
        elif hasattr(item, name) and getattr(item, name) is not None:
            return getattr(item, name)
    return default


def settled(items: Iterable[Any]) -> list[Any]:
    return [i for i in items if _get(i, "profit_units") is not None]


def roi(items: Iterable[Any]) -> dict[str, Any]:
    """{"plays", "profit_units", "roi"}; roi None senza giocate regolate."""
    rows = settled(items)
    plays = len(rows)
    profit = float(sum(float(_get(r, "profit_units")) for r in rows))
    return {"plays": plays, "profit_units": round(profit, 4), "roi": None if plays == 0 else round(profit / plays, 4)}


def block_bootstrap_ci(
    items: Iterable[Any],
    block_key: str | Sequence[str] = ("day", "match_date"),
    n: int = BOOTSTRAP_DEFAULT_N,
    seed: int = 0,
    alpha: float = BOOTSTRAP_ALPHA,
) -> tuple[float | None, float | None]:
    """Intervallo del ROI ricampionando i blocchi (giornate) con rimessa. (None, None) senza giocate.
    I blocchi conservano la dipendenza tra giocate dello stesso giorno."""
    rows = settled(items)
    if not rows:
        return None, None
    keys = (block_key,) if isinstance(block_key, str) else tuple(block_key)
    blocks: dict[Any, list[float]] = defaultdict(list)
    for r in rows:
        blocks[str(_get(r, *keys, default="_"))].append(float(_get(r, "profit_units")))
    block_profit = np.array([sum(v) for v in blocks.values()], dtype=float)
    block_plays = np.array([len(v) for v in blocks.values()], dtype=float)
    b = len(block_profit)
    if b == 1:
        value = float(block_profit[0] / block_plays[0])
        return round(value, 4), round(value, 4)
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, b, size=(int(n), b))
    rois = block_profit[idx].sum(axis=1) / block_plays[idx].sum(axis=1)
    lo, hi = np.quantile(rois, [alpha / 2.0, 1.0 - alpha / 2.0])
    return round(float(lo), 4), round(float(hi), 4)


def clv(quota_taken: float | None, quota_closing: float | None) -> float | None:
    """Closing line value = quota presa / quota di chiusura - 1. Positivo: prezzo migliore della chiusura."""
    if quota_taken is None or quota_closing is None or float(quota_closing) <= 1.0:
        return None
    return round(float(quota_taken) / float(quota_closing) - 1.0, 4)


def clv_summary(items: Iterable[Any]) -> dict[str, Any]:
    """{"plays", "clv" (media), "clv_positive_share"} sulle voci con CLV o con quota di chiusura."""
    values: list[float] = []
    for it in items:
        value = _get(it, "clv")
        if value is None:
            value = clv(_get(it, "quota_used", "quota"), _get(it, "closing_quota", "quota_closing"))
        if value is not None:
            values.append(float(value))
    if not values:
        return {"plays": 0, "clv": None, "clv_positive_share": None}
    arr = np.array(values)
    return {"plays": len(values), "clv": round(float(arr.mean()), 4), "clv_positive_share": round(float((arr > 0).mean()), 4)}


def cusum(series: Sequence[float], k: float = CUSUM_K, h: float = CUSUM_H) -> list[int]:
    """CUSUM a un lato per il decadimento: S_t = max(0, S_{t-1} + (k - x_t)). Allarme quando S_t > h,
    poi ripartenza da zero. Ritorna gli indici (0-based) degli allarmi."""
    alarms: list[int] = []
    s = 0.0
    for i, x in enumerate(series):
        s = max(0.0, s + (float(k) - float(x)))
        if s > h:
            alarms.append(i)
            s = 0.0
    return alarms


@dataclass
class GroupSummary:
    key: str
    plays: int
    profit_units: float
    roi: float | None
    roi_lo: float | None
    roi_hi: float | None
    clv: float | None
    alarm_at: int | None

    def to_dict(self, key_name: str) -> dict[str, Any]:
        return {
            key_name: self.key,
            "plays": self.plays,
            "profit_units": self.profit_units,
            "roi": self.roi,
            "roi_lo": self.roi_lo,
            "roi_hi": self.roi_hi,
            "clv": self.clv,
            "alarm": self.alarm_at is not None,
        }


def _order_key(item: Any) -> tuple[str, str]:
    kickoff = _get(item, "kickoff_at", "day", "match_date", default="")
    return (str(kickoff), str(_get(item, "fixture_id", default="")))


def _group_summary(key: str, rows: list[Any], bootstrap_n: int, seed: int) -> GroupSummary:
    base = roi(rows)
    lo, hi = block_bootstrap_ci(rows, n=bootstrap_n, seed=seed)
    ordered = sorted(settled(rows), key=_order_key)
    alarm_at: int | None = None
    if len(ordered) >= CUSUM_MIN_PLAYS:
        alarms = cusum([float(_get(r, "profit_units")) for r in ordered])
        alarm_at = alarms[-1] if alarms else None
    return GroupSummary(
        key=key,
        plays=base["plays"],
        profit_units=base["profit_units"],
        roi=base["roi"],
        roi_lo=lo,
        roi_hi=hi,
        clv=clv_summary(rows)["clv"],
        alarm_at=alarm_at,
    )


def _alert_sentence(scope_label: str, name: str, group: GroupSummary, ordered_rows: list[Any]) -> str:
    when = _get(ordered_rows[group.alarm_at or 0], "day", "match_date", "kickoff_at", default=None) if ordered_rows else None
    when_text = f" dal {str(when)[:10]}" if when else ""
    roi_text = "n.d." if group.roi is None else fmt_pct(group.roi, signed=True)
    return (
        f"{scope_label} {name}: rendimento in calo{when_text} "
        f"({group.plays} giocate, ROI {roi_text}). Ritiro proposto finché il CUSUM non rientra."
    )


def summary(
    items: Iterable[Any],
    by: Sequence[str] = ("league_code", "market_family"),
    bootstrap_n: int = 500,
    seed: int = 0,
) -> dict[str, Any]:
    """Forma di `GET /measure/summary` (docs/v4/API.md): `by_league`, `by_market`, `totals`, `alerts`.
    Le voci non regolate contano solo per il CLV."""
    rows = list(items)
    total_roi = roi(rows)
    lo, hi = block_bootstrap_ci(rows, n=bootstrap_n, seed=seed)
    totals = {
        "plays": total_roi["plays"],
        "profit_units": total_roi["profit_units"],
        "roi": total_roi["roi"],
        "roi_lo": lo,
        "roi_hi": hi,
        "clv": clv_summary(rows)["clv"],
    }

    out: dict[str, Any] = {"by_league": [], "by_market": [], "totals": totals, "alerts": []}
    for dim in by:
        names = ("league_code",) if dim == "league_code" else ("family", "market_family")
        groups: dict[str, list[Any]] = defaultdict(list)
        for r in rows:
            key = _get(r, *names)
            if key is not None:
                groups[str(key)].append(r)
        target = "by_league" if dim == "league_code" else "by_market"
        key_name = "league_code" if dim == "league_code" else "market_family"
        for key in sorted(groups):
            group = _group_summary(key, groups[key], bootstrap_n, seed)
            entry = group.to_dict(key_name)
            if key_name == "market_family":
                entry["label"] = family_label(key)
            out[target].append(entry)
            if group.alarm_at is not None:
                ordered = sorted(settled(groups[key]), key=_order_key)
                scope_label = "Campionato" if key_name == "league_code" else "Mercato"
                name = key if key_name == "league_code" else family_label(key)
                out["alerts"].append(
                    {
                        "scope": "league" if key_name == "league_code" else "market",
                        "key": key,
                        "plays": group.plays,
                        "alarm_at": group.alarm_at,
                        "roi": group.roi,
                        "sentence": _alert_sentence(scope_label, name, group, ordered),
                    }
                )
    return out


def luck_vs_merit(
    goals_payload: dict[str, Any] | None,
    result: dict[str, Any] | None,
    play: dict[str, Any] | None = None,
    outcome: str | None = None,
    home_team: str = "Casa",
    away_team: str = "Ospite",
) -> str:
    """Una frase su fortuna o merito: gol attesi contro reali e, se c'è una giocata, se era l'esito più probabile."""
    if not result or result.get("ft_home") is None or result.get("ft_away") is None:
        return "Risultato non ancora disponibile."
    ft_home, ft_away = int(result["ft_home"]), int(result["ft_away"])
    parts: list[str] = []
    lam_home = (goals_payload or {}).get("lambda_home")
    lam_away = (goals_payload or {}).get("lambda_away")
    if lam_home is not None and lam_away is not None:
        diff = (ft_home + ft_away) - (float(lam_home) + float(lam_away))
        if abs(diff) <= 1.0:
            parts.append(
                f"Gol attesi {fmt_num(lam_home)} per {home_team} e {fmt_num(lam_away)} per {away_team}, reali {ft_home}-{ft_away}: risultato in linea con le attese."
            )
        elif diff > 0:
            parts.append(
                f"Gol attesi {fmt_num(lam_home)} e {fmt_num(lam_away)}, reali {ft_home}-{ft_away}: più gol del previsto, partita sopra le attese."
            )
        else:
            parts.append(
                f"Gol attesi {fmt_num(lam_home)} e {fmt_num(lam_away)}, reali {ft_home}-{ft_away}: meno gol del previsto, partita sotto le attese."
            )
    if play and outcome:
        p = float(play.get("p_prudent") or play.get("p") or 0.0)
        likely = p >= 0.5
        if outcome in ("vinta", "mezza_vinta"):
            parts.append("Giocata vinta con merito: era l'esito più probabile." if likely else "Giocata vinta con una parte di fortuna: era l'esito meno probabile, pagato dalla quota.")
        elif outcome in ("persa", "mezza_persa"):
            parts.append("Giocata persa con sfortuna: era l'esito più probabile." if likely else "Giocata persa: la quota copriva un esito meno probabile, è andata dall'altra parte.")
        else:
            parts.append("Giocata rimborsata.")
    return " ".join(parts) if parts else "Nessun confronto disponibile."
