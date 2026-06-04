# Cecchino

Modulo **parallelo** al modello SOT per stimare quote 1X2 da picchetti tecnici (record Vittorie/Pareggi/Sconfitte). Non modifica né legge `team_sot_predictions`, v2.0 o v2.1.

## Stato

| Campo | Valore |
|-------|--------|
| Versione corrente | `cecchino_v0_4_bookmaker_kpi` |
| Versioni precedenti | `cecchino_v0_3_signals_matrix`, `cecchino_v0_2_real_records`, `cecchino_v0_1_excel_parity` (cache legacy) |
| Fase | 1–3 come prima; **4** — quote bookmaker API-Football + Pannello KPI DASHBOARD |
| Separazione SOT | Totale — engine, API, UI e tabella dedicati |

## Obiettivo

Replicare online la logica del foglio **CECCHINO** di `AutomazioneCecchino.xlsm`:

1. Picchetto tecnico casa/trasferta
2. Picchetto tecnico somma partite totali
3. Picchetto stato di forma ultime 5 casa/fuori
4. Picchetto stato di forma ultime 6 totali
5. Quota matematica finale Cecchino (media ponderata)

**Implementate in v0.4:**

- Bookmaker whitelist API-Football: **Bet365** (id 8), **Betfair** (3), **Pinnacle** (4)
- Persistenza quote in `fixture_bookmaker_odds` (per `selection_key`: HOME, DRAW, AWAY, ONE_X, …)
- Media aritmetica bookmaker; doppie chance **derivate** da 1X2 se non in feed (`100/(p_home+p_draw)`, …)
- **Pannello KPI** (tab DASHBOARD): colonne STATISTICA, CECCHINO, BOOK (media 3 book), MEDIA, EDGE
- EDGE: `(BOOK / CECCHINO) - 1` in percentuale; quote statistiche da W25–W32 su `input_snapshot`
- DELTA DI FORZA e ANALISI DEL MATCH (Equilibrio / Squilibrio / Neutro) su statistica, Cecchino e book
- Legenda metrica delta forza sotto il pannello; mercati assenti → `not_available` (no quote inventate)

**Implementate in v0.3:**

- Matrice segnali SI/NO (formule Excel F32–F60, colonne D/E/F/G)
- Indice affidabilità (`sample` picchetto casa/trasferta, `index = min(sample/20, 1)`)

**Non implementate:**

- Movimento quota / rumors
- OVER PT senza mercato reale in feed

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

### `input_snapshot` (8 slice)

Ogni chiave (`home_context`, …) espone:

| Campo | Descrizione |
|-------|-------------|
| `label` | Etichetta UI (es. Casa split casalinghe) |
| `wdl` | `{ wins, draws, losses }` |
| `sample_count` | Partite nel campione |
| `target_sample` | Target 5/6 per contesti recenti, altrimenti `null` |
| `status` | `available` \| `partial_low_sample` \| `insufficient_data` |
| `fixture_ids` | ID fixture usate |

### Blocco `data_quality` (API)

Campi: conteggi campione per contesto, `leakage_check` (oggetto), `warnings`, `fixture_ids_used`.

`leakage_check`:

```json
{
  "status": "passed|failed|undefined",
  "target_kickoff": "ISO8601",
  "max_source_fixture_date": "ISO8601",
  "checked_at": "ISO8601"
}
```

Se `status = failed` → risposta `cecchino_leakage_failed`, nessun calcolo quote salvato come `available`.

### Matrice segnali SI/NO (v0.3)

Modulo: [`cecchino_signals_matrix.py`](../backend/app/services/cecchino/cecchino_signals_matrix.py)

**Input (solo quote Cecchino, nessun output SOT):**

| Variabile | Excel | Formula |
|-----------|-------|---------|
| q1 | F32 | quota finale 1 |
| qx | F33 | quota finale X |
| q2 | F34 | quota finale 2 |
| avg_q | F35 | media(q1, qx, q2) |
| diff_1_2 | F36 | q2 − q1 |

**Righe:** UNDER/UNDER PT, SEGNO X, OVER/OVER PT, 1, 1X, 2, X2, 12 — colonne Excel D/E/F/G (+ Scala per 1 e 2).

**Affidabilità:** `sample` = somma campioni picchetto casa/trasferta; `index = min(sample/20, 1)`; status OK/NO BET; livello ALTA/MEDIA/BASSA.

Se q1/qx/q2 mancanti → `signals_matrix.status = insufficient_data`.

### Cache v0.3

Righe `cecchino_predictions` con `cecchino_version = cecchino_v0_3_signals_matrix`. Cache senza `signals_matrix.status = available` o snapshot incompleto → ricalcolo automatico.

