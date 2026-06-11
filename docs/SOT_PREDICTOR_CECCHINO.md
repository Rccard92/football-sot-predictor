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

## Cecchino Today — discovery giornaliera v0.3 (timeline, filtri, risultati)

Versione `cecchino_today_v0_3_timeline_results`: dashboard giornaliera con timeline ±7 giorni, scan per giornata selezionata, aggiornamento risultati post-kickoff, filtri client-side, card arricchite (stato, score, loghi).

| Metodo | Path | Scopo |
|--------|------|--------|
| GET | `/api/cecchino/today/days` | Timeline ±7: oggi, futuro, storico; counts per stato |
| GET | `/api/cecchino/today?date=` | Eleggibili + summary + filters + score/loghi |
| POST | `/api/admin/cecchino/today/scan-day` | Avvia scan async (wrapper → `/scan-day/start`; `sync=true` solo debug) |
| POST | `/api/admin/cecchino/today/update-results` | Aggiorna stato/score eleggibili salvate |
| POST | `/api/admin/cecchino/today/scan-today` | Alias scan oggi (mantenuto) |
| POST | `/api/admin/cecchino/today/scan-tomorrow` | Alias scan domani (mantenuto) |

**Persistenza post-kickoff:** le eleggibili restano in lista; `update-results` aggiorna `match_display_status`, score e loghi. Cleanup retention 7 giorni invariato.

**UI:** timeline a frecce (finestra paginata 3/5/7 giorni, no scrollbar), filtri stato/nazione/campionato/ricerca, card senza badge bookmaker, lista sticky su desktop, dettaglio KPI → Quote → Segnali (verticale).

## Cecchino Today — Fase 10 UX (refinement timeline e card)

- Timeline `CecchinoDayTimeline`: frecce avanti/indietro, 7/5/3 giorni visibili, centrata su oggi al mount, nessuna scrollbar.
- Lista partite sticky su desktop (`lg:sticky`); scroll interno se lunga.
- Card partita: riga principale (ora, squadre, CTA destra); riga secondaria predizione consigliata + risultato.
- Debug escluse sotto il layout principale (accordion, default chiuso).
- Nessuna modifica backend o formule Cecchino/SOT.

## Cecchino Today — Fase 11 — Final eligibility gate (v0.4)

Versione `cecchino_today_v0_4_final_eligibility_gate`: gate post-calcolo che impedisce l’ingresso in lista principale di partite con Cecchino o KPI incompleti.

| Metodo | Path | Scopo |
|--------|------|--------|
| POST | `/api/admin/cecchino/today/revalidate-day` | Ricalcola eleggibilità su snapshot persistiti per una giornata |

**Regole bloccanti (ordine di valutazione):**

1. Bookmaker Bet365/Betfair/Pinnacle con 1X2 HOME/DRAW/AWAY completo
2. Campioni statistici minimi + assenza `low_sample:*` sotto soglia
3. Leakage `failed` ( `undefined` → warning non bloccante )
4. Picchetti obbligatori calcolabili (`home_away`, `totals`, `last5_home_away`, `last6_totals`)
5. Nessuna `zero_probability` su 1/X/2
6. Quote finali Cecchino `status=available` con quota/prob 1/X/2
7. KPI 1X2 con valori Cecchino, BOOK ed edge calcolabili (Over 1.5/2.5/PT opzionali)

**Debug escluse:** `blocking_reasons`, `cecchino_debug`, `kpi_debug`, `import_info`.

**UI:** label italiane per motivi esclusione; dettaglio eligible mostra «Note dati» (non bloccanti) vs avvisi; pulsante «Rivalida eleggibilità».

## Cecchino Today — Fase 12 — Idempotenza scan-day (v0.5)

Versione `cecchino_today_v0_5_scan_idempotency`: bootstrap idempotente leghe/squadre/fixture; scan-day non va in 500 per duplicate league.

| Componente | Comportamento |
|------------|---------------|
| `league_ingest_helpers.py` | `get_or_create_league_by_api_id`, Season, Competition; `safe_upsert_team_from_api_item` |
| IntegrityError | Savepoint + rollback + re-fetch record esistente |
| Bootstrap fallito | `excluded_mapping_error` + `blocking_reasons`; scan prosegue |
| Report scan | Campi `errors`, `excluded_summary` |

**UI:** messaggio chiaro su HTTP 500 scan («Controlla i log backend»); report 200 con esclusioni mostrato normalmente.

## Cecchino Today — Fase 13 — Over/Under bookmaker (v0.6)

| Componente | Comportamento |
|------------|---------------|
| Debug mercati | `GET /api/admin/bookmakers/fixture-markets-debug` — raw bets API-Football per Bet365/Betfair/Pinnacle |
| Mercato raw | `Goals Over/Under` (bet id 5), selection `Over 1.5` / `Over 2.5` |
| Scan-day | Persiste 1X2 + DC + OU in `fixture_bookmaker_odds` |
| KPI dettaglio | Righe OVER mostrano quote per book + media coerente; badge «Parziale» se 1–2 book |

**Eleggibilità:** invariata; Over e Over PT opzionali nel KPI.

## Cecchino Today — Fase 16 — Scan asincrona e polling (v0.10)

Versione `cecchino_today_v0_10_async_scan`: scan giornaliera come job background con polling UI; odds ottimizzate (single-call + cache).

