# SOT Predictor — Contesto progetto

File indice da leggere all'inizio di ogni nuova chat (ChatGPT, Cursor o altro assistente).

## Cecchino Today — workspace master-detail adattivo (2026-07-19)

Route `/cecchino-today` fluid (override Layout); 2xl lista 370–410px + dettaglio; sotto 2xl drawer «Partite eleggibili»; card partite a due righe squadre; KPI tabella da xl senza scroll.

## Cecchino Today — KPI full-width senza scrollbar (2026-07-19)

Pagina Today `max-w-[1800px]`; da xl sidebar fissa 320px e dettaglio fluido; KPI senza scroll orizzontale (`table-fixed`); sotto xl card; toggle Espandi analisi.

## Equilibrio vs Squilibrio v5 — dettaglio storico snapshot (2026-07-19)

Detail Today: `historical_snapshot` per `scan_date` passate (identity status/score non bloccanti, solo snapshot salvati, KPI senza fallback DB). `current_strict` invariato per oggi. Meta `balance_v5_snapshot_meta`. Nessun ricalcolo post-match in GET.

## Equilibrio vs Squilibrio v5 — fix incoerenze + Intensità Goal UI (2026-07-19)

Fix su `cecchino_balance_v5_v2` (no bump): F36 via `class_key` tecnico; normalizzazione 1X2 unica (`*_norm`); `goal_markets` argomento separato; FE label/disclaimer/market; Intensità Goal v4 nascosta dal Today Detail; titolo v5 = `Intensità Goal Avanzata - v5 Preview research`. Legacy ICM/Signals intatti.

## Equilibrio vs Squilibrio v5 — modulo canonico (2026-07-19)

Versione `cecchino_balance_v5_v2`: unico modulo [`cecchino_balance_v5.py`](backend/app/services/cecchino/cecchino_balance_v5.py). Quattro pilastri (F36 ufficiale, Dominanza ufficiale, Credibilità X descrittiva, Gap ufficiale) + scostamento mercato separato. Eliminati Preview e research_candidates. Adapter legacy `cecchino_balance_analysis.py` per ICM/Signals. Nessun impatto su formule ICM/Segnali/KPI.

## Indice di Acquistabilità — empirica v1.1 Pannello KPI (2026-07-19)

Colonna **Acquistabilità** dopo Rating: `cecchino_purchasability_empirical_rating_v1_1`. Current da `kpi_panel_json`; coorte locale→globale; mercati panel con settlement; formula score invariata; nessuna probabilità/stake. Vedi `SOT_PREDICTOR_PURCHASABILITY_RESEARCH.md`.

## Indice di Acquistabilità — empirica v1 Pannello KPI (2026-07-18)

Sostituita da v1.1. Coorte solo locale; current da audit rows.

## Indice di Acquistabilità — Fase 2A.4.1 coorte DC / OOF / span (2026-07-18)

Research `cecchino_purchasability_residual_reliability_v2a_4_1`: linkage DC cross-market, maschera OOF comune, gate temporale 90g/3 mesi, readiness `continue_data_collection` su span corto. La conclusione `v2a_4` non è definitiva. Vedi `SOT_PREDICTOR_PURCHASABILITY_RESEARCH.md`.

## Indice di Acquistabilità — Fase 2A.4 residual reliability (2026-07-18)

Research `cecchino_purchasability_residual_reliability_v2a_4`: fair Book probability, target `direction_correct` / `signed_book_residual`, GAP_ONLY vs context, gate Fase 2B residuale. Statistica `v2a_2` invariata. Nessuna formula 0–100. Vedi `SOT_PREDICTOR_PURCHASABILITY_RESEARCH.md`.

## Indice di Acquistabilità — Fase 2A.3.2 coorte/dedup/Rating (2026-07-18)

Class balance fold su `y_win`; confronti paired unici con riuso Rating; Rating resta benchmark diagnostico. Versione `v2a_2` invariata; readiness verso residual reliability research. Vedi `SOT_PREDICTOR_PURCHASABILITY_RESEARCH.md`.

## Indice di Acquistabilità — Fase 2A.3.1 result FE (2026-07-18)

FE carica summary poi result completo; classificazione effetto/temporale/mercato separata; `candidate_decision`. Versione `v2a_2` invariata. Vedi `SOT_PREDICTOR_PURCHASABILITY_RESEARCH.md`.

