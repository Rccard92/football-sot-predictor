"""Prova storica V5 Valore sull'Under 2,5 (richiesta di Giovanni del 17/11/2026, risposte del 18/11). Sola lettura.

Regole congelate (non si cambiano dopo aver visto i risultati):
- dati: dataset del laboratorio (cecchino_lab_matches), 16 campionati, gare con quota Bet365 Under/Over 2,5 prima
  della gara; stagione 2026/27 = verdetto (mai usata per costruire o tarare V5), 2025/26 = sola conferma
  (gia' usata come esame il 22/10, dichiarato);
- modello: V5 Valore com'e' oggi (versione v5_live_v1_20261022): probabilita' V3 "finale" con i parametri del
  run 11, taratura per fasce di 5 punti stimata su 2021/22-2024/25 (VALORE_CALIBRATION), probabilita' prudente =
  tarata - 1 errore standard. Le gare si calcolano in ordine di data e ognuna usa solo gare giocate prima;
- regola: Under 2,5 se probabilita' prudente x quota Bet365 prima della gara - 1 e' tra 10% e 30% compresi, quota
  tra 1,80 e 2,20 (fascia del protocollo V5, congelata); 1 unita' a giocata;
- confronto: tutti gli Under 2,5 senza filtro e le giocate con valore oltre il 30%.
Per la 2026/27 le probabilita' V3 non sono salvate: si ricalcolano qui con lo stesso codice del V3 dal vivo; prima si
controlla che sulla 2025/26 il ricalcolo coincida con le probabilita' salvate del run 11.
"""

from __future__ import annotations

import logging
import math
import threading
import time
from collections import defaultdict
from datetime import datetime
from statistics import median
from typing import Any
from zoneinfo import ZoneInfo

import numpy as np
from sqlalchemy import select, text

from app.models.cecchino_lab_dataset import CecchinoLabDataset
from app.models.cecchino_lab_match import CecchinoLabMatch
from app.services.cecchino_v3.constants import FINAL_PHASE_MATCHES, MIN_MATCHES_PLAYED, PHASE_EARLY, PHASE_FINAL, PHASE_MID, group_of
from app.services.cecchino_v3.data import _EPOCH, MatchRecord, annotate_season_context, group_matches

logger = logging.getLogger(__name__)

EXAM_VERSION = "v5_valore_u25_exam_20261118"
MARKET = "UNDER_2_5"
CONFIRM = "2025/2026"
VERDICT = "2026/2027"
MIN_Q, MAX_Q = 1.80, 2.20
MIN_VALUE, MAX_VALUE = 0.10, 0.30
BOOT = 4000
SEED = 20261118
ROME = ZoneInfo("Europe/Rome")

_lock = threading.Lock()
_state: dict[str, Any] = {"status": "idle"}


def _int(v: Any) -> int | None:
    return int(v) if v is not None else None


def _float(v: Any) -> float | None:
    try:
        f = float(v) if v not in (None, "") else None
    except (TypeError, ValueError):
        return None
    return f if f and f > 1.0 else None


