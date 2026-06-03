# Backtest Engine — Changelog tecnico

Changelog backend dedicato al Backtest Engine multi-mercato. Non sostituisce `frontend/src/data/modelChangelog.ts` (modelli SOT v2.x).

---

---

---

---

---

---

---

---

---

---

---

---

## v31-simulator-light-report-hybrid

**Titolo:** Report JSON leggero, strategy_status e strategia ibrida high guard

**Descrizione:** `strategy_status` active/diagnostic/archived; export default `report?detail=summary`; nuova `v31_bias_dynamic_high_guard`; `dynamic_score` per raccomandazione; UI filtri e tab errori con boost/signal.

**File toccati:** `v31_calibration_simulator_*`, `backtest_v31.py`, frontend simulatore, test, docs.

---

## v31-predictive-dynamics

**Titolo:** Simulatore v3.1 — varianza, bucket e strategie aggressive

**Descrizione:** Fix `avg_total_shots_for` (builder standard + resolver); `prediction_distribution` e warning compressione; metriche bucket; 6 strategie aggressive (`variance_unlocked`, `big_match_boost`, …); interazioni PIT; ranking con high recall e compression score; UI tab Varianza/Bucket.

**File toccati:** `v31_calibration_*`, `v31_calibration_row_builder_standard.py`, frontend simulatore, test, docs.

---

## v31-predictive-simulator

**Titolo:** Simulatore predittivo v3.1 (refactor numerico)

**Descrizione:** Rimossa logica betting (GIOCA/NO_BET, linee, hit rate) dalla fase calibrazione. Otto strategie numeriche predicono home/away/total su tutte le fixture. Metriche: MAE/RMSE/bias, within bands, coverage WIN, error distribution, `balanced_prediction_score`. UI: 7 tab predittivi + export JSON. Endpoint `GET /calibration-simulator/report-json`.

**File toccati:** `v31_calibration_simulator_*`, `backtest_v31.py`, frontend simulatore, test, `sot-model-v31.md`.

---

## v31-calibration-simulator-scale-fix

**Titolo:** Correzione scala predizione simulatore v3.1

**Descrizione:** Base SOT assoluta (`v31_calibration_simulator_base_sot.py`) con conversione macro→SOT; context multiplier cappato; probabilità Over normale (σ=2.2); selector e confidence rivisti; `prediction_diagnostics` e UI tab Diagnostica scala; `best_by` esclude strategie a 0 pick.

**File toccati:** moduli `v31_calibration_simulator_*`, frontend simulatore, test, `sot-model-v31.md`.

---

## v31-calibration-simulator

**Titolo:** Simulatore calibrazione v3.1 con 5 strategie sperimentali

**Descrizione:** Nuovo `GET /api/backtest/v31/calibration-simulator` che carica righe dataset standard, predice SOT solo da feature pre-match (no predizioni legacy in input), calcola metriche regressione/betting, walk-forward (5–15→16–26, 5–26→27–37), spiegazioni IT. UI Backtest con tab Strategie/Walk-forward/Linee/No bet/Reason codes/Audit. Docs `docs/sot-model-v31.md`.

**File toccati:** `v31_calibration_simulator_*.py`, `backtest_v31.py`, frontend sezione simulatore, test, docs.

---

## v31-full-export-chunks

**Titolo:** Export JSON completo v3.1 in 3 chunk per intervallo giornate

**Descrizione:** L’export full è partizionato in tre job indipendenti (giornate 5–15, 16–26, 27–37) con `round_from`/`round_to`, metadata `chunk` nel payload, log `V31_FULL_EXPORT_CHUNK_*`, filename `v31-calibration-dataset-full-part-{n}-rounds-{from}-{to}.json`. UI: tre card con Genera/Scarica/Annulla/Rigenera; nessun timeout 120s; warning stallo se `rows_done` fermo 90s. Filtro giornate anche su `GET ?detail=full&round_from=&round_to=`.

**File toccati:** `v31_calibration_dataset_builder.py`, `v31_calibration_full_export_job.py`, `backtest_v31.py`, `v31_calibration_dataset_service.py`, frontend sezione v3.1 + `api.ts`, test job API, docs.

---

## v31-full-export-async-job

**Titolo:** Export JSON completo v3.1 via job asincrono

**Descrizione:** Il JSON full (rebuild PIT × N fixture) non usa più una richiesta HTTP lunga dalla UI. Job in-memory con POST/GET poll/cancel/download, log diagnostici per fixture (`V31_FULL_EXPORT_*`, `V31_DATASET_EXPORT_PROGRESS detail=full rows_done=`), progress bar determinata in UI, warning 60s e timeout 120s con cancel automatico (sostituito in UI da chunk + stall 90s).

**File toccati:** `v31_calibration_full_export_job.py`, `v31_calibration_dataset_builder.py`, `backtest_v31.py`, frontend sezione v3.1, test job API.

---

## v31-anti-leakage-export-fix

**Titolo:** Anti-leakage corretto e export standard veloce v3.1

**Descrizione:** Anti-leakage scansiona solo `row.features` (chiavi esplicite; `actuals_used_as_input` consentito). Summary non legge più `explanation_json` intero (fix falsi 960 failure). Export `detail=standard` senza rebuild PIT; `detail=full` con PIT e progress log. Download bloccato (422) se leakage; endpoint report anti-leakage; CSV solo standard.

**File toccati:** `v31_calibration_anti_leakage.py`, `v31_calibration_row_builder_standard.py`, builder/service/routes, frontend sezione v3.1, test.

