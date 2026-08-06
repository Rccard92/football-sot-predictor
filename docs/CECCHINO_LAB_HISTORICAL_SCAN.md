# Cecchino Lab — Scansione storica (replay pre-match)

## Monitoraggio Segnali Cecchino — consenso V2 (2026-08-06)

Nota operativa (pagina `/monitoraggio-segnali`, non Lab Run): formule X V3 Decimal + consenso min-two; sync/monitoraggio **current-only** (V3); V1/V2 preservate fuori scope; nessun backfill storico automatico; default UI `current`+`acquired`. Il Lab scan storico non è modificato da questa feature.

## Segnali KPI operativi — 19 mercati (2026-08-06)

Nota operativa (pagina `/segnali-kpi`, non Lab Run): Heatmap allineata ai 19 mercati Pannello KPI; settlement PT/FT completo; filtri Acquistabilità V3/V3.1 su snapshot pre-match storicizzati. Il Lab storico KPI (STEP 4A/4B) resta separato e non è modificato da questa estensione.

Fix follow-up (stesso giorno): persistenza `purchasability_v31_registry_status` (migration `20260806143000`); Quota Book candidati solo finite > 1,00; nessun ricalcolo Acquistabilità né impatto sul Lab scan.

## STEP 2B — Replay Acquistabilità V3.1 (shadow validation) (2026-08-06)

| Campo | Valore |
|-------|--------|
| Formula corrente | `cecchino_purchasability_v31_fixed_discount_empirical_v2` |
| Formula v1 frozen | `cecchino_purchasability_v31_fixed_discount_empirical_v1` |
| Infra | riuso tabelle/API replay V3 (`formula_version` distingue) |
| Mercati | 19 classificati; assenti → `source_market_unavailable` |
| HR | walk-forward anti-leakage; metriche anche con n&lt;30 (provisional) |
| GO/NO-GO | `purchasability_v31_go_no_go_v2` (v1 preservata) |
| Preservati | Run #3, Replay V3 ID 1, eventuali replay V3.1 v1 |
| Promozione | solo `GO_FINAL` v2 (non eseguita senza holdout/replay reale) |

## STEP 4B — KPI × Acquistabilità V3 + Segnali A–F (2026-08-02)

| Voce | Valore |
|------|--------|
| Filtro KPI | `purchasability_min_score` 0–100 inclusivo; null = nessun filtro |
| Replay | `resolve_official_purchasability_v3_replay` (nessun hardcode ID) |
| Join | `(match_snapshot_id, market_key)` ↔ `(source_snapshot_id, market_key)` |
| Mercati V3 | HOME, DRAW, AWAY, OVER_2_5, UNDER_2_5, ONE_X, X_TWO, ONE_TWO |
| Funnel | base → supported+joined → scored → matched; gate failed ≠ score 0 |
| Schema KPI | `cecchino_lab_historical_kpi_signals_v2` |
| Pagina A–F | `/cecchino-lab/historical-scans/{run_id}/signals-af` |
| Endpoint A–F | `GET …/signals-af/{summary,activations}` |
| Granularità A–F | opportunità unica (run+snapshot+modello+mercato); celle = diagnostica |
| Nav Storico | solo Analisi KPI · Segnali A–F · Report (hub non linkato) |
| Nessuna | migration, scansione, replay, backfill, modifica formule |

## STEP 4A — Analisi KPI storico resource-safe (2026-08-02)

Backtest del Pannello KPI sulle MarketResult della Run, senza ricalcolo e senza API esterne.

| Voce | Valore |
|------|--------|
| Servizio | `historical_kpi_signals_analytics.py` |
| Schema | `cecchino_lab_historical_kpi_signals_v1` |
| Hub Run | solo overview al mount; moduli on-demand |
| Pagina | `/cecchino-lab/historical-scans/{run_id}/kpi-signals` |
| Universo | eligible_core, rating ≥ 50; &lt;50 solo diagnostics |
| Metriche | allineate a Segnali KPI operativi (quota void = 1/win rate) |
| Heatmap | Pronostico × Rating, sample_class visuale |
| Timeline | per data/settimana; matchday non disponibile → fallback data |
| Resource | select scalari, no full ORM, no JSONB snapshot |
| Nessuna | migration, scansione, replay, backfill, modifica V3 |

