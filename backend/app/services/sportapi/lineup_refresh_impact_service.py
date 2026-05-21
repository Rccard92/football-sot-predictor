"""Confronto snapshot pre/post refresh formazioni e motivi leggibili."""

from __future__ import annotations

from typing import Any

FLAT_THRESHOLD = 0.10


def direction_for_delta(delta: float | None) -> str:
    if delta is None:
        return "FLAT"
    d = float(delta)
    if d > FLAT_THRESHOLD:
        return "UP"
    if d < -FLAT_THRESHOLD:
        return "DOWN"
    return "FLAT"


def _severity_for_delta(delta: float | None) -> str:
    if delta is None:
        return "none"
    ad = abs(float(delta))
    if ad >= 0.5:
        return "high"
    if ad >= 0.25:
        return "moderate"
    if ad > FLAT_THRESHOLD:
        return "low"
    return "none"


def _player_key(p: dict[str, Any]) -> str:
    name = (p.get("player_name") or "").strip().lower()
    pid = p.get("player_id")
    return f"{pid}:{name}" if name else str(pid)


def _index_lineup_players(players: list[dict[str, Any]]) -> dict[str, str]:
    return {_player_key(p): str(p.get("lineup_status") or "") for p in players if _player_key(p)}


def _index_missing(missing: list[dict[str, Any]]) -> set[str]:
    return {(m.get("player_name") or "").strip().lower() for m in missing if m.get("player_name")}


def _reason_entry(
    *,
    text: str,
    player_name: str | None = None,
    previous_status: str | None = None,
    new_status: str | None = None,
    impact_type: str = "offensive",
    affected_team: str = "home",
    affected_prediction: str = "home",
    estimated_sot_impact: float | None = None,
) -> dict[str, Any]:
    return {
        "text": text,
        "player_name": player_name,
        "previous_status": previous_status,
        "new_status": new_status,
        "impact_type": impact_type,
        "affected_team": affected_team,
        "affected_prediction": affected_prediction,
        "estimated_sot_impact": estimated_sot_impact,
    }


def _compare_side_players(
    before_side: dict[str, Any],
    after_side: dict[str, Any],
    *,
    team_name: str,
    team_key: str,
) -> list[dict[str, Any]]:
    reasons: list[dict[str, Any]] = []
    b_idx = _index_lineup_players(before_side.get("lineup_players") or [])
    a_idx = _index_lineup_players(after_side.get("lineup_players") or [])

    all_keys = set(b_idx) | set(a_idx)
    for key in all_keys:
        b_st = b_idx.get(key)
        a_st = a_idx.get(key)
        if b_st == a_st:
            continue
        name = key.split(":", 1)[-1].title() if ":" in key else key
        for p in (before_side.get("lineup_players") or []) + (after_side.get("lineup_players") or []):
            if _player_key(p) == key and p.get("player_name"):
                name = str(p["player_name"])
                break

        if b_st == "STARTER" and a_st and a_st != "STARTER":
            reasons.append(
                _reason_entry(
                    text=f"{name} non è più titolare: riduce la forza offensiva {team_name}.",
                    player_name=name,
                    previous_status=b_st,
                    new_status=a_st,
                    impact_type="offensive",
                    affected_team=team_key,
                    affected_prediction=team_key,
                ),
            )
        elif b_st != "STARTER" and a_st == "STARTER":
            reasons.append(
                _reason_entry(
                    text=f"{name} è tornato titolare: aumenta la forza offensiva {team_name}.",
                    player_name=name,
                    previous_status=b_st,
                    new_status=a_st,
                    impact_type="offensive",
                    affected_team=team_key,
                    affected_prediction=team_key,
                ),
            )
        elif a_st == "MISSING" and b_st != "MISSING":
            reasons.append(
                _reason_entry(
                    text=f"{name} è stato aggiunto tra gli indisponibili: calo della produzione offensiva {team_name}.",
                    player_name=name,
                    previous_status=b_st,
                    new_status=a_st,
                    impact_type="availability",
                    affected_team=team_key,
                    affected_prediction=team_key,
                ),
            )
        elif b_st == "MISSING" and a_st != "MISSING":
            reasons.append(
                _reason_entry(
                    text=f"{name} non è più tra gli indisponibili.",
                    player_name=name,
                    previous_status=b_st,
                    new_status=a_st,
                    impact_type="availability",
                    affected_team=team_key,
                    affected_prediction=team_key,
                ),
            )

    b_miss = _index_missing(before_side.get("missing_players") or [])
    a_miss = _index_missing(after_side.get("missing_players") or [])
    for name in a_miss - b_miss:
        if name:
            reasons.append(
                _reason_entry(
                    text=f"{name.title()} aggiunto tra gli indisponibili: calo produzione offensiva {team_name}.",
                    player_name=name.title(),
                    impact_type="availability",
                    affected_team=team_key,
                    affected_prediction=team_key,
                ),
            )
    for name in b_miss - a_miss:
        if name:
            reasons.append(
                _reason_entry(
                    text=f"{name.title()} non è più tra gli indisponibili.",
                    player_name=name.title(),
                    impact_type="availability",
                    affected_team=team_key,
                    affected_prediction=team_key,
                ),
            )

    b_off = float(before_side.get("offensive_lineup_factor") or 1.0)
    a_off = float(after_side.get("offensive_lineup_factor") or 1.0)
    if abs(a_off - b_off) >= 0.02:
        if a_off > b_off:
            reasons.append(
                _reason_entry(
                    text=f"Fattore offensivo {team_name} aumentato ({b_off:.3f} → {a_off:.3f}).",
                    impact_type="offensive",
                    affected_team=team_key,
                    affected_prediction=team_key,
                ),
            )
        else:
            reasons.append(
                _reason_entry(
                    text=f"Fattore offensivo {team_name} ridotto ({b_off:.3f} → {a_off:.3f}).",
                    impact_type="offensive",
                    affected_team=team_key,
                    affected_prediction=team_key,
                ),
            )

    b_def = float(before_side.get("opponent_defensive_weakness_factor") or 1.0)
    a_def = float(after_side.get("opponent_defensive_weakness_factor") or 1.0)
    if abs(a_def - b_def) >= 0.02:
        opp = "avversario"
        if a_def > b_def:
            reasons.append(
                _reason_entry(
                    text=f"Debolezza difensiva {opp} aumentata: più SOT attesi per {team_name}.",
                    impact_type="defensive",
                    affected_team=team_key,
                    affected_prediction=team_key,
                ),
            )
        else:
            reasons.append(
                _reason_entry(
                    text=f"Debolezza difensiva {opp} ridotta: meno SOT attesi per {team_name}.",
                    impact_type="defensive",
                    affected_team=team_key,
                    affected_prediction=team_key,
                ),
            )

    b_players = {(_player_key(p), p.get("replacement_player_name")) for p in before_side.get("lineup_players") or []}
    a_players = {(_player_key(p), p.get("replacement_player_name")) for p in after_side.get("lineup_players") or []}
    for key, b_rep in b_players:
        a_rep = next((r for k, r in a_players if k == key), None)
        if b_rep != a_rep and (b_rep or a_rep):
            pname = key.split(":", 1)[-1].title() if ":" in key else key
            reasons.append(
                _reason_entry(
                    text=f"Il sostituto compensa parzialmente la perdita offensiva ({pname}).",
                    player_name=pname,
                    impact_type="offensive",
                    affected_team=team_key,
                    affected_prediction=team_key,
                ),
            )

    return reasons