---

## v31-calibration-dataset-summary-ui

**Titolo:** Summary leggera e download on-demand dataset v3.1

**Descrizione:** Endpoint `GET /calibration-dataset/summary` (conteggi rapidi da analisi persistite, proxy macro v2.1, anti-leakage su `explanation_json`). UI Backtest: mount carica solo summary; export JSON/CSV solo al click con timer, barra indeterminata, `AbortController` e log export `duration_ms`.

**File toccati:** `v31_calibration_dataset_summary.py`, `v31_calibration_dataset_service.py`, `backtest_v31.py`, `RoundAnalysisV31CalibrationDatasetSection.tsx`, `api.ts`, test API, docs.

---

## v31-calibration-dataset

**Titolo:** Dataset calibrazione v3.1 SOT Calibrated Predictor

**Descrizione:** Step V3.1-A: export JSON/CSV del dataset di calibrazione con feature pre-match ricostruite via PIT storico (`historical_official_xi`), target separato (`actual_*`, `final_score`), sezione `comparisons` isolata dai modelli legacy (non usata come feature), controllo anti-leakage sul payload. Predittore v3.1 registrato come experimental scaffold (`SotV31CalibratedPredictorService`, `SotV31BetSelectorService`) senza integrazione nel loop `analyze`. v3.0 e motori v1/v2 invariati.

**File toccati:** `constants.py`, `backtest_round_analysis.py`, `round_analysis_model_registry.py`, `sot_v31_*`, `v31_calibration_*`, `backtest_v31.py`, frontend `RoundAnalysisV31CalibrationDatasetSection`, `api.ts`, `Backtest.tsx`, test `test_v31_calibration_dataset_api.py`, docs.

---

## backtest-season-batch-partial-model-update

**Titolo:** Analisi stagione con aggiornamento parziale modelli

**Descrizione:** Aggiunta analisi massiva stagione con checkbox modelli, progress bar e log batch sul frontend. L’endpoint `POST /api/backtest/round-analysis/analyze` supporta `selected_models`, `merge_mode=upsert_selected_models` e `only_missing_models` per aggiornare solo i modelli mancanti (es. aggiungere v3.0 senza ricalcolare v1.1/v2.0/v2.1), preservando i risultati esistenti e incrementando la versione interna. La lista giornate mostra una sola card per giornata (ultima versione), con storico consultabile via endpoint `GET /versions`. I report aggregati continuano a usare solo la latest version per round.

**File toccati:** `round_analysis_service.py`, `round_analysis_merge.py`, `round_analysis_visible_selection.py`, `round_analysis_summary_resolver.py`, routes Round Analysis, frontend Backtest (season batch + versioni), docs.

---

## backtest-v30-value-selector-refinement

**Titolo:** Value selector v3.0-C — refinement simulatore calibrazione

**Descrizione:** Estensione simulatore con 5 strategie value selector (`v3_safe_6_5_*`, consensus balanced, premium 7.5, hybrid con tier/reason_codes), indicatore diagnostico `low_total_risk_v2`, loss diagnostics arricchite per ogni LOSS, `strategy_verdict` e ranking aggiornato. UI simulatore a tab. Nessun modello ufficiale v3.0, nessuna modifica motori v1.1/v2.0/v2.1.

**File toccati:** `round_analysis_low_total_risk_v2.py`, `round_analysis_value_selector_helpers.py`, `round_analysis_value_selector_strategies.py`, `round_analysis_calibration_simulator*.py`, frontend Backtest simulator, test, docs.

---

## backtest-v30-calibration-simulator

**Titolo:** Simulatore calibrazione v3.0 per strategie pick Backtest

**Descrizione:** Simulazione read-only di 8 strategie di selezione pick (filtri GIOCA, linea, macro overheat, consenso v1.1+v2.1, selector conservativo candidato) su analisi persistite. Fix `split_avg` da macro `home_away_split`; `split_status` e disclaimer `low_total_risk` experimental. Endpoint `/calibration-simulator` + export JSON; UI ranking strategie con walk-forward light.

**File toccati:** `round_analysis_v21_trace_helpers.py`, `round_analysis_calibration_simulator_*.py`, diagnostics/export, routes, frontend Backtest, test, docs.

---

## backtest-v30-diagnostics

**Titolo:** Diagnostica avanzata per calibrazione modello v3.0

**Descrizione:** Aggiunta diagnostica aggregata per identificare pattern di errore dei modelli e preparare il futuro modello v3.0 senza modificare le formule esistenti. Endpoint `GET /diagnostics` e `/diagnostics/report-json`; CSV overview esteso (fixture×modello, macro v2.1, bucket); fix download CSV frontend (`VITE_API_BASE_URL`). Breakdown fasce SOT, linee, edge, advice GIOCA/NON GIOCARE, macro v2.1, low total risk score, partite critiche. UI tab «Diagnostica modelli» in Backtest.

**File toccati:** `round_analysis_diagnostics_*.py`, `round_analysis_calibration_export.py`, routes, frontend Backtest/diagnostics, test, docs.

---

## backtest-calibration-export-v3

**Titolo:** Summary robusto accordion + export calibrazione v3.0

**Descrizione:** Ricostruzione chip/summary da fixture quando JSON persistito è stale (giornate 9/10 pre-fix). Badge «Da ricalcolare», pulsante Ricalcola (`POST /recalculate`). Export JSON calibrazione (`round_analysis_calibration_v3`) con fixture granulari, macro v2.1, CSV piatto. Normalizzazione advice legacy `play` → GIOCA.

