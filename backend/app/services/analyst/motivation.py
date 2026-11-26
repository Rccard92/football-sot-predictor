"""Avvisi di calendario e motivazione nella testata del Diario (capitolato di Giovanni del 24/11/2026, modifica 17).

Solo informazione: non cambiano nessuno stato dei segni.

A · gara ravvicinata: una delle due squadre ha giocato da 2 giorni o meno, rigioca entro 2 giorni o ha gia'
    2 gare negli ultimi 7 giorni (calendario con le coppe).
B · fine campionato: quando a una delle due squadre restano 8 gare o meno. Per ogni squadra il primo stato vero:
    "posizione decisa" (la posizione migliore e la peggiore ancora possibili stanno nella stessa fascia: titolo,
    coppe/promozione/play-off, centro, zona pericolo; a pari punti la posizione resta aperta, salvo il Brasile
    dove lo spareggio e' per vittorie), "in lotta per ..." (puo' ancora raggiungere i punti della posizione
    dell'obiettivo), "in lotta per la salvezza" (ha 3 x gare che restano punti o meno sopra la prima posizione
    della zona pericolo), "senza obiettivi". Le fasce vengono dalla descrizione delle posizioni del fornitore;
    senza descrizione: "motivazione n.d.".
C · avvisi "pietra" con il testo esatto del capitolato (P27, casa motivata, ipotesi 2, gara senza motivazioni,
    possibile turnover).
"""

from __future__ import annotations

from typing import Any

LAST_ROUNDS = 8
MIDDLE_NONE_GAP = 6  # 26/11/2026: centro deciso a piu' di 6 punti da entrambe le zone = "senza obiettivi" (None = regola del 24/11)
CLOSE_DAYS = 2
CUP_TURNOVER_DAYS = 4

ZONE_TITLE = "titolo"
ZONE_GOAL = "obiettivo"
ZONE_MIDDLE = "centro"
ZONE_DANGER = "pericolo"

_DANGER_WORDS = ("relegat", "play-out", "playout", "play out", "abstieg", "descenso", "rebaixamento", "retroced")
_GOAL_WORDS = (
    "champions", "europa", "conference", "libertadores", "sudamericana", "promotion", "promoted", "play-off", "playoff",
    "play off", "qualification", "qualif", "final series", "championship round", "cup", "promozione", "ascenso",
)

STATUS_DECIDED = "decisa"
STATUS_GOAL = "lotta"
STATUS_SAFETY = "salvezza"
STATUS_NONE = "senza"


def zone_of(description: str | None) -> str:
    d = (description or "").lower()
    if any(w in d for w in _DANGER_WORDS):
        return ZONE_DANGER
    if any(w in d for w in _GOAL_WORDS):
        return ZONE_GOAL
    return ZONE_MIDDLE


def goal_words(description: str | None) -> str:
    d = (description or "").lower()
    if "play" in d:
        return "i play-off"
    if "promot" in d or "promozione" in d or "ascenso" in d:
        return "la promozione"
    return "le coppe"


def fasce(zones: dict[str, Any] | None, teams: int) -> list[str] | None:
    """Fascia di ogni posizione (indice 0 = 1ª). None se mancano le descrizioni."""
    if not zones or teams < 2:
        return None
    out = []
    for rank in range(1, teams + 1):
        if rank == 1:
            out.append(ZONE_TITLE)
            continue
        out.append(zone_of(zones.get(str(rank))))
    if ZONE_GOAL not in out and ZONE_DANGER not in out:
        return None  # nessuna descrizione utile: non si inventa
    return out


def _can_reach(points: int, left: int, target_points: int) -> bool:
    return points + 3 * left >= target_points


