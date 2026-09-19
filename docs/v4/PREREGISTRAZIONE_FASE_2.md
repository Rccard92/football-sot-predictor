# Pre-registrazione Fase 2: motore statistiche ed esame E2

Scritta il 20 settembre 2026, prima di calcolare qualsiasi risultato dell'esame. Vale per `backend/app/services/cecchino_v4/engine_stats/` e `backend/app/services/cecchino_v4/exams/e2.py`. Il risultato va in `docs/v4/esami/E2.json` e `docs/v4/esami/E2.md`. I criteri qui sotto non si ritoccano dopo aver visto i numeri: ogni scostamento va dichiarato nel rapporto con il motivo.

## 1. Bersagli

Cinque statistiche (`constants.STATS`): tiri (`shots`), tiri in porta (`sot`), corner (`corners`), cartellini (`cards`), falli (`fouls`). Tre lati (`constants.STAT_SIDES`): casa, ospite, totale. I cartellini sono un conteggio pesato, giallo 1 e rosso 2 (`CARD_WEIGHT_YELLOW`, `CARD_WEIGHT_RED`): con questi pesi il valore e' sempre intero, quindi la distribuzione di conteggio si applica senza arrotondamenti.

Dati: solo i CSV football-data in `backend/app/data/v4/football_data/`, caricati con `load_history()`, che esclude la stagione 2025/26 (regola 3). Le quote Bet365 di chiusura presenti nello storico entrano **solo** nel punto (b) dell'esame come metro; mai nel modello.

## 2. Il modello (fissato prima dei risultati)

### 2.1 Struttura

Per ogni statistica, stesso modello log-lineare "fatto/subito" del motore V3 (`cecchino_v3.strength_model`, importato come libreria e non modificato), applicato al conteggio della statistica al posto dei gol:

- casa: `log E[fatto casa] = mu[d] + home[d] + for(casa) - against(ospite)`
- ospite: `log E[fatto ospite] = mu[d] + for(ospite) - against(casa)`

dove `d` e' la divisione della partita; `for(i)` e `against(i)` includono il livello della divisione di appartenenza, lo scarto medio delle squadre nuove nel dataset e lo scarto della singola squadra, trattenuto verso zero con deviazione a priori `sigma`. Il livello a priori `mu` parte dal logaritmo della media della statistica per squadra nel rodaggio (valore fisso in `config.py`).

**Gruppi.** Piramidi nazionali come nella V3 (`COUNTRY_GROUPS`): Inghilterra 4 divisioni, Italia 2, Spagna 2, Germania 2, Francia 2, Olanda, Belgio, Portogallo e Turchia da sole. Motivo: promosse e retrocesse si portano dietro la forza stimata, e la Fase 2 deve predire dalla prima giornata.

**Walk-forward.** Per ogni giorno di gara di un gruppo: finestra = tutte le partite del gruppo nei giorni strettamente precedenti, peso `exp(-xi * giorni)`, escluse quelle con peso sotto `MIN_TIME_WEIGHT`. Le partite dello stesso giorno non si vedono tra loro. Le partite bersaglio non entrano mai nella finestra.

**Stima.** Massima verosimiglianza di Poisson pesata per tempo e penalizzata (Newton, funzione convessa), identica alla V3: e' una quasi-verosimiglianza e vale per conteggi anche non interi.

### 2.2 Iperparametri

Griglia `xi ∈ {0.001, 0.002, 0.004}` per giorno, `sigma ∈ {0.1, 0.2, 0.4}`. Per la stagione S e la statistica k si adotta la coppia che ha ottenuto la **log-verosimiglianza di Poisson media piu' alta** sulle partite `eval_eligible` della stagione S−1 (lati casa e ospite), previste anch'esse walk-forward. Nella stagione di rodaggio 2021/22 si usa il default `xi=0.002, sigma=0.2`. Nessun iperparametro viene scelto guardando la stagione che si sta prevedendo.

### 2.3 Dispersione

Per ogni (divisione, statistica) e stagione S: binomiale negativa con parametro `alpha` stimato con il metodo dei momenti sui residui walk-forward della stagione S−1 (lati casa e ospite insieme):

`alpha = Σ[(y − m)² − m] / Σ m²`

Se `alpha ≤ 0` o le righe sono meno di `DISPERSION_MIN_ROWS` (200), si usa Poisson (`dispersion = null`). Nel rodaggio 2021/22: Poisson. `Var = m + alpha·m²`.

**Totale.** Il totale e' la somma dei due lati, trattati come indipendenti. Somma di Poisson = Poisson. Con binomiale negativa si fa aggancio dei momenti: `m_tot = m_casa + m_ospite`, `Var_tot = Var_casa + Var_ospite`, `alpha_tot = (Var_tot − m_tot) / m_tot²`.

### 2.4 Probabilita' per linea e intervallo

Per ogni linea `L` (mezza) in `constants.STAT_LINES[k]`: `P(over L) = 1 − F(⌊L⌋)` con `F` la funzione di ripartizione Poisson o binomiale negativa; `under = 1 − over`.

