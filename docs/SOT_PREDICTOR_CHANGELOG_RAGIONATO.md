# SOT Predictor — Changelog ragionato

## Cecchino — Fase 28 — Nuovi pesi goal market KPI confermato (2026-06-08)

- Pannello KPI Betfair-only confermato nella struttura finale (colonne, layout, mapping quote invariati).
- Aggiornati i pesi dei picchetti per i mercati goal Over/Under FT e PT.
- Totali stagione ridotto al 10%; Casa/Fuori mantenuto al 20%; Ultime 6 totali al 35%; Ultime 5 casa/fuori aumentato al 35%.
- I pesi 1/X/2 restano invariati (25/20/35/20) — costanti separate `CECCHINO_1X2_WEIGHTS` e `CECCHINO_GOAL_MARKET_WEIGHTS`.
- `goal_market_poisson_empirical_v2` aggiornato: lambda, probabilità empirica e reliability con pesi 10/20/35/35.
- Rinormalizzazione pesi quando un contesto è escluso; debug con `original_weight`, `effective_weight`, `weight_renormalized`.
- Debug Picchetti e JSON KPI (`cecchino_goal_odds_used`) aggiornati con sezione `weights` per mercato goal.
- Nessuna modifica ai modelli SOT v2.0/v2.1 né a `team_sot_predictions`.

## Cecchino — Fase 27 — Goal market Poisson + storico (2026-06-08)

- Introdotto modello `goal_market_poisson_empirical_v2` per i 7 mercati Over/Under.
- Sostituita Excel parity come formula principale KPI; soglie 1.5 / 2.5 / 3.5 ora producono quote distinte.
- Calcolo basato su gol attesi (lambda da 4 contesti picchetti), distribuzione Poisson e hit-rate storico.
- Blend 65% Poisson + 35% empirico con reliability shrinkage verso probabilità lega quando disponibile.
- Mercati PT con lambda HT e hit-rate su fixture con score primo tempo valido.
- Excel parity mantenuta solo come `legacy_excel_parity` nel debug (non usata nel KPI).
- Debug Picchetti v3: card summary, tabella contesti, accordion dettaglio tecnico.
- JSON KPI: `cecchino_goal_odds_used` con summary, contexts, legacy.
- Nessuna modifica ai modelli SOT v2.0/v2.1.

## Cecchino — Fase 26 — Formule goal da fogli OVER/UNDER Excel (2026-06-08)

- Analizzati fogli OVER e UNDER di `AutomazioneCecchino.xlsm` (riferimento esterno, non in repo).
- Aggiunte formule Quota Cecchino per Over 1.5 e Over 2.5 (`over_under_fulltime_excel_parity_v1`, divisori 6/11/16).
- Aggiunte formule Quota Cecchino per Under 2.5 e Under 3.5 (divisori 4/9/14).
- Formule full time: media di tre blocchi (casa/fuori, totals, mixed); Over 1.5 = Over 2.5; Under 2.5 = Under 3.5 (parità Excel).
- Formule primo tempo `first_half_rate_to_odd_v1`: Over PT 0.5, Over PT 1.5, Under PT 1.5 (rate HT → prob → 1/prob).
- Storico goal da fixture DB PIT (`build_goal_fixture_slices`); halftime da `raw_json.score.halftime`.
- `goal_markets` persistito in `cecchino_output_json`; KPI Betfair-only popola `quota_cecchino` OU quando dati sufficienti.
- Debug Picchetti v2: tab Over FT, Under FT, Primo tempo; `missing_formulas` dinamico.
- JSON KPI: sezione `cecchino_goal_odds_used` con breakdown formule.
- Nessuna modifica ai modelli SOT v2.0/v2.1.

## Cecchino — Fase 25 — Debug Picchetti Quota Cecchino (2026-06-08)

- Aggiunta sezione Debug Picchetti nel dettaglio analisi (accordion chiuso di default).
- Mostrati pesi totals/home_away/last6_totals/last5_home_away.
- Mostrato breakdown quote Cecchino per 1/X/2 con campioni, record W/D/L, probabilità, quote picchetto e contributi ponderati.
- Aggiunta derivazione 1X/X2/12 da probabilità implicite 1/X/2.
- Indicate formule ancora mancanti per Over/Under (nessuna formula inventata).
- Aggiunto controllo coerenza tra debug e colonna Quota Cecchino del KPI.
- Endpoint `GET /api/cecchino/today/{id}/picchetti-debug` e summary leggero nel detail.
- Nessuna modifica ai modelli SOT v2.0/v2.1.

