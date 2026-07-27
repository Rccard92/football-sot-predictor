# Schema report AI — Cecchino Lab Historical Scan

Versione schema: `cecchino_lab_ai_report_v3`

## Contenuto ZIP

| File | Descrizione |
|------|-------------|
| `manifest.json` | Metadati run, scope, revision git, policy, versioni, Betfair/Bet365 |
| `summary.json` | `eligible_analysis`, aggregazioni GI/purch/A–F, `excluded_diagnostics`, `errors`, `data_coverage` |
| `data_quality.json` | Preflight stagione |
| `eligibility.json` | Conteggi eleggibilità |
| `module_coverage.json` | Copertura + parity Intensità/Acquistabilità/segnali |
| `matches.jsonl` | Una riga per partita |
| `markets.jsonl` | Partita×mercato **solo eligible_core** |
| `signal_models.jsonl` | Partita × modello A–F × segnale attivo |
| `goal_intensity.jsonl` | Pilastri Intensità per eligible_core |
| `purchasability.jsonl` | Partita × mercato Acquistabilità storica |
| `patterns.json` | Pattern combinati (rating×purch×intensità×modello×segnale×Balance) |
| `AI_INSTRUCTIONS.md` | Istruzioni ChatGPT |
| `SCHEMA.md` | Schema sintetico |

## Manifest (campi chiave)

- `report_schema_version = cecchino_lab_ai_report_v3`
- `source_git_commit` / `source_git_commit_source` / `source_revision_status`
- `run_scope` (`full` | `pilot` | `balanced_pilot`) / `is_partial_run` / `not_full_season_report`
- `pilot_strategy` / `eligible_per_competition`
- `modules.goal_intensity = historical_partial_v1`
- `modules.purchasability = historical_bet365_progressive_v1`
- `modules.signals_matrix = imported_pure_models_A_F`
- `modules_parity`
- `profit_policy.technical_sum_across_all_independent_market_rows.not_a_betting_strategy = true`
- `operational_today_bookmaker = Betfair`, `historical_replay_bookmaker = Bet365`

## Summary — eligible_analysis

- Aggregazioni per mercato, segnale, modello A–F, fascia rating, fascia Acquistabilità (0–19…80–100 e decili 0–9…100)
- Pilastri Intensità per classe
- `coverage_distinctions` (outcome_base_rate ≠ performance Cecchino)
- `technical_sum_across_all_independent_market_rows`: diagnostica tecnica, **non** strategia

## Pattern

Ogni pattern: `sample_size`, wins/losses, hit_rate, quote reali/derivate, profitto/ROI reale e sintetico, campionati, concentrazione, stabilità, status, limitazioni. Nessuna conclusione prescrittiva.

## Universe

Metriche di performance: **solo** `eligible_core`. Escluse solo in diagnostica.
