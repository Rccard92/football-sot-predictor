# SOT Predictor — Changelog ragionato

## Cecchino — Modifica formula X D42 (2026-07-08)

- Aggiornata formula segnale X, colonna Excel D, cella D42.
- Nuova formula: `=IF(AND(F36<0.6,F36>-0.57,F32>=F34),"SI","NO")`.
- F32 = quota Cecchino 1 (`q1`); F34 = quota Cecchino 2 (`q2`); F36 = `diff_1_2` (= q2 − q1).
- Il segnale X/D si accende solo con F36 in range equilibrio **e** quota 1 ≥ quota 2.
- **Invariato:** E42/F42/G42, altre formule matrice, Pannello KPI, Segnali KPI, value gate, X PT.

## Cecchino — X primo tempo nel Monitoraggio Segnali (2026-07-05)

- Aggiunta activation derivata **X PT** (`DRAW_PT`): creata solo quando la X finale è SI e passa il filtro valore (`quota_book >= quota_cecchino`).
- X PT valutata sul risultato primo tempo già in DB (HT pari = vinta); non richiede FT né quota X PT autonoma.
- X PT è monitoraggio derivato: `quota_book`/`quota_cecchino` null; non altera metriche profitto quote prese.
- **Invariato:** mapping 1/2/1X/X2, Pannello KPI, Segnali KPI, formule Cecchino/KPI, matrice dettaglio partita.
- Ordine visualizzazione aggiornato: 1, X, 2, 1X, X2, 1/2, X PT, Under, Over.
- Nessuna DELETE; nessuna migration obbligatoria.

## Cecchino — Filtro valore quota sui segnali monitorati (2026-07-05)

- Introdotto value gate nel sync activation: `quota_book >= quota_cecchino` (Decimal) da `kpi_panel_json`.
- Monitoraggio Segnali, Segnali Lab e backtest modelli A–F mostrano solo segnali comprabili a valore.
- Activation no-value: `is_current=false`, `deactivated_at` e `evaluation_reason` (nessuna DELETE).
- Nuovo modulo `cecchino_signal_value_gate.py`; contatori backfill: `si_cells_seen`, `value_passed`, `no_value_skipped`, `deactivated_no_value`, quote mancanti.
- Ricalcolo storico: pulsante **Ricalcola filtro valore** (backfill `force_remap=true`, `only_missing=false`).
- **Invariato:** matrice SI/NO dettaglio partita, Pannello KPI, Segnali KPI, formule KPI/Cecchino, Betfair-only, SOT v2.0/v2.1.

## Frontend — Restyling Segnali KPI e default date odierna (2026-07-04)

- Rifatta UI pagina `/segnali-kpi` in stile Segnali Lab (framer-motion, card animate, heatmap moderna, drawer, metric ribbon, top ranking).
- Componenti dedicati in `frontend/src/components/cecchino-kpi-signals/` (KpiSignalsHeatmapLab, KpiSignalsActivationsLab, KpiRatingBucketCarousel, ecc.).
- Pagina Segnali KPI resta separata da Monitoraggio Segnali e Segnali Lab (modulo e tabella DB distinti).
- Default range data Cecchino: `date_from` e `date_to` = giornata odierna su Monitoraggio Segnali, Segnali Lab e Segnali KPI.
- Helper `todayLocalIso` / `isoDaysAgoLocal` in `frontend/src/utils/dateLocal.ts` (no UTC per default UI).
- **Invariato:** backend Segnali KPI, formule KPI/Cecchino, endpoint API, Betfair-only, SOT v2.0/v2.1.

## Cecchino — Robustezza backfill Segnali KPI (2026-07-04)

- Risolto 500 su `POST /api/admin/cecchino/kpi-signals/backfill` (errore mostrato in UI come CORS).
- Il backfill KPI isola errori per singola fixture (`begin_nested` + savepoint); una fixture problematica non blocca più tutta la sincronizzazione.
- Payload con `status: ok|partial`, contatori e `errors[]` diagnostici (`today_fixture_id`, `provider_fixture_id`, `match`, `error_type`).
- Mercati PT valutati solo con risultato primo tempo; FT mancante non causa più `int(None)`.
- Pending/result_missing non genera eccezione; `profit_units` resta null.
- **Invariato:** formule KPI, Segnali Cecchino (`evaluate_signal_activation`), Monitoraggio Segnali, Segnali Lab, Betfair-only, SOT v2.0/v2.1.

## Backend — Merge Alembic heads dopo Segnali KPI (2026-07-04)

