# Indice di Acquistabilità — Research

Modulo **indipendente** dal Rating. Risponde a: *quanto il valore individuato dal Cecchino è sostenuto dal contesto statistico e probabilistico della partita e dei mercati opposti?*

## Affidabilità storica vs Acquistabilità (FASE 1/5)

| Concetto | Definizione |
|----------|-------------|
| **AFFIDABILITÀ STORICA** | Misura il comportamento storico dello stesso mercato e della stessa fascia Rating (Win Rate, ROI, margine vs break-even, stabilità, numerosità). |
| **ACQUISTABILITÀ v1.1** | Misura quanto il valore individuato dal Cecchino è sostenuto dal contesto statistico e probabilistico della partita e dei mercati opposti (`balanced_geometric_v1_1`). |
| **ACQUISTABILITÀ v2** | Indice decisionale parallelo (`decision_quality_v2`): valore assoluto (Rating/Edge/Vantaggio) × qualità della decisione (dominanze, shift Book→Cecchino, contrasto opposto), con normalizzazione storica congelata. |
| **ACQUISTABILITÀ v3** | Candidato parallelo osservazionale (`fixed_discount_v3`): gate valore positivo → value score da Edge (scala fissa) scontato da penalità di qualità reali; nessuna media geometrica, nessun profilo storico. |

## Acquistabilità v3 — fixed_discount_v3 (2026-07-29)

Versione parallela osservazionale; **non** sostituisce v1.1 né v2; **non** è ancora operativa/promossa.

| Campo | Valore |
|-------|--------|
| Candidate | `cecchino_purchasability_v3_candidate_1` / `fixed_discount_v3` |
| Formula | `cecchino_purchasability_v3_fixed_discount_v1` |
| Audit | `cecchino_purchasability_v3_audit_v1` |
| Snapshot | `cecchino_purchasability_snapshot_v3` |
| Persistenza | `cecchino_output_json.purchasability_preview_v3` |
| Gate | Edge e vantaggio entrambi disponibili e > 0; fallimento → `score=null`, `class=null`, `status=not_applicable` |
| Value | `clamp(edge_pct / 50 × 100, 0, 100)` — sola base del valore |
| Quality | `100 − Σ penalità` (probabilità, opposto fair, divergenza fragile, ambiguità famiglia, quota derivata) |
| Finale | `score = ROUND_HALF_UP(value × quality / 100)` — **non** √(v×q) |
| Scale | fisse versionate; `historical_profile_used=false`, `fixed_scales_used=true` |
| Famiglie | `MATCH_WINNER_FT`, `GOALS_FT_2_5`, `DOUBLE_CHANCE` separate (AWAY ≠ X_TWO) |
| DC collegata | solo `linked_market_context` diagnostico (`used_in_score=false`) |
| Non usa | Rating/vantaggio come pesi, Score Acquisto, percentili, caps storici, profilo V2 |
| Promozione | richiede replay storico dedicato (STEP 3) prima di qualsiasi promozione |

### STEP 2 UI (2026-07-29)

- Pannello KPI: colonne **Acq. V2** e **Acq. V3** (badge «Candidato»); **V1.1 rimossa solo dalla UI** (calcolo/snapshot/API/audit legacy preservati).
- Popup `purchasability_v3`: ricostruzione completa (gate → value → penalità come sottrazioni → famiglia separata → opposto → linked diagnostico → `value×quality/100` → diagnostica).
- Nessun ROI storico V3 in cella (replay non ancora eseguito); sottotitolo «Non validato».
- V3 **non** dichiarata operativa, validata, migliore o sostitutiva della V2.

### STEP 2.1 — Audit hardening (2026-07-29)

- Nessuna modifica a formula, soglie, score, snapshot o motori V1.1/V2/V3.
- Versioni distinte in audit UI: `candidate_version` ≠ `formula_version` ≠ `audit_version` (no fallback candidate←formula).
- Metadata propagati dallo snapshot: `generated_at`, `source_snapshot_at`, flag pre-match/scale/parallelo (null → «—»).
- `family_comparison.market_rows`: Edge/gate/leader/rank reali per famiglia; FE non ricostruisce Edge (es. gap negativo DRAW ≠ Edge AWAY inventato).
- Gate reading semantici (`unsupported_market` / `unavailable_inputs` / failed / passed); input grezzi in `<details>` chiuso; reading non duplicata; quote derivate solo diagnostiche.
- Replay storico ancora **non** eseguito (STEP 3).

