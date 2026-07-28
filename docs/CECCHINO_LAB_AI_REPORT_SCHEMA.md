# Schema report AI â€” Cecchino Lab Historical Scan

Versione schema: `cecchino_lab_ai_report_v4`
Versione aggregazione: `cecchino_lab_analytics_agg_v2` (`analytics_aggregation_version`)

Le funzioni pure di aggregazione/pattern (`agg_bucket`, `finalize_bucket`, `build_combined_patterns`, â€¦) vivono in `historical_analytics_agg.py` e sono riusate dalla **dashboard run** senza rigenerare lo ZIP. Vedi `docs/CECCHINO_LAB_RUN_DASHBOARD.md`.

## Riconciliazione quote

Classificazione mutuamente esclusiva sui flag persistiti (`is_real_book_quote` / `is_derived_quote`):

- **real** â€” quota Bet365 reale
- **derived** â€” quota derivata consentita
- **unavailable** â€” nessuna quota reale/derivata

Deve sempre valere:

`real_quote_count + derived_quote_count + unavailable_quote_count = market_rows`

con `quote_count_reconciliation_ok: true` in `eligible_analysis.quote_reconciliation` e nei bucket finalizzati.
**Non** usare `profit = null` come proxy della qualitÃ  quota.

## Null vs zero (medie odds)

- Nessuna quota valida nel gruppo â†’ `average_real_odds` / `average_derived_odds` = **`null`**
- Quote valide (`finite` e `> 1.0`) â†’ media reale
- Zero non Ã¨ una quota valida; non mostrare `0.0` per dati non calcolati

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
- `analytics_aggregation_version = cecchino_lab_analytics_agg_v2`
- `source_git_commit` / `source_git_commit_source` / `source_revision_status`
- `run_scope` (`full` | `pilot` | `balanced_pilot`) / `is_partial_run` / `not_full_season_report`
- `pilot_strategy` / `eligible_per_competition`
- `performance_universe = eligible_core`
- `modules.goal_intensity = historical_partial_v1`
- `modules.purchasability = historical_bet365_progressive_v1`
- `modules.signals_matrix = imported_pure_models_A_F`
- `profit_policy.technical_sum_across_all_independent_market_rows.not_a_betting_strategy = true`
- Bookmaker operativo Today: **Betfair**; replay storico: **Bet365**

## Summary â€” eligible_analysis

- `quote_reconciliation` + `analytics_aggregation_version`
- Aggregazioni per mercato, segnale, modello Aâ€“F, fascia rating, fascia AcquistabilitÃ
- Pilastri IntensitÃ  (complete e parziali in copertura moduli)
- Balance / Equilibrio
- `coverage_distinctions` (outcome_base_rate â‰  performance Cecchino; conteggi probabilitÃ /fair quote/rating distinti)
- `technical_sum_across_all_independent_market_rows`: diagnostica tecnica, **non** strategia

## Pattern

Ogni pattern: `market_key`, `sample_size`, wins/losses, hit_rate, quote reali/derivate/unavailable, profitto/ROI reale e sintetico, campionati, concentrazione, `cross_competition_stability`, status, limitazioni. Nessuna conclusione prescrittiva.
`patterns_top` seleziona in modo deterministico i migliori/peggiori con sample size sufficiente; include `coverage_diagnostics`.
