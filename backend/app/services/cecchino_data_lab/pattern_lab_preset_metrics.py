"""Valutazione economica preset Pattern Lab.

Separa pattern filters da performance_quote_policy=real_only:
- selections = righe che matchano il pattern
- real_quote_count / profit / ROI / avg odds = solo Bet365 reali
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Iterable

from app.services.cecchino_data_lab.pattern_lab_filters import parse_pattern_lab_filters
from app.services.cecchino_data_lab.pattern_lab_presets import (
    PERFORMANCE_QUOTE_POLICY_REAL_ONLY,
    PATTERN_LAB_PRESETS,
    PRESET_REGISTRY_VERSION,
    derive_preset_status_group,
    preset_scientific_filters,
    scientific_filters_sha256,
)


def is_real_quote(row: dict[str, Any]) -> bool:
    """True se la riga ha quota Bet365 reale (performance real_only)."""
    return row.get("pre_quote_type") == "real" or row.get("pre_is_real_book_quote") is True


def empty_econ_bucket() -> dict[str, Any]:
    """Bucket mutabile per aggregazione economica real_only."""
    return {
        "selections": 0,
        "real_quote_count": 0,
        "wins": 0,
        "losses": 0,
        "void": 0,
        "profit_1u": 0.0,
        "quota_sum": 0.0,
        "quota_n": 0,
    }


def bump_pattern_selection(bucket: dict[str, Any], row: dict[str, Any]) -> None:
    """Incrementa selections (match pattern, indipendente da quote reale)."""
    _ = row
    bucket["selections"] += 1


def bump_real_only_econ(bucket: dict[str, Any], row: dict[str, Any]) -> None:
    """Metriche economiche solo su quote reali."""
    if not is_real_quote(row):
        return
    bucket["real_quote_count"] += 1
    if row.get("target_won") is True:
        bucket["wins"] += 1
    elif row.get("target_lost") is True:
        bucket["losses"] += 1
    elif row.get("target_void") is True:
        bucket["void"] += 1
    # Preferisci profit reale dedicato; fallback target_profit_1u se già real.
    profit = row.get("target_profit_1u_real")
    if profit is None and is_real_quote(row):
        profit = row.get("target_profit_1u")
    if profit is not None:
        bucket["profit_1u"] += float(profit)
    quota = row.get("pre_quota_bet365")
    if quota is not None:
        bucket["quota_sum"] += float(quota)
        bucket["quota_n"] += 1


def finalize_real_only_econ(
    bucket: dict[str, Any], *, key: str | None = None
) -> dict[str, Any]:
    """Finalizza ROI/WR/avg odds su real_quote_count (non su selections)."""
    real_n = int(bucket["real_quote_count"])
    decided = int(bucket["wins"]) + int(bucket["losses"])
    win_rate = (float(bucket["wins"]) / decided) if decided else None
    avg_quota = (
        float(bucket["quota_sum"]) / float(bucket["quota_n"]) if bucket["quota_n"] else None
    )
    profit = float(bucket["profit_1u"])
    roi = (profit / real_n) if real_n else None
    out: dict[str, Any] = {
        "selections": int(bucket["selections"]),
        "real_quote_count": real_n,
        "wins": int(bucket["wins"]),
        "losses": int(bucket["losses"]),
        "void": int(bucket["void"]),
        "win_rate": win_rate,
        "avg_real_odds": avg_quota,
        "profit_1u": profit,
        "roi": roi,
    }
    if key is not None:
        out["key"] = key
    return out


# Alias legacy interni (smoke / AI summary): stessa implementazione pubblica.
_is_real_quote = is_real_quote
_empty_econ = empty_econ_bucket
_bump_pattern = bump_pattern_selection
_bump_real = bump_real_only_econ
_finalize_econ = finalize_real_only_econ


def _preset_meta_export(preset: dict[str, Any]) -> dict[str, Any]:
    """Meta scientifici esportati (non alterano i filtri)."""
    filters = preset_scientific_filters(preset)
    return {
        "preset_id": preset["id"],
        "label": preset.get("label"),
        "status": preset.get("status"),
        "ui_badge": preset.get("ui_badge"),
        "status_group": derive_preset_status_group(preset.get("status")),
        "discovery_seasons": list(preset.get("discovery_seasons") or []),
        "validation_seasons": list(preset.get("validation_seasons") or []),
        "validation_history": list(preset.get("validation_history") or []),
        "first_oos_season": preset.get("first_oos_season"),
        "flags": dict(preset.get("flags") or {}) or None,
        "filters": filters,
        "scientific_filters_sha256": scientific_filters_sha256(filters),
        "performance_quote_policy": preset.get(
            "performance_quote_policy", PERFORMANCE_QUOTE_POLICY_REAL_ONLY
        ),
        "notes": preset.get("notes"),
    }


def _month_key(row: dict[str, Any]) -> str:
    kick = str(row.get("kickoff_at") or "")[:7]
    return kick if len(kick) == 7 else "unknown"


def _quarter_key(row: dict[str, Any]) -> str:
    kick = str(row.get("kickoff_at") or "")[:7]
    if len(kick) != 7:
        return "unknown"
    try:
        y, m = kick.split("-")
        q = (int(m) - 1) // 3 + 1
        return f"{y}-Q{q}"
    except (TypeError, ValueError):
        return "unknown"


def evaluate_preset_on_rows(
    preset: dict[str, Any],
    rows: Iterable[dict[str, Any]],
) -> dict[str, Any]:
    """Aggrega un preset su righe (filtra con i filters scientifici del preset)."""
    from app.services.cecchino_data_lab.pattern_lab_filters import row_passes_filters

    filters = parse_pattern_lab_filters(preset_scientific_filters(preset))
    total = empty_econ_bucket()
    by_competition: dict[str, dict[str, Any]] = {}
    by_month: dict[str, dict[str, Any]] = {}
    by_quarter: dict[str, dict[str, Any]] = {}
    by_season: dict[str, dict[str, Any]] = {}

    for row in rows:
        if not row_passes_filters(row, filters):
            continue
        bump_pattern_selection(total, row)
        bump_real_only_econ(total, row)

        for store, key in (
            (by_competition, str(row.get("competition") or "unknown")),
            (by_month, _month_key(row)),
            (by_quarter, _quarter_key(row)),
            (by_season, str(row.get("season") or "unknown")),
        ):
            if key not in store:
                store[key] = empty_econ_bucket()
            bump_pattern_selection(store[key], row)
            bump_real_only_econ(store[key], row)

    return {
        **_preset_meta_export(preset),
        **finalize_real_only_econ(total),
        "by_competition": [
            finalize_real_only_econ(b, key=k) for k, b in sorted(by_competition.items())
        ],
        "by_month": [finalize_real_only_econ(b, key=k) for k, b in sorted(by_month.items())],
        "by_quarter": [
            finalize_real_only_econ(b, key=k) for k, b in sorted(by_quarter.items())
        ],
        "by_season": [
            finalize_real_only_econ(b, key=k) for k, b in sorted(by_season.items())
        ],
    }


def evaluate_all_presets(
    db: Any,
    run_ids: list[int],
    *,
    presets: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Una passata sulle righe eligible; applica ogni preset in memoria."""
    from app.services.cecchino_data_lab.pattern_lab_filters import row_passes_filters
    from app.services.cecchino_data_lab.pattern_lab_service import iter_pattern_lab_rows

    preset_list = presets if presets is not None else list(PATTERN_LAB_PRESETS)
    parsed = [
        (p, parse_pattern_lab_filters(preset_scientific_filters(p))) for p in preset_list
    ]
    totals: dict[str, dict[str, Any]] = {p["id"]: empty_econ_bucket() for p, _ in parsed}
    by_comp: dict[str, dict[str, dict[str, Any]]] = {p["id"]: {} for p, _ in parsed}
    by_month: dict[str, dict[str, dict[str, Any]]] = {p["id"]: {} for p, _ in parsed}
    by_quarter: dict[str, dict[str, dict[str, Any]]] = {p["id"]: {} for p, _ in parsed}
    by_season: dict[str, dict[str, dict[str, Any]]] = {p["id"]: {} for p, _ in parsed}

    # Universo base: eligible_core, market_informative (come default Pattern Lab).
    base_filters = parse_pattern_lab_filters(
        {"eligibility": "eligible_core", "market_informative": True}
    )
    for row in iter_pattern_lab_rows(db, run_ids, filters=base_filters, apply_filters=True):
        for preset, filt in parsed:
            # I filtri preset includono già eligibility + market_informative.
            # Riapplicare solo i vincoli del preset sulla riga già informative.
            if not row_passes_filters(row, filt):
                continue
            pid = preset["id"]
            bump_pattern_selection(totals[pid], row)
            bump_real_only_econ(totals[pid], row)
            for store, key in (
                (by_comp[pid], str(row.get("competition") or "unknown")),
                (by_month[pid], _month_key(row)),
                (by_quarter[pid], _quarter_key(row)),
                (by_season[pid], str(row.get("season") or "unknown")),
            ):
                if key not in store:
                    store[key] = empty_econ_bucket()
                bump_pattern_selection(store[key], row)
                bump_real_only_econ(store[key], row)

    items = []
    for preset, _ in parsed:
        pid = preset["id"]
        items.append(
            {
                **_preset_meta_export(preset),
                **finalize_real_only_econ(totals[pid]),
                "by_competition": [
                    finalize_real_only_econ(b, key=k)
                    for k, b in sorted(by_comp[pid].items())
                ],
                "by_month": [
                    finalize_real_only_econ(b, key=k)
                    for k, b in sorted(by_month[pid].items())
                ],
                "by_quarter": [
                    finalize_real_only_econ(b, key=k)
                    for k, b in sorted(by_quarter[pid].items())
                ],
                "by_season": [
                    finalize_real_only_econ(b, key=k)
                    for k, b in sorted(by_season[pid].items())
                ],
            }
        )

    return {
        "registry_version": PRESET_REGISTRY_VERSION,
        "performance_quote_policy": PERFORMANCE_QUOTE_POLICY_REAL_ONLY,
        "run_ids": [int(x) for x in run_ids],
        "presets": items,
    }