**Incertezza.** Deviazione a posteriori dello scarto di una squadra su scala logaritmica, approssimata da prior gaussiano piu' informazione di Poisson: `var(for_i) = 1 / (1/sigma² + evidenza_i · media_divisione)`, dove `evidenza_i` e' la somma dei pesi temporali delle partite della squadra nella finestra (partite equivalenti) e `media_divisione` la media della statistica per squadra nella divisione; lo stesso per `against`. Per un lato: `var(log m) = var(for attaccante) + var(against difensore)`. Per il totale: `var(log m_tot) = (m_c² var_c + m_o² var_o) / m_tot²`. L'intervallo al 90% della probabilita' over e' `[P(over | m·e^(−1.645·sd)), P(over | m·e^(+1.645·sd))]`, ordinato. Squadra mai vista nel gruppo: parametri a priori (scarto 0, offset squadra nuova) e `evidenza = 0`, quindi varianza massima `sigma²` per parametro.

### 2.5 Media di divisione e posizioni

- `division_mean` per lato: media pesata per tempo della statistica per squadra sul lato (casa, ospite, totale) nelle partite della divisione dentro la finestra; senza partite, media a priori.
- `rank_for`: posizione della squadra per `for` decrescente fra le squadre della divisione nella stagione in corso (che hanno gia' giocato in quella divisione prima del giorno, piu' quelle in campo quel giorno). `rank_against`: posizione per `against` decrescente (1 = subisce meno). `teams_in_division` = numero di squadre di quell'insieme. Per il totale sono `null`.

## 3. Esame E2

Partite `eval_eligible` (entrambe le squadre con almeno 5 partite giocate nella stagione, regola del valutatore V3) delle stagioni di giudizio 2022/23, 2023/24, 2024/25, con la statistica disponibile. Ogni metrica si calcola per statistica, per lato, per stagione.

### 3.1 Parte (a): accuratezza

**Baseline ingenue** (senza quote, senza decadimento):

- **B1**: media stagionale a oggi (stesso campionato e stagione, partite strettamente precedenti) del "fatto" della squadra sul lato, miscelata al 50% con il "subito" dell'avversaria; se una delle due ha meno di 3 partite, al suo posto la media di divisione a oggi. Totale = B1 casa + B1 ospite.
- **B2**: come B1 ma con le ultime 5 partite della squadra e dell'avversaria (stesso campionato e stagione), senza minimo.

Distribuzione predittiva delle baseline: Poisson con media pari alla baseline.

**Metriche.** MAE = media di `|y − m|`. CRPS calcolato numericamente dalla distribuzione predittiva: `CRPS = Σ_k [F(k) − 1(y ≤ k)]²` su `k = 0 … K` con `K` tale che la coda residua sia trascurabile (`K = max(y, m + 12·sd) + 5`).

**Criterio (a):** per ogni lato e ogni stagione di giudizio, MAE del modello < MAE di B1 e di B2, e CRPS del modello < CRPS di B1 e di B2 (confronto stretto sui valori non arrotondati).

**Calibrazione.** Per ogni statistica, tutte le coppie (partita, lato, linea di `STAT_LINES`) delle tre stagioni di giudizio insieme: 10 intervalli di ampiezza 0,1 sulla probabilita' over prevista; in ogni intervallo non vuoto lo scarto e' `|media delle probabilita' previste − frequenza degli over realizzati|`; il **divario medio** e' la media degli scarti pesata per il numero di osservazioni. Criterio: divario medio ≤ 0,03 (3 punti percentuali).

### 3.2 Parte (b): oltre il mercato (le quote solo qui)

Per ogni stagione di giudizio e lato, OLS di `y` (statistica realizzata) su `[1, m_modello, dominio_mercato, totale_mercato]` dove, dalle quote Bet365 **di chiusura** presenti nello storico:

- probabilita' implicite 1X2 normalizzate per togliere il margine: `p_i = (1/q_i) / Σ_j (1/q_j)`;
- `dominio_mercato = p_casa − p_ospite`, con segno positivo per il lato casa e negativo per il lato ospite; per il totale si usa `p_casa − p_ospite` cosi' com'e';
- `totale_mercato = (1/q_over2.5) / (1/q_over2.5 + 1/q_under2.5)`.

Partite senza quote di chiusura complete escluse dalla parte (b). Statistica t con errori standard OLS classici. Si riportano R² con e senza `m_modello` (regressione ridotta su `[1, dominio_mercato, totale_mercato]`).

**Criterio (b):** per ogni lato, il coefficiente di `m_modello` e' > 0 con t ≥ 2 in **ogni** stagione di giudizio; il segno non cambia mai.

### 3.3 Verdetto

Per statistica: **superato** solo se (a) e (b) sono soddisfatti su tutti e tre i lati e la calibrazione rientra nei 3 punti; altrimenti **non superato**. Chi non supera resta "Solo descrittivo" nella selezione (`exam = "non_superato"`). Non si riformulano i criteri dopo i risultati; non si scelgono sottoinsiemi di lati o stagioni a posteriori.

## 4. Cosa produce il codice

- `engine_stats/config.py`: `ADOPTED_CONFIG` con griglia, default, soglie, valori a priori.
- `engine_stats/engine.py`: `predict_history(history, config)` e `predict_targets(history_matches, targets, config)` con il payload `stats` di `docs/v4/API.md`; `exam` letto da `docs/v4/esami/E2.json` se esiste, altrimenti `in_attesa`.
- `exams/e2.py`: eseguibile con `python -m app.services.cecchino_v4.exams.e2`; scrive `docs/v4/esami/E2.json` e `E2.md`.
- Cache degli intermedi in `backend/.runtime/v4/engine_stats/` (fuori dal controllo di versione).
