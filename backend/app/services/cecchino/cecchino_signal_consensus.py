"""Consenso minimo per acquisizione segni Cecchino (policy v1 min-two).

Separa risultato grezzo formula (SI/NO per cella) da acquisizione del segno.
"""

from __future__ import annotations

from typing import Any

from app.services.cecchino.cecchino_signal_target_mapping import (
    SIGNAL_COLUMN_TO_SOURCE,
    map_row_key_to_signal_group,
)

SIGNAL_CONSENSUS_POLICY_VERSION = "cecchino_signal_consensus_v1_min_two"
LEGACY_SIGNAL_FORMULA_VERSION = "cecchino_signals_matrix_v1_legacy"
PREVIOUS_SIGNAL_FORMULA_VERSION = "cecchino_signals_matrix_v2_draw_dfg"
CURRENT_SIGNAL_FORMULA_VERSION = "cecchino_signals_matrix_v3_draw_dfg_decimal2"

# Ordine canonico colonne conferma
CANONICAL_SOURCE_COLUMNS: tuple[str, ...] = (
    "EXCEL_D",
    "EXCEL_E",
    "EXCEL_F",
    "EXCEL_G",
    "SCALA",
)

# Gruppi con almeno due formule → soglia 2
CONSENSUS_REQUIRED_TWO_GROUPS: frozenset[str] = frozenset(
    {
        "UNDER_UNDER_PT",
        "DRAW",
        "OVER_OVER_PT",
        "ONE_X",
        "X_TWO",
        "ONE_TWO",
    },
)

# Gruppi esenti (unica formula diretta)
SINGLE_FORMULA_EXEMPT_GROUPS: frozenset[str] = frozenset({"HOME", "AWAY"})

# Colonne disponibili per gruppo (conferme valide)
GROUP_AVAILABLE_COLUMNS: dict[str, tuple[str, ...]] = {
    "UNDER_UNDER_PT": ("EXCEL_D", "EXCEL_E", "EXCEL_F", "EXCEL_G"),
    "DRAW": ("EXCEL_D", "EXCEL_E", "EXCEL_F", "EXCEL_G"),
    "OVER_OVER_PT": ("EXCEL_D", "EXCEL_E", "EXCEL_F", "EXCEL_G"),
    "ONE_X": ("EXCEL_D", "EXCEL_E", "EXCEL_F", "EXCEL_G", "SCALA"),
    "X_TWO": ("EXCEL_D", "EXCEL_E", "EXCEL_F", "EXCEL_G", "SCALA"),
    "ONE_TWO": ("EXCEL_D", "EXCEL_E"),
    "HOME": ("EXCEL_D",),
    "AWAY": ("EXCEL_D",),
}

ACQ_ACQUIRED_CONSENSUS = "acquired_consensus"
ACQ_REJECTED_INSUFFICIENT = "rejected_insufficient_consensus"
ACQ_SINGLE_FORMULA_EXEMPT = "acquired_single_formula_exempt"
ACQ_LEGACY_UNCLASSIFIED = "legacy_unclassified"
ACQ_NO_RAW_SIGNAL = "no_raw_signal"

REASON_DRAW_PT_PARENT_CONSENSUS_BELOW = "draw_pt_parent_consensus_below_minimum"

FORMULA_SOURCE_PERSISTED_LIVE = "persisted_live_matrix"
FORMULA_SOURCE_RECOMPUTED_PREMATCH = "recomputed_from_prematch_snapshot"
FORMULA_SOURCE_OFFLINE_WEIGHT = "offline_weight_model_recompute"
FORMULA_SOURCE_LEGACY = "legacy_persisted_matrix"


def _payload_key_to_source(column_key: str) -> str | None:
    return SIGNAL_COLUMN_TO_SOURCE.get(column_key)


def _yes_columns_from_signals(
    signals: dict[str, Any],
    *,
    available: tuple[str, ...],
) -> list[str]:
    """Colonne distinte con SI, in ordine canonico, solo tra quelle disponibili al gruppo."""
    seen: set[str] = set()
    for column_key, raw in signals.items():
        if str(raw).upper() != "SI":
            continue
        source = _payload_key_to_source(str(column_key))
        if source is None or source not in available:
            continue
        seen.add(source)
    return [col for col in CANONICAL_SOURCE_COLUMNS if col in seen]