def team_status(
    team_id: int,
    table: list[dict[str, Any]],
    left: dict[int, int],
    zones: list[str],
    *,
    descriptions: dict[str, Any],
    wins_tiebreak: bool = False,
    middle_none_gap: int | None = MIDDLE_NONE_GAP,
) -> dict[str, Any] | None:
    """Stato di motivazione di una squadra con la classifica alla data (rank, points, won) e le gare che restano."""
    me = next((r for r in table if int(r["team_id"]) == int(team_id)), None)
    if me is None or int(team_id) not in left:
        return None
    p, w, r = int(me["points"]), int(me.get("won") or 0), int(left[int(team_id)])
    others = [t for t in table if int(t["team_id"]) != int(team_id)]
    # posizione migliore: davanti restano solo le squadre che non si possono piu' prendere
    ahead = 0
    for t in others:
        pt = int(t["points"])
        if pt > p + 3 * r or (wins_tiebreak and pt == p + 3 * r and int(t.get("won") or 0) > w + r):
            ahead += 1
    # posizione peggiore: dietro restano solo le squadre che non possono piu' arrivare ai nostri punti
    can_pass = 0
    for t in others:
        rt = int(left.get(int(t["team_id"]), 0))
        top = int(t["points"]) + 3 * rt
        if top > p or (top == p and (not wins_tiebreak or int(t.get("won") or 0) + rt >= w)):
            can_pass += 1
    best, worst = ahead + 1, can_pass + 1
    n = len(zones)
    best, worst = min(best, n), min(worst, n)
    by_rank = {int(t["rank"]): t for t in table}
    rank = int(me["rank"])
    goal_ranks = [i + 1 for i, z in enumerate(zones) if z == ZONE_GOAL] or [1]
    danger_ranks = [i + 1 for i, z in enumerate(zones) if z == ZONE_DANGER]
    goal_holder = by_rank.get(max(goal_ranks))
    danger_holder = by_rank.get(min(danger_ranks)) if danger_ranks else None
    gap_goal = int(goal_holder["points"]) - p if goal_holder is not None else None
    gap_danger = p - int(danger_holder["points"]) if danger_holder is not None else None
    if zones[best - 1] == zones[worst - 1]:
        zone = zones[best - 1]
        # 26/11/2026 (Giovanni): il centro classifica deciso conta come "senza obiettivi" se la squadra e' a piu'
        # di 6 punti sia dalla zona Europa/promozione sia dalla zona retrocessione/playout
        if (
            middle_none_gap is not None
            and zone == ZONE_MIDDLE
            and gap_goal is not None
            and gap_danger is not None
            and gap_goal > middle_none_gap
            and gap_danger > middle_none_gap
        ):
            words = goal_words(descriptions.get(str(max(goal_ranks))))
            return {
                "status": STATUS_NONE,
                "text": f"senza obiettivi (centro classifica deciso: {gap_goal} punti sotto {words}, {gap_danger} sopra la zona retrocessione)",
                "best": best,
                "worst": worst,
                "rank": rank,
            }
        if zone == ZONE_DANGER:
            what = "retrocessa"
        elif best == worst:
            what = "campione" if best == 1 else f"{best}ª"
        elif zone == ZONE_GOAL:
            what = "obiettivo raggiunto"
        else:
            what = "centro classifica"
        return {"status": STATUS_DECIDED, "text": f"posizione decisa ({what})", "best": best, "worst": worst, "rank": rank}
    # in lotta per un obiettivo: la miglior posizione d'obiettivo ancora raggiungibile
    goal_ranks = [i + 1 for i, z in enumerate(zones) if z in (ZONE_TITLE, ZONE_GOAL)]
    for gr in goal_ranks:
        holder = by_rank.get(gr)
        if holder is None or not _can_reach(p, r, int(holder["points"])):
            continue
        if gr == 1:
            words = "il titolo"
            dist = "in vetta" if rank == 1 else f"{int(holder['points']) - p} punti sotto la vetta"
        else:
            words = goal_words(descriptions.get(str(gr)))
            dist = "dentro la zona" if rank <= gr else f"{int(holder['points']) - p} punti sotto {words}"
        return {"status": STATUS_GOAL, "text": f"in lotta per {words} ({dist})", "best": best, "worst": worst, "rank": rank}
    danger_ranks = [i + 1 for i, z in enumerate(zones) if z == ZONE_DANGER]
    if danger_ranks:
        first = by_rank.get(min(danger_ranks))
        if first is not None:
            margin = p - int(first["points"])
            if margin <= 3 * r:
                dist = f"{margin} punti sopra la zona" if rank < min(danger_ranks) else "dentro la zona"
                return {"status": STATUS_SAFETY, "text": f"in lotta per la salvezza ({dist})", "best": best, "worst": worst, "rank": rank}
    bits = []
    goal_last = by_rank.get(max(goal_ranks)) if goal_ranks else None
    if goal_last is not None and len(goal_ranks) > 1:
        bits.append(f"{int(goal_last['points']) - p} punti sotto {goal_words(descriptions.get(str(max(goal_ranks))))}")
    if danger_ranks:
        first = by_rank.get(min(danger_ranks))
        if first is not None:
            bits.append(f"{p - int(first['points'])} sopra la zona retrocessione")
    return {"status": STATUS_NONE, "text": "senza obiettivi" + (f" ({', '.join(bits)})" if bits else ""), "best": best, "worst": worst, "rank": rank}


def _competition(g: dict[str, Any]) -> str:
    return "campionato" if g.get("league_match") else (g.get("competition") or "altra competizione")