| Metodo | Path | Scopo |
|--------|------|--------|
| POST | `/api/admin/cecchino/today/scan-day/start` | Avvia job; risposta immediata `{job_id, status}` |
| GET | `/api/admin/cecchino/today/scan-jobs/{job_id}` | Stato job completo per polling |
| GET | `/api/admin/cecchino/today/scan-jobs/latest?date=` | Ultimo job per giornata (o `null`) |
| POST | `/api/admin/cecchino/today/scan-day` | Wrapper async (default); `?sync=true` sync deprecato |

| Componente | Comportamento |
|------------|---------------|
| Tabella | `cecchino_today_scan_jobs` — status, progress, step, contatori, JSON summary/warnings/errors |
| Thread | `SessionLocal` dedicata; commit progress ogni batch (~10 fixture) |
| Duplicati | Job `queued\|running` stesso `scan_date` → restituisce esistente; `force_rescan` + running → 409 |
| Stale | Job running >30 min → `failed` (`stale job timeout`) |
| Odds | `get_fixture_odds_by_fixture` + cache snapshot; strategie `cached`, `fixture_single_call`, fallback |
| Timeline | `scan_job_status`, `scan_job_id`, `scan_state=scanning` su GET `/days` |

**UI:** `CecchinoTodayScanProgressCard`, polling 2,5s, resume job su reload pagina via `latest`.

**UI:** progress card con elapsed time; pulsante «Scansione in corso» disabilitato; nessun auto-scan al cambio giorno.

## Cecchino Today — Fase 39 — Legenda formule Monitoraggio Segnali (v0.33)

Versione UI `cecchino_today_v0_33_signals_formula_legend` — debug formule heatmap.

| Componente | Comportamento |
|------------|---------------|
| UI | Accordion «Legenda formule segnali Cecchino» sotto heatmap, chiuso di default |
| Dati | `cecchinoSignalFormulaLegend.ts` — formule Excel + parlanti statiche |
| Tab | 8 segnali (stesso ordine heatmap): UNDER 2.5, SEGNO X, OVER 2.5, 1, 1X, 2, X2, 12 |
| Colonne | Excel D/E/F/G + SCALA; colonne non previste marcate «Non prevista da Excel» |
| Nota SCALA | G48 solo 1X/SCALA; G54 solo X2/SCALA; righe 1 e 2 senza SCALA |
| Aggregazione | Box intro su Attivazioni, Valutati, Success rate heatmap |

**Invariato:** backend segnali, Betfair-only, SOT v2.0/v2.1, formule calcolo matrice.

## Cecchino Today — Fase 38 — Fix definitivo Scala 1X/X2 (v0.32)

Versione UI `cecchino_today_v0_32_scala_fix_definitivo` — heatmap e storico SCALA corretti.

| Componente | Comportamento |
|------------|---------------|
| Mapping | G48 → ONE_X+SCALA; G54 → X_TWO+SCALA; D48 → HOME+EXCEL_D; D54 → AWAY+EXCEL_D |
| Sync guard | Mai creare HOME/AWAY+SCALA anche da matrici legacy malformate |
| force_remap | `force_rebuild=True` sovrascrive sempre `signals_matrix` prima del sync |
| Summary | Esclude legacy HOME/AWAY+SCALA da heatmap e aggregati |
| Diagnostics | `legacy_wrong_scala_mapping_count`; warning se > 0 |
| UI | Banner amber + difesa heatmap su righe 1/2 colonna SCALA |

**Invariato:** formule SI/NO, Betfair-only, SOT v2.0/v2.1, Under/Over 2.5 FT (Fase 34).

## Cecchino Today — Fase 37 — Correzione mapping Scala segnali (v0.31)

Versione UI `cecchino_today_v0_31_scala_mapping` — SCALA su righe 1X/X2.

| Riga | `row.key` | `signal_group` | Colonne signals |
|------|-----------|----------------|-----------------|
| 1 | `one` | HOME | solo `excel_d` (D48) |
| 1X | `one_x` | ONE_X | D/E/F/G + `scala_1x` (G48) |
| 2 | `two` | AWAY | solo `excel_d` (D54) |
| X2 | `x_two` | X_TWO | D/E/F/G + `scala_x2` (G54) |

| Componente | Comportamento |
|------------|---------------|
| Backfill | `force_remap=true` ricalcola matrice, disattiva legacy HOME/AWAY+SCALA, risincronizza |
| Remap | `remap_legacy_scala_activations_in_range` con `evaluation_reason` dedicato |
| UI | Pulsante «Ricalcola mapping segnali»; heatmap corretta dopo remap |
| Dettaglio | `CecchinoSignalsMatrixPanel` mostra Scala solo su righe 1X e X2 |

**Invariato:** formule SI/NO, Betfair-only, SOT v2.0/v2.1, Under/Over 2.5 FT (Fase 34).

## Cecchino — Fase 47 — Intensità Goal v2 calibrata

Evoluzione Fase 46: normalizzazione su baseline mediana storica.

| Componente | Comportamento |
|------------|---------------|
| Versione | `cecchino_goal_intensity_v2` |
| Grezzi | `raw.offensive_index` / `raw.defensive_index` (OVER/UNDER Q44) |
| Baseline | `get_goal_intensity_baselines` — mediana, fallback league (≥30) → country (≥40) → global (≥50) |
| Calibrato | `normalized.intensity_ratio` = (OVER/baseline_OVER) / (UNDER/baseline_UNDER) |
| Delta | `normalized.intensity_delta` = OVER_norm − UNDER_norm (conferma) |
| Classificazione | Solo su rapporto calibrato; soglie invariate v1 |
| Stati | `available`, `insufficient_data`, `insufficient_baseline` |
| Cache | In-process per scope/fixture |

