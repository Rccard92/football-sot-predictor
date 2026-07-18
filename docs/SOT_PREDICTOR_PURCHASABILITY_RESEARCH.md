# Indice di Acquistabilità — Research

Modulo **indipendente** dal Rating. Risponde a: *quanto è statisticamente affidabile acquistare il valore individuato dal modello?*

## Fase 2A.3 — Job asincrono (infrastruttura, versione statistica invariata)

Problema: il GET sincrono tiene aperta la connessione HTTP per tutto il calcolo (~155–160s con 200 bootstrap). Il proxy Railway chiude prima → nel browser appare spesso “Failed to fetch” / assenza di `Access-Control-Allow-Origin` (**falso CORS**; non modificare CORS).

Soluzione process-local (research/admin only):

- `POST .../statistical-research/jobs` → HTTP 202 immediato + `job_id`
- Polling `GET .../jobs/{id}` ogni ~2s
- Risultati su `/tmp/cecchino_purchasability_research` (`*.result.json`, `*.summary.json`), scrittura atomica, strict JSON
- `ThreadPoolExecutor(max_workers=1)`; registry in-memory; **i job si perdono su restart/deploy**
- Nessuna migration, Redis, Celery, scrittura dati applicativi
- Versione statistica resta `cecchino_purchasability_statistical_research_v2a_2`
- GET sincrono conservato con header `X-Research-Execution-Mode: synchronous-debug` (Console/test)

## Fase 2A.2 — Timeout FE e gate indipendenza vs Book (`…_v2a_2`)

Correzioni post-benchmark Railway (~155,7s / 200 bootstrap vs timeout FE 90s):

- **Timeout dedicato** su `getPurchasabilityStatisticalResearch`: ≤200 → 300s, 201–500 → 600s, >500 → 1200s. Il default `adminGetJson` resta 90s per le altre API.
- **`classify_marginal`**: mai `positive_*` con ΔAUC ≤ 0; nuova classe `negative_but_uncertain`.
- **`comparison_role`**: `independent_vs_book` | `model_enrichment_diagnostic` | `rating_diagnostic`.
- **Book dependence**: VALUE_ADVANTAGE/EDGE (+ context/plus-rating) con `contains_book_information` e dipendenze deterministiche.
- **Readiness 2B**: conta separatamente positivi vs Book/Model/Rating; `phase_2b_candidate_construction` solo con evidenza indipendente vs Book + retained non vuoto; altrimenti residual research / stop / data quality.
- **`book_baseline_assessment`**: dominance descrittiva (`book_dominant` | …).
- **Invariants**: `readiness_invariant_errors` (es. `negative_delta_classified_positive`, `phase_2b_without_independent_feature`).
- Nessuna formula 0–100. Dataset `cecchino_purchasability_dataset_v1_1` invariato.

## Fase 2A.1 — Confronti paired e ROI discriminante (`…_v2a_1`)

Correzioni su v2a prima del benchmark Railway:

- **ROI coorte** (`cohort_full_coverage_roi`): descrittivo, identico tra candidati a stake 1 full-coverage — **non** usarlo per delta tra modelli.
- **ROI discriminante**: ranking OOF (`roi_top_10pct/20pct`, quintili, spread top–bottom).
- **`paired_oof_comparison`**: delta classificazione con segno “migliore = positivo”; CI bootstrap **paired** clusterizzato per fixture sulla differenza.
- **Stabilità fold**: `fold_signs` reali da delta AUC per fold test; soglie documentate (`DELTA_AUC_*`, `FOLD_NEUTRAL_ABS`).
- **Stabilità mercati**: Pass 1 per mercato → Pass 2 aggregato (`cross_market_stable` / `market_specific_signal` / …).
- **Rating**: confronti **prespecificati** (niente selezione best-spec su OOF).
- **`stable_seed`**: SHA-256, nessun `hash()` Python.
- Readiness 2B richiede evidenza paired reale (superseduta dal gate Book in v2a_2).

## Fase 2A — Ricerca statistica (`cecchino_purchasability_statistical_research_v2a`)

Read-only sulla coorte **settled_core** del dataset `cecchino_purchasability_dataset_v1_1` (non duplicato). Superseduta da v2a_1/v2a_2 per confronti paired e gate indipendenza.

### Coorte

`is_settled_core` + settlement won/lost/void + timestamp verified pre-KO + no leakage. Void: profitto 0, escluso dal Win Rate, incluso nel ROI. Blocking se `canonical_row_key` duplicata; feature-vector uguali su fixture diverse = OK.

### Dipendenza intra-fixture

