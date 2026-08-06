# Schema report AI — Cecchino Lab Historical Scan

Versione schema: `cecchino_lab_ai_report_v4`
Versione aggregazione: `cecchino_lab_analytics_agg_v2_3` (`analytics_aggregation_version`)
Versione export segnali: `cecchino_lab_signal_export_v1` (`signal_export_schema_version`)
Acquistabilità ufficiale: **V3 replay** (`cecchino_lab_purchasability_v3_analytics_v2` / `…_export_v2`)
Export V2 Lab (`cecchino_lab_purchasability_export_v1`): legacy tecnico isolato, non usato dai percorsi ufficiali

## Segnali A–F / mercati — allineamento V3 (2026-08-06)

- Formula/consenso/audit: `cecchino_signals_matrix_v3_draw_dfg_decimal2` + `cecchino_signal_consensus_v1_min_two` + `cecchino_signal_explanations_v3`
- Module version Lab: `cecchino_lab_signals_af_v2_current_v3_consensus` — performance/settlement **acquired-only** (`is_acquired=true`); celle SI grezze solo diagnostica
- DRAW_PT: consenso ereditato da DRAW
- Mercati KPI/settlement nel report: **19** (`KPI_V2_ROW_DEFS`), non 14
- Contratto helper: `get_current_signal_contract()`; derived rebuild Lab può riallineare signals/market results senza full scan (`REBUILD_CECCHINO_LAB_DERIVED_V3`, provenance `derived_refresh`, no overwrite `source_git_commit`)

## STEP 3C.2 — V3 unica Acquistabilità ufficiale (2026-08-02)

- `module=purchasability` → ZIP V3 ufficiale (`cecchino-run-{run_id}-purchasability-v3.zip`)
- `ai_summary.purchasability` → summary/analytics V3 + metadata replay; se assente → `status=unavailable`
- competition / full_archive: `legacy_purchasability_excluded=true`; nessun `purchasability_compact.jsonl` V2
- Istruzioni AI: usare esclusivamente V3; non cercare V1.1/V2; gate failed ≠ score 0

## STEP 3C.1 — Export Replay Acquistabilità V3 (autonomo)

Schema analytics: `cecchino_lab_purchasability_v3_analytics_v1` → **v2 in 3C.2**
Schema export: `cecchino_lab_purchasability_v3_export_v1` → **v2 in 3C.2**

ZIP dedicato al replay V3 (`mode=analysis` consigliato per ChatGPT; `full_archive` opzionale). Dal STEP 3C.2 è la sorgente ufficiale anche per Sintesi/Dettaglio Run.

File primari analysis: `summary.json`, `reconciliation.json`, `replay_results_compact.jsonl`, `family_decisions.jsonl`, `AI_INSTRUCTIONS.md`, `ANALYSIS_CHECKLIST.md`, ...
Full: + `replay_results_full.jsonl`.
Flag: `formula_recomputed=false`, `performance_real_and_synthetic_separated=true`.

## STEP 3A — Preflight replay V3 (non è un export report)

Il preflight `cecchino_lab_purchasability_v3_replay_preflight_v1` **non** entra nello ZIP report AI e **non** modifica `purchasability_compact.jsonl` / export V2. Serve solo a certificare la riusabilità degli input congelati prima di STEP 3B (replay isolato). Anti-leakage: risultati/settlement fuori dalla formula.

Le funzioni pure di aggregazione/pattern (`agg_bucket`, `finalize_bucket`, `build_combined_patterns`, …) vivono in `historical_analytics_agg.py` e sono riusate dalla **dashboard run** senza rigenerare lo ZIP. Vedi `docs/CECCHINO_LAB_RUN_DASHBOARD.md`.

## Acquistabilità storica — export compatto

Modulo read-only `historical_purchasability_export.py` (nessun ricalcolo formula/pesi/gate; `formula_recomputed=false`).

| File | Ruolo |
|---|---|
| `purchasability_compact.jsonl` | **Canonico** — 1 riga = `snapshot_id × market_key`; `purchasability_evaluation_id=run:{id}:snapshot:{id}:market:{mk}` |
| `purchasability_decisions.jsonl` | Scelta relativa diagnostica per famiglia (`ONE_X_TWO_REAL` / `GOALS_FT_2_5_REAL` / `DOUBLE_CHANCE_DERIVED`) |
| `purchasability_drift.json` | Drift mensile/campionato (sample size, gate, score≥80, profile hash) |
| `purchasability_profiles.jsonl` | Profili normalizzazione deduplicati per hash |
| `purchasability.jsonl` | Legacy full — solo in `full_archive` |

