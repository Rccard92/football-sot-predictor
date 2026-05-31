# Backtest Engine — Changelog tecnico

Changelog backend dedicato al Backtest Engine multi-mercato. Non sostituisce `frontend/src/data/modelChangelog.ts` (modelli SOT v2.x).

---

## backtest-step-g2b

**Titolo:** Rolling Player Layer Historical Official XI

**Descrizione:** Implementato il rolling player layer point-in-time in modalità `historical_official_xi`: XI ufficiale storico + prior stats strict PIT alimentano la macro `player_layer` (peso 9) in preview e mini-run. `pre_lineup` invariato.

**Highlights:**

- Estrazione helper condivisi in `pit_player_rolling_stats.py` (G2A + G2B).
- `RollingPlayerLayerService` con formule offensive XI, top shooter presence, replacement depth.
- Branch mode esplicito nel macro builder PIT.
- Preview/mini-run accettano `historical_official_xi`.
- Aggregato mini-run `player_layer_summary`.
- UI: select mode preview + mini-run, card player layer.
- Regression `pre_lineup`: macro player_layer neutra.

**File toccati:**

- `backend/app/services/backtest/pit_player_rolling_stats.py` (nuovo)
- `backend/app/services/backtest/rolling_player_layer_service.py` (nuovo)
- `backend/app/services/backtest/historical_lineup_audit_service.py`
- `backend/app/services/backtest/point_in_time_context_service.py`
- `backend/app/services/backtest/sot_v21_pit_macro_builder.py`
- `backend/app/services/backtest/sot_v21_preview_service.py`
- `backend/app/services/backtest/sot_v21_mini_run_preview_service.py`
- `backend/app/schemas/backtest_point_in_time.py`
- `backend/app/schemas/backtest_sot_v21_mini_run.py`
- `backend/tests/test_rolling_player_layer.py` (nuovo)
- `backend/tests/test_historical_lineup_audit.py`
- `backend/tests/test_backtest_sot_v21_preview.py`
- `backend/tests/test_backtest_sot_v21_mini_run.py`
- `frontend/src/lib/api.ts`
- `frontend/src/components/admin/BacktestDebugPanel.tsx`
- `docs/BACKTEST_ENGINE_ARCHITECTURE.md`

---

## backtest-step-g2a

**Titolo:** Historical Official XI Audit

**Descrizione:** Aggiunto audit read-only per verificare copertura delle formazioni ufficiali storiche, mapping giocatori e statistiche player point-in-time prima di implementare il rolling player layer.

**Highlights:**

- Endpoint audit fixture.
- Endpoint audit round.
- Verifica copertura XI ufficiale.
- Verifica mapping giocatori.
- Calcolo diagnostico player prior stats.
- Distinzione pre_lineup vs historical_official_xi.
- Nessun salvataggio DB.
- Nessuna modifica a v2.0/v2.1 runtime.

**File toccati:**

- `backend/app/services/backtest/historical_lineup_audit_service.py`
- `backend/app/schemas/backtest_historical_lineup_audit.py`
- `backend/app/services/backtest/backtest_fixture_debug_service.py`
- `backend/app/routes/backtest_debug.py`
- `backend/app/backtest/constants.py`
- `backend/tests/test_historical_lineup_audit.py`
- `frontend/src/lib/api.ts`
- `frontend/src/components/admin/BacktestDebugPanel.tsx`
- `docs/BACKTEST_ENGINE_ARCHITECTURE.md`

---

## backtest-step-g1

**Titolo:** Split casa/trasferta point-in-time

**Descrizione:** Aggiunta ricostruzione point-in-time dello split casa/trasferta nella preview e mini-run SOT v2.1 PIT, usando solo fixture precedenti al kickoff.

**Highlights:**

- Calcolo home/away split nel PointInTimeContext.
- Macro split non più neutra quando disponibile.
- Status available / partial_low_sample / fallback.
- Trace macro split con components.
- Split summary nella mini-run.
- Nessun salvataggio DB.
- Nessuna modifica a v2.0/v2.1 live runtime.

**File toccati:**

- `backend/app/services/backtest/pit_split_stats_builder.py`
- `backend/app/schemas/backtest_point_in_time.py`
- `backend/app/services/backtest/point_in_time_context_service.py`
- `backend/app/services/backtest/sot_v21_pit_macro_builder.py`
- `backend/app/services/backtest/sot_v21_preview_service.py`
- `backend/app/schemas/backtest_sot_v21_preview.py`
- `backend/app/schemas/backtest_sot_v21_mini_run.py`
- `backend/app/services/backtest/sot_v21_mini_run_preview_service.py`
- `backend/tests/test_pit_home_away_split.py`
- `frontend/src/lib/api.ts`
- `frontend/src/components/admin/BacktestDebugPanel.tsx`
- `docs/BACKTEST_ENGINE_ARCHITECTURE.md`

