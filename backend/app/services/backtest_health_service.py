"""Health check read-only Backtest Engine (Step C.1)."""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.orm import Session

from app.algorithms.registry import ALGORITHM_REGISTRY
from app.core.db_tables import get_existing_table_names
from app.markets.registry import MARKET_REGISTRY
from app.models import BacktestPick, BacktestPrediction, BacktestRun, BacktestRunMetric

BACKTEST_TABLE_NAMES = (
    "backtest_runs",
    "backtest_predictions",
    "backtest_picks",
    "backtest_run_metrics",
)


class BacktestHealthService:
    def get_health(self, db: Session) -> dict[str, Any]:
        existing: set[str] = set()
        try:
            existing = get_existing_table_names(db.get_bind())
        except Exception:  # noqa: BLE001
            existing = set()

        tables = {name: name in existing for name in BACKTEST_TABLE_NAMES}
        all_tables_ok = all(tables.values())

        markets = [
            {"market_key": spec.market_key, "status": spec.status}
            for spec in MARKET_REGISTRY.values()
        ]
        algorithms = [
            {
                "market_key": spec.market_key,
                "algorithm_version": spec.algorithm_version,
                "status": spec.status,
            }
            for spec in ALGORITHM_REGISTRY.values()
        ]
        active_markets = [m["market_key"] for m in markets if m["status"] == "active"]
        planned_markets = [m["market_key"] for m in markets if m["status"] == "planned"]
        active_algorithms = [
            a["algorithm_version"]
            for a in algorithms
            if a["status"] == "production" and a["market_key"] in active_markets
        ]

        runs_count = 0
        predictions_count = 0
        picks_count = 0
        metrics_count = 0
        if all_tables_ok:
            try:
                runs_count = int(db.scalar(select(func.count()).select_from(BacktestRun)) or 0)
                predictions_count = int(
                    db.scalar(select(func.count()).select_from(BacktestPrediction)) or 0,
                )
                picks_count = int(db.scalar(select(func.count()).select_from(BacktestPick)) or 0)
                metrics_count = int(
                    db.scalar(select(func.count()).select_from(BacktestRunMetric)) or 0,
                )
            except (OperationalError, ProgrammingError):
                all_tables_ok = False

        status = "ok" if all_tables_ok else "degraded"
        return {
            "status": status,
            "tables": tables,
            "runs_count": runs_count,
            "predictions_count": predictions_count,
            "picks_count": picks_count,
            "metrics_count": metrics_count,
            "markets": markets,
            "algorithms": algorithms,
            "active_markets": active_markets,
            "planned_markets": planned_markets,
            "active_algorithms": active_algorithms,
        }
