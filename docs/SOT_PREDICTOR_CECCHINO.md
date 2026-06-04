# Cecchino

Modulo **parallelo** al modello SOT per stimare quote 1X2 da picchetti tecnici (record Vittorie/Pareggi/Sconfitte). Non modifica né legge `team_sot_predictions`, v2.0 o v2.1.

## Stato

| Campo | Valore |
|-------|--------|
| Versione | `cecchino_v0_1_excel_parity` |
| Fase | 1 — parità Excel; **2** — recupero dati reali e anti-leakage; **3** — dashboard frontend autonoma |
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

Warning `low_sample:{contesto}` se meno di 5/6 partite nel target (calcolo comunque se `total_matches > 0`).

## Fase 2 — Recupero dati e no leakage

Modulo dedicato: [cecchino_fixture_history.py](../backend/app/services/cecchino/cecchino_fixture_history.py)

### 8 contesti dati

| Chiave | Contenuto |
|--------|-----------|
| `home_context` | Record casalinghe squadra home |
| `away_context` | Record esterne squadra away |
| `home_total` / `away_total` | Record totali stagione/competition |
| `home_recent_context_5` / `away_recent_context_5` | Ultime 5 nel rispettivo split |
| `home_recent_total_6` / `away_recent_total_6` | Ultime 6 totali |

### Filtri query

- Solo `status IN (FT, AET, PEN)`
- `competition_id` = competizione target
- `season_id` quando non in modalità solo-competition
- Partita prior solo se `kickoff` (e `fixture_id`) strettamente prima del target — **no data leakage**
- Esclusi stati live (`1H`, …) e futuri (`NS`, …) dal pool usato

### Blocco `data_quality` (API)

Campi: `sample_home_context`, `sample_away_context`, `sample_home_total`, `sample_away_total`, `sample_home_recent_context`, `sample_away_recent_context`, `sample_home_recent_total`, `sample_away_recent_total`, `leakage_check` (`passed` | `failed`), `warnings`, `fixture_ids_used`.

Se `leakage_check = failed` → risposta `cecchino_leakage_failed`, nessun calcolo quote.

### Picchetto arricchito

Ogni picchetto in `output.picchetti` include: `input_records`, `sample_home` / `sample_away`, `probabilities`, `mathematical_odds`, `status`.

## Status e warning

| Status | Significato |
|--------|-------------|
| `available` | Tutte le quote calcolabili, campione sufficiente |
| `partial_low_sample` | Quote calcolabili ma meno partite del target 5/6 |
| `insufficient_data` | Nessuna partita o probabilità zero |
| `pending_formula_extraction` | Placeholder sezioni 6–8 |
| `error` | Errore runtime / leakage failed |

Warning tipici: `zero_matches_in_context`, `zero_probability`, `low_sample:*`, `leakage:*`.

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

Route `/cecchino` — voce menu principale. Modulo separato da SOT v2.0/v2.1 (nessun `model_version` SOT).

### Fase 3 — Dashboard autonoma

| File | Ruolo |
|------|--------|
| `frontend/src/lib/cecchinoApi.ts` | Client HTTP e tipi Cecchino (non in `api.ts`) |
| `frontend/src/lib/cecchinoUtils.ts` | `formatWdl`, `computeBestSide`, `canShowFinalOdds`, badge stato |
| `frontend/src/pages/CecchinoPage.tsx` | Layout: header → tabella partite → dettaglio sotto |
| `CecchinoFixturesTable` | Colonne quote/prob/best side; quote `—` se non `available`/`partial_low_sample` |
| `CecchinoFixtureDetailPanel` | Sezioni A–F: metadati, picchetti, final, placeholder, debug JSON |

**Stati UI dettaglio:** `available` / `partial_low_sample` → picchetti + quote finali; `insufficient_data` → messaggio senza numeri; `leakage failed` → banner errore; accordion «Debug tecnico» con JSON serializzato.

**URL:** `?competition_id=&fixture_id=` per deep-link al dettaglio.

## Test parità Excel

Caso di riferimento: **San Lorenzo de Almagro vs Deportivo Riestra** — vedi `backend/tests/test_cecchino_engine_excel_parity.py`.

## Codice

| Componente | Path |
|------------|------|
| Engine | `backend/app/services/cecchino/cecchino_engine.py` |
| Fixture history | `backend/app/services/cecchino/cecchino_fixture_history.py` |
| Service | `backend/app/services/cecchino/cecchino_service.py` |
| Route | `backend/app/routes/cecchino.py` |
| Model | `backend/app/models/cecchino_prediction.py` |
| UI | `frontend/src/pages/CecchinoPage.tsx`, `frontend/src/lib/cecchinoApi.ts` |