Motivazione: rispondere «quanto del valore Cecchino rimane dopo rischio e qualità», evitando il doppio conteggio di Rating/Edge/vantaggio e la normalizzazione storica V2.

## Acquistabilità v2 — decision_quality_v2 (2026-07-27)

Versione parallela; **non** sostituisce la validation baseline v1.1.

| Campo | Valore |
|-------|--------|
| Candidate | `cecchino_purchasability_v2_candidate_1` / `decision_quality_v2` |
| Contract / features / snapshot | `cecchino_purchasability_v2_contract` / `…_features_v1` / `…_snapshot_v2` |
| Persistenza | `cecchino_output_json.purchasability_preview_v2` |
| Norm profile | `cecchino_purchasability_v2_norm_profile_2026_07_26_v2`, cutoff `2026-07-26` |
| Selezione storica | solo `eligibility_status=eligible` + KPI rows + timestamp verificato + `snapshot_at < kickoff` |
| Non ammessi | `updated_at` come prova pre-match; post-kickoff; non eligible; KPI mancanti |
| Metodo | P95 nearest-rank su positivi/negativi; normalizzazione zero-anchored 0–100 |
| Scope | OUTCOMES, GOALS_FT_2_5, GOALS_HT_1_5 (+ sottogruppi probabilità) |
| Fallback | scope ≥15 → global → provisional versioned |
| Gruppi | Esiti (6) / Goal FT / Goal HT; probabilità 1X2 e DC separate |
| Opposti | HOME↔AWAY, DRAW→max fair HOME/AWAY, DC e OU mappati |
| Finale | √(F1×F2), ROUND_HALF_UP; gate valore positivo → score 0 (formula invariata) |
| Backfill | `python -m app.jobs.backfill_purchasability_v2` (manuale; dry-run default non scrivente; salta non verificabili) |
| History guard | `evaluate_purchasability_v2_historical_source` (condivisa profilo + backfill) |
| Cecchino Lab | escluso dalla costruzione del profilo; file Lab intatti |

## Acquistabilità — FASE 5/5 validazione prospettica (2026-07-19)

Coorte primaria da `purchasability_preview` persistito (verified + before kickoff). Tabella `cecchino_purchasability_evaluations`.

| Campo | Valore |
|-------|--------|
| Validation | `cecchino_purchasability_validation_v1` |
| Feature | `cecchino_purchasability_features_v1_1` |
| Policy | `cecchino_purchasability_promotion_policy_v1` |
| Coorti eligible | `prospective_persisted`, `legacy_persisted_backfill` |
| Esclusa dai gate | `legacy_derived_diagnostic` |
| Candidate | `candidate_2` resta `active_preview` |
| Max readiness | `eligible_for_manual_promotion` (mai auto) |
| `prima_data_teorica` | primo settled prospettico + 90 giorni |

Endpoint: `GET …/kpi-signals/purchasability-validation/{health,summary,rows,readiness,export.csv}` + jobs; admin sync.

Target residuale post-match: `signed_book_residual = y_win - fair_book`. Nessun Brier/LogLoss sullo score. Lab FE sottotab Validazione.

## Acquistabilità — FASE 4/5 KPI + snapshot `balanced_geometric_v1_1` (2026-07-19)

- **candidate_1** frozen (`python_round_legacy`); **candidate_2** attivo (`round_half_up`, UI + compact snapshot).
- Reading Phase1=0: priorità assoluta (favorevole / intermedia / limitata per Phase2).
- Persistenza: `cecchino_output_json["purchasability_preview"]` (`cecchino_purchasability_snapshot_v1`); nessuna migrazione.
- Fallback storico: `persisted_pre_match_snapshot` | `derived_read_only_from_stored_snapshot`.
- FE: colonna Acquistabilità solo numero 0–100; Affidabilità separata; Signals no.
- Validazione/promozione controllata: **FASE 5/5**.

