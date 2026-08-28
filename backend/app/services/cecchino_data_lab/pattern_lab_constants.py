"""Costanti Pattern Lab — layer analitico READ-ONLY multi-run."""

from __future__ import annotations

PATTERN_LAB_VERSION = "cecchino_lab_pattern_lab_v1"
PATTERN_LAB_EXPORT_KIND = "pattern_lab_discovery"
PATTERN_LAB_SORT_POLICY_BB = "v36_substitutes_v31_evidence_historical"

# Chunk snapshot per load batch (export e query streaming)
SNAPSHOT_CHUNK_SIZE = 150

# CSV incluso solo sotto soglia (righe)
CSV_ROW_THRESHOLD = 200_000

DEFAULT_ELIGIBILITY = "eligible_core"

EXPORT_MODE_FULL = "full_selected_runs"
EXPORT_MODE_FILTERED = "current_filters"
