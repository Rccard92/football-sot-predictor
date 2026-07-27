# Schema report AI — Cecchino Lab Historical Scan

Versione schema: `cecchino_lab_ai_report_v2`

## Contenuto ZIP

| File | Descrizione |
|------|-------------|
| `manifest.json` | Metadati run, scope full/pilot, policy, versioni, Betfair operativo / Bet365 storico |
| `summary.json` | Sezioni `eligible_analysis`, `excluded_diagnostics`, `errors`, `data_coverage` |
| `data_quality.json` | Output preflight stagione |
| `eligibility.json` | Conteggi stati eleggibilità |
| `module_coverage.json` | Copertura moduli + limiti Intensità/Acquistabilità |
| `matches.jsonl` | Una riga JSON per partita (pre-match separato da `result_after_lock`) |
| `markets.jsonl` | Una riga per partita×mercato **solo eligible_core** |
| `patterns.json` | Pattern combinati con soglie sample |
| `AI_INSTRUCTIONS.md` | Istruzioni per ChatGPT |
| `SCHEMA.md` | Schema sintetico |

## Manifest (campi chiave)

- `operational_today_bookmaker = "Betfair"`
- `historical_replay_bookmaker = "Bet365"`
- `operational_today_modified = false`
- `profit_policy.do_not_sum = true`
- `performance_universe = "eligible_core_only"`
- `run_scope` / `is_partial_run` / `max_matches`
- `do_not_propose_formula_changes = true`
- Intensità/Acquistabilità: `raw_features_export_only` / `inputs_export_only`

## Summary JSON

### `eligible_analysis`

Unico insieme per hit rate, profitto, ROI, fasce rating, pattern, segnali.

Aggregazioni tipiche: mercato, campionato, fascia rating/edge, quote reale/derivata, famiglia/modello/conteggio segnali, classi Balance, closing/pre, campione storico.

`coverage_distinctions` separa:

- `outcome_base_rate` (frequenza naturale — **non** “performance del Cecchino”)
- mercati con quota Cecchino / rating / segnale attivo / Bet365 reale / derivata

### `excluded_diagnostics`

Diagnostica partite non `eligible_core` (motivi, sample, settlement zero mercati).

### `errors` / `data_coverage`

Errori di processing e copertura run (incluso flag pilota).

## Matches JSONL

Il blocco pre-match **non** include il risultato. Il risultato è in `result_after_lock` dopo `pre_match_locked_at` / hash.
Include `settlement_status` (`settled` | `excluded` | `error`).

## Markets JSONL

Solo partite `eligible_core`. Campi aggiuntivi:

- `eligibility_status`, `competition_name` (dallo snapshot)
- `signal_active`, `signal_family`, `active_signal_count`, `signal_sources_json`
- `profit_1u_real`, `profit_1u_synthetic`, `profit_category`

## Patterns JSON

Pattern combinati iniziali:

- mercato + fascia rating
- mercato + segnale
- mercato + fascia rating + segnale
- mercato + classe Balance
- mercato + fascia rating + classe Balance
- campionato + mercato + fascia rating
- campionato + mercato + segnale

Ogni pattern: `sample_size`, wins/losses, `hit_rate`, real/derived quote counts, real/synthetic profit+ROI, `competitions_count`, stabilità per campionato, `status`.

Soglie status:

- `<30` → `small_sample`
- `30–99` → `descriptive_only`
- `≥100` → `candidate_for_review` solo se non dipende da un unico campionato / poche partite

Nessuna proposta automatica di modifica formule.
