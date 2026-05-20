"""Impatto difensivo Lineup Impact — debolezza difensiva e SOT concessi all'avversario."""

from __future__ import annotations

from typing import Any

from app.services.sportapi.sportapi_lineup_impact_logic import PlayerLineupStatus

DEFENSIVE_PENALTY_WEIGHT: dict[bool, dict[str, float]] = {
    False: {
        "STARTER": 0.0,
        "BENCH": 0.25,
        "MISSING": 1.0,
        "OUT_OF_LINEUP": 0.50,
        "UNMAPPED": 0.0,
    },
    True: {
        "STARTER": 0.0,
        "BENCH": 0.35,
        "MISSING": 1.0,
        "OUT_OF_LINEUP": 0.80,
        "UNMAPPED": 0.0,
    },
}

DEFENSIVE_WEIGHT_LINEUP = {False: 0.25, True: 0.40}
DEFENSIVE_FACTOR_MAX = {False: 1.15, True: 1.25}

REPLACEMENT_WEIGHT_STARTER = 0.75
REPLACEMENT_WEIGHT_BENCH = 0.35

DEFENSIVE_TOP_N = 8


def is_defensive_relevant_position(position: str | None) -> bool:
    if not position:
        return False
    p = str(position).strip().upper()
    if p in ("G", "GK", "GOALKEEPER", "P"):
        return True
    if p in ("D", "DF", "DEF", "DEFENDER", "CB", "LB", "RB", "WB"):
        return True
    if any(k in p for k in ("DM", "CDM", "CM", "MID", "M ")):
        return True
    if p and p[0] in ("G", "D"):
        return True
    return False


def defensive_role_group(position: str | None) -> str:
    if not position:
        return "C"
    p = str(position).strip().upper()
    if p in ("G", "GK", "GOALKEEPER", "P") or (p and p[0] == "G"):
        return "P"
    if p in ("D", "DF", "DEF", "DEFENDER", "CB", "LB", "RB", "WB") or (p and p[0] == "D"):
        return "D"
    return "C"


def roles_match_defensive(replacement_role: str, target_role: str) -> bool:
    if replacement_role == target_role:
        return True
    if target_role == "C" and replacement_role == "C":
        return True
    return False


def compute_raw_defensive_importance(
    *,
    position: str | None,
    total_minutes: int,
    starts: int,
    appearances: int,
    avg_rating: float | None,
    tackles_total: int,
    interceptions: int,
    tackles_blocks: int,
    duels_won: int,
) -> float:
    role = defensive_role_group(position)
    role_w = {"P": 1.0, "D": 0.85, "C": 0.55}.get(role, 0.4)
    mins = max(0, int(total_minutes))
    min_score = min(mins / 2000.0, 1.0)
    app = max(1, int(appearances))
    start_share = min(float(starts) / float(app), 1.0)
    rating_score = min(max((avg_rating or 6.0) - 5.0, 0.0) / 3.0, 1.0) if avg_rating else 0.5
    def_stats = tackles_total + interceptions + tackles_blocks + duels_won
    def_score = min(def_stats / 80.0, 1.0) if def_stats > 0 else min_score * 0.3
    raw = (
        0.35 * role_w
        + 0.25 * min_score
        + 0.20 * start_share
        + 0.10 * rating_score
        + 0.10 * def_score
    )
    return max(0.0, min(1.0, raw))


def normalize_defensive_scores(players: list[dict[str, Any]]) -> None:
    if not players:
        return
    mx = max(float(p.get("raw_defensive_importance") or 0) for p in players)
    if mx <= 0:
        for p in players:
            p["defensive_importance"] = 0.0
        return
    for p in players:
        p["defensive_importance"] = round(float(p.get("raw_defensive_importance") or 0) / mx, 4)


def defensive_penalty_weight(status: PlayerLineupStatus, confirmed: bool) -> float:
    return DEFENSIVE_PENALTY_WEIGHT[bool(confirmed)].get(status, 0.0)