- Score 0 con `gate_status` rejected ≠ fascia «Molto Bassa»: `score_zero_semantics=gate_rejected`, UI «Bloccato dal gate»
- `final_score` / `persisted_score` = valore congelato; `diagnostic_ungated_score` = `sqrt(phase_1×phase_2)` solo se ricostruibile (read-only)
- Bande numeriche (`0-19`…) applicate principalmente a `gate_status=accepted`; altrimenti `gate_rejected`
- Join MarketResult: `matched` / `missing_market_result` / `ambiguous_market_result` / `invalid_market_key`
- Summary: sezione `purchasability_export` + riconciliazione ID unici
- Decisioni e soglie: `diagnostic_only=true`, `discovered_on_same_season=true`, `not_a_betting_strategy=true`

## Segnali A–F: opportunità vs celle

Due livelli distinti (nessuna modifica a pesi/soglie/formule):

| Livello | File | Granularità | Uso |
|---|---|---|---|
| **Opportunità** (canonico) | `signal_opportunities.jsonl` | `run + snapshot + model_key + market_key` | Performance, ROI, overlap, consenso |
| **Cella** (legacy) | `signal_models.jsonl` | una riga per cella SI attiva | Diagnostica; `do_not_sum_as_independent_opportunities=true` |

- `opportunity_id` deterministico: `run:{id}:snapshot:{id}:model:{k}:market:{mk}`
- `with_signal_active` nei riepiloghi modello = **alias deprecato** di `model_active_opportunity_count` (non overlap con F)
- Sovrapposizione con F: `overlap_with_current_model_F_*` / `model_overlap_matrix`
- Join a `CecchinoLabHistoricalMarketResult` per `prob_cecchino` / `quota_cecchino` / Rating / Acquistabilità per mercato (`market_join_status`)
- Acquistabilità da `purchasability_compatibility_json.markets[]` per `market_key` (mai score partita generico)
- F = modello corrente, non automaticamente il migliore
- Nessuna probabilità/quota Cecchino inventata da Bet365

Vedi anche `model_overlap.json`, `signal_export_reconciliation`, `market_join_diagnostics`, `current_model_F_diagnostics`.

## Riconciliazione quote

Classificazione mutuamente esclusiva sui flag persistiti (`is_real_book_quote` / `is_derived_quote`):

- **real** â€” quota Bet365 reale
- **derived** â€” quota derivata consentita
- **unavailable** â€” nessuna quota reale/derivata

Deve sempre valere:

`real_quote_count + derived_quote_count + unavailable_quote_count = market_rows`

con `quote_count_reconciliation_ok: true` in `eligible_analysis.quote_reconciliation` e nei bucket finalizzati.
**Non** usare `profit = null` come proxy della qualitÃ  quota.

## Null vs zero (medie odds e profit)

- Nessuna quota nel gruppo (`*_quote_count == 0`) → `*_profit_1u` / `*_roi_pct` / `average_*_odds` = **`null`**
- Quote presenti → numerici (incluso profitto economico **0**)
- Zero non è una quota valida; non mostrare `0.0` per dati non calcolati

## Contatori Cecchino distinti

| Campo | Fonte DB |
|-------|----------|
| `with_cecchino_probability` | `prob_cecchino` |
| `with_cecchino_fair_quote` | `quota_cecchino` |
| `with_rating` | `rating` |

`with_cecchino_quote` Ã¨ alias compat di `with_cecchino_fair_quote` (non inventare fair quote dalla sola probabilitÃ ).

## Pattern market-specific

Ogni pattern di performance include obbligatoriamente `market_key` in `conditions` / `pattern_id`.
Non aggregare HOME+DRAW+AWAY+OU nello stesso pattern.

### Soglie (su quote reali)

| Status | Quote reali |
|--------|-------------|
| `small_sample` | &lt; 30 |
| `exploratory_only` | 30â€“99 |
| `descriptive_only` | 100â€“199 (o gate candidatura falliti) |
| `candidate_for_validation` | â‰¥ 200 + market_key + â‰¥3 campionati + main share â‰¤60% + non concentrato nel tempo + condizioni informative |

### StabilitÃ  cross-competition

Campo `cross_competition_stability`:

`insufficient_evidence` | `concentrated` | `inconsistent` | `directionally_consistent` | `stable_candidate`

`stable_candidate` richiede â‰¥200 reali, â‰¥5 campionati, main â‰¤40%, â‰¥65% stessa direzione, metÃ  stagione coerenti, nessun periodo dominante.
Non usare il termine Â«stabileÂ» fuori da `stable_candidate`.

### Diagnostica assenze dati