## Acquistabilità — FASE 3/5 candidato `balanced_geometric_v1` (2026-07-19)

Candidato frozen Preview su feature Fase 2. Modulo `cecchino_purchasability_candidate.py`.

| Campo | Valore |
|-------|--------|
| Version | `cecchino_purchasability_v1_preview_candidate_1` (frozen; superseded) |
| Nome | `balanced_geometric_v1` |
| Endpoint | `GET …/purchasability-preview/candidate/{today_fixture_id}` |

**Phase 1 (valore):** input attivi `prob_cecchino`, `edge_pct`.  
`probability_strength = clamp(p×100)`; `edge_value = clamp(max(edge,0)/20×100)`;  
`phase_1 = √(probability_strength × edge_value)` (2 dp). Edge ≤0 → 0 + `no_positive_value_detected`.  
Rating / score_acquisto / Affidabilità storica: solo diagnostici, mai pesi.

**Phase 2 (qualità):** pesi configurati 0.40 / 0.30 / 0.20 / 0.10.  
**Finale:** `√(phase_1 × phase_2)` → intero 0–100 (v2: ROUND_HALF_UP).  
Classi: Molto Bassa / Bassa / Media / Alta / Molto Alta su soglie 20/40/60/80.

**Nota Lab storico:** nello export/dashboard Acquistabilità storica (`cecchino_lab_purchasability_export_v1`) uno score finale 0 con gate rejected **non** va etichettato «Molto Bassa»: usare «Bloccato dal gate» / `score_zero_semantics=gate_rejected`. `final_score` resta il valore persistito; `diagnostic_ungated_score` è solo diagnostica read-only (`√(phase_1×phase_2)`). Formula/pesi/gate operativi invariati.

## Acquistabilità — FASE 2/5 feature operative pre-match (2026-07-19)

Layer feature `cecchino_purchasability_features_v1` su snapshot `kpi_panel_json` (read-only).

- **phase_1_value**: input KPI riga (quote, prob, vantaggio, edge, score, rating) + `dependency_metadata`; score fase = null sul feature layer.
- **phase_2_quality**: opposizione, fair Book, model context, comparator_evidence, favorito/intensità, gap non penalizzante; score = null sul feature layer.
- **status** feature contract = `not_calculated`; **feature_status** = ready|partial|unavailable.
- Endpoint debug: `GET /api/cecchino/kpi-signals/purchasability-preview/features/{today_fixture_id}`
- Double Chance: fair/model da 1/X/2 normalizzato (non tre DC esclusive).
- Score 0–100 calcolato dal candidato Fase 3 (non dal feature layer).

In Fase 1/5 l’ex «Acquistabilità empirica» è ridenominata **Affidabilità storica**. Factory `not_calculated` resta senza score.

## Affidabilità storica v1.1 — Pannello KPI (`cecchino_historical_reliability_v1_1`)

Implementazione **produttiva read-only** nel Pannello KPI (colonna **Affidabilità** dopo Rating). Formula score **invariata** rispetto a `cecchino_purchasability_empirical_rating_v1_1`.

- **Modulo**: `backend/app/services/cecchino/cecchino_historical_reliability.py`
- **Shim legacy**: `cecchino_purchasability_empirical.py` (alias, nessuna seconda formula)
- **metric_kind**: `historical_reliability`
- **legacy_version**: `cecchino_purchasability_empirical_rating_v1_1`
- **Current rows**: esattamente le righe di `kpi_panel_json` / v2
- **Chiave item**: `today_fixture_id:market_key`
- **Coorte gerarchica**: locale ≥30 → `same_competition`; altrimenti globale ≥30 → `all_competitions_fallback`
- Endpoint canonico: `GET /api/cecchino/kpi-signals/historical-reliability`
- Endpoint legacy: `GET /api/cecchino/kpi-signals/purchasability-empirical` (`deprecated=true`)

## Acquistabilità empirica v1.1 — (rinominata; storico)

Sostituita semanticamente da Affidabilità storica v1.1. Stessa formula numerica.

