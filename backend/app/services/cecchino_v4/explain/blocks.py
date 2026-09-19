"""I sei blocchi del Ragionamento (docs/v4/API.md, `FixtureDetail.blocks`) e la scheda partita (`FixtureCard`).

Ogni blocco ha una `sentence` in italiano, generata da regole fisse (nessun modello di linguaggio),
con i numeri scritti all'italiana (virgola decimale, percentuali intere). Funzioni pure.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from app.services.cecchino_v3.markets import score_matrix
from app.services.cecchino_v4.constants import EVIDENCE_FULL_KNOWLEDGE, PROFIT_MARGIN, STATS, VERDICT_DESCRIPTIVE, VERDICT_LABELS
from app.services.cecchino_v4.explain.format import fmt_days, fmt_interval, fmt_num, fmt_pct, fmt_quota, join_it, ordinal
from app.services.cecchino_v4.measure.metrics import luck_vs_merit
from app.services.cecchino_v4.selection.labels import KIND_STAT, parse_market_key
from app.services.cecchino_v4.selection.rules import MarketRow, best_play, no_play_reason
from app.services.cecchino_v4.selection.settlement import profit_units, settle, stat_value

MAX_GOALS_SHOWN = 5  # la mappa dei punteggi mostra 0-5 gol per squadra
EVIDENCE_LITTLE = 5.0  # sotto, la squadra è "conosciuta poco"
FORM_TREND_THRESHOLD = 0.05  # scarto tiri fatto-atteso per parlare di crescita o calo

_SIDE_WORD = {"home": "in casa", "away": "fuori casa"}
_LINEUPS_SENTENCE = {
    "non_note": "Formazioni non ancora note.",
    "probabili": "Formazioni probabili, non ancora ufficiali.",
    "ufficiali": "Formazioni ufficiali.",
}
_LINEUPS_PLAY_SENTENCE = {
    "non_note": "Formazioni non ancora note: la giocata è provvisoria e verrà confermata o ritirata alle formazioni ufficiali.",
    "probabili": "Formazioni probabili: la giocata resta provvisoria fino alle formazioni ufficiali.",
    "ufficiali": "Formazioni ufficiali: la giocata è confermata.",
}
_UNCERTAINTY_SENTENCE = {
    "bassa": "Incertezza bassa: il modello conosce bene entrambe le squadre.",
    "media": "Incertezza media: una delle due squadre è conosciuta solo in parte.",
    "alta": "Incertezza alta: il modello conosce poco almeno una delle due squadre.",
}


def _get(d: dict[str, Any] | None, *path: str, default: Any = None) -> Any:
    cur: Any = d or {}
    for key in path:
        if not isinstance(cur, dict) or key not in cur or cur[key] is None:
            return default
        cur = cur[key]
    return cur


def known_level(evidence: float | None) -> str:
    if evidence is None:
        return "poco"
    if float(evidence) >= EVIDENCE_FULL_KNOWLEDGE:
        return "bene"
    if float(evidence) < EVIDENCE_LITTLE:
        return "poco"
    return "abbastanza"


def form_trend(shots_delta: float | None) -> str | None:
    if shots_delta is None:
        return None
    if float(shots_delta) > FORM_TREND_THRESHOLD:
        return "in crescita"
    if float(shots_delta) < -FORM_TREND_THRESHOLD:
        return "in calo"
    return "stabile"


# --- Blocco 1: chi sono -------------------------------------------------------------
def _team_who(goals: dict[str, Any], side: str, team: str, competition: str | None) -> tuple[dict[str, Any], str]:
    ratings = _get(goals, "ratings", side, default={}) or {}
    evidence = _get(goals, "uncertainty", f"{side}_evidence")
    new_team = bool(_get(goals, "uncertainty", f"new_team_{side}", default=False))
    trend = form_trend(_get(goals, "specialists", "form", f"shots_{side}"))
    known = known_level(evidence)
    if new_team:
        inherited = "squadra nuova nella divisione: forza ereditata dalla piramide nazionale"
    elif evidence is not None and float(evidence) < EVIDENCE_FULL_KNOWLEDGE:
        inherited = "forza in parte ereditata dalla stagione precedente"
    else:
        inherited = "forza stimata sulle partite recenti, con la stagione precedente come base"
    data = {
        "team": team,
        "attack": ratings.get("attack"),
        "defence": ratings.get("defence"),
        "attack_rank": ratings.get("attack_rank"),
        "defence_rank": ratings.get("defence_rank"),
        "teams_in_division": ratings.get("teams_in_division"),
        "home_advantage": ratings.get("home_advantage"),
        "evidence": evidence,
        "known": known,
        "trend": trend,
        "inherited": inherited,
    }
    attack_rank, defence_rank = ratings.get("attack_rank"), ratings.get("defence_rank")
    if attack_rank is None or defence_rank is None:
        sentence = f"{team}: forza non ancora stimata."
    else:
        where = f" della {competition}" if competition else " della divisione"
        trend_text = f" {trend}" if trend in ("in crescita", "in calo") else ""
        known_text = f"conosciuta {known}" + (f" ({fmt_num(evidence, 0)} partite equivalenti)" if evidence is not None else "")
        sentence = f"{team}: {ordinal(attack_rank)} attacco{where}{trend_text}, {ordinal(defence_rank, feminine=True)} difesa, {known_text}."
    return data, sentence


def build_who(goals: dict[str, Any] | None, home_team: str, away_team: str, competition: str | None) -> dict[str, Any]:
    goals = goals or {}
    home, s_home = _team_who(goals, "home", home_team, competition)
    away, s_away = _team_who(goals, "away", away_team, competition)
    return {"sentence": f"{s_home} {s_away}", "home": home, "away": away}


# --- Blocco 2: come giocano -----------------------------------------------------------
def build_how(stats: dict[str, Any] | None, home_team: str, away_team: str) -> dict[str, Any]:
    blocks = _get(stats, "stats", default={}) or {}
    rows: list[dict[str, Any]] = []
    best: tuple[float, dict[str, Any]] | None = None
    for stat, label in STATS.items():
        block = blocks.get(stat)
        if not isinstance(block, dict):
            continue
        home = block.get("home") or {}
        away = block.get("away") or {}
        division_mean = home.get("division_mean", away.get("division_mean"))
        row = {
            "stat": stat,
            "label": label,
            "exam": block.get("exam"),
            "home_for": home.get("mean"),
            "home_against": home.get("mean_against"),
            "away_for": away.get("mean"),
            "away_against": away.get("mean_against"),
            "division_mean": division_mean,
            "home_rank_for": home.get("rank_for"),
            "away_rank_for": away.get("rank_for"),
            "total": _get(block, "total", "mean"),
        }
        rows.append(row)
        if division_mean:
            for side, team in (("home", home_team), ("away", away_team)):
                mean = row[f"{side}_for"]
                if mean is None:
                    continue
                deviation = abs(float(mean) - float(division_mean)) / float(division_mean)
                if best is None or deviation > best[0]:
                    other_against = row["away_against" if side == "home" else "home_against"]
                    other = away_team if side == "home" else home_team
                    best = (deviation, {"team": team, "other": other, "side": side, "mean": mean, "label": label, "division_mean": division_mean, "other_against": other_against, "exam": block.get("exam")})

    if not rows:
        return {"sentence": "Statistiche di squadra non ancora calcolate.", "rows": []}
    if best is None:
        return {"sentence": "Statistiche attese disponibili, senza media di divisione per il confronto.", "rows": rows}
    b = best[1]
    sentence = f"{b['team']}: {fmt_num(b['mean'])} {b['label']} attesi {_SIDE_WORD[b['side']]} contro una media di divisione di {fmt_num(b['division_mean'])}"
    if b["other_against"] is not None:
        sentence += f"; {b['other']} ne concede {fmt_num(b['other_against'])}"
    sentence += "."
    if b["exam"] and b["exam"] != "superato":
        sentence += " Statistica solo descrittiva: esame non superato."
    return {"sentence": sentence, "rows": rows}


# --- Blocco 3: contesto ---------------------------------------------------------------
def build_context(
    goals: dict[str, Any] | None,
    context: dict[str, Any] | None,
    home_team: str,
    away_team: str,
    lineups_status: str,
) -> dict[str, Any]:
    goals = goals or {}
    context = context or {}
    form_raw = _get(goals, "specialists", "form", default={}) or {}
    form = {
        side: {
            "trend": form_trend(form_raw.get(f"shots_{side}")),
            "goals_delta": form_raw.get(f"goals_{side}"),
            "shots_delta": form_raw.get(f"shots_{side}"),
            "matches": form_raw.get(f"matches_{side}"),
        }
        for side in ("home", "away")
    }
    calendar = _get(goals, "specialists", "calendar", default={}) or {}
    rest_in = context.get("rest") or {}
    rest = {
        "home_days": rest_in.get("home_days", calendar.get("rest_days_home")),
        "away_days": rest_in.get("away_days", calendar.get("rest_days_away")),
        "final_phase": calendar.get("final_phase"),
    }
    lineups_in = context.get("lineups") or {}
    lineups = {"status": lineups_in.get("status") or lineups_status, "absences": list(lineups_in.get("absences") or [])}
    motivation = context.get("motivation")
    referee = context.get("referee")

    parts: list[str] = []
    form_bits = []
    for side, team in (("home", home_team), ("away", away_team)):
        trend = form[side]["trend"]
        if trend:
            matches = form[side]["matches"]
            detail = "più tiri del previsto" if trend == "in crescita" else "meno tiri del previsto" if trend == "in calo" else "tiri in linea con le attese"
            form_bits.append(f"{team} {trend}" + (f" nelle ultime {matches} ({detail})" if matches else f" ({detail})"))
    if form_bits:
        parts.append("; ".join(form_bits) + ".")
    if rest["home_days"] is not None or rest["away_days"] is not None:
        parts.append(f"Riposo: {home_team} {fmt_days(rest['home_days'])}, {away_team} {fmt_days(rest['away_days'])}.")
    if motivation:
        text = motivation.get("sentence") if isinstance(motivation, dict) else str(motivation)
        if text:
            parts.append(text if text.endswith(".") else f"{text}.")
    parts.append(_LINEUPS_SENTENCE.get(lineups["status"], "Stato formazioni sconosciuto."))
    if lineups["absences"]:
        by_team: dict[str, list[str]] = {"home": [], "away": []}
        for absence in lineups["absences"]:
            by_team.setdefault(absence.get("team", "home"), []).append(str(absence.get("name", "?")))
        bits = [f"{home_team} senza {join_it(by_team['home'])}" if by_team["home"] else "", f"{away_team} senza {join_it(by_team['away'])}" if by_team["away"] else ""]
        parts.append("Assenze: " + "; ".join(b for b in bits if b) + ".")
    if referee:
        name = referee.get("name") if isinstance(referee, dict) else str(referee)
        if name:
            parts.append(f"Arbitro: {name}.")
    return {"sentence": " ".join(parts), "form": form, "rest": rest, "motivation": motivation, "lineups": lineups, "referee": referee}


# --- Blocco 4: cosa prevede -----------------------------------------------------------
def _rows_sort_key(row: dict[str, Any]) -> tuple[int, float, float]:
    """Prima i mercati con prezzo e verdetto pieno per profitto atteso, poi i solo descrittivi con prezzo, infine i non quotati."""
    ep = row.get("expected_profit")
    if ep is None:
        group = 2
    elif row.get("verdict") == VERDICT_DESCRIPTIVE:
        group = 1
    else:
        group = 0
    return (group, -(ep or 0.0), -float(row.get("p") or 0.0))


def most_likely_sign(rows: list[MarketRow], goals: dict[str, Any] | None) -> dict[str, Any] | None:
    by_key = {r.market_key: r for r in rows}
    candidates = []
    for key, label in (("HOME", "1"), ("DRAW", "X"), ("AWAY", "2")):
        row = by_key.get(key)
        p = row.p if row else _get(goals, "markets", key, "p")
        if p is not None:
            candidates.append({"market_key": key, "label": row.label if row else label, "p": round(float(p), 4)})
    return max(candidates, key=lambda c: c["p"]) if candidates else None


def build_predicts(goals: dict[str, Any] | None, rows: list[MarketRow], home_team: str, away_team: str) -> dict[str, Any]:
    goals = goals or {}
    lam_home, lam_away = goals.get("lambda_home"), goals.get("lambda_away")
    matrix_list: list[list[float]] = []
    most_likely_score: dict[str, Any] | None = None
    if lam_home is not None and lam_away is not None:
        matrix = score_matrix(float(lam_home), float(lam_away), float(goals.get("rho") or 0.0))
        h, a = np.unravel_index(int(np.argmax(matrix)), matrix.shape)
        most_likely_score = {"home": int(h), "away": int(a), "p": round(float(matrix[h, a]), 4)}
        shown = matrix[: MAX_GOALS_SHOWN + 1, : MAX_GOALS_SHOWN + 1]
        matrix_list = [[round(float(x), 4) for x in line] for line in shown]

    sign = most_likely_sign(rows, goals)
    by_key = {r.market_key: r for r in rows}
    over = by_key.get("OVER_2_5")
    p_over = over.p if over else _get(goals, "markets", "OVER_2_5", "p")

    parts: list[str] = []
    if most_likely_score:
        parts.append(f"Risultato più probabile {most_likely_score['home']}-{most_likely_score['away']} ({fmt_pct(most_likely_score['p'])}).")
    if sign:
        parts.append(f"Segno più probabile: {sign['label']} al {fmt_pct(sign['p'])}.")
    if lam_home is not None and lam_away is not None:
        goals_text = f"Gol attesi: {home_team} {fmt_num(lam_home)}, {away_team} {fmt_num(lam_away)}"
        parts.append(goals_text + (f"; over 2,5 al {fmt_pct(p_over)}." if p_over is not None else "."))
    if not parts:
        parts.append("Previsione gol non ancora calcolata.")
    markets = sorted((r.to_dict() for r in rows), key=_rows_sort_key)
    return {
        "sentence": " ".join(parts),
        "score_matrix": matrix_list,
        "max_goals": MAX_GOALS_SHOWN,
        "most_likely_score": most_likely_score,
        "most_likely": sign,
        "expected_goals": {"home": lam_home, "away": lam_away},
        "markets": markets,
    }


# --- Blocco 5: perché si', perché no -------------------------------------------------
def _evidence_sentence(play: MarketRow, goals: dict[str, Any] | None, stats: dict[str, Any] | None, home_team: str, away_team: str) -> str:
    parsed = parse_market_key(play.market_key)
    if parsed.kind == KIND_STAT and parsed.stat:
        label = STATS[parsed.stat]
        block = _get(stats, "stats", parsed.stat, default={}) or {}
        if parsed.side == "total":
            total = _get(block, "total", "mean")
            div_total = _get(block, "total", "division_mean")
            text = f"{label[0].upper()}{label[1:]} totali attesi {fmt_num(total)}"
            if div_total is not None:
                text += f" contro una media di divisione di {fmt_num(div_total)}"
            return text + "."
        side = parsed.side or "home"
        team = home_team if side == "home" else away_team
        other = away_team if side == "home" else home_team
        mean = _get(block, side, "mean")
        div_mean = _get(block, side, "division_mean")
        other_against = _get(block, "away" if side == "home" else "home", "mean_against")
        rank = _get(block, side, "rank_for")
        text = f"{team}: {fmt_num(mean)} {label} attesi {_SIDE_WORD[side]}"
        if div_mean is not None:
            text += f" contro una media di divisione di {fmt_num(div_mean)}"
        if rank is not None:
            text += f" ({ordinal(rank, feminine=True)} squadra della divisione per {label})"
        if other_against is not None:
            text += f"; {other} ne concede {fmt_num(other_against)}"
        return text + "."

    lam_home, lam_away = (goals or {}).get("lambda_home"), (goals or {}).get("lambda_away")
    bits = []
    if lam_home is not None and lam_away is not None:
        bits.append(f"Gol attesi: {home_team} {fmt_num(lam_home)}, {away_team} {fmt_num(lam_away)}")
    ar_home, dr_home = _get(goals, "ratings", "home", "attack_rank"), _get(goals, "ratings", "home", "defence_rank")
    ar_away, dr_away = _get(goals, "ratings", "away", "attack_rank"), _get(goals, "ratings", "away", "defence_rank")
    if None not in (ar_home, dr_home, ar_away, dr_away):
        bits.append(
            f"attacco {home_team} {ordinal(ar_home)} e difesa {ordinal(dr_home, feminine=True)}, attacco {away_team} {ordinal(ar_away)} e difesa {ordinal(dr_away, feminine=True)}"
        )
    return ("; ".join(bits) + ".") if bits else "Previsione dal modello gol."


def _no_play_sentences(reason: str | None, rows: list[MarketRow], goals: dict[str, Any] | None, home_team: str, away_team: str) -> list[str]:
    if not rows:
        return ["Nessuna giocata: nessun mercato calcolato per questa partita."]
    if reason == "non_quotato":
        return ["Nessuna giocata: nessun mercato quotato da Bet365 o Betfair per questa partita."]
    if reason == "solo_descrittivo":
        return ["Nessuna giocata: le statistiche con scarto dal prezzo sono solo descrittive, l'esame del motore non è superato."]
    if reason == "incertezza_alta":
        ev_home, ev_away = _get(goals, "uncertainty", "home_evidence"), _get(goals, "uncertainty", "away_evidence")
        little = [t for t, ev in ((home_team, ev_home), (away_team, ev_away)) if ev is not None and float(ev) < EVIDENCE_FULL_KNOWLEDGE]
        who = f" il modello conosce poco {join_it(little)}" if little else " il modello non conosce abbastanza le squadre"
        return [f"Nessuna giocata: incertezza alta,{who}."]
    priced = [r for r in rows if r.expected_profit is not None]
    if priced:
        top = max(priced, key=lambda r: r.expected_profit or -9)
        return [
            f"Nessuna giocata: il miglior candidato, {top.label} a {fmt_quota(top.quota_used)} ({top.bookmaker_used}), ha profitto atteso {fmt_pct(top.expected_profit, signed=True)}, sotto il {fmt_pct(PROFIT_MARGIN)} richiesto."
        ]
    return [f"Nessuna giocata: {VERDICT_LABELS.get(reason or '', 'nessun mercato con prezzo').lower()}."]


def build_why(
    rows: list[MarketRow],
    goals: dict[str, Any] | None,
    stats: dict[str, Any] | None,
    home_team: str,
    away_team: str,
    lineups_status: str,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    play = best_play(rows)
    if play is None:
        reason = no_play_reason(rows)
        return {"play": None, "reason": reason, "sentences": _no_play_sentences(reason, rows, goals, home_team, away_team), "would_change": []}

    implied = 1.0 / float(play.quota_used) if play.quota_used else None
    sentences = [_evidence_sentence(play, goals, stats, home_team, away_team)]
    sentences.append(
        f"La quota {fmt_quota(play.quota_used)} di {play.bookmaker_used} vale il {fmt_pct(implied)}; il modello dice {fmt_pct(play.p)} con intervallo {fmt_interval(play.lo, play.hi)}, probabilità prudente {fmt_pct(play.p_prudent)}."
    )
    ep = play.expected_profit or 0.0
    sentences.append(f"Il profitto atteso è {fmt_pct(ep, signed=True)}, {'sopra' if ep >= PROFIT_MARGIN else 'sotto'} il {fmt_pct(PROFIT_MARGIN)} richiesto.")
    status = (context or {}).get("lineups", {}).get("status") if context else None
    status = status or lineups_status
    sentences.append(_LINEUPS_PLAY_SENTENCE.get(status, _LINEUPS_PLAY_SENTENCE["non_note"]))
    level = _get(goals, "uncertainty", "level")
    if level in _UNCERTAINTY_SENTENCE:
        sentences.append(_UNCERTAINTY_SENTENCE[level])
    if not play.advised:
        sentences.append("Famiglia di mercato in osservazione: l'esame E4 non è superato, la giocata è mostrata ma non consigliata.")

    would_change: list[str] = []
    parsed = parse_market_key(play.market_key)
    team_for_absence = None
    if parsed.kind == KIND_STAT and parsed.side in ("home", "away"):
        team_for_absence = home_team if parsed.side == "home" else away_team
    would_change.append(f"Assenza di un titolare chiave{(' nel ' + team_for_absence) if team_for_absence else ''}")
    if play.p_prudent > 0:
        threshold = (1.0 + PROFIT_MARGIN) / play.p_prudent
        break_even = 1.0 / play.p_prudent
        would_change.append(
            f"Quota {play.bookmaker_used} sotto {fmt_quota(threshold)}: il profitto atteso scenderebbe sotto il {fmt_pct(PROFIT_MARGIN)} (pareggio a {fmt_quota(break_even)})"
        )
    would_change.append("Formazioni con turnover")
    if level == "media":
        would_change.append("Incertezza che sale ad alta")
    return {"play": play.to_dict(), "reason": None, "sentences": sentences, "would_change": would_change}


# --- Blocco 6: come è andata ---------------------------------------------------------
def build_aftermath(
    goals: dict[str, Any] | None,
    stats: dict[str, Any] | None,
    rows: list[MarketRow],
    aftermath: dict[str, Any] | None,
    home_team: str,
    away_team: str,
) -> dict[str, Any] | None:
    result = (aftermath or {}).get("result")
    if not result or result.get("ft_home") is None or result.get("ft_away") is None:
        return None
    actual_stats = (aftermath or {}).get("stats")
    goals = goals or {}
    parts: list[str] = []
    lam_home, lam_away = goals.get("lambda_home"), goals.get("lambda_away")
    if lam_home is not None and lam_away is not None:
        parts.append(f"Previsto {fmt_num(lam_home)}-{fmt_num(lam_away)}, reale {int(result['ft_home'])}-{int(result['ft_away'])}.")
    else:
        parts.append(f"Risultato {int(result['ft_home'])}-{int(result['ft_away'])}.")

    stat_rows: list[dict[str, Any]] = []
    for stat, label in STATS.items():
        block = _get(stats, "stats", stat)
        if not isinstance(block, dict):
            continue
        exp_home, exp_away = _get(block, "home", "mean"), _get(block, "away", "mean")
        act_home, act_away = stat_value(actual_stats, stat, "home"), stat_value(actual_stats, stat, "away")
        stat_rows.append({"stat": stat, "label": label, "expected_home": exp_home, "expected_away": exp_away, "actual_home": act_home, "actual_away": act_away})
        if act_home is not None and act_away is not None:
            parts.append(
                f"{label[0].upper()}{label[1:]}: {home_team} attesi {fmt_num(exp_home)}, reali {fmt_num(act_home, 0)}; {away_team} attesi {fmt_num(exp_away)}, reali {fmt_num(act_away, 0)}."
            )

    play = best_play(rows)
    play_block: dict[str, Any] | None = None
    outcome: str | None = None
    if play is not None:
        outcome = settle(play.market_key, result, actual_stats)
        units = profit_units(outcome, play.quota_used)
        play_block = {"label": play.label, "market_key": play.market_key, "outcome": outcome, "profit_units": units}
        if outcome is None:
            parts.append(f"Giocata {play.label}: esito non ancora regolabile, manca il dato.")
        else:
            parts.append(f"Giocata {play.label}: {outcome.replace('_', ' ')} ({fmt_num(units, 2, signed=True)} unità).")
    luck = luck_vs_merit(goals, result, play.to_dict() if play else None, outcome, home_team, away_team)
    return {
        "sentence": " ".join(parts),
        "result": result,
        "goals": {"expected_home": lam_home, "expected_away": lam_away, "actual_home": result.get("ft_home"), "actual_away": result.get("ft_away")},
        "stats": stat_rows,
        "play": play_block,
        "luck": luck,
    }


# --- Insieme ------------------------------------------------------------------------
def build_explanation(
    fixture_meta: dict[str, Any],
    goals_payload: dict[str, Any] | None,
    stats_payload: dict[str, Any] | None,
    rows: list[MarketRow],
    context: dict[str, Any] | None = None,
    aftermath: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """I sei blocchi di `FixtureDetail.blocks`. `fixture_meta` con `home_team`, `away_team`, `competition`, `lineups_status`."""
    home_team = str(fixture_meta.get("home_team") or "Casa")
    away_team = str(fixture_meta.get("away_team") or "Ospite")
    competition = fixture_meta.get("competition")
    lineups_status = str(_get(context, "lineups", "status") or fixture_meta.get("lineups_status") or "non_note")
    return {
        "who": build_who(goals_payload, home_team, away_team, competition),
        "how": build_how(stats_payload, home_team, away_team),
        "context": build_context(goals_payload, context, home_team, away_team, lineups_status),
        "predicts": build_predicts(goals_payload, rows, home_team, away_team),
        "why": build_why(rows, goals_payload, stats_payload, home_team, away_team, lineups_status, context),
        "aftermath": build_aftermath(goals_payload, stats_payload, rows, aftermath, home_team, away_team),
    }


def fixture_card(
    fixture_meta: dict[str, Any],
    goals_payload: dict[str, Any] | None,
    rows: list[MarketRow],
    lineups_status: str | None = None,
    result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """`FixtureCard` (docs/v4/API.md) dagli stessi ingredienti del Ragionamento."""
    goals = goals_payload or {}
    play = best_play(rows)
    unc = goals.get("uncertainty") or {}
    card = {
        key: fixture_meta.get(key)
        for key in ("id", "api_fixture_id", "league_code", "competition", "season_label", "kickoff_at", "home_team", "away_team", "status")
    }
    if isinstance(card.get("kickoff_at"), (bytes,)):
        card["kickoff_at"] = str(card["kickoff_at"])
    elif hasattr(card.get("kickoff_at"), "isoformat"):
        card["kickoff_at"] = card["kickoff_at"].isoformat()
    card.update(
        {
            "most_likely": most_likely_sign(rows, goals),
            "expected_goals": {"home": goals.get("lambda_home"), "away": goals.get("lambda_away")},
            "uncertainty": {"score": unc.get("score"), "level": unc.get("level")},
            "lineups_status": lineups_status or fixture_meta.get("lineups_status") or "non_note",
            "best_play": play.to_dict() if play else None,
            "no_play_reason": no_play_reason(rows),
            "result": result,
        }
    )
    return card