- Risolto errore Railway «Multiple head revisions are present for given argument 'head'».
- Aggiunta merge migration Alembic `dd07defcb335` (`down_revision`: `20260704120000`, `5e0e69b60bde`); `upgrade()`/`downgrade()` pass — nessuna DDL.
- Nessuna modifica schema distruttiva; nessuna migration esistente cancellata.
- Nessuna modifica formule Cecchino, Segnali KPI (logica), Monitoraggio Segnali, Betfair-only, SOT v2.0/v2.1.
- Una sola Alembic head verificata (`dd07defcb335`); Railway continua con `alembic upgrade head`.

## Cecchino — Segnali KPI (2026-07-04)

- Introdotta nuova pagina **Segnali KPI** (`/segnali-kpi`) per monitorare righe Pannello KPI con rating ≥ 50 e quota book presente.
- Scaglioni rating: 50–59, 60–69, 70–79, 80–89, 90–99, 100.
- Valutazione esito su risultati PT/FT già salvati; stake fisso 1; metriche win rate, quota media, quota void, profitto e ROI.
- Nuova tabella `cecchino_kpi_signal_activations` (FK RESTRICT, separata da `cecchino_signal_activations`).
- Endpoint: summary, activations, export CSV, backfill e revaluate admin — **nessuna chiamata API esterna**.
- **Invariato:** formule KPI/Cecchino, Monitoraggio Segnali, Segnali Lab, Betfair-only, SOT v2.0/v2.1, cleanup/retention.

## Cecchino Today — Gate locale data fixture (2026-07-03)

- Aggiunto controllo locale di coerenza tra `scan_date` e kickoff locale fixture (timezone default `Europe/Rome`).
- La scansione processa solo fixture con `fixture_local_date == scan_date` (`get_fixture_local_date`, `fixture_belongs_to_scan_date` in `cecchino_today_fixture_filter.py`).
- Fixture restituite dal provider ma appartenenti ad altro giorno vengono saltate subito dopo il fetch, prima di qualsiasi upsert.
- Le fixture fuori data non compaiono più nel debug escluse del giorno sbagliato e non chiamano Betfair/stats/KPI.
- Aggiunti contatori report job: `provider_items_received`, `provider_out_of_scan_date_skipped`, `fixtures_in_scan_date`; opzionale `out_of_scan_date_examples` (max 10).
- `fixtures_found` resta il conteggio in-scope (compatibilità UI).
- **Invariato:** formule Cecchino, Pannello KPI, segnali, Monitoraggio Segnali, Monitoraggio Segnali Lab, backtest A–F, EGE, ICM, Intensità Goal, Equilibrio, Betfair-only, SOT v2.0/v2.1, `team_sot_predictions`, cleanup/retention, database.

## Backend — Fix circular import helper datetime Cecchino (2026-07-03)

- Risolto `ImportError` al startup Railway: catena `v10_prior_context` → `cecchino.cecchino_datetime` → `cecchino.__init__` → `cecchino_fixture_history` → `v10_prior_context`.
- Helper datetime spostato da `cecchino/cecchino_datetime.py` a modulo neutro [`datetime_utils.py`](../backend/app/services/datetime_utils.py) (stesse funzioni: `utc_now`, `ensure_datetime_utc`, `ensure_datetime`, `safe_isoformat`, `fixture_key_before_safe`, ecc.).
- `app.services.cecchino.__init__` reso side-effect free: rimossi re-export pesanti da `cecchino_constants`, `cecchino_engine`, `cecchino_fixture_history`.
- Import aggiornati in 8 file (v10, ingestion, moduli Cecchino Today, test).
- **Invariato:** formule Cecchino, KPI, ICM, Intensità Goal, EGE (formule), segnali, Monitoraggio/Lab, backtest A–F, Betfair-only, SOT v2.0/v2.1, `team_sot_predictions`, database.

## Cecchino — Fix robustezza datetime in scansione Today (2026-07-03)

- Risolto bug tecnico `'str' object has no attribute 'utc'` causato da shadowing del parametro `timezone: str` su `datetime.timezone` in `run_scan` (path esclusione bookmaker).
- Aggiunto helper centralizzato [`datetime_utils.py`](../backend/app/services/datetime_utils.py): `ensure_datetime_utc`, `ensure_datetime`, `safe_isoformat`, `utc_now`, `fixture_key_before_safe`.
- La pipeline Cecchino Today ora gestisce datetime aware/naive, stringhe ISO con `Z`, offset `+00:00` e date senza timezone.
- Una partita non viene più esclusa per bug tecnico data/orario; date invalide tracciate con motivi espliciti (`target_kickoff_invalid`, `prior_fixture_kickoff_invalid`, `datetime_normalization_error`).
- KPI missing non nasconde più errori datetime: debug `kpi_status=skipped_due_to_datetime_error` + `datetime_debug` su partite escluse.
- **Invariato:** formule Cecchino, Pannello KPI (logiche), ICM, Intensità Goal, Expected Goal Engine (formule), Segnali Cecchino, Monitoraggio Segnali, Monitoraggio Segnali Lab, backtest modelli A–F, Betfair-only, modelli SOT v2.0/v2.1, `team_sot_predictions`.