def load_all(db) -> tuple[list[MatchRecord], dict[int, dict[str, Any]]]:
    """Tutte le gare finite del laboratorio (tutte le stagioni) e le loro quote Over/Under 2,5."""
    rows = db.execute(
        select(CecchinoLabMatch, CecchinoLabDataset.competition_name, CecchinoLabDataset.season_label).join(
            CecchinoLabDataset, CecchinoLabDataset.id == CecchinoLabMatch.dataset_id
        )
    ).all()
    records: list[MatchRecord] = []
    odds: dict[int, dict[str, Any]] = {}
    for lm, comp, season in rows:
        if lm.ft_home_goals is None or lm.ft_away_goals is None or not lm.home_team or not lm.away_team:
            continue
        day = lm.match_date or (lm.kickoff_at.date() if lm.kickoff_at else None)
        if day is None:
            continue
        records.append(
            MatchRecord(
                lab_match_id=int(lm.id), competition=comp, group=group_of(comp), season_label=season, match_date=day,
                kickoff_at=lm.kickoff_at, day=(day - _EPOCH).days, home_team=lm.home_team.strip(), away_team=lm.away_team.strip(),
                ft_home=int(lm.ft_home_goals), ft_away=int(lm.ft_away_goals), ht_home=_int(lm.ht_home_goals), ht_away=_int(lm.ht_away_goals),
                home_shots=_int(lm.home_shots), away_shots=_int(lm.away_shots), home_sot=_int(lm.home_shots_on_target),
                away_sot=_int(lm.away_shots_on_target), home_fouls=_int(lm.home_fouls), away_fouls=_int(lm.away_fouls),
                home_yellow=_int(lm.home_yellow_cards), away_yellow=_int(lm.away_yellow_cards), home_red=_int(lm.home_red_cards),
                away_red=_int(lm.away_red_cards), referee=(lm.referee or "").strip() or None,
            )
        )
        if season in (CONFIRM, VERDICT):
            raw = lm.raw_json or {}
            odds[int(lm.id)] = {
                "season": season, "league": comp, "home": lm.home_team, "away": lm.away_team, "kickoff": lm.kickoff_at, "day": day,
                "qu": _float(lm.bet365_under_25), "qo": _float(lm.bet365_over_25),
                "cu": _float(lm.bet365_closing_under_25), "co": _float(lm.bet365_closing_over_25),
                "pu": _float(raw.get("PC<2.5")), "po": _float(raw.get("PC>2.5")),
                "goals": int(lm.ft_home_goals) + int(lm.ft_away_goals), "score": f"{lm.ft_home_goals}-{lm.ft_away_goals}",
            }
    records.sort(key=lambda m: (m.day, m.kickoff_at or datetime.min, m.lab_match_id))
    annotate_season_context(records)
    _fix_partial_season(records, VERDICT, CONFIRM)
    return records, odds


def _fix_partial_season(records: list[MatchRecord], season: str, previous: str) -> None:
    """Stagione in corso: le "rimanenti" vengono dalla lunghezza della stagione precedente dello stesso campionato
    (come il V3 dal vivo), altrimenti le ultime gare scaricate sembrerebbero la fase finale."""
    per_comp_prev: dict[str, list[int]] = defaultdict(list)
    counts: dict[tuple[str, str], int] = defaultdict(int)
    for m in records:
        if m.season_label == previous:
            counts[(m.competition, m.home_team)] += 1
            counts[(m.competition, m.away_team)] += 1
    for (comp, _team), n in counts.items():
        per_comp_prev[comp].append(n)
    expected = {c: int(median(v)) for c, v in per_comp_prev.items() if v}
    for m in records:
        if m.season_label != season:
            continue
        total = expected.get(m.competition)
        if not total:
            continue
        m.home_remaining = max(total - m.home_played, 1)
        m.away_remaining = max(total - m.away_played, 1)
        if not m.eval_eligible:
            m.phase = PHASE_EARLY
        elif min(m.home_remaining, m.away_remaining) <= FINAL_PHASE_MATCHES:
            m.phase = PHASE_FINAL
        else:
            m.phase = PHASE_MID
    _ = MIN_MATCHES_PLAYED  # stessa soglia di idoneita' del V3 (5 gare per squadra)


def _stored(db) -> dict[int, float]:
    return {
        int(mid): float(p)
        for mid, p in db.execute(
            text("SELECT lab_match_id, probability FROM cecchino_v3_market_predictions WHERE run_id = 11 AND market_key = :m"),
            {"m": MARKET},
        ).all()
    }