**Invariato:** Equilibrio, ICM, KPI, Segnali, Betfair-only, SOT.

## Cecchino — Fase 46 — Intensità Goal (sostituita da Fase 47)

Nuova sezione nel dettaglio Cecchino Today (`GET /api/cecchino/today/{id}`).

| Componente | Comportamento |
|------------|---------------|
| Posizione UI | Equilibrio vs Squilibrio → **Intensità Goal** → ICM |
| Builder | `cecchino_goal_intensity_analysis.py` — `build_cecchino_goal_intensity_analysis` |
| Indice Offensivo | OVER Q44 = (Q39+R39)/2 + (Q42+R42)/2 da parità Excel `calculate_over_fulltime_excel_parity` |
| Indice Difensivo | UNDER Q44 = stessa struttura con `calculate_under_fulltime_excel_parity` |
| Rapporto | OVER Q44 / UNDER Q44 (principale) |
| Delta | OVER Q44 − UNDER Q44 (conferma) |
| Payload | `goal_intensity_analysis` nel detail response |
| UI | `CecchinoGoalIntensityAnalysisPanel` — card, metriche, scala, conferma delta, accordion tecnico |

**Indipendente** da Equilibrio vs Squilibrio (F36/Dominanza/Quota X). **Non implementati:** Goal Attesi Totali/Casa/Ospite, Dominanza Offensiva, Risultati Compatibili.

**Invariato:** balance_analysis, icm_analysis, KPI, Segnali, Betfair-only, SOT v2.0/v2.1.

## Cecchino — Fase 45 — Aggiornamento formule segnali 1, 2, 1X, X2 e 12

Motore unico `build_signals_matrix` — valido per Monitoraggio Segnali stabile e Lab.

| Cella | Segnale | Nuova logica |
|-------|---------|--------------|
| D48 | 1 / Excel D | `G48=SI` AND `F36>2` AND `Dominanza>10` |
| D54 | 2 / Excel D | `G54=SI` AND `F36<-2.3` AND `Dominanza>10` |
| E51 | 1X / Excel E | `F32+0.4<F33` AND `F33+0.5<F34` AND `F32+0.6<F34` |
| G57 | X2 / Excel G | `F32+0.5>F33` AND `F33+0.6>F34` AND `F32+0.7>F34` |
| D60 | 12 / Excel D | `(F33>=4.8 & F32<2.40 & F36<-1.5)` OR `(F33>=4.8 & F34<2.40 & F36>1.5)` |
| E60 | 12 / Excel E | `F33>=4.8` AND `Dominanza>=10` AND `|F36|>=1.5` |

| Componente | Comportamento |
|------------|---------------|
| Dominanza | `compute_dominance_pp` in `cecchino_balance_analysis.py` — stessa scala Equilibrio vs Squilibrio (punti percentuali); se prob mancanti → formule che la richiedono = NO |
| Call site | `cecchino_engine`, `cecchino_signal_backfill`, `cecchino_signal_model_backtest` passano `prob_1/x/2` da quote finali |
| Recompute | `sync_cecchino_signal_activations`, backfill (`force_rebuild`/`force_remap`), `POST .../signals/revaluate`, `POST .../signals/backtest-models` |
| UI stabile | Legenda formule aggiornata + nota Dominanza in `SignalsFormulaLegendAccordion` |
| UI Lab | Stesso accordion riusato in `MonitoraggioSegnaliLab` |

**Invariato:** G48/G54 SCALA, UNDER/OVER/X, altre celle 1X/X2 non elencate, Betfair-only, SOT v2.0/v2.1, `team_sot_predictions`, KPI, ICM.

## Cecchino Today — Fase 44 — Monitoraggio Segnali Lab

Pagina sperimentale frontend-only (`/monitoraggio-segnali-lab`).

| Componente | Comportamento |
|------------|---------------|
| Route | `/monitoraggio-segnali-lab`; voce sidebar **Segnali Lab** |
| Dati | Stessi endpoint Fase 43 (`models-summary`, `summary`, `activations`, `backtest-models`, `revaluate`, export CSV) |
| UI | Card A–F, ribbon 11 metriche, ECharts, heatmap 8×6, top ranking, drawer dettaglio, tabella partite |
| Stack | `framer-motion`, ECharts tree-shaken, Sonner toast; markup Tailwind custom |
| Isolamento | Codice in `components/cecchino-lab/`; pagina stabile `/monitoraggio-segnali` invariata |
| Persistenza | `cecchino_signals_lab_selected_model` (separato dalla pagina stabile) |

**Invariato:** backend, Cecchino Today live, SOT v2.0/v2.1, Betfair-only.

## Cecchino Today — Fase 43 — Backtest modelli pesi A-F

Confronto offline modelli pesi 1X2 nel Monitoraggio Segnali (`/monitoraggio-segnali`).

| Componente | Comportamento |
|------------|---------------|
| Modelli A–F | Pesi indipendenti su Totali / Casa-Fuori / Ultime 6 / Ultime 5 C/F |
| `model_key` | Colonna su `cecchino_signal_activations` (storico backfill → F) |
| Backtest | `POST /signals/backtest-models` — ricalcolo offline da picchetti DB, zero API |
| Models summary | `GET /signals/models-summary` — card comparativi Win Rate / quota prese / void / rendimento |
| Filtro UI | `model_key` su summary, activations, export CSV; default F |
| Live vs backtest | Cecchino Today live resta su `CECCHINO_1X2_WEIGHTS`; A–F sono solo comparativi monitoraggio |