## STEP 3C.2 — Acquistabilità V3 ufficiale per Run storiche (2026-08-02)

V3 è l’**unica sorgente ufficiale** di Acquistabilità per le Run che possiedono un replay V3 completato e compatibile (resolver read-only, nessun hardcode di Replay ID).

| Voce | Valore |
|------|--------|
| Resolver | `resolve_official_purchasability_v3_replay(db, source_scan_run_id)` |
| Analytics schema | `cecchino_lab_purchasability_v3_analytics_v2` (niente `v2_v3_comparison`) |
| Export schema | `cecchino_lab_purchasability_v3_export_v2` |
| Dashboard Run | sezione Acquistabilità → replay V3 ufficiale |
| Dettaglio Acquistabilità | ZIP V3 (`cecchino-run-{id}-purchasability-v3.zip`) |
| Sintesi ChatGPT | sezione `purchasability` solo V3; se assente → `status=unavailable` |
| Archivio ufficiale | `legacy_purchasability_excluded=true` (nessuna serializzazione V1.1/V2) |
| Endpoint Run-centric | `GET …/historical-scans/{run_id}/purchasability` (+ `/report`) |
| Fallback legacy | **disabilitato** (`LEGACY_PURCHASABILITY_FALLBACK_ALLOWED=false`) |
| Dati | V1.1/V2 restano nel DB fisicamente; percorsi ufficiali non li leggono |
| Invariato | formula V3, Replay ID 1, 36488 risultati, Run #3, snapshot, MarketResult, nessuna migration |

Run #3 risolve attualmente Replay ID 1 perché è l’unico replay compatibile completato (selezione dinamica, non hardcodata).

## STEP 3C.1 — Analytics ed export Replay Acquistabilità V3 (2026-08-02)

Replay ID 1 su Run #3 (2021/2022) completato con warning: 4561 snapshot, 36488 risultati, 13534 scored, 22950 gate failed, 4 unavailable, 22801 quote reali, 13683 derivate, 0 errori.

| Voce | Valore |
|------|--------|
| Analytics schema | `cecchino_lab_purchasability_v3_analytics_v1` → **superseded by v2 in 3C.2** |
| Export schema | `cecchino_lab_purchasability_v3_export_v1` → **superseded by v2 in 3C.2** |
| Endpoint analytics | `GET /api/cecchino-lab/purchasability-v3-replays/{id}/analytics` (lazy) |
| Endpoint report | `GET …/report?mode=analysis\|full_archive` (StreamingResponse) |
| Sorgente | solo `CecchinoLabPurchasabilityV3ReplayRun` + `…ReplayResult` |
| Formula | `formula_recomputed=false` — nessun ricalcolo |
| Universi | ALL / SCORED / GATE_FAILED / UNAVAILABLE / REAL_PERF / SYNTHETIC_PERF |
| Gate failed | non mappato a score 0 / fascia 0–19 |
| Family decisions | diagnostiche in-memory; no migration |
| UI | sezione Analisi Replay V3 su `/cecchino-lab/purchasability-replay` |
| Post-3C.2 | percorsi ufficiali Run usano V3; V2 solo conservazione tecnica |

**STEP 3C.2:** completato — V3 unica Acquistabilità ufficiale; nessun fallback legacy.

## STEP 3B.1.2 — Paginazione transaction-safe replay V3 (2026-08-02)

Incidente sul primo replay reale (Replay ID 1): dopo il primo batch (100 snapshot / 800 risultati persistiti) PostgreSQL ha invalidato il named/server-side cursor (`named cursor isn't valid anymore`) perché il worker faceva `commit` a cursore ancora aperto (`stream_results` + `yield_per`).

