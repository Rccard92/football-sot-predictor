# Pre-registrazione Fase 4: regola della selezione ed esame E4

Scritta il 20 settembre 2026, prima di qualunque calcolo dell'esame. Codice: `backend/app/services/cecchino_v4/selection/`, `measure/`, `explain/`. Vale la regola 4 di `docs/v4/REGOLE.md`: questo file non si modifica dopo il calcolo; se la regola cambia, si scrive una nuova pre-registrazione (Fase 4b) e si ricalcola da zero.

## 1. La regola della selezione, esattamente come implementata

Le quote entrano solo qui, come prezzo. Mai in `p`, `lo`, `hi`, nei gol attesi o nell'incertezza.

### 1.1 Ingredienti per ogni mercato

- `p`: probabilità calibrata del motore (gol o statistiche).
- `lo`, `hi`: intervallo al 90% dall'incertezza a posteriori.
- `u`: `uncertainty.score` del payload gol (per le statistiche, l'incertezza della statistica se presente, altrimenti quella dei gol), tagliato in [0, 1].
- `tasso_base`: probabilità "di richiamo" del mercato, senza modello:
  - mercati classici, tabella fissa (`rules.BASE_RATES`, frequenze storiche arrotondate dei 16 campionati): 1 0,44 · X 0,26 · 2 0,30 · 1X 0,70 · X2 0,56 · 12 0,74 · Over 0,5 0,93 · Under 0,5 0,07 · Over 1,5 0,75 · Under 1,5 0,25 · Over 2,5 0,51 · Under 2,5 0,49 · Over 3,5 0,29 · Under 3,5 0,71 · 1 primo tempo 0,31 · X primo tempo 0,42 · 2 primo tempo 0,27;
  - handicap asiatico: probabilità efficace `w / (w + l)` della linea nella partita media della divisione (Dixon-Coles con gol attesi 1,45 casa e 1,15 ospite, rho −0,05), dove `w = P(vinta) + P(mezza vinta)/2` e `l = P(persa) + P(mezza persa)/2`;
  - statistiche: `P(X > linea)` con `X ~ Poisson(media di divisione)` fornita nel payload della statistica (`division_mean`), e `1 − P` per l'under.
- Prezzo: `quota_usata` = quota Bet365 se presente, altrimenti Betfair (`bookmaker_used` lo registra). L'utente gioca su Bet365.

### 1.2 Probabilità prudente

```
u = min(1, max(0, uncertainty.score))
se lo > tasso_base:  p_prudente = lo − (lo − tasso_base) × u
altrimenti:          p_prudente = lo
```

Si parte dal bordo inferiore dell'intervallo, mai da `p`; se il bordo sta sopra il tasso base, lo si restringe verso il tasso base in proporzione all'incertezza; se sta sotto, si lascia dov'è (mai gonfiare). `p_prudente` non supera mai `p`. Senza intervallo, `lo = p`.

### 1.3 Profitto atteso e verdetto

```
profitto_atteso = p_prudente × quota_usata − 1
```

Verdetti, nell'ordine in cui vengono controllati (`rules.evaluate_market`):

1. `solo_descrittivo`: statistica il cui esame E2 non è `superato`.
2. `non_quotato`: nessuna quota Bet365 né Betfair.
3. `incertezza_alta`: `uncertainty.level == "alta"`.
4. `giocabile`: `profitto_atteso ≥ 0,03` (`PROFIT_MARGIN`) **e** `quota_usata ≥ 1,20` (`MIN_QUOTA`).
5. `prezzo_giusto`: tutto il resto.

Le formazioni non note **non** bloccano il verdetto: la riga porta `provisional = true` e la voce in shortlist nasce `provvisoria`; alle formazioni ufficiali viene confermata o ritirata con motivo.

### 1.4 Shortlist del giorno (`shortlist.build_shortlist`)

- Candidate: solo righe `giocabile`.
- Una giocata per partita (`PLAYS_PER_MATCH = 1`): quella con profitto atteso più alto; a parità, probabilità prudente più alta.
- Ordinamento per profitto atteso decrescente; taglio a 50 (`MAX_PLAYS_PER_DAY`); le prime 15 marcate `top` (`TOP_PLAYS`).
- Sigillo: `sha256` del JSON canonico (chiavi ordinate) di `{fixture_id, market_key, quota, p, p_prudent}` per ogni voce, più l'orario del sigillo. Dopo il sigillo la lista non si sostituisce.
- Regolamento (`settlement.settle`): esiti `vinta | persa | void | mezza_vinta | mezza_persa`; profitto in unità a puntata piatta 1: `q − 1`, `−1`, `0`, `(q − 1)/2`, `−0,5`. Cartellini pesati giallo 1, rosso 2. Statistica assente → esito `None`, la voce resta non regolata.
- Astensioni: per ogni partita senza giocata, il motivo è il verdetto bloccante più frequente tra i primi 5 mercati per `p × quota` (tra quelli con prezzo, se ne esiste almeno uno; altrimenti `non_quotato`).

## 2. Esame E4: i mercati classici sulle stagioni di giudizio

### 2.1 Dati e procedura

- Stagioni: 2022/23, 2023/24, 2024/25 (`JUDGE_SEASONS`), 16 campionati. 2021/22 è solo rodaggio. 2025/26 non si tocca.
- Previsioni: payload `goals` del motore V4 in walk-forward (Fase 1, esame E1 superato), con la calibrazione della stagione precedente.
- Prezzi: quote di chiusura Bet365 del CSV football-data (`B365CH`, `B365CD`, `B365CA`, `B365C>2.5`, `B365C<2.5`, e le colonne handicap asiatico `AHCh`, `B365CAHH`, `B365CAHA` dove presenti). Doppia chance e primo tempo non hanno quota storica: restano fuori da E4 e non entrano nel conteggio delle giocate.
- Selezione: la regola del paragrafo 1 applicata giornata per giornata, con `lineups_status = "ufficiali"` (nel dataset storico non esiste lo stato provvisorio) e `u` dal payload.
- Blocco = giornata di campionato (`round` del CSV, o la data quando manca).

### 2.2 Criteri, tutti da superare

| Codice | Criterio | Soglia |
|---|---|---|
| E4.1 | ROI delle giocate selezionate sulle tre stagioni insieme, puntata piatta 1, con intervallo bootstrap a blocchi al 90% (blocchi = giornate, 2.000 ricampionamenti, seme 20260920) | bordo inferiore dell'intervallo > 0 |
| E4.2 | Numero di giocate selezionate nelle tre stagioni | ≥ 300 |
| E4.3 | Nullo di procedura: per 200 volte si permutano gli esiti (risultato finale) tra le partite della stessa giornata, si riapplica **tutta** la selezione (stessa regola, stesse quote, stesse probabilità) e si calcola il profitto; il profitto osservato deve superare il 95° percentile della distribuzione nulla | profitto osservato > 95° percentile |
| E4.4 | Concentrazione: quota del profitto totale portata dal singolo campionato che contribuisce di più (sui campionati con profitto positivo) | ≤ 40% |

Si riportano inoltre, senza soglia: ROI per stagione, ROI per famiglia (1X2, over/under, handicap), numero di giocate per campionato, CLV non disponibile (le quote storiche sono già di chiusura).

### 2.3 Cosa succede se E4 fallisce

La shortlist **esiste comunque**: l'utente vuole vedere tutto, e la V4 mostra tutto. Cambia solo l'etichetta:

- ogni riga di mercato e ogni voce di shortlist delle famiglie classiche porta `advised = false`;
- la vista Shortlist mostra il banner **"Esame E4 non superato: giocate classiche in osservazione, non consigliate"** (`shortlist.E4_FAILED_BANNER`);
- il blocco 5 aggiunge la frase "Famiglia di mercato in osservazione: l'esame E4 non è superato, la giocata è mostrata ma non consigliata";
- nulla cambia nel calcolo: niente soglie nuove, niente filtri nuovi. Un esame fallito non si adotta nemmeno come descrizione con soglie (regola 4).

Se E4 fallisce per il solo criterio E4.2 (poche giocate) ma E4.1, E4.3 ed E4.4 sono superati, il verdetto è comunque "non superato": non si abbassa il margine per far salire il conteggio.

### 2.5 Precisazioni scritte prima del calcolo di E4 (20/09/2026)

- L'esame E1 **non** e' stato superato: nessuna novita' V4 e' stata adottata. Il payload `goals` usato in E4 e' quindi la configurazione adottata da E1 (`engine_goals.config.ADOPTED_CONFIG`): V3 Fase 4 come libreria piu' handicap asiatico e ratings descrittivi. Senza intervalli, `lo = p` e la probabilita' prudente si riduce a `p − (p − tasso base) × u`, con `u` il punteggio di incertezza del payload.
- I CSV football-data non hanno il campo `round`: il blocco per il bootstrap e per il nullo di E4.3 e' la coppia (campionato, data). La permutazione degli esiti avviene tra le partite dello stesso campionato nella stessa data (risultato finale, primo tempo e statistiche insieme); un gruppo con una sola partita resta invariato.
- La shortlist storica e' costruita per data di calendario su tutti i campionati insieme, come nel live (una giocata per partita, massimo 50 al giorno).
- Le quote di chiusura dell'handicap asiatico si abbinano alla linea di chiusura `AHCh` con le chiavi `AH_HOME:<linea>` e `AH_AWAY:<−linea>`; se il motore non produce quella linea, il mercato resta non quotato.
- Seme dei ricampionamenti e delle permutazioni: 20260920.

### 2.4 Mercati speciali

Per le statistiche (tiri, tiri in porta, corner, cartellini, falli) non esistono quote storiche: il giudizio è **solo prospettico**, con l'esame G6 della Fase 6 (CLV medio positivo con intervallo che esclude lo zero e numero minimo di giocate per gruppo). Fino ad allora, le righe statistiche con esame E2 superato sono `giocabile` quando la regola lo dice, ma il banner della Shortlist ricorda che il giudizio sulla redditività arriva dopo il paper trading.

## 3. Cosa è fissato da questo file

`PROFIT_MARGIN = 0,03`, `MIN_QUOTA = 1,20`, `MAX_PLAYS_PER_DAY = 50`, `TOP_PLAYS = 15`, `PLAYS_PER_MATCH = 1`, la tabella dei tassi base, la partita media per l'handicap (1,45 / 1,15 / −0,05), la formula della probabilità prudente, Bet365 prima di Betfair, i parametri del bootstrap (90%, 2.000, seme 20260920), le 200 permutazioni e il 95° percentile, la soglia 300 e il 40%. Nessuno di questi numeri è stato scelto guardando un risultato su 2022/23–2024/25.
