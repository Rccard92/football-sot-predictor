# Indice di Acquistabilità — Research

Modulo **indipendente** dal Rating. Risponde a: *quanto è statisticamente affidabile acquistare il valore individuato dal modello?*

## Fase 2A.1 — Confronti paired e ROI discriminante (`…_v2a_1`)

Correzioni su v2a prima del benchmark Railway:

- **ROI coorte** (`cohort_full_coverage_roi`): descrittivo, identico tra candidati a stake 1 full-coverage — **non** usarlo per delta tra modelli.
- **ROI discriminante**: ranking OOF (`roi_top_10pct/20pct`, quintili, spread top–bottom).
- **`paired_oof_comparison`**: delta classificazione con segno “migliore = positivo”; CI bootstrap **paired** clusterizzato per fixture sulla differenza.
- **Stabilità fold**: `fold_signs` reali da delta AUC per fold test; soglie documentate (`DELTA_AUC_*`, `FOLD_NEUTRAL_ABS`).
- **Stabilità mercati**: Pass 1 per mercato → Pass 2 aggregato (`cross_market_stable` / `market_specific_signal` / …).
- **Rating**: confronti **prespecificati** (niente selezione best-spec su OOF).
- **`stable_seed`**: SHA-256, nessun `hash()` Python.
- Readiness 2B richiede evidenza paired reale.

## Fase 2A — Ricerca statistica (`cecchino_purchasability_statistical_research_v2a`)

Read-only sulla coorte **settled_core** del dataset `cecchino_purchasability_dataset_v1_1` (non duplicato). Superseduta da v2a_1 per confronti paired.

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

`retain_candidate` / `benchmark_only` / `redundant_exclude` / `unstable_exclude` / `market_specific_candidate` / `insufficient_evidence`. Rating: conclusioni tipizzate senza modificare la formula.

### API

- `GET .../purchasability/statistical-research`
- `.../markets|features|candidates`
- `.../export/{kind}` (10 export JSON-safe)

### Frontend

Sub-tab **Ricerca statistica — Fase 2A** sotto Acquistabilità su Segnali KPI (Audit conservato). Banner obbligatorio; nessuna colonna produttiva.

### Limiti / Fase 2B

Nessuna formula 0–100. Readiness in `phase_2b_readiness.recommended_next_step`. Benchmark Railway richiede `DATABASE_URL`; altrimenti `DATABASE_URL_missing`.

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
