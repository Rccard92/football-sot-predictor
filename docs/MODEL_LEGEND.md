# Legenda del modello (Serie A, tiri in porta)

Documento di riferimento per **baseline v0.1**, per le metriche di qualità e per i **layer informativi** aggiunti nello Step 9 (giocatori, formazioni, H2H, disponibilità). Se cambiano formule o pesi, aggiornare questo file insieme al codice.

## Obiettivo

Stimare i **tiri in porta attesi** (shots on target, SOT) per squadra su una partita, usando solo statistiche di squadra storiche e medie derivate dal database. Il totale match è la **somma** delle due stime squadra quando entrambe sono disponibili.

## Baseline v0.1: formula e pesi

Il valore atteso per lato è una **combinazione lineare** di sei fattori, ciascuno moltiplicato per un peso. I pesi di default (somma = 1) sono:

| Fattore | Peso |
|--------|------|
| Media stagionale tiri in porta fatti (`season_avg_sot_for`) | 0,30 |
| Media stagionale tiri in porta concessi dall’avversario (`opponent_season_avg_sot_conceded`) | 0,25 |
| Media tiri in porta fatti in casa o in trasferta (`home_away_avg_sot_for`) | 0,15 |
| Tiri concessi dall’avversario in casa o in trasferta (`opponent_home_away_avg_sot_conceded`) | 0,10 |
| Forma recente: ultime partite, attacco (`last5_avg_sot_for`) | 0,10 |
| Forma recente: ultime partite, difesa avversaria (`opponent_last5_avg_sot_conceded`) | 0,10 |

Formula sintetica:

\[
\text{expected\_sot} = \sum_k w_k \cdot \text{resolved}_k
\]

dove `resolved_k` è il valore numerico effettivamente usato per il fattore \(k\) dopo eventuali sostituzioni (fallback) se un input grezzo manca.

### Fallback sui fattori

Se un input grezzo è assente, la risoluzione usa in ordine: altri campi della stessa feature (es. media stagionale attacco), poi una **media pre-partita di campionato** se disponibile, infine un valore prudenziale numerico costante (es. 3,5). Le note utente sul breakdown indicano quando è stato usato un sostituto.

## Variabili principali (feature)

- **Medie stagionali** e **medie casa/trasferta** su tiri fatti e subiti.
- **Ultime 5 partite** (e meta come conteggio partite precedenti) per attacco e per ciò che l’avversario concede.
- Flag **`fallback_used`** quando i dati sono parziali e si è ricorsi a catene di sostituzione.

Tutti i valori provengono da partite già giocate prima del riferimento temporale della previsione (logica implementata nel servizio feature).

## `expected_sot`, qualità dati e affidabilità della previsione

- **`expected_sot`**: risultato arrotondato della combinazione pesata sopra, con pavimento a zero.
- **`confidence_score` / `confidence_label`** (API upcoming): restano allineati alla **qualità dei dati** (stesso significato di `data_quality_*`), per compatibilità con client esistenti. Il valore è euristico: quantità di storia disponibile (partite proprie e avversario), presenza della forma recente e penalità se sono stati usati fallback sulla riga feature. **Non** è una probabilità calibrata sull’errore di previsione.
- **`data_quality_score` / `data_quality_label`**: stesso contenuto di `confidence_*`, esposto esplicitamente nella risposta “Prossima giornata”.
- **`prediction_confidence_score` / `prediction_confidence_label`**: punteggio **prudenziale** mostrato come “affidabilità previsione”. Parte dalla qualità dati e applica tetti per la baseline v0.1 (es. massimo 85), aggiustamenti se il backtest stagionale riporta MAE/RMSE in certi intervalli, e una penalità se risultano fallback sui fattori. Anche questo **non** è una probabilità calibrata.

Il backtest (MAE, RMSE) **non** ricalcola questi punteggi riga per riga: serve solo al blocco aggregato stagionale esposto dal servizio backtest e riusato nell’euristica di `prediction_confidence_*`.

