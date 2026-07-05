# SOT Predictor — Contesto progetto

File indice da leggere all'inizio di ogni nuova chat (ChatGPT, Cursor o altro assistente).

## Obiettivo

**SOT Predictor** è un tool full-stack per stimare i **tiri in porta attesi (Shots on Target / SOT)** delle partite di calcio, con focus sui mercati **Over/Under SOT** (squadra e totale match).

Il sistema combina dati storici pre-match, profili giocatore, formazioni e indisponibili (SportAPI), xG reali da API-Football e modelli statistici versionati.

## Stack tecnico

| Layer | Tecnologie |
|-------|------------|
| Frontend | React 19, React Router 7, Vite 8, TypeScript, Tailwind CSS 4 |
| Backend | FastAPI, Uvicorn, SQLAlchemy 2, Alembic, Pydantic 2, httpx |
| Database | PostgreSQL |
| Deploy | Railway (backend, frontend, cron, Postgres) |
| Fonti esterne | API-Football / API-Sports, SportAPI via RapidAPI |

## Concetti chiave

| Concetto | Significato |
|----------|-------------|
| `competition_id` | Identificativo interno del campionato attivo (multi-lega). Ogni pipeline e ogni prediction devono filtrare per questo valore. |
| `season` | Anno stagione (es. 2025). Associato alla `Competition`. |
| `fixture_id` | Identificativo interno della partita. |
| `model_version` | Slug del modello SOT (es. `baseline_v2_1_weighted_components`). Ogni prediction è model-aware. |
| `cecchino_version` | Slug del modulo Cecchino (corrente: `cecchino_v0_3_signals_matrix`). Indipendente da `model_version`. |
| `provider_league_id` | ID lega su API-Football, collegato alla `Competition`. |

## Fonti dati

- **API-Football / API-Sports**: leghe, squadre, fixture, statistiche squadra (`expected_goals`), statistiche giocatore, formazioni, classifica, arbitri.
- **SportAPI / RapidAPI**: mapping fixture, formazioni probabili/ufficiali, missing players, quote/bookmaker (admin).
- **PostgreSQL**: persistenza di tutti i dati elaborati e delle predizioni.
- **Railway cron**: job pre-match per refresh lineups ufficiali.

Dettaglio: [API_DATA_CATALOG.md](./API_DATA_CATALOG.md).

## Cecchino — X primo tempo nel Monitoraggio Segnali (2026-07-05)

Activation derivata X PT nel sync segnali: nasce da X finale a valore, valutata su HT, senza quota PT. Ordine UI 1→Over con X PT dopo 1/2. 1/2 non trasformati in 1X/X2. Segnali KPI e KPI panel invariati.

## Cecchino — Filtro valore quota sui segnali monitorati (2026-07-05)

Monitoraggio Segnali / Segnali Lab / backtest A–F: solo activation con matrice SI e `quota_book >= quota_cecchino` (KPI salvato). Matrice fixture detail e Segnali KPI invariati. Ricalcolo storico: **Ricalcola filtro valore** (`force_remap`).

## Frontend — Restyling Segnali KPI e default date odierna (2026-07-04)

Segnali KPI restyled stile Lab; filtri data Cecchino (Monitoraggio, Lab, KPI) default oggi locale via `todayLocalIso`. Zero modifiche backend.

## Cecchino — Robustezza backfill Segnali KPI (2026-07-04)

Backfill Segnali KPI resiliente: isolamento errori per fixture, payload `partial` con diagnostica, fix valutazione mercati PT. Formule KPI e Segnali Cecchino/Lab invariati.

## Backend — Merge Alembic heads dopo Segnali KPI (2026-07-04)

Risolto «Multiple head revisions» su Railway con merge migration `dd07defcb335` (KPI + merge precedente). Nessuna DDL distruttiva; formule Cecchino, Segnali KPI e Monitoraggio Segnali invariati. Singola head Alembic per deploy `alembic upgrade head`.

## Cecchino — Segnali KPI (2026-07-04)

Nuova pagina `/segnali-kpi` (sidebar Cecchino): monitoraggio quote di valore dal Pannello KPI, bucket rating 50–100, valutazione PT/FT offline, tabella `cecchino_kpi_signal_activations`.

## Cecchino Today — Gate locale data fixture (2026-07-03)

Scansione Today: solo fixture con kickoff locale uguale a `scan_date` (timezone `Europe/Rome`). Fuori data → skip pre-salvataggio; contatori `provider_out_of_scan_date_skipped` nel report job.

## Backend — Fix circular import helper datetime Cecchino (2026-07-03)

