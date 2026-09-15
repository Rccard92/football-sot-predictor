"""Osservazione live per modello: le giocate indicate da ogni modello e come stanno andando.

Due strade per ogni modello, sempre separate (scelta utente "C"):
- indice: predizioni dell'Indice di Acquistabilita' con punteggio >= 70; giocata = quota Bet365 >= 1,50;
- pattern: un segnale per mercato con quota per partita (piu' pattern sullo stesso mercato = uno solo);
  i pattern con condizioni sulla quota del bookmaker restano in un blocco a parte.
Profitto sempre a 1 unita' per giocata alla quota registrata prima della partita.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from typing import Any

from sqlalchemy.orm import Session

from app.models.cecchino_live_prediction import LIVE_STATUS_SETTLED, CecchinoLivePrediction
from app.services.cecchino_live.observation import group_active_patterns, markets_conflict

INDEX_MIN_SCORE = 70.0
PLAYABLE_MIN_QUOTA = 1.50
SAMPLE_EARLY = 100  # sotto: "presto per dirlo"
SAMPLE_RELIABLE = 300  # da qui: "affidabile"
SCORE_BANDS = tuple((f"{lo}-{lo + 10}", float(lo), float(lo + 10) if lo < 90 else 100.01) for lo in range(0, 100, 10))
FAMILY_LABELS = {"esito": "Esito finale", "primo_tempo": "Primo tempo", "gol": "Gol (Over/Under)"}


def market_family(key: str) -> str:
    if key.endswith("_PT"):
        return "primo_tempo"
    if key.startswith(("OVER_", "UNDER_")):
        return "gol"
    return "esito"


def sample_label(closed: int) -> str:
    if closed < SAMPLE_EARLY:
        return "presto per dirlo"
    if closed < SAMPLE_RELIABLE:
        return "indicativo"
    return "affidabile"


class Tally:
    """Giocate, vinte/perse e profitto a 1 unita'."""

    def __init__(self) -> None:
        self.plays = 0
        self.won = 0
        self.lost = 0
        self.pending = 0
        self.priced = 0
        self.profit = 0.0
        self._quota = 0.0

    def add(self, won: bool | None, quota: float | None) -> None:
        self.plays += 1
        if won is None:
            self.pending += 1
            return
        if won:
            self.won += 1
        else:
            self.lost += 1
        if quota:
            self.priced += 1
            self._quota += float(quota)
            self.profit += float(quota) - 1.0 if won else -1.0

    def to_dict(self) -> dict[str, Any]:
        closed = self.won + self.lost
        return {
            "plays": self.plays,
            "closed": closed,
            "pending": self.pending,
            "won": self.won,
            "lost": self.lost,
            "won_pct": round(100.0 * self.won / closed, 1) if closed else None,
            "roi_pct": round(100.0 * self.profit / self.priced, 1) if self.priced else None,
            "profit": round(self.profit, 2),
            "avg_quota": round(self._quota / self.priced, 2) if self.priced else None,
            "sample": sample_label(closed),
        }


def _won(pred: CecchinoLivePrediction, key: str) -> bool | None:
    if pred.status != LIVE_STATUS_SETTLED:
        return None
    return (((pred.result_json or {}).get("markets") or {}).get(key) or {}).get("won")


def _annotated_patterns(db: Session, pred: CecchinoLivePrediction) -> list[dict[str, Any]]:
    from app.services.cecchino_live.pattern_signals import annotate_book_conditions

    block = {"active": [dict(p) for p in (((pred.modules_json or {}).get("patterns") or {}).get("active") or [])]}
    try:
        annotate_book_conditions(db, pred.model, block)
    except Exception:  # noqa: BLE001 - senza annotazione valgono come costruiti sui moduli
        pass
    return block["active"]


class ModelBook:
    def __init__(self) -> None:
        self.index_all = Tally()  # tutte le predizioni 70+ (anche quota sotto 1,50)
        self.index = Tally()  # giocate: 70+ con quota >= 1,50
        self.index_last7 = Tally()
        self.index_bands = {label: Tally() for label, _, _ in SCORE_BANDS}  # tutte le righe con punteggio
        self.index_by_pattern = {k: Tally() for k in ("confermate", "in_contrasto", "altri_pattern", "senza_pattern")}
        self.index_top = {"90-100": Tally(), "70-90": Tally()}
        self.index_by_market: dict[str, Tally] = defaultdict(Tally)
        self.index_by_family: dict[str, Tally] = defaultdict(Tally)
        self.index_by_league: dict[str, Tally] = defaultdict(Tally)
        self.index_available = False
        self.pattern = Tally()
        self.pattern_last7 = Tally()
        self.pattern_book = Tally()
        self.pattern_by_market: dict[str, dict[str, Any]] = {}
        self.pattern_by_family: dict[str, Tally] = defaultdict(Tally)
        self.pattern_by_league: dict[str, Tally] = defaultdict(Tally)
        self.pattern_concordance = {label: Tally() for label in ("1 pattern", "2-4 pattern", "5+ pattern")}
        self.days: dict[date, dict[str, Any]] = {}

    def day(self, d: date) -> dict[str, Any]:
        item = self.days.get(d)
        if item is None:
            item = self.days[d] = {"index": Tally(), "pattern": Tally(), "fixtures": []}
        return item


