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

### Player Impact (profilo SOT)

I profili in `player_sot_profiles` sono un **layer di debug / analisi**: arricchiscono API e dashboard ma **non entrano** nel calcolo di `expected_sot` (baseline v0.1). Dopo `POST .../player-sot-profiles/.../build`, ogni `player_id` con almeno una riga in `fixture_player_stats` per la stagione ottiene un profilo.

Per ogni giocatore e stagione:

- **`appearances`**: numero di righe `fixture_player_stats` nella stagione.
- **`total_minutes` / `avg_minutes`**: somma dei minuti (null → 0), media su presenze.
- **`total_shots` / `total_shots_on_target`**: somme con null → 0.
- **`shots_on_target_per90`**: `total_shots_on_target / total_minutes * 90` se `total_minutes > 0`, altrimenti 0.
- **`starts`**: se esiste `start_xi` non vuoto in formazione per `(partita, squadra)`, titolare se `api_player_id` è tra gli id; altrimenti proxy **minuti ≥ 60** sulla singola partita.
- **`team_sot_share_pct`** (0–100): percentuale dei tiri in porta del giocatore rispetto alla somma dei tiri in porta di squadra (`fixture_team_stats`) sulle stesse partite in cui ha giocato; se il denominatore è 0 → 0.
- **`last5_shots_on_target_per90`**: sulle ultime al massimo 5 presenze (ordinate per data), media dei valori per 90′ (se minuti = 0 in una presenza, quel pezzo conta 0).
- **`reliability_score`**: 50 base; +20 se `total_minutes ≥ 900`; +10 se `appearances ≥ 10`; −20 se `total_minutes < 300`; clamp 0–100.
- **`impact_score`** (stessa scala 0–100 dei contributi):  
  `0,50 * normalized_shots_on_target_per90 + 0,30 * team_sot_share_pct + 0,20 * reliability_score`  
  con `normalized_shots_on_target_per90 = min(shots_on_target_per90 / 2, 1) * 100`.

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

## Roadmap v0.2 (indicativa)

- Opzionale: uso controllato di H2H o quote come **feature** aggiuntiva con pesi espliciti e versione modello nuova.
- Opzionale: aggiustamenti attacco/difesa per assenze pesate, solo dopo validazione e nuova versione (`model_version`).
- Mantenere sempre tracciabilità: pesi, fallback e versione nel `raw_json` delle previsioni.
