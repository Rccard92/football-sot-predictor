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
   - `POST /api/admin/cecchino-lab/historical-scans` con:
     - `confirm: "RUN_CECCHINO_LAB_HISTORICAL_SCAN"`
     - `max_matches` opzionale (`null`/assente = stagione completa; es. `200` = pilota)

### Modalità pilota vs completa

| Modalità | Body | UI |
|----------|------|-----|
| Pilota | `max_matches: 200` | “Scansione pilota — prime 200 partite” |
| Completa | `max_matches: null` | “Scansione completa” |

Il pilota rispetta l’ordine cronologico della pipeline, produce ZIP/statistiche, è marcato `is_partial_run` / `run_scope=pilot` e **non** va confuso con il report stagione completa. Non modifica dataset o partite storiche.

Nessun avvio automatico su deploy/startup/migrazione.

## Pipeline per partita

1. Contesti pre-match (anti-leakage)
2. Cecchino + goal markets + KPI Bet365 + segnali + Balance + feature Intensità/Acquistabilità
3. Eleggibilità storica
4. Freeze snapshot + hash SHA-256 pre-match
5. Collegamento risultato FT/HT
6. Settlement mercati **solo se** `core_eligible=true`

### Partite escluse

- Snapshot + risultato + motivo di esclusione salvati
- `settlement_status = "excluded"`
- `settlement_summary.markets_analyzed = 0`
- **Nessuna** riga mercato nelle metriche di performance
- Diagnostica separata nel report (`excluded_diagnostics`)

## Policy quote Bet365

1X2 / O/U 2.5: trio/coppia **closing** completa, altrimenti **pre** completa; mai mix.
DC 1X/X2/12: derivate fair normalizzate da 1X2 (`normalized_fair_probability_from_bet365_1x2`).
Non derivabili: O1.5, U3.5, mercati HT da FT.

## Anti-leakage e hash pre-match

Per competizione, solo partite con kickoff strettamente precedente. Stesso kickoff escluso.

L’hash copre l’analisi congelata: identity, input snapshot, picchetti, final Cecchino, goal markets, KPI Bet365, matrice segnali, Balance v5, feature/compat Intensità e Acquistabilità, quote Bet365 + provenienza, versioni moduli, stato eleggibilità.

**Non** include: FT, HT, esito, profitto, settlement.

## Segnali

Estrazione dalla matrice canonica: `row["key"]` + `row["signals"][modello] = "SI"|"NO"`.
Mapping famiglia → modello/cella → mercato riusato da `cecchino_signal_target_mapping` (nessuna nuova mappa).
Su ogni mercato settled: `signal_active`, `signal_sources_json` (family, count, sources).

## Eleggibilità storica

Gate separato (no Betfair). Stati: `eligible_core`, `excluded_insufficient_history`, …
Disponibilità quote registrata separatamente dalla core eleggibilità.
Hit rate / profitto / ROI / fasce rating / pattern / confronti campionato / analisi segnali: **solo** `eligible_core`.

## Intensità Goal / Acquistabilità

- Intensità: export feature raw pre-match (`raw_features_available`); `v5_score_not_executed=true`; no xG inventato; no bundle prospettico produttivo.
- Acquistabilità: export input per mercato (`inputs_available`); `final_score_not_executed=true`; no profilo Betfair; no falso score finale Bet365.
- La prima scansione può **studiare le feature**, non ancora validare i punteggi finali.

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
- Intensità Goal / Acquistabilità: feature/input only, non punteggi finali.