def _concordance(n: int) -> str:
    return "1 pattern" if n <= 1 else "2-4 pattern" if n <= 4 else "5+ pattern"


def models_overview(db: Session, rows: list[CecchinoLivePrediction], *, today: date | None = None) -> dict[str, Any]:
    today = today or date.today()
    last7_from = today - timedelta(days=6)
    books: dict[str, ModelBook] = defaultdict(ModelBook)
    index_scores: dict[tuple[int, str], dict[str, tuple[float, bool | None, float | None]]] = defaultdict(dict)

    for r in rows:
        book = books[r.model]
        modules = r.modules_json or {}
        league = " · ".join(x for x in (getattr(r, "country_name", None), getattr(r, "league_name", None)) if x) or "—"
        day = book.day(r.scan_date)
        fixture_item: dict[str, Any] = {
            "today_fixture_id": int(r.today_fixture_id),
            "match": f"{getattr(r, 'home_team_name', None) or '—'} - {getattr(r, 'away_team_name', None) or '—'}",
            "league": league,
            "kickoff": r.kickoff.isoformat() if getattr(r, "kickoff", None) else None,
            "status": r.status,
            "score": (r.result_json or {}).get("score"),
            "index": [],
            "patterns": [],
        }

        # --- pattern con quota: un segnale per mercato ---
        active = _annotated_patterns(db, r)
        market_active = [p for p in active if p.get("target_type") == "market"]
        clean_markets = {str(p["target_key"]) for p in market_active if not p.get("uses_book")}
        for uses_book in (False, True):
            subset = [p for p in market_active if bool(p.get("uses_book")) == uses_book]
            for g in group_active_patterns(subset):
                key = str(g["target_key"])
                won = _won(r, key)
                quota = g.get("quota_book")
                if uses_book:
                    book.pattern_book.add(won, quota)
                    continue
                book.pattern.add(won, quota)
                if r.scan_date >= last7_from:
                    book.pattern_last7.add(won, quota)
                entry = book.pattern_by_market.setdefault(
                    key, {"market_key": key, "tally": Tally(), "_hist_win": [], "_hist_roi": []}
                )
                entry["tally"].add(won, quota)
                if g.get("hist_win_rate_pct") is not None:
                    entry["_hist_win"].append(float(g["hist_win_rate_pct"]))
                if g.get("hist_roi_pct_best") is not None:
                    entry["_hist_roi"].append(float(g["hist_roi_pct_best"]))
                book.pattern_by_family[market_family(key)].add(won, quota)
                book.pattern_by_league[league].add(won, quota)
                book.pattern_concordance[_concordance(int(g["patterns_count"]))].add(won, quota)
                day["pattern"].add(won, quota)
                fixture_item["patterns"].append(
                    {"market_key": key, "patterns": int(g["patterns_count"]), "quota": quota, "won": won}
                )

        # --- indice di acquistabilita' ---
        index = modules.get("purchasability_index") or {}
        if index.get("status") == "ok":
            book.index_available = True
            for key, m in (index.get("markets") or {}).items():
                score = float(m.get("score") or 0.0)
                quota = m.get("quota")
                won = _won(r, key)
                index_scores[(int(r.today_fixture_id), key)][r.model] = (score, won, quota)
                for label, lo, hi in SCORE_BANDS:
                    if lo <= score < hi:
                        book.index_bands[label].add(won, quota)
                if score < INDEX_MIN_SCORE:
                    continue
                book.index_all.add(won, quota)
                playable = quota is not None and float(quota) >= PLAYABLE_MIN_QUOTA
                if key in clean_markets:
                    bucket = "confermate"
                elif any(markets_conflict(key, other) for other in clean_markets):
                    bucket = "in_contrasto"
                elif clean_markets:
                    bucket = "altri_pattern"
                else:
                    bucket = "senza_pattern"
                fixture_item["index"].append(
                    {"market_key": key, "score": round(score, 1), "quota": quota, "playable": playable, "won": won, "pattern": bucket}
                )
                if not playable:
                    continue
                book.index.add(won, quota)
                if r.scan_date >= last7_from:
                    book.index_last7.add(won, quota)
                book.index_by_pattern[bucket].add(won, quota)
                book.index_top["90-100" if score >= 90 else "70-90"].add(won, quota)
                book.index_by_market[key].add(won, quota)
                book.index_by_family[market_family(key)].add(won, quota)
                book.index_by_league[league].add(won, quota)
                day["index"].add(won, quota)

        if fixture_item["index"] or fixture_item["patterns"]:
            day["fixtures"].append(fixture_item)

    return {
        "thresholds": {
            "index_min_score": INDEX_MIN_SCORE,
            "playable_min_quota": PLAYABLE_MIN_QUOTA,
            "sample_early": SAMPLE_EARLY,
            "sample_reliable": SAMPLE_RELIABLE,
        },
        "models": {model: _serialize(book) for model, book in sorted(books.items())},
        "agreement": _agreement(index_scores),
    }


