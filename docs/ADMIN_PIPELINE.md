# Pipeline Admin — guida operativa

Guida operativa aggiornata per la pagina **Admin** e le pipeline multi-campionato.

Contesto: [PROJECT_CONTEXT.md](./PROJECT_CONTEXT.md). Endpoint: [API_DATA_CATALOG.md](./API_DATA_CATALOG.md). Modelli: [MODEL_LEGEND.md](./MODEL_LEGEND.md).

---

## Principi fondamentali

1. **Multi-campionato**: ogni operazione filtra per `competition_id`. Non usare endpoint legacy `/serie-a/{season}/...` per flussi operativi multi-lega.
2. **Model-aware**: ogni prediction ha `model_version` esplicita. v2.0 = baseline stabile (**non modificare**). v2.1 = engine autonomo sperimentale/attivo.
3. **No xG proxy**: xG solo da `fixture_team_stats.expected_goals`.
4. **Guardrail**: refresh interrotto se fixture senza `competition_id` o appartenente ad altra competition.

### Entità Competition

| Campo | Significato |
|-------|-------------|
| `competition_id` | ID interno (PK) |
| `key` | Slug univoco (es. `serie-a-2025`) |
| `provider_league_id` | ID lega API-Football |
| `season` | Anno stagione |
| `league_id` / `season_id` | FK interne post-bootstrap |
| `is_primary` | Competizione default in UI |
| `pre_match_cron_enabled` | Abilita job cron pre-match |
| `is_active` | Visibile in selettore campionato |

---

## Ordine consigliato — nuova competizione

```
1. Discovery        POST /api/admin/competitions/discover
2. Creazione        POST /api/admin/competitions
3. Bootstrap        POST .../ingest/bootstrap
4. Classifica       POST .../ingest/standings
5. Team stats       POST .../ingest/team-stats
6. Player match     POST .../ingest/player-match-stats
7. Profili          POST .../features/player-season-profiles/build
8. Lineups AF       POST .../ingest/lineups
9. Lineups SportAPI POST .../ingest/sportapi-lineups  (scope: next_round)
10. Predizioni      POST .../refresh/next-round         (generate_mode: v20_v21_comparison)
11. Verifica        GET  /api/competitions/{id}/model-status
                    GET  /api/admin/debug/competitions/{id}/xg-coverage
                    GET  /api/admin/data-health/competitions/{id}
```

**Suggerimenti:**
- Usare `dry_run: true` su bootstrap e refresh per stimare volumi prima dell'esecuzione reale.
- Dopo bootstrap, verificare che tutte le fixture abbiano `competition_id` valorizzato.
- Abilitare `pre_match_cron_enabled` solo dopo il primo refresh riuscito con SportAPI.

---

## Ordine consigliato — aggiornamento prossimo turno

Dopo una giornata giocata:

```
1. Team stats (partite finite)     POST .../ingest/team-stats
2. Player match stats              POST .../ingest/player-match-stats
3. Profili giocatore               POST .../features/player-season-profiles/build
4. Lineups API-Football            POST .../ingest/lineups
5. Lineups SportAPI                POST .../ingest/sportapi-lineups
6. Refresh + predizioni            POST .../refresh/next-round
7. (Opzionale) Pick tracciate      POST .../betting-picks/create-from-round
8. Verifica UI                     Prossima giornata → model-status, quick-report, confronto v2.0/v2.1
```

La pagina **Prossima giornata** può ricaricarsi automaticamente dopo pipeline riuscita (`sessionStorage`, entro ~2 minuti).

---

## Operazioni dettagliate

### Discovery e creazione competizione

| Step | Endpoint | Note |
|------|----------|------|
| Discovery | `POST /api/admin/competitions/discover` | Body: `provider_league_id`, `season`. Valida lega/stagione su API-Football. |
| Creazione | `POST /api/admin/competitions` | Crea record `competitions` con `key`, `name`, `provider_league_id`, `season`. |
| Update | `PATCH /api/admin/competitions/{competition_id}` | Es. abilitare `pre_match_cron_enabled`, `is_primary`. |