## Indice di Acquistabilità — Fase 2A.3 job asincrono (2026-07-18)

Esecuzione asincrona process-local della ricerca statistica (`…_v2a_2` invariata): POST job + polling FE, risultati temporanei in `/tmp`, nessuna persistenza DB. Evita timeout proxy sulle richieste sincrone lunghe (falso errore CORS). Vedi `SOT_PREDICTOR_PURCHASABILITY_RESEARCH.md`.

## Indice di Acquistabilità — Fase 2A.2 timeout e gate Book (2026-07-18)

Research `cecchino_purchasability_statistical_research_v2a_2`: timeout FE 300–1200s; classificazione marginale con `negative_but_uncertain`; readiness 2B solo con evidenza indipendente vs Book; Book dominance descrittiva. Nessuna formula 0–100. Vedi `SOT_PREDICTOR_PURCHASABILITY_RESEARCH.md`.

## Indice di Acquistabilità — Fase 2A.1 ricerca statistica (2026-07-18)

Research `cecchino_purchasability_statistical_research_v2a_1`: confronti paired + CI fixture-clustered, ROI ranking OOF, stabilità fold/mercato, Rating prespecificato, seed SHA-256. Nessuna formula 0–100. Vedi `SOT_PREDICTOR_PURCHASABILITY_RESEARCH.md`.

## Indice di Acquistabilità — Fase 2A ricerca statistica (2026-07-18)

Research read-only `cecchino_purchasability_statistical_research_v2a` su settled_core del dataset v1_1: CV temporale per fixture, logistic L2, benchmark Book/Model/Rating, contributo marginale, feature decisions, readiness 2B. Nessuna formula 0–100. Sub-tab FE «Ricerca statistica — Fase 2A». Vedi `SOT_PREDICTOR_PURCHASABILITY_RESEARCH.md`.

## Indice di Acquistabilità — Fase 1.1 integrità temporale (2026-07-18)

Audit `cecchino_purchasability_audit_v1_1`: timestamp da odds_meta (non updated_at), bookmaker dict vs odds_source, DC non normalizzata, core rigoroso, paginazione batch. Nessuna formula 0–100. Vedi `SOT_PREDICTOR_PURCHASABILITY_RESEARCH.md`.

## Indice di Acquistabilità — Fase 1 Audit (2026-07-18)

Research read-only `cecchino_purchasability_audit_v1` / `dataset_v1`: inventario KPI da `kpi_panel_json`, mappa opposizioni, dataset pre-match senza bias rating≥50, Rating = benchmark. Nessuna formula 0–100; tab «Acquistabilità — Audit» su Segnali KPI. Vedi `SOT_PREDICTOR_PURCHASABILITY_RESEARCH.md`.

## Intensità Goal v5 Research — Fase 2A.1 Preview freeze reale (2026-07-18)

Preview `cecchino_goal_intensity_v5_preview_v1_1`: freeze reale (`frozen_at=now`), ammissione `source_snapshot_at > frozen_at` e `< kickoff`, esclusione retrospettiva per identity sets. Same-day post-freeze ok. Min 200 = solo gate 2B. Formule/hash/v4 invariati; nessuna migration.

## Intensità Goal v5 Research — Fase 2A Preview (2026-07-18)

Preview prospettica storica `cecchino_goal_intensity_v5_preview_v1` (superseduta): bundle ECDF+calibrazioni 1D.1, snapshot/lock/result, monitoraggio GI_A/GI_B/MT1/diagnostico. Cache export 1D saltata.

## Intensità Goal v5 Research — Fase 1D.1 eval calibrata (2026-07-18)

Correzione layer valutazione `candidate_indices_v1_1`: calibrazione train-only, paired/ablation dimensionalmente validi, expanding multi-candidato, protocollo prospettico post-freeze. Score e dataset invariati; v4 invariata.

## Intensità Goal v5 Research — Fase 1D candidate indices (2026-07-17)

Indici candidati research `cecchino_goal_intensity_v5_candidate_indices_v1`: ECDF train-only, pilastri/compositi GI_A–D equal weight, ablation/Pareto/xG optional, readiness 2A. Riusa dataset 1B; statistics `v1_2` e v4 invariati. Nessuna formula produttiva.

## Intensità Goal v5 Research — Fase 1C.2 normalizzazione readiness (2026-07-17)