`no_rating` / `no_purch` / `signal_off` / moduli mancanti â†’ `diagnostic_patterns` / `coverage_diagnostics`, **non** candidati positivi/negativi.
`signal_off` puÃ² essere controllo solo a confronto esplicito con `signal_on` sullo stesso mercato.

## ModalitÃ  export

| Mode | Contenuto |
|------|-----------|
| `ai_summary` (consigliata) | Manifest, report_index, summary, data_quality, eligibility, module_coverage, patterns_top, istruzioni â€” **senza** JSONL partita-per-partita |
| `competition` | Come sintesi + JSONL compatti filtrati per campionato |
| `module` | Un modulo: `markets` \| `signals` \| `goal_intensity` \| `purchasability` \| `balance` |
| `full_archive` | Archivio tecnico completo (JSONL interi + patterns) â€” non necessario per la prima analisi ChatGPT |

Generazione: `SpooledTemporaryFile` + JSONL riga-per-riga + streaming HTTP (lâ€™archivio non viene costruito come unico blob in RAM).

## Contenuto ZIP (per mode)

| File | ai_summary | competition | module | full_archive |
|------|------------|-------------|--------|--------------|
| `report_index.json` | sÃ¬ | sÃ¬ | sÃ¬ | sÃ¬ |
| `manifest.json` | sÃ¬ | sÃ¬ | sÃ¬ | sÃ¬ |
| `summary.json` | sÃ¬ | sÃ¬ | sÃ¬ | sÃ¬ |
| `data_quality.json` | sÃ¬ | sÃ¬ | â€” | sÃ¬ |
| `eligibility.json` | sÃ¬ | sÃ¬ | â€” | sÃ¬ |
| `module_coverage.json` | sÃ¬ | sÃ¬ | sÃ¬ | sÃ¬ |
| `patterns_top.json` | sÃ¬ | sÃ¬ | â€” | â€” |
| `patterns.json` | â€” | sÃ¬ | â€” | sÃ¬ |
| `matches_compact.jsonl` | â€” | sÃ¬ | â€” | â€” |
| `matches.jsonl` | â€” | â€” | â€” | sÃ¬ |
| JSONL modulo | â€” | selettivi | uno | tutti |
| `AI_INSTRUCTIONS.md` / `SCHEMA.md` | sÃ¬ | sÃ¬ | sÃ¬ | sÃ¬ |

## Manifest (campi chiave)

- `report_schema_version = cecchino_lab_ai_report_v4`
- `analytics_aggregation_version = cecchino_lab_analytics_agg_v2_2`
- `signal_export_schema_version = cecchino_lab_signal_export_v1`
- `scan_source_git_commit*` (snapshot congelati) vs `report_generator_git_commit*` (codice a generazione)
- alias legacy: `source_git_commit*` = scan
- `run_scope` (`full` | `pilot` | `balanced_pilot`) / `is_partial_run` / `not_full_season_report`
- `pilot_strategy` / `eligible_per_competition`
- `performance_universe = eligible_core`
- `modules.goal_intensity = historical_partial_v1`
- `modules.purchasability = historical_bet365_progressive_v1`
- `modules.signals_matrix = imported_pure_models_A_F` (runtime Lab: `cecchino_lab_signals_af_v2_current_v3_consensus`, acquired-only)
- `profit_policy.technical_sum_across_all_independent_market_rows.not_a_betting_strategy = true`
- Bookmaker operativo Today: **Betfair**; replay storico: **Bet365**

## Summary — eligible_analysis

- `quote_reconciliation` + `analytics_aggregation_version`
- Primarie: `rating_by_market`, `purchasability_by_market` (confrontare fasce solo nello stesso mercato)
- Diagnostiche: `rating_global_distribution_diagnostic`, `purchasability_global_distribution_diagnostic`
- Fascia Rating: `0-9`…`90-99`, poi **`100`** esclusivo (mai `100-109`)
- Aggregazioni per mercato, segnale, modello A–F; pilastri Intensità; Balance
- `coverage_distinctions` (outcome_base_rate ≠ performance Cecchino)
- `technical_sum_across_all_independent_market_rows`: diagnostica tecnica, **non** strategia

## markets.jsonl (competition / module / full_archive)

Identity + kickoff storico + scores HT/FT + metriche mercato. Compatto: senza raw moduli/picchetti/contexts.
`ai_summary` **non** include `markets.jsonl` completo.

## Pattern

Ogni pattern: `market_key`, `sample_size`, wins/losses, hit_rate, quote reali/derivate/unavailable, profitto/ROI reale e sintetico, campionati, concentrazione, `cross_competition_stability`, status, limitazioni. Nessuna conclusione prescrittiva.
`patterns_top` seleziona in modo deterministico i migliori/peggiori con sample size sufficiente; include `coverage_diagnostics`.