## Cecchino — Disabilitazione cleanup automatico storico (2026-06-09)

- Rimosso `cleanup_cecchino_today_snapshots` da `run_scan`: nessuna DELETE automatica post-scan.
- Log post-scan: `Cecchino retention cleanup disabled: historical data is preserved`.
- Cleanup manuale admin (`POST /api/admin/cecchino/today/cleanup`) protetto da:
  - `dry_run=true` di default (solo conteggio `would_delete`, nessuna DELETE);
  - `CECCHINO_ALLOW_DESTRUCTIVE_CLEANUP=false` di default (env `cecchino_allow_destructive_cleanup`);
  - token `confirm=DELETE_CECCHINO_HISTORY` obbligatorio per delete reale.
- `DEFAULT_RETENTION_DAYS=7` resta solo parametro del cleanup manuale (cutoff), non più usato in scan.
- Timeline ±30 (`CECCHINO_TODAY_TIMELINE_WINDOW_DAYS`) invariata — solo navigazione UI, non cancella dati.
- ATTENZIONE CASCADE: DELETE su `cecchino_today_fixtures` elimina `cecchino_signal_activations` collegate.
- **Invariato:** revalidate, recompute, update-results, backtest segnali, Equilibrio, Intensità Goal, ICM, EGE, KPI, Monitoraggio/Lab, Betfair-only, SOT v2.0/v2.1, `team_sot_predictions`.

## Cecchino — Timeline estesa ±30 giorni (2026-06-11)

- Estesa la finestra navigabile della timeline Cecchino Today da ±7 a ±30 giorni (`CECCHINO_TODAY_TIMELINE_WINDOW_DAYS`).
- La modifica riguarda solo la visualizzazione/navigazione della timeline (`GET /api/cecchino/today/days`).
- Nessun dato storico viene cancellato dalla timeline; il cleanup automatico post-scan è stato disabilitato (vedi sezione sopra).
- Monitoraggio Segnali e Monitoraggio Segnali Lab restano invariati.
- Backtest modelli A–F e statistiche storiche restano invariati.
- Nessuna modifica a Expected Goal Engine, ICM, Intensità Goal, Equilibrio, Betfair-only o moduli SOT.

## Cecchino — Fase 53 — xG storico automatico per fixture eleggibili (2026-06-09)

- Automatizzato il recupero xG storico current season alla eleggibilità Cecchino (scan, recompute, revalidate, detail lazy).
- Profili xG persistiti su `cecchino_today_fixtures.xg_profiles_json` (`cecchino_xg_profiles_v1`).
- Cache-first su `FixtureTeamStat`; chiamate API solo `fixture_statistics` su cache miss.
- Source diagnostics aggiornato a `current_season_historical_xg`; payload con `xg_profiles` e `xg_api_usage`.
- Hook non bloccanti: errori/rate-limit non impattano eleggibilità.
- UI: nota anti-leakage automatica, warning campione basso, pulsante opzionale «Ricalcola xG storico».
- **Invariato:** variabili non-xG diagnostics, Equilibrio, Intensità Goal, ICM, Monitoraggio, Betfair-only, SOT v2.0/v2.1.

## Cecchino — Fase 52 — xG storico current season per Expected Goal Engine (2026-06-09)

- Aggiornato il recupero delle variabili xG nel diagnostics builder Expected Goal Engine.
- Gli xG non usano più la partita corrente (anti-leakage esplicito).
- Calcolo xG For e xG Against su tutte le partite precedenti disponibili del campionato/stagione corrente.
- Escluse partite stagione precedente, coppe/competizioni diverse e fixture analizzata.
- Mapping da `fixture_statistics` → `expected_goals` (case-insensitive).
- Aggiunto `sample_size` xG con soglie availability dedicate (≥3 available).
- Nota anti-leakage in UI diagnostica; endpoint admin backfill xG opzionale.
- **Invariato:** variabili non-xG diagnostics, Equilibrio, Intensità Goal, ICM, Monitoraggio, Betfair-only, SOT v2.0/v2.1.

## Cecchino — Fase 51 — API Raw Inspector per Expected Goal Engine (2026-06-09)