Helper datetime in `app.services.datetime_utils` (non più sotto `cecchino/`). `cecchino.__init__` senza re-export per evitare circular import con `v10_prior_context` al startup Railway.

## Cecchino Today — datetime (2026-07-03)

Kickoff e cutoff PIT in Cecchino Today passano da `datetime_utils.ensure_datetime_utc`. Il debug partite escluse distingue errori datetime da KPI mancanti reali.

## Modelli attivi

| Modello | Slug | Ruolo |
|---------|------|-------|
| v2.1 SOT Weighted Components | `baseline_v2_1_weighted_components` | Engine autonomo sperimentale/attivo — modello principale da confrontare |
| v2.0 SOT Lineup Impact | `baseline_v2_0_lineup_impact` | Baseline stabile di confronto — **non modificare formula/comportamento** |
| v1.1 SOT | `baseline_v1_1_sot` | Base interna di v2.0; non visibile nel selettore UI principale |
| Legacy v0.x–v1.0 | vari slug | Storico/research; non proposti nel frontend principale |

Dettaglio: [MODEL_LEGEND.md](./MODEL_LEGEND.md), [SOT_MODEL_FEATURE_REGISTRY.md](./SOT_MODEL_FEATURE_REGISTRY.md).

## Sezioni frontend

Selettore campionato (`CompetitionSelector`) in sidebar.

**Navigazione principale:**
- Framework Analisi
- Spiegazione previsione (audit model-aware)
- Prossima giornata (quick report, confronto v2.0 vs v2.1)
- Cecchino — dashboard autonoma (picchetti, KPI DASHBOARD classico con 3 bookmaker; **non** influenza SOT)
- Cecchino — sezione sidebar dedicata in alto (Fase 35): Cecchino, Cecchino Today, Monitoraggio Segnali, **Segnali Lab (Fase 44)**
- Cecchino Today — dashboard giornaliera Betfair-only, KPI v2 unico riferimento quote (Fase 22), refresh quote Betfair on-demand singola fixture (Fase 23), export mercati JSON, debug JSON KPI, debug Picchetti (Fase 25), formule goal Poisson+storico v2 (Fase 27), pesi globali 1X2 30/30/20/20 e goal 20/30/20/30 (Fase 40), ricalcolo offline `POST /api/admin/cecchino/recompute`, sezione Equilibrio vs Squilibrio (Fase 29), **Intensità Goal v4 Goal Attesi** nel dettaglio partita (Fase 46/47/48/49), **Expected Goal Engine Diagnostica Variabili** (Fase 50), **API Raw Inspector** manuale per esplorazione xG/expected (Fase 51), **xG storico current season** nel diagnostics EGE (Fase 52), **xG storico automatico** su fixture eleggibili con cache `xg_profiles_json` (Fase 53), Dominanza contestualizzata X vs 1/2 (Fase 30), legenda operativa equilibrio 18 righe (Fase 31), Monitoraggio Segnali storico SI/NO con valutazione esito, backfill giornate pregresse (Fase 32/33), mapping Under/Over 2.5 FT (Fase 34), Indice di Convergenza Match ICM (Fase 41, sostituisce Delta Forza Fase 36), mapping Scala su righe 1X/X2 (Fase 37), fix definitivo Scala heatmap/storico (Fase 38), card PT/FT, mapping strict Match Winner, layout 35/65, **timeline ±30** (navigazione, non retention), **nessun cleanup automatico post-scan** (storico preservato; DELETE solo admin gated), scan async (`/cecchino-today`)
- Monitoraggio Segnali — pagina aggregata `/monitoraggio-segnali` (heatmap UNDER/OVER 2.5, KPI con media segnali/partita Fase 35, Quota media prese / Quota Void / Rendimento prese Fase 42, **Confronto modelli pesi A–F Fase 43**, **formule segnali aggiornate Fase 45** con Dominanza da Equilibrio, export CSV, backfill storico, pulsante «Ricalcola modelli A–F», pulsante «Ricalcola filtro valore» (value gate quota book ≥ Cecchino), diagnostics legacy SCALA Fase 38, legenda formule Excel espandibile Fase 39/45)
- **Segnali Lab** — pagina sperimentale `/monitoraggio-segnali-lab` (Fase 44): UI premium con framer-motion, ECharts, Sonner; stessi dati/endpoint della pagina stabile; codice isolato in `cecchino-lab/`; drawer dettaglio heatmap/partite; **legenda formule Fase 45** (accordion condiviso con pagina stabile)
- Monitoraggio Giocate
- Bookmakers — discovery provider/mercati, coverage e sync 1X2 per competizione (`fixture_bookmaker_odds`; non collegato a Cecchino/SOT)
- Changelog