## Limiti noti (baseline v0.1)

- Nessuna modellazione esplicita del caso testa-coda o degli infortuni nel numeratore baseline.
- **Impatto giocatori** (profili, formazioni, disponibilità): layer informativi; **non** entrano nella formula `expected_sot` della v0.1.
- Dipendenza dalla qualità e completezza delle statistiche importate (API-Football → DB).
- Il backtest confronta previsioni con esiti reali solo dove esistono SOT effettivi a referto.

## Metriche di backtest (MAE, RMSE)

In linguaggio semplice:

- **MAE (errore assoluto medio)**: in media, di quanti tiri in porta la previsione si discosta dall’esito reale, senza guardare il segno dell’errore.
- **RMSE**: simile all’MAE ma **penalizza di più** gli errori grandi: un match molto sbagliato pesa più che tanti errori piccoli.

Entrambe sono calcolate sulle partite per cui esiste sia previsione sia dato reale.

## Layer roadmap (Step 9)

Dati aggiuntivi presenti nel sistema ma **non mescolati** nella formula baseline v0.1:

| Layer | Contenuto | Applicato alla previsione? |
|-------|-----------|----------------------------|
| Statistiche giocatore per partita | Colonne parse da API, persistite su `fixture_player_stats` | No |
| Formazioni storiche | `fixture_lineups` (allenatore, titolari, panchina) | No |
| Profili giocatore | `player_sot_profiles` (aggregati stagione) | No |
| Eventi disponibilità | `player_availability_events` (import cauto) | No |
| H2H | Riepilogo API + SOT da DB dove coperto | No |

### Import statistiche giocatore (`fixture_player_stats`)

**Problema riscontrato:** la risposta API-Sports `GET /fixtures/players` espone spesso `statistics` come **array di un oggetto** con blocchi annidati (`games`, `shots`, `goals`, …), non come lista di `{ type, value }`. Un parser solo “flat” lasciava `shots_on_target`, `shots_total` e altri campi vuoti nel DB pur avendo `raw_json` corretto.

**Mapping corretto (implementato in `parse_fixture_player_statistics` in [`backend/app/services/player_stats_parsing.py`](backend/app/services/player_stats_parsing.py)):** dal primo elemento di `statistics` si leggono, tra gli altri:

| Campo DB | Path tipico API |
|----------|-----------------|
| minutes, position, rating, captain, substitute | `games.*` |
| shots_total, shots_on_target | `shots.total`, `shots.on` |
| goals, assists | `goals.total`, `goals.assists` |
| passes_total, passes_key, passes_accuracy_pct | `passes.*` |
| tackles_*, interceptions | `tackles.*` |
| duels_*, dribbles_*, fouls_*, cards_* | rispettivi blocchi |

È mantenuto un **fallback** sul formato legacy `type`/`value`. Dopo correzione, `POST /api/admin/ingest/serie-a/{season}/player-stats` aggiorna le righe in modo idempotente.

**Diagnostica:** `GET /api/admin/debug/player-stats/serie-a/{season}/summary` e `.../sample` (sola lettura) per verificare distribuzione minuti/tiri e campioni di `raw_json`.

### Player Impact (profilo SOT) — layer debug, **non** in baseline

I profili in `player_sot_profiles` arricchiscono API e dashboard ma **non modificano** `expected_sot` (baseline v0.1 squadra). Il campo API/dashboard `player_profiles_sot_data_suspicious` segnala profili presenti ma senza alcun dato positivo sui tiri in porta aggregati (utile dopo import errato).

Per ogni giocatore e stagione (aggregazione da `fixture_player_stats`):