Ricalcolo manuale: `GET .../fixture/{id}?recalculate=true` o `?force_recalculate=true`, oppure `POST /api/admin/competitions/{id}/cecchino/recalculate`.

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
| POST | `/api/admin/cecchino/today/scan` |
| GET | `/api/cecchino/today` |
| GET | `/api/cecchino/today/{today_fixture_id}` |
| GET | `/api/admin/cecchino/today/excluded` |

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
| `CecchinoFixtureDetailPanel` | Sezioni A–F: metadati, picchetti, final, matrice SI/NO, debug JSON |
| `CecchinoSignalsMatrixPanel` | Tabella segnali D/E/F/G + card affidabilità |

**Stati UI dettaglio:** `available` / `partial_low_sample` → picchetti + quote finali; `insufficient_data` → messaggio senza numeri; `leakage failed` → banner errore; accordion «Debug tecnico» con JSON serializzato.

**URL:** `?competition_id=&fixture_id=` per deep-link al dettaglio.

## Cecchino Today — discovery giornaliera v0.2 (persistenza giornate)

Pipeline **manuale** (no cron) per scoprire partite via API-Football per giornata (`scan_date`), filtrare competizioni non ammesse, verificare quote 1X2 complete su Bet365/Betfair/Pinnacle, bootstrap DB minimo Cecchino-only, gate statistiche + leakage, calcolo Cecchino + KPI.

| Filtro | Esclusione |
|--------|------------|
| Femminili / coppe / amichevoli / youth | `excluded_women`, `excluded_cup`, … |
| Partita già iniziata | `excluded_started` |
| Bookmaker o 1X2 incompleti | `excluded_missing_bookmaker`, `excluded_missing_1x2_market` |
| Stats insufficienti o leakage | `excluded_insufficient_stats` |

**Soglie stats:** home/away context ≥3, total ≥6, recent_5 ≥3, recent_6 ≥5, leakage `passed`.

**Persistenza:** tabella `cecchino_today_fixtures` — upsert per `(scan_date, provider_fixture_id)`; ogni scan tocca **solo** la propria giornata. Retention 7 giorni (cleanup post-scan).

**Endpoint:**

| Metodo | Path | Scopo |
|--------|------|--------|
| GET | `/api/cecchino/today/days` | Giornate (oggi, domani, storico 7d) |
| GET | `/api/cecchino/today?date=` | Solo eleggibili persistiti + `scan_meta` |
| GET | `/api/cecchino/today/{id}` | Dettaglio persistito |
| POST | `/api/admin/cecchino/today/scan` | Scan generico (data opzionale) |
| POST | `/api/admin/cecchino/today/scan-today` | Scan oggi (Europe/Rome) |
| POST | `/api/admin/cecchino/today/scan-tomorrow` | Scan domani |
| POST | `/api/admin/cecchino/today/cleanup` | Retention manuale |
| GET | `/api/admin/cecchino/today/excluded?date=` | Escluse + debug |
| GET | `/api/admin/cecchino/today/debug-search?date=&q=` | Ricerca diagnostica |

**UI:** route `/cecchino-today` — pill giornate, scan oggi/domani, layout 2 colonne (38% lista / 62% dettaglio). Dettaglio verticale: KPI → Quote finali → Segnali → Dettaglio bookmaker. Pannello admin «Vedi escluse» con debug. Il KPI classico su `/cecchino` resta invariato.

**Versione:** `cecchino_today_v0_2_persistent_days`. Nessuna modifica a SOT v2.0/v2.1 né `team_sot_predictions`.

## Cecchino Today — discovery giornaliera v0.1 (storico)

Versione iniziale con date picker singolo e scan generico — sostituita da v0.2 (Fase 8).

## Test parità Excel

Caso di riferimento: **San Lorenzo de Almagro vs Deportivo Riestra** — vedi `backend/tests/test_cecchino_engine_excel_parity.py`.

## Codice

| Componente | Path |
|------------|------|
| Engine | `backend/app/services/cecchino/cecchino_engine.py` |
| Signals matrix | `backend/app/services/cecchino/cecchino_signals_matrix.py` |
| Fixture history | `backend/app/services/cecchino/cecchino_fixture_history.py` |
| Service | `backend/app/services/cecchino/cecchino_service.py` |
| Route | `backend/app/routes/cecchino.py` |
| Cecchino Today | `backend/app/services/cecchino/cecchino_today_service.py`, `backend/app/routes/cecchino_today.py` |
| Model | `backend/app/models/cecchino_prediction.py`, `cecchino_today_fixture.py` |
| UI | `frontend/src/pages/CecchinoPage.tsx`, `CecchinoTodayPage.tsx`, componenti `CecchinoToday*`, `cecchinoApi.ts`, `cecchinoTodayApi.ts` |