def _play_row(mid: int, o: dict[str, Any], p: float, cal: float, prud: float) -> dict[str, Any]:
    won = o["goals"] < 2.5
    qu = o["qu"]

    def novig(u: float | None, ov: float | None) -> float | None:
        if not u or not ov:
            return None
        return qu * (1 / u) / (1 / u + 1 / ov) - 1

    return {
        "lab_match_id": mid,
        "stagione": o["season"],
        "data": o["day"].isoformat(),
        "campionato": o["league"],
        "partita": f"{o['home']} - {o['away']}",
        "prob_v3": round(p, 4),
        "prob_tarata": round(cal, 4),
        "prob_prudente": round(prud, 4),
        "valore": round(prud * qu - 1, 4),
        "b365_pre_under": qu,
        "b365_pre_over": o["qo"],
        "b365_chiusura_under": o["cu"],
        "b365_chiusura_over": o["co"],
        "pinnacle_chiusura_under": o["pu"],
        "pinnacle_chiusura_over": o["po"],
        "gol": o["score"],
        "esito": "vinta" if won else "persa",
        "profitto": round(qu - 1 if won else -1.0, 2),
        "profitto_chiusura": (round(o["cu"] - 1 if won else -1.0, 2)) if o["cu"] else None,
        "clv_b365": round(novig(o["cu"], o["co"]), 4) if novig(o["cu"], o["co"]) is not None else None,
        "clv_pinnacle": round(novig(o["pu"], o["po"]), 4) if novig(o["pu"], o["po"]) is not None else None,
    }


def summarize(rows: list[dict[str, Any]], rng: np.random.Generator | None = None) -> dict[str, Any]:
    if not rows:
        return {"giocate": 0}
    n = len(rows)
    days: dict[str, list[float]] = defaultdict(list)
    for r in rows:
        days[r["data"]].append(r["profitto"])
    out: dict[str, Any] = {
        "giocate": n,
        "giornate": len(days),
        "vinte_pct": round(100 * sum(r["esito"] == "vinta" for r in rows) / n, 1),
        "prob_prudente_media_pct": round(100 * sum(r["prob_prudente"] for r in rows) / n, 1),
        "prob_tarata_media_pct": round(100 * sum(r["prob_tarata"] for r in rows) / n, 1),
        "quota_media": round(sum(r["b365_pre_under"] for r in rows) / n, 2),
        "roi_pre_pct": round(100 * sum(r["profitto"] for r in rows) / n, 1),
    }
    closing = [r["profitto_chiusura"] for r in rows if r["profitto_chiusura"] is not None]
    out["roi_chiusura_pct"] = round(100 * sum(closing) / len(closing), 1) if closing else None
    for key, name in (("clv_b365", "clv_b365"), ("clv_pinnacle", "clv_pinnacle")):
        vals = [r[key] for r in rows if r[key] is not None]
        out[f"{name}_n"] = len(vals)
        out[f"{name}_medio_pct"] = round(100 * sum(vals) / len(vals), 1) if vals else None
        out[f"{name}_positivi_pct"] = round(100 * sum(v > 0 for v in vals) / len(vals), 1) if vals else None
    if rng is not None and len(days) >= 2:
        keys = list(days)
        prof = np.array([sum(days[k]) for k in keys])
        cnt = np.array([len(days[k]) for k in keys])
        idx = rng.integers(0, len(keys), size=(BOOT, len(keys)))
        roi = prof[idx].sum(axis=1) / cnt[idx].sum(axis=1)
        out["roi_ic95_pct"] = [round(100 * float(np.percentile(roi, 2.5)), 1), round(100 * float(np.percentile(roi, 97.5)), 1)]
    return out


def _breakdown(rows: list[dict[str, Any]], key) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        groups[key(r)].append(r)
    return [
        {"chiave": k, "giocate": len(v), "vinte_pct": round(100 * sum(r["esito"] == "vinta" for r in v) / len(v), 1),
         "roi_pct": round(100 * sum(r["profitto"] for r in v) / len(v), 1)}
        for k, v in sorted(groups.items())
    ]


def _band(v: float) -> str:
    return "10-15" if v < 0.15 else "15-20" if v < 0.20 else "20-25" if v < 0.25 else "25-30"


