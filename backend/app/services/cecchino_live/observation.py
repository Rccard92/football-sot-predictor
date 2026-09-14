"""Osservazione live (Step 7): motori e pattern Master misurati giorno per giorno.

- Motori: precisione solo sulle partite chiuse per tutti i motori presenti (confronto onesto),
  con le quote Bet365 senza margine come metro di paragone.
- Pattern: raggruppati per mercato (stesso mercato, linea e direzione = un solo segnale per
  partita, con il numero di pattern concordi), esito live confrontato con lo storico 4/4.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.cecchino_live_prediction import LIVE_STATUS_SETTLED, CecchinoLivePrediction

BOOK_REFERENCE = "Bet365"
_1X2 = ("HOME", "DRAW", "AWAY")
_OU25 = ("OVER_2_5", "UNDER_2_5")
_FAMILIES = {
    "1X2": _1X2,
    "Doppia chance": ("ONE_X", "X_TWO", "ONE_TWO"),
    "1X2 primo tempo": ("HOME_PT", "DRAW_PT", "AWAY_PT"),
    "Over/Under 2.5": _OU25,
}
# Fasce di concordanza: quanti pattern Master indicano lo stesso segnale sulla partita.
CONCORDANCE_BANDS = ((1, 1, "1 pattern"), (2, 4, "2-4 pattern"), (5, 19, "5-19 pattern"), (20, None, "20+ pattern"))


# ---------------------------------------------------------------------------
# Raggruppamento pattern accesi
# ---------------------------------------------------------------------------


def pattern_group_key(p: dict[str, Any]) -> str:
    threshold = p.get("threshold")
    th = "" if threshold is None else f"{float(threshold):g}"
    return f"{p.get('target_type')}|{p.get('target_key')}|{th}|{int(p.get('direction') or 1)}"


def _mean(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 2) if values else None


def group_active_patterns(active: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """Un gruppo per mercato/linea/direzione: i pattern dello stesso gruppo danno lo stesso esito."""
    groups: dict[str, dict[str, Any]] = {}
    for p in active or []:
        key = pattern_group_key(p)
        g = groups.get(key)
        if g is None:
            g = groups[key] = {
                "key": key,
                "target_type": p.get("target_type"),
                "target_key": p.get("target_key"),
                "threshold": p.get("threshold"),
                "direction": int(p.get("direction") or 1),
                "market_label": p.get("market_label"),
                "quota_book": p.get("quota_book"),
                "pattern_ids": [],
                "_win": [],
                "_roi": [],
                "_dev": [],
                "max_total_n": 0,
            }
        g["pattern_ids"].append(int(p["id"]))
        if p.get("win_rate_pct") is not None:
            g["_win"].append(float(p["win_rate_pct"]))
        if p.get("roi_pct") is not None:
            g["_roi"].append(float(p["roi_pct"]))
        if p.get("avg_deviation_pct") is not None:
            g["_dev"].append(float(p["avg_deviation_pct"]))
        g["max_total_n"] = max(int(g["max_total_n"]), int(p.get("total_n") or 0))
    out = []
    for g in groups.values():
        win, roi, dev = g.pop("_win"), g.pop("_roi"), g.pop("_dev")
        g["patterns_count"] = len(g["pattern_ids"])
        g["hist_win_rate_pct"] = _mean(win)
        g["hist_roi_pct_best"] = round(max(roi), 2) if roi else None
        g["hist_deviation_pct"] = _mean(dev)
        out.append(g)
    out.sort(key=lambda g: (g["target_type"] != "market", -g["patterns_count"], str(g["market_label"])))
    return out


def group_outcome(pred: CecchinoLivePrediction, group: dict[str, Any]) -> dict[str, Any]:
    """Esito del gruppo sulla partita: mercato dal risultato quote, senza quota dai pattern."""
    result = pred.result_json or {}
    if group["target_type"] == "market":
        r = (result.get("markets") or {}).get(str(group["target_key"])) or {}
        return {"won": r.get("won"), "profit": r.get("profit")}
    by_pattern = result.get("patterns") or {}
    for pid in group["pattern_ids"]:
        r = by_pattern.get(str(pid)) or {}
        if r.get("won") is not None:
            return {"won": r["won"], "profit": None, "actual": r.get("actual")}
    return {"won": None, "profit": None}


# ---------------------------------------------------------------------------
# Metriche motori
# ---------------------------------------------------------------------------


def _won(pred: CecchinoLivePrediction, key: str) -> bool | None:
    return (((pred.result_json or {}).get("markets") or {}).get(key) or {}).get("won")


def _prob(pred: CecchinoLivePrediction, key: str) -> float | None:
    v = ((pred.markets_json or {}).get(key) or {}).get("probability")
    return None if v is None else float(v)


def book_fair_probabilities(pred: CecchinoLivePrediction, keys: tuple[str, ...]) -> dict[str, float] | None:
    """Probabilita' Bet365 senza margine dalle quote registrate (serve la famiglia completa)."""
    quotas = []
    for k in keys:
        q = ((pred.markets_json or {}).get(k) or {}).get("quota_book")
        if q is None or float(q) <= 1.0:
            return None
        quotas.append(float(q))
    inv = [1.0 / q for q in quotas]
    total = sum(inv)
    return {k: v / total for k, v in zip(keys, inv)}


