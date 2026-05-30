# Backtest Engine — Changelog tecnico

Changelog backend dedicato al Backtest Engine multi-mercato. Non sostituisce `frontend/src/data/modelChangelog.ts` (modelli SOT v2.x).

---

## backtest-step-b

**Titolo:** DB foundation Backtest Engine

**Descrizione:** Create le tabelle generiche `backtest_runs`, `backtest_predictions`, `backtest_picks` e `backtest_run_metrics` per supportare backtest multi-mercato e multi-algoritmo.

**Highlights:**

- Aggiunte tabelle `backtest_*` (migration `20260605120000_create_backtest_tables.py`).
- Aggiunti modelli SQLAlchemy (`BacktestRun`, `BacktestPrediction`, `BacktestPick`, `BacktestRunMetric`).
- Aggiunti campi `market_key` e `algorithm_version` su runs, predictions e picks.
- Aggiunti `feature_snapshot_json` e `trace_json` su predictions.
- Aggiunto supporto `partial_completed` / `error_json` su runs.
- Aggiunte costanti in `backend/app/backtest/constants.py`.
- Registry stub market/algorithms già presenti da Step A (nessuna modifica runtime).
- Nessun runtime backtest collegato.
- Nessuna modifica ai modelli SOT v2.0/v2.1.

**File toccati:**

- `backend/alembic/versions/20260605120000_create_backtest_tables.py`
- `backend/app/models/backtest.py`
- `backend/app/models/__init__.py`
- `backend/app/backtest/constants.py`
- `backend/app/core/db_tables.py`
- `backend/tests/test_backtest_models_import.py`
- `docs/BACKTEST_ENGINE_ARCHITECTURE.md`

**Test eseguiti (locale):**

- `python -c "from app.main import app; print('ok')"` — OK
- `pytest tests/test_import_app_main.py tests/test_backtest_models_import.py` — 3 passed

**Test non eseguiti (motivo):**

- `alembic upgrade head` / `downgrade -1` — ambiente locale usa SQLite (`SQLiteImpl`); le migration richiedono PostgreSQL (guard `if bind.dialect.name != "postgresql"`). Eseguire su DB PostgreSQL in deploy/staging.