### Bootstrap

`POST /api/admin/competitions/{competition_id}/ingest/bootstrap`

Sequenza interna:
1. Valida lega/stagione API-Football
2. Dry-run: stima teams/fixtures/API calls
3. Persist: league → season → teams → fixtures

Richiede `API_FOOTBALL_KEY` configurata.

### Standings

`POST /api/admin/competitions/{competition_id}/ingest/standings`

Importa classifica in `standings_snapshots` / `standing_entries`.

### Team stats

`POST /api/admin/competitions/{competition_id}/ingest/team-stats`

Importa statistiche squadra per partite finite. **Include `expected_goals`** se presente nel provider → fondamentale per v2.1 macro xG.

Verifica copertura: `GET /api/admin/debug/competitions/{competition_id}/xg-coverage`.

### Player match stats

`POST /api/admin/competitions/{competition_id}/ingest/player-match-stats`

Query opzionale: `force=true` per reimport.

### Player season profiles

`POST /api/admin/competitions/{competition_id}/features/player-season-profiles/build`

Costruisce `player_season_profiles` per la competition. Prerequisito per player layer v1.1/v2.1.

### Lineups API-Football

`POST /api/admin/competitions/{competition_id}/ingest/lineups`

Query opzionali: `fixture_id`, `force`. Salva in `fixture_lineups` / `fixture_lineup_players`.

### Lineups SportAPI

`POST /api/admin/competitions/{competition_id}/ingest/sportapi-lineups`

Body:
```json
{
  "scope": "next_round",
  "dry_run": false,
  "force": false,
  "regenerate_v20": false,
  "upcoming_limit": 20,
  "fixture_ids": null
}
```

**Scope:**
- `next_round` — prossimo turno (default)
- `upcoming_limit` — N prossime fixture
- `fixture_ids` — lista esplicita

**Comportamento:**
- Mapping auto se confidence ≥ 90
- Fetch formazioni probabili/ufficiali
- Opzione `regenerate_v20` per rigenerare v2.0 post-fetch

Richiede SportAPI configurata (`SPORTAPI_ENABLED`, `SPORTAPI_RAPIDAPI_KEY`).

### Refresh prossimo turno

`POST /api/admin/competitions/{competition_id}/refresh/next-round`

Body:
```json
{
  "dry_run": false,
  "model_version": null,
  "generate_mode": "default"
}
```

**`generate_mode`:**

| Mode | Comportamento |
|------|---------------|
| `default` | Genera v1.1 + v2.0. Se lineups SportAPI assenti → v2.0 in `degraded_fallback` (fattori = 1.0) |
| `v21_only` | Solo v2.1. Attivato anche se `model_version=baseline_v2_1_weighted_components` |
| `v20_v21_comparison` | Genera v2.0 e v2.1 in parallelo per confronto UI |

**Guardrail:** verifica `competition_id` su ogni fixture del turno. Max 100 fixture per selezione.

---

## Generazione prediction — modelli

| Modello | Slug | Quando generare |
|---------|------|-----------------|
| v2.1 | `baseline_v2_1_weighted_components` | `generate_mode: v21_only` o `v20_v21_comparison` |
| v2.0 | `baseline_v2_0_lineup_impact` | `default` o `v20_v21_comparison`. Richiede v1.1 + SportAPI per impatto lineup |
| v1.1 | `baseline_v1_1_sot` | Generata internamente in mode `default` come base v2.0 |

**v2.0 non va modificata** salvo richiesta esplicita. È la baseline di confronto stabile.

**v2.1** è il modello principale sperimentale/attivo da confrontare con v2.0.

---

## Cron pre-match — lineups ufficiali

| Aspetto | Dettaglio |
|---------|-----------|
| Endpoint | `POST /api/admin/jobs/pre-match-official-lineups/run` |
| Alias deprecato | `POST /api/admin/jobs/pre-match-lineup-refresh/run` |
| Auth cron | Header `X-Admin-Cron-Secret` o Bearer con `CRON_SECRET` |
| Admin UI | Chiamata senza secret consentita |
| Flag | `Competition.pre_match_cron_enabled = true` |