**Invariato:** Betfair-only, formule segnali, KPI Today, ICM, SOT v2.0/v2.1, goal market live.

## Cecchino Today — Fase 42 — Quota media prese e Quota Void

Metriche Monitoraggio Segnali (`/monitoraggio-segnali`).

| Componente | Comportamento |
|------------|---------------|
| Quota media prese | Media `quota_book` solo su segnali `won` con quota valorizzata |
| Quota Void | `1 / (won / settled)` — soglia pareggio teorica |
| Margine Void | `avg_won_book_odds - quota_void` |
| Rendimento prese | `(won/settled) × avg_won_book_odds - 1` (indicatore qualità prese, non ROI reale) |
| Summary API | Campi in `overall`, `by_signal`, `by_column`, `by_signal_and_column` |
| Refresh quote | `POST /revaluate` con `refresh_signal_odds=true` da `kpi_panel_json` (offline) |
| UI | Card KPI, heatmap, top segnali, dettaglio partite, CSV, accordion spiegazione |

**Invariato:** Betfair-only, formule segnali, KPI Today, ICM, SOT v2.0/v2.1.

## Cecchino Today — Fase 41 — Indice di Convergenza Match (ICM)

Versione builder `cecchino_icm_v1` — sostituisce Delta Forza Match (Fase 36, deprecata in Today).

| Componente | Comportamento |
|------------|---------------|
| ICM | Score 0–100 da narrative scoring su 5 pilastri (F36, Dominanza, Quota X, Rating, Vantaggio Prob.) |
| Narrative | `balance_under`, `balance_draw`, `imbalance_home/away`, `imbalance_over`, `contradictory_markets` |
| Classificazione | ≤20 contraddittoria, ≤40 debole, ≤60 moderata, ≤80 forte, >80 totale |
| Penalità ambiguità | Gap tra 1ª e 2ª narrativa: 0/5/10/20 punti |
| API | `icm_analysis` in GET `/api/cecchino/today/{id}` e `kpi-debug-json` |
| UI | Sezione dedicata tra Equilibrio vs Squilibrio e Segnali (`CecchinoIcmAnalysisPanel`) |
| Balance v4 | `cecchino_balance_analysis_v4` senza embed `delta_force` |
| Ricalcolo | ICM derivato a read-time; `recompute_kpi=true` aggiorna gli input implicitamente |

**Rimosso da Today:** mini-card Delta Forza KPI, quinta card Equilibrio, legenda Delta Forza, `delta_force_analysis` nel payload.

**Invariato:** pesi Cecchino Fase 40, Betfair-only, colonne KPI, formule Segnali, SOT v2.0/v2.1.

## Cecchino Today — Fase 36 — Delta Forza e Linearità Match (v0.30) — deprecata

> Sostituita da ICM (Fase 41). Il modulo `cecchino_delta_force_analysis.py` resta nel repo per compatibilità legacy.

Versione UI `cecchino_today_v0_30_delta_force` — linearità match vs book Betfair.

| Componente | Comportamento |
|------------|---------------|
| Delta Forza | `abs(edge_pct)` su 1/X/2; edge = `(quota_book/quota_cecchino - 1) * 100` |
| Soglie | `<17%` lineare, `17-31%` non lineare, `>31%` forte distorsione |
| Match-level | `max(delta_1, delta_x, delta_2)` + segno responsabile |
| KPI UI | Mini-card «Delta Forza Match» sopra tabella (nessuna colonna nuova) |
| Equilibrio | Quinta card Delta Forza + arricchimento lettura operativa |
| Debug | `delta_force_analysis` in detail e `kpi-debug-json` |

**Invariato:** Betfair-only, formule KPI, F36/Dominanza come fattori primari, SOT v2.0/v2.1.

## Cecchino Today — Fase 35 — Sidebar Cecchino e metriche Monitoraggio Segnali (v0.29)

Versione UI `cecchino_today_v0_29_signals_ui_metrics` — navigazione e KPI monitoraggio.

| Componente | Comportamento |
|------------|---------------|
| Sidebar | Sezione **CECCHINO** in alto: Cecchino, Cecchino Today, Monitoraggio Segnali |
| Heatmap | Label righe `UNDER 2.5` e `OVER 2.5` (signal_group interni invariati) |
| Summary | `eligible_fixtures_count`, `fixtures_with_signals_count`, `avg_signals_per_fixture` |
| UI KPI | Card «Media segnali / partita» con 1 decimale, sottotitolo «su partite eleggibili» |

**Invariato:** SOT v2.0/v2.1, KPI Betfair-only, valutazione Under/Over 2.5 FT (Fase 34).

## Cecchino Today — Fase 34 — Mapping Under/Over su 2.5 FT (v0.28)

Versione UI `cecchino_today_v0_28_under_over_mapping` — valutazione segnali UNDER/OVER aggregati.

| Componente | Comportamento |
|------------|---------------|
| Mapping | `UNDER_UNDER_PT` → `UNDER_2_5` FT; `OVER_OVER_PT` → `OVER_2_5` FT |
| Remap storico | `remap_under_over_activations_in_range` su backfill/revaluate |
| Valutazione | Won/lost da gol totali FT (Under ≤2, Over ≥3); `evaluation_reason` leggibile |
| API/UI | Target serializzato come «Under 2.5 FT» / «Over 2.5 FT»; nota sotto heatmap |
| Rivaluta | Ex-`not_evaluable` UNDER/OVER rivalutati senza API aggiuntive |

