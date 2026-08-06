# Cecchino Lab — Dashboard analisi run storico

## Nota — Benchmark Goal Intensity V4 vs V5 (2026-08-06)

Sezione hub su run completed: preflight read-only, independence badge, pilot 300, full gated, cancel/resume, export ZIP. Job version `cecchino_lab_goal_intensity_v4_v5_historical_benchmark_v1`. Bundle frozen v2.1 non live. Overlap sviluppo → etichetta `historical_diagnostic_replay` (non external validation). Nessuna modifica run/snapshot.

## Nota — Segnali Cecchino V3 + Lab A–F (2026-08-06)

Contratto operativo: formula `cecchino_signals_matrix_v3_draw_dfg_decimal2` + consenso `cecchino_signal_consensus_v1_min_two` + audit `cecchino_signal_explanations_v3`. Raw SI ≠ `is_acquired`. Lab A–F: `cecchino_lab_signals_af_v2_current_v3_consensus` acquired-only; KPI/dashboard mercati **19**. Derived rebuild senza full scan: confirm `REBUILD_CECCHINO_LAB_DERIVED_V3` (provenance `derived_refresh`, no overwrite `source_git_commit`). Monitoraggio Today resta su `/monitoraggio-segnali`; overview STEP 4A/4B invariati nel layout.

## STEP 4B — Filtro V3 su KPI + pagina Segnali A–F (2026-08-02)

- Analisi KPI: filtro **Acquistabilità V3 minima** con funnel di copertura; aggregati ricalcolati sul sottoinsieme.
- Pagina autonoma Segnali A–F (non monta l’hub); opportunità vs celle; F = modello corrente.
- Tab Scansioni storiche: CTA semplificate (Analisi KPI · Segnali A–F · Report). Hub raggiungibile solo via URL.

| Voce | Valore |
|------|--------|
| Route A–F | `/cecchino-lab/historical-scans/:runId/signals-af` |
| Schema A–F | `cecchino_lab_historical_signals_af_v1` |
| Schema KPI | `cecchino_lab_historical_kpi_signals_v2` |

## STEP 4A — Hub resource-safe + Analisi KPI storico (2026-08-02)

**Causa crash:** la pagina Run caricava overview + `Promise.all` di 8 moduli + lazy timeline/pattern/esclusioni dopo 400 ms, saturando Railway.

**Hub nuovo:** al mount solo `GET …/dashboard/overview`. Card moduli con fetch on-demand (accordion). Card primaria **Analisi KPI storico** → route autonoma.

| Voce | Valore |
|------|--------|
| Route hub | `/cecchino-lab/historical-scans/:runId` |
| Route KPI | `/cecchino-lab/historical-scans/:runId/kpi-signals` |
| Schema analytics | `cecchino_lab_historical_kpi_signals_v1` |
| Endpoint | `GET …/kpi-signals/{summary,timeline,activations}` |
| Universo | eligible_core + rating ≥ 50 |
| Fasce | 50–59 … 90–99, 100 esclusiva |
| Quote | real (default) / derived / all (ROI mai misti) |
| Timeline | default date; matchday → fallback data (nessuna colonna giornata) |
| Attivazioni | limit 50 (max 100), paginate |
| Cache | summary + timeline TTL 300s |
| Invariato | Acquistabilità V3, Replay ID 1, Run #3, pagina Segnali KPI operativa |

Link in Storico run: **Apri analisi** (hub) + **Analisi KPI** (pagina KPI).

## STEP 3C.2 — Acquistabilità V3 ufficiale (2026-08-02)

Sezione **Acquistabilità** della dashboard Run: solo replay V3 ufficiale (resolver). Mostra Replay ID, stato, formula, scored/gate/unavailable, quote real/derived, ROI separati, riconciliazione. Se replay assente: «Acquistabilità V3 non disponibile» + CTA verso pagina Replay. Menu **Dettaglio Acquistabilità** e **Sintesi per ChatGPT** usano solo V3. Nessun fallback V1.1/V2. Endpoint: `GET …/dashboard/purchasability`, `GET …/purchasability`, `GET …/purchasability/report`.

## STEP 3C.1 — Analytics Replay V3 (fuori dashboard Run) (2026-08-02)

Analytics/export V3 su `/cecchino-lab/purchasability-replay` (lazy + download analysis/full). **STEP 3C.2** ha collegato V3 a dashboard e menu report ufficiali.

## STEP 3B.1.2 — Paginazione transaction-safe (2026-08-02)

