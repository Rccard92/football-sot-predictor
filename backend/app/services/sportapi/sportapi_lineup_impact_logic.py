"""Logica pura Lineup Impact — status, penalità, sostituti, confidence."""

from __future__ import annotations

from typing import Any, Literal

PlayerLineupStatus = Literal["STARTER", "BENCH", "MISSING", "OUT_OF_LINEUP", "UNMAPPED"]

PENALTY_WEIGHT: dict[bool, dict[str, float]] = {
    False: {
        "STARTER": 0.0,
        "BENCH": 0.35,
        "MISSING": 1.0,
        "OUT_OF_LINEUP": 0.60,
        "UNMAPPED": 0.0,
    },
    True: {
        "STARTER": 0.0,
        "BENCH": 0.45,
        "MISSING": 1.0,
        "OUT_OF_LINEUP": 0.85,
        "UNMAPPED": 0.0,
    },
}

REPLACEMENT_WEIGHT_STARTER = 0.75
REPLACEMENT_WEIGHT_BENCH = 0.35

OFFENSIVE_ROLES = frozenset({"A", "C"})


def resolve_display_name(
    *,
    player_name_api: str | None = None,
    mapping_name_api: str | None = None,
    sportapi_name: str | None = None,
    sportapi_short: str | None = None,
    api_player_id: int | None = None,
    sportapi_player_id: int | None = None,
) -> str:
    for candidate in (player_name_api, mapping_name_api, sportapi_name, sportapi_short):
        if candidate and str(candidate).strip():
            return str(candidate).strip()
    if api_player_id is not None:
        return f"Nome non disponibile (API-Sports ID: {api_player_id})"
    if sportapi_player_id is not None:
        return f"Nome non disponibile (SportAPI ID: {sportapi_player_id})"
    return "Nome non disponibile"


def classify_lineup_status(
    *,
    player_id: int | None,
    mapping_recommendation: str | None,
    mapping_confidence: float | None,
    sportapi_provider_id: int | None,
    sportapi_starter_pids: set[int],
    sportapi_bench_pids: set[int],
    sportapi_missing_pids: set[int],
) -> PlayerLineupStatus:
    if player_id is None:
        return "UNMAPPED"
    if mapping_recommendation == "NO_MATCH" or (mapping_confidence is not None and mapping_confidence < 75):
        return "UNMAPPED"
    if sportapi_provider_id is not None and sportapi_provider_id in sportapi_missing_pids:
        return "MISSING"
    if sportapi_provider_id is not None and sportapi_provider_id in sportapi_starter_pids:
        return "STARTER"
    if sportapi_provider_id is not None and sportapi_provider_id in sportapi_bench_pids:
        return "BENCH"
    if sportapi_provider_id is not None:
        return "OUT_OF_LINEUP"
    return "UNMAPPED"


def penalty_weight_for_status(status: PlayerLineupStatus, confirmed: bool) -> float:
    return PENALTY_WEIGHT[bool(confirmed)].get(status, 0.0)


def status_note_it(
    status: PlayerLineupStatus,
    *,
    absence_group: str | None = None,
    description: str | None = None,
) -> str:
    if status == "STARTER":
        return "Titolare"
    if status == "BENCH":
        return "In panchina"
    if status == "MISSING":
        if absence_group == "suspended" or (description and "suspension" in description.lower()):
            return "Squalificato"
        if absence_group == "injured" or (description and any(
            k in (description or "").lower() for k in ("injury", "muscle", "cruciate", "knee", "ankle")
        )):
            return "Infortunato"
        return "Indisponibile"
    if status == "OUT_OF_LINEUP":
        return "Fuori lista / non in probabile formazione"
    return "Mapping mancante"


def is_offensive_role(display_role: str) -> bool:
    return display_role in OFFENSIVE_ROLES


def roles_match(replacement_role: str, target_role: str) -> bool:
    if replacement_role == target_role:
        return True
    return is_offensive_role(replacement_role) and is_offensive_role(target_role)