## Cecchino — Fase 24 — Pulizia toolbar KPI Betfair (2026-06-08)

- Rimossi pulsanti tecnici dal Pannello KPI.
- Spostato Aggiorna quote Betfair nella toolbar principale.
- Endpoint JSON/debug mantenuti ma non visibili nel pannello.
- Pannello KPI più pulito.
- Nessuna modifica a formule Cecchino/KPI.
- Nessuna modifica a SOT v2.0/v2.1.

## Cecchino — Fase 23 — Refresh quote Betfair singola fixture (2026-06-08)

- Aggiunto metadata timestamp quote in `odds_snapshot_json.odds_meta` (source, fetched_at, is_cached, last_betfair_refresh_at).
- Nuovo refresh on-demand per singola fixture: `POST /api/cecchino/today/{id}/refresh-betfair-odds` con confronto before/after 1X2 e rebuild KPI.
- Fetch live usa solo Betfair (bookmaker_id=3), bypass cache snapshot, tracking API usage con job_id dedicato.
- Nuovo export diagnostico `GET /api/cecchino/today/{id}/betfair-markets-json` con tutti i mercati Betfair del payload raw.
- UI Pannello KPI: pulsante Aggiorna quote Betfair, download/copia JSON mercati, box timestamp; aggiornamento KPI senza reload pagina.
- Nessuna modifica ai modelli SOT v2.0/v2.1 né alla pipeline scan giornata intera.

## Cecchino — Fase 22 — Cleanup dettaglio analisi e debug JSON KPI Betfair (2026-06-08)

- Rimosse dal dettaglio analisi le card Quote finali Cecchino e Dettaglio quote Betfair; il Pannello KPI resta l’unico riferimento per quote e metriche.
- Ridisegnata la card partite eleggibili: orario, stato, squadre, predizione consigliata, risultato PT/FT e CTA Apri/Rivedi analisi.
- Aggiunto supporto risultato primo tempo e finale nelle card (`score.halftime` / `score.fulltime`).
- Rafforzato mapping Betfair 1/X/2 tramite solo `Match Winner` con selection per nome (inclusi nomi squadra).
- Rafforzato mapping Double Chance raw o derivato da 1X2 con `book_source` tracciabile.
- Aggiunto endpoint `GET /api/cecchino/today/{id}/kpi-debug-json` e pulsanti Scarica/Copia JSON KPI nel pannello.
- JSON debug filtrato solo su Betfair con `raw_market_name`, `raw_value` e `source` per ogni quota.
- Nessuna modifica ai modelli SOT v2.0/v2.1.

## Cecchino — Fase 21 — Fix KPI Betfair rows e quote book (2026-06-08)

- Corretta colonna SEGNO vuota: ogni riga KPI espone `segno` e `label`; frontend con fallback `segno || label || market_key`.
- Quota Book Betfair costruita da raw/snapshot (`build_betfair_payload_from_raw`) prima del DB; rebuild automatico in `get_today_fixture_detail`.
- Corretta derivazione DC da 1X2: probabilità implicite decimali `1/quota` invece di `100/quota`.
- Layout desktop Cecchino Today 32%/68%; pannello KPI senza overflow orizzontale; colonna SEGNO 12%.
- Nessuna modifica ai modelli SOT v2.0/v2.1, formule Cecchino 1/X/2 né segnali SI/NO.

## Cecchino — Fase 20 — KPI Betfair-only e nuovo rating panel (2026-06-08)

- Sostituito il vecchio Pannello KPI con lo schema a 9 colonne: Segno, Quota Book, Quota Cecchino, Prob. Book, Prob. Cecchino, Vantaggio Prob., Edge %, Score Acquisto, Rating 0-100.
- Bookmaker di riferimento Cecchino Today diventato solo **Betfair** (API-Football id 3); rimossi Bet365 e Pinnacle dalla pipeline Today.
- Rimossa media bookmaker dal KPI e dal dettaglio quote; gate bookmaker richiede solo Betfair 1X2 completo.
- Ridotte chiamate API odds: single-call fixture + filtro bookmaker_id=3; fallback solo su Betfair.
- Aggiunti mercati Under 2.5, Under 3.5 e Under PT1.5 nel dettaglio quote e nelle righe KPI (quota Cecchino `—` finché senza formula).
- Rating 0-100 con label Elite/Premium/Forte/Buona/Sufficiente/Debole/Scarto; UI ottimizzata senza scrollbar orizzontale desktop.
- Nessuna modifica ai modelli SOT v2.0/v2.1, formule Cecchino 1/X/2 né segnali SI/NO.