Body opzionale:
```json
{
  "force": false,
  "minutes_before": 60,
  "window_minutes": 15,
  "season": null,
  "competition_id": null
}
```

**Sequenza job per fixture in finestra kickoff:**
1. Snapshot pre-refresh
2. Refresh SportAPI (mapping + lineups)
3. Rigenera v2.0
4. Finalize impact → `fixture_lineup_refresh_impacts`
5. Persist tracked picks (`source=auto_pre_match`)

**DA VERIFICARE:**
- Schedule Railway/cron non presente nel repo (solo endpoint + env)
- Con più competition stessa season/league, il job filtra per `season_id` — possibile overlap

---

## Monitoraggio giocate

| Operazione | Endpoint |
|------------|----------|
| Crea pick da turno | `POST /api/admin/competitions/{competition_id}/betting-picks/create-from-round` |
| Lista pick (UI) | `GET /api/competitions/{competition_id}/betting-picks/tracked?model_version=` |
| Refresh risultati | `POST /api/admin/betting-picks/serie-a/{season}/refresh-results` (legacy Serie A) |

**DA VERIFICARE:** endpoint competition-scoped per refresh risultati pick — al momento solo path legacy Serie A confermato.

---

## xG coverage

`GET /api/admin/debug/competitions/{competition_id}/xg-coverage`

Mostra copertura `expected_goals` per la competition: quante fixture hanno xG, percentuali, sample.

Legacy Serie A: `GET /api/admin/debug/serie-a/{season}/expected-goals-summary`.

---

## Data Health

| Endpoint | Scope |
|----------|-------|
| `GET /api/admin/data-health/competitions/{competition_id}` | Multi-campionato (canonico) |
| `GET /api/admin/data-health/serie-a/{season}` | Legacy |

Verifica copertura dati per model_version: team stats, profili, lineups, predizioni.

Pagina frontend: **Data Health** (strumenti tecnici).

---

## Bookmakers / odds

Operazioni admin (pagina **Bookmakers**):

### Discovery unificata (competition-scoped)

1. `GET /api/admin/bookmakers/providers` — fonti API-Football + SportAPI (`available` / `not_configured`)
2. `GET /api/admin/bookmakers/providers/bookmakers` — lista bookmaker aggregata
3. `GET /api/admin/bookmakers/markets` — catalogo mercati normalizzati (`MATCH_WINNER_1X2`, …, `UNKNOWN`)
4. `GET /api/admin/competitions/{id}/bookmakers/coverage` — coverage % quote 1X2 sul prossimo turno
5. `POST /api/admin/competitions/{id}/bookmakers/sync-next-round-odds` — sync 1X2 → `fixture_bookmaker_odds` (+ snapshot legacy SportAPI)

Sync bookmaker: `POST /api/admin/bookmakers/sync` (API-Football) + `POST /api/admin/bookmakers/sportapi/providers/sync` (SportAPI).

### Legacy SportAPI (SOT / probe)

1. `POST /api/admin/bookmakers/sportapi/providers/sync` — sync provider
2. `POST /api/admin/bookmakers/sportapi/odds-discovery` — discovery odds
3. `POST /api/admin/bookmakers/sportapi/odds/markets-discovery` — discovery mercati SOT
4. `POST /api/admin/bookmakers/sportapi/odds/next-round-sot` — quote SOT prossimo turno

**Nota:** odds/bookmakers admin discovery sono **informativi** per SOT. Il **Cecchino** usa `fixture_bookmaker_odds` + pannello KPI (Bet365/Betfair/Pinnacle) — vedi sezione Cecchino sotto.

---

## Arbitri

Endpoint admin (`/api/admin/referees/`):

| Endpoint | Uso |
|----------|-----|
| `POST /sync-fixture` | Associa arbitro a fixture |
| `POST /profile` | Costruisce profilo arbitro |
| `POST /import-season-history` | Import storico stagione |
| `POST /recent-history` | Storico recente |
| `POST /match-context` | Contesto arbitro per match |
| `GET /fixture/{fixture_id}/summary` | Summary arbitro fixture |