Dashboard Run invariata. Worker: keyset per snapshot id (niente named cursor tra commit); UI progress mostra Non applicabili / Non classificati + messaggio failed recuperabile. **Riprendere Replay ID 1** dopo deploy (non nuovo start).

## STEP 3B.1.1 — Harden worker replay V3 (2026-08-02)

Dashboard Run invariata. Worker ottimizzato (batch mercati, contatori incrementali, resource_profile in progressione UI). Aggiornato in 3B.1.2 per commit-safe pagination.

## STEP 3B.1 — Job replay V3 (2026-08-02)

La dashboard Run **non** esegue il replay. Job isolato + UI su `/cecchino-lab/purchasability-replay`. Tabelle dedicate; Run storico immutabile. Replay reale avviato (Replay ID 1) e interrotto al batch 1 — ripresa post-3B.1.2. Analytics/export V3 = STEP 3C.

## STEP 3A.2 — Integrità storica preflight (2026-08-02)

Il preflight resta fuori dalla dashboard. Schema v2 + policy ricostruzione storica: lock chronology non applicabile; hash/lock come prova di freeze; classificazione completa in UI Replay. Infrastruttura job = STEP 3B.1 (nessun avvio reale ancora).

## STEP 3A.1 — Preflight fuori dalla dashboard (2026-07-29)

Il preflight replay Acquistabilità V3 **non** è più montato su `/cecchino-lab/historical-scans/:runId`. Accesso da **Storico run → Verifica replay Acquistabilità** → `/cecchino-lab/purchasability-replay?run_id=`. La dashboard Run non chiama più l’endpoint preflight e non compete con summary/probe resource-safe.

## STEP 3A — Replay Acquistabilità V3 preflight (2026-07-29) [superato da 3A.1 per UI]

Originariamente sulla pagina run, dopo Acquistabilità (export V2). Dal 3A.1: pagina autonoma; summary `include_probe=false`; probe opzionale; nessun Avvia replay. Schema aggiornato in 3A.2; motore V3 e export V2 invariati.

## Obiettivo

Dashboard **read-only** per visualizzare e analizzare ogni run storico del Cecchino Lab (pilota, bilanciato, completo, attivo, fallito, cancellato).

Legge esclusivamente tabelle `cecchino_lab_*` già persistite. **Non** riesegue scan, settlement, formule, né scrive snapshot/`summary_json`.

## Isolamento

- Nessuna modifica a Cecchino Today / Betfair / formule operative
- Servizio dedicato: `backend/app/services/cecchino_data_lab/historical_run_analytics_service.py`
- Aggregazioni pure condivise: `historical_analytics_agg.py` (riusate anche dal report AI ZIP) — stessa `analytics_aggregation_version` (`cecchino_lab_analytics_agg_v2_3`)
- Export segnali: `historical_signal_export.py` (`signal_export_schema_version=cecchino_lab_signal_export_v1`) — opportunità deduplicate vs celle legacy
- Export Acquistabilità: `historical_purchasability_export.py` (`purchasability_export_schema_version=cecchino_lab_purchasability_export_v1`) — compact/decisions/drift; gate ≠ «Molto Bassa»
- Route: `backend/app/routes/cecchino_lab.py` sotto `/api/cecchino-lab/historical-scans/{run_id}/dashboard/*`
- Frontend: `/cecchino-lab/historical-scans/:runId`

## Acquistabilità (dashboard)

Quattro viste osservazionali (nessuna modifica formula):

1. **Punteggi per mercato** — gate, score finale persistito, diagnostico pre-gate, Rating/Edge/vantaggio/quota/risultato/profitto
2. **Gate** — accettati/rifiutati/motivi; etichetta obbligatoria «Bloccato dal gate» (mai «Molto Bassa» su rejected)
3. **Scelta per famiglia** — 1X2 / Goal 2.5 / DC sintetica; tie espliciti; nessuna selezione se tutti rejected
4. **Drift** — score zero / gate accepted / ≥80 / sample normalizzazione / profili distinti

Warning persistente: modulo osservazionale; descrive la formula congelata del Run #3; non è una strategia.

## Segnali A–F (dashboard)

Sezione a due livelli (module `cecchino_lab_signals_af_v2_current_v3_consensus`, formula V3 + consenso min-two):

- **Opportunità uniche / acquired** — metrica operativa = segni con `is_acquired=true`; ROI/hit/overlap con F; mai sommare celle SI grezze come scommesse
- **Celle attive (raw SI)** — solo diagnostica overlapping (`attribution_mode=overlapping`); non equivalgono ad acquisizione
- `with_signal_active` non mostrato come sovrapposizione; etichette: «Opportunità uniche», «Celle attive», «Sovrapposizione con F», «F — modello corrente»
- Consenso **per mercato** (non ROI multi-mercato aggregato); DRAW_PT eredita consenso DRAW