- Aggiunto strumento **API Raw Inspector** per ispezionare dati raw/cache/API di una singola fixture.
- Endpoint admin `GET /api/admin/cecchino/fixtures/{today_fixture_id}/api-raw-inspector` — solo invocazione manuale dalla UI.
- Ricerca ricorsiva per keyword xG, expected, expected goals, xGA, npxg e simili.
- Distinzione esplicita tra `today_fixture_id` interno e `provider_fixture_id` provider.
- Sezione `suggested_xg_mapping` non invasiva (solo suggerimento, non modifica il diagnostics builder).
- UI tecnica dentro **Expected Goal Engine — Diagnostica Variabili** con pulsanti Ispeziona cache / API live / JSON completo.
- Warning consumo chiamate provider sull’ispezione API live.
- Nessuna modifica al diagnostics builder ufficiale in questa fase.
- **Invariato:** Equilibrio vs Squilibrio, Intensità Goal, ICM, Monitoraggio Segnali, Monitoraggio Segnali Lab, Betfair-only, modelli SOT v2.0/v2.1.

## Cecchino — Fase 50 — Expected Goal Engine Diagnostica Variabili (2026-06-09)

- Introdotto payload `expected_goal_engine_diagnostics` nel dettaglio Cecchino Today.
- Diagnostica variabili per il futuro Expected Goal Engine (audit only, nessun calcolo finale).
- Mappati Blocco A Produzione Goal (8), Blocco B Distribuzione Temporale (7), Correttori Avanzati (5).
- Aggiunto coverage variabili disponibili e readiness del motore (`can_compute_*` diagnostico).
- UI: sezione **Expected Goal Engine — Diagnostica Variabili** tra Intensità Goal e ICM.
- Tabella variabili con stato, valore, fonte, campo sorgente, campione; JSON raw/debug.
- Nessun pronostico secco; nessun goal atteso calcolato in questa fase.
- **Invariato:** Equilibrio vs Squilibrio, Intensità Goal, ICM, Segnali, Monitoraggio, Betfair-only, SOT v2.0/v2.1.

## Cecchino — Fase 49 — Intensità Goal v4 Goal Attesi (2026-06-09)

- Aggiornata la sezione Intensità Goal alla versione **v4 Goal Attesi** (`cecchino_goal_intensity_v4_expected_goals`).
- Rimossa la classificazione basata su percentile OVER Q44 (v3).
- Introdotta classificazione basata sui Goal Attesi Cecchino interni (`lambda_total` motore Poisson goal).
- Aggiunte soglie progressive Over 0.5, Over 1.5, Over 2.5 e Over 3.5.
- Molto Difensiva = goal attesi sotto 0.5; Difensiva = solo Over 0.5; Equilibrata = Over 0.5+1.5; Offensiva = fino a Over 2.5; Molto Offensiva = fino a Over 3.5.
- Chiarito che non vengono usati xG esterni, risultati reali o quote bookmaker.
- UI: badge v4 Goal Attesi, Goal Attesi Cecchino, soglie Over accese/spente, scala intensità, dettaglio tecnico v4.
- **Invariato:** Equilibrio vs Squilibrio, ICM, KPI, Segnali, Monitoraggio stabile/Lab, Betfair-only, SOT v2.0/v2.1.

## Cecchino — Fase 48 — Intensità Goal v3 OVER-only (2026-06-09)

- Aggiornata la sezione Intensità Goal alla versione **v3 OVER-only** (`cecchino_goal_intensity_v3_over_only`).
- Classificazione basata sul **percentile rank** di OVER Q44 rispetto allo storico Cecchino (metodo `proportion_leq`).
- Baseline OVER-only con mediana e percentili P20/P40/P60/P80; fallback league → country → global invariato.
- UNDER Q44 non influenza più `final_label`, `plain_summary` né classificazione (deprecato nel payload).
- Indice vs mediana: `over_index_vs_median = OVER Q44 / median_over_q44`.
- UI: badge v3 OVER-only, metriche Pressione Goal / Percentile / Indice vs Mediana / Baseline Mediana, scala percentile, box baseline.
- **Invariato:** Equilibrio vs Squilibrio, ICM, KPI, Segnali, Monitoraggio stabile/Lab, Betfair-only, SOT v2.0/v2.1.

## Cecchino — Fase 47 — Intensità Goal v2 calibrata (2026-06-09)

- Aggiornata la sezione Intensità Goal alla versione **v2 calibrata** (`cecchino_goal_intensity_v2`).
- Mantenuto il calcolo grezzo di OVER Q44 e UNDER Q44; introdotta normalizzazione su baseline storica mediana.
- Il Rapporto Intensità usa ora OVER normalizzato / UNDER normalizzato; il Delta usa OVER norm − UNDER norm.
- La classificazione finale usa il rapporto calibrato, non il rapporto grezzo.
- Baseline con fallback: stesso campionato (≥30), stessa nazione (≥40), globale Cecchino (≥50).
- UI: badge v2 calibrata, valori normalizzati, grezzi, baseline e fonte baseline; stato baseline insufficiente.
- **Invariato:** Equilibrio vs Squilibrio, ICM, KPI, Segnali, Monitoraggio stabile/Lab, Betfair-only, SOT v2.0/v2.1.