def find_replacement(
    *,
    target_role: str,
    target_share: float,
    starter_pool: list[dict[str, Any]],
    bench_pool: list[dict[str, Any]],
    used_replacement_player_ids: set[int],
) -> tuple[dict[str, Any] | None, float, str]:
    """Ritorna (replacement_row, credit_share, replacement_status)."""
    candidates: list[tuple[dict[str, Any], str]] = []
    for row in starter_pool:
        candidates.append((row, "STARTER"))
    for row in bench_pool:
        candidates.append((row, "BENCH"))
    filtered: list[tuple[dict[str, Any], str]] = []
    for row, pool_status in candidates:
        pid = row.get("player_id")
        if pid is None or int(pid) in used_replacement_player_ids:
            continue
        role = str(row.get("display_role") or "C")
        if roles_match(role, target_role):
            filtered.append((row, pool_status))

    def _sort_key(item: tuple[dict[str, Any], str]) -> tuple[float, float]:
        r, _ = item
        share = float(r.get("team_sot_share") or 0)
        sot90 = float(r.get("sot_per_90") or 0)
        return (share, sot90)

    filtered.sort(key=_sort_key, reverse=True)
    if not filtered:
        return None, 0.0, ""

    best, best_status = filtered[0]
    rep_share = float(best.get("team_sot_share") or 0)
    weight = REPLACEMENT_WEIGHT_STARTER if best_status == "STARTER" else REPLACEMENT_WEIGHT_BENCH
    credit = rep_share * weight
    return best, credit, best_status


def clamp_factor(raw: float, confirmed: bool, *, confidence_multiplier: float = 1.0) -> float:
    adjusted = raw * confidence_multiplier
    if confirmed:
        return max(0.65, min(1.20, adjusted))
    return max(0.75, min(1.15, adjusted))


def build_reason_sentence(
    *,
    team_name: str,
    player_name: str,
    status: PlayerLineupStatus,
    confirmed: bool,
    sot_share_pct: float,
    penalty_share: float,
    replacement_name: str | None,
    replacement_credit: float,
    note: str,
) -> str | None:
    pct = round(sot_share_pct, 1)
    if status == "MISSING" and penalty_share > 0:
        return f"{team_name} — {player_name} è missingPlayer: penalità piena su share {pct}% ({note})"
    if status == "OUT_OF_LINEUP" and penalty_share > 0:
        w = int(penalty_weight_for_status("OUT_OF_LINEUP", confirmed) * 100)
        return f"{team_name} — {player_name} fuori lista: penalità {w}% su share {pct}%"
    if status == "BENCH" and penalty_share > 0:
        return f"{team_name} — {player_name} in panchina: penalità parziale su share {pct}%"
    if status == "STARTER":
        if replacement_name and replacement_credit > 0:
            return f"{team_name} — {replacement_name} titolare compensa (share stimata)"
        return f"{team_name} — {player_name} titolare: nessuna penalità"
    if status == "UNMAPPED":
        return f"{team_name} — {player_name}: escluso dal calcolo penalità (mapping mancante)"
    return None


def compute_impact_confidence(
    *,
    confirmed: bool,
    top_players: list[dict[str, Any]],
    profiles_missing: bool,
) -> tuple[str, list[str]]:
    score = 100
    reasons: list[str] = []

    if not confirmed:
        score -= 15
        reasons.append("Formazione probabile, non ufficiale")
    if profiles_missing:
        score -= 25
        reasons.append("Profili player_sot_profiles assenti per la stagione")

    unmapped = sum(1 for p in top_players if p.get("status") == "UNMAPPED")
    out_lineup = sum(1 for p in top_players if p.get("status") == "OUT_OF_LINEUP")
    low_mapping = sum(
        1
        for p in top_players
        if p.get("mapping_recommendation") not in ("AUTO_SAFE",) and p.get("status") != "UNMAPPED"
    )
    unresolved_names = sum(
        1 for p in top_players if str(p.get("player_name", "")).startswith("Nome non disponibile")
    )

    if unmapped:
        score -= unmapped * 12
        reasons.append(f"{unmapped} top player non mappati SportAPI ↔ API-Sports")
    if out_lineup >= 2:
        score -= 8
        reasons.append(f"{out_lineup} top player fuori lista ma non in missingPlayers")
    if low_mapping:
        score -= 5
        reasons.append("Alcuni mapping giocatori sotto soglia AUTO_SAFE")
    if unresolved_names:
        score -= unresolved_names * 5
        reasons.append(f"{unresolved_names} nomi giocatore non risolti")

    if score >= 75:
        label = "alta"
    elif score >= 50:
        label = "media"
    else:
        label = "bassa"

    if not reasons:
        reasons.append("Dati lineup e profili sufficienti per la simulazione")

    return label, reasons