class LineupRefreshImpactService:
    def compare(self, before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
        bh = before.get("predicted_home_sot")
        ba = before.get("predicted_away_sot")
        bt = before.get("predicted_total_sot")
        ah = after.get("predicted_home_sot")
        aa = after.get("predicted_away_sot")
        at = after.get("predicted_total_sot")

        delta_home = round(float(ah) - float(bh), 3) if bh is not None and ah is not None else None
        delta_away = round(float(aa) - float(ba), 3) if ba is not None and aa is not None else None
        delta_total = round(float(at) - float(bt), 3) if bt is not None and at is not None else None

        direction_home = direction_for_delta(delta_home)
        direction_away = direction_for_delta(delta_away)
        direction_total = direction_for_delta(delta_total)

        hn = str(before.get("home_team_name") or "Casa")
        an = str(before.get("away_team_name") or "Trasferta")
        reasons: list[dict[str, Any]] = []
        reasons.extend(
            _compare_side_players(
                before.get("home") or {},
                after.get("home") or {},
                team_name=hn,
                team_key="home",
            ),
        )
        reasons.extend(
            _compare_side_players(
                before.get("away") or {},
                after.get("away") or {},
                team_name=an,
                team_key="away",
            ),
        )

        if not reasons and direction_total == "FLAT":
            reasons.append(
                _reason_entry(
                    text="Nessuna variazione rilevante nella formazione.",
                    impact_type="offensive",
                    affected_team="total",
                    affected_prediction="total",
                ),
            )

        main_reason = "Nessuna variazione rilevante nella formazione."
        if direction_total != "FLAT":
            for r in reasons:
                txt = str(r.get("text") or "")
                if "Nessuna variazione" not in txt:
                    main_reason = txt
                    break
        elif reasons:
            main_reason = str(reasons[0].get("text") or main_reason)

        severity = _severity_for_delta(delta_total)

        return {
            "delta_home_sot": delta_home,
            "delta_away_sot": delta_away,
            "delta_total_sot": delta_total,
            "direction_home": direction_home,
            "direction_away": direction_away,
            "direction_total": direction_total,
            "before_total_sot": bt,
            "after_total_sot": at,
            "before_home_sot": bh,
            "after_home_sot": ah,
            "before_away_sot": ba,
            "after_away_sot": aa,
            "main_reason": main_reason,
            "severity": severity,
            "reasons": reasons,
        }

    def to_public_delta(self, impact: dict[str, Any]) -> dict[str, Any]:
        return {
            "direction_total": impact.get("direction_total"),
            "delta_total_sot": impact.get("delta_total_sot"),
            "direction_home": impact.get("direction_home"),
            "delta_home_sot": impact.get("delta_home_sot"),
            "direction_away": impact.get("direction_away"),
            "delta_away_sot": impact.get("delta_away_sot"),
            "before_total_sot": impact.get("before_total_sot"),
            "after_total_sot": impact.get("after_total_sot"),
            "before_home_sot": impact.get("before_home_sot"),
            "after_home_sot": impact.get("after_home_sot"),
            "before_away_sot": impact.get("before_away_sot"),
            "after_away_sot": impact.get("after_away_sot"),
            "main_reason": impact.get("main_reason"),
            "severity": impact.get("severity"),
            "reasons": impact.get("reasons") or [],
        }
