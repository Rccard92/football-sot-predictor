# SOT Predictor — Changelog ragionato

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
