# Cecchino

Modulo **parallelo** al modello SOT per stimare quote 1X2 da picchetti tecnici (record Vittorie/Pareggi/Sconfitte). Non modifica né legge `team_sot_predictions`, v2.0 o v2.1.

## Stato

| Campo | Valore |
|-------|--------|
| Versione | `cecchino_v0_1_excel_parity` |
| Fase | 1 — parità Excel base (picchetti 1–5) |
| Separazione SOT | Totale — engine, API, UI e tabella dedicati |

## Obiettivo

Replicare online la logica del foglio **CECCHINO** di `AutomazioneCecchino.xlsm`:

1. Picchetto tecnico casa/trasferta
2. Picchetto tecnico somma partite totali
3. Picchetto stato di forma ultime 5 casa/fuori
4. Picchetto stato di forma ultime 6 totali
5. Quota matematica finale Cecchino (media ponderata)

Sezioni **non ancora implementate** (solo placeholder in `output_json`):

- Matrice segnali SI/NO → `pending_formula_extraction`
- Indice affidabilità → `not_implemented_yet`
- Confronto quota matematica vs bookmaker → `not_implemented_yet`
- Movimento quota / rumors → non presente in v0.1

## Formule (v0.1)

Per ogni picchetto, dati `home_context` e `away_context` (wins, draws, losses):

```
total_matches = sum(home) + sum(away)
prob_1 = (home.wins + away.losses) / total_matches
prob_x = (home.draws + away.draws) / total_matches
prob_2 = (home.losses + away.wins) / total_matches
quota_* = 1 / prob_*   (se prob > 0, altrimenti null + warning)
```

**Quota finale:**

| Esito | Pesi |
|-------|------|
| 1 | 20% casa/trasferta + 25% totali + 20% ultime 5 + 35% ultime 6 |
| X | stessi pesi sulle quote X dei picchetti |
| 2 | stessi pesi sulle quote 2 dei picchetti |

`final_prob_* = 1 / final_quota_*`

## Dati input (DB)

Record W/D/L aggregati da `fixtures` finite **prima** del kickoff target (anti-leakage), scoped per `competition_id`:

- Casa/trasferta: split home della squadra casa + split away della squadra ospite
- Totali: tutti i prior della stagione/competition
- Ultime 5: ultimi 5 match nello split casa/fuori
- Ultime 6: ultimi 6 match totali

Warning `partial_recent_sample` se meno di 5/6 partite disponibili (calcolo comunque se `total_matches > 0`).

## Status e warning

| Status | Significato |
|--------|-------------|
| `available` | Tutte le quote calcolabili |
| `insufficient_data` | Nessuna partita o probabilità zero |
| `pending_formula_extraction` | Placeholder sezioni 6–8 |
| `error` | Errore runtime service |

Warning tipici: `zero_matches_in_context`, `zero_probability`, `partial_recent_sample`.

## Endpoint

| Metodo | Path |
|--------|------|
| GET | `/api/competitions/{competition_id}/cecchino/upcoming` |
| GET | `/api/competitions/{competition_id}/cecchino/fixture/{fixture_id}` |
| POST | `/api/admin/competitions/{competition_id}/cecchino/recalculate` |
| POST | `/api/admin/cecchino/debug/calculate` |

Body recalculate opzionale: `{ "fixture_id": number, "limit": number }`.

## Persistenza

Tabella `cecchino_predictions` — unique `(competition_id, fixture_id, cecchino_version)`.

Campi: `input_snapshot_json`, `output_json`, `warnings_json`, `status`, team ids, timestamps.

## Frontend

Route `/cecchino` — voce menu principale. Banner: modulo separato da SOT v2.0/v2.1.

## Test parità Excel

Caso di riferimento: **San Lorenzo de Almagro vs Deportivo Riestra** — vedi `backend/tests/test_cecchino_engine_excel_parity.py`.

## Codice

| Componente | Path |
|------------|------|
| Engine | `backend/app/services/cecchino/cecchino_engine.py` |
| Service | `backend/app/services/cecchino/cecchino_service.py` |
| Route | `backend/app/routes/cecchino.py` |
| Model | `backend/app/models/cecchino_prediction.py` |
| UI | `frontend/src/pages/CecchinoPage.tsx` |