## Cecchino — Fase 19 — Gate progressivi e riduzione consumo API (2026-06-04)

- Tutte le fixture della giornata vengono censite (`eligibility_status=discovered`) prima dei gate.
- Short-circuit per fixture: competition → odds → bookmaker → stats → Cecchino; stop immediato al primo fallimento.
- Negative cache odds (`negative_cache_until`, 6h) evita richiamate API su fixture già escluse per bookmaker/1X2.
- Cache bootstrap lega (`cecchino_league_stats_cache`, TTL 12h/24h) deduplica `teams` + `fixtures FT`.
- Tabella `api_usage_events` + `GET /admin/api-usage/summary`; budget guard (7500/giorno, max 1000/job, stop a 500 residui).
- `update-results` ottimizzato: 1× `fixtures?date=`; `revalidate-day` resta offline-only.
- UI: consumo API nel box job, funnel esclusioni post-scan; nessuna modifica SOT v2.0/v2.1.

## Cecchino — Fase 18 — Fix progress bar e finalizzazione scan job (2026-06-04)

- Corretto calcolo `progress_pct`: gli update step-only non azzerano più la percentuale (merge con stato job DB).
- Aggiunto fallback frontend `computeScanJobProgressPct` da `progress_current/progress_total`.
- Progress bar riflette l'avanzamento reale (208/433 ≈ 48%, 432/433 ≈ 99.8%, completed = 100%).
- Loop fixture con `finally` per progress garantito e log `provider_fixture_id`; errore singola fixture non blocca il job.
- Finalizzazione `completed` imposta `progress_current`, `progress_total`, `progress_pct=100`, `finished_at`.
- Stale job più aggressivo: `updated_at` fermo >5 min o elapsed >30 min → `failed`.
- UI completed/failed con barra, badge e retry; nessuna modifica ai modelli SOT v2.0/v2.1.

## Cecchino — Fase 17 — Fix polling scan job e selectedDay persistente (2026-06-04)

- Corretto reset di `selectedDay` a oggi dopo refresh timeline/polling (init effect instabile con dipendenza da `activeJob`).
- Polling agganciato al job della data selezionata; `activePollRef` evita doppio attach e stop al cambio giorno.
- Click su giorno in scanning non riporta più a oggi; timeline centrata sulla data selezionata.
- Background job usa `SessionLocal` autonoma; eccezioni marcano `failed` con rollback e guard in `finally`.
- Stale job recovery estesa a `queued` (via `created_at`) e `running` (via `updated_at`/`started_at`).
- GET `/days` espone `scan_status` e `active_job_id`; progress card con elapsed time e header disabilitato durante scan.
- Scan completed ricarica la giornata selezionata, non oggi; nessuna modifica ai modelli SOT v2.0/v2.1.

## Cecchino — Fase 16 — Scan asincrona e polling Today (2026-06-04)

- Scan giornaliera spostata su job asincrono persistito (`cecchino_today_scan_jobs`) con thread daemon e stato su DB.
- Nuovi endpoint: `POST /scan-day/start`, `GET /scan-jobs/{job_id}`, `GET /scan-jobs/latest?date=`; `POST /scan-day` delega al job (param `sync=true` solo debug).
- Progress step-by-step (`fetching_fixtures` → … → `completed`), contatori fixture/odds/eleggibili/escluse, `result_summary_json` con metriche API.
- Ottimizzazione odds: singola chiamata `GET /odds?fixture=` con filtro Bet365/Betfair/Pinnacle; fallback selettivo o per-bookmaker; cache da `odds_snapshot_json` se `force_rescan=false`.
- Prevenzione job duplicati (stesso `scan_date` running → job esistente) e stale job (>30 min → `failed`).
- Frontend: polling ogni 2,5s, card progresso, badge «Scanning» in timeline; niente timeout browser 180s sullo start.
- Nessuna modifica ai modelli SOT v2.0/v2.1 né alle formule Cecchino/eligibility gate.

