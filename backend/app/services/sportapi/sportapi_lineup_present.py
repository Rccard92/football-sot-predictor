"""Serializzazione lineups SportAPI per UI audit/debug (solo lettura DB)."""

from __future__ import annotations

import re
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.fixture_missing_player import FixtureMissingPlayer
from app.models.fixture_provider_mapping import PROVIDER_SPORTAPI, FixtureProviderMapping
from app.models.fixture_provider_lineup import FixtureProviderLineup
from app.models.fixture_provider_lineup_player import FixtureProviderLineupPlayer

DisplayRole = Literal["P", "D", "C", "A"]
MissingGroup = Literal["injured", "suspended", "other"]

_FORMATION_RE = re.compile(r"(\d+)")


def to_display_role(position: str | None) -> DisplayRole:
    if not position:
        return "C"
    p = str(position).strip().upper()
    if p in ("G", "GK", "GOALKEEPER", "GOAL KEEPER"):
        return "P"
    if p in ("D", "DF", "DEF", "DEFENDER", "CB", "LB", "RB", "WB"):
        return "D"
    if p in ("M", "MF", "MID", "MIDFIELDER", "CM", "DM", "AM", "LM", "RM"):
        return "C"
    if p in ("F", "FW", "FOR", "FORWARD", "ST", "CF", "LW", "RW", "ATT", "ATTACKER"):
        return "A"
    if p and p[0] in ("G", "D", "M", "F"):
        return {"G": "P", "D": "D", "M": "C", "F": "A"}[p[0]]  # type: ignore[return-value]
    return "C"


def extract_sort_key(raw: dict[str, Any] | None, original_index: int) -> tuple[int, int, int]:
    """Chiave ordinamento: campi tattici API, poi original_index."""
    if not isinstance(raw, dict):
        return (999, 999, original_index)
    for key in (
        "formationPosition",
        "formation_position",
        "positionOrder",
        "order",
        "grid",
        "row",
        "column",
        "x",
        "y",
    ):
        v = raw.get(key)
        if v is not None:
            try:
                return (0, int(v), original_index)
            except (TypeError, ValueError):
                pass
    return (1, original_index, original_index)


def extract_original_index(raw: dict[str, Any] | None, fallback: int) -> int:
    if isinstance(raw, dict) and "_original_index" in raw:
        try:
            return int(raw["_original_index"])
        except (TypeError, ValueError):
            pass
    return fallback


def classify_missing_group(
    *,
    reason: str | None,
    description: str | None,
    external_type: str | None,
) -> MissingGroup:
    blob = " ".join(
        x.lower()
        for x in (reason or "", description or "", external_type or "")
        if x
    )
    if any(
        k in blob
        for k in (
            "red_card_suspension",
            "yellow_card_suspension",
            "suspension",
            "squalifica",
        )
    ):
        return "suspended"
    if str(reason or "").strip() == "1":
        return "injured"
    if any(
        k in blob
        for k in ("injury", "muscle", "cruciate", "knee", "ankle", "illness", "infortun")
    ):
        return "injured"
    return "other"


def parse_formation_counts(formation: str | None) -> list[int]:
    if not formation:
        return []
    return [int(x) for x in _FORMATION_RE.findall(str(formation))]


def _sort_by_role_and_index(players: list[dict[str, Any]], role: DisplayRole) -> list[dict[str, Any]]:
    subset = [p for p in players if p.get("display_role") == role]
    subset.sort(key=lambda p: extract_sort_key(p.get("_raw_payload"), int(p.get("original_index") or 0)))
    return subset


