"""Resolver campi team_raw pre-match per simulatore v3.1 (PIT, no leakage)."""

from __future__ import annotations

from typing import Any

LEAGUE_AVG_SHOTS_FOR = 12.0
LEAGUE_AVG_SOT_FOR = 3.35


def _league_avgs(league_context: dict[str, Any] | None) -> tuple[float, float, float]:
    lc = league_context if isinstance(league_context, dict) else {}
    sot = _f(lc.get("league_avg_sot_for")) or LEAGUE_AVG_SOT_FOR
    shots = _f(lc.get("league_avg_shots_for")) or _f(lc.get("league_avg_total_shots")) or LEAGUE_AVG_SHOTS_FOR
    xg = _f(lc.get("league_avg_xg_for")) or 1.25
    return float(sot), float(xg), float(shots)

SHOTS_FIELD_ALIASES = (
    "avg_total_shots_for",
    "avg_shots_for",
    "shots_for_avg",
    "total_shots_for_avg",
    "avg_total_shots",
    "shots_total_for",
    "total_shots_avg",
)

SHOTS_AGAINST_ALIASES = (
    "avg_total_shots_against",
    "avg_shots_against",
    "shots_against_avg",
    "total_shots_against_avg",
)


def _f(v: Any) -> float | None:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _first_alias(team_raw: dict[str, Any], aliases: tuple[str, ...]) -> tuple[float | None, str | None]:
    for key in aliases:
        val = _f(team_raw.get(key))
        if val is not None:
            return val, key
    return None, None


def resolve_shots_for_side(
    team_raw: dict[str, Any],
    macros: dict[str, float | None],
    league_context: dict[str, Any] | None,
    *,
    field: str = "for",
) -> dict[str, Any]:
    """Risolve volume tiri; mai actual post-match della fixture target."""
    aliases = SHOTS_FIELD_ALIASES if field == "for" else SHOTS_AGAINST_ALIASES
    league_sot, _xg, league_shots = _league_avgs(league_context)
    _ = league_sot

    raw, source = _first_alias(team_raw, aliases)
    if raw is not None:
        if 0.65 <= raw <= 1.45:
            return {
                "value": round(league_shots * raw, 4),
                "raw_value": raw,
                "source_field_used": f"team_raw.{source}",
                "resolved": True,
                "resolution": "macro_index_to_absolute",
            }
        if 4.0 <= raw <= 25.0:
            return {
                "value": raw,
                "raw_value": raw,
                "source_field_used": f"team_raw.{source}",
                "resolved": True,
                "resolution": "absolute",
            }

    pace = _f(macros.get("pace_control_index"))
    if pace is not None and 0.5 <= pace <= 1.8:
        return {
            "value": round(league_shots * pace, 4),
            "raw_value": pace,
            "source_field_used": "macro.pace_control_index",
            "resolved": True,
            "resolution": "pace_macro_proxy",
        }

    return {
        "value": None,
        "raw_value": None,
        "source_field_used": "unavailable",
        "resolved": False,
        "resolution": None,
        "note": "feature non disponibile da fonte DB",
    }


def enrich_team_raw_side(
    team_raw: dict[str, Any],
    macros: dict[str, float | None],
    league_context: dict[str, Any] | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Copia team_raw arricchito con avg_total_shots_for risolto."""
    out = dict(team_raw)
    shots_res = resolve_shots_for_side(team_raw, macros, league_context, field="for")
    if shots_res.get("resolved") and shots_res.get("value") is not None:
        raw_val = shots_res.get("raw_value")
        if raw_val is not None and 0.65 <= float(raw_val) <= 1.45:
            out["avg_total_shots_for"] = raw_val
        else:
            out["avg_total_shots_for"] = shots_res["value"]
    return out, shots_res


def aggregate_shots_availability(resolutions: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggrega risoluzioni shots da tutte le fixture (home+away)."""
    n = len(resolutions)
    available = sum(1 for r in resolutions if r.get("resolved"))
    source_counts: dict[str, int] = {}
    for r in resolutions:
        src = str(r.get("source_field_used") or "unavailable")
        source_counts[src] = source_counts.get(src, 0) + 1
    missing = n - available
    note = None
    if n > 0 and missing / n > 0.05:
        note = "feature non disponibile da fonte DB su parte significativa delle fixture"
    return {
        "avg_total_shots_for": {
            "available_count": available,
            "missing_count": missing,
            "fixtures_sides_total": n,
            "source_field_used_counts": source_counts,
            "note": note,
        },
    }