## Acquistabilità empirica v1 — Pannello KPI (`…_empirical_rating_v1`)

Sostituita da v1.1 per copertura operativa. Logica storica: coorte solo locale, current da audit rows, whitelist mercati ridotta.

## Fase 2A.4.1 — Coorte DC, OOF comune, span temporale (`…_v2a_4_1`)

Correzione post-run Railway su `v2a_4` (conclusioni **non** definitive).

- **DC↔1X2 cross-market**: `cross_market_snapshot_key` senza `odds_source` (DC `betfair_raw_double_chance` ↔ 1X2 `betfair_raw_match_winner`); `same_market_sibling_key` resta per 1X2/OU.
- Fair audit: observed/settled/residual per source; diagnostica DC; mercati attesi/mancanti.
- **Maschera OOF comune**: baseline `BOOK_DIRECTION` = NaN fuori dai test fold; metriche confrontabili; `oof_evaluation_identity`.
- Economia paired su coorte OOF∩positive comune.
- Span: `limited_temporal_span` se &lt;90 giorni o &lt;3 mesi calendario → readiness `continue_data_collection` (niente stop definitivo su ~1 mese).
- Dataset `v1_1` e statistica `v2a_2` invariati; nessuna formula 0–100.

## Fase 2A.4 — Residual Reliability (`…_residual_reliability_v2a_4`)

Dopo Book dominance in 2A (`v2a_2`): non si ripete la corsa a battere il Book sull’esito.

- **Domanda**: quanto è affidabile il *disaccordo* Cecchino–Book (direzione/ampiezza/contesto)?
- Fair Book: 1X2/OU normalizzati; DC derivata da 1X2 normalizzato (`derived_double_chance_from_normalized_1x2`); raw implied solo secondario.
- Target: `direction_correct`, `signed_book_residual`; baseline `BOOK_DIRECTION_BASELINE` e `GAP_ONLY`.
- Decisivo: `GAP_RELIABILITY_CONTEXT` vs `GAP_ONLY`. Rating solo diagnostico.
- Job: stesso executor con `research_mode=phase2a_residual_reliability`.
- Nessuna formula 0–100.
- **Nota**: su Railway `v2a_4` le DC erano assenti per mismatch `odds_source`; vedi 2A.4.1.

## Fase 2A.3.2 — Coorte fold, dedup paired, Rating benchmark

Versione statistica invariata `cecchino_purchasability_statistical_research_v2a_2` (nessun cambio a OOF/bootstrap/metriche elementari).

- **Class balance fold** da `y_win` (1/0/None), non da `selection_won`/`selection_lost`; W/L/Void + WR (void esclusi dal denominatore); blocking `fold_class_balance_mismatch` se somma ≠ rows.
- **Dedup paired**: chiave `market|spec|vs|comparison_role`; i confronti Rating già presenti nel ciclo generale sono riusati (niente secondo bootstrap); summary `paired_comparisons_total/unique/duplicates_removed`; invariant `duplicate_paired_comparison_key`.
- **Rating = benchmark**: decisioni ammesse `benchmark_only` / `market_specific_benchmark` / `redundant_exclude` / `unstable_benchmark` / `insufficient_evidence`; mai candidate indipendente; positivi diagnostici non abilitano Fase 2B.
- Contatori post-dedup vs Book/Model/Rating per `comparison_role`; readiness tipicamente verso `phase_2a_residual_reliability_research`.

## Fase 2A.3.1 — Result completo FE + assi di classificazione

Dopo il job async 2A.3:

- Il FE carica prima lo **summary** (header/readiness), poi il **result** completo (`marginal_contribution`, `market_results`, `temporal_folds`).
- Se il result fallisce, lo summary resta visibile con avviso strutturato.
- Classificazione separata (metriche numeriche invariate, versione `v2a_2`):
  - `effect_classification` (direzione Δ+CI) → anche `classification` per compat
  - `temporal_classification` (solo fold)
  - `market_classification` (cross-market)
- `candidate_decision` esplicita (non lo status run `"ok"`).
- Elapsed UI in minuti/secondi.
- Prossima fase residua **non** avviata in questo step.

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