## Cecchino — Fase 15 — Over/Under full time e primo tempo bookmaker (2026-06-04)

- Corretto mapping Over 1.5 / Over 2.5 usando solo mercato `Goals Over/Under` con bet_id=5.
- Aggiunto mapping Over PT 0.5 / Over PT 1.5 usando mercato `Goals Over/Under First Half` (variante `Goals Over/Under - First Half` accettata).
- Esclusi mercati ambigui come Goal Line, Result/Total Goals, Total - Home/Away, RTG_H1 dal feed principale Over.
- Aggiunte righe OVER PT 0.5 e OVER PT 1.5 al dettaglio quote bookmaker (10 righe stabili).
- Aggiunte righe OVER PT 0.5 e OVER PT 1.5 al Pannello KPI; BOOK e MEDIA popolati solo da quote bookmaker tracciate.
- Nessun edge calcolato senza quota Cecchino; STATISTICA e CECCHINO restano `—` per i mercati Over.
- Debug raw odds separato in `over_under_full_time_debug` e `over_under_first_half_debug` con mercati scartati.
- Nessuna modifica ai modelli SOT v2.0/v2.1.

## Cecchino — Fase 14 — Fixture ID e JSON raw odds filtrato (2026-06-04)

- Ripristinate righe Over 1.5 e Over 2.5 sempre visibili nel dettaglio quote bookmaker.
- Aggiunta esposizione `provider_fixture_id` API-Football e `fixture_ids` nel dettaglio Cecchino Today.
- Nuovo endpoint `GET /api/admin/bookmakers/fixture-raw-odds` con JSON filtrato Bet365/Betfair/Pinnacle.
- UI Bookmakers: copy/download JSON, summary Over 1.5/2.5, prefill da query param.
- Campo `bookmaker_odds_detail` con 8 righe stabili; media Over solo da book whitelist.
- Nessuna modifica ai modelli SOT v2.0/v2.1.

## Cecchino — Fase 13 — Debug mercati Over/Under bookmaker (2026-06-04)

- Aggiunto debug raw markets per fixture/bookmaker (`GET /api/admin/bookmakers/fixture-markets-debug`).
- Verificata disponibilità Over 1.5 e Over 2.5 da API-Football (mercato `Goals Over/Under`, bet id 5).
- Migliorata normalizzazione `OVER_UNDER_GOALS` con `normalize_api_football_market` e `normalize_over_under_selection`.
- Scan-day persiste quote OU in `fixture_bookmaker_odds` con `provider_bookmaker_id` corretto.
- Corretta media book Over: derivata solo dai tre bookmaker visibili; KPI espone dettaglio per-book.
- Impedita incoerenza media valorizzata con singoli bookmaker vuoti nel dettaglio Cecchino.
- Nessuna modifica ai modelli SOT v2.0/v2.1.

## Cecchino — Fase 12 — Fix idempotenza scan-day e upsert leghe (2026-06-04)

- Corretto errore duplicate key su `leagues.api_league_id` (es. Uruguay 268) che causava HTTP 500 su scan-day.
- Introdotto `league_ingest_helpers.py` con get-or-create idempotente per League, Season, Competition e safe upsert Team (savepoint + recovery IntegrityError).
- Evitato `PendingRollbackError`: rollback sessione + savepoint per fixture in bootstrap.
- Errori mapping → `excluded_mapping_error` con `blocking_reasons` (`league_upsert_error`); scan continua sulle altre partite.
- Report scan arricchito con `errors` e `excluded_summary`.
- Versione `cecchino_today_v0_5_scan_idempotency`; v2.0/v2.1 e `team_sot_predictions` non modificati.

## Cecchino — Fase 11 — Final eligibility gate e esclusione dati incompleti (2026-06-04)

