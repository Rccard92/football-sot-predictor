"""Estrazione segnali matrice Cecchino per settlement storico Lab.

Formula corrente V3 (Decimal2) + consenso min-two: non ogni cella SI è un
segno acquisito. Separa SI grezzi (`iter_raw_si_signal_cells`) da gruppi
acquisiti (`iter_acquired_signal_groups`).

Riusa la mappatura canonica famiglia → modello/cella → mercato
(`cecchino_signal_target_mapping`). Non applica value-gate Betfair / DRAW_PT operativo.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from app.services.cecchino.cecchino_signal_consensus import (
    CURRENT_SIGNAL_FORMULA_VERSION,
    SIGNAL_CONSENSUS_POLICY_VERSION,
    compute_consensus_for_matrix_row,
    inherit_draw_consensus,
    is_current_signal_matrix,
)
from app.services.cecchino.cecchino_signal_target_mapping import (
    is_valid_scala_activation,
    map_cecchino_signal_to_target,
    map_column_to_source,
    map_draw_pt_derived_target,
    map_row_key_to_signal_group,
)


def _unwrap_matrix(signals_matrix: dict[str, Any] | None) -> dict[str, Any] | None:
    """Supporta wrapper A–F (`default_matrix`) e matrice flat legacy."""
    if not isinstance(signals_matrix, dict):
        return signals_matrix
    if isinstance(signals_matrix.get("default_matrix"), dict):
        return signals_matrix["default_matrix"]
    models = signals_matrix.get("models")
    if isinstance(models, dict):
        f = models.get("F")
        if isinstance(f, dict) and isinstance(f.get("matrix"), dict):
            return f["matrix"]
    return signals_matrix


def iter_raw_si_signal_cells(signals_matrix: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Celle SI grezze dalla matrice canonica (`row["key"]` + `row["signals"][modello]`)."""
    signals_matrix = _unwrap_matrix(signals_matrix)
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


