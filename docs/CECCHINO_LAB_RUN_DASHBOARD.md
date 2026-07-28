# Cecchino Lab â€” Dashboard analisi run storico

## Obiettivo

Dashboard **read-only** per visualizzare e analizzare ogni run storico del Cecchino Lab (pilota, bilanciato, completo, attivo, fallito, cancellato).

Legge esclusivamente tabelle `cecchino_lab_*` giÃ  persistite. **Non** riesegue scan, settlement, formule, nÃ© scrive snapshot/`summary_json`.

## Isolamento

- Nessuna modifica a Cecchino Today / Betfair / formule operative
- Servizio dedicato: `backend/app/services/cecchino_data_lab/historical_run_analytics_service.py`
- Aggregazioni pure condivise: `historical_analytics_agg.py` (riusate anche dal report AI ZIP) â€” stessa `analytics_aggregation_version` (`cecchino_lab_analytics_agg_v2_2`)
- Export segnali: `historical_signal_export.py` (`signal_export_schema_version=cecchino_lab_signal_export_v1`) — opportunità deduplicate vs celle legacy
- Route: `backend/app/routes/cecchino_lab.py` sotto `/api/cecchino-lab/historical-scans/{run_id}/dashboard/*`
- Frontend: `/cecchino-lab/historical-scans/:runId`

## Segnali A–F (dashboard)

Sezione a due livelli:

- **Opportunità uniche** — ROI/hit/overlap con F; mai sommare celle come scommesse
- **Celle attive** — diagnostica overlapping (`attribution_mode=overlapping`)
- `with_signal_active` non mostrato come sovrapposizione; etichette: «Opportunità uniche», «Celle attive», «Sovrapposizione con F», «F — modello corrente»
- Consenso **per mercato** (non ROI multi-mercato aggregato)

## Formulazioni obbligatorie

Usare: prestazioni osservate, pattern candidato, campione insufficiente / esplorativo / descrittivo, modulo osservazionale, quota Bet365 reale / derivata / N/D, risultati congelati.

**Non** dichiarare: profitto complessivo del Cecchino, modello vincitore, giocata migliore, somma HOME+DRAW+AWAY / Over+Under, Â«stabileÂ» fuori da `stable_candidate`.

## Coerenza report / dashboard

Report AI e dashboard usano le **stesse** funzioni pure in `historical_analytics_agg.py` per:

- conteggi real / derived / unavailable (+ riconciliazione)
- medie quote (`null` se assenti)
- fasce Rating / AcquistabilitÃ  / Aâ€“F / pattern / stabilitÃ

Differenze ammesse solo per **filtri** diversi, non per formule divergenti.
Ogni response rilevante espone `analytics_aggregation_version`.

## Quote e UI

- KPI / mercati: quote reali, derivate, **non disponibili**
- Medie odds e profit/ROI: `formatNullableNumber` / `—` se `null` (zero solo se `quote_count > 0`)
- Contatori: `with_cecchino_probability`, `with_cecchino_fair_quote`, `with_rating`
- Header: badge Scansione / Analytics / Aggregatore (`scan_source_git_commit` ≠ `analytics_runtime_git_commit`)
- Rating/Acquistabilità: vista primaria per mercato; warning mercati indipendenti; fascia `100` esclusiva

## Pattern Radar

- Sempre con `market_key` nel titolo
- Badge campione: Esplorativo / Descrittivo / Candidato da validare
- Badge stabilitÃ : Insufficiente / Concentrata / Incoerente / Coerente / Candidata stabile
- Sezione **Diagnostica copertura** separata (`diagnostics`)
- Warning campione piccolo; nessuna frase che suggerisca una giocata

## Filtri

Cumulabili su tutti gli endpoint analytics:

`competition`, `date_from`, `date_to`, `market_key`, `rating_band`, `purchasability_band`, `quote_quality`, `signal_model`, `signal_active`, `balance_class`, `goal_intensity_status`, `purchasability_status`, `eligibility_status`

Default performance: `eligible_core`. Esclusioni solo in sezione esclusioni/qualitÃ .

I filtri frontend restano in query string (URL condivisibile).

## Endpoint

| Path | Contenuto |
|------|-----------|
| `GET .../dashboard/overview` | run meta, progress, KPI, `scan_source_git_commit`, `analytics_runtime_git_commit*`, `analytics_aggregation_version`, `is_provisional` |
| `GET .../dashboard/markets` | 14 mercati indipendenti + unavailable + medie/profit null-safe |
| `GET .../dashboard/ratings` | matrice mercato × fascia Rating + warning indipendenza |
| `GET .../dashboard/purchasability` | primaria `by_market`; distribuzione globale diagnostica |
| `GET .../dashboard/signals` | modelli Aâ€“F (F = corrente) |
| `GET .../dashboard/balance` | 4 pilastri + combinazioni |
| `GET .../dashboard/goal-intensity` | 4 componenti GI |
| `GET .../dashboard/competitions` | League DNA |
| `GET .../dashboard/timeline` | cronologia su kickoff storico |
| `GET .../dashboard/patterns` | positive / negative / watchlist / unstable / **diagnostics** |
| `GET .../dashboard/exclusions` | motivi esclusione |
| `GET .../matches` | explorer (filtri estesi) |
| `GET .../matches/{snapshot_id}` | prematch vs result_after_lock |

## Sezioni UI

A Header Â· B Live progress Â· C V1 Pulse Â· D 14 mercati Â· E Rating Â· F AcquistabilitÃ  Â· G Segnali Aâ€“F Â· H Balance Â· I IntensitÃ  Goal Â· J League DNA Â· K Timeline Â· L Pattern Â· M Match explorer Â· N Esclusioni

Report download: riusa API ZIP esistenti (voce consigliata Â«Sintesi per ChatGPTÂ»). Rigenerabile dagli snapshot giÃ  presenti (nessuna nuova scansione).

## Run attivo vs completato

- Attivo: `is_provisional=true`, badge Â«Dati provvisoriÂ», polling overview ~4s / analytics ~20s
- Completato: `is_provisional=false`, badge Â«Risultati congelatiÂ», nessun polling continuo

Compatibile con Run #1, #2, #3 completo e run futuri (sola lettura).
