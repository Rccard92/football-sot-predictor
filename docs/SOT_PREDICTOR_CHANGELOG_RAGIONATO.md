# SOT Predictor — Changelog ragionato

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