Normalizzazione raccomandazioni/readiness senza ricalcolo metriche: dipendenze da formule di costruzione (`derived_aggregate` pair), rolling selected∉excluded, regole candidate_core, gate consistency. Versione `cecchino_goal_intensity_v5_statistics_v1_2`. Nessuna formula v5; v4 invariata.

## Intensità Goal v5 Research — Fase 1C.1 statistica completa (2026-07-17)

Completamento Fase 1C: metriche flat su quattro target, `target_specific_strengths`, decisioni rolling/stability, dipendenze exact/derived, VIF non fuorviante, xG paired valorizzata, readiness reale e profiling performance. Versione `cecchino_goal_intensity_v5_statistics_v1_1`. Nessuna formula v5; v4 invariata.

## Intensità Goal v5 Research — Fase 1C statistica (2026-07-17)

Statistiche read-only sul dataset Today eleggibile Fase 1B.1: descrittive, correlazioni/bootstrap, quintili, ridondanza/VIF, PSI/KS e confronto xG temporale. Versione `cecchino_goal_intensity_v5_statistics_v1` (superseded by v1_1); export streaming e benchmark <30s/<2 MB. Limite dichiarato `legacy_pre_utc_fix`: nessuna riclassificazione delle esclusioni UTC storiche; non è un blocco automatico della readiness. Nessuna formula o peso produttivo; v4 invariata.

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

## Intensità Goal v5 Research — Coorte Today eleggibile (2026-07-17)

Audit/dataset Intensità Goal v5 solo su partite **eleggibili Cecchino Today** (`eligibility_status` persistito), range `scan_date` ≥ 2026-06-19. Storico locale solo come supporto feature. Versioni `audit_v1_5` / `dataset_v1_2`; `cohort_basis=cecchino_today_eligible_scan_date`. Fail-closed su unknown/ineligible nel model-ready.

## Intensità Goal v5 Research — Dataset Fase 1B.1 (2026-07-17)

Dataset storico research: dedupe composita O(n log n), summary HTTP compatto (`preview` ≤100, hash paired), export StreamingResponse CSV/JSON. Versione `cecchino_goal_intensity_v5_dataset_v1_1`. Timeout globale invariato.

## Intensità Goal v5 Research — Dataset Fase 1B (2026-07-17)

Dataset storico research: dedupe composita, coorti history/xG paired, exclusion bias, identity diagnostics. Versione `cecchino_goal_intensity_v5_dataset_v1`.

## Intensità Goal v5 Research — xG opzionale (1A.4) (2026-07-17)

xG opzionale per ammissibilità, obbligatorio quando completo/sicuro; stati available/partial/missing/excluded_unsafe; coorti + fixture audit + FE. Versione `cecchino_goal_intensity_v5_audit_v1_4`.

## Intensità Goal v5 Research — Identity storica + qualità (2026-07-17)

Identity statica storica (no status/score bloccanti); gate xG anti-leakage; `audit_quality` usable/degraded/unusable; feature-safe rate. Versione `cecchino_goal_intensity_v5_audit_v1_3`.

## Intensità Goal v5 Research — Audit Fase 1A.3 (2026-07-17)

Perf audit: preload indici Fixture/Today/Team/Competition/xG; loop DB-free; `GET .../availability`; versione `cecchino_goal_intensity_v5_audit_v1_2`. Timeout FE 180s invariato.

## Intensità Goal v5 Research — Audit Fase 1A.2 (2026-07-17)

Fix audit: coorte kickoff, identity keyword-only, feature goal reali senza Today. Versione `cecchino_goal_intensity_v5_audit_v1_1`.

## Intensità Goal v5 Research — Audit Fase 1A (2026-07-17)

Audit storico offline a quattro pilastri (produzione, solidità, ritmo, stabilità). v4 resta legacy_reference. Lab `/cecchino/ricerca-intensita-goal`. Docs: [SOT_PREDICTOR_GOAL_INTENSITY_V5_RESEARCH.md](./SOT_PREDICTOR_GOAL_INTENSITY_V5_RESEARCH.md).

## Equilibrio vs Squilibrio v5 — Fase 2B (2026-07-17)

Pannello ufficiale «Equilibrio vs Squilibrio v5» (`balance_v5_v1` + alias `balance_v5`). Stati pilastro invariati; link laboratorio Credibilità X; ICM nascosto; nessuna formula nuova.