def _split_pool(pool: list[dict[str, Any]], n: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if n <= 0:
        return [], list(pool)
    return pool[:n], pool[n:]


def build_tactical_lines(formation: str | None, starters: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    """Righe tattiche ordinate: P, poi linee del modulo, fallback per ruolo."""
    if not starters:
        return []

    by_role: dict[DisplayRole, list[dict[str, Any]]] = {
        "P": _sort_by_role_and_index(starters, "P"),
        "D": _sort_by_role_and_index(starters, "D"),
        "C": _sort_by_role_and_index(starters, "C"),
        "A": _sort_by_role_and_index(starters, "A"),
    }

    lines: list[list[dict[str, Any]]] = []
    if by_role["P"]:
        lines.append(by_role["P"][:1])

    counts = parse_formation_counts(formation)
    d_pool = list(by_role["D"])
    c_pool = list(by_role["C"])
    a_pool = list(by_role["A"])

    if counts:
        for i, n in enumerate(counts):
            if i == 0:
                chunk, d_pool = _split_pool(d_pool, n)
                if chunk:
                    lines.append(chunk)
            elif i == len(counts) - 1:
                chunk, a_pool = _split_pool(a_pool, n)
                if chunk:
                    lines.append(chunk)
            else:
                chunk, c_pool = _split_pool(c_pool, n)
                if chunk:
                    lines.append(chunk)
        remainder = d_pool + c_pool + a_pool
        if remainder:
            lines.append(remainder)
    else:
        for role in ("D", "C", "A"):
            if by_role[role]:
                lines.append(by_role[role])

    return lines


def _player_row(p: FixtureProviderLineupPlayer, *, idx: int) -> dict[str, Any]:
    raw = p.raw_payload if isinstance(p.raw_payload, dict) else {}
    oi = extract_original_index(raw, idx)
    display = to_display_role(p.position)
    return {
        "provider_player_id": int(p.provider_player_id),
        "player_name": p.player_name,
        "short_name": p.short_name,
        "position": p.position,
        "display_role": display,
        "jersey_number": p.jersey_number,
        "is_substitute": bool(p.is_substitute),
        "avg_rating": p.avg_rating,
        "original_index": oi,
        "_raw_payload": raw,
    }


def _missing_row(m: FixtureMissingPlayer, *, idx: int) -> dict[str, Any]:
    raw = m.raw_payload if isinstance(m.raw_payload, dict) else {}
    oi = extract_original_index(raw, idx)
    group = classify_missing_group(
        reason=m.reason,
        description=m.description,
        external_type=m.external_type,
    )
    return {
        "provider_player_id": int(m.provider_player_id),
        "player_name": m.player_name,
        "short_name": None,
        "position": m.position,
        "display_role": to_display_role(m.position),
        "jersey_number": m.jersey_number,
        "reason": m.reason,
        "description": m.description,
        "external_type": m.external_type,
        "expected_end_date": m.expected_end_date.isoformat() if m.expected_end_date else None,
        "original_index": oi,
        "absence_group": group,
        "_raw_payload": raw,
    }


def _serialize_player_for_api(row: dict[str, Any]) -> dict[str, Any]:
    out = {k: v for k, v in row.items() if not k.startswith("_")}
    return out


def _build_side_team(
    *,
    team_name: str,
    formation: str | None,
    confirmed: bool | None,
    players: list[FixtureProviderLineupPlayer],
    missing: list[FixtureMissingPlayer],
    side: str,
) -> dict[str, Any]:
    side_players = [p for p in players if p.team_side == side]
    side_missing = [m for m in missing if m.team_side == side]

    starters_raw: list[dict[str, Any]] = []
    subs_raw: list[dict[str, Any]] = []
    for i, p in enumerate(side_players):
        row = _player_row(p, idx=i)
        if p.is_substitute:
            subs_raw.append(row)
        else:
            starters_raw.append(row)

    starters = [_serialize_player_for_api(r) for r in starters_raw]
    substitutes = [_serialize_player_for_api(r) for r in subs_raw]
    tactical_lines = [
        [_serialize_player_for_api(p) for p in line]
        for line in build_tactical_lines(formation, starters_raw)
    ]

    missing_grouped: dict[str, list[dict[str, Any]]] = {
        "injured": [],
        "suspended": [],
        "other": [],
    }
    for i, m in enumerate(side_missing):
        mr = _missing_row(m, idx=i)
        grp = mr.pop("absence_group", "other")
        missing_grouped[str(grp)].append(_serialize_player_for_api(mr))

    return {
        "team_name": team_name,
        "formation": formation,
        "confirmed": confirmed,
        "starters": starters,
        "substitutes": substitutes,
        "tactical_lines": tactical_lines,
        "missing_players": missing_grouped,
    }


def build_sportapi_lineups_audit(
    db: Session,
    fixture_id: int,
    *,
    home_team_name: str,
    away_team_name: str,
) -> dict[str, Any]:
    """Payload UI audit/debug — solo lettura DB, nessuna chiamata SportAPI."""
    internal_id = int(fixture_id)
    mapping = db.scalar(
        select(FixtureProviderMapping).where(
            FixtureProviderMapping.fixture_id == internal_id,
            FixtureProviderMapping.provider_name == PROVIDER_SPORTAPI,
        ),
    )
    lineup = db.scalar(
        select(FixtureProviderLineup).where(
            FixtureProviderLineup.fixture_id == internal_id,
            FixtureProviderLineup.provider_name == PROVIDER_SPORTAPI,
        ),
    )

    empty_side = lambda name: {  # noqa: E731
        "team_name": name,
        "formation": None,
        "confirmed": None,
        "starters": [],
        "substitutes": [],
        "tactical_lines": [],
        "missing_players": {"injured": [], "suspended": [], "other": []},
    }

    if lineup is None:
        return {
            "available": False,
            "provider_event_id": int(mapping.provider_event_id) if mapping else None,
            "confidence_score": float(mapping.confidence_score) if mapping and mapping.confidence_score is not None else None,
            "confirmed": None,
            "fetched_at": None,
            "home": empty_side(home_team_name),
            "away": empty_side(away_team_name),
        }

    players = list(
        db.scalars(
            select(FixtureProviderLineupPlayer)
            .where(
                FixtureProviderLineupPlayer.fixture_id == internal_id,
                FixtureProviderLineupPlayer.provider_name == PROVIDER_SPORTAPI,
            )
            .order_by(
                FixtureProviderLineupPlayer.team_side,
                FixtureProviderLineupPlayer.is_substitute,
                FixtureProviderLineupPlayer.jersey_number,
            ),
        ).all(),
    )
    missing = list(
        db.scalars(
            select(FixtureMissingPlayer).where(
                FixtureMissingPlayer.fixture_id == internal_id,
                FixtureMissingPlayer.provider_name == PROVIDER_SPORTAPI,
            ),
        ).all(),
    )

    confirmed = bool(lineup.confirmed)
    home = _build_side_team(
        team_name=home_team_name,
        formation=lineup.home_formation,
        confirmed=confirmed,
        players=players,
        missing=missing,
        side="home",
    )
    away = _build_side_team(
        team_name=away_team_name,
        formation=lineup.away_formation,
        confirmed=confirmed,
        players=players,
        missing=missing,
        side="away",
    )

    has_data = bool(
        home["starters"]
        or away["starters"]
        or home["substitutes"]
        or away["substitutes"]
        or any(home["missing_players"].values())
        or any(away["missing_players"].values()),
    )

    return {
        "available": has_data,
        "provider_event_id": int(mapping.provider_event_id) if mapping else int(lineup.provider_event_id),
        "confidence_score": float(mapping.confidence_score) if mapping and mapping.confidence_score is not None else None,
        "confirmed": confirmed,
        "fetched_at": lineup.fetched_at.isoformat() if lineup.fetched_at else None,
        "home": home,
        "away": away,
    }