class _Acc:
    """Accumulatore Brier (per selezione) e colpi del favorito per una famiglia."""

    def __init__(self) -> None:
        self.rows = 0
        self.brier = 0.0
        self.fixtures = 0
        self.hits = 0

    def add(self, probs: dict[str, float | None], outcomes: dict[str, bool | None]) -> None:
        if any(v is None for v in probs.values()) or any(outcomes.get(k) is None for k in probs):
            return
        for k, p in probs.items():
            self.rows += 1
            self.brier += (float(p) - (1.0 if outcomes[k] else 0.0)) ** 2
        favourite = max(probs, key=lambda k: float(probs[k] or 0.0))
        self.fixtures += 1
        self.hits += 1 if outcomes[favourite] else 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "fixtures": self.fixtures,
            "brier": round(self.brier / self.rows, 5) if self.rows else None,
            "favourite_hit_pct": round(100.0 * self.hits / self.fixtures, 1) if self.fixtures else None,
        }


def _engine_block(preds_by_fixture: list[dict[str, CecchinoLivePrediction]], models: list[str]) -> dict[str, Any]:
    accs: dict[str, dict[str, _Acc]] = {m: {f: _Acc() for f in _FAMILIES} for m in [*models, BOOK_REFERENCE]}
    for fixture in preds_by_fixture:
        reference = fixture.get("V2.5") or next(iter(fixture.values()))
        for fam, keys in _FAMILIES.items():
            outcomes = {k: _won(reference, k) for k in keys}
            for m in models:
                accs[m][fam].add({k: _prob(fixture[m], k) for k in keys}, outcomes)
            if fam in ("1X2", "Over/Under 2.5"):
                fair = book_fair_probabilities(reference, keys)
                if fair is not None:
                    accs[BOOK_REFERENCE][fam].add(fair, outcomes)
    return {m: {fam: acc.to_dict() for fam, acc in fams.items()} for m, fams in accs.items()}


# ---------------------------------------------------------------------------
# Cruscotto
# ---------------------------------------------------------------------------