## Cecchino — Fase 46 — Intensità Goal (2026-06-09)

- Aggiunta nuova sezione **Intensità Goal** nel dettaglio analisi Cecchino Today, tra Equilibrio vs Squilibrio e Indice di Convergenza Match.
- Modulo indipendente `build_cecchino_goal_intensity_analysis` (v1, sostituita da Fase 47): Indice Offensivo da OVER Q44, Indice Difensivo da UNDER Q44 (parità Excel goal).
- Rapporto Intensità = indicatore principale; Delta Intensità = conferma testuale.
- Classificazione rapporto: &lt;0.70 Molto Difensiva, 0.70–&lt;0.90 Difensiva, 0.90–1.05 Equilibrata, &gt;1.05–1.20 Offensiva, &gt;1.20 Molto Offensiva.
- Classificazione delta: Forte/Moderata Spinta Offensiva, Zona Neutra, Moderata/Forte Spinta Difensiva.
- UI: card classificazione, 4 metriche, scala rapporto, conferma delta, accordion dettaglio tecnico.
- **Non implementati:** Goal Attesi Totali, Goal Casa, Goal Ospite, Dominanza Offensiva, Risultati Compatibili.
- **Invariato:** Equilibrio vs Squilibrio, ICM, KPI, Segnali, Monitoraggio stabile/Lab, Betfair-only, SOT v2.0/v2.1, `team_sot_predictions`.

## Cecchino — Fase 45 — Aggiornamento formule segnali 1, 2, 1X, X2 e 12 (2026-06-09)

- Aggiornata formula D48 (segno 1): `G48=SI`, `F36>2`, `Dominanza>10`.
- Aggiornata formula D54 (segno 2): `G54=SI`, `F36<-2.3`, `Dominanza>10`.
- Aggiornata formula E51 (1X): tolleranze su F32/F33/F34 (+0.4 / +0.5 / +0.6).
- Aggiornata formula G57 (X2): tolleranze inverse su F32/F33/F34 (+0.5 / +0.6 / +0.7).
- Aggiornata formula D60 (12): quota X alta con favorito 1 o 2 (soglia 4.8).
- Aggiornata formula E60 (12): `F33>=4.8`, `Dominanza>=10`, `|F36|>=1.5`.
- Introdotta Dominanza condivisa (`compute_dominance_pp`) dalla logica Equilibrio vs Squilibrio; scala in punti percentuali.
- Legenda formule aggiornata in Monitoraggio Segnali stabile e Lab (componente condiviso).
- Backtest modelli A–F, revaluate e backfill usano le nuove formule via `build_signals_matrix`.
- **Invariato:** Betfair-only, modelli SOT v2.0/v2.1, `team_sot_predictions`, KPI, ICM, G48/G54 e altre formule non elencate.

## Cecchino — Fase 44 — Monitoraggio Segnali Lab (2026-06-09)

- Aggiunta pagina sperimentale **Segnali Lab** (`/monitoraggio-segnali-lab`) con UI premium isolata in `components/cecchino-lab/`.
- Stessi endpoint e dati della pagina stabile `/monitoraggio-segnali` (models-summary, summary, activations, backtest, revaluate, export CSV).
- UI Lab: card modelli A–F animate, ribbon metriche, grafici ECharts (confronto modelli, donut esiti, top segnali), heatmap con drawer dettaglio, ranking top segnali, tabella partite.
- Dipendenze frontend: `framer-motion`, `echarts`, `echarts-for-react`, `sonner` (toast globali in `main.tsx`).
- Voce sidebar **Segnali Lab** (icona flask); localStorage separato `cecchino_signals_lab_selected_model`.
- **Invariato:** backend, pagina stabile Monitoraggio Segnali, componenti `cecchino/signals/*`, Cecchino Today, SOT v2.0/v2.1, Betfair-only.

## Cecchino — Fase 43 — Backtest modelli pesi A-F (2026-06-09)