**Strumenti tecnici:**
- Debug Modello, Catalogo dati API, Dashboard modello, Data Health, Backtest (placeholder), Legenda Modello, Admin

## Pipeline principali

1. **Setup nuova competizione**: discover → create → bootstrap → standings → team-stats → player-match-stats → profili → lineups → SportAPI → refresh next-round.
2. **Aggiornamento prossimo turno**: stats partite finite → profili → lineups → SportAPI → generazione v2.0/v2.1.
3. **Cron pre-match**: refresh lineups ufficiali → rigenera v2.0 → impact snapshot → tracked picks.

Dettaglio operativo: [ADMIN_PIPELINE.md](./ADMIN_PIPELINE.md).

## Regole dure

1. **Multi-campionato**: usare sempre endpoint con `competition_id`. Non usare endpoint legacy Serie A per flussi operativi multi-lega.
2. **Model-aware**: ogni prediction, audit e report deve specificare `model_version`. Nessun fallback silenzioso quando il modello è richiesto esplicitamente.
3. **v2.0 frozen**: non modificare formula o comportamento di v2.0 salvo richiesta esplicita.
4. **v2.1 autonomo**: v2.1 non è una patch di v2.0; ha engine e manifest propri.
5. **xG reali**: solo da `fixture_team_stats.expected_goals`. **No proxy xG**.
6. **Anti-leakage**: per ogni fixture target, usare solo dati di partite finite **prima** del kickoff target.
7. **SportAPI nel modello**: entra in v2.0 (moltiplicatori lineup) e v2.1 (macro lineups/infortuni/player). Non trattarlo come «solo debug».
8. **Documentazione**: i file in `/docs` sono la fonte aggiornata. L'endpoint runtime `GET /api/model/legend` è ancora legacy (v0.x) — vedi [MODEL_LEGEND.md](./MODEL_LEGEND.md).

## Workflow ChatGPT → Cursor → GitHub → Railway

```
ChatGPT (analisi, prompt, docs)
    ↓ prepara prompt
Cursor (modifica codice)
    ↓ test locale
Utente (commit + push)
    ↓
GitHub
    ↓
Railway (deploy backend / frontend / cron / Postgres)
    ↓ post-deploy
ChatGPT (aggiornamento docs /docs se autorizzato)
```

**Regola fondamentale:** ChatGPT **non modifica direttamente** codice applicativo. ChatGPT può leggere il repository e preparare prompt per Cursor. Cursor modifica il codice. L'utente testa, committa e pusha. Railway deploya. Dopo il deploy, ChatGPT può aiutare ad aggiornare la documentazione in `/docs`. La documentazione deve rimanere allineata al codice.

## Indice documentazione

| File | Contenuto |
|------|-----------|
| [PROJECT_CONTEXT.md](./PROJECT_CONTEXT.md) | Questo file — contesto e indice |
| [ADMIN_PIPELINE.md](./ADMIN_PIPELINE.md) | Guida operativa admin multi-campionato |
| [API_DATA_CATALOG.md](./API_DATA_CATALOG.md) | Fonti dati, tabelle DB, endpoint |
| [MATCH_ANALYSIS_FRAMEWORK.md](./MATCH_ANALYSIS_FRAMEWORK.md) | Framework interpretazione partita |
| [MODEL_LEGEND.md](./MODEL_LEGEND.md) | Legenda modelli v2.0/v2.1 e legacy |
| [SOT_MODEL_FEATURE_REGISTRY.md](./SOT_MODEL_FEATURE_REGISTRY.md) | Registry feature/macro/micro v2.1 |
| [SOT_PREDICTOR_CECCHINO.md](./SOT_PREDICTOR_CECCHINO.md) | Modulo Cecchino (1X2, separato da SOT) |

## Prompt di ripartenza (nuova chat)

Copia e incolla questo blocco per riprendere il lavoro:

```
Sto lavorando su Rccard92/football-sot-predictor (SOT Predictor).
Leggi docs/PROJECT_CONTEXT.md e i file in /docs pertinenti al task.
Il progetto è multi-campionato (competition_id), con modelli v2.0 (baseline stabile) e v2.1 (engine autonomo sperimentale).
Regole: model-aware, no xG proxy, v2.0 non modificare, endpoint competition-scoped (non legacy Serie A).
Stack: React + FastAPI + PostgreSQL su Railway.
[Descrivi qui il task specifico]
```