def compute_signal_group_consensus(
    *,
    signal_group: str,
    signals: dict[str, Any] | None,
) -> dict[str, Any]:
    """Calcola consenso per un gruppo della matrice (helper puro)."""
    group = str(signal_group or "").upper()
    signals_dict = signals if isinstance(signals, dict) else {}

    available = GROUP_AVAILABLE_COLUMNS.get(group)
    if available is None:
        # DRAW_PT e gruppi sconosciuti: non valutati autonomamente
        return {
            "consensus_policy_version": SIGNAL_CONSENSUS_POLICY_VERSION,
            "consensus_eligible": False,
            "consensus_available_count": 0,
            "consensus_required_count": 0,
            "consensus_yes_count": 0,
            "consensus_yes_columns": [],
            "consensus_passed": False,
            "acquisition_status": ACQ_NO_RAW_SIGNAL,
            "is_acquired": False,
            "consensus_source_group": group or None,
        }

    yes_columns = _yes_columns_from_signals(signals_dict, available=available)
    yes_count = len(yes_columns)
    available_count = len(available)
    eligible = group in CONSENSUS_REQUIRED_TWO_GROUPS
    exempt = group in SINGLE_FORMULA_EXEMPT_GROUPS

    if eligible:
        required = 2
        passed = yes_count >= required
    elif exempt:
        required = 1
        passed = yes_count >= required
    else:
        required = 1
        passed = yes_count >= required

    if yes_count == 0:
        status = ACQ_NO_RAW_SIGNAL
        is_acquired = False
    elif passed and exempt:
        status = ACQ_SINGLE_FORMULA_EXEMPT
        is_acquired = True
    elif passed and eligible:
        status = ACQ_ACQUIRED_CONSENSUS
        is_acquired = True
    elif passed:
        status = ACQ_ACQUIRED_CONSENSUS
        is_acquired = True
    else:
        status = ACQ_REJECTED_INSUFFICIENT
        is_acquired = False

    return {
        "consensus_policy_version": SIGNAL_CONSENSUS_POLICY_VERSION,
        "consensus_eligible": eligible,
        "consensus_available_count": available_count,
        "consensus_required_count": required,
        "consensus_yes_count": yes_count,
        "consensus_yes_columns": yes_columns,
        "consensus_passed": passed,
        "acquisition_status": status,
        "is_acquired": is_acquired,
        "consensus_source_group": group,
    }


def compute_consensus_for_matrix_row(row: dict[str, Any]) -> dict[str, Any]:
    """Consensus da una riga payload signals_matrix."""
    row_key = str(row.get("key") or "")
    signal_group = map_row_key_to_signal_group(row_key) or ""
    signals = row.get("signals") if isinstance(row.get("signals"), dict) else {}
    return compute_signal_group_consensus(signal_group=signal_group, signals=signals)


def inherit_draw_consensus(draw_consensus: dict[str, Any]) -> dict[str, Any]:
    """DRAW_PT eredita i metadati di consenso dal gruppo DRAW (non aumenta yes_count)."""
    return {
        "consensus_policy_version": draw_consensus.get("consensus_policy_version")
        or SIGNAL_CONSENSUS_POLICY_VERSION,
        "consensus_eligible": bool(draw_consensus.get("consensus_eligible")),
        "consensus_available_count": int(draw_consensus.get("consensus_available_count") or 0),
        "consensus_required_count": int(draw_consensus.get("consensus_required_count") or 0),
        "consensus_yes_count": int(draw_consensus.get("consensus_yes_count") or 0),
        "consensus_yes_columns": list(draw_consensus.get("consensus_yes_columns") or []),
        "consensus_passed": bool(draw_consensus.get("consensus_passed")),
        "acquisition_status": draw_consensus.get("acquisition_status") or ACQ_NO_RAW_SIGNAL,
        "is_acquired": bool(draw_consensus.get("is_acquired")),
        "consensus_source_group": "DRAW",
    }


def attach_consensus_to_matrix_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Aggiunge blocco consensus a ogni riga (mutazione in-place + return)."""
    for row in rows:
        if isinstance(row, dict):
            row["consensus"] = compute_consensus_for_matrix_row(row)
    return rows


def consensus_by_group_from_matrix(signals_matrix: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Mappa signal_group → consensus dalla matrice."""
    out: dict[str, dict[str, Any]] = {}
    rows = signals_matrix.get("rows") or []
    if not isinstance(rows, list):
        return out
    for row in rows:
        if not isinstance(row, dict):
            continue
        row_key = str(row.get("key") or "")
        group = map_row_key_to_signal_group(row_key)
        if not group:
            continue
        consensus = row.get("consensus")
        if not isinstance(consensus, dict):
            consensus = compute_consensus_for_matrix_row(row)
        out[group] = consensus
    return out


def normalize_formula_version(value: str | None) -> str:
    """Payload storici senza formula_version → legacy.

    Alias:
    - current / v3 → CURRENT (V3)
    - v2 → PREVIOUS (V2)
    - legacy / v1 → LEGACY (V1)
    """
    if not value:
        return LEGACY_SIGNAL_FORMULA_VERSION
    text = str(value).strip()
    if text in ("current", "v3"):
        return CURRENT_SIGNAL_FORMULA_VERSION
    if text in ("v2",):
        return PREVIOUS_SIGNAL_FORMULA_VERSION
    if text == PREVIOUS_SIGNAL_FORMULA_VERSION:
        return PREVIOUS_SIGNAL_FORMULA_VERSION
    if text in ("legacy", "v1"):
        return LEGACY_SIGNAL_FORMULA_VERSION
    return text


def is_current_signal_matrix(matrix: dict[str, Any] | None) -> bool:
    """True solo se status=available e formula_version è esattamente CURRENT (V3)."""
    if not isinstance(matrix, dict):
        return False
    if str(matrix.get("status") or "") != "available":
        return False
    fv = matrix.get("formula_version")
    if fv is None or str(fv).strip() == "":
        return False
    return str(fv).strip() == CURRENT_SIGNAL_FORMULA_VERSION