**File toccati:** `round_analysis_summary_resolver.py`, `round_analysis_calibration_export.py`, service/list/overview routes, frontend accordion/overview, test, docs.

---

## backtest-dashboard-model-scorecards

**Titolo:** Dashboard affidabilità modelli Backtest (overview aggregato)

**Descrizione:** Corretti conteggi player layer v2.1 da JSON persistiti (`player_layer_fixture_status`, `data_quality_summary` e report giornata). Nuovi endpoint `GET /api/backtest/round-analysis/overview` e `overview/report-json` (ultima versione per giornata, solo analisi completate). Metriche advised (solo GIOCA) vs calculated, `reliability_score`, trend ultime 5 giornate. UI: scorecard affidabilità, ranking provvisorio, chip C/A in accordion, filtri tabella, partite da rivedere.

**File toccati:** `player_layer_fixture_status.py`, `round_analysis_overview_*.py`, `round_analysis_mode_stats.py`, aggregator/report, routes, frontend Backtest, test, docs.

---

## backtest-step-i-json-report

**Titolo:** Report JSON per analisi giornata Backtest

**Descrizione:** Aggiunto export JSON completo per analisi giornata e singola fixture (`report-json`), utile per controllare input, output, fallback e qualità di ogni modello. Arricchito persist audit v2.1 (`explanation_json`) e trace v2.0 (`lineup_impact_factors`). Log `prior_fixtures season_id fallback` declassato a INFO. UI: download JSON e tab debug modello.

**File toccati:** `round_analysis_report_builder.py`, `round_analysis_report_service.py`, `backtest_round_analysis.py`, adapter v21/v20 (audit), `v10_prior_context.py`, frontend Backtest, test, docs.

---

## backtest-step-i-v11-split-fallback

**Titolo:** Fallback controllato v1.1 su campione split insufficiente

**Descrizione:** Corretto `V11RoundAnalysisPreviewService` / `compute_v11_side` (flag `allow_split_fallback` solo Round Analysis): quando lo split casa/trasferta è insufficiente ma lo storico generale e gli altri 5 componenti strict sono disponibili, la v1.1 calcola con blend rinormalizzato (senza termine split), `formula_quality=partial_low_sample`, warning `V11_SPLIT_SAMPLE_INSUFFICIENT_USED_GENERAL_BASE`, invece di `no_prediction`. v2.0 riparte quando la base v1.1 ha `predicted_total_sot`. Nessun fallback su v2.1.

**File toccati:** `offensive_production_strict.py`, `v11_round_analysis_engine.py`, `v11_round_analysis_preview.py`, `round_analysis_v11_context.py`, adapter v11, debug API, UI, test, docs.

---

## backtest-step-i-fix-v11-real-engine

**Titolo:** Collegamento motore v1.1 reale alla Round Analysis

**Descrizione:** Round Analysis v1.1 usa ora `v11_round_analysis_engine` (stesso percorso di `SotPredictionV11BaselineSotService`: `build_prior_context` produzione + `compute_v11_side`), rimuovendo i flag PIT che causavano fallimenti su entrambi i lati nonostante prior e baseline lega presenti. Trace esteso (`formula_inputs`/`formula_outputs`, `infer_v11_failure_code`, log con `failed_components`), adapter con codici errore granulari, debug API con aggressive/cautious, UI «Debug modello» in dettaglio partita.

**File toccati:** `v11_round_analysis_engine.py`, `v11_round_analysis_preview.py`, `round_analysis_v11_context.py`, adapter v11, `backtest_debug.py`, `RoundAnalysisFixtureRowDetail.tsx`, test, docs.

---

## backtest-step-i-fix-v11-v20-adapters

**Titolo:** Correzione adapter v1.1/v2.0 nella Round Analysis

**Descrizione:** Corretto il flusso di calcolo v1.1/v2.0 nella pagina Backtest: contesto prior allineato al PIT (`competition_scoped_only`, `strict_kickoff_only`), risoluzione `season_id` tracciata, trace diagnostico per fixture, estrazione output e codici errore granulari (`V11_LEAGUE_BASELINE_EMPTY`, `V11_MISSING_TOTAL_SOT`, `V20_REQUIRES_HOME_AWAY_BASE`). Endpoint debug `GET /api/backtest/debug/round-analysis/fixture/{id}/model/{version}`.

**File toccati:** `round_analysis_v11_context.py`, `v11_round_analysis_preview.py`, adapter v11/v20, `backtest_debug.py`, frontend `roundAnalysisUtils.ts`, test, docs.

---

## backtest-step-i-model-isolation

**Titolo:** Isolamento modelli nel confronto Backtest

**Descrizione:** Blindato il confronto v1.1/v2.0/v2.1: ogni modello usa il proprio adapter (`SotV11RoundAnalysisAdapter`, `SotV20RoundAnalysisAdapter`, `SotV21RoundAnalysisAdapter`) e salva `model_version_requested` / `model_version_used` / `model_engine_name`, evitando mix o fallback silenziosi. ND ed errori con `error_code` specifico (es. `V11_PREDICTION_INCOMPLETE` vs storico insufficiente generico). Preflight giornata solo informativo.

**Highlights:**