---

## backtest-step-f-fix-round-filter

**Titolo:** Filtro giornata esatta e label mini-run

**Descrizione:** Corretto il filtro round della mini-run PIT per usare il numero esatto della giornata ed evitare che "3" selezioni anche "13". Migliorate le label UI delle metriche SOT totale partita.

**Highlights:**

- Aggiunto `round_number` esatto.
- La giornata 3 non include più la 13.
- Label metriche rese più chiare (SOT totale partita = casa + trasferta).
- Mini-run resta read-only.
- Nessuna modifica a v2.0/v2.1 runtime.

**File toccati:**

- `backend/app/services/backtest/round_filter.py`
- `backend/app/schemas/backtest_sot_v21_mini_run.py`
- `backend/app/services/backtest/backtest_fixture_debug_service.py`
- `backend/app/services/backtest/sot_v21_mini_run_preview_service.py`
- `backend/app/routes/backtest_debug.py`
- `backend/tests/test_round_filter.py`
- `frontend/src/lib/api.ts`
- `frontend/src/components/admin/BacktestDebugPanel.tsx`
- `docs/BACKTEST_ENGINE_ARCHITECTURE.md`

---

## backtest-step-f

**Titolo:** Mini-run preview SOT v2.1 point-in-time

**Descrizione:** Aggiunta mini-run read-only per applicare la preview SOT v2.1 PIT a più fixture e calcolare metriche aggregate senza persistere prediction, picks o metriche.

**Highlights:**

- Endpoint debug `POST /api/backtest/debug/sot-v21-mini-run`.
- MAE, RMSE e bias aggregati.
- Breakdown per sample storico (early/medium/stable).
- Breakdown per totale SOT reale (low/medium/high).
- Worst/best cases.
- UI Debug Backtest aggiornata.
- Nessun salvataggio DB.
- Nessuna modifica a v2.0/v2.1 runtime.

**File toccati:**

- `backend/app/schemas/backtest_sot_v21_mini_run.py`
- `backend/app/services/backtest/sot_v21_mini_run_preview_service.py`
- `backend/app/services/backtest/backtest_fixture_debug_service.py`
- `backend/app/schemas/backtest_sot_v21_preview.py` (prior counts additivi)
- `backend/app/services/backtest/sot_v21_preview_service.py` (prior counts additivi)
- `backend/app/routes/backtest_debug.py`
- `backend/tests/test_backtest_sot_v21_mini_run.py`
- `frontend/src/lib/api.ts`
- `frontend/src/components/admin/BacktestDebugPanel.tsx`
- `docs/BACKTEST_ENGINE_ARCHITECTURE.md`

---

## backtest-step-e

**Titolo:** Preview SOT v2.1 point-in-time

**Descrizione:** Aggiunta preview read-only per calcolare una previsione SOT v2.1 point-in-time su singola fixture storica, usando solo dati precedenti al kickoff.

**Highlights:**

- Endpoint `GET /api/backtest/debug/sot-v21-preview`.
- Calcolo base anchor SOT point-in-time (0.55/0.45).
- Moltiplicatore macro v2.1 preview da PointInTimeContext.
- Actuals separati dagli input; errori home/away/totale.
- Pulsante Admin "Preview prediction v2.1 PIT".
- Nessuna prediction persistita; v2.0/v2.1 runtime invariati.

**File toccati:**

- `backend/app/schemas/backtest_sot_v21_preview.py`
- `backend/app/services/backtest/sot_v21_pit_macro_builder.py`
- `backend/app/services/backtest/sot_v21_preview_service.py`
- `backend/app/routes/backtest_debug.py`
- `backend/tests/test_backtest_sot_v21_preview.py`
- `frontend/src/lib/api.ts`
- `frontend/src/components/admin/BacktestDebugPanel.tsx`
- `docs/BACKTEST_ENGINE_ARCHITECTURE.md`

---

## backtest-step-d-ui-fixture-selector

**Titolo:** Fixture selector PIT — paginazione e ID manuale