- Introdotto confronto modelli pesi A–F nel Monitoraggio Segnali; ogni modello ha pesi indipendenti sui picchetti 1X2.
- Aggiunto `model_key` sulle signal activations (`model_label`, `weights_version`, `weights_json`).
- Aggiunto backtest offline dei modelli su range date (`POST /api/admin/cecchino/signals/backtest-models`) — zero API-Football.
- Aggiunta sezione **Confronto modelli pesi** con card cliccabili A–F (Win Rate, pesi, quota prese, quota void, rendimento).
- Cliccando un modello si aggiornano summary, heatmap, top segnali e dettaglio partite (filtro `model_key`).
- Aggiunto endpoint `GET /api/admin/cecchino/signals/models-summary` per le card comparativi.
- Aggiornati summary, activations ed export CSV con filtro `model_key` (default F = modello conservativo / storico live).
- I modelli A–F sono backtest comparativi in Monitoraggio Segnali; il Cecchino Today live resta sulle costanti attuali.
- Nessuna modifica ai modelli SOT v2.0/v2.1, a Betfair-only, a formule segnali, ICM o KPI produzione live.

## Cecchino — Fase 42 — Quota media prese e Quota Void (2026-06-09)

- Aggiunta metrica **Quota media prese** nel Monitoraggio Segnali: media quote book solo su segnali WON con quota disponibile.
- Segnali LOST e WON senza quota book esclusi dalla media.
- Aggiunta **Quota Void** = 1 / Win Rate; **Margine Void** = quota prese − quota void; **Rendimento prese** = WR × quota prese − 1.
- Summary API (`overall`, `by_signal`, `by_column`, `by_signal_and_column`) arricchito con le nuove metriche.
- Heatmap, Top segnali (ordinamento per rendimento prese), dettaglio partite ed export CSV aggiornati.
- `POST /revaluate` con `refresh_signal_odds=true` ripopola quote da `kpi_panel_json` salvato (offline, zero API).
- Nessuna modifica a Betfair-only, SOT v2.0/v2.1, KPI, ICM, Equilibrio, formule segnali.

## Cecchino — Fase 41 — Indice di Convergenza Match ICM (2026-06-09)

- Sostituito Delta Forza Match con ICM: convergenza interna degli indicatori Cecchino (non book vs Cecchino).
- Nuovo builder `build_cecchino_icm_analysis` con narrative scoring, classificazione 0–100, driver parlanti e dettaglio tecnico.
- Rimosso Delta Forza da KPI panel, Equilibrio vs Squilibrio (griglia 4 card), legenda e payload API.
- Balance analysis v4 (`cecchino_balance_analysis_v4`) senza embed `delta_force`.
- Nuova sezione UI `CecchinoIcmAnalysisPanel` tra Equilibrio e Segnali.
- API: `icm_analysis` al posto di `delta_force_analysis`; flag `recompute_icm` nello schema recompute (ricalcolo implicito via KPI).
- Invariati: pesi Fase 40, Betfair-only, colonne KPI, formule Segnali, SOT v2.0/v2.1.

## Cecchino — Fase 40 — Nuovi pesi globali 1X2 e Under/Over (2026-06-09)

- Aggiornati i pesi dei picchetti per i segni 1X2: Totali stagione 30%, Casa/Fuori 30%, Ultime 6 totali 20%, Ultime 5 casa/fuori 20%.
- Aggiornati i pesi dei picchetti per Under/Over: Totale stagione 20%, Casa/Fuori 30%, Ultime 6 20%, Ultime 5 casa/fuori 30%.
- Separate e validate le costanti `CECCHINO_1X2_WEIGHTS` e `CECCHINO_GOAL_MARKET_WEIGHTS` (somma = 1.0).
- Aggiornati KPI, Debug Picchetti, Equilibrio vs Squilibrio, Delta Forza e Segnali Cecchino (input da nuove quote).
- Aggiunto endpoint `POST /api/admin/cecchino/recompute` per ricalcolo offline storico (no API-Football se `refresh_bookmaker_odds=false`).
- Pulsante UI «Ricalcola Cecchino con nuovi pesi» su Cecchino Today e Monitoraggio Segnali.
- Versioni debug: `1x2_weights_30_30_20_20`, `goal_weights_20_30_20_30`.
- Nessuna modifica ai modelli SOT v2.0/v2.1, `team_sot_predictions`, Betfair-only.

## Cecchino — Fase 39 — Legenda formule Monitoraggio Segnali (2026-06-08)

- Aggiunta sezione espandibile sotto la Heatmap Segnale × Colonna in Monitoraggio Segnali.
- La legenda mostra cella Excel, formula Excel, formula parlante, target e regola W/L per ogni segnale/colonna.
- Documentate tutte le formule della tab CECCHINO (UNDER 2.5, SEGNO X, OVER 2.5, 1, 1X, 2, X2, 12).
- Chiarito che SCALA è valida solo per 1X (G48) e X2 (G54); D48 → 1 Excel D; D54 → 2 Excel D.
- Legenda statica frontend (`cecchinoSignalFormulaLegend.ts`); nessun endpoint backend aggiuntivo.
- Nessuna modifica a modelli SOT v2.0/v2.1, Betfair-only, KPI, Equilibrio, Delta Forza.