- `round_analysis_model_registry.py` + adapter dedicati; runner via registry.
- Guard `MODEL_VERSION_MISMATCH` se `model_version_used != requested`.
- Aggregator: display `OK` | `ND` | `ERROR` | `WARNINGS`, `prevalent_error_code`, conteggi fixture ok/nd/error.
- UI: celle ND con codice errore; dettaglio partita con requested/used/engine; summary modelli arricchito.
- Log `ROUND_ANALYSIS_MODEL_RUN` per fixture/modello.

**File toccati:** registry, adapters, runner, preflight, aggregator, schemas, frontend backtest, test, docs.

---

## backtest-step-i-round-analysis-delete-sort

**Titolo:** Eliminazione analisi giornata e ordinamento lista Backtest

**Descrizione:** Endpoint `DELETE` per rimuovere un’analisi salvata (solo tabelle backtest; CASCADE su `backtest_round_fixture_results`). Lista giornate ordinata per default con `round_number`, `analysis_version` e `created_at` in ordine decrescente; parametri opzionali `sort_by` / `sort_dir`. UI con pulsante Elimina, modal di conferma e messaggio di successo.

**Highlights:**

- `RoundAnalysisService.delete_analysis`: conteggio fixture results, hard delete analisi, commit.
- GET lista: query `sort_by` (`round_number` | `created_at`), `sort_dir` (`asc` | `desc`); tie-breaker `analysis_version` e `created_at`.
- Frontend: `deleteRoundAnalysis`, `RoundAnalysisDeleteConfirm`, accordion con Elimina; `Backtest` azzera dettaglio se analisi eliminata.
- Test: `test_round_analysis_delete_api.py`, `test_round_analysis_list_sort.py`.

**File toccati:** `round_analysis_service.py`, `backtest_round_analysis.py` (routes + schemas), `api.ts`, `RoundAnalysisAccordion.tsx`, `RoundAnalysisDeleteConfirm.tsx`, `Backtest.tsx`, test, docs.

---

## backtest-step-i-round-analysis-ux-fixes

**Titolo:** Migliorie UX Backtest e gestione storico insufficiente

**Descrizione:** La pagina Backtest gestisce giornate con prior matches = 0 (es. giornata 1) senza `failed` tecnico e tabella vuota: status `completed_with_warnings`, celle modello `ND` / «Storico insuff.», preflight storico e banner stagione 2025/2026 senza selettore modello singolo.

**Highlights:**

- `round_analysis_preflight.py`: preflight storico, `build_no_prediction_block`, `first_recommended_round`.
- Runner: isolamento errori per modello; v2.1 non lancia più su `total_predicted_sot` null.
- Status: `completed` | `completed_with_warnings` | `failed` (failed solo errori tecnici / zero fixture).
- UI: ContextBanner senza modello selezionato; accordion e tabella con ND; box «Dettaglio analisi».
- API detail/list: `season_label`, `status_reason`, `accordion_summary`, `failed_models_count`.

**File toccati:** `round_analysis_preflight.py`, `round_analysis_model_runner.py`, `round_analysis_service.py`, `round_analysis_aggregator.py`, `backtest_round_analysis.py` (schemas), componenti `frontend/src/components/backtest/*`, `Backtest.tsx`, `ContextBanner.tsx`, `api.ts`, test, docs.

---

## backtest-step-i-round-analysis

**Titolo:** Step I — Analisi giornata persistente (Backtest operativo)

**Descrizione:** Pagina `/backtest` operativa con analisi one-click per giornata: preparazione automatica mapping/indisponibili, confronto v1.1 / v2.0 / v2.1 su fixture finite, persistenza su `backtest_round_analyses` e `backtest_round_fixture_results`.

**Highlights:**

- Migration `20260606120000_backtest_round_analyses.py` + modelli SQLAlchemy dedicati.
- API: `POST /api/backtest/round-analysis/analyze`, `GET` lista e dettaglio.
- Runner in-memory v1.1 (`build_prior_context` + `compute_v11_side`) e v2.0 (v1.1 × lineup impact); v2.1 riusa PIT preview + pick eval.
- `RoundAnalysisDataPrepService`: preflight, backfill mapping/unavailable per giornata (solo high confidence mapping).
- Rianalisi: `force_recalculate` → nuova `analysis_version`; altrimenti **409** se già `completed`.
- Frontend: form, accordion giornate, tabella partite, dettaglio espandibile (copy italiano non tecnico).

**File toccati:**

- `backend/alembic/versions/20260606120000_backtest_round_analyses.py`
- `backend/app/models/backtest_round_analysis.py`
- `backend/app/schemas/backtest_round_analysis.py`
- `backend/app/routes/backtest_round_analysis.py`
- `backend/app/services/backtest/round_analysis_*.py`
- `backend/app/services/backtest/v11_round_analysis_preview.py`
- `backend/app/services/backtest/v20_round_analysis_preview.py`
- `frontend/src/pages/Backtest.tsx`
- `frontend/src/components/backtest/*`
- `frontend/src/lib/api.ts`
- `docs/BACKTEST_ENGINE_ARCHITECTURE.md`

**Test eseguiti (locale):**

- `pytest tests/test_round_analysis_*.py tests/test_backtest_models_import.py`

---

## backtest-step-k5-unavailable-macro-trace

**Titolo:** Macro K verificabile — conteggi normalizzati e trace dettagliato

**Descrizione:** Corretto il mini-run che contava `fixtures_with_unavailable=10` quando solo una fixture aveva righe in `fixture_missing_players`. La macro K legge ora solo dati normalizzati SportAPI; trace per giocatore con mapping, impact e `importance_reason`.

**Highlights:**