## Equilibrio vs Squilibrio — xG cache refresh Fase 2A.4 (2026-07-17)

Cache xG stale se cutoff ≠ kickoff; rebuild cache-only senza API; script `--refresh-xg-cache-only`.

## Riparazione Caso A — Today 9510 / Fixture 562 (2026-07-17)

Kickoff canonico `2026-07-16T22:30Z`; script dry-run + apply gated; recompute offline senza API. Warning `fixture_identity_repaired_case_a`.

## Equilibrio vs Squilibrio — Identity false-positive Fase 2A.3 (2026-07-17)

GET detail read-only; check su raw (kickoff/status/score/snapshot); Preview `v1_2` bloccata su mismatch; audit admin Railway. Nessuna formula cambiata.

## Equilibrio vs Squilibrio — Identità fixture Fase 2A.2 (2026-07-17)

Protezione read-only `fixture_identity_consistency` + blocco Preview v5 (`balance_v5_preview_v1_1`) su mismatch. Tolleranza kickoff 6h. Nessuna formula cambiata.

## Equilibrio vs Squilibrio — Preview v5 Fase 2A.1 (2026-07-17)

Pulizia semantica F36/Gap, fonti research corrette, formattazione italiana. Nessuna modifica alle formule.

## Equilibrio vs Squilibrio — Preview v5 Fase 2A (2026-07-17)

Pannello a quattro pilastri descrittivi su Cecchino Today (`balance_v5_preview`). F36 ufficiale; altri in ricerca/calibrazione; Book separato; ICM nascosto in UI. Nessuna nuova formula. Consolidato in Fase 2B.

## Credibilità X Research — Confronto modelli Fase 1D (2026-07-17)

Validazione temporale esplorativa (M0–M12, OOF, holdout, calibrazione, ROI Market OOF). Versione `cecchino_draw_credibility_model_comparison_v1`. Nessuna promozione produttiva.

## Credibilità X Research — Export JSON analisi statistica (2026-07-17)

Export frontend del payload statistico (`lastAnalysis`) completo o per sezione, senza trasformazione. Helper `downloadJsonFile.ts` + pannello nel tab Analisi statistica. Nessun impatto produttivo.

## Credibilità X Research — Correzione Pattern Market Fase 1C.2 (2026-07-15)

Propagazione boundaries Primary → ROI pattern Market, metadati strutturati, celle soppresse, semantica conteggio leghe. Versione `cecchino_draw_credibility_statistics_v1_2`. Pronto per Fase 1D esplorativa.

## Credibilità X Research — Correzione e completamento Fase 1C.1 (2026-07-15)

Correzione segni HOME/DRAW/AWAY, convinzione direzionale, trend/bootstrap, interazioni/pattern, stabilità temporale/leghe, Market/ROI per fasce, famiglie feature. Versione `cecchino_draw_credibility_statistics_v1_1`.

## Credibilità X Research — Analisi statistica Fase 1C (2026-07-15)

Modulo statistico offline (`cecchino_draw_credibility_statistics.py`) con endpoint `statistical-analysis` e tab UI dedicato. Solo stdlib Python; conclusioni derivate dalle metriche, non hardcoded.

## Credibilità X Research — Correzione Dataset Fase 1B.1 (2026-07-15)

Fix semantica metriche globali/coorte, anti-leakage selezionato, export CSV completo e filename distinto. Versione `cecchino_draw_credibility_dataset_v1_1`.

## Credibilità X Research — Dataset storico Fase 1B (2026-07-15)

Laboratorio offline — seconda fase: costruzione dataset storico deduplicato con anti-leakage.

- Common: `backend/app/services/cecchino/cecchino_draw_credibility_research_common.py`
- Dataset: `backend/app/services/cecchino/cecchino_draw_credibility_dataset.py`
- Endpoint: `POST /api/admin/cecchino/research/draw-credibility/dataset`, export CSV su `.../dataset/export.csv`
- Frontend: tab Dataset storico in `/cecchino/ricerca-credibilita-x`
- Coorti primary/sensitivity/market; formule candidate solo nel service dataset
- Nessuna API esterna, nessuna migration, nessuna modifica al modello produttivo
- Prossimo step: Fase 1C analisi statistica

## Credibilità X Research — Audit storico Fase 1A (2026-07-15)

Laboratorio offline Cecchino per misurare copertura dati storici prima di definire la formula Credibilità X.

