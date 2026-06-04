# Catalogo dati e endpoint API

Catalogo aggiornato delle fonti dati, tabelle PostgreSQL ed endpoint del backend SOT Predictor.

Contesto: [PROJECT_CONTEXT.md](./PROJECT_CONTEXT.md). Pipeline admin: [ADMIN_PIPELINE.md](./ADMIN_PIPELINE.md).

---

## Fonti dati esterne

### API-Football / API-Sports

| Aspetto | Dettaglio |
|---------|-----------|
| **Cosa fornisce** | Leghe/competitions, squadre, fixture, statistiche squadra (incluso `expected_goals`), statistiche giocatore per partita, formazioni, classifica, arbitri |
| **Config** | `API_FOOTBALL_KEY`, base URL API-Sports |
| **Tabelle DB** | `leagues`, `seasons`, `teams`, `players`, `fixtures`, `fixture_team_stats`, `fixture_player_stats`, `player_match_stats`, `fixture_lineups`, `fixture_lineup_players`, `standings_snapshots`, `standing_entries`, `referees`, `fixture_referees`, `referee_season_profiles` |
| **Servizi/route** | `CompetitionIngestionService`, `IngestionService` (legacy Serie A), route admin ingest, `admin_referees` |
| **Uso modello** | **Sì** — stats squadra, xG, profili giocatore alimentano v1.1, v2.1; formazioni AF sono complementari |
| **Solo debug/audit** | Scan catalogo API (`admin_debug_api_football_catalog`), summary expected-goals |
| **Rischi/limiti** | Rate limit giornaliero; `expected_goals` non sempre presente per tutte le leghe/stagioni; ritardo aggiornamento post-partita |

**Campi chiave per il modello:**
- `fixture_team_stats.expected_goals` → xG reali v2.1 macro `chance_quality` (no proxy)
- `fixture_team_stats.shots_on_goal`, `total_shots`, `passes`, `passes_accuracy`, `ball_possession` → macro offensive/pace
- `player_match_stats` → costruzione `player_season_profiles`

### SportAPI / RapidAPI

| Aspetto | Dettaglio |
|---------|-----------|
| **Cosa fornisce** | Mapping fixture (provider event id), formazioni probabili/ufficiali (`confirmed` true/false), missing players, quote/bookmaker |
| **Config** | `SPORTAPI_ENABLED=true`, `SPORTAPI_RAPIDAPI_KEY` |
| **Tabelle DB** | `fixture_provider_mappings`, `fixture_provider_lineups`, `fixture_provider_lineup_players`, `fixture_missing_players`, `player_provider_mappings`, `fixture_lineup_refresh_impacts`, `sportapi_odds_providers`, `sportapi_fixture_odds_snapshots`, `sportapi_odds_market_mappings` |
| **Servizi/route** | `CompetitionSportApiLineupService`, `sportapi_lineup_service`, `admin_sportapi`, `admin_bookmakers`, job pre-match |
| **Uso modello** | **Sì** — v2.0 (fattori lineup), v2.1 (macro lineups/infortuni/player) |
| **Solo debug/audit** | Debug fixture, player-matching, mapping debug, odds discovery |
| **Rischi/limiti** | Affidabilità formazioni probabili; mapping auto solo con confidence ≥90; feed indisponibile se non configurato; quote SOT non sempre disponibili per tutti i provider |

**Limiti affidabilità:**
- Formazioni **probabili** (`confirmed=false`) → confidence ridotta, non certezza
- Missing players possono essere incompleti
- Mapping errato → impact lineup distorto (conferma manuale admin disponibile)

### PostgreSQL (DB interno)