- `HistoricalUnavailableMacroService` usa `load_normalized_unavailable_for_side` (no fallback raw snapshot).
- Trace `unavailable_macro_detail` per side in preview/mini-run (`include_trace`).
- Summary mini-run: `total_unavailable_players`, `mapped/unmapped`, `fixtures_with_important_absences`.
- Fallback mapping prudente nome+team univoco in `resolve_player_ids`.
- `classify_importance` con reason esplicito (UNMAPPED, NO_PRIOR_STATS, LOW_IMPACT, …).
- UI BacktestDebugPanel: card K estesa + tabella trace preview.

**File toccati:**

- `backend/app/services/backtest/historical_unavailable_macro_service.py`
- `backend/app/services/backtest/pit_player_rolling_stats.py`
- `backend/app/services/backtest/sot_v21_pit_macro_builder.py`
- `backend/app/services/backtest/sot_v21_mini_run_preview_service.py`
- `backend/app/services/backtest/sot_pick_evaluation_preview_service.py`
- `backend/app/schemas/backtest_unavailable_macro_detail.py` (nuovo)
- `backend/app/schemas/backtest_point_in_time.py`
- `backend/app/schemas/backtest_sot_v21_mini_run.py`
- `frontend/src/lib/api.ts`
- `frontend/src/components/admin/BacktestDebugPanel.tsx`
- `backend/tests/test_historical_unavailable_macro.py`
- `backend/tests/test_unavailable_macro_summary.py` (nuovo)
- `backend/tests/test_unavailable_importance.py` (nuovo)
- `backend/tests/test_resolve_player_ids_name_fallback.py` (nuovo)
- `docs/BACKTEST_ENGINE_ARCHITECTURE.md`
- `docs/BACKTEST_ENGINE_CHANGELOG.md`

---

## backtest-step-k4-deduplicate-unavailable

**Titolo:** Deduplica indisponibili SportAPI (audit JK.1 / macro K)

**Descrizione:** Corretto doppio conteggio audit quando coesistono righe normalizzate in `fixture_missing_players` e payload raw SportAPI. Introdotto dedupe condiviso per chiave giocatore e separazione path usati vs diagnostici.

**Highlights:**

- Helper `pit_unavailable_dedup.py`: dedupe per `(fixture_id, team_side, provider_player_id, absence_group)`.
- Audit JK.1: conteggi solo da normalized se presente; raw in `source_paths_detected_diagnostic`.
- Schema/UI: `source_paths_used_for_counts`, `source_paths_detected_diagnostic`.
- Snapshot/macro K: dedupe su missing rows e unavailable raw; raw fallback solo se normalized=0.
- Persist: dedupe input backfill + upsert robusto su chiave naturale.
- Nessuna modifica formule/pesi v2.1; nessuna scrittura tabelle backtest.

**File toccati:**

- `backend/app/services/backtest/pit_unavailable_dedup.py` (nuovo)
- `backend/app/services/backtest/historical_unavailable_audit_service.py`
- `backend/app/services/backtest/pit_player_rolling_stats.py`
- `backend/app/services/backtest/historical_fixture_snapshot_service.py`
- `backend/app/services/backtest/historical_unavailable_macro_service.py`
- `backend/app/services/sportapi/sportapi_unavailable_persist_service.py`
- `backend/app/schemas/backtest_historical_unavailable_audit.py`
- `frontend/src/lib/api.ts`
- `frontend/src/components/admin/BacktestDebugPanel.tsx`
- `backend/tests/test_unavailable_dedup.py` (nuovo)
- `backend/tests/test_historical_unavailable_audit.py`
- `docs/BACKTEST_ENGINE_ARCHITECTURE.md` (§26/§27)
- `docs/BACKTEST_ENGINE_CHANGELOG.md` (questa entry)

---

## backtest-step-k4-bulk-sportapi-mapping-unavailable

**Titolo:** Bulk mapping e indisponibili SportAPI

**Descrizione:** Aggiunto flusso bulk per mappare fixture interne verso SportAPI e importare gli indisponibili storici missingPlayers in `fixture_missing_players`.

**Highlights:**

- Mapping fixture per giornata e stagione (`backfill-fixture-mappings-season`).
- Import unavailable per giornata e stagione (`backfill-unavailable-season`).
- Supporto dry-run/write, limit/offset, `api_calls`, `has_more`.
- Strict skip unavailable se mapping assente (no auto-match default).
- Parser missingPlayers home/away, upsert incrementale persist.
- Audit JK.1 verdict `unavailable_found_normalized`.
- UI BacktestDebugPanel K.3/K.4 con pulsanti stagione.
- Nessuna scrittura tabelle backtest.

**File toccati:**

- `backend/app/services/backtest/backtest_fixture_debug_service.py` (selector stagione)
- `backend/app/services/sportapi/sportapi_fixture_mapping_discovery.py` (cache scheduled-events)
- `backend/app/services/sportapi/sportapi_fixture_mapping_season_backfill_service.py` (nuovo)
- `backend/app/services/sportapi/sportapi_unavailable_season_backfill_service.py` (nuovo)
- `backend/app/services/sportapi/sportapi_fixture_mapping_backfill_service.py` (would_write intent)
- `backend/app/services/sportapi/sportapi_unavailable_backfill_service.py` (strict mapping)
- `backend/app/services/sportapi/sportapi_unavailable_persist_service.py` (upsert)
- `backend/app/services/backtest/historical_unavailable_audit_service.py` (verdict)
- `backend/app/schemas/sportapi_fixture_mapping_season_backfill.py` (nuovo)
- `backend/app/schemas/sportapi_unavailable_season_backfill.py` (nuovo)
- `backend/app/schemas/sportapi_unavailable_backfill.py` (response fields)
- `backend/app/routes/admin_sportapi.py`
- `frontend/src/lib/api.ts`
- `frontend/src/components/admin/BacktestDebugPanel.tsx`
- `backend/tests/test_sportapi_fixture_mapping_season_backfill.py` (nuovo)
- `backend/tests/test_sportapi_unavailable_backfill_strict.py` (nuovo)
- `docs/BACKTEST_ENGINE_ARCHITECTURE.md` (§29)
- `docs/BACKTEST_ENGINE_CHANGELOG.md` (questa entry)