def close_games(home: str, away: str, schedule: dict[str, Any] | None) -> dict[str, Any] | None:
    """A · gara ravvicinata (None se non scatta o se il calendario manca)."""
    if not schedule:
        return None
    lines = []
    for name, s in ((home, schedule.get("home")), (away, schedule.get("away"))):
        if not s:
            continue
        bits = []
        last, nxt = s.get("last"), s.get("next")
        if last and last.get("days") is not None and last["days"] <= CLOSE_DAYS:
            bits.append(f"ha giocato {last['days']} giorni fa ({_competition(last)})")
        if int(s.get("games_7") or 0) >= 2:
            bits.append(f"ha {s['games_7']} gare in 7 giorni")
        if nxt and nxt.get("days") is not None and nxt["days"] <= CLOSE_DAYS:
            bits.append(f"gioca di nuovo tra {nxt['days']} giorni ({_competition(nxt)})")
        if bits:
            lines.append(f"{name} " + " e ".join(bits))
    if not lines:
        return None
    return {"code": "ravvicinata", "label": "⚠ gara ravvicinata", "text": " · ".join(lines)}


def motivation_alerts(
    *,
    home: str,
    away: str,
    home_status: dict[str, Any] | None,
    away_status: dict[str, Any] | None,
    remaining: dict[str, Any] | None,
    favorite: str | None,
    schedule: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """C · avvisi pietra (solo con il badge B acceso e le due motivazioni note)."""
    if not home_status or not away_status:
        return []
    out: list[dict[str, Any]] = []
    fighting = (STATUS_GOAL, STATUS_SAFETY)
    hs, as_ = home_status["status"], away_status["status"]
    fav_s = hs if favorite == "home" else as_ if favorite == "away" else None
    other_s = as_ if favorite == "home" else hs if favorite == "away" else None
    if fav_s == STATUS_DECIDED and other_s in fighting:
        out.append(
            {
                "code": "p27",
                "text": "⚠ P27 · favorita senza nulla da giocarsi contro una squadra in lotta: non giocare la favorita, né secca né in doppia chance (storico −9,4% secca, −7,1% doppia chance)",
            }
        )
    if hs in fighting and as_ == STATUS_NONE:
        out.append({"code": "casa_motivata", "text": "⚠ casa motivata, ma il book lo sa già: l'1 non rende (storico −5,2%)"})
    if hs == STATUS_NONE and as_ in fighting:
        out.append({"code": "ipotesi_2", "text": "⚠ non giocare 1 né 1X · ipotesi in prova: 2 (storico +8,9%, non provata)"})
    if hs in (STATUS_NONE, STATUS_DECIDED) and as_ in (STATUS_NONE, STATUS_DECIDED):
        out.append({"code": "senza_motivazioni", "text": "⚠ gara senza motivazioni: risultato poco prevedibile, la X rende meno della quota (storico −9,0%)"})
    for name, st, side in ((home, hs, "home"), (away, as_, "away")):
        nxt = ((schedule or {}).get(side) or {}).get("next") or {}
        if st in (STATUS_NONE, STATUS_DECIDED) and nxt and not nxt.get("league_match") and nxt.get("days") is not None and nxt["days"] <= CUP_TURNOVER_DAYS:
            out.append({"code": "turnover", "text": f"⚠ possibile turnover: {name} gioca {nxt.get('competition') or 'una coppa'} tra {nxt['days']} giorni"})
    return out


def end_of_season(
    *,
    home_id: int,
    away_id: int,
    home: str,
    away: str,
    remaining: dict[str, Any] | None,
    table: list[dict[str, Any]],
    left: dict[int, int] | None,
    zones_row: dict[str, Any] | None,
    country: str | None,
    favorite: str | None,
    schedule: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """B + C. None se a nessuna delle due squadre restano 8 gare o meno."""
    rh, ra = (remaining or {}).get("home"), (remaining or {}).get("away")
    games = [x["games"] for x in (rh, ra) if x and not x.get("phase") and x.get("games") is not None]
    if not games or min(games) > LAST_ROUNDS:
        return None
    n = (rh or {}).get("games") if rh and rh.get("games") is not None else min(games)
    exact = bool((rh or {}).get("exact"))
    label = f"⚑ ultime {n if exact else f'circa {n}'} giornate"
    zones = fasce((zones_row or {}).get("zones"), len(table)) if (zones_row or {}).get("status") == "ok" and (zones_row or {}).get("teams") == len(table) else None
    if zones is None or not left:
        return {"code": "fine", "label": label, "text": "motivazione n.d.", "home": None, "away": None, "alerts": []}
    brazil = (country or "").strip().lower() == "brazil"
    desc = (zones_row or {}).get("zones") or {}
    hs = team_status(home_id, table, left, zones, descriptions=desc, wins_tiebreak=brazil)
    as_ = team_status(away_id, table, left, zones, descriptions=desc, wins_tiebreak=brazil)
    text = " · ".join(f"{name}: {st['text']}" for name, st in ((home, hs), (away, as_)) if st) or "motivazione n.d."
    return {
        "code": "fine",
        "label": label,
        "text": text,
        "home": hs,
        "away": as_,
        "alerts": motivation_alerts(home=home, away=away, home_status=hs, away_status=as_, remaining=remaining, favorite=favorite, schedule=schedule),
    }