def iter_active_signal_cells(signals_matrix: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Deprecated: alias di `iter_raw_si_signal_cells` (SI grezzi, non acquisiti)."""
    return iter_raw_si_signal_cells(signals_matrix)


def iter_acquired_signal_groups(signals_matrix: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Gruppi con consenso acquisito (solo matrice current V3 + status available).

    DRAW_PT non è una riga matrice: non viene prodotto qui (eredità in
    `build_market_signal_index` quando DRAW è acquisito).
    """
    signals_matrix = _unwrap_matrix(signals_matrix)
    if not is_current_signal_matrix(signals_matrix):
        return []

    rows = signals_matrix.get("rows") or []
    if not isinstance(rows, list):
        return []

    raw_by_group: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for cell in iter_raw_si_signal_cells(signals_matrix):
        raw_by_group[str(cell["signal_group"])].append(cell)

    groups: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        row_key = str(row.get("key") or "")
        signal_group = map_row_key_to_signal_group(row_key)
        if not signal_group:
            continue
        consensus = row.get("consensus")
        if not isinstance(consensus, dict):
            consensus = compute_consensus_for_matrix_row(row)
        if not consensus.get("is_acquired"):
            continue
        groups.append(
            {
                "signal_group": signal_group,
                "signal_label": str(row.get("label") or row_key),
                "is_acquired": True,
                "acquisition_status": consensus.get("acquisition_status"),
                "consensus_yes_count": int(consensus.get("consensus_yes_count") or 0),
                "consensus_required_count": int(consensus.get("consensus_required_count") or 0),
                "consensus_available_count": int(consensus.get("consensus_available_count") or 0),
                "consensus_yes_columns": list(consensus.get("consensus_yes_columns") or []),
                "consensus_policy_version": (
                    consensus.get("consensus_policy_version") or SIGNAL_CONSENSUS_POLICY_VERSION
                ),
                "formula_version": CURRENT_SIGNAL_FORMULA_VERSION,
                "raw_si_cells": list(raw_by_group.get(signal_group, [])),
            }
        )
    return groups


def _primary_source_column(group: dict[str, Any]) -> str:
    yes_columns = group.get("consensus_yes_columns") or []
    if yes_columns:
        return str(yes_columns[0])
    raw_cells = group.get("raw_si_cells") or []
    if raw_cells:
        return str(raw_cells[0].get("source_column") or "EXCEL_D")
    return "EXCEL_D"


def _acquired_group_target(group: dict[str, Any]) -> dict[str, Any]:
    signal_group = str(group.get("signal_group") or "")
    if signal_group == "DRAW_PT":
        return map_draw_pt_derived_target()
    return map_cecchino_signal_to_target(signal_group, _primary_source_column(group))


def _with_inherited_draw_pt(acquired_groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Se DRAW è acquisito, aggiunge DRAW_PT ereditato (non è riga matrice)."""
    by_group = {str(g["signal_group"]): g for g in acquired_groups}
    draw = by_group.get("DRAW")
    if draw is None or "DRAW_PT" in by_group:
        return list(acquired_groups)
    draw_consensus = {
        "consensus_policy_version": draw.get("consensus_policy_version"),
        "consensus_eligible": True,
        "consensus_available_count": draw.get("consensus_available_count"),
        "consensus_required_count": draw.get("consensus_required_count"),
        "consensus_yes_count": draw.get("consensus_yes_count"),
        "consensus_yes_columns": draw.get("consensus_yes_columns"),
        "consensus_passed": True,
        "acquisition_status": draw.get("acquisition_status"),
        "is_acquired": True,
        "consensus_source_group": "DRAW",
    }
    pt = inherit_draw_consensus(draw_consensus)
    if not pt.get("is_acquired"):
        return list(acquired_groups)
    out = list(acquired_groups)
    out.append(
        {
            "signal_group": "DRAW_PT",
            "signal_label": "X PT",
            "is_acquired": True,
            "acquisition_status": pt.get("acquisition_status"),
            "consensus_yes_count": int(pt.get("consensus_yes_count") or 0),
            "consensus_required_count": int(pt.get("consensus_required_count") or 0),
            "consensus_available_count": int(pt.get("consensus_available_count") or 0),
            "consensus_yes_columns": list(pt.get("consensus_yes_columns") or []),
            "consensus_policy_version": (
                pt.get("consensus_policy_version") or SIGNAL_CONSENSUS_POLICY_VERSION
            ),
            "formula_version": CURRENT_SIGNAL_FORMULA_VERSION,
            "raw_si_cells": [],
        }
    )
    return out


def build_market_signal_index(
    signals_matrix: dict[str, Any] | None,
) -> dict[str, dict[str, Any]]:
    """Mappa market_key → payload segnale (acquired = active; SI grezzi in diagnostics)."""
    matrix = _unwrap_matrix(signals_matrix)
    raw_cells = iter_raw_si_signal_cells(matrix)
    acquired_groups = _with_inherited_draw_pt(iter_acquired_signal_groups(matrix))

    raw_by_market: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for cell in raw_cells:
        target = map_cecchino_signal_to_target(cell["signal_group"], cell["source_column"])
        market_key = target.get("target_market_key")
        if not market_key:
            continue
        raw_by_market[str(market_key)].append(
            {
                **cell,
                "target_market_key": str(market_key),
                "target_market_label": target.get("target_market_label"),
            }
        )

    acquired_by_market: dict[str, dict[str, Any]] = {}
    for group in acquired_groups:
        target = _acquired_group_target(group)
        market_key = target.get("target_market_key")
        if not market_key:
            continue
        mk = str(market_key)
        # Un solo gruppo acquisito per mercato (0 o 1)
        if mk in acquired_by_market:
            continue
        acquired_by_market[mk] = group

    market_keys = set(raw_by_market) | set(acquired_by_market)
    out: dict[str, dict[str, Any]] = {}
    for market_key in market_keys:
        sources = raw_by_market.get(market_key, [])
        acquired = acquired_by_market.get(market_key)
        is_acquired = acquired is not None
        families = sorted(
            {
                str(s.get("signal_family") or s.get("signal_group"))
                for s in sources
                if s.get("signal_family") or s.get("signal_group")
            }
        )
        if is_acquired and acquired.get("signal_group"):
            fam = str(acquired["signal_group"])
            if fam not in families:
                families = sorted([*families, fam])
        family = families[0] if len(families) == 1 else ("|".join(families) if families else None)
        if is_acquired and not family:
            family = str(acquired.get("signal_group") or "") or None

        raw_si_count = len(sources)
        acquired_signal_count = 1 if is_acquired else 0
        out[market_key] = {
            "signal_active": is_acquired,
            "signal_sources_json": {
                "sources": sources,
                "signal_family": family,
                "signal_families": families,
                "active_signal_count": raw_si_count,
                "raw_si_count": raw_si_count,
                "acquired_signal_count": acquired_signal_count,
                "acquisition_status": acquired.get("acquisition_status") if acquired else None,
                "consensus_yes_columns": (
                    list(acquired.get("consensus_yes_columns") or []) if acquired else []
                ),
            },
            "signal_family": family,
            "active_signal_count": raw_si_count,
            "raw_si_count": raw_si_count,
            "acquired_signal_count": acquired_signal_count,
            "consensus_yes_count": int(acquired.get("consensus_yes_count") or 0) if acquired else 0,
            "consensus_required_count": (
                int(acquired.get("consensus_required_count") or 0) if acquired else 0
            ),
            "consensus_available_count": (
                int(acquired.get("consensus_available_count") or 0) if acquired else 0
            ),
            "consensus_yes_columns": (
                list(acquired.get("consensus_yes_columns") or []) if acquired else []
            ),
            "acquisition_status": acquired.get("acquisition_status") if acquired else None,
            "signal_formula_version": (
                acquired.get("formula_version") if acquired else None
            ),
            "consensus_policy_version": (
                acquired.get("consensus_policy_version") if acquired else None
            ),
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
            "raw_si_count": 0,
            "acquired_signal_count": 0,
        },
        "signal_family": None,
        "active_signal_count": 0,
        "raw_si_count": 0,
        "acquired_signal_count": 0,
        "consensus_yes_count": 0,
        "consensus_required_count": 0,
        "consensus_available_count": 0,
        "consensus_yes_columns": [],
        "acquisition_status": None,
        "signal_formula_version": None,
        "consensus_policy_version": None,
    }


def signal_payload_for_market(
    index: dict[str, dict[str, Any]],
    market_key: str,
) -> dict[str, Any]:
    payload = index.get(market_key)
    if not payload:
        return empty_signal_payload()
    base = empty_signal_payload()
    base.update(payload)
    base["signal_active"] = bool(payload.get("signal_active"))
    base["raw_si_count"] = int(payload.get("raw_si_count") or 0)
    base["acquired_signal_count"] = int(payload.get("acquired_signal_count") or 0)
    base["active_signal_count"] = int(
        payload.get("active_signal_count")
        if payload.get("active_signal_count") is not None
        else base["raw_si_count"]
    )
    base["consensus_yes_count"] = int(payload.get("consensus_yes_count") or 0)
    base["consensus_required_count"] = int(payload.get("consensus_required_count") or 0)
    base["consensus_available_count"] = int(payload.get("consensus_available_count") or 0)
    base["consensus_yes_columns"] = list(payload.get("consensus_yes_columns") or [])
    sources_json = payload.get("signal_sources_json")
    if not isinstance(sources_json, dict):
        base["signal_sources_json"] = empty_signal_payload()["signal_sources_json"]
    return base