---

## backtest-step-k3-sportapi-fixture-mapping

**Titolo:** Mapping fixture storiche SportAPI

**Descrizione:** Aggiunto discovery/scoring sicuro e backfill mapping interno ↔ SportAPI in `fixture_provider_mappings` per sbloccare K.2 su fixture finished senza mapping.

**Highlights:**

- Debug mapping fixture (`GET .../debug/fixture/{id}/mapping`).
- Backfill mapping round/fixture finished (`POST .../backfill-fixture-mappings`).
- Scoring K.3 dedicato: stesso giorno UTC obbligatorio, anti-ambiguità high.
- Salvataggio solo confidence `high` via `confirm_mapping` (`matched_by=sportapi_fixture_discovery`).
- K.2 unavailable: `suggested_next_step` se `mapping_missing`.
- UI BacktestDebugPanel sezione K.3.
- Nessun salvataggio tabelle backtest.

**File toccati:**

- `backend/app/services/sportapi/sportapi_fixture_mapping_discovery.py` (nuovo)
- `backend/app/services/sportapi/sportapi_fixture_mapping_scoring.py` (nuovo)
- `backend/app/services/sportapi/sportapi_fixture_mapping_debug_service.py` (nuovo)
- `backend/app/services/sportapi/sportapi_fixture_mapping_backfill_service.py` (nuovo)
- `backend/app/schemas/sportapi_fixture_mapping_debug.py` (nuovo)
- `backend/app/schemas/sportapi_fixture_mapping_backfill.py` (nuovo)
- `backend/app/schemas/sportapi_unavailable_debug.py` (suggested_next_step)
- `backend/app/services/sportapi/sportapi_unavailable_debug_service.py` (warning K.3)
- `backend/app/routes/admin_sportapi.py`
- `frontend/src/lib/api.ts`
- `frontend/src/components/admin/BacktestDebugPanel.tsx`
- `backend/tests/test_sportapi_fixture_mapping_scoring.py` (nuovo)
- `backend/tests/test_sportapi_fixture_mapping_debug.py` (nuovo)
- `backend/tests/test_sportapi_fixture_mapping_backfill.py` (nuovo)
- `docs/BACKTEST_ENGINE_ARCHITECTURE.md` (§28)
- `docs/BACKTEST_ENGINE_CHANGELOG.md` (questa entry)

---

## backtest-step-k2-sportapi-unavailable-backfill

**Titolo:** Import indisponibili storici SportAPI

**Descrizione:** Aggiunto debug/backfill degli indisponibili storici SportAPI e normalizzazione in `fixture_missing_players` per alimentare la macro Indisponibili storici.

**Highlights:**

- Debug fixture SportAPI unavailable (`GET .../lineup-unavailable`).
- Backfill round/fixture finished (`POST .../backfill-unavailable`).
- Parser robusto unavailable/injured/suspended multi-path.
- Normalizzazione `fixture_missing_players` con `source_fixture_id` = fixture target.
- Refactor `fetch_and_persist_lineups` su parser+persist condivisi.
- Macro K e snapshot: fallback `provider_raw_payload`.
- Audit JK.1: verdict `unavailable_found_in_raw_not_normalized`.
- UI BacktestDebugPanel sezione K.2.
- Nessun salvataggio tabelle backtest.

**File toccati:**

- `backend/app/services/sportapi/sportapi_unavailable_parser.py` (nuovo)
- `backend/app/services/sportapi/sportapi_unavailable_persist_service.py` (nuovo)
- `backend/app/services/sportapi/sportapi_unavailable_debug_service.py` (nuovo)
- `backend/app/services/sportapi/sportapi_unavailable_backfill_service.py` (nuovo)
- `backend/app/schemas/sportapi_unavailable_debug.py` (nuovo)
- `backend/app/schemas/sportapi_unavailable_backfill.py` (nuovo)
- `backend/app/services/sportapi/sportapi_lineup_service.py`
- `backend/app/services/backtest/historical_fixture_snapshot_service.py`
- `backend/app/services/backtest/historical_unavailable_audit_service.py`
- `backend/app/routes/admin_sportapi.py`
- `backend/tests/test_sportapi_unavailable_parser.py` (nuovo)
- `backend/tests/test_sportapi_unavailable_persist.py` (nuovo)
- `backend/tests/test_sportapi_unavailable_backfill.py` (nuovo)
- `backend/tests/test_historical_unavailable_audit.py`
- `frontend/src/lib/api.ts`
- `frontend/src/components/admin/BacktestDebugPanel.tsx`
- `docs/BACKTEST_ENGINE_ARCHITECTURE.md`

---

## backtest-step-jk1-validation-audit

**Titolo:** Step JK.1 — Validazione snapshot target e audit indisponibili