## Formulazioni obbligatorie

Usare: prestazioni osservate, pattern candidato, campione insufficiente / esplorativo / descrittivo, modulo osservazionale, quota Bet365 reale / derivata / N/D, risultati congelati.

**Non** dichiarare: profitto complessivo del Cecchino, modello vincitore, giocata migliore, somma HOME+DRAW+AWAY / Over+Under, Â«stabileÂ» fuori da `stable_candidate`.

## Coerenza report / dashboard

Report AI e dashboard usano le **stesse** funzioni pure in `historical_analytics_agg.py` per:

- conteggi real / derived / unavailable (+ riconciliazione)
- medie quote (`null` se assenti)
- fasce Rating / AcquistabilitÃ  / Aâ€“F / pattern / stabilitÃ

Differenze ammesse solo per **filtri** diversi, non per formule divergenti.
Ogni response rilevante espone `analytics_aggregation_version`.

## Quote e UI

- KPI / mercati: quote reali, derivate, **non disponibili**
- Medie odds e profit/ROI: `formatNullableNumber` / `—` se `null` (zero solo se `quote_count > 0`)
- Contatori: `with_cecchino_probability`, `with_cecchino_fair_quote`, `with_rating`
- Header: badge Scansione / Analytics / Aggregatore (`scan_source_git_commit` ≠ `analytics_runtime_git_commit`)
- Rating/Acquistabilità: vista primaria per mercato; warning mercati indipendenti; fascia `100` esclusiva

## Pattern Radar

- Sempre con `market_key` nel titolo
- Badge campione: Esplorativo / Descrittivo / Candidato da validare
- Badge stabilitÃ : Insufficiente / Concentrata / Incoerente / Coerente / Candidata stabile
- Sezione **Diagnostica copertura** separata (`diagnostics`)
- Warning campione piccolo; nessuna frase che suggerisca una giocata

## Filtri

Cumulabili su tutti gli endpoint analytics:

`competition`, `date_from`, `date_to`, `market_key`, `rating_band`, `purchasability_band`, `quote_quality`, `signal_model`, `signal_active`, `balance_class`, `goal_intensity_status`, `purchasability_status`, `eligibility_status`

Default performance: `eligible_core`. Esclusioni solo in sezione esclusioni/qualitÃ .

I filtri frontend restano in query string (URL condivisibile).

## Endpoint

| Path | Contenuto |
|------|-----------|
| `GET .../dashboard/overview` | run meta, progress, KPI, `scan_source_git_commit`, `analytics_runtime_git_commit*`, `analytics_aggregation_version`, `is_provisional` |
| `GET .../dashboard/markets` | **19** mercati indipendenti (`KPI_V2_ROW_DEFS`) + unavailable + medie/profit null-safe |
| `GET .../dashboard/ratings` | matrice mercato × fascia Rating + warning indipendenza |
| `GET .../dashboard/purchasability` | primaria `by_market`; distribuzione globale diagnostica |
| `GET .../dashboard/signals` | modelli Aâ€“F (F = corrente) |
| `GET .../dashboard/balance` | 4 pilastri + combinazioni |
| `GET .../dashboard/goal-intensity` | 4 componenti GI |
| `GET .../dashboard/competitions` | League DNA |
| `GET .../dashboard/timeline` | cronologia su kickoff storico |
| `GET .../dashboard/patterns` | positive / negative / watchlist / unstable / **diagnostics** |
| `GET .../dashboard/exclusions` | motivi esclusione |
| `GET .../matches` | explorer (filtri estesi) |
| `GET .../matches/{snapshot_id}` | prematch vs result_after_lock |

## Sezioni UI

A Header · B Live progress · C V1 Pulse · D 19 mercati · E Rating · F Acquistabilità · G Segnali A–F · H Balance · I Intensità Goal · J League DNA · K Timeline · L Pattern · M Match explorer · N Esclusioni

Report download: riusa API ZIP esistenti (voce consigliata Â«Sintesi per ChatGPTÂ»). Rigenerabile dagli snapshot giÃ  presenti (nessuna nuova scansione).

## Run attivo vs completato

- Attivo: `is_provisional=true`, badge Â«Dati provvisoriÂ», polling overview ~4s / analytics ~20s
- Completato: `is_provisional=false`, badge Â«Risultati congelatiÂ», nessun polling continuo

Compatibile con Run #1, #2, #3 completo e run futuri (sola lettura).
