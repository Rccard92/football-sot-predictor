# Indice di Acquistabilità — Research

Modulo **indipendente** dal Rating. Risponde a: *quanto è statisticamente affidabile acquistare il valore individuato dal modello?*

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

1. Audit + dataset (1 / 1.1)
2. Statistica
3. Indice 0–100
4. Integrazione monitorata
