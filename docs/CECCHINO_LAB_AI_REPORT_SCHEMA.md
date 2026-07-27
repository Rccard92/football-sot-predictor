# Schema report AI — Cecchino Lab Historical Scan

Versione schema: `cecchino_lab_ai_report_v4`

## Modalità export

| Mode | Contenuto |
|------|-----------|
| `ai_summary` (consigliata) | Manifest, report_index, summary, data_quality, eligibility, module_coverage, patterns_top, istruzioni — **senza** JSONL partita-per-partita |
| `competition` | Come sintesi + JSONL compatti filtrati per campionato |
| `module` | Un modulo: `markets` \| `signals` \| `goal_intensity` \| `purchasability` \| `balance` |
| `full_archive` | Archivio tecnico completo (JSONL interi + patterns) — non necessario per la prima analisi ChatGPT |

Generazione: `SpooledTemporaryFile` + JSONL riga-per-riga + streaming HTTP (l’archivio non viene costruito come unico blob in RAM).

## Contenuto ZIP (per mode)

| File | ai_summary | competition | module | full_archive |
|------|------------|-------------|--------|--------------|
| `report_index.json` | sì | sì | sì | sì |
| `manifest.json` | sì | sì | sì | sì |
| `summary.json` | sì | sì | sì | sì |
| `data_quality.json` | sì | sì | — | sì |
| `eligibility.json` | sì | sì | — | sì |
| `module_coverage.json` | sì | sì | sì | sì |
| `patterns_top.json` | sì | sì | — | — |
| `patterns.json` | — | sì | — | sì |
| `matches_compact.jsonl` | — | sì | — | — |
| `matches.jsonl` | — | — | — | sì |
| JSONL modulo | — | selettivi | uno | tutti |
| `AI_INSTRUCTIONS.md` / `SCHEMA.md` | sì | sì | sì | sì |

## Manifest (campi chiave)

- `report_schema_version = cecchino_lab_ai_report_v4`
- `source_git_commit` / `source_git_commit_source` / `source_revision_status`
- `run_scope` (`full` | `pilot` | `balanced_pilot`) / `is_partial_run` / `not_full_season_report`
- `pilot_strategy` / `eligible_per_competition`
- `performance_universe = eligible_core`
- `modules.goal_intensity = historical_partial_v1`
- `modules.purchasability = historical_bet365_progressive_v1`
- `modules.signals_matrix = imported_pure_models_A_F`
- `profit_policy.technical_sum_across_all_independent_market_rows.not_a_betting_strategy = true`
- Bookmaker operativo Today: **Betfair**; replay storico: **Bet365**

## Summary — eligible_analysis

- Aggregazioni per mercato, segnale, modello A–F, fascia rating, fascia Acquistabilità
- Pilastri Intensità (complete e parziali in copertura moduli)
- Balance / Equilibrio
- `coverage_distinctions` (outcome_base_rate ≠ performance Cecchino)
- `technical_sum_across_all_independent_market_rows`: diagnostica tecnica, **non** strategia

## Pattern

Ogni pattern: `sample_size`, wins/losses, hit_rate, quote reali/derivate, profitto/ROI reale e sintetico, campionati, concentrazione, stabilità, status, limitazioni. Nessuna conclusione prescrittiva.
`patterns_top` seleziona in modo deterministico i migliori/peggiori con sample size sufficiente.

## Universe

Metriche di performance: **solo** `eligible_core`. Moduli osservazionali parziali **non** escludono la partita. Escluse solo in diagnostica.