**Descrizione:** Layer read-only di validazione per `historical_official_xi`: sintesi `historical_summary` nel PIT context, `source_fixture_id` esplicito su preview/mini-run/pick eval, audit indisponibili su storage fixture target. Nessuna modifica formule/pesi/persistenza.

**Highlights:**

- `HistoricalPitExtensionsBuilder` condiviso tra PIT context e preview.
- `PointInTimeHistoricalSummary` su `GET point-in-time-context` in historical mode.
- Quattro campi `source_fixture_id_*` top-level su preview, mini-run fixture result, pick eval.
- `HistoricalUnavailableAuditService` + endpoint `GET historical-unavailable-audit`.
- Parser condiviso `pit_unavailable_parsing.py` per snapshot e audit.
- UI BacktestDebugPanel: card historical_summary, source_fixture_id, sezione audit JK.1.
- Verdict zero indisponibili documentato (`unavailable_not_found_in_current_storage`).
- `db_writes=false`, `pre_lineup` invariato.

**File toccati:**

- `backend/app/services/backtest/historical_pit_extensions_builder.py` (nuovo)
- `backend/app/services/backtest/historical_source_fixture_ids.py` (nuovo)
- `backend/app/services/backtest/historical_unavailable_audit_service.py` (nuovo)
- `backend/app/services/backtest/pit_unavailable_parsing.py` (nuovo)
- `backend/app/schemas/backtest_point_in_time_historical_summary.py` (nuovo)
- `backend/app/schemas/backtest_historical_unavailable_audit.py` (nuovo)
- `backend/app/services/backtest/point_in_time_context_service.py`
- `backend/app/services/backtest/sot_v21_preview_service.py`
- `backend/app/services/backtest/sot_v21_mini_run_preview_service.py`
- `backend/app/services/backtest/sot_pick_evaluation_preview_service.py`
- `backend/app/services/backtest/historical_fixture_snapshot_service.py`
- `backend/app/schemas/backtest_point_in_time.py`
- `backend/app/schemas/backtest_sot_v21_preview.py`
- `backend/app/schemas/backtest_sot_v21_mini_run.py`
- `backend/app/schemas/backtest_sot_pick_evaluation.py`
- `backend/app/routes/backtest_debug.py`
- `backend/tests/test_historical_pit_extensions.py` (nuovo)
- `backend/tests/test_historical_unavailable_audit.py` (nuovo)
- `backend/tests/test_backtest_point_in_time_context.py`
- `frontend/src/lib/api.ts`
- `frontend/src/components/admin/BacktestDebugPanel.tsx`
- `docs/BACKTEST_ENGINE_ARCHITECTURE.md`

---

## backtest-step-jk-historical-lineup-unavailable

**Titolo:** Lineup e indisponibili storici da fixture target esatta

**Descrizione:** Aggiunte macro Lineups e Indisponibili in modalità `historical_official_xi`, usando XI, panchina e indisponibili della fixture target esatta e rolling player stats solo pre-kickoff.

**Highlights:**

- Snapshot storico unificato per fixture target (`HistoricalFixtureSnapshotService`).
- Macro lineup storica (Step J) refactor su snapshot condiviso.
- Macro indisponibili storica (Step K) con penalità offensive e boost difensivo avversario prudente.
- `source_fixture_id` tracciato in preview trace.
- Warning `not_built_yet` rimossi in `historical_official_xi` quando dati disponibili.
- Nessun uso di formazioni precedenti/successive per la lineup target.
- Mini-run `unavailable_macro_summary`; pick eval con index indisponibili.
- Nessun salvataggio DB; `pre_lineup` invariato.

**File toccati:**

- `backend/app/services/backtest/historical_fixture_snapshot_service.py` (nuovo)
- `backend/app/services/backtest/historical_unavailable_macro_service.py` (nuovo)
- `backend/app/schemas/backtest_historical_fixture_snapshot.py` (nuovo)
- `backend/app/services/backtest/historical_lineup_macro_service.py`
- `backend/app/services/backtest/rolling_player_layer_service.py`
- `backend/app/services/backtest/sot_v21_preview_service.py`
- `backend/app/services/backtest/sot_v21_pit_macro_builder.py`
- `backend/app/services/backtest/sot_v21_mini_run_preview_service.py`
- `backend/app/services/backtest/sot_pick_evaluation_preview_service.py`
- `backend/app/schemas/backtest_point_in_time.py`
- `backend/app/schemas/backtest_sot_v21_preview.py`
- `backend/app/schemas/backtest_sot_v21_mini_run.py`
- `backend/app/schemas/backtest_sot_pick_evaluation.py`
- `backend/tests/test_historical_fixture_snapshot.py` (nuovo)
- `backend/tests/test_historical_unavailable_macro.py` (nuovo)
- `backend/tests/test_historical_lineup_macro.py`
- `backend/tests/test_rolling_player_layer.py`
- `frontend/src/lib/api.ts`
- `frontend/src/components/admin/BacktestDebugPanel.tsx`
- `docs/BACKTEST_ENGINE_ARCHITECTURE.md`

---

## backtest-step-j-historical-lineup-macro

**Titolo:** Step J — Historical Lineup Macro (macro `lineups` peso 5)

**Descrizione:** Valorizzazione read-only della macro `lineups` in modalità `historical_official_xi` da XI ufficiale storica, modulo, continuità titolari e panchina. `pre_lineup` invariato.

**Highlights:**