**Escluso:** mercati PT (`UNDER_PT_1_5`, `OVER_PT_*`), formule OU KPI, SOT v2.0/v2.1.

## Cecchino Today — Fase 33 — Backfill Monitoraggio Segnali (v0.27)

Versione UI `cecchino_today_v0_27_signal_backfill` — popolamento storico activations.

| Componente | Comportamento |
|------------|---------------|
| Causa pagina vuota | Giornate pre-Fase 32 senza materializzazione in `cecchino_signal_activations` |
| Backfill | `POST /admin/cecchino/signals/backfill` — offline da `cecchino_output_json.signals_matrix` |
| Diagnostics | `GET /admin/cecchino/signals/diagnostics` — confronto fixture vs activations |
| UI | Pulsante «Sincronizza segnali» + alert se partite esistono ma activations = 0 |
| Revaluate | `sync_missing=true` esegue backfill prima della rivalutazione |
| Scan | `sync_signals_for_scan_date` a fine `run_scan` |

**Invariato:** KPI Betfair-only, SOT v2.0/v2.1, matrice segnali nel dettaglio.

## Cecchino Today — Fase 32 — Monitoraggio Segnali Cecchino (v0.26)

Versione UI `cecchino_today_v0_26_signal_monitoring` — persistenza e analisi storica segnali SI.

| Componente | Comportamento |
|------------|---------------|
| Matrice dettaglio | Invariata nel dettaglio partita (`CecchinoSignalsMatrixPanel`) |
| Tabella DB | `cecchino_signal_activations` — ogni SI salvato come activation |
| Sync | Idempotente su scan upsert e apertura dettaglio (`sync_cecchino_signal_activations`) |
| Valutazione | `won`/`lost`/`pending`/`not_evaluable` dopo update-results (offline) |
| Mapping sicuro | 1/X/2/1X/X2/12 valutabili FT; UNDER/OVER generici `not_evaluable` |
| Pagina UI | `/monitoraggio-segnali` — KPI, heatmap, top segnali, lista, export CSV |
| API admin | `GET summary`, `GET activations`, `GET export.csv`, `POST revaluate` |

**Invariato:** KPI Betfair-only, SOT v2.0/v2.1, Debug Picchetti, Equilibrio vs Squilibrio, formule matrice segnali.

## Cecchino Today — Fase 31 — Legenda operativa equilibrio (v0.25)

Versione UI `cecchino_today_v0_25_balance_legend` — legenda operativa aggiornata sotto Dettaglio tecnico.

| Componente | Comportamento |
|------------|---------------|
| Legenda UI | Accordion «Legenda lettura operativa» sotto Dettaglio tecnico equilibrio |
| Tabella | 18 righe: F36, Segno dominante, Dominanza, Quota X, Lettura operativa |
| Responsive | Tabella desktop + card stack mobile |
| Note | 2 note esplicative su Dominanza contestualizzata e F36 |
| Backend label | Allineamento: DRAW dom 0–5 → «X forte»; 6–10 → «X molto interessante»; laterale dom≤5 → «X possibile» |
| technical.legend_version | `balance_operational_legend_v2_contextual_dominance` |

**Invariato:** formule F36/Dominanza/Gap, logica decisionale, KPI Betfair-only, SOT v2.0/v2.1.

## Cecchino Today — Fase 30 — Dominanza contestualizzata (v0.24)

Versione UI `cecchino_today_v0_24_dominance_context` — correzione lettura Dominanza.

| Componente | Comportamento |
|------------|---------------|
| Formula Dominanza | Invariata: prob_max − prob_seconda (p.p.) |
| dominance_context | Interpretazione in base a best_side (HOME/DRAW/AWAY) |
| X dominante | Dominanza rafforza equilibrio (`reinforces_balance`) |
| 1/2 dominante | Dominanza indebolisce o conferma squilibrio laterale |
| Falso equilibrio | Solo se F36<0.75, dom>10 e domina HOME/AWAY |
| Gap 1/2 Prob. | `abs(prob_1 − prob_2)` — metrica di supporto |
| Versione | `cecchino_balance_analysis_v2` |

**Invariato:** F36, Quota X, KPI Betfair-only, SOT v2.0/v2.1.

## Cecchino Today — Fase 40 — Nuovi pesi globali 1X2 e Under/Over

Versione pesi `1x2_weights_30_30_20_20` / `goal_weights_20_30_20_30`.

| Componente | Comportamento |
|------------|---------------|
| Pesi 1X2 | totals 30%, home_away 30%, last6_totals 20%, last5_home_away 20% |
| Pesi goal OU | totals 20%, home_away 30%, last6_totals 20%, last5_home_away 30% |
| Costanti | `CECCHINO_1X2_WEIGHTS` e `CECCHINO_GOAL_MARKET_WEIGHTS` separate con validazione somma = 1 |
| KPI / Equilibrio / ICM / Segnali | Ricalcolati automaticamente dalle nuove quote Cecchino |
| Debug Picchetti | Formula parlante dinamica; JSON `weights.1x2` e `weights.goal_markets` con version |
| Ricalcolo storico | `POST /api/admin/cecchino/recompute` — offline, usa dati DB; pulsante UI su Today e Monitoraggio |

**Invariato:** SOT v2.0/v2.1, `team_sot_predictions`, Betfair-only, refresh quote Betfair, struttura Pannello KPI.

## Cecchino Today — Fase 29 — Equilibrio vs Squilibrio (v0.23)

Versione UI `cecchino_today_v0_23_balance_analysis` — lettura equilibrio partita da Cecchino 1/X/2.