- Introdotto validatore finale `validate_cecchino_today_final_eligibility`: una partita è `eligible` solo se bookmaker 1X2 completi, statistiche sufficienti, picchetti obbligatori, quote finali Cecchino e KPI 1X2 sono tutti disponibili.
- `low_sample` sotto soglia, `zero_probability`, `missing_picchetto_quotas` e `final_odds insufficient_data` diventano bloccanti ed escludono dalla lista principale.
- `fixtures_ft_imported` spostato da warning ad `import_info` (non compare più come avviso giallo).
- Endpoint admin `POST /api/admin/cecchino/today/revalidate-day` per riclassificare snapshot già salvati senza richiamare API-Football.
- GET `/today` restituisce solo `eligibility_status=eligible`; escluse arricchite con `blocking_reasons`, `cecchino_debug`, `kpi_debug`.
- Versione `cecchino_today_v0_4_final_eligibility_gate`; migrazione `blocking_reasons_json`.
- v2.0/v2.1 e `team_sot_predictions` non modificati.

## Cecchino — Fase 10 — Refinement timeline e card partite (2026-06-04)

- Rimossa scrollbar visibile dalla timeline; aggiunte frecce avanti/indietro con finestra paginata (3/5/7 giorni).
- Timeline centrata su oggi all’apertura; `selectedDay` invariato durante navigazione frecce.
- Lista partite resa sticky su desktop con scroll interno.
- Card partite riorganizzate: predizione e risultato in riga secondaria; solo CTA a destra nella riga principale.
- Debug escluse spostato sotto grid lista/dettaglio; filtri, bandiere, loghi e raggruppamento invariati.
- Nessuna modifica logica Cecchino/KPI/segnali; v2.0/v2.1 non toccati.

## Cecchino — Fase 9 — Timeline giornaliera, filtri e risultati finali (2026-06-04)

- Versione `cecchino_today_v0_3_timeline_results`: timeline orizzontale ±7 giorni con oggi evidenziato e count eleggibili per giorno.
- Scan per giornata selezionata (`POST scan-day`) con `force_rescan`; mantenuti scan-today/scan-tomorrow.
- `POST update-results` aggiorna stato/score eleggibili persistite; non rimuove partite finite dalla lista.
- GET `/today` arricchito: summary, filters, score, loghi, placeholder predizione consigliata.
- UI: filtri stato/nazione/campionato/ricerca client-side; card raggruppate per nazione/campionato; rimossi badge Bet365/Betfair/Pinnacle/Stats dalle card.
- Migrazione colonne display: score, loghi, `match_display_status`.
- v2.0/v2.1 e `team_sot_predictions` non modificati.

## Cecchino — Fase 8 — Today persistente, scan oggi/domani e storico 7 giorni (2026-06-04)

- Versione `cecchino_today_v0_2_persistent_days`: snapshot per `scan_date` indipendenti (scan domani non cancella oggi).
- Endpoint: `GET /api/cecchino/today/days`, `POST .../scan-today`, `POST .../scan-tomorrow`, `POST .../cleanup`, `GET .../debug-search`, escluse arricchite con debug bookmaker/stats.
- Retention automatica post-scan: elimina solo `scan_date < oggi - 7` (Europe/Rome); oggi/domani/future protetti.
- UI `/cecchino-today`: pill giornate (Oggi/Domani/storico), pulsanti scan oggi/domani (no date picker), empty state per giornata non scansionata, pannello escluse collapsible, dettaglio verticale Quote → Segnali.
- Report scan: `fixtures_found`, `top_exclusion_reasons`; lista pubblica include `scan_meta`.
- v2.0/v2.1 e `team_sot_predictions` non modificati.

## Cecchino — Fase 7 — Restyling UI/UX dashboard Today (2026-06-04)

- Redesign pagina `/cecchino-today`: layout 2 colonne (38% lista / 62% dettaglio), sfondo chiaro allineato al layout globale.
- Nuove card partite con micro-badge bookmaker/stats, stati selezione/hover, empty state e skeleton loading.
- Header dettaglio partita dedicato; KPI Today-only (`CecchinoTodayKpiPanel`) con EDGE colorato e tabella più leggibile.
- Dettaglio quote bookmaker in card secondaria separata dal KPI principale.
- Segnali e quote finali affiancate su desktop; riuso `CecchinoFinalOddsDashboard` con highlight best side.
- Nessuna modifica alla logica di business Cecchino, formule KPI/segnali, filtri o backend.
- v2.0/v2.1 e `team_sot_predictions` non modificati.

## Cecchino — Fase 6 — Cecchino Today manual discovery (2026-06-04)

