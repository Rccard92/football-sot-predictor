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

## `expected_sot` e `confidence_score`

- **`expected_sot`**: risultato arrotondato della combinazione pesata sopra, con pavimento a zero.
- **`confidence_score`** (0–100): punteggio euristico basato su quantità di storia disponibile (partite proprie e avversario), presenza della forma recente e penalità se sono stati usati fallback. Non è una probabilità calibrata; serve come **indicatore di affidabilità del dato** (bassa / media / alta nel testo mostrato all’utente).

## Limiti noti

- Nessuna modellazione esplicita del caso testa-coda o degli infortuni nel numeratore baseline.
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

- Dati testa-testa da API-Football; conteggi vittorie / pareggi riferiti alle due squadre della partita corrente.
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
