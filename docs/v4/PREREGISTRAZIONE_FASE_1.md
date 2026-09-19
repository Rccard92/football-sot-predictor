# Pre-registrazione Fase 1: motore gol ed esame E1

Scritta il 20 settembre 2026, prima di calcolare qualsiasi risultato dell'esame. Vale per `backend/app/services/cecchino_v4/engine_goals/` e `backend/app/services/cecchino_v4/exams/e1.py`. Il risultato va in `docs/v4/esami/E1.json` e `docs/v4/esami/E1.md`. I criteri qui sotto non si ritoccano dopo aver visto i numeri: ogni scostamento va dichiarato nel rapporto con il motivo.

## 1. Dati

Solo i CSV football-data in `backend/app/data/v4/football_data/`, caricati con `load_history()` (esclude 2025/26, regola 3). Stagioni: 2021/22 rodaggio, 2022/23, 2023/24, 2024/25 giudizio. I 16 campionati di `constants.LEAGUES`, raggruppati nelle piramidi nazionali della V3 (`COUNTRY_GROUPS`). Le quote del book presenti nello storico (`History.extras.odds_*`) non entrano in nessun punto del motore né dell'esame E1.

Partite valutate: solo `eval_eligible` (entrambe le squadre con almeno 5 partite giocate nella stagione e campionato), come nella V3. Il motore predice comunque ogni partita (regola 5).

## 2. Termine di paragone: V3 Fase 4 riprodotta

`engine_goals/baseline_v3.py::run_v3_phase4` riproduce la Fase 4 della V3 come funzione pura, importando il motore V3 come libreria senza modificarlo:

- specialista Forza (`walkforward.run_group`, `movers=False`) e specialisti Gioco tiri in porta e tiri (`walkforward.run_game_group`) su tutta la griglia `HYPER_GRID` (6 coppie xi/sigma), per ogni piramide;
- scelta degli iperparametri per stagione sulla stagione precedente (`select_hypers` e `_select_by_previous_season` di V3: log-loss 1X2 per la Forza, log-verosimiglianza Poisson dei gol per il Gioco; default nel rodaggio);
- pesi dell'orchestratore stimati sulla stagione precedente (`orchestrator.fit_weights`), prima senza correzioni (attese di base per la forma) poi con le correzioni Forma (`form.compute_form`) e Calendario (`calendar_features.compute_calendar`) unite da `build_adjustments`;
- gol attesi finali con `orchestrator.combine`; nessuna calibrazione, nessuna disciplina, nessun parametro promozione.

Gli helper privati di `cecchino_v3.service` (`_select_by_previous_season`, `_opinions`, `_orchestrator_weights`, `_base_expectations`, `_specialists_payload`, `build_adjustments`) sono ricopiati alla lettera in `baseline_v3.py` perché `service.py` non e' importabile senza database (istanzia `Settings()` all'import). Le 17 probabilita' vengono da `cecchino_v3.markets.market_probabilities`.

Il motore V4 con tutte le novita' spente deve restituire esattamente le probabilita' del termine di paragone (test automatico, differenza massima < 1e-9).

## 3. Le novita' (una alla volta, ognuna accendibile in `V4GoalsConfig`)

Ordine di prova: a, b, c, d, e. La f (handicap asiatico) e i blocchi `ratings` e `specialists` sono descrittivi: non cambiano le probabilita' dei 17 mercati e non hanno esame.

### a. Vantaggio casa per squadra (`team_home_advantage`)

Walk-forward dentro la piramide. Per ogni squadra T e ogni sua partita passata (giorni strettamente precedenti), residuo di differenza reti dal punto di vista di T rispetto ai gol attesi della V3 Fase 4 di quella partita:

`d = (gol fatti − gol subiti) − (lambda a favore − lambda contro)`

Somme pesate nel tempo con `exp(−xi·giorni)` (xi = 0,002, come `DEFAULT_HYPER`): `S_h`, `n_h` sulle partite in casa; `S_a`, `n_a` su quelle fuori. Deviazione di vantaggio casa della squadra, in gol di differenza reti, trattenuta verso zero con peso a priori `K = 20` partite (`K/2` per lato):

`hdev_T = 0,5 · [ S_h / (n_h + K/2) − S_a / (n_a + K/2) ]`

Per la partita casa H contro ospite A la correzione in scala logaritmica e'

`kappa = clip( (hdev_H + hdev_A) / 2 / (lambda_h + lambda_a) , −0,25, +0,25 )`

applicata come `lambda_h · exp(kappa)`, `lambda_a · exp(−kappa)`: la differenza reti attesa si sposta di circa `(hdev_H + hdev_A)/2`, i gol totali attesi restano invariati al primo ordine. Squadra senza partite passate: `hdev = 0`. I residui usano i gol attesi della V3 (senza questa correzione): nessun circolo.

### b. Rho Dixon-Coles per divisione (`division_rho`)