| Aspetto | Dettaglio |
|---------|-----------|
| **Cosa fornisce** | Persistenza di tutti i dati ingeriti, predizioni, profili, pick tracciate, odds |
| **Tabelle attese** | Vedi sezione [Tabelle DB](#tabelle-db) |
| **Check schema** | `GET /api/admin/db/check` — **DA VERIFICARE:** `db_tables.py` non elenca `competitions`, standings, referees |
| **Uso modello** | Fonte primaria per aggregati pre-kickoff e predizioni salvate |

### Railway cron / jobs

| Aspetto | Dettaglio |
|---------|-----------|
| **Cosa fornisce** | Esecuzione schedulata job pre-match |
| **Endpoint** | `POST /api/admin/jobs/pre-match-official-lineups/run` |
| **Auth** | `CRON_SECRET` / `ADMIN_CRON_SECRET` (header `X-Admin-Cron-Secret` o Bearer); Admin UI senza secret |
| **Tabelle DB** | Aggiorna SportAPI lineups, `team_sot_predictions` (v2.0), `fixture_lineup_refresh_impacts`, `tracked_betting_picks` |
| **Uso modello** | Refresh lineups ufficiali pre-kickoff → rigenera v2.0 |
| **DA VERIFICARE** | Schedule Railway/cron non presente nel repository (solo endpoint + `.env.example`) |

### Odds / Bookmakers

| Aspetto | Dettaglio |
|---------|-----------|
| **Cosa fornisce** | Provider SportAPI, quote 1X2, mercati SOT, discovery mercati |
| **Tabelle DB** | `odds_bookmakers`, `odds_discovery_snapshots`, `sportapi_odds_providers`, `sportapi_fixture_odds_snapshots`, `sportapi_odds_market_mappings` |
| **Route** | `/api/admin/bookmakers/*` |
| **Uso modello** | **No** — solo confronto operativo in pagina Bookmakers |
| **Rischi/limiti** | Mercati SOT non uniformi tra provider; discovery manuale/periodica |

---

## Tabelle DB

### Core multi-campionato

| Tabella | Modello | Contenuto |
|---------|---------|-----------|
| `competitions` | `Competition` | Campionato attivo: `key`, `provider_league_id`, `season`, `league_id`, `season_id`, `pre_match_cron_enabled`, `is_primary` |
| `fixtures` | `Fixture` | Partite con `competition_id`, kickoff, status, round |
| `fixture_team_stats` | `FixtureTeamStat` | Stats squadra per partita, incluso `expected_goals` |

### Predizioni e feature

| Tabella | Contenuto |
|---------|-----------|
| `team_sot_predictions` | Predizioni SOT per fixture/squadra/`model_version` |
| `cecchino_predictions` | Predizioni Cecchino 1X2 per fixture/`cecchino_version` (modulo separato da SOT) |
| `team_sot_features` | Feature store (legacy) |
| `team_sot_prediction_adjustments` | Aggiustamenti predizione |
| `player_season_profiles` | Profili stagionali giocatore per `competition_id` |
| `player_match_stats` | Stats giocatore per partita |
| `player_team_seasons` | Associazione giocatore-squadra-stagione |

### Lineups e provider

| Tabella | Contenuto |
|---------|-----------|
| `fixture_lineups` | Formazioni API-Football |
| `fixture_lineup_players` | Giocatori in formazione AF |
| `fixture_provider_mappings` | Mapping fixture ↔ evento SportAPI |
| `fixture_provider_lineups` | Formazioni SportAPI (probabili/ufficiali) |
| `fixture_provider_lineup_players` | Giocatori in formazione SportAPI |
| `fixture_missing_players` | Indisponibili SportAPI |
| `fixture_lineup_refresh_impacts` | Snapshot impatto pre/post refresh lineup |
| `player_provider_mappings` | Mapping giocatore ↔ provider SportAPI |

### Monitoraggio e odds

| Tabella | Contenuto |
|---------|-----------|
| `tracked_betting_picks` | Pick tracciate per monitoraggio giocate |
| `odds_bookmakers` | Bookmaker sincronizzati |
| `odds_discovery_snapshots` | Snapshot discovery odds |
| `sportapi_odds_providers` | Provider SportAPI |
| `sportapi_fixture_odds_snapshots` | Quote per fixture |
| `sportapi_odds_market_mappings` | Mapping mercati SOT |

### Standings e arbitri

| Tabella | Contenuto |
|---------|-----------|
| `standings_snapshots` | Snapshot classifica |
| `standing_entries` | Righe classifica |
| `referees` | Anagrafica arbitri |
| `fixture_referees` | Arbitro per fixture |
| `referee_season_profiles` | Profilo stagionale arbitro |
| `referee_fixture_card_summaries` | Summary cartellini arbitro |

### Ingestion e legacy

| Tabella | Contenuto |
|---------|-----------|
| `ingestion_runs` | Log run ingestion |
| `prediction_backtests` | Risultati backtest |
| `player_sot_profiles` | Profili SOT legacy |
| `player_availability` / `player_availability_events` | Disponibilità giocatore (legacy) |

> **DA VERIFICARE:** `backend/app/core/db_tables.py` (`EXPECTED_TABLES`) non include `competitions`, standings, referees, `team_sot_prediction_adjustments`. `/api/admin/db/check` può segnalare `missing_tables` anche con schema OK.

---

## Endpoint API

Prefisso globale: **`/api`**.

### Pubblici — catalogo competizioni

| Metodo | Path | Descrizione |
|--------|------|-------------|
| GET | `/api/competitions` | Lista competizioni attive |
| GET | `/api/competitions/default` | Competizione predefinita (`is_primary`) |
| GET | `/api/competitions/{competition_id}` | Dettaglio competizione |

### Pubblici — competition-scoped (canonici)

| Metodo | Path | Query | Descrizione |
|--------|------|-------|-------------|
| GET | `/api/competitions/{competition_id}/model-status` | `model_version?` | Stato modelli per campionato |
| GET | `/api/competitions/{competition_id}/next-round/quick-report` | `model_version?`, `limit`, `only_next_round` | Report rapido prossimo turno |
| GET | `/api/competitions/{competition_id}/next-round/model-comparison` | `base_model`, `compare_model`, `limit`, `only_next_round` | Confronto v2.0 vs v2.1 |
| GET | `/api/competitions/{competition_id}/predictions/sot/upcoming-fixture/{fixture_id}/detail` | `model_version?` | Dettaglio singola fixture upcoming |
| GET | `/api/competitions/{competition_id}/predictions/sot/fixtures` | `scope`, `model_version?`, `limit` | Lista fixture per audit dropdown |
| GET | `/api/competitions/{competition_id}/predictions/sot/fixture/{fixture_id}/explanation` | `model_version?` | Spiegazione/audit predizione |
| GET | `/api/competitions/{competition_id}/betting-picks/tracked` | `model_version?` | Pick tracciate (monitoraggio) |
| GET | `/api/competitions/{competition_id}/fixtures/{fixture_id}/lineup-player-mapping-debug` | — | Debug mapping giocatori SportAPI |

### Admin — competizioni e ingest

| Metodo | Path | Descrizione |
|--------|------|-------------|
| POST | `/api/admin/competitions/discover` | Discovery lega/stagione API-Football |
| POST | `/api/admin/competitions` | Crea competizione |
| PATCH | `/api/admin/competitions/{competition_id}` | Aggiorna competizione |
| POST | `/api/admin/competitions/{competition_id}/ingest/bootstrap` | Bootstrap (lega, season, teams, fixtures) |
| POST | `/api/admin/competitions/{competition_id}/ingest/standings` | Import classifica |
| POST | `/api/admin/competitions/{competition_id}/ingest/team-stats` | Import stats squadra |
| POST | `/api/admin/competitions/{competition_id}/ingest/player-match-stats` | Import stats giocatore |
| POST | `/api/admin/competitions/{competition_id}/features/player-season-profiles/build` | Costruisci profili stagionali |
| POST | `/api/admin/competitions/{competition_id}/ingest/lineups` | Import formazioni API-Football |
| POST | `/api/admin/competitions/{competition_id}/ingest/sportapi-lineups` | Import formazioni SportAPI |
| POST | `/api/admin/competitions/{competition_id}/refresh/next-round` | Refresh + generazione predizioni |
| POST | `/api/admin/competitions/{competition_id}/betting-picks/create-from-round` | Crea pick tracciate da turno |

**Body comuni ingest:** `{ "dry_run": false, "model_version": null, "generate_mode": "default" }`

**`generate_mode` refresh next-round:**
- `default` — v1.1 + v2.0 (degraded se lineups assenti)
- `v21_only` — solo v2.1
- `v20_v21_comparison` — genera v2.0 e v2.1 in parallelo

**SportAPI lineups body:** `{ "scope": "next_round"|"upcoming_limit"|"fixture_ids", "dry_run", "force", "regenerate_v20", "upcoming_limit", "fixture_ids" }`

### Admin — debug, health, jobs

| Metodo | Path | Descrizione |
|--------|------|-------------|
| GET | `/api/admin/debug/competitions/{competition_id}/xg-coverage` | Copertura xG per campionato |
| GET | `/api/admin/data-health/competitions/{competition_id}` | Data health competition-scoped |
| POST | `/api/admin/jobs/pre-match-official-lineups/run` | Job cron pre-match lineups |
| GET | `/api/admin/db/check` | Verifica tabelle attese |
| GET | `/api/admin/api-football/test` | Test connessione API-Football |

### Admin — SportAPI

| Metodo | Path | Descrizione |
|--------|------|-------------|
| GET | `/api/admin/sportapi/debug/fixture/{fixture_id}` | Debug fixture SportAPI |
| POST | `/api/admin/sportapi/mappings/{fixture_id}/confirm` | Conferma mapping manuale |
| POST | `/api/admin/sportapi/lineups/{fixture_id}/fetch` | Fetch lineups singola fixture |
| GET | `/api/admin/sportapi/lineups/{fixture_id}` | Lineups salvate |
| GET | `/api/admin/sportapi/lineups/{fixture_id}/last-refresh-impact` | Ultimo impact refresh |
| GET | `/api/admin/sportapi/fixture/{fixture_id}/player-matching` | Matching giocatori |

### Admin — bookmakers

| Metodo | Path | Descrizione |
|--------|------|-------------|
| GET | `/api/admin/bookmakers` | Lista bookmaker |
| POST | `/api/admin/bookmakers/sync` | Sync bookmaker |
| GET | `/api/admin/bookmakers/sportapi/providers` | Provider SportAPI |
| POST | `/api/admin/bookmakers/sportapi/providers/sync` | Sync provider |
| POST | `/api/admin/bookmakers/sportapi/odds-discovery` | Discovery odds |
| POST | `/api/admin/bookmakers/sportapi/odds/markets-discovery` | Discovery mercati |
| POST | `/api/admin/bookmakers/sportapi/odds/next-round-sot` | Quote SOT prossimo turno |
| POST | `/api/admin/bookmakers/sportapi/odds/scan-sot-providers` | Scan provider SOT |

### Admin — arbitri

| Metodo | Path | Descrizione |
|--------|------|-------------|
| POST | `/api/admin/referees/sync-fixture` | Sync arbitro per fixture |
| POST | `/api/admin/referees/profile` | Profilo arbitro |
| POST | `/api/admin/referees/import-season-history` | Import storico stagione |
| GET | `/api/admin/referees/fixture/{fixture_id}/summary` | Summary arbitro fixture |

### Legacy Serie A (deprecati per flussi operativi multi-camp)

| Metodo | Path | Note |
|--------|------|------|
| POST | `/api/admin/pipeline/serie-a/{season}/refresh-upcoming-v04` | Pipeline v0.4/v1.0 legacy |
| POST | `/api/admin/ingest/serie-a/{season}/*` | Ingest Serie A legacy |
| POST | `/api/admin/sportapi/serie-a/{season}/refresh-next-round-lineups` | SportAPI legacy |
| GET | `/api/admin/data-health/serie-a/{season}` | Data health legacy |
| GET | `/api/predictions/sot/serie-a/{season}/*` | Predictions legacy (~25 route) |
| GET | `/api/betting-picks/serie-a/{season}/tracked` | Monitoraggio legacy |
| POST | `/api/admin/betting-picks/serie-a/{season}/refresh-results` | Refresh risultati pick |

> Per flussi operativi multi-campionato usare sempre endpoint con `{competition_id}`.

### Cecchino (modulo separato da SOT)

| Metodo | Path | Descrizione |
|--------|------|-------------|
| GET | `/api/competitions/{competition_id}/cecchino/upcoming` | Lista prossime partite + summary quote |
| GET | `/api/competitions/{competition_id}/cecchino/fixture/{fixture_id}` | Dettaglio picchetti, `data_quality`, quota finale |
| POST | `/api/admin/competitions/{competition_id}/cecchino/recalculate` | Ricalcolo e persistenza |
| POST | `/api/admin/cecchino/debug/calculate` | Calcolo da W/D/L manuali (test Excel) |

Risposta arricchita (Fase 2): `data_quality` (8 sample count, `leakage_check`, `fixture_ids_used`), `input_snapshot` con 8 contesti W/D/L.

Dettaglio: [SOT_PREDICTOR_CECCHINO.md](./SOT_PREDICTOR_CECCHINO.md).

### Health

| Metodo | Path |
|--------|------|
| GET | `/api/ping` |
| GET | `/api/health` |

---

## Mappa dato → modello

| Dato | v1.1 | v2.0 | v2.1 | Solo debug |
|------|------|------|------|------------|
| `fixture_team_stats` (SOT, tiri, passes) | sì | via v1.1 | sì (macro 1–4, 9) | — |
| `expected_goals` | sì | via v1.1 | sì (macro 5) | xG coverage admin |
| `player_season_profiles` | sì | — | sì (macro 6) | — |
| SportAPI lineups | no* | sì | sì (macro 6–8) | debug mapping |
| SportAPI missing | no | sì | sì (macro 8) | — |
| Odds/bookmakers | no | no | no | sì |
| Arbitri | no | no | no | sì (audit) |

\* v1.1 rispetta `USE_SPORTAPI_LINEUPS_IN_MODEL=false` di default.

---

## Riferimenti

- Pipeline admin: [ADMIN_PIPELINE.md](./ADMIN_PIPELINE.md)
- Registry feature: [SOT_MODEL_FEATURE_REGISTRY.md](./SOT_MODEL_FEATURE_REGISTRY.md)
- Legenda modelli: [MODEL_LEGEND.md](./MODEL_LEGEND.md)