**Nota:** dati arbitro **non entrano** nel calcolo SOT v2.0/v2.1. Utili per audit e catalogo dati.

---

## SportAPI — operazioni singola fixture

| Endpoint | Uso |
|----------|-----|
| `GET /api/admin/sportapi/debug/fixture/{fixture_id}` | Debug mapping/lineups |
| `POST /api/admin/sportapi/mappings/{fixture_id}/confirm` | Conferma mapping manuale |
| `POST /api/admin/sportapi/lineups/{fixture_id}/fetch` | Fetch forzato lineups |
| `GET /api/admin/sportapi/lineups/{fixture_id}/last-refresh-impact` | Variazione post-lineup |

---

## Errori noti Railway / API

| Errore | Causa | Azione |
|--------|-------|--------|
| `API_FOOTBALL_KEY non configurata` | Env mancante su Railway | Impostare variabile backend |
| `SportAPI non configurata` | `SPORTAPI_ENABLED=false` o key assente | Configurare env SportAPI |
| Rate limit API-Football | Troppe chiamate | Ridurre scope, usare dry_run, batch |
| `degraded_fallback` v2.0 | Lineups SportAPI assenti | Eseguire ingest sportapi-lineups |
| `guardrail_competition_id` | Fixture senza/mismatch competition_id | Re-bootstrap o fix manuale |
| `manifest_invalid` v2.1 | Manifest non valido | Verificare `v21_manifest_validation` |
| `feed_unavailable` xG | Lega senza expected_goals | Verificare xG coverage; v2.1 neutralizza macro xG |
| DB connection timeout | Railway Postgres cold start | Retry; verificare `DATABASE_URL` |

---

## Sezione Legacy (Serie A)

Collassata in Admin UI. **Non usare per flussi multi-campionato.**

| Operazione | Endpoint legacy |
|------------|-----------------|
| Pipeline v0.4/v1.0 | `POST /api/admin/pipeline/serie-a/{season}/refresh-upcoming-v04` |
| Post-matchday | `POST /api/admin/refresh/serie-a/{season}/post-matchday` |
| Ingest Serie A | `POST /api/admin/ingest/serie-a/{season}/*` |
| Genera v0.4 | `POST /api/predictions/sot/serie-a/{season}/generate-v04-offensive-core-sot` |
| Genera v1.0/v1.1 | `POST /api/predictions/sot/serie-a/{season}/generate-v10-sot` / `generate-v11-sot` |
| SportAPI legacy | `POST /api/admin/sportapi/serie-a/{season}/refresh-next-round-lineups` |
| Backfill Serie A | `POST /api/admin/competitions/backfill/serie-a/{season}` |

---

## Workflow ChatGPT → Cursor → GitHub → Railway

ChatGPT **non modifica direttamente** codice applicativo. ChatGPT prepara prompt per Cursor. Cursor modifica il codice. L'utente testa, committa e pusha. Railway deploya. Dopo il deploy, ChatGPT può aiutare ad aggiornare la documentazione in `/docs`. La documentazione deve rimanere allineata al codice.

Vedi anche [PROJECT_CONTEXT.md](./PROJECT_CONTEXT.md).

---

## Tabella endpoint principali (quick reference)

### Competitions (pubblico)

| Metodo | Path |
|--------|------|
| GET | `/api/competitions` |
| GET | `/api/competitions/default` |
| GET | `/api/competitions/{competition_id}` |
| GET | `/api/competitions/{competition_id}/model-status` |
| GET | `/api/competitions/{competition_id}/next-round/quick-report` |
| GET | `/api/competitions/{competition_id}/next-round/model-comparison` |
| GET | `/api/competitions/{competition_id}/predictions/sot/upcoming-fixture/{fixture_id}/detail` |
| GET | `/api/competitions/{competition_id}/predictions/sot/fixtures` |
| GET | `/api/competitions/{competition_id}/predictions/sot/fixture/{fixture_id}/explanation` |
| GET | `/api/competitions/{competition_id}/cecchino/upcoming` |
| GET | `/api/competitions/{competition_id}/cecchino/fixture/{fixture_id}` |

