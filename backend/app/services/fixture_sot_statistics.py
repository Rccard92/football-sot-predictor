"""Estrazione SOT da payload API-Football GET /fixtures/statistics."""

from __future__ import annotations

import json
import re
import unicodedata
from typing import Any

from app.services.fixture_team_stats_mapping import _parse_float

SOT_LABELS_NORM = frozenset(
    {
        "shots on goal",
        "shots on target",
        "shot on goal",
        "shot on target",
        "tiri in porta",
        "tiri nello specchio",
        "on target",
    },
)


def _norm_label(raw: str) -> str:
    return " ".join((raw or "").strip().lower().split())


def _norm_team_name(name: str | None) -> str:
    if not name:
        return ""
    s = unicodedata.normalize("NFKD", name.strip().lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return " ".join(s.split())


def parse_sot_stat_value(val: Any) -> float | None:
    """Accetta 5, 5.0, \"5\"; rifiuta null, \"-\", percentuali."""
    if val is None or val == "":
        return None
    if isinstance(val, bool):
        return None
    if isinstance(val, int):
        return float(val)
    if isinstance(val, float):
        return val
    s = str(val).strip()
    if not s or s == "-" or s.lower() in ("null", "none"):
        return None
    if "%" in s:
        return None
    parsed = _parse_float(s)
    if parsed is not None:
        return parsed
    try:
        return float(s.replace(",", "."))
    except ValueError:
        return None


def _find_sot_in_statistics_list(statistics: list[dict[str, Any]] | None) -> tuple[float | None, str | None]:
    """Ritorna (valore SOT, label originale trovata)."""
    for item in statistics or []:
        if not isinstance(item, dict):
            continue
        label_raw = str(item.get("type") or "").strip()
        label = _norm_label(label_raw)
        if label not in SOT_LABELS_NORM:
            continue
        v = parse_sot_stat_value(item.get("value"))
        if v is not None:
            return v, label_raw or label
    return None, None


def _team_api_id(block: dict[str, Any]) -> int | None:
    team = block.get("team") or {}
    tid = team.get("id")
    if tid is None:
        return None
    try:
        return int(tid)
    except (TypeError, ValueError):
        return None


def _team_name_from_block(block: dict[str, Any]) -> str:
    team = block.get("team") or {}
    return str(team.get("name") or "").strip()


def _sot_from_block(block: dict[str, Any]) -> tuple[float | None, str | None]:
    return _find_sot_in_statistics_list(block.get("statistics"))


def extract_sot_from_statistics_response(
    stats_blocks: list[dict],
    *,
    home_team_id: int,
    away_team_id: int,
    home_api_team_id: int | None,
    away_api_team_id: int | None,
    home_team_name: str | None = None,
    away_team_name: str | None = None,
    raw_sample_max_chars: int = 2048,
) -> dict[str, Any]:
    """
    Estrae home/away/total SOT da blocchi statistics API-Football.

    Match: api_team_id → nome squadra normalizzato → fallback ordine (solo se api id assenti).
    """
    blocks = [b for b in (stats_blocks or []) if isinstance(b, dict)]
    labels_seen: list[str] = []
    for block in blocks:
        for item in block.get("statistics") or []:
            if isinstance(item, dict):
                t = str(item.get("type") or "").strip()
                if t and t not in labels_seen:
                    labels_seen.append(t)

    home_sot: float | None = None
    away_sot: float | None = None
    metric_label_home: str | None = None
    metric_label_away: str | None = None
    match_method: str | None = None
    matched_home = False
    matched_away = False
    norm_home = _norm_team_name(home_team_name)
    norm_away = _norm_team_name(away_team_name)

    for block in blocks:
        api_id = _team_api_id(block)
        sot, metric_label = _sot_from_block(block)
        if sot is None:
            continue
        block_name = _norm_team_name(_team_name_from_block(block))

        if home_api_team_id is not None and api_id == home_api_team_id:
            home_sot = sot
            metric_label_home = metric_label
            matched_home = True
            match_method = "api_team_id"
        elif away_api_team_id is not None and api_id == away_api_team_id:
            away_sot = sot
            metric_label_away = metric_label
            matched_away = True
            match_method = "api_team_id"
        elif norm_home and block_name and block_name == norm_home and home_sot is None:
            home_sot = sot
            metric_label_home = metric_label
            matched_home = True
            if match_method is None:
                match_method = "team_name"
        elif norm_away and block_name and block_name == norm_away and away_sot is None:
            away_sot = sot
            metric_label_away = metric_label
            matched_away = True
            if match_method is None:
                match_method = "team_name"

    if home_api_team_id is None and away_api_team_id is None and len(blocks) == 2:
        if home_sot is None or away_sot is None:
            first_sot, first_label = _sot_from_block(blocks[0])
            second_sot, second_label = _sot_from_block(blocks[1])
            if home_sot is None and first_sot is not None:
                home_sot = first_sot
                metric_label_home = first_label
                matched_home = True
                match_method = "order_fallback"
            if away_sot is None and second_sot is not None:
                away_sot = second_sot
                metric_label_away = second_label
                matched_away = True
                if match_method is None:
                    match_method = "order_fallback"

    total_sot: float | None = None
    sot_available = False
    sot_unavailable_reason: str | None = None
    extraction_error: str | None = None

    statistics_found = len(blocks) > 0

    if not blocks:
        sot_unavailable_reason = "Statistiche API-Sports vuote"
        extraction_error = "empty_response"
    elif home_sot is not None and away_sot is not None:
        total_sot = round(home_sot + away_sot, 2)
        sot_available = True
    else:
        if home_sot is None and away_sot is None:
            sot_unavailable_reason = "Nessun SOT nei blocchi statistiche"
            extraction_error = "metric_not_found"
        else:
            sot_unavailable_reason = "SOT parziale (manca casa o trasferta)"
            extraction_error = "partial_team_sot"

    raw_sample = json.dumps(stats_blocks, ensure_ascii=False)[:raw_sample_max_chars]

    return {
        "home_sot": home_sot,
        "away_sot": away_sot,
        "total_sot": total_sot,
        "sot_available": sot_available,
        "sot_unavailable_reason": sot_unavailable_reason,
        "debug": {
            "statistics_found": statistics_found,
            "raw_blocks_count": len(blocks),
            "matched_home": matched_home,
            "matched_away": matched_away,
            "labels_seen": labels_seen[:30],
            "metric_label_home": metric_label_home,
            "metric_label_away": metric_label_away,
            "match_method": match_method,
            "extraction_error": extraction_error,
            "home_api_team_id": home_api_team_id,
            "away_api_team_id": away_api_team_id,
            "home_team_id": home_team_id,
            "away_team_id": away_team_id,
            "raw_statistics_sample": raw_sample,
        },
    }