| Componente | Comportamento |
|------------|---------------|
| Sezione UI | «Equilibrio vs Squilibrio» sotto Debug Picchetti Cecchino |
| F36 | `quota_2 - quota_1` (assoluto) — indicatore equilibrio/squilibrio quote 1 vs 2 |
| Dominanza | `prob_max - prob_seconda` (punti percentuali) su probabilità Cecchino |
| Quota X | Classificazione pareggio forte/possibile/debole/poco probabile |
| Lettura incrociata | F36 + Dominanza → equilibrio, falso equilibrio, anomalia, squilibrio confermato |
| Lettura operativa | 12 regole decisionali X/Under, zona grigia, tendenza 1/2 |
| Backend | `build_cecchino_balance_analysis` — `balance_analysis` nel detail e kpi-debug-json |
| Dati | Solo Quota/Probabilità Cecchino 1/X/2 (`cecchino_output.final`) |

**Invariato:** KPI Betfair-only, SOT v2.0/v2.1, `team_sot_predictions`, Debug Picchetti, engine 1X2.

## Cecchino Today — Fase 28 — Nuovi pesi goal market KPI confermato (v0.22)

Versione UI `cecchino_today_v0_22_goal_weights` — pesi picchetti goal separati da 1X2.

| Componente | Comportamento |
|------------|---------------|
| Pannello KPI | Struttura Betfair-only confermata (invariata); solo valori `quota_cecchino` OU aggiornati |
| Pesi 1X2 | Invariati: totals 25%, home_away 20%, last6_totals 35%, last5_home_away 20% |
| Pesi goal OU | totals 10%, home_away 20%, last6_totals 35%, last5_home_away 35% |
| Modello | `goal_market_poisson_empirical_v2` — lambda FT/HT, empirico e reliability con nuovi pesi |
| Rinormalizzazione | Se contesto escluso (campione basso), pesi effective sui contesti disponibili |
| Debug | Badge pesi goal nel tab OU; contesti con `original_weight`, `effective_weight`, `weight_renormalized` |
| JSON debug | `weights` per mercato goal + campi peso per contesto |

**Invariato:** engine 1X2, SOT v2.0/v2.1, `team_sot_predictions`, Betfair-only, refresh quote, colonne KPI.

## Cecchino Today — Fase 27 — Goal market Poisson + storico (v0.21)

Versione UI `cecchino_today_v0_21_goal_poisson_v2` — modello analitico OU distinto per soglia.

| Componente | Comportamento |
|------------|---------------|
| Formula principale | `goal_market_poisson_empirical_v2` |
| Lambda FT/HT | 4 contesti (totals, casa/fuori, ultime 6, ultime 5) pesati 25/20/35/20 |
| Poisson | Probabilità mercato da `lambda` (soglie distinte per 1.5 / 2.5 / 3.5) |
| Empirico | Hit-rate ponderato per contesto |
| Blend | 65% Poisson + 35% storico + shrinkage reliability verso lega |
| Legacy | Excel parity in `legacy_excel_parity` (solo debug) |
| Debug v3 | Summary card, tabella contesti, dettaglio tecnico chiuso |
| KPI | `quota_cecchino` da v2; `insufficient_data` se campione basso |

**Invariato:** engine 1X2, SOT v2.0/v2.1, Betfair-only, refresh quote.

## Cecchino Today — Fase 26 — Formule goal Over/Under Excel (v0.20)

Versione UI `cecchino_today_v0_20_goal_formulas` — Quota Cecchino per 7 mercati goal.

| Componente | Comportamento |
|------------|---------------|
| Modulo formule | `cecchino_goal_formulas.py` — FT Excel parity + PT rate-to-odd |
| Storico dati | `build_goal_fixture_slices` — slice PIT goal + halftime da fixture DB |
| FT Over | Blocchi CF (÷6), totals (÷11), mixed (÷16); Over 1.5 = Over 2.5 |
| FT Under | Blocchi CF (÷4), totals (÷9), mixed (÷14); Under 2.5 = Under 3.5 |
| PT | Rate hit HT casa/fuori → prob media → quota = 1/prob |
| Persistenza | `cecchino_output_json.goal_markets` |
| KPI v2 | `quota_cecchino` OU popolata; `insufficient_data` se campione basso |
| Debug picchetti v2 | Tab Over FT / Under FT / Primo tempo; formule mancanti dinamiche |
| JSON KPI | `cecchino_goal_odds_used` con inputs e valori intermedi |

**Invariato:** engine 1X2 (`cecchino_engine.py`), SOT v2.0/v2.1, gate Betfair-only, refresh quote.

## Cecchino Today — Fase 25 — Debug Picchetti Quota Cecchino (v0.19)

Versione UI `cecchino_today_v0_19_picchetti_debug` — breakdown formule Quota Cecchino nel dettaglio.

| Componente | Comportamento |
|------------|---------------|
| Debug picchetti | Sezione accordion sotto Pannello KPI con tab 1/X/2, 1X/X2/12, formule mancanti |
| Pesi | totals 25%, home_away 20%, last6_totals 35%, last5_home_away 20% |
| Breakdown 1/X/2 | Per picchetto: campione, W-D-L, probabilità, quota, peso, contributo ponderato |
| DC | 1X/X2/12 derivate da prob implicite quote finali 1/X/2 |
| Over/Under | `formula_status: missing_formula` — nessuna Quota Cecchino inventata |
| Coerenza KPI | Warning `kpi_debug_mismatch` se debug ≠ KPI (tolleranza 0.01) |
| API | `GET /cecchino/today/{id}/picchetti-debug` + `picchetti_debug_summary` nel detail |