def _ranked(tallies: dict[str, Tally], label: dict[str, str] | None = None) -> list[dict[str, Any]]:
    out = [{"key": k, "label": (label or {}).get(k, k), **t.to_dict()} for k, t in tallies.items() if t.plays]
    out.sort(key=lambda x: (-(x["closed"] or 0), x["key"]))
    return out


def _serialize(book: ModelBook) -> dict[str, Any]:
    running_index = 0.0
    running_pattern = 0.0
    daily = []
    for d in sorted(book.days):
        item = book.days[d]
        idx, pat = item["index"].to_dict(), item["pattern"].to_dict()
        running_index += idx["profit"]
        running_pattern += pat["profit"]
        daily.append(
            {
                "scan_date": d.isoformat(),
                "index": idx,
                "pattern": pat,
                "cumulative_index_profit": round(running_index, 2),
                "cumulative_pattern_profit": round(running_pattern, 2),
                "fixtures": sorted(item["fixtures"], key=lambda f: f["kickoff"] or ""),
            }
        )
    pattern_markets = []
    for entry in book.pattern_by_market.values():
        hist_win, hist_roi = entry["_hist_win"], entry["_hist_roi"]
        pattern_markets.append(
            {
                "key": entry["market_key"],
                "label": entry["market_key"],
                **entry["tally"].to_dict(),
                "hist_win_pct": round(sum(hist_win) / len(hist_win), 1) if hist_win else None,
                "hist_roi_pct": round(sum(hist_roi) / len(hist_roi), 1) if hist_roi else None,
            }
        )
    pattern_markets.sort(key=lambda x: (-(x["closed"] or 0), x["key"]))
    return {
        "index": {
            "available": book.index_available,
            "plays": book.index.to_dict(),
            "all_predictions": book.index_all.to_dict(),
            "last7": book.index_last7.to_dict(),
            "top": {k: t.to_dict() for k, t in book.index_top.items()},
            "by_pattern": {k: t.to_dict() for k, t in book.index_by_pattern.items()},
            "bands": [{"key": k, **t.to_dict()} for k, t in book.index_bands.items()],
            "by_market": _ranked(book.index_by_market),
            "by_family": _ranked(book.index_by_family, FAMILY_LABELS),
            "by_league": _ranked(book.index_by_league),
        },
        "patterns": {
            "plays": book.pattern.to_dict(),
            "last7": book.pattern_last7.to_dict(),
            "with_book_conditions": book.pattern_book.to_dict(),
            "by_market": pattern_markets,
            "by_family": _ranked(book.pattern_by_family, FAMILY_LABELS),
            "by_league": _ranked(book.pattern_by_league),
            "concordance": [{"key": k, **t.to_dict()} for k, t in book.pattern_concordance.items()],
        },
        "daily": daily,
    }


def _agreement(index_scores: dict[tuple[int, str], dict[str, tuple[float, bool | None, float | None]]]) -> dict[str, Any]:
    """V2.5 e V3 sulla stessa partita e mercato: giocate con quota >= 1,50."""
    groups = {
        "entrambi_90+": Tally(),
        "entrambi_70+": Tally(),
        "V3_90+_e_V2.5_sotto_50": Tally(),
        "V2.5_90+_e_V3_sotto_50": Tally(),
    }
    for scores in index_scores.values():
        a, b = scores.get("V2.5"), scores.get("V3")
        if a is None or b is None:
            continue
        s25, s3 = a[0], b[0]
        won, quota = b[1] if b[1] is not None else a[1], b[2] if b[2] is not None else a[2]
        if quota is None or float(quota) < PLAYABLE_MIN_QUOTA:
            continue
        if s25 >= 90 and s3 >= 90:
            groups["entrambi_90+"].add(won, quota)
        if s25 >= INDEX_MIN_SCORE and s3 >= INDEX_MIN_SCORE:
            groups["entrambi_70+"].add(won, quota)
        if s3 >= 90 and s25 < 50:
            groups["V3_90+_e_V2.5_sotto_50"].add(won, quota)
        if s25 >= 90 and s3 < 50:
            groups["V2.5_90+_e_V3_sotto_50"].add(won, quota)
    return {k: t.to_dict() for k, t in groups.items()}
