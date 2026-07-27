"""Estrazione segnali matrice Cecchino per settlement storico Lab.

Riusa la mappatura canonica famiglia → modello/cella → mercato
(`cecchino_signal_target_mapping`). Non applica value-gate Betfair / DRAW_PT operativo.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from app.services.cecchino.cecchino_signal_target_mapping import (
    is_valid_scala_activation,
    map_cecchino_signal_to_target,
    map_column_to_source,
    map_row_key_to_signal_group,
)


def iter_active_signal_cells(signals_matrix: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Celle SI dalla matrice canonica (`row["key"]` + `row["signals"][modello]`)."""
    if not isinstance(signals_matrix, dict):
        return []
    rows = signals_matrix.get("rows") or []
    if not isinstance(rows, list):
        return []
    cells: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        row_key = str(row.get("key") or "")
        signal_group = map_row_key_to_signal_group(row_key)
        if not signal_group:
            continue
        signals = row.get("signals")
        if not isinstance(signals, dict):
            continue
        for column_key, raw_value in signals.items():
            if str(raw_value).upper() != "SI":
                continue
            source_column = map_column_to_source(str(column_key))
            if not source_column:
                continue
            if not is_valid_scala_activation(signal_group, source_column):
                continue
            cells.append(
                {
                    "row_key": row_key,
                    "signal_group": signal_group,
                    "signal_family": signal_group,
                    "signal_label": str(row.get("label") or row_key),
                    "source_column": source_column,
                    "column_key": str(column_key),
                    "raw_signal_value": "SI",
                }
            )
    return cells


def build_market_signal_index(
    signals_matrix: dict[str, Any] | None,
) -> dict[str, dict[str, Any]]:
    """Mappa market_key → payload segnale (active, sources, family, count)."""
    by_market: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for cell in iter_active_signal_cells(signals_matrix):
        target = map_cecchino_signal_to_target(cell["signal_group"], cell["source_column"])
        market_key = target.get("target_market_key")
        if not market_key:
            continue
        by_market[str(market_key)].append(
            {
                **cell,
                "target_market_key": str(market_key),
                "target_market_label": target.get("target_market_label"),
            }
        )

    out: dict[str, dict[str, Any]] = {}
    for market_key, sources in by_market.items():
        families = sorted({str(s["signal_family"]) for s in sources})
        out[market_key] = {
            "signal_active": True,
            "signal_sources_json": {
                "sources": sources,
                "signal_family": families[0] if len(families) == 1 else "|".join(families),
                "signal_families": families,
                "active_signal_count": len(sources),
            },
            "signal_family": families[0] if len(families) == 1 else "|".join(families),
            "active_signal_count": len(sources),
        }
    return out


def empty_signal_payload() -> dict[str, Any]:
    return {
        "signal_active": False,
        "signal_sources_json": {
            "sources": [],
            "signal_family": None,
            "signal_families": [],
            "active_signal_count": 0,
        },
        "signal_family": None,
        "active_signal_count": 0,
    }


def signal_payload_for_market(
    index: dict[str, dict[str, Any]],
    market_key: str,
) -> dict[str, Any]:
    return index.get(market_key) or empty_signal_payload()