**Invariato:** engine Cecchino, SOT v2.0/v2.1, gate Betfair, refresh quote.

## Cecchino Today — Fase 24 — Pulizia toolbar KPI Betfair (v0.18)

Versione UI `cecchino_today_v0_18_kpi_cleanup` — pannello KPI snello, refresh in toolbar.

| Componente | Comportamento |
|------------|---------------|
| Pannello KPI | Solo titolo, bookmaker, timestamp e tabella; nessun pulsante tecnico |
| Refresh quote | Pulsante **Aggiorna quote Betfair** nella toolbar principale (visibile con partita selezionata) |
| Feedback | Banner inline: aggiornate / nessuna variazione / errore / budget bloccato |
| Endpoint debug | `refresh-betfair-odds`, `betfair-markets-json`, `kpi-debug-json` restano attivi ma non esposti in UI |

**Invariato:** formule Cecchino/KPI, modelli SOT v2.0/v2.1, scan giornata, Cecchino classico.

## Cecchino Today — Fase 23 — Refresh quote Betfair singola fixture (v0.17)

Versione UI `cecchino_today_v0_17_betfair_refresh` — quote live on-demand e export mercati.

| Componente | Comportamento |
|------------|---------------|
| Timestamp quote | `odds_snapshot_json.odds_meta`: `odds_source`, `odds_fetched_at`, `is_cached`, `last_betfair_refresh_at` |
| Refresh singola | `POST /cecchino/today/{id}/refresh-betfair-odds` — bypass cache, solo bookmaker_id=3, rebuild KPI |
| Risposta refresh | `before`/`after` 1X2, `changed`, `changed_markets`, `api_calls_used`, `manual_comparison_note` |
| Export mercati | `GET /cecchino/today/{id}/betfair-markets-json?force=` — tutti i bets Betfair con normalizzazione opzionale |
| UI KPI (Fase 24) | Pulsanti tecnici spostati/rimossi; refresh in toolbar; box timestamp nel pannello |
| Aggiornamento UI | KPI aggiornato nello state senza reload pagina dopo refresh |

**Budget:** `check_api_budget_before_scan` prima di ogni fetch live; status `budget_blocked` se guard attivo.

**Invariato:** modelli SOT v2.0/v2.1, formule Cecchino 1/X/2, segnali SI/NO, Cecchino classico, scan giornata intera.

## Cecchino Today — Fase 22 — Cleanup dettaglio analisi e debug JSON KPI Betfair (v0.16)

Versione UI `cecchino_today_v0_16_cleanup` — dettaglio snello, card eleggibili, mapping strict.

| Componente | Comportamento |
|------------|---------------|
| Dettaglio analisi | Rimossi Quote finali Cecchino e Dettaglio quote Betfair; KPI unico riferimento quote |
| Card eleggibili | Layout 2 righe: orario/stato, squadre vs, CTA; box Predizione, PT, FT |
| Score | `score.halftime` + `score.fulltime` da API-Football (`update-results`) |
| Mapping 1X2 | Solo `Match Winner` bet_id=1; selection per nome/team; no First Half Winner |
| Mapping DC | `Double Chance` raw oppure `derived_from_betfair_1x2` |
| Debug JSON | `GET /cecchino/today/{id}/kpi-debug-json` + pulsante Scarica/Copia nel KPI |
| Layout | Griglia lista 35% / dettaglio 65% |

**Invariato:** modelli SOT v2.0/v2.1, formule Cecchino 1/X/2, segnali SI/NO, Cecchino classico.

## Cecchino Today — Fase 21 — Fix KPI Betfair rows e quote book (v0.15)

Versione KPI `cecchino_kpi_v2_betfair` — correzione SEGNO, Quota Book e layout desktop.

| Componente | Comportamento |
|------------|---------------|
| Payload Betfair | `build_betfair_payload_from_raw` da `odds_by_bookmaker[3]` o snapshot; fallback DB |
| DC derivata | Formula `1/(prob_i+prob_j)` con prob decimali `1/quota`; source `derived_from_betfair_1x2` |
| KPI righe | Ogni riga espone `segno` + `label` (alias legacy); Under PT 1.5 con spazio |
| Dettaglio API | `_resolve_kpi_panel_for_detail` normalizza/rebuild da snapshot senza rescan |
| Layout UI | Griglia desktop 32%/68%; colonna SEGNO 12%; header abbreviati; no overflow orizzontale |

**UI:** fallback `segno || label || market_key` nel pannello KPI; tabella desktop più ampia.

**Invariato:** modelli SOT v2.0/v2.1, formule Cecchino 1/X/2, segnali SI/NO, Cecchino classico (`/cecchino`).

## Cecchino Today — Fase 20 — KPI Betfair-only e nuovo rating panel (v0.14)

Versione KPI `cecchino_kpi_v2_betfair`: bookmaker unico Betfair e pannello rating.

| Componente | Comportamento |
|------------|---------------|
| Bookmaker | Solo Betfair (API-Football id 3); gate 1X2 HOME/DRAW/AWAY |
| Odds fetch | `GET /odds?fixture=` + filtro id 3; fallback `bookmaker=3` |
| KPI colonne | Segno, Quota Book, Quota Cecchino, Prob. Book/Cecchino, Vantaggio Prob., Edge %, Score Acquisto, Rating |
| KPI righe | 13 righe fisse: 1/X/2, 1X/X2/12, Over/Under FT e PT |
| Rating | Formula Excel: `(prob_cecchino_pct×0,5)+(vantaggio_prob_pct×2)+edge_pct`, clamp 0-100 |
| Quote Cecchino | 1/X/2 da final odds; DC derivate; Over/Under senza formula → `—` |
| Dettaglio book | Tabella Betfair-only: Mercato, Quota, Source, Status |
| Debug link | `/bookmakers?provider_fixture_id=…&bookmaker_ids=3` |