- `HistoricalLineupMacroService` con 7 componenti e cap 0.85–1.15.
- Helper PIT-safe `load_previous_official_lineups` / `count_xi_overlap`.
- Integrazione preview + pit macro builder + cleanup warning probabili.
- Mini-run `lineup_macro_summary` e campi lineup su pick evaluation.
- UI BacktestDebugPanel: preview, mini-run card J, riga compatta Step H.
- Nessun impatto consiglio giocata H.1, runtime live o persistenza.

**File toccati:**

- `backend/app/services/backtest/historical_lineup_macro_service.py` (nuovo)
- `backend/app/services/backtest/pit_player_rolling_stats.py`
- `backend/app/services/backtest/sot_v21_pit_macro_builder.py`
- `backend/app/services/backtest/sot_v21_preview_service.py`
- `backend/app/services/backtest/sot_v21_mini_run_preview_service.py`
- `backend/app/services/backtest/sot_pick_evaluation_preview_service.py`
- `backend/app/schemas/backtest_point_in_time.py`
- `backend/app/schemas/backtest_sot_v21_preview.py`
- `backend/app/schemas/backtest_sot_v21_mini_run.py`
- `backend/app/schemas/backtest_sot_pick_evaluation.py`
- `backend/tests/test_historical_lineup_macro.py` (nuovo)
- `frontend/src/lib/api.ts`
- `frontend/src/components/admin/BacktestDebugPanel.tsx`
- `docs/BACKTEST_ENGINE_ARCHITECTURE.md`

---

## backtest-step-h1-advice-layer

**Titolo:** Consiglio giocata pre-match per pick evaluation SOT

**Descrizione:** Aggiunto livello di consiglio giocata indipendente dal risultato finale: il sistema mostra sempre linee aggressive/caute e outcome, ma indica se prima del match avrebbe consigliato o escluso la giocata.

**Highlights:**

- Linee aggressive/caute sempre visibili.
- Consiglio GIOCA / NON GIOCARE / BORDERLINE.
- Motivi sintetici e playability score.
- `calculated_summary` separata da `advised_summary`.
- Breakdown advised (line, confidence, sample bucket).
- Linee default estese a 4.5, 10.5 e 11.5.
- Nessun Under.
- Nessun salvataggio DB.

**File toccati:**

- `backend/app/services/backtest/sot_pick_play_advice_logic.py` (nuovo)
- `backend/app/services/backtest/sot_pick_evaluation_logic.py`
- `backend/app/services/backtest/sot_pick_evaluation_preview_service.py`
- `backend/app/schemas/backtest_sot_pick_evaluation.py`
- `backend/app/routes/backtest_debug.py`
- `backend/tests/test_sot_pick_evaluation.py`
- `backend/tests/test_sot_pick_play_advice.py` (nuovo)
- `frontend/src/lib/api.ts`
- `frontend/src/components/admin/BacktestDebugPanel.tsx`
- `docs/BACKTEST_ENGINE_ARCHITECTURE.md`

---

## backtest-step-h-over-only-aggressive-cautious

**Titolo:** Step H — Over-only con strategia aggressiva + cauta

**Descrizione:** Correzione Step H: valutazione read-only **solo Over SOT** con due pick per fixture (linea aggressiva = max linea sotto prediction; linea cauta = scende se edge aggressivo ≤ soglia). Rimossi Under, `recommended_pick` unico e `min_edge`.

**Highlights:**

- Due pick Over per fixture: `aggressive_pick` + `cautious_pick`.
- `cautious_drop_threshold` (default 0.75) al posto di `min_edge`.
- Summary e breakdown separati aggressive/cautious (8 liste breakdown).
- Nessun salvataggio DB; invarianti PIT invariati.

**File toccati:**

- `backend/app/services/backtest/sot_pick_evaluation_logic.py`
- `backend/app/services/backtest/sot_pick_evaluation_preview_service.py`
- `backend/app/schemas/backtest_sot_pick_evaluation.py`
- `backend/app/routes/backtest_debug.py`
- `backend/tests/test_sot_pick_evaluation.py`
- `frontend/src/lib/api.ts`
- `frontend/src/components/admin/BacktestDebugPanel.tsx`
- `docs/BACKTEST_ENGINE_ARCHITECTURE.md`

---

## backtest-step-h

**Titolo:** Betting Pick Evaluation read-only

**Descrizione:** Aggiunta valutazione read-only delle giocate Over/Under SOT proposte dal modello PIT, con esito WIN/LOSS rispetto ai SOT reali.

**Highlights:**

- Endpoint pick evaluation preview.
- Recommended pick per fixture (max edge vs min_edge).
- Supporto linee 5.5/6.5/7.5/8.5/9.5.
- Min edge configurabile.
- Hit rate e breakdown per linea, side, confidence, sample, actual total.
- Nessun salvataggio DB.
- Nessuna modifica a v2.0/v2.1 runtime.

**File toccati:**

- `backend/app/services/backtest/sot_pick_evaluation_logic.py` (nuovo)
- `backend/app/services/backtest/sot_pick_evaluation_preview_service.py` (nuovo)
- `backend/app/schemas/backtest_sot_pick_evaluation.py` (nuovo)
- `backend/app/routes/backtest_debug.py`
- `backend/tests/test_sot_pick_evaluation.py` (nuovo)
- `frontend/src/lib/api.ts`
- `frontend/src/components/admin/BacktestDebugPanel.tsx`
- `docs/BACKTEST_ENGINE_ARCHITECTURE.md`

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