Split e bootstrap **per fixture** (mai random row-split). Expanding temporal CV (≥3 fold se possibile, altrimenti `limited_temporal_span`).

### Feature engineering

Gap comparator/complement solo da payload pre-match. Hard redundancy: no `odds`+`raw_implied`; no `score`+(model+edge); Rating+componenti solo in `RATING_MARGINAL_DIAGNOSTIC`.

### Specs

`BOOK_BASELINE`, `MODEL_BASELINE`, `RATING_BASELINE`, `VALUE_*`, `CONTEXT_ONLY`, `VALUE_*_CONTEXT`, `RATING_CONTEXT`, `RATING_MARGINAL_DIAGNOSTIC`.

### Metriche

Logistic L2 + StandardScaler train-only; OOF AUC/Brier/LogLoss/calibration; ROI stake=1; bootstrap cluster fixture (FE default 200–500).

### Decisioni

`retain_independent_candidate` / `model_enrichment_only` / `benchmark_only` / `redundant_exclude` / `unstable_exclude` / `market_specific_candidate` / `negative_incremental_value` / `insufficient_evidence`. Rating: conclusioni tipizzate senza modificare la formula; non retain solo perché batte MODEL.

### API

- `GET .../purchasability/statistical-research`
- `.../markets|features|candidates`
- `.../export/{kind}` (10 export JSON-safe)

### Frontend

Sub-tab **Ricerca statistica — Fase 2A** sotto Acquistabilità su Segnali KPI (Audit conservato). Banner obbligatorio; nessuna colonna produttiva. Loading 2–4 min; no auto-load; keep results + “Nuovo calcolo in corso”.

### Limiti / Fase 2B

Nessuna formula 0–100. Readiness in `phase_2b_readiness.recommended_next_step` (gate vs Book). Benchmark Railway richiede `DATABASE_URL`; altrimenti `DATABASE_URL_missing`.

## Hotfix JSON-safe VIF (2026-07-18)

Causa HTTP 500 su `GET .../purchasability/audit`: `input_redundancy.vif` poteva contenere `Infinity` (R²≈1). Starlette `JSONResponse` rifiuta float non finiti (CORS nel browser è solo effetto collaterale).

Trattamento: VIF non finito → `null` + lista `infinite_variables`; `status = perfect_multicollinearity_detected`. Sanitizer `make_json_safe` sull’output audit/export JSON. Nessun cambiamento a coorti, correlazioni, readiness o dati.

## Fase 1.1 — Integrità temporale e dataset core (`cecchino_purchasability_audit_v1_1`)

Correzioni rispetto a v1:

### Timestamp canonico (non `updated_at`)

`resolve_purchasability_snapshot_timestamp(fixture)` priorità:

1. `kpi_panel_json.odds_meta.last_betfair_refresh_at` / `odds_updated_at` / `odds_fetched_at` → `verified_panel_odds_meta`
2. stessi campi su `odds_snapshot_json.odds_meta` → `verified_snapshot_odds_meta`
3. `odds_checked_at` → `verified_odds_checked_at`
4. `updated_at` → `generic_updated_at_fallback` (**non** entra in core; exclusion `snapshot_timestamp_not_verifiable`)

`updated_at` è un timestamp generico della riga Today e può essere aggiornato post-kickoff da risultati/stato.

`no_post_match_data_in_features = true` solo con timestamp pre-match **verificato**.

### Bookmaker vs odds_source

- `panel.bookmaker` = dict `{name, provider_bookmaker_id, provider_source}`
- `row.book_source` = `odds_source` per selezione
- Filtro query non sovrascrive la sorgente

### Doppia Chance

1X/X2/12 non sono mutuamente esclusivi → `book_probability_normalization_status = not_applicable_overlapping_outcomes`. Restano ammesse al core se modello completo.

### Core complete

Identity + mercato supported + timestamp verified pre-kickoff + odds>1 + model/advantage/edge/score/rating non null + book identificata + no leakage. Rating/Edge bassi o negativi ammessi. Book-only escluso.

### Coorti

`all_observed` / `pre_match` / `market_valid` / `model_complete` / `core_complete` / `settled_core` / `excluded`.

### Readiness

`markets_ready` richiede supported + core + settled + timestamp verificabile. Blocking strutturali → `resolve_data_gaps`.

## Fase 1 — Audit iniziale (`v1`, superseduta)

Sorgente `kpi_panel_json`; unità partita+mercato+selezione; Rating = benchmark; nessuna formula 0–100.

## Roadmap

1. Audit + dataset (1 / 1.1) — fatto
2. Statistica (2A) — fatto
3. Candidati Indice (2B)
4. Indice 0–100
5. Integrazione monitorata