| Voce | Valore |
|------|--------|
| Causa | commit per-batch durante Result streaming |
| Fix | keyset pagination `id > :after` + `.all()`; nessun `stream_results`/`yield_per` nel loop worker |
| Strategia | `snapshot_pagination_strategy: keyset_by_snapshot_id` (`formula_order_independent: true`) |
| Resume | stesso Replay ID 1; `done_ids` + reconcile; nessuna perdita delle 800 righe |
| Contatori | gate_failed ha priorità su `calculation_status=not_applicable` della formula |
| Error code rete | `snapshot_pagination_cursor_invalidated` (recoverable) |
| Invariato | formula V3, schema, migration, preflight, Run #3, snapshot, MarketResult |

**Nessun nuovo start / nessuna scansione durante il fix.** Dopo deploy: Riprendi Replay ID 1 (non «Avvia replay»).

## STEP 3B.1.1 — Harden worker replay V3 (2026-08-02)

Ottimizzazione resource-safe del worker **prima** dell’avvio reale. Formula, schema, migration, preflight, endpoint e semantica cancel/resume **invariati**.

| Voce | Valore |
|------|--------|
| Batch snapshot | `REPLAY_BATCH_SNAPSHOTS = 100` via keyset `_fetch_next_eligible_snapshot_batch` (ex streaming, sostituito in 3B.1.2) |
| Market query | 1 `_load_markets_for_snapshots` per batch (~46 per Run #3, non 4561) |
| Contatori | incrementali (`summarize_result_rows`); no full recount a ogni heartbeat |
| Riconciliazione SQL | `_reconcile_counts_from_db` solo a inizio resume / fine job / cancel |
| Memoria | max ≤100 snapshot e ≤800 righe mercato per batch |
| Duplicati | nessun troncamento silenzioso; `ambiguous_market_join` → fail controllato |
| Diagnostica | `summary_json.resource_profile` (batch, query, formula invocations, max memory) |

Worker aggiornato in STEP 3B.1.2 (keyset commit-safe). Replay reale avviato poi fallito al batch 1 → ripresa post-fix.

## STEP 3B.1 — Job replay Acquistabilità V3 isolato (2026-08-02)

Infrastruttura persistente per replay V3 **separato** dal Run storico. Non modifica snapshot, MarketResult né Run #3.

| Voce | Valore |
|------|--------|
| Schema replay | `cecchino_lab_purchasability_v3_replay_v1` |
| Engine | `cecchino_lab_purchasability_v3_replay_engine_v1` |
| Tabelle | `cecchino_lab_purchasability_v3_replay_runs`, `…_replay_results` |
| Migration | `20260802120000` (solo nuove tabelle + indici) |
| Start | `POST /api/admin/cecchino-lab/historical-scans/{run_id}/purchasability-v3-replays` (`confirmed: true` + versioni attese) |
| Status / list | `GET …/purchasability-v3-replays/{id}`, `GET …/historical-scans/{run_id}/purchasability-v3-replays` |
| Cancel / resume | `POST …/cancel`, `POST …/resume` |
| Worker | thread daemon + `SessionLocal` dedicata; batch 100 snapshot; heartbeat 5s; stale→`interrupted` 120s |
| Idempotenza | chiave deterministica; completed/active riusati; nessun `force_new` |
| Anti-leakage | panel whitelist; performance collegata **dopo** lo score; 1 riga per valutazione teorica |

UI: CTA **Avvia replay Acquistabilità** sulla pagina autonoma (dopo preflight+probe Go), modal di conferma, progressione/polling, cancel/resume. Worker hardenato in STEP 3B.1.1. **Nessun replay reale ancora avviato** (STEP 3B.2). Analytics/export V3 = STEP 3C.

## STEP 3A.2 — Semantica integrità storica preflight (2026-08-02)

Causa Run #3: `pre_match_locked_at` è il wall-clock del **freeze di ricostruzione** durante lo scan Lab (`_utcnow()`), non una cattura prospettica pre-kickoff. Confrontarlo con `kickoff_at` storico (2021) marcava tutte le valutazioni come `invalid` → contatori exact/warning/not_replayable a 0 in UI.

| Voce | Valore |
|------|--------|
| Schema | `cecchino_lab_purchasability_v3_replay_preflight_v2` |
| Integrity policy | `cecchino_lab_historical_reconstruction_integrity_v1` |
| Mode Lab | `historical_reconstruction_frozen` (chronology lock check = `not_applicable`) |
| Mode prospettico | `prospective_pre_match` solo se `lock < kickoff` dimostrabile |
| Classificazione | somma stati = `theoretical_evaluations`; `unclassified_evaluations` deve essere 0 |
| Probe | contatori completi + `by_market` + invariante somma = `formula_items_returned` |
| Cache | `run_id\|schema\|integrity_policy\|formula\|runtime_git\|summary\|probe` |

Anti-leakage invariato (whitelist formula / performance separate). **Nessun replay eseguito.** STEP 3B subordinato a Go sul nuovo summary+probe.

## STEP 3A.1 — Preflight resource-safe (2026-07-29)

Incidente Run #3: click preflight → `Failed to fetch` su preflight e sezioni dashboard; processo backend Railway riavviato; nessuna risposta HTTP sul preflight. **Nessuna prova definitiva di OOM**; causa applicativa individuata nel caricamento ORM completo (~6308 snapshot + ~63854 MarketResult) + mappa globale `markets_by_snap` in competizione con la dashboard Run.

Mitigazione 3A.1:

| Voce | Valore |
|------|--------|
| Schema | `cecchino_lab_purchasability_v3_replay_preflight_v1` (poi superato da v2 in 3A.2) |
| Endpoint | `GET .../preflight?include_probe=false` (default summary) / `include_probe=true` (probe 30) |
| Strategia | aggregati SQL + streaming colonne scalari (`yield_per=500`); niente full ORM / JSON pesanti |
| Budget | max 100k righe supportate; max 30s runtime → `blocked` + `preflight_resource_budget_exceeded` |
| UI | pagina autonoma `/cecchino-lab/purchasability-replay` (link da Storico run); **rimossa** dalla dashboard Run |
| Cache | chiave include `include_probe` |

Regole business del preflight invariate fino a 3A.2 (integrità). **Nessun replay eseguito.**

## STEP 3A — Preflight replay Acquistabilità V3 (2026-07-29)

Preflight **read-only** per verificare se Acquistabilità V3 può essere ricalcolata sugli snapshot pre-match già congelati, **senza** nuova scansione, ricalcolo modello/KPI/segnali/Balance/GI, API esterne o scritture DB.

| Voce | Valore |
|------|--------|
| Schema | vedi 3A.2 (`…_preflight_v2`) |
| Servizio | `historical_purchasability_v3_replay_preflight.py` |
| Endpoint | `GET /api/cecchino-lab/historical-scans/{run_id}/purchasability-v3-replay/preflight` |
| UI (post 3A.1) | `/cecchino-lab/purchasability-replay?run_id=` — summary poi probe opzionale |
| Universo | snapshot `eligible_core`; 8 mercati V3; escluse conteggiate a parte |
| Probe | solo se `include_probe=true`; max 30 snapshot; nessuna persistenza |
| Cache | vedi 3A.2 |

**STEP 3B.1 (job isolato):** tabelle/API/UI start+progress; **nessun replay reale ancora**. STEP 3B.2 = avvio controllato Run #3. STEP 3C = analytics/export V3. Export V2 invariato. Motore V3 invariato.

Anti-leakage: formula usa solo campi pre-match; `won`/`profit_*`/`result_*`/`settlement_*` solo per copertura performance futura.

## Dashboard analisi run

Dopo il completamento della scansione, aprire l’analisi da **Storico run → Apri analisi** oppure `/cecchino-lab/historical-scans/:runId`.

Documentazione dedicata: [`CECCHINO_LAB_RUN_DASHBOARD.md`](./CECCHINO_LAB_RUN_DASHBOARD.md).

Endpoint JSON read-only sotto `/api/cecchino-lab/historical-scans/{run_id}/dashboard/*`. Aggregazioni pure in `historical_analytics_agg.py` (condivise col report ZIP, `analytics_aggregation_version=cecchino_lab_analytics_agg_v2_3`). Export segnali opportunità/celle in `historical_signal_export.py` (`signal_export_schema_version=cecchino_lab_signal_export_v1`). Export Acquistabilità compatto in `historical_purchasability_export.py` (`purchasability_export_schema_version=cecchino_lab_purchasability_export_v1`). **Nessuna riscrittura** di run/snapshot/settlement.

Aggregazioni hardened: riconciliazione real+derived+unavailable; medie odds `null` se assenti; pattern sempre `market_key`; soglie su quote reali; `cross_competition_stability`; diagnostiche assenze dati separate. Report AI e dashboard condividono le stesse formule pure — vedi `CECCHINO_LAB_AI_REPORT_SCHEMA.md` e `CECCHINO_LAB_RUN_DASHBOARD.md`.

## Isolamento

- Solo Cecchino Lab (`cecchino_lab_*` + `cecchino_data_lab`).
- **Non** modifica Cecchino Today, formule, gate Betfair, snapshot operativi.
- Bookmaker operativo Today: **Betfair** (invariato).
- Bookmaker replay storico: **Bet365** (CSV Football-Data).
- Run #1 (test tecnico 200 partite) resta consultabile e non viene rielaborato.

## Audit moduli (FASE 1)

| Modulo | Funzione canonica | Parità live | Lab |
|--------|-------------------|-------------|-----|
| Intensità Goal | 7 feature + `TrainEcdf` + `_pillar_scores_from_pct` | **Parziale** (no bundle Today, no xG) | `historical_goal_intensity.py` |
| Acquistabilità | `calculate_purchasability_v2_item` + profilo progressivo | **Non equivalente Betfair** | `historical_purchasability.py` |
| Segnali A–F | pesi ufficiali + `compute_final_odds` + `build_signals_matrix` | **F = modello corrente** | `historical_signal_models.py` |

## Avvio

1. UI: tab **Scansioni storiche** in `/cecchino-lab`
2. API `POST /api/admin/cecchino-lab/historical-scans`

### Modalità

| Modalità | Body | UI |
|----------|------|-----|
| **Scansione completa** (percorso primario) | `max_matches: null` | “Scansione completa” |
| Test tecnico (diagnostica) | `max_matches: 200` | menu **Opzioni tecniche** |
| Pilota bilanciato (diagnostica) | `pilot_strategy: "eligible_per_competition"`, `eligible_per_competition: 20` | menu **Opzioni tecniche** |

La UI principale mostra solo **Verifica dati** e **Scansione completa**. Test tecnico e pilota bilanciato restano disponibili nel backend e nel menu secondario «Opzioni tecniche».

Intensità Goal e Equilibrio vs Squilibrio sono **moduli osservazionali**: valori completi/parziali/non disponibili vengono salvati su ogni partita eleggibile e **non** bloccano l’eleggibilità `eligible_core`.

Pilota bilanciato: per ogni campionato, ordine cronologico, registra escluse, si ferma a N `eligible_core`, poi passa al successivo. Target tipico fino a 320 eleggibili; processate totali possono superare il target. `run_scope=balanced_pilot`, `is_partial_run=true`, `not_full_season_report=true`.

Progresso: a completamento `competitions_completed == competitions_total`, `current_competition=null`, `progress_pct=100` (fix off-by-one sull’ultimo campionato). Run #1/#2 già persistiti non vengono riscritti.

Scansione completa con revisione git sconosciuta: **bloccata**. Pilota: permesso + warning in policy/manifest.

## Revisione Git

Ordine: `RAILWAY_GIT_COMMIT_SHA` → `SOURCE_VERSION` → `GIT_COMMIT_SHA` → `VERCEL_GIT_COMMIT_SHA` → `git rev-parse HEAD`.

Salvati sul run: `source_git_commit`, `source_git_commit_source`, `source_revision_status` (revisione **scan**).
Report/dashboard espongono anche la revisione **runtime** (`report_generator_git_commit` / `analytics_runtime_git_commit`) risolva a generazione/lettura — non riscrivono il run.

## Pipeline per partita

1. Contesti pre-match (anti-leakage)
2. Cecchino + goal markets + KPI Bet365
3. Intensità Goal storica (pilastri) + Acquistabilità storica Bet365 + segnali modelli A–F
4. Eleggibilità storica
5. Freeze snapshot + hash SHA-256 pre-match (include GI/purch/A–F/profilo/versioni; **no** risultato/settlement)
6. Collegamento risultato FT/HT
7. Settlement mercati **solo se** `core_eligible=true` (default settlement su modello F)

### Partite escluse

- Snapshot + risultato + motivo salvati; `settlement_status=excluded`
- Zero righe mercato nelle metriche di performance
- Diagnostica in `excluded_diagnostics`

## Intensità Goal storica

- Versione: `cecchino_lab_goal_intensity_historical_v1`
- `parity_status=partial`: stesse feature/pilastri, ECDF progressivo solo su eligible_core precedenti dello stesso run; **nessun** bundle produzione Today
- xG: `missing`, mai imputato a 0
- Campione insufficiente → status esplicito, score null
- Persistenza: `goal_intensity_compatibility_json` (payload arricchito, retrocompatibile)

## Acquistabilità storica Bet365

- Versione: `cecchino_lab_purchasability_historical_v1`
- Profilo progressivo: solo KPI eligible_core precedenti; target/futuro esclusi; no risultati reali nel profilo; no profilo Betfair
- Prima di `MIN_SIDE_SAMPLES` (15): `insufficient_historical_normalization_sample`, score null
- `quote_quality`: `real` | `derived` | `unavailable`
- Osservazionale: non blocca eleggibilità, non sceglie giocate, non entra in Today
- Resume: stesso profilo hash dagli snapshot precedenti
- **Export read-only** (`cecchino_lab_purchasability_export_v1`): `purchasability_compact.jsonl` canonico; gate rejected ≠ «Molto Bassa»; `diagnostic_ungated_score` da phase persistite; decisioni/drift/profili; formula **non** ricalcolata; Run #3 invariato

## Modelli segnali A–F

`signals_json`:

```json
{
  "default_model_key": "F",
  "default_matrix": {},
  "models": { "A": { "meta", "weights", "final", "matrix", "active_signals", "settlements" }, "...": "F" }
}
```

Pesi ufficiali invariati; F ≡ modello corrente. Snapshot legacy (Run #1, matrice flat) restano leggibili.

## Report AI v4 (frammentati)

`GET /api/cecchino-lab/historical-scans/{id}/report?mode=...`

| Mode | Contenuto |
|------|-----------|
| `ai_summary` | Sintesi ChatGPT (consigliata): manifest, report_index, summary, patterns_top, schema — senza JSONL enormi |
| `competition` | Singolo campionato + matches/purchasability compact |
| `module` | `markets` \| `signals` \| `goal_intensity` \| `purchasability` \| `balance` |
| `full_archive` | Archivio tecnico completo — non necessario per la prima analisi ChatGPT |

Generazione progressiva (`SpooledTemporaryFile` + JSONL riga-per-riga). Etichette A–F da `model_meta_for_key` / `get_cecchino_weight_model` (nessun `model_label` null in export).

Profitto in `summary_json` del run: per mercato / modello A–F / fascia rating / fascia Acquistabilità.
`technical_sum_across_all_independent_market_rows` + `not_a_betting_strategy=true` — non è profitto del Cecchino.

## Anti-leakage e hash

Priori con kickoff strettamente precedente. Hash include moduli calcolati; non include FT/HT/esito/profitto.

## Test

```bash
cd backend
pytest -q tests/test_cecchino_lab_historical_scan.py
pytest -q tests/test_cecchino_lab_historical_modules_v3.py
pytest -q tests/test_cecchino_lab_*.py
```