- **`appearances`**, **`total_minutes`**, **`avg_minutes`**, **`total_shots`**, **`total_shots_on_target`**, **`shots_on_target_per90`**, **`starts`**, **`team_sot_share_pct`**, **`last5_shots_on_target_per90`**, **`reliability_score`** come da logica nel servizio profili (vedi codice).
- **`reliability_score`**: 50 base; +20 se `total_minutes ≥ 900`; +10 se `appearances ≥ 10`; −20 se `total_minutes < 300`; clamp 0–100.

**Player impact v0_1** (valore salvato in `impact_score`, scala ~0–100):

- `normalized_sot_per90 = min(shots_on_target_per90 / 1,5, 1) × 100`
- `impact_score = 0,60 × normalized_sot_per90 + 0,25 × team_sot_share_pct + 0,15 × reliability_score`
- Se `total_minutes < 300`: **`impact_score` moltiplicato per 0,7** (penalità campione basso). Nelle API di riepilogo è esposto anche `sample_warning: true` quando i minuti totali sono sotto 300.

Le liste **top** in `GET .../player-sot-profiles/.../summary` privilegiano giocatori con minuti e tiri coerenti (ordinamenti in query; chi ha `shots_on_target_per90 = 0` in coda per la classifica per90).

### H2H (scontri diretti)

- Riepilogo da API-Football filtrato su **partite concluse** con risultato (`goals_home` / `goals_away` presenti). La partita **corrente** (stesso `api_fixture_id`) è esclusa dal campione; niente partite future o non finite nei conteggi W/D/L, nelle medie o in `last_5`.
- Conteggi vittorie / pareggi riferiti alle due squadre della scheda upcoming.
- **`h2h_sample_limited`**: `true` se il numero di match conclusi nel campione è inferiore a 5 (campione storico ridotto).
- **SOT storici**: solo per gli incontri H2H che esistono anche nel DB locale con `fixture_team_stats` completi; flag `h2h_sot_available` se almeno un match ha SOT lato casa e trasferta.

### Lineup e infortuni

- Le formazioni sono storiche (partite finite); per partite future di solito non c’è ancora riga in `fixture_lineups`.
- L’import infortuni/assenze è **prudente**: payload non gestibile → risposta `skipped` senza errore server.

## Flag: `*_applied_in_prediction`

Per chiarezza operativa:

- **`lineup_adjustment_applied`**, **`h2h_*` nei layer upcoming**, **`player_impact_status`**: sono **informativi** nell’API e nel frontend (sezione debug).  
- **`expected_sot_resolved` / pesi `WEIGHTS_BASELINE_V0_1`**: **non** sono stati modificati per includere questi layer.

Equivale a documentare che **`player_layer_applied_in_prediction = false`**, **`h2h_applied_in_prediction = false`**, **`availability_applied_in_prediction = false`** per la baseline v0.1.

## Roadmap: `expected_sot_adjusted_v0_2` (indicativa)

Step successivo possibile: una versione **v0.2** che introduca un **`expected_sot_adjusted`** (o nuova `model_version`) integrando in modo controllato layer giocatori / H2H / disponibilità, con pesi espliciti e validazione su backtest — **distinta** dalla baseline v0.1 attuale.

Altre idee: H2H o quote come feature aggiuntiva; aggiustamenti attacco/difesa per assenze. Mantenere tracciabilità: pesi, fallback e versione nel `raw_json` delle previsioni.

## Baseline v0.2 (player-only): `baseline_v0_2_player_adjusted`

Questa versione **affianca** la baseline v0.1 e applica **solo** una correzione prudente basata su `player_sot_profiles`.
Non applica H2H, motivation/context, availability (tutti a 0).

Formula:

`expected_sot_v0_2_player_adjusted = expected_sot_v0_1 + player_adjustment`

Dettaglio `player_adjustment`:

- si prendono fino a **top 5** giocatori per `impact_score` della squadra (preferendo `total_minutes >= 300`)
- si calcola `team_top5_avg_impact` e la media di campionato `league_avg_top5_impact`
- `player_strength_ratio = team_top5_avg_impact / league_avg_top5_impact`
- correzione prudente con cap `±0.35`:
  - `ratio >= 1.25` → `+0.35`
  - `ratio >= 1.10` → `+0.20`
  - `0.90 < ratio < 1.10` → `0`
  - `ratio <= 0.90` → `-0.20`
  - `ratio <= 0.75` → `-0.35`

Regole:

- `adjusted_expected_sot >= 1.0`
- arrotondamento a 2 decimali
- breakdown in `team_sot_prediction_adjustments.adjustment_breakdown` con:
  - `player_adjustment.applied = true|false`
  - `h2h_adjustment.applied = false`
  - `motivation_adjustment.applied = false`
  - `availability_adjustment.applied = false`

## Step 10: Post-matchday refresh pipeline

Endpoint admin orchestrato: `POST /api/admin/refresh/serie-a/{season}/post-matchday`.

Ordine step:
1. Sync fixtures
2. Sync team stats concluse
3. Sync player stats concluse
4. Sync lineups concluse
5. Rebuild `team_sot_features` (completed, no leakage)
6. Regenerate `team_sot_predictions` baseline_v0_1 (completed)
7. Run backtest
8. Build upcoming features
9. Generate upcoming predictions
10. Build player SOT profiles

Ogni run è tracciata in `ingestion_runs` con source `post_matchday_refresh`.

## Baseline v0.2: `baseline_v0_2_context_player`

La v0.2 **affianca** la baseline v0.1, non la sostituisce.

Formula:

`expected_sot_v0_2 = expected_sot_v0_1 + player_adjustment + h2h_adjustment + motivation_adjustment + availability_adjustment`

Cap adjustment:

- player: `±0.35`
- H2H: `±0.20` (ridotto a `±0.10` con sample limitato)
- motivation/context: `±0.25`
- availability: fino a `-0.45`
- total adjustment: `±0.90`

Regole prudenziali:

- `adjusted_expected_sot >= 1.0`
- arrotondamento a 2 decimali
- se un layer non ha dati affidabili: adjustment `0` con stato `not_available`/`not_reliable`

Confidence v0.2:

- parte dal punteggio v0.1
- aggiustamenti su disponibilità layer e rischio contesto
- cap finale `[40, 85]`
- label: `Alta >= 80`, `Media >= 60`, `Bassa < 60`

Note anti-leakage:

- in questa iterazione la v0.2 è generata principalmente su upcoming
- nessuna riscrittura predizioni storiche v0.1
- nessun uso di formazioni ufficiali non disponibili

Stato applicazione layer:

- `player_impact_applied = true` in v0.2
- `h2h_applied = true` in v0.2
- `motivation_context_applied = true` in v0.2 upcoming
- `availability_applied = only_if_reliable`
- `official_lineups_applied = false`

Prerequisiti operativi v0.2 (`generate-v02-upcoming`):

- fixture upcoming disponibili
- prediction `baseline_v0_1` sulle upcoming gia generate
- `player_sot_profiles` disponibili per il layer player (altrimenti fallback `0`)
- standings disponibili per motivation context (altrimenti fallback `0`)
- tabella `team_sot_prediction_adjustments` presente a schema

Troubleshooting Railway:

- errore `Missing baseline_v0_1 prediction for fixture/team. Run generate-upcoming first.`:
  eseguire prima `POST /api/predictions/sot/serie-a/{season}/generate-upcoming`
- errore `Missing table team_sot_prediction_adjustments. Run alembic upgrade head.`:
  eseguire migration con `alembic upgrade head`
- verificare prerequisiti con `GET /api/predictions/sot/serie-a/{season}/v02-readiness`

## Standings layer

- Ingestion standings: `POST /api/admin/ingest/serie-a/{season}/standings`
- Lettura ultimo snapshot: `GET /api/standings/serie-a/{season}/latest`
- API-Football standings: chiamata `GET /standings` **senza paginazione** (`page` non supportato)
- Tabelle:
  - `standings_snapshots`
  - `standing_entries`