def find_defensive_replacement(
    *,
    target_role: str,
    starter_pool: list[dict[str, Any]],
    bench_pool: list[dict[str, Any]],
    used_ids: set[int],
    max_credit: float,
) -> tuple[dict[str, Any] | None, float]:
    candidates: list[tuple[dict[str, Any], str]] = []
    for row in starter_pool:
        candidates.append((row, "STARTER"))
    for row in bench_pool:
        candidates.append((row, "BENCH"))
    filtered: list[tuple[dict[str, Any], str]] = []
    for row, pool_status in candidates:
        pid = row.get("player_id")
        if pid is None or int(pid) in used_ids:
            continue
        role = str(row.get("defensive_role") or "C")
        if roles_match_defensive(role, target_role):
            filtered.append((row, pool_status))
    filtered.sort(
        key=lambda x: float(x[0].get("defensive_importance") or 0),
        reverse=True,
    )
    if not filtered:
        return None, 0.0
    best, best_status = filtered[0]
    imp = float(best.get("defensive_importance") or 0)
    weight = REPLACEMENT_WEIGHT_STARTER if best_status == "STARTER" else REPLACEMENT_WEIGHT_BENCH
    credit = min(max_credit, imp * weight)
    return best, credit


def clamp_defensive_weakness_factor(raw: float, confirmed: bool) -> float:
    mx = DEFENSIVE_FACTOR_MAX[bool(confirmed)]
    return max(1.0, min(mx, raw))


def build_defensive_reason(
    *,
    team_name: str,
    player_name: str,
    status: PlayerLineupStatus,
    importance_pct: float,
    note: str,
) -> str | None:
    if status == "MISSING" and importance_pct > 0:
        return (
            f"{team_name} — {player_name} missingPlayer: impatto difensivo "
            f"({importance_pct:.0f}% importanza), può aumentare i SOT avversari ({note})"
        )
    if status == "OUT_OF_LINEUP" and importance_pct > 0:
        return (
            f"{team_name} — {player_name} fuori lista: rischio difensivo "
            f"({importance_pct:.0f}% importanza tattica)"
        )
    if status == "BENCH" and importance_pct > 0:
        return f"{team_name} — {player_name} in panchina: leggero rischio difensivo"
    return None


def compute_defensive_weakness_side(
    *,
    team_name: str,
    confirmed: bool,
    key_players: list[dict[str, Any]],
    starter_pool: list[dict[str, Any]],
    bench_pool: list[dict[str, Any]],
) -> dict[str, Any]:
    """Calcola factor difensivo per una squadra (applicato ai SOT dell'avversario)."""
    used: set[int] = set()
    gross = 0.0
    credit_total = 0.0
    reasons: list[str] = []

    for player in key_players:
        status = player.get("status")
        if status in ("UNMAPPED", "STARTER"):
            player["defensive_penalty"] = 0.0
            player["defensive_replacement_credit"] = 0.0
            player["net_defensive_loss"] = 0.0
            continue
        imp = float(player.get("defensive_importance") or 0)
        pw = defensive_penalty_weight(status, confirmed)
        penalty = imp * pw
        player["defensive_penalty"] = round(penalty, 4)
        if penalty <= 0:
            player["net_defensive_loss"] = 0.0
            continue
        gross += penalty
        rep, credit = find_defensive_replacement(
            target_role=str(player.get("defensive_role") or "C"),
            starter_pool=starter_pool,
            bench_pool=bench_pool,
            used_ids=used,
            max_credit=penalty,
        )
        if rep:
            rid = int(rep["player_id"])
            used.add(rid)
            player["replacement_player_id"] = rid
            player["replacement_player_name"] = rep.get("player_name")
            player["defensive_replacement_credit"] = round(credit, 4)
            credit_total += credit
        else:
            player["defensive_replacement_credit"] = 0.0
        net = max(0.0, penalty - float(player.get("defensive_replacement_credit") or 0))
        player["net_defensive_loss"] = round(net, 4)
        reason = build_defensive_reason(
            team_name=team_name,
            player_name=str(player.get("player_name") or "?"),
            status=status,
            importance_pct=imp * 100,
            note=str(player.get("status_note") or ""),
        )
        if reason:
            reasons.append(reason)

    net_loss = max(0.0, gross - credit_total)
    dw = DEFENSIVE_WEIGHT_LINEUP[bool(confirmed)]
    raw_factor = 1.0 + net_loss * dw
    factor = clamp_defensive_weakness_factor(raw_factor, confirmed)

    return {
        "defensive_weakness_factor": round(factor, 4),
        "gross_defensive_loss": round(gross, 4),
        "defensive_replacement_credit": round(credit_total, 4),
        "net_defensive_loss": round(net_loss, 4),
        "defensive_weight": dw,
        "defensive_key_players": key_players,
        "defensive_reasons": reasons,
        "defensive_stats_limited": any(
            p.get("stats_source") == "minutes_role_only" for p in key_players
        ),
    }