- Backend: `backend/app/services/cecchino/cecchino_draw_credibility_research.py`
- Endpoint: `POST /api/admin/cecchino/research/draw-credibility/audit`
- Frontend: `/cecchino/ricerca-credibilita-x` (sezione Cecchino sidebar)
- Nessuna API esterna, nessuna migration, nessuna modifica al modello produttivo
- Prossimo step: Fase 1B dataset storico

Documentazione: [SOT_PREDICTOR_CECCHINO.md](./SOT_PREDICTOR_CECCHINO.md).

## Cecchino — Condizione F32>=F34 su tutte le formule X (2026-07-09)

Tutte le formule SEGNO X (D42/E42/F42/G42) richiedono quota Cecchino 1 >= quota Cecchino 2 (`F32>=F34` / `q1>=q2`). Nessuna modifica Under/Over, Pannello KPI, Segnali KPI, soglie quota book.

## Cecchino — Modifica formule Under F39 e G39 (2026-07-09)

Formule Under F39 e G39 estese con `F32 >= F34` e `UNDER2.5 <= 2` (stesso parametro `under_2_5_cecchino_odd` di D39). Se UNDER2.5 assente → NO. D39/E39 invariati. Nessuna modifica Pannello KPI, Segnali KPI, soglie quota book.

## Cecchino — Modifica formula X F42 (2026-07-08)

Formula F42 (SEGNO X, Excel F) aggiornata: `=IF(AND(F33<=2.4,F36>-1.7,F32>=F34),"SI","NO")`. F32/F33/F34/F36 = quote 1/X/2 e differenza q2−q1. Il segnale si accende solo con quota X bassa, F36 > -1.70 e quota 1 ≥ quota 2. Nessuna modifica D42/E42/G42, Pannello KPI, Segnali KPI, soglie quota book.

## Cecchino — Soglie quota book configurabili (2026-07-08)

Soglie minime quota book editabili da admin e persistite in `cecchino_signal_min_book_odd_settings`. Default fallback in `cecchino_signal_min_odds.py` (X 3.00, X PT 1.90, 1X 1.37, X2 1.45, 1/2 1.37, Under 2.5 2.00, Over 2.5 1.85). API: `GET/PUT /api/admin/cecchino/signal-min-book-odds`, reset-defaults, save-and-backtest (backfill storico con ripescaggio). Pannello condiviso in `/monitoraggio-segnali` e Segnali Lab. Post-deploy: `alembic upgrade head`. Segnali KPI / formule Cecchino / rating KPI invariati.

## Cecchino — Soglie minime quota book nel Monitoraggio Segnali (2026-07-08)

Il Monitoraggio Segnali applica due filtri: (1) `quota_book >= quota_cecchino`; (2) `quota_book >= soglia minima` per mercato. Soglie centralizzate in `cecchino_signal_min_odds.py`: X 3.00, X PT 1.90, 1X 1.37, X2 1.45, 1/2 1.37, Under 2.5 2.00, Over 2.5 1.85. Monitoraggio classico e Segnali Lab condividono la logica; segnali sotto soglia esclusi/disattivati (no DELETE). Rebuild offline KPI da cache: `POST /api/admin/cecchino/rebuild-kpi-panels-from-cache`. *(Step 3: soglie configurabili in DB + pannello editabile.)* Segnali KPI / formule Cecchino / rating KPI invariati.

## Cecchino — X PT reale nel Pannello KPI (2026-07-08)

X PT nel Pannello KPI con quota book reale (FH 1X2 Betfair) e quota Cecchino da storico primo tempo. Monitoraggio usa quote proprie; nessuna modifica rating KPI / Segnali KPI / soglie book.

## Cecchino — Modifica formula Under D39 (2026-07-08)

Formula D39 aggiornata: Under Excel D richiede F36 in range, quota Cecchino 1 ≥ quota Cecchino 2 e quota Under 2.5 Cecchino ≤ 2. Modulo `cecchino_signal_goal_refs.py`; rebuild matrice post-goal_markets in Today. Solo matrice segnali + legenda; KPI/Segnali KPI/value gate/X PT invariati.

## Cecchino — Modifica formula X D42 (2026-07-08)

Formula D42 aggiornata: X Excel D richiede F36 in range e quota Cecchino 1 ≥ quota Cecchino 2. Solo matrice segnali + legenda; KPI/Segnali KPI/value gate/X PT invariati.

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
