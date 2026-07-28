# Cecchino Lab — Dashboard analisi run storico

## Obiettivo

Dashboard **read-only** per visualizzare e analizzare ogni run storico del Cecchino Lab (pilota, bilanciato, completo, attivo, fallito, cancellato).

Legge esclusivamente tabelle `cecchino_lab_*` già persistite. **Non** riesegue scan, settlement, formule, né scrive snapshot/`summary_json`.

## Isolamento

- Nessuna modifica a Cecchino Today / Betfair / formule operative
- Servizio dedicato: `backend/app/services/cecchino_data_lab/historical_run_analytics_service.py`
- Aggregazioni pure condivise: `historical_analytics_agg.py` (riusate anche dal report AI ZIP)
- Route: `backend/app/routes/cecchino_lab.py` sotto `/api/cecchino-lab/historical-scans/{run_id}/dashboard/*`
- Frontend: `/cecchino-lab/historical-scans/:runId`

## Formulazioni obbligatorie

Usare: prestazioni osservate, pattern candidato, campione insufficiente, modulo osservazionale, quota Bet365 reale / derivata, risultati congelati.

**Non** dichiarare: profitto complessivo del Cecchino, modello vincitore, giocata migliore, somma HOME+DRAW+AWAY / Over+Under.

## Filtri

Cumulabili su tutti gli endpoint analytics:

`competition`, `date_from`, `date_to`, `market_key`, `rating_band`, `purchasability_band`, `quote_quality`, `signal_model`, `signal_active`, `balance_class`, `goal_intensity_status`, `purchasability_status`, `eligibility_status`

Default performance: `eligible_core`. Esclusioni solo in sezione esclusioni/qualità.

I filtri frontend restano in query string (URL condivisibile).

## Endpoint

| Path | Contenuto |
|------|-----------|
| `GET .../dashboard/overview` | run meta, progress, KPI, module coverage, `is_provisional` |
| `GET .../dashboard/markets` | 14 mercati indipendenti |
| `GET .../dashboard/ratings` | matrice mercato × fascia Rating |
| `GET .../dashboard/purchasability` | fasce granulari + cross |
| `GET .../dashboard/signals` | modelli A–F (F = corrente) |
| `GET .../dashboard/balance` | 4 pilastri + combinazioni |
| `GET .../dashboard/goal-intensity` | 4 componenti GI |
| `GET .../dashboard/competitions` | League DNA |
| `GET .../dashboard/timeline` | cronologia su kickoff storico |
| `GET .../dashboard/patterns` | positive / negative / watchlist / unstable |
| `GET .../dashboard/exclusions` | motivi esclusione |
| `GET .../matches` | explorer (filtri estesi) |
| `GET .../matches/{snapshot_id}` | prematch vs result_after_lock |

## Sezioni UI

A Header · B Live progress · C V1 Pulse · D 14 mercati · E Rating · F Acquistabilità · G Segnali A–F · H Balance · I Intensità Goal · J League DNA · K Timeline · L Pattern · M Match explorer · N Esclusioni

Report download: riusa API ZIP esistenti (voce consigliata «Sintesi per ChatGPT»).

## Run attivo vs completato

- Attivo: `is_provisional=true`, badge «Dati provvisori», polling overview ~4s / analytics ~20s
- Completato: `is_provisional=false`, badge «Risultati congelati», nessun polling continuo

## Cache

In-memory (no Redis): TTL 15s se attivo, 180s se terminale. Key = run_id + endpoint + filtri + matches_processed + status + updated_at. Max 256 entry.

## Profitto

- Reale: solo quote Bet365 presenti
- Sintetico: separato
- Nessun totale globale aggregato sui 14 mercati

## Compatibilità

Funziona con Run #1, Run #2, run completo 2021/2022 e run futuri senza migration.

## Test

- Backend: `tests/test_cecchino_lab_historical_run_dashboard.py`
- Frontend: helper filtri/route in `cecchinoLabApi.test.ts` + Vitest