## Cecchino — Fase 38 — Fix definitivo Scala 1X/X2 (2026-06-08)

- Corretto definitivamente il mapping SCALA della matrice Segnali Cecchino.
- G48 assegnato solo a 1X / SCALA; G54 solo a X2 / SCALA; D48 a 1 / Excel D; D54 a 2 / Excel D.
- Rimosso il mapping errato HOME/AWAY su SCALA (guardrail sync + filtro summary/heatmap).
- `force_remap` ricostruisce sempre la matrice da quote finali (fix matrici legacy pre-Fase 37).
- Protezione backend: summary/list/export ignorano activation `HOME+SCALA` e `AWAY+SCALA`.
- Diagnostics: `legacy_wrong_scala_mapping_count` + banner UI con invito a Ricalcola mapping.
- Nessuna modifica a modelli SOT v2.0/v2.1, Betfair-only, KPI, Equilibrio, Delta Forza.

## Cecchino — Fase 37 — Correzione mapping Scala segnali (2026-06-08)

- Corretto mapping matrice: `scala_1x` (G48) su riga 1X (`ONE_X`), `scala_x2` (G54) su riga X2 (`X_TWO`).
- Righe 1/2 espongono solo `excel_d` (D48/D54); niente più activation `HOME+SCALA` / `AWAY+SCALA`.
- Aggiunto `remap_legacy_scala_activations_in_range` per disattivare activation legacy errate.
- Backfill/revaluate supportano `force_remap=true` (ricalcolo matrice + sync + rivalutazione offline).
- UI Monitoraggio: pulsante «Ricalcola mapping segnali»; matrice dettaglio mostra Scala solo su 1X/X2.
- Zero chiamate API-Football; nessuna modifica a SOT v2.0/v2.1, KPI Betfair-only, Under/Over Fase 34.

## Cecchino — Fase 36 — Delta Forza e Linearità Match (2026-06-08)

- Aggiunto Delta Forza come valore assoluto dell'Edge % su 1/X/2.
- Classificazione Partita statistica (<17%), Partita non statistica (17-31%), Forte favorita/Forte distorsione (>31%).
- Delta Forza Match basato sul massimo scostamento tra 1/X/2 con segno responsabile.
- Mini-card Delta Forza nel Pannello KPI senza nuove colonne.
- Quinta card Linearità in Equilibrio vs Squilibrio + dettaglio tecnico Delta 1X2.
- Legenda operativa v3 con blocco Lettura Delta Forza.
- Delta Forza completa F36/Dominanza senza sostituirli.
- Nessuna modifica a Betfair-only né modelli SOT v2.0/v2.1.

## Cecchino — Fase 35 — Sidebar Cecchino e metriche Monitoraggio Segnali (2026-06-08)

- Creata sezione Cecchino nella sidebar con voci in alto: Cecchino, Cecchino Today, Monitoraggio Segnali.
- Rinominate righe heatmap `UNDER / UNDER PT` → `UNDER 2.5` e `OVER / OVER PT` → `OVER 2.5`.
- Aggiunta card «Media segnali / partita» nel Monitoraggio Segnali.
- Aggiornato summary endpoint con `avg_signals_per_fixture`, `eligible_fixtures_count`, `fixtures_with_signals_count`.
- Nessuna modifica ai modelli SOT v2.0/v2.1, Betfair-only, logica valutazione segnali Fase 34.

## Cecchino — Fase 34 — Mapping Under/Over su 2.5 FT (2026-06-08)

- Mappati segnali aggregati `UNDER_UNDER_PT` e `OVER_OVER_PT` su Under/Over 2.5 FT nel monitoraggio.
- Aggiunto remap automatico activation storiche `not_evaluable` prima di backfill/revaluate.
- Rimosso early-skip in `evaluate_activations_for_fixture` per rivalutare record già persistiti.
- Messaggi `evaluation_reason` leggibili (es. «Totale gol FT 3: Over 2.5 vinto»).
- UI: target «Under 2.5 FT» / «Over 2.5 FT» e nota esplicativa sotto heatmap.
- Zero chiamate API-Football aggiuntive; nessuna modifica a SOT v2.0/v2.1, KPI Betfair-only, mercati PT.

## Cecchino — Fase 33 — Backfill Monitoraggio Segnali (2026-06-08)