def run_exam() -> dict[str, Any]:
    from app.core.database import SessionLocal
    from app.services.cecchino_v3_live.engine import predict_records
    from app.services.cecchino_v3_live.params import load_params
    from app.services.cecchino_v5.pipeline import valore_probability

    t0 = time.monotonic()
    db = SessionLocal()
    try:
        records, odds = load_all(db)
        params = load_params(db)
        stored = _stored(db)
    finally:
        db.close()
    probs: dict[int, float] = {}
    eligible = {m.lab_match_id for m in records if m.eval_eligible}
    for _group, group_records in group_matches(records).items():
        if not any(m.season_label in (CONFIRM, VERDICT) for m in group_records):
            continue
        finals = predict_records(group_records, params)
        for mid, fin in finals.items():
            if mid in odds and mid in eligible:
                p = (fin.get("probabilities") or {}).get(MARKET)
                if p is not None:
                    probs[mid] = float(p)
    # controllo: sulla 2025/26 il ricalcolo deve coincidere con il run 11 salvato
    diffs = [abs(probs[m] - stored[m]) for m in probs if odds[m]["season"] == CONFIRM and m in stored]
    check = {
        "partite_confrontate": len(diffs),
        "scarto_medio": round(sum(diffs) / len(diffs), 6) if diffs else None,
        "scarto_massimo": round(max(diffs), 6) if diffs else None,
        "nota": "per la 2025/26 si usano le probabilita' salvate del run 11; il ricalcolo serve solo a provare che il codice e' lo stesso",
    }
    rng = np.random.default_rng(SEED)
    result: dict[str, Any] = {"version": EXAM_VERSION, "controllo_ricalcolo": check, "stagioni": {}}
    for season in (VERDICT, CONFIRM):
        everything, plays, over30 = [], [], []
        for mid, o in odds.items():
            if o["season"] != season or o["qu"] is None or mid not in eligible:
                continue
            p = stored.get(mid) if season == CONFIRM else probs.get(mid)
            if p is None:
                continue
            vp = valore_probability(MARKET, p)
            if vp is None:
                continue
            cal, prud = vp
            row = _play_row(mid, o, p, cal, prud)
            everything.append(row)
            value = row["valore"]
            if value > MAX_VALUE:
                over30.append(row)
            if MIN_Q <= o["qu"] <= MAX_Q and MIN_VALUE <= value <= MAX_VALUE:
                plays.append(row)
        plays.sort(key=lambda r: (r["data"], r["lab_match_id"]))
        result["stagioni"][season] = {
            "regola": summarize(plays, rng),
            "tutti_under_senza_filtro": summarize(everything, rng),
            "valore_oltre_30": summarize(over30, rng),
            "per_mese": _breakdown(plays, lambda r: r["data"][:7]),
            "per_campionato": _breakdown(plays, lambda r: r["campionato"]),
            "per_fascia_valore": _breakdown(plays, lambda r: _band(r["valore"])),
            "giocate": plays,
            "ultima_gara": max((o["day"] for o in odds.values() if o["season"] == season), default=None),
        }
    result["seconds"] = round(time.monotonic() - t0, 1)
    _ = math  # (radice quadrata nella taratura, in valore_probability)
    return result


def exam_state(start: bool = False) -> dict[str, Any]:
    with _lock:
        if start and _state.get("status") in ("idle", "failed", "done"):
            _state.clear()
            _state.update({"status": "running", "started_at": time.time()})

            def target() -> None:
                try:
                    result = run_exam()
                    with _lock:
                        _state.update({"status": "done", "result": result, "finished_at": time.time()})
                except Exception as exc:  # noqa: BLE001
                    logger.exception("prova V5 Valore Under 2,5 fallita")
                    with _lock:
                        _state.update({"status": "failed", "error": f"{type(exc).__name__}: {exc}"[:500]})

            threading.Thread(target=target, name="v5-valore-u25-exam", daemon=True).start()
        return dict(_state)
