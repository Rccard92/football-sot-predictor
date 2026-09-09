"""Riconciliazione BLOCCO 2 stats da raw_json — solo dry-run/audit.

Non modifica BLOCCO 1 (quote, KPI, segnali, buyability, pattern).
"""

from app.services.cecchino_data_lab.stats_raw_reconciliation.constants import (
    COVERAGE_GROUPS,
    RAW_TO_DB_FIELD_MAP,
    STATS_MODEL_FIELDS,
)
from app.services.cecchino_data_lab.stats_raw_reconciliation.dry_run import (
    run_stats_raw_reconciliation_dry_run,
)

__all__ = [
    "COVERAGE_GROUPS",
    "RAW_TO_DB_FIELD_MAP",
    "STATS_MODEL_FIELDS",
    "run_stats_raw_reconciliation_dry_run",
]