- Versione `cecchino_today_v0_1_manual_discovery`: scan manuale partite odierne via API-Football (`GET fixtures?date=`).
- Filtri competizione (no coppe/femminili/amichevoli/youth), gate quote strict 3 bookmaker 1X2, bootstrap DB minimo Cecchino-only (teams + fixture FT, no SOT).
- Gate statistiche + leakage; calcolo Cecchino + KPI; snapshot in `cecchino_today_fixtures`.
- Endpoint: `POST /api/admin/cecchino/today/scan`, `GET /api/cecchino/today`, dettaglio, `GET .../excluded` admin.
- UI `/cecchino-today`; fix regressione DC Cecchino nel pannello KPI (`1/(prob_1+prob_x)`).
- v2.0/v2.1 e `team_sot_predictions` non modificati.

## Cecchino — Fase 4 — Bookmaker odds e Pannello KPI (2026-06-04)

- Versione `cecchino_v0_4_bookmaker_kpi`; whitelist API-Football Bet365 (8), Betfair (3), Pinnacle (4).
- Import quote per fixture / prossimo turno → `fixture_bookmaker_odds` (righe per `selection_key`).
- Medie bookmaker, doppie chance derivate da 1X2, pannello KPI tab DASHBOARD (STATISTICA / CECCHINO / BOOK / MEDIA / EDGE).
- Endpoint: `POST .../cecchino/bookmakers/sync-next-round`, `GET .../bookmaker-odds`; `kpi_panel` nel dettaglio fixture.
- v2.0/v2.1 e `team_sot_predictions` non modificati.

## Bookmakers — Discovery provider e mercati odds (2026-06-04)

- Tabelle `bookmaker_markets` e `fixture_bookmaker_odds` (unique per competizione/fixture/fonte/bookmaker/mercato).
- Endpoint: `GET /api/admin/bookmakers/providers`, `GET .../markets`, `GET /api/admin/competitions/{id}/bookmakers/coverage`, `POST .../sync-next-round-odds`.
- UI Bookmakers: card provider, lista unificata, mercati normalizzati (`UNKNOWN` evidenziato), coverage prossimo turno, sync 1X2 competition-scoped.
- Sync 1X2 via SportAPI (API-Football lista bookmaker only fino a integrazione odds fixture); snapshot legacy `sportapi_fixture_odds_snapshots` invariato.
- Cecchino e SOT v2.0/v2.1 non modificati.

## Cecchino — Fase 3 — Matrice segnali SI/NO da Excel (2026-06-04)

- Versione backend `cecchino_v0_3_signals_matrix`; cache v0.2 senza matrice → ricalcolo.
- Implementate formule reali del foglio CECCHINO (F32–F36 input, righe D39–D60) senza segnali inventati.
- Segnali: UNDER/UNDER PT, SEGNO X, OVER/OVER PT, 1, 1X, 2, X2, 12; indice affidabilità da sample picchetto casa/trasferta.
- UI: tabella Excel D/E/F/G + card affidabilità; stato `insufficient_data` se quote finali assenti.
- Nessun uso di `team_sot_predictions` né output SOT; v2.0 e v2.1 invariati.

## Cecchino — Fase 2 — Recupero dati reali e tracciabilità input (2026-06-04)

- Rimossi dalla UI i testi descrittivi sul modulo separato da SOT (il modulo resta tecnicamente isolato).
- Introdotto `cecchino_v0_2_real_records`: nuove righe in `cecchino_predictions`; le cache `cecchino_v0_1_excel_parity` con `input_snapshot` nullo o formato legacy non vengono più servite.
- Recupero W/D/L da fixture finite (competition-scoped, PIT su kickoff) tramite `cecchino_fixture_history` e helper condivisi solo su tabelle fixture (`_prior_fixtures_for_team`, `team_split_fixtures`, `last_n`).
- **Non** usa `team_sot_predictions`, output v2.0/v2.1, `model_version` SOT, audit o pick SOT.
- `input_snapshot` con 8 slice (`label`, `wdl`, `sample_count`, `status`, …) e `data_quality.leakage_check` come oggetto con `status`, `target_kickoff`, `max_source_fixture_date`, `checked_at`.
- Endpoint invariati; query `recalculate` / `force_recalculate` per forzare ricalcolo singola fixture.
- v2.0 e v2.1: nessuna modifica.

Vedi anche [SOT_PREDICTOR_CECCHINO.md](./SOT_PREDICTOR_CECCHINO.md).