**UI:** tabella KPI full-width desktop senza scroll orizzontale; card compatte su mobile.

**Invariato:** modelli SOT v2.0/v2.1, formule Cecchino 1/X/2, segnali SI/NO, Cecchino classico (`/cecchino`).

## Cecchino Today — Fase 19 — Gate progressivi e riduzione consumo API (v0.13)

Versione `cecchino_today_v0_13_api_gates`: ottimizzazione consumo API-Football con gate progressivi e tracking.

| Componente | Comportamento |
|------------|---------------|
| Censimento | Tutte le fixture → `discovered` prima dei gate |
| Short-circuit | Stop immediato su esclusione; no stats/Cecchino se bookmaker fallisce |
| Odds | Single-call + cache positiva + negative cache 6h |
| Bootstrap | `cecchino_league_stats_cache` deduplica import lega |
| API usage | Tabella `api_usage_events`; summary admin e job report |
| Budget guard | 7500/giorno; max 1000/job; status `partial_stopped_budget` |
| UI | Box job con API usate, cache, budget residuo; funnel esclusioni |

## Cecchino Today — Fase 18 — Fix progress bar e finalizzazione (v0.12)

Versione `cecchino_today_v0_12_progress_fix`: barra avanzamento e chiusura job robusta.

| Componente | Comportamento |
|------------|---------------|
| `progress_pct` | Calcolato da `progress_current/total`; mai azzerato da update step-only |
| Frontend | `computeScanJobProgressPct` fallback se backend manda pct 0/null |
| Loop fixture | `try/except/finally` per fixture; errore singola → excluded, job continua |
| Completed | `progress_current=total`, `progress_pct=100`, `finished_at`, `result_summary_json` |
| Stale | `updated_at` fermo >5 min **o** elapsed >30 min → `failed` (`stale_job_timeout`) |
| UI | Barra visibile con % reale; completed/failed con badge e retry |

## Cecchino Today — Fase 17 — Fix polling e selectedDay (v0.11)

Versione `cecchino_today_v0_11_scan_polling_fix`: correzione UX scan async e lifecycle job.

| Componente | Comportamento |
|------------|---------------|
| Frontend | Init mount-only; `selectedDay` preservato su refresh days/poll; polling per `job_id` + data |
| Timeline | `scan_status`, badge Scanning/Fallita/Scansionata; finestra centrata su giorno selezionato |
| Stale recovery | `queued` vecchi via `created_at`; `running` bloccati via `updated_at` o `started_at` >30 min |
| Runner | `SessionLocal` autonoma; `rollback` + mark `failed`; guard se thread esce senza stato terminale |
| GET `/days` | Campi `scan_status`, `active_job_id` (+ alias legacy `scan_job_*`) |

**UI:** progress card con elapsed time; pulsante «Scansione in corso» disabilitato; nessun auto-scan al cambio giorno.

## Cecchino Today — Fase 15 — Over/Under strict FT e PT (v0.9)

| Componente | Comportamento |
|------------|---------------|
| Over FT | Solo `Goals Over/Under` bet_id=5 → `OVER_1_5`, `OVER_2_5` |
| Over PT | Solo `Goals Over/Under First Half` (o `- First Half`) → `OVER_PT_0_5`, `OVER_PT_1_5` |
| Esclusi | Goal Line, Result/Total Goals, Total Home/Away, RTG_H1, combo, corner |
| Dettaglio quote | 10 righe stabili (1/X/2/1X/X2/12/OVER 1.5/2.5/OVER PT 0.5/1.5) |
| KPI | BOOK/MEDIA da media book; STATISTICA/CECCHINO/EDGE = `—` per Over |
| Debug raw | `over_under_full_time_debug` + `over_under_first_half_debug` con rejected |

**Eleggibilità:** invariata; Over e Over PT opzionali nel KPI.

## Cecchino Today — Fase 14 — Fixture ID e export JSON (v0.7)

| Componente | Comportamento |
|------------|---------------|
| Dettaglio quote | Righe OVER 1.5/2.5 **sempre visibili** (— se assenti) |
| `bookmaker_odds_detail` | 8 righe stabili con status not_available/partial/available |
| ID tecnici | Today, Local, API-Football copiabili; link a Bookmakers debug |
| Raw odds | `GET /api/admin/bookmakers/fixture-raw-odds` — solo book 8/3/4 |

## Cecchino Today — discovery giornaliera v0.2 (persistenza giornate)

Versione `cecchino_today_v0_2_persistent_days` — sostituita da v0.3 (Fase 9).

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
| Cecchino Today | `backend/app/services/cecchino/cecchino_today_service.py`, `cecchino_today_scan_job_service.py`, `cecchino_today_odds_fetch.py`, `backend/app/routes/cecchino_today.py` |
| Model | `backend/app/models/cecchino_prediction.py`, `cecchino_today_fixture.py` |
| UI | `frontend/src/pages/CecchinoPage.tsx`, `CecchinoTodayPage.tsx`, componenti `CecchinoToday*`, `cecchinoApi.ts`, `cecchinoTodayApi.ts` |