Il sistema usa sempre l’ultimo snapshot disponibile.
Lo standings layer e necessario per il layer motivation/context della v0.2 (in sua assenza il service applica fallback prudente a 0).

## Match Motivation Layer

Servizio: `backend/app/services/match_context_service.py`.
Endpoint: `GET /api/match-context/fixture/{fixture_id}`.

Per ogni squadra espone: objective, motivation level, reasons, turnover risk, warning, late-season-risk.
Il layer è prudente e descrive rischio/contesto, non certezze sulle formazioni.

## Logica `motivation_level` (prudenziale)

- Fine stagione (`round >= late_season_round_threshold`) => rischio più alto.
- Vicinanza a Champions/Europa/retrocessione entro `points_gap_close` => motivazione alta/media.
- Squadre senza obiettivo di classifica evidente => motivazione bassa/media e rischio turnover maggiore.
- Dati insufficienti (es. classifica assente) => `motivation_level=incerta`.

## Significato `turnover_risk`

`turnover_risk` è una stima qualitativa (`alto|medio|basso|incerto`) del rischio rotazioni.
Non implica che una squadra schiererà riserve: indica solo che il contesto competitivo può aumentare la variabilità.

## Limiti del layer motivation

- Non è una certezza sulle formazioni.
- Non sostituisce news pre-partita e formazioni ufficiali.
- È particolarmente utile nelle ultime giornate.

## Stato integrazione

- `motivation_context_applied_to_prediction = false`
- `motivation_context_visible_in_ui = true`

Il layer è visibile e debuggabile in API/UI, ma non modifica ancora il calcolo numerico baseline.

## Configurazione obiettivi stagionali

Configurazione Serie A 2025 in codice (`competition_context_config`):
- title/champions/europe/relegation zones
- soglia late season
- gap punti close/practically out

Queste soglie sono configurabili e vanno verificate stagione per stagione.

## Prossimo step

`expected_sot_adjusted_v0_2` con integrazione controllata di player impact e motivation context, separata dalla baseline v0.1.

## Legenda visibile in dashboard

La legenda non e piu solo documentale: e disponibile anche via API e frontend.

- Endpoint backend: `GET /api/model/legend`
- Pagina frontend dedicata: `Legenda Modello`
- Link rapidi:
  - Sidebar: voce `Legenda Modello`
  - Dashboard Modello: link `Apri legenda modello`
  - Prossima Giornata: link `Come funziona il modello?`

La risposta API include:

- `model_version`, `title`, `description`
- `expected_sot_formula` (formula esplicita baseline)
- sezioni ordinate:
  - `baseline_formula` (`applicata`)
  - `player_impact` (`solo_debug`)
  - `h2h` (`solo_debug`)
  - `match_context` (`solo_debug`)
  - `confidence` (`applicata_alla_lettura`)
  - `not_yet_applied` (`non_applicata`)

Ogni variabile espone nome leggibile, chiave tecnica, descrizione, peso (se applicabile), stato, impatto e interpretazione semplice.

Questa implementazione mantiene invariati:

- formula `expected_sot` baseline
- logica `baseline_v0_1`
- uso matematico di player impact, H2H e motivation context (restano informativi/debug).

## Framework Analisi Partita (documentazione)

Per una vista completa e consultabile di **tutte** le variabili che il modello può valutare pre-partita (divise per aree e per mercato), vedi:

- [`docs/MATCH_ANALYSIS_FRAMEWORK.md`](docs/MATCH_ANALYSIS_FRAMEWORK.md)

## Modello attivo e versioni modello

Per evitare ambiguità tra modelli disponibili e modello realmente usato in UI:

- **v0.1**: `baseline_v0_1` — baseline storica squadra pura.
- **v0.2**: `baseline_v0_2_player_adjusted` — correzione prudente “player impact” (se predictions presenti).
- **v0.3**: `baseline_v0_3_core_sot` — core SOT evoluto (componenti salvate in `raw_json`).
- **v0.4**: `baseline_v0_4_offensive_core_sot` — core offensivo migliorato (componente offensiva salvata in `raw_json`).

### Regola Prossima Giornata (routing)

La pagina **Prossima Giornata** deve usare gli endpoint di routing:

- `GET /api/predictions/sot/serie-a/{season}/model-status`
  - elenca quali `model_version` esistono davvero nel DB e la coverage sulle fixture upcoming
  - restituisce `recommended_model_version` per preferenza (v0.4 > v0.3 > v0.2 > v0.1) **solo se** disponibile per upcoming
- `GET /api/predictions/sot/serie-a/{season}/upcoming-active`
  - restituisce la Prossima Giornata usando la versione selezionata (o la recommended se non specificata)
  - include confronto con baseline v0.1 e differenza quando disponibili

### Regola Audit Variabili (coerenza)

La **Scheda Analisi Partita / Audit Variabili** deve mostrare variabili e componenti applicate al **modello attivo**.
Se Audit e Prossima Giornata risultano su `model_version` diverse, la UI deve mostrare un warning per evitare confusione.

## Model Debug e confronto versioni

Quando introduciamo una nuova `model_version` (es. v0.4), non è sostenibile verificare tutto “a mano” partita per partita.
Il **Model Debug** serve a confrontare automaticamente i numeri tra versioni e a segnalare i match che richiedono audit manuale.

### Cosa confrontiamo

Per una singola fixture confrontiamo:

- **casa**: `expected_sot` per ogni `model_version` disponibile
- **trasferta**: `expected_sot` per ogni `model_version` disponibile
- **totale match**: somma casa+trasferta (solo se entrambi i lati sono presenti per quel modello)

La diagnosi principale è centrata su **v0.1 / v0.3 / v0.4** (baseline, core SOT, core offensivo).
Le v0.2 sono mostrate se presenti, ma sono considerate secondarie per la diagnosi (possono introdurre layer specifici).

### Stati (Stabile / Da controllare / Red flag)

Regole iniziali (heuristiche, non probabilistiche):

- **Stabile**: scostamenti piccoli rispetto alla baseline v0.1 e range ridotto tra modelli.
- **Da controllare**: differenze moderate o segnali tecnici che riducono fiducia (fallback, cap, divergenza).
- **Red flag**: scostamenti molto grandi (soprattutto sul totale match) o modelli fortemente discordanti.

### Quando un modello è “troppo prudente” o “troppo aggressivo”

- **Troppo prudente**: v0.4 scende rispetto a v0.3 di oltre ~0.50 SOT sul singolo lato, o riduce il totale match in modo anomalo.
- **Troppo aggressivo**: v0.4 sale rispetto a v0.3 di oltre ~0.50 SOT sul singolo lato, o aumenta il totale match in modo anomalo.

In questi casi il debug evidenzia un motivo umano (“possibile prudente/aggressivo”) e suggerisce audit.

### Perché compare “fallback” o “cap applicato”

Quando il breakdown (`raw_json`) indica:

- **fallback usati**: alcuni input necessari non erano disponibili; il valore è calcolabile ma meno affidabile → stato almeno “Da controllare”.
- **cap applicato**: il componente è stato limitato (clamp) per prudenza; è atteso, ma va verificato nei match più estremi → stato almeno “Da controllare”.

### Endpoints di debug (read-only)

- `GET /api/debug/sot/fixture/{fixture_id}/model-comparison`:\n  confronto completo su una fixture, con diagnosi automatica.\n  Query param: `include_raw=true` per includere anche `raw_json` (tecnico).\n- `GET /api/debug/sot/serie-a/{season}/model-comparison/upcoming`:\n  panoramica della prossima giornata, ordinata per criticità (red_flag → inspect → stable).
