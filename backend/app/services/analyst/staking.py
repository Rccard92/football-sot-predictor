"""Metodi di puntata del Diario analisi (dal 30/10/2026), ricostruiti dalle formule del file
"IL CECCHINO (Report).xlsm" (fogli "Cecchino1", "CeccXino1", "8° Meraviglia1").

Una "progressione" (ciclo) e' una sequenza di giocate con un metodo e le sue impostazioni. Dato l'elenco delle
giocate gia' chiuse (in ordine), si ricostruisce lo stato del ciclo e si suggerisce la puntata della prossima
giocata a una certa quota. L'analista puo' sempre puntare un importo diverso: conta l'importo reale.
Le giocate nulle (rimborsate) non entrano nella sequenza.

- Cecchino: progressione a obiettivo. Profitto preteso = cassa x target; su N scommesse con uno strike previsto
  servono W vincenti e si possono perdere L = N - W. A ogni giocata la puntata e' "quanto manca all'obiettivo /
  vincite che servono ancora", diviso (quota - 1). Finisce quando la cassa arriva a cassa + profitto preteso.
- CeccXino: puntata base = cassa x 6%; dopo una persa +meta' base, dopo una vinta -1 (mai sotto la base);
  stop loss e stop win in % della cassa iniziale. Nel file la colonna di appoggio continuava a salire anche con
  la puntata ferma alla base: qui si segue la regola scritta nel foglio (+5 / -1 su una base di 10).
- 8a Meraviglia: puntata = % della cassa attuale + recupero di una parte di ogni giocata persa in precedenza
  (10% fino a 3 giocate prima, 15% fino a 6, 20% fino a 12, 25% fino a 17, 30% fino a 20). Un ciclo = un mese.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

METHOD_CECCHINO = "cecchino"
METHOD_CECCXINO = "ceccxino"
METHOD_MERAVIGLIA = "meraviglia"
METHODS = (METHOD_CECCHINO, METHOD_CECCXINO, METHOD_MERAVIGLIA)

METHOD_LABELS = {METHOD_CECCHINO: "Cecchino", METHOD_CECCXINO: "CeccXino", METHOD_MERAVIGLIA: "8ª Meraviglia"}
MAX_BETS = {METHOD_CECCHINO: 30, METHOD_CECCXINO: 20, METHOD_MERAVIGLIA: 21}

WON, LOST, VOID = "won", "lost", "void"

# impostazioni di partenza, come nel file
DEFAULTS: dict[str, dict[str, Any]] = {
    METHOD_CECCHINO: {"bankroll": 1000.0, "target_pct": 0.20, "strike": 0.6, "bets": 10, "quota_min": 1.5, "quota_max": 2.5},
    METHOD_CECCXINO: {"bankroll": 1000.0, "base_pct": 0.06, "step_down": 1.0, "stop_loss_pct": 0.30, "stop_win_pct": 0.20, "decimals": True},
    METHOD_MERAVIGLIA: {"bankroll": 1000.0, "stake_pct": 0.05, "monthly_withdrawal": 0.0},
}


@dataclass(frozen=True)
class SettledBet:
    stake: float
    quota: float
    outcome: str  # won | lost | void


@dataclass
class CycleState:
    method: str
    settings: dict[str, Any]
    bankroll_start: float
    bankroll: float
    bets_played: int
    won: int
    lost: int
    profit: float
    status: str = "in_corso"  # in_corso | obiettivo_raggiunto | stop_win | stop_loss | esaurita
    status_label: str = "In corso"
    info: dict[str, Any] = field(default_factory=dict)
    # stato interno per la prossima puntata
    _history: list[SettledBet] = field(default_factory=list, repr=False)

    def payload(self) -> dict[str, Any]:
        return {
            "method": self.method,
            "method_label": METHOD_LABELS[self.method],
            "settings": self.settings,
            "bankroll_start": round(self.bankroll_start, 2),
            "bankroll": round(self.bankroll, 2),
            "bets_played": self.bets_played,
            "max_bets": MAX_BETS[self.method],
            "won": self.won,
            "lost": self.lost,
            "profit": round(self.profit, 2),
            "status": self.status,
            "status_label": self.status_label,
            "info": self.info,
        }


def normalize_settings(method: str, settings: dict[str, Any] | None) -> dict[str, Any]:
    if method not in METHODS:
        raise ValueError(f"metodo sconosciuto: {method}")
    out = dict(DEFAULTS[method])
    for key, value in (settings or {}).items():
        if key not in out:
            continue
        if isinstance(out[key], bool):
            out[key] = bool(value)
        elif isinstance(out[key], int):
            out[key] = int(value)
        else:
            out[key] = float(value)
    if out["bankroll"] <= 0:
        raise ValueError("La cassa iniziale deve essere maggiore di zero")
    if method == METHOD_CECCHINO:
        if not 0 < out["strike"] < 1:
            raise ValueError("Lo strike deve essere tra 0 e 100%")
        if out["bets"] < 2 or out["target_pct"] <= 0:
            raise ValueError("Servono almeno 2 scommesse e un target maggiore di zero")
        wins = round(out["bets"] * out["strike"])
        if wins < 1 or wins >= out["bets"]:
            raise ValueError("Con questo strike le vincenti previste devono essere tra 1 e il numero di scommesse - 1")
    return out


def _ceil(x: float) -> float:
    """Arrotondamento per eccesso come CEILING di Excel, senza i residui della virgola mobile (33/0,2 = 165)."""
    return float(math.ceil(round(x, 9)))


def _profit(bet: SettledBet) -> float:
    if bet.outcome == WON:
        return bet.stake * bet.quota - bet.stake
    if bet.outcome == LOST:
        return -bet.stake
    return 0.0


# --- Cecchino ---------------------------------------------------------------------------------------


def _cecchino_plan(s: dict[str, Any]) -> dict[str, float]:
    cassa = s["bankroll"]
    target = cassa * s["target_pct"]  # PROFITTO PRETESO (C12)
    wins = round(s["bets"] * s["strike"])  # VINCENTI DA STRIKE (C14)
    losses = s["bets"] - wins  # PERDENTI DA STRIKE (C15)
    avg_stake = round(cassa / s["bets"])  # PUNTATA MEDIA (C20)
    avg_win = round(target / wins)  # VINCITA MEDIA PER REALIZZARE PROFITTO (C21)
    ref_quota = 1 + avg_win / avg_stake if avg_stake else float("nan")  # QUOTA DI RIFERIMENTO MEDIA (C22)
    return {"target": target, "wins": wins, "losses": losses, "avg_stake": avg_stake, "avg_win": avg_win, "ref_quota": ref_quota}


def _cecchino_next(state: CycleState, quota: float) -> float | None:
    info = state.info
    if not state._history:
        plan = _cecchino_plan(state.settings)
        if quota >= plan["ref_quota"]:
            return float(plan["avg_stake"])
        return _ceil(plan["avg_win"] / (quota - 1))
    need, can_lose = info["wins_needed"], info["losses_allowed"]
    if need <= 0 or need + can_lose <= 0:
        return None
    ab = state.bankroll / (need + can_lose)  # AB: puntata media sulle giocate che restano
    ac = info["target_left"] / need  # AC: vincita che serve per ogni vincente che manca
    ref = 1 + ac / ab if ab else float("inf")  # AD: quota di riferimento del momento
    if abs(quota - ref) < 1e-9:
        return float(round(ab))
    if quota > ref:
        return float(round(ac / (quota - 1)))
    return _ceil(ac / (quota - 1))


def _cecchino_state(state: CycleState) -> None:
    plan = _cecchino_plan(state.settings)
    need, can_lose = plan["wins"], plan["losses"]
    for bet in state._history:
        if bet.outcome == WON:
            need -= 1
        elif bet.outcome == LOST:
            can_lose -= 1
    reached = state.bankroll - state.bankroll_start >= plan["target"] - 1e-9
    state.info = {
        "target_profit": round(plan["target"], 2),
        "target_left": max(0.0, plan["target"] - (state.bankroll - state.bankroll_start)),
        "wins_needed": need,
        "losses_allowed": can_lose,
        "planned_bets": state.settings["bets"],
        "avg_stake": plan["avg_stake"],
        "ref_quota": round(plan["ref_quota"], 2),
        "quota_range": [state.settings["quota_min"], state.settings["quota_max"]],
    }
    if reached:
        state.status, state.status_label = "obiettivo_raggiunto", "Obiettivo raggiunto"
    elif need <= 0 or need + can_lose <= 0 or state.bets_played >= MAX_BETS[METHOD_CECCHINO] or state.bankroll <= 0:
        state.status, state.status_label = "esaurita", "Progressione esaurita senza obiettivo"


# --- CeccXino ---------------------------------------------------------------------------------------


def _ceccxino_next(state: CycleState, quota: float) -> float | None:
    s = state.settings
    base = s["bankroll"] * s["base_pct"]
    if not state._history:
        stake = base
    else:
        last = state._history[-1]
        if last.outcome == WON:
            stake = max(base, last.stake - s["step_down"])
        else:
            stake = last.stake + base / 2
    stake = max(stake, base)
    return round(stake, 2) if s["decimals"] else _ceil(stake)


def _ceccxino_state(state: CycleState) -> None:
    s = state.settings
    loss_floor = s["bankroll"] * (1 - s["stop_loss_pct"])
    win_ceiling = s["bankroll"] * (1 + s["stop_win_pct"])
    state.info = {
        "base_stake": round(s["bankroll"] * s["base_pct"], 2),
        "stop_loss_at": round(loss_floor, 2),
        "stop_win_at": round(win_ceiling, 2),
    }
    if state.bankroll <= loss_floor + 1e-9:
        state.status, state.status_label = "stop_loss", "Stop loss raggiunto"
    elif state.bankroll >= win_ceiling - 1e-9:
        state.status, state.status_label = "stop_win", "Stop win raggiunto"
    elif state.bets_played >= MAX_BETS[METHOD_CECCXINO]:
        state.status, state.status_label = "esaurita", "Progressione completata (20 giocate)"


# --- 8a Meraviglia ----------------------------------------------------------------------------------


def recovery_weight(distance: int) -> float:
    """Parte di una giocata persa `distance` giocate prima che si aggiunge alla puntata (colonne P..AI)."""
    if distance <= 3:
        return 0.10
    if distance <= 6:
        return 0.15
    if distance <= 12:
        return 0.20
    if distance <= 17:
        return 0.25
    return 0.30


def _meraviglia_next(state: CycleState, quota: float) -> float | None:
    s = state.settings
    if not state._history:
        return round(s["stake_pct"] * s["bankroll"], 2)
    n = len(state._history)
    recovery = sum(
        recovery_weight(n - j) * bet.stake for j, bet in enumerate(state._history) if bet.outcome == LOST and n - j <= 20
    )
    return round(s["stake_pct"] * state.bankroll + recovery, 2)


def _meraviglia_state(state: CycleState) -> None:
    state.info = {"stake_pct": state.settings["stake_pct"], "monthly_withdrawal": state.settings["monthly_withdrawal"]}
    if state.bankroll <= 0:
        state.status, state.status_label = "esaurita", "Cassa esaurita"
    elif state.bets_played >= MAX_BETS[METHOD_MERAVIGLIA]:
        state.status, state.status_label = "esaurita", "Mese completato (21 giocate)"


# --- interfaccia ------------------------------------------------------------------------------------

_NEXT = {METHOD_CECCHINO: _cecchino_next, METHOD_CECCXINO: _ceccxino_next, METHOD_MERAVIGLIA: _meraviglia_next}
_STATE = {METHOD_CECCHINO: _cecchino_state, METHOD_CECCXINO: _ceccxino_state, METHOD_MERAVIGLIA: _meraviglia_state}


def cycle_state(method: str, settings: dict[str, Any] | None, bets: list[SettledBet]) -> CycleState:
    """Stato del ciclo dopo le giocate chiuse `bets` (in ordine); le nulle non contano."""
    s = normalize_settings(method, settings)
    played = [b for b in bets if b.outcome in (WON, LOST)]
    start = s["bankroll"]
    bankroll = start
    for i, bet in enumerate(played):
        bankroll += _profit(bet)
        if method == METHOD_MERAVIGLIA and i == 0:
            bankroll -= s["monthly_withdrawal"]  # prelievo mensile tolto alla prima giocata del mese (O10)
    state = CycleState(
        method=method,
        settings=s,
        bankroll_start=start,
        bankroll=bankroll,
        bets_played=len(played),
        won=sum(1 for b in played if b.outcome == WON),
        lost=sum(1 for b in played if b.outcome == LOST),
        profit=sum(_profit(b) for b in played),
        _history=played,
    )
    _STATE[method](state)
    return state


def suggest_stake(state: CycleState, quota: float) -> dict[str, Any]:
    """Puntata suggerita dal metodo per la prossima giocata a `quota` (None se il ciclo e' chiuso)."""
    if quota is None or quota <= 1.0:
        return {"stake": None, "reason": "Quota non valida"}
    if state.status != "in_corso":
        return {"stake": None, "reason": state.status_label}
    stake = _NEXT[state.method](state, float(quota))
    if stake is None or stake <= 0:
        return {"stake": None, "reason": "Il metodo non prevede altre giocate"}
    out: dict[str, Any] = {"stake": stake, "reason": None}
    if state.method == METHOD_CECCHINO:
        qmin, qmax = state.settings["quota_min"], state.settings["quota_max"]
        if not qmin <= quota <= qmax:
            out["warning"] = f"Quota fuori dal range scelto ({qmin:g}–{qmax:g})"
    if stake > state.bankroll:
        out["warning"] = "La puntata supera la cassa disponibile"
    return out