Verificato: la V3 stima un solo `rho` per piramide e giorno (`fit_rho` su tutta la finestra in `walkforward._run_strength`). La V4 rifa' la stessa stima (`strength_model.fit_rho`, stessa griglia −0,20…+0,20 passo 0,01, stessi gol attesi della Forza sulla finestra, stessi pesi) **restringendo la finestra alle partite della divisione** della partita da prevedere. Se il peso totale delle partite della divisione nella finestra e' sotto 100 partite equivalenti, resta il `rho` di piramide della V3. Lo specialista Forza per questo passo viene rieseguito dalla V4 (`strength_params.py`) con le stesse funzioni di `strength_model` e lo stesso iperparametro scelto per la stagione: il problema e' convesso, quindi i parametri coincidono con quelli della V3 a meno della tolleranza di Newton.

### c. Binomiale negativa per divisione (`division_dispersion`)

Per ogni divisione d, lato (casa/ospite) e stagione S: `alpha` con il metodo dei momenti sui residui fuori campione della stagione S−1 (partite `eval_eligible`, gol attesi V4 con le novita' adottate prima di questa):

`alpha = Σ[(y − lambda)² − lambda] / Σ lambda²`

Se `alpha ≤ 0,005` o le righe sono meno di `DISPERSION_MIN_ROWS` (200): Poisson (`dispersion = null`). Rodaggio 2021/22: Poisson. `Var = lambda + alpha·lambda²`.

Matrice dei punteggi (0…10 gol per lato, `MAX_GOALS` della V3): prodotto delle due marginali (binomiale negativa con media `lambda` e `r = 1/alpha`, oppure Poisson), correzione Dixon-Coles `tau` sui punteggi 0-0, 1-0, 0-1, 1-1 con lo stesso `rho`, troncamento a zero e normalizzazione: identica a `markets.score_matrix` quando `alpha` e' nullo. Tutti i mercati a tempo pieno (1X2, doppia chance, over/under, handicap) escono dalla stessa matrice. Il primo tempo resta come nella V3: Poisson con `lambda·ht_share`, `rho = 0`.

### d. Incertezza (`uncertainty`)

Segnali, tutti pre-partita e senza quote:

- `k = 1 − min(1, min(evidenza casa, evidenza ospite) / EVIDENCE_FULL_KNOWLEDGE)` con `EVIDENCE_FULL_KNOWLEDGE = 15` partite equivalenti (evidenza = somma dei pesi temporali delle partite della squadra nella finestra della Forza);
- `dis = max |log(lambda_i / lambda_j)|` tra gli specialisti Forza, tiri in porta, tiri, su entrambi i lati; `dnorm = min(1, dis / 0,5)`;
- `new_team_home`, `new_team_away`: la squadra non ha nessuna partita passata nella piramide (evidenza = 0); `nt = 1` se almeno una e' nuova.

Punteggio: `score = clip(0,50·k + 0,35·dnorm + 0,15·nt, 0, 1)`.

Livelli: per la stagione S i punti di taglio sono il 30° e il 70° percentile del punteggio sulle partite `eval_eligible` della stagione S−1 (bassa sotto il 30°, alta dal 70° in su). Nel rodaggio 2021/22 tagli fissi 0,20 e 0,45. La regola e' fissa e usa solo il passato; i valori realizzati vengono riportati in E1.json.

Intervallo al 90% per ogni mercato: perturbazione parametrica di `(log lambda_h, log lambda_a)` con deviazione `sigma = 0,05 + 0,20·score` per lato. Si valuta la probabilita' del mercato negli 8 punti a distanza `1,645·sigma` dal centro sulle 8 direzioni a 45° del piano `(log lambda_h, log lambda_a)`; `lo` e `hi` sono il minimo e il massimo tra il centro e gli 8 punti. Con la calibrazione (e) attiva, `lo` e `hi` passano per la stessa mappa isotonica di `p`.

### e. Calibrazione isotonica per mercato (`isotonic_calibration`)

Per la stagione S e ogni mercato: `sklearn.isotonic.IsotonicRegression(out_of_bounds="clip", y_min=0, y_max=1, increasing=True)` stimata sulle probabilita' V4 fuori campione (novita' adottate prima di questa) delle partite `eval_eligible` della stagione S−1 contro l'esito reale. Meno di `CALIBRATION_MIN_ROWS` (300) righe: identita'. Rodaggio 2021/22: identita' (`calibration.applied = false`).

Coerenza dopo la calibrazione: `HOME`, `DRAW`, `AWAY` calibrati e rinormalizzati a somma 1; doppia chance come somma dei tre calibrati; `OVER_x` calibrato e `UNDER_x = 1 − OVER_x`; `HOME_PT`, `DRAW_PT`, `AWAY_PT` calibrati e rinormalizzati. I mercati handicap non sono calibrati (escono dalla matrice, come descrittivi).

### f. Handicap asiatico (`AH_LINES`, descrittivo)

Dalla stessa matrice dei punteggi. `AH_HOME:L` = casa con handicap L (segno come in `docs/v4/API.md`): vince se `casa + L > ospite`, rimborso se `casa + L = ospite`. Linee a quarto: meta' puntata su ciascuna delle due linee adiacenti (es. −0,75 = meta' su −0,5 e meta' su −1,0). Probabilita' esposta:

`p = (quota di puntata vincente attesa) / (1 − quota di puntata rimborsata attesa)`

cioe' la probabilita' di vincita condizionata al non rimborso, pesata per le meta' puntate: e' il numero per cui `p · quota = 1` da' profitto atteso zero anche con i rimborsi. `AH_AWAY:L` simmetrico dal punto di vista dell'ospite. Controlli automatici: `AH_HOME:-0.5 = HOME`, `AH_HOME:+0.5 = ONE_X`, `AH_AWAY:-0.5 = AWAY`, `AH_HOME:0.0 = HOME / (HOME + AWAY)`.

### Blocco `ratings` (descrittivo)

Dal passo walk-forward della Forza rieseguito dalla V4 (stesso iperparametro della stagione, `beta` del giorno): `attack = a[T]`, `defence = b[T]` (scarti della squadra rispetto al livello della propria divisione, scala logaritmica; `defence` positivo = subisce meno). Classifiche (1 = migliore) tra le squadre della divisione che hanno gia' giocato almeno una partita in quella stagione fino a quel giorno, piu' le due squadre della partita; `teams_in_division` = numero di quelle squadre. `home_advantage = home[d] + 0,5·hdev_T / exp(mu[d] + home[d]/2)` (vantaggio casa della divisione piu' la deviazione della squadra, portata in scala logaritmica con la media gol della divisione).

## 4. Misure

Sulle partite `eval_eligible`, per famiglia (`FT_1X2`, `DOUBLE_CHANCE`, `FT_OVER_UNDER`, `HT_1X2`) e stagione di giudizio, sulle righe (partita, mercato della famiglia):

- **Brier**: media di `(p − y)²` (come il valutatore V3);
- **log-loss**: media di `−[y·ln p + (1−y)·ln(1−p)]`, con `p` limitata a `[1e-6, 1−1e-6]`;
- **errore di calibrazione**: 10 classi di `p` di ampiezza 0,1; media pesata per numerosita' di `|media p − frequenza reale|`, in punti percentuali; per `FT_1X2` e per `FT_OVER_UNDER`, stagioni di giudizio insieme;
- **errore in eccesso 1X2**: `Brier_1X2 reale − (1 − Σ p²)/3` per partita (come `reliability.excess_brier_1x2` della V3), mediato per livello di incertezza e stagione.

## 5. Criteri dell'esame E1 (verdetto finale, configurazione adottata contro V3 Fase 4)

- **E1.1** In ogni famiglia e in ogni stagione di giudizio: `Brier V4 ≤ Brier V3 · (1 + 0,001)` (tolleranza +0,1% relativa).
- **E1.2** In ogni famiglia: media del Brier sulle tre stagioni di giudizio piu' bassa della V3.
- **E1.3** Errore di calibrazione V4 ≤ V3 sia su `FT_1X2` sia su `FT_OVER_UNDER` (stagioni di giudizio insieme).
- **E1.4** Incertezza: in ogni stagione di giudizio l'errore in eccesso 1X2 medio e' strettamente decrescente alta → media → bassa e ogni livello contiene almeno il 15% delle partite `eval_eligible`.

L'esame e' superato solo se passano tutti e quattro.

## 6. Ablazione e regola di adozione

Si parte dal termine di paragone (tutte le novita' spente). Le novita' si provano nell'ordine a, b, c, d, e; ognuna si accende **sopra la configurazione adottata fino a quel momento** e si adotta solo se supera la sua regola; se non la supera, si spegne e si passa alla successiva.

- a, b, c, e (cambiano le probabilita'): adottate se, rispetto alla configurazione adottata fino a quel momento, valgono E1.1 ed E1.2 (tolleranza +0,1% in ogni famiglia e stagione; media piu' bassa in ogni famiglia). Per la e serve anche E1.3 rispetto alla configurazione precedente.
- d (non cambia le probabilita'): adottata se vale E1.4.

La configurazione finale adottata viene scritta come costante JSON `ADOPTED_CONFIG` in `engine_goals/config.py` ed e' quella usata dal live. Il verdetto E1 si calcola sulla configurazione adottata contro il termine di paragone. Se nessuna novita' che cambia le probabilita' viene adottata, E1.2 non puo' passare e l'esame risulta non superato: si riporta cosi'.

## 7. Live

`engine_goals/live.py::predict_targets` stima una finestra per (piramide, giorno bersaglio) con le sole partite di giorno strettamente precedente (le partite bersaglio non entrano mai nella finestra, controllo automatico), applica le stesse novita' adottate e usa gli oggetti stimati sull'ultima stagione completa (iperparametri scelti sul 2024/25, pesi dell'orchestratore, `alpha` di dispersione, tagli dell'incertezza, mappe isotoniche). Squadre mai viste: livello della divisione con la correzione "squadra nuova" della V3, `new_team = true`, incertezza `alta`.

## 8. Cache

Risultati intermedi pesanti (griglie walk-forward, parametri Forza per giorno) in `backend/.runtime/v4/` (ignorata da git), con chiave che include l'impronta dei dati e dell'iperparametro. La cache non cambia nessun numero.