- Corretta pagina Monitoraggio Segnali vuota su giornate già scansionate prima del deploy Fase 32.
- Aggiunto backfill offline `POST /admin/cecchino/signals/backfill` da `cecchino_today_fixtures`.
- Aggiunto endpoint diagnostics per distinguere partite mancanti vs activations mancanti.
- Pulsante UI «Sincronizza segnali» con alert intelligente quando servono activations.
- `revaluate` supporta `sync_missing=true` per backfill automatico prima della valutazione.
- `summary` supporta `include_diagnostics=true`.
- Sync batch a fine scan giornaliero (`sync_signals_for_scan_date`).
- Backfill/revaluate/diagnostics offline-only — zero API-Football.
- Nessuna modifica a SOT v2.0/v2.1, KPI Betfair-only, Debug Picchetti, Equilibrio vs Squilibrio.

## Cecchino — Fase 32 — Monitoraggio Segnali Cecchino (2026-06-08)

- Mantenuta matrice Segnali Cecchino nel dettaglio analisi partita.
- Aggiunta pagina «Monitoraggio Segnali» (`/monitoraggio-segnali`) con KPI, heatmap Signal×Column, top segnali e lista dettaglio.
- Ogni segnale SI persistito in `cecchino_signal_activations` con sync idempotente (`is_current`, `deactivated_at`).
- Valutazione automatica esito dopo `POST /admin/cecchino/today/update-results` (solo DB, nessuna API extra).
- Mapping sicuro 1/X/2/1X/X2/12; UNDER/OVER generici restano `not_evaluable` finché manca target esplicito.
- Endpoint aggregati: summary, activations, export CSV, revaluate offline.
- Link «Apri monitoraggio segnali» nel dettaglio partita con filtri preimpostati per giornata.
- Nessuna modifica a SOT v2.0/v2.1, `team_sot_predictions`, KPI Betfair-only, Debug Picchetti, Equilibrio vs Squilibrio.

## Cecchino — Fase 31 — Legenda operativa equilibrio (2026-06-08)

- Aggiunta legenda operativa aggiornata (18 righe) nella sezione Equilibrio vs Squilibrio.
- Componente `CecchinoBalanceLegend` con accordion separato sotto Dettaglio tecnico.
- Tabella responsive: desktop overflow-x-auto, mobile card stack.
- Allineate 3 label operative backend alla legenda (DRAW dom bassa/media, laterale dom≤5).
- Campo `technical.legend_version`: `balance_operational_legend_v2_contextual_dominance`.
- Rimossa tabella regole ridotta dal dettaglio tecnico (sostituita dalla legenda completa).
- Nessuna modifica a formule F36/Dominanza/Gap né a Betfair-only / SOT v2.0/v2.1.

## Cecchino — Fase 30 — Dominanza contestualizzata (2026-06-08)

- Corretta interpretazione Dominanza nella sezione Equilibrio vs Squilibrio.
- Dominanza resta `prob_max − prob_seconda` in punti percentuali.
- Aggiunta distinzione tra Dominanza della X (`reinforces_balance`) e Dominanza laterale 1/2 (`weakens_balance` / `confirms_imbalance`).
- Se domina X, la Dominanza rafforza equilibrio e lettura X/Under; mai classificata come falso equilibrio.
- Falso equilibrio scatta solo con F36<0.75, dominanza>10 e best_side HOME/AWAY.
- Aggiunto indicatore Gap 1/2 Probabilistico (`side_probability_gap`).
- UI aggiornata: 4 card, dominance_context, flag `is_x_dominance`.
- Versione analisi: `cecchino_balance_analysis_v2`.
- Nessuna modifica a Betfair-only né SOT v2.0/v2.1.

## Cecchino — Fase 29 — Equilibrio vs Squilibrio (2026-06-08)

- Aggiunta nuova sezione «Equilibrio vs Squilibrio» nel dettaglio analisi Cecchino Today (sotto Debug Picchetti).
- Implementato calcolo F36 come quota 2 Cecchino meno quota 1 Cecchino; F36 assoluto come indicatore principale.
- Implementata Dominanza modello come differenza tra probabilità Cecchino più alta e seconda più alta (in p.p.).
- Implementata classificazione Quota X Cecchino (pareggio forte/possibile/debole/poco probabile).
- Aggiunta lettura incrociata F36 + Dominanza e lettura operativa (12 regole: X/Under, falso equilibrio, zona grigia, squilibrio confermato).
- Dettaglio tecnico in accordion con formule e tabella regole applicate.
- Campo `balance_analysis` in GET detail e JSON kpi-debug; dati solo da Cecchino 1/X/2, senza Betfair né SOT.
- Nessuna modifica a Betfair-only né ai modelli SOT v2.0/v2.1.

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
