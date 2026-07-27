# Schema report AI — Cecchino Lab Historical Scan

Versione schema: `cecchino_lab_ai_report_v1`

## Contenuto ZIP

| File | Descrizione |
|------|-------------|
| `manifest.json` | Metadati run, policy, versioni, Betfair operativo / Bet365 storico |
| `summary.json` | Aggregazioni per campionato, mercato, quote type, rating, edge, … |
| `data_quality.json` | Output preflight stagione |
| `eligibility.json` | Conteggi stati eleggibilità |
| `module_coverage.json` | Copertura moduli |
| `matches.jsonl` | Una riga JSON per partita (pre-match separato da `result_after_lock`) |
| `markets.jsonl` | Una riga per partita×mercato |
| `patterns.json` | Pattern descrittivi non prescrittivi |
| `AI_INSTRUCTIONS.md` | Istruzioni per ChatGPT |
| `SCHEMA.md` | Schema sintetico |

## Manifest (campi chiave)

- `operational_today_bookmaker = "Betfair"`
- `historical_replay_bookmaker = "Bet365"`
- `operational_today_modified = false`
- `profit_policy.do_not_sum = true`

## Matches JSONL

Il blocco pre-match **non** include il risultato. Il risultato è in `result_after_lock` dopo `pre_match_locked_at` / hash.

## Markets JSONL

Campi profitto separati: `profit_1u_real`, `profit_1u_synthetic`, `profit_category`.