def observation_dashboard(db: Session, *, date_from: date | None = None, date_to: date | None = None) -> dict[str, Any]:
    q = select(CecchinoLivePrediction)
    if date_from is not None:
        q = q.where(CecchinoLivePrediction.scan_date >= date_from)
    if date_to is not None:
        q = q.where(CecchinoLivePrediction.scan_date <= date_to)
    rows = list(db.scalars(q.order_by(CecchinoLivePrediction.scan_date, CecchinoLivePrediction.id)).all())

    models = sorted({r.model for r in rows})
    settled = [r for r in rows if r.status == LIVE_STATUS_SETTLED]
    by_fixture: dict[int, dict[str, CecchinoLivePrediction]] = defaultdict(dict)
    for r in settled:
        by_fixture[int(r.today_fixture_id)][r.model] = r
    common = [f for f in by_fixture.values() if all(m in f for m in models)]

    # Motori: totale e serie giornaliera cumulata sulle partite comuni.
    common_by_day: dict[date, list[dict[str, CecchinoLivePrediction]]] = defaultdict(list)
    for f in common:
        common_by_day[next(iter(f.values())).scan_date].append(f)
    daily_engines = []
    running: list[dict[str, CecchinoLivePrediction]] = []
    for day in sorted(common_by_day):
        running.extend(common_by_day[day])
        daily_engines.append(
            {
                "scan_date": day.isoformat(),
                "fixtures": len(common_by_day[day]),
                "day": _engine_block(common_by_day[day], models),
                "cumulative_fixtures": len(running),
                "cumulative": _engine_block(running, models),
            }
        )

    # Pattern: gruppi per mercato e singoli pattern.
    groups: dict[str, dict[str, Any]] = {}
    patterns: dict[int, dict[str, Any]] = {}
    bands = {label: {"band": label, "signals": 0, "won": 0, "lost": 0} for *_r, label in CONCORDANCE_BANDS}
    days: dict[date, dict[str, Any]] = {}
    fixtures_seen: dict[date, set[int]] = defaultdict(set)
    fixtures_settled: dict[date, set[int]] = defaultdict(set)

    for r in rows:
        fixtures_seen[r.scan_date].add(int(r.today_fixture_id))
        if r.status == LIVE_STATUS_SETTLED:
            fixtures_settled[r.scan_date].add(int(r.today_fixture_id))
        day = days.setdefault(
            r.scan_date,
            {"scan_date": r.scan_date.isoformat(), "patterns_active": 0, "groups_active": 0, "groups_won": 0, "groups_lost": 0, "groups_pending": 0},
        )
        active = (((r.modules_json or {}).get("patterns") or {}).get("active")) or []
        if not active:
            continue
        by_id = {int(p["id"]): p for p in active}
        day["patterns_active"] += len(active)
        for g in group_active_patterns(active):
            outcome = group_outcome(r, g) if r.status == LIVE_STATUS_SETTLED else {"won": None, "profit": None}
            won = outcome.get("won")
            day["groups_active"] += 1
            if won is None:
                day["groups_pending"] += 1
            elif won:
                day["groups_won"] += 1
            else:
                day["groups_lost"] += 1

            agg = groups.setdefault(
                f"{r.model}|{g['key']}",
                {
                    "model": r.model,
                    "key": g["key"],
                    "target_type": g["target_type"],
                    "target_key": g["target_key"],
                    "threshold": g["threshold"],
                    "direction": g["direction"],
                    "market_label": g["market_label"],
                    "signals": 0,
                    "won": 0,
                    "lost": 0,
                    "pending": 0,
                    "profit": 0.0,
                    "priced": 0,
                    "_quota": [],
                    "_patterns": [],
                    "_hist_win": [],
                    "_hist_dev": [],
                },
            )
            agg["signals"] += 1
            agg["_patterns"].append(g["patterns_count"])
            if g["hist_win_rate_pct"] is not None:
                agg["_hist_win"].append(g["hist_win_rate_pct"])
            if g["hist_deviation_pct"] is not None:
                agg["_hist_dev"].append(g["hist_deviation_pct"])
            if g["quota_book"] is not None:
                agg["_quota"].append(float(g["quota_book"]))
            if won is None:
                agg["pending"] += 1
            else:
                agg["won" if won else "lost"] += 1
                if outcome.get("profit") is not None:
                    agg["profit"] += float(outcome["profit"])
                    agg["priced"] += 1
                for lo, hi, label in CONCORDANCE_BANDS:
                    if g["patterns_count"] >= lo and (hi is None or g["patterns_count"] <= hi):
                        bands[label]["signals"] += 1
                        bands[label]["won" if won else "lost"] += 1
                        break

            for pid in g["pattern_ids"]:
                p = by_id[pid]
                pa = patterns.setdefault(
                    pid,
                    {
                        "id": pid,
                        "model": r.model,
                        "target_type": p.get("target_type"),
                        "target_key": p.get("target_key"),
                        "market_label": p.get("market_label"),
                        "conditions_text": p.get("conditions_text"),
                        "total_n": p.get("total_n"),
                        "hist_win_rate_pct": p.get("win_rate_pct"),
                        "hist_roi_pct": p.get("roi_pct"),
                        "hist_deviation_pct": p.get("avg_deviation_pct"),
                        "signals": 0,
                        "won": 0,
                        "lost": 0,
                        "pending": 0,
                        "profit": 0.0,
                        "priced": 0,
                    },
                )
                pa["signals"] += 1
                if won is None:
                    pa["pending"] += 1
                else:
                    pa["won" if won else "lost"] += 1
                    if outcome.get("profit") is not None:
                        pa["profit"] += float(outcome["profit"])
                        pa["priced"] += 1

    def _finish(item: dict[str, Any]) -> dict[str, Any]:
        closed = item["won"] + item["lost"]
        item["win_rate_pct"] = round(100.0 * item["won"] / closed, 1) if closed else None
        item["roi_pct"] = round(100.0 * item["profit"] / item["priced"], 1) if item["priced"] else None
        item["profit"] = round(item["profit"], 2)
        return item

    group_list = []
    for agg in groups.values():
        agg["avg_quota"] = _mean(agg.pop("_quota"))
        agg["avg_patterns"] = _mean([float(x) for x in agg.pop("_patterns")])
        agg["hist_win_rate_pct"] = _mean(agg.pop("_hist_win"))
        agg["hist_deviation_pct"] = _mean(agg.pop("_hist_dev"))
        group_list.append(_finish(agg))
    group_list.sort(key=lambda g: (-g["signals"], g["target_type"] != "market", str(g["market_label"])))

    pattern_list = [_finish(p) for p in patterns.values()]
    pattern_list.sort(key=lambda p: (-(p["won"] + p["lost"]), -p["signals"], p["id"]))

    for label, b in bands.items():
        closed = b["won"] + b["lost"]
        b["win_rate_pct"] = round(100.0 * b["won"] / closed, 1) if closed else None

    day_list = []
    for d in sorted(days, reverse=True):
        item = days[d]
        item["fixtures"] = len(fixtures_seen[d])
        item["fixtures_settled"] = len(fixtures_settled[d])
        day_list.append(item)

    return {
        "date_from": date_from.isoformat() if date_from else None,
        "date_to": date_to.isoformat() if date_to else None,
        "models": models,
        "book_reference": BOOK_REFERENCE,
        "totals": {
            "fixtures": len({int(r.today_fixture_id) for r in rows}),
            "fixtures_settled": len(by_fixture),
            "common_fixtures": len(common),
            "predictions_by_model": {m: sum(1 for r in rows if r.model == m) for m in models},
            "settled_by_model": {m: sum(1 for r in settled if r.model == m) for m in models},
            "signals": sum(g["signals"] for g in group_list),
            "signals_closed": sum(g["won"] + g["lost"] for g in group_list),
        },
        "engines": _engine_block(common, models),
        "engines_daily": daily_engines,
        "pattern_groups": group_list,
        "patterns": pattern_list[:300],
        "patterns_total": len(pattern_list),
        "concordance": list(bands.values()),
        "days": day_list,
    }
