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
