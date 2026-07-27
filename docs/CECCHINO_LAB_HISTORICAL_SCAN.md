# Cecchino Lab — Scansione storica (replay pre-match)

## Isolamento

- Solo Cecchino Lab (`cecchino_lab_*`).
- **Non** modifica Cecchino Today, formule, gate Betfair, snapshot operativi.
- Bookmaker operativo Today: **Betfair** (invariato).
- Bookmaker replay storico: **Bet365** (CSV Football-Data).

## Avvio

1. UI: tab **Scansioni storiche** in `/cecchino-lab`
2. Oppure API:
   - `POST /api/admin/cecchino-lab/historical-scans/preflight` `{ "season_label": "2021/2022" }`
   - `POST /api/admin/cecchino-lab/historical-scans` con `confirm: "RUN_CECCHINO_LAB_HISTORICAL_SCAN"`

Nessun avvio automatico su deploy/startup/migrazione.

## Policy quote Bet365

1X2 / O/U 2.5: trio/coppia **closing** completa, altrimenti **pre** completa; mai mix.
DC 1X/X2/12: derivate fair normalizzate da 1X2 (`normalized_fair_probability_from_bet365_1x2`).
Non derivabili: O1.5, U3.5, mercati HT da FT.

## Anti-leakage

Per competizione, solo partite con kickoff strettamente precedente. Stesso kickoff escluso. Risultato FT/HT collegato solo dopo SHA-256 lock del payload pre-match.

## Eleggibilità storica

Gate separato (no Betfair). Stati: `eligible_core`, `excluded_insufficient_history`, …
Disponibilità quote registrata separatamente dalla core eleggibilità.

## ROI

- `profit_1u_real` / real ROI: solo quote Bet365 reali
- `profit_1u_synthetic` / synthetic ROI: solo derivate
- Non sommare i due

## Resume / cancel

`POST .../historical-scans/{id}/resume` e `.../cancel`. Lock: un solo run attivo per stagione.

## Report AI

`GET /api/cecchino-lab/historical-scans/{id}/report` → ZIP (vedi `CECCHINO_LAB_AI_REPORT_SCHEMA.md`).

## Limiti prima stagione (2021/2022)

- Nessuno storico da stagioni precedenti nella pipeline.
- Prime giornate escluse per campione insufficiente.
- Intensità Goal / Acquistabilità: solo compatibility, non bundle operativo.