**Descrizione:** Miglioramento UI-only del pannello Debug Backtest per esplorare fixture storiche su tutta la stagione (early/mid/late) senza modificare il motore PointInTimeContext.

**Highlights:**

- Paginazione offset/limit con prev/next e "Mostrate X–Y di Z".
- Filtro `round_contains` su GET `/api/backtest/debug/fixtures`.
- Input fixture_id manuale per Preview context.
- Reset PIT al cambio campionato.
- Nessuna prediction, nessun backtest runtime, v2.0/v2.1 invariati.

**File toccati:**

- `frontend/src/components/admin/BacktestDebugPanel.tsx`
- `frontend/src/lib/api.ts`
- `backend/app/services/backtest/backtest_fixture_debug_service.py`
- `backend/app/routes/backtest_debug.py`
- `backend/tests/test_backtest_point_in_time_context.py`
- `docs/BACKTEST_ENGINE_ARCHITECTURE.md`

---

## backtest-step-d

**Titolo:** PointInTimeContext SOT preview

**Descrizione:** Aggiunto il primo builder read-only del contesto point-in-time per il mercato SOT, con endpoint e pannello debug per verificare dati disponibili prima del kickoff.

**Highlights:**

- Context SOT filtrato per `cutoff_time` (`fixture_key_before`, `FINISHED_STATUSES`).
- Calcolo medie SOT/xG solo su fixture precedenti (home/away + lega).
- League baselines point-in-time (riuso `compute_v21_xg_league_baselines`).
- Actuals separati dagli input (`actuals_used_as_input=false`).
- Preview da Admin Debug Backtest (lista fixture + Preview context).
- Nessuna prediction generata, nessuna modifica v2.0/v2.1.

**File toccati:**

- `backend/app/services/backtest/point_in_time_context_service.py`
- `backend/app/services/backtest/backtest_fixture_debug_service.py`
- `backend/app/schemas/backtest_point_in_time.py`
- `backend/app/routes/backtest_debug.py`
- `backend/tests/test_backtest_point_in_time_context.py`
- `frontend/src/lib/api.ts`
- `frontend/src/components/admin/BacktestDebugPanel.tsx`
- `docs/BACKTEST_ENGINE_ARCHITECTURE.md`

---

## backtest-step-c1

**Titolo:** Debug Backtest Panel (Admin)

**Descrizione:** Pannello Admin con 6 pulsanti di test UI, endpoint health read-only e client API frontend per `/api/backtest/runs`. Nessun backtest runtime.

**Highlights:**

- `GET /api/backtest/debug/health` — registry markets/algorithms, stato tabelle, conteggi.
- `BacktestDebugPanel` in Admin: health, crea run pending v2.1, lista, dettaglio, test 422 planned market / algoritmo errato.
- Client `fetchBacktestApiRaw` per gestire 422 attesi senza throw.
- Nessuna modifica v2.0/v2.1, Monitoraggio, Audit, Prossima giornata.

**File toccati:**

- `backend/app/services/backtest_health_service.py`
- `backend/app/routes/backtest_debug.py`
- `backend/app/routes/__init__.py`
- `backend/tests/test_backtest_debug_health.py`
- `frontend/src/lib/api.ts`
- `frontend/src/components/admin/BacktestDebugPanel.tsx`
- `frontend/src/pages/Admin.tsx`
- `docs/BACKTEST_ENGINE_ARCHITECTURE.md`

---

## backtest-step-c

**Titolo:** API base Backtest Runs

**Descrizione:** Aggiunti endpoint generici per creare, listare e leggere run di backtest multi-mercato, senza avviare ancora il motore di calcolo.

**Highlights:**

- `POST /api/backtest/runs` — crea run in stato `pending`.
- `GET /api/backtest/runs` — lista con filtri e paginazione.
- `GET /api/backtest/runs/{id}` — dettaglio con conteggi predictions/picks/metrics.
- Validazione `market_key` e `algorithm_version` via registry (solo market `active`).
- Calcolo `algorithm_config_hash` deterministico.
- Nessuna prediction/pick/metrica generata.
- Nessuna modifica a v2.0/v2.1.

**File toccati:**

- `backend/app/routes/backtest_runs.py`
- `backend/app/services/backtest_run_service.py`
- `backend/app/schemas/backtest_runs.py`
- `backend/app/backtest/errors.py`
- `backend/app/backtest/git_info.py`
- `backend/app/routes/__init__.py`
- `backend/tests/test_backtest_runs_api.py`
- `docs/BACKTEST_ENGINE_ARCHITECTURE.md`

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