### Admin (multi-campionato)

| Metodo | Path |
|--------|------|
| POST | `/api/admin/competitions/discover` |
| POST | `/api/admin/competitions` |
| PATCH | `/api/admin/competitions/{competition_id}` |
| POST | `/api/admin/competitions/{competition_id}/ingest/bootstrap` |
| POST | `/api/admin/competitions/{competition_id}/ingest/standings` |
| POST | `/api/admin/competitions/{competition_id}/ingest/team-stats` |
| POST | `/api/admin/competitions/{competition_id}/ingest/player-match-stats` |
| POST | `/api/admin/competitions/{competition_id}/features/player-season-profiles/build` |
| POST | `/api/admin/competitions/{competition_id}/ingest/lineups` |
| POST | `/api/admin/competitions/{competition_id}/ingest/sportapi-lineups` |
| POST | `/api/admin/competitions/{competition_id}/refresh/next-round` |
| GET | `/api/admin/debug/competitions/{competition_id}/xg-coverage` |
| GET | `/api/admin/data-health/competitions/{competition_id}` |
| POST | `/api/admin/jobs/pre-match-official-lineups/run` |
| POST | `/api/admin/competitions/{competition_id}/cecchino/recalculate` |

---

## Cecchino (modulo separato)

Il **Cecchino** non è incluso in `refresh/next-round` né nella generazione v2.0/v2.1.

Per sincronizzare quote bookmaker API-Football (Bet365 8, Betfair 3, Pinnacle 4) sul prossimo turno o su una fixture:

```
POST /api/admin/competitions/{competition_id}/cecchino/bookmakers/sync-next-round
Body: { "fixture_id": 123, "bookmaker_ids": [8, 3, 4], "markets": ["MATCH_WINNER_1X2", "DOUBLE_CHANCE", "OVER_UNDER_GOALS"] }
```

Per ricalcolare le quote 1X2 Cecchino sulle prossime partite (o su una singola fixture):

```
POST /api/admin/competitions/{competition_id}/cecchino/recalculate
Body opzionale: { "fixture_id": 12345, "limit": 50 }
```

Lettura UI: `/cecchino`. Dettaglio: [SOT_PREDICTOR_CECCHINO.md](./SOT_PREDICTOR_CECCHINO.md).

### Cecchino Today (scan manuale giornaliero persistente)

Equivalente operativo per giornata corrente o successiva — **non** incluso in cron pre-match SOT:

```
POST /api/admin/cecchino/today/scan-today
POST /api/admin/cecchino/today/scan-tomorrow
POST /api/admin/cecchino/today/scan
Body opzionale scan: { "scan_date": "YYYY-MM-DD", "timezone": "Europe/Rome" }
POST /api/admin/cecchino/today/cleanup
Body opzionale: { "retention_days": 7, "timezone": "Europe/Rome" }
```

Lettura: `GET /api/cecchino/today/days`, `GET /api/cecchino/today?date=` (solo eleggibili + `scan_meta`). Debug admin: `GET /api/admin/cecchino/today/excluded`, `GET .../debug-search?date=&q=`. UI: `/cecchino-today`. Retention automatica post-scan: elimina snapshot con `scan_date` più vecchi di 7 giorni (oggi/domani protetti).

**Fase 2 (dati reali):** i record W/D/L derivano solo da fixture **finite** prima del kickoff target, filtrate per `competition_id`. La risposta API include `data_quality` (sample count, `leakage_check`). Dopo deploy, eseguire `recalculate` per aggiornare righe già in cache con il nuovo schema.

---

## Riferimenti

- Catalogo dati: [API_DATA_CATALOG.md](./API_DATA_CATALOG.md)
- Framework analisi: [MATCH_ANALYSIS_FRAMEWORK.md](./MATCH_ANALYSIS_FRAMEWORK.md)
- Registry feature: [SOT_MODEL_FEATURE_REGISTRY.md](./SOT_MODEL_FEATURE_REGISTRY.md)
