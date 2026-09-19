# Roadmap Cecchino V4

Versione 2, 19 settembre 2026. Recepisce le sei decisioni e aggiunge la parte visiva. Nessuna riga di codice ancora scritta.

## 1. Obiettivo e perimetro

**Obiettivo.** Un modulo nuovo, affiancato a V2, V2.5 e V3, che analizza tutte le partite dei 16 campionati principali dalla prima giornata, predice i mercati classici (1X2, doppia chance, over/under, primo tempo, handicap asiatico) e i mercati speciali (tiri, tiri in porta, corner, cartellini, per squadra e totali), mostra per ogni partita il ragionamento completo, e segnala le giocate che superano la regola del profitto. Chi guarda vede tutto; il sistema consiglia poco.

**Esempio del risultato atteso.** Scheda "Milan - Inter, Inter over 6,5 tiri in porta, probabilità 61% (intervallo 55-66), quota Bet365 1,85, profitto atteso +13%, perché: Inter quarta per tiri in porta fuori casa, Milan concede sopra la media, formazione confermata".

**I 16 campionati.** Premier League, Championship, League One, League Two, Serie A, Serie B, La Liga, La Liga 2, Bundesliga, Bundesliga 2, Ligue 1, Ligue 2, Eredivisie, Jupiler Pro League, Primeira Liga, Süper Lig. Dove Bet365 non quota un mercato in una divisione, la scheda lo dice e il mercato resta descrittivo.

**Fuori perimetro.** Campionati extra-europei e divisioni oscure, mercati giocatore singolo, puntate automatiche.

## 2. Decisioni prese

| Tema | Decisione |
|---|---|
| Ramo | `feature/cecchino-v4` da `cleanup/sot-removal`, il ramo in produzione. `main` e la versione attuale non vengono toccati |
| Secondo bookmaker | Betfair, accanto a Bet365 |
| Regola del profitto | Margine minimo 3%, massimo 50 giocate al giorno, una per partita. Le prime 15 evidenziate come "Top" |
| Quote storiche mercati speciali | Nessun acquisto esterno. Il registro parte da quando lo accendiamo |
| Budget API | Nessuna ripartizione tra moduli. Un solo contatore giornaliero e un arresto di sicurezza della V4 a 7.000 chiamate totali, per non lasciare mai Cecchino Today senza quota |
| Visibilità | Ogni partita dei 16 campionati è visibile con il ragionamento completo, anche quando la V4 non consiglia nulla. La shortlist è un filtro e un'etichetta, non un cancello |

## 3. Regole non negoziabili

1. **Isolamento totale.** Cartelle, tabelle, rotte e pagina proprie. Nessuna modifica a scansione, gate, modelli o pagine esistenti. Migrazioni solo additive.
2. **Quote del book: mai nella probabilità, mai negli indici.** Entrano solo nello strato di selezione come prezzo e nello strato di misura come metro.
3. **Stagione 2025/26.** Le partite già giocate entrano nel walk-forward live come input. Nessun parametro, esame o soglia viene stimato su 2025/26. Il giudizio della V4 sulla stagione in corso è solo prospettico.
4. **Esami scritti prima dei risultati.** File di pre-registrazione nel ramo prima di ogni calcolo. Un esame fallito non si adotta, nemmeno come descrizione con soglie.
5. **Nessun minimo di partite giocate.** La V4 predice dalla prima giornata con la forza ereditata dalle stagioni precedenti. L'incertezza cresce con poche partite e lo strato di selezione la usa per astenersi.
6. **Budget API-Football.** Contatore per job, registrazione nella tabella eventi d'uso esistente, arresto a 7.000.
7. **Interfaccia.** Base 16 px, nessun testo a 10-12 px. Quote con la virgola. Spiegazioni in parole prima dei numeri.

## 4. Architettura in quattro strati

| Strato | Cosa fa | Quote del book |
|---|---|---|
| 1. Dati | Storico football-data (5 stagioni, già in database) più pipeline live API-Football per i 16 campionati: fixture, statistiche, eventi, formazioni, infortuni, classifiche, registro quote Bet365 e Betfair | Registrate, non usate |
| 2. Probabilità | Motore gol (Dixon-Coles con decadimento, piramidi nazionali, walk-forward, ereditato dalla V3) più motore statistiche (tiri, tiri in porta, corner, cartellini per squadra) con incertezza e calibrazione per mercato | Nessuna |
| 3. Selezione | Probabilità prudente per quota maggiore o uguale a 1,03; ordinamento per profitto atteso; una giocata per partita; massimo 50; astensione motivata | Solo come prezzo |
| 4. Misura | CLV, ROI con intervalli bootstrap a blocchi per giornata, CUSUM per campionato e mercato, post-mortem, arena degli sfidanti | Solo come metro |

### Mappa nel codice

- Backend: `backend/app/services/cecchino_v4/` con `data`, `engine_goals`, `engine_stats`, `selection`, `explain`, `measure`, `live`; job `backend/app/jobs/cecchino_v4_*.py`; rotte `backend/app/routes/cecchino_v4.py` con `/api/cecchino/v4` in lettura e `/api/admin/cecchino/v4` sotto sessione admin.
- Tabelle `cecchino_v4_*`: fixture, team_map, match_stats, lineups, player_minutes, injuries, standings, odds_snapshot, run, prediction_goals, prediction_stats, explanation, shortlist, shortlist_item, settlement, exam, challenger.
- Frontend: pagina `/cecchino-v4`, componenti `frontend/src/components/cecchino-v4/`, client `frontend/src/lib/cecchinoV4Api.ts`, voce di menu "Cecchino V4" nella sezione Cecchino, subito dopo Cecchino Today.
- Flag `CECCHINO_V4_ENABLED`, acceso in staging dalla Fase 0, in produzione dalla Fase 4.
- Documenti: `docs/v4/ROADMAP.md`, `docs/v4/REGOLE.md`, `docs/v4/PREREGISTRAZIONE_FASE_N.md`; voci V4 nella Roadmap in-app e capitolo V4 nella Guida ai modelli.

### Cosa si riusa, con certezza

- Motore V3: caricamento dati, stima forza Dixon-Coles con decadimento, generatore dei 17 mercati dalla matrice dei punteggi, scelta iperparametri sulla stagione precedente, piramidi nazionali. Importato come libreria, non modificato.
- Logistica walk-forward del valutatore V3, riattivata come strumento di misura.
- Audit anti-leakage della RUN V2, adattato alle tabelle V4.
- Client API-Football con controllo del ritmo, gestione 429 e quota esaurita; tabella eventi d'uso API.
- Sessione admin per le rotte di azione.
- Schema job con riga in tabella, heartbeat e advisory lock; job formazioni pre-partita come modello.
- Interfaccia: selettore giorni (`CecchinoDayTimeline`), filtri e lista partite di Cecchino Today, drawer mobile e pannello laterale desktop (`CecchinoTodayFixtureDrawer`, `CecchinoOverlayPortal`), anello punteggio (`PurchasabilityScoreRing`) riproposto come anello del profitto atteso, stili di sezione di Today, `Card`, `LabEChartsCore` per i grafici, switch tra viste del Bet Builder, `PageShell` per le viste tecniche con dimensioni portate a 16 px, formattazione orari su Europe/Rome.

### Cosa non si riusa

Ricerca pattern V2 e V3, Master Pattern, indici di acquistabilità, rating KPI con edge, gate di ammissibilità di Cecchino Today, calibrazione V3 Fase 7.

## 5. La parte visiva: come immaginare la tab

Una sola pagina, "Cecchino V4", con quattro viste selezionabili in alto, come oggi nel Bet Builder. Layout identico a Cecchino Today: giorni in alto, filtri, lista partite, dettaglio a destra sul desktop e in drawer sul telefono. Chi conosce Today si orienta subito.

### Vista 1: Partite (predefinita)

- **Selettore giorni** a 7 giorni. Filtri: campionato, famiglia di mercato, "solo con giocata", "solo formazioni note", ordinamento per orario o per profitto atteso.
- **Scheda partita** in lista, compatta ma leggibile a 16 px: squadre, orario, campionato; segno più probabile con percentuale; gol attesi; **giocata migliore** se esiste, con mercato, probabilità, quota e profitto atteso in verde; altrimenti "Nessuna giocata" con il motivo in una riga: prezzo giusto, incertezza alta, formazioni non note, mercato non quotato. Una barra sottile dell'incertezza. Stato formazioni con un punto colorato.
- Clic sulla scheda: si apre il **Ragionamento**.

### Il Ragionamento: il cuore della V4

Il dettaglio non è un pannello di numeri, è una catena di sei blocchi che si legge dall'alto in basso, ognuno apribile, ognuno con una frase in parole prima dei dati. È la risposta a "che ragionamento stai facendo".

1. **Chi sono.** Attacco e difesa delle due squadre con posizione nella divisione e freccia di tendenza; quanto il modello le conosce (partite equivalenti) e quindi quanto è incerto; vantaggio casa specifico della squadra; una riga su cosa è ereditato dalla stagione precedente. Esempio: "Inter: terzo attacco della Serie A, difesa sesta, conosciuta bene (34 partite equivalenti). Milan: attacco settimo in calo, difesa nona."
2. **Come giocano.** Per squadra: tiri, tiri in porta, corner, cartellini attesi fatti e subiti contro la media della divisione, con barre orizzontali. È qui che compare "Inter 6,8 tiri in porta attesi fuori casa, media divisione 4,9; Milan ne concede 5,1".
3. **Contesto.** Forma come scarto tra fatto e atteso nelle ultime cinque; giorni di riposo con coppe; motivazione in punti da salvezza, promozione o playoff; formazioni: non note, probabili, ufficiali, con assenze e impatto stimato; arbitro. I blocchi non ancora attivi non compaiono, niente segnaposto vuoti.
4. **Cosa prevede.** Una piccola mappa dei punteggi probabili e una **tabella dei mercati**: Mercato, Probabilità, Intervallo, Quota Bet365, Quota Betfair, Profitto atteso, Verdetto. I mercati speciali sono raggruppati per statistica con un selettore di linea: scegli "tiri in porta Inter" e scorri over 5,5, 6,5, 7,5 vedendo la probabilità cambiare. Il verdetto è una parola: Giocabile, Prezzo giusto, Incertezza alta, Non quotato, Solo descrittivo (statistica che non ha superato l'esame). Ordinabile per profitto atteso.
5. **Perché sì, perché no.** Per la giocata migliore, quattro o cinque frasi generate da regole fisse, non da un modello di linguaggio, che collegano i blocchi precedenti: "Inter tira in porta 6,8 volte fuori casa contro una media di 4,9; il Milan ne concede 5,1. La linea 6,5 a 1,85 vale il 54%; il modello dice 61% con intervallo 55-66. Il margine è +13%, sopra il 3% richiesto. Formazioni non ancora note: la giocata è provvisoria e verrà confermata o ritirata alle 19:30." Sotto, "cosa la farebbe cambiare": assenza di un titolare chiave, quota sotto 1,68, formazioni con turnover.
6. **Come è andata.** Dopo la partita: previsto contro reale per gol e statistiche, esito della giocata, una riga su fortuna o merito rispetto ai gol attesi.

Sul telefono i sei blocchi sono una lista verticale con il primo e il quarto aperti; sul desktop sono nel pannello a destra con la tabella dei mercati sempre visibile.

### Vista 2: Shortlist

- La lista del giorno ordinata per profitto atteso, con le prime 15 in evidenza e le altre fino a 50 sotto. Ogni riga: partita, mercato, probabilità, quota, profitto, stato: **provvisoria** (formazioni non note), **confermata** (sigillata), **ritirata** (con motivo), **regolata** (vinta o persa).
- In alto l'impronta della shortlist sigillata con l'orario: è la prova che nulla è cambiato dopo il calcio d'inizio.
- Sezione **Astensioni**: partite analizzate senza giocata, raggruppate per motivo. Serve a capire cosa il sistema ha scartato e perché.

### Vista 3: Misura

- Cruscotto CLV e ROI per campionato e per mercato, con intervalli, grafici `LabEChartsCore`.
- Allarmi CUSUM: campionati e mercati in decadimento, con la data di ritiro proposto.
- Post-mortem settimanale in parole: cosa ha funzionato, cosa no, quota di esiti sfortunati.

### Vista 4: Motore

- **Esami**: ogni esame con testo della pre-registrazione, esito superato o non superato, numeri a confronto. Niente si nasconde.
- **Arena**: gli sfidanti (assenze, motivazione, boosting…) con esito e data.
- **Dati**: matrice copertura mercati per divisione, qualità dati per campionato, stato del registro quote, contatore API del giorno.

### Regole grafiche

Shell chiara di Cecchino Today per Partite e Shortlist, che sono le viste da telefono nel giorno di gara. Colori con significato fisso: verde giocabile, ambra provvisoria, grigio astensione, azzurro solo descrittivo, rosso ritirata. Quote con la virgola, percentuali intere, intervalli sempre accanto alla probabilità. Titoli 20-24 px, testo 16 px, etichette 16 px in maiuscoletto pesante invece che piccole.

## 6. Budget API-Football

Stime per 16 campionati, circa 170 partite a settimana.

| Job | Chiamate | Settimana |
|---|---|---|
| Fixture per data (tutti i campionati in una chiamata), 3 giorni | 3 al giorno | 21 |
| Statistiche post-partita | 1 per partita | 170 |
| Eventi | 1 per partita | 170 |
| Giocatori per partita (minuti) | 1 per partita | 170 |
| Formazioni ufficiali | 1-2 per partita | 250 |
| Infortuni | 1 per campionato al giorno | 112 |
| Classifiche | 1 per campionato a settimana | 16 |
| Registro quote per campionato e data, Bet365 e Betfair | 3 istantanee al giorno, circa 1,5 pagine, 2 book | 1.000 |
| Quota di chiusura per partita | 1 per partita | 170 |
| Partite di coppa delle squadre | 1 per squadra a settimana | 300 |
| **Totale regime** | | **circa 2.400, cioè 340 al giorno** |

Backfill una tantum per formazioni, eventi, giocatori e tiri dentro area: circa 24.000 chiamate a stagione. Con il resto della quota libera, due stagioni in circa una settimana. Le statistiche di base sono già nello storico: le Fasi 1 e 2 non aspettano il backfill.

Fatto certo: API-Football non fornisce quote storiche oltre il periodo corrente. Il registro quote dei mercati speciali parte dal giorno in cui lo accendiamo.

## 7. Fasi

Ogni fase indica obiettivo, esame, cosa compare nella tab, stima in settimane di lavoro.

### Fase 0. Fondamenta e vista Partite (settimana 1)

- Ramo, cartelle, flag, prime tabelle, rotte di lettura, pagina con vista Partite: schede dei 16 campionati a 7 giorni da API-Football, senza predizioni.
- Mappa squadre football-data ↔ API-Football con verifica dei casi ambigui.
- Contatore API e arresto a 7.000.
- **Matrice copertura mercati**: una chiamata quote per partita della settimana per Bet365 e Betfair, per sapere in quali divisioni esistono davvero linee su corner, cartellini, tiri e tiri in porta di squadra. Il catalogo del repo conosce le etichette; la copertura reale è da misurare.
- `docs/v4/REGOLE.md`.
- Nella tab: Partite con schede vuote di predizione; Motore con Dati.

### Fase 1. Motore gol (settimane 2-3)

- Involucro V4 sul motore V3. Novità, una alla volta: vantaggio casa per squadra con shrinkage; rho per divisione; binomiale negativa per divisione; incertezza a posteriori per squadra esposta come intervallo; calibrazione isotonica per mercato sulla stagione precedente; handicap asiatico.
- Esame E1 pre-registrato, stagioni 2022/23-2024/25: Brier e log-loss non peggiori della V3 Fase 4 in ogni famiglia; calibrazione non peggiore; l'incertezza deve predire l'errore in eccesso in ogni stagione.
- Nella tab: blocco 1 "Chi sono" e blocco 4 con i mercati classici e gli intervalli; Motore con Esami.

### Fase 2. Motore statistiche (settimane 3-5, in parallelo)

- Bersagli: tiri, tiri in porta, corner, cartellini, falli, per squadra e totali. Attacco e difesa per statistica, decadimento, piramidi, walk-forward; Poisson o binomiale negativa per statistica e divisione; probabilità per qualsiasi linea.
- Esame E2 pre-registrato, per statistica: (a) errore assoluto e CRPS migliori delle baseline ingenue in ogni stagione; (b) **test oltre il mercato**: regressione della statistica reale su attesa del modello più dominio implicito dalle quote gol di chiusura già nello storico; coefficiente del modello positivo e stabile ogni stagione. Chi fallisce (b) resta "Solo descrittivo".
- Nella tab: blocco 2 "Come giocano", mercati speciali nel blocco 4 con selettore di linea e verdetto "Solo descrittivo" o "Anteprima" finché la Fase 4 non è chiusa.

### Fase 3. Pipeline live e registro quote (settimane 3-5, in parallelo)

- Job giornalieri: fixture, statistiche, eventi, giocatori, infortuni, classifiche, coppe. Job formazioni a 60 e 30 minuti.
- **Registro quote** Bet365 e Betfair, tre istantanee al giorno più chiusura per partita, con orario. Da qui in avanti ogni quota mostrata nella tab viene dal registro.
- Backfill formazioni, eventi, giocatori per 2024/25 e 2025/26.
- Esame G3: due settimane con meno del 2% di partite senza statistiche nelle prime divisioni e registro completo.
- Nella tab: colonne quota nel blocco 4; stato formazioni nelle schede; Motore con Dati completo.

### Fase 4. Selezione, Shortlist, Perché (settimane 6-7)

- Regola del profitto con probabilità prudente, margine 3%, una per partita, massimo 50. Shortlist sigillata con impronta; stati provvisoria, confermata, ritirata, regolata. Regolamento automatico.
- Generatore del "Perché sì, perché no" da regole fisse sui blocchi 1-3.
- Esame E4 pre-registrato sui mercati classici con quote storiche: ROI con intervallo bootstrap a blocchi; conteggio vincenti contro la distribuzione nulla per permutazione degli esiti per giornata. Per i mercati speciali il giudizio è solo prospettico.
- Nella tab: vista Shortlist con Astensioni; blocco 5 in ogni partita; verdetti nel blocco 4; flag acceso in produzione.

### Fase 5. Giocatori e contesto come sfidanti (settimane 8-11)

- Indice di assenza da plus-minus regolarizzato sui minuti dei giocatori; ricalcolo della shortlist alle formazioni ufficiali con ritiro automatico. Motivazione da classifica walk-forward. Riposo con coppe, cambio allenatore, arbitro. Gol attesi approssimati da tiri dentro e fuori area. Sfidante a gradient boosting sui residui.
- Ogni voce con esame E5.x pre-registrato contro il campione. Chi non passa non entra.
- Nella tab: blocco 3 "Contesto" completo; Motore con Arena.

### Fase 6. Paper trading prospettico (8-12 settimane di calendario dalla fine della Fase 4)

- Shortlist pubblicata e sigillata ogni giorno, regolata ogni sera. Cruscotto CLV, ROI, CUSUM, post-mortem.
- Esame G6 pre-registrato per gruppo di mercati: CLV medio positivo con intervallo che esclude lo zero e numero minimo di giocate. Decisione per gruppo: live, continua, ritira.
- Nella tab: vista Misura; blocco 6 "Come è andata".

### Fase 7. Live e consolidamento (dopo G6)

- Notifiche shortlist e formazioni; registro puntate personali con slittamento; bankroll flat e allarmi; ritiro automatico. Guida ai modelli e Roadmap in-app aggiornate.

## 8. Cosa vedrai e quando

| Momento | Nella tab Cecchino V4 |
|---|---|
| Fine settimana 1 | Partite dei 16 campionati a 7 giorni, matrice copertura mercati, contatore API |
| Fine settimana 3 | Per ogni partita: chi sono, mercati classici con probabilità e intervalli; pagina Esami |
| Fine settimana 5 | Come giocano; mercati speciali con selettore di linea e quote Bet365 e Betfair accanto; verdetto "Anteprima" |
| Fine settimana 7 | Shortlist sigillata, verdetti, Perché sì e perché no, Astensioni |
| Settimane 8-11 | Contesto: formazioni, assenze, motivazione; Arena |
| Da settimana 8 a 18 | Misura: CLV e ROI prospettici; Come è andata; verdetto per mercato |

Sulla scadenza: il blocco "Inter over 6,5 tiri in porta a 1,85" con verdetto Giocabile non è realistico nel prossimo fine settimana. La partita con il ragionamento e le probabilità dei mercati classici la vedi dal terzo fine settimana; i mercati speciali con quota accanto dal quinto, etichettati Anteprima; la shortlist dal settimo. Il verdetto sulla redditività dei mercati speciali arriva almeno tre mesi dopo l'accensione del registro quote.

## 9. Rischi

- **Copertura dei mercati speciali su API-Football.** Etichette note, copertura per divisione ignota. La Fase 0 la misura. Se una linea manca, il blocco 4 mostra la probabilità e un campo per inserire la quota a mano.
- **L'83% si ridurrà contro le linee.** Il test oltre il mercato della Fase 2 lo dirà presto.
- **Limitazione del conto** su mercati secondari da parte di Bet365. Non riguarda il modello.
- **Tempo.** Circa quattro mesi fino al verdetto. Saltare gli esami ripete gli errori di V2 e V2.5.
- **Budget API.** Regime a un ventesimo del limite; l'unico rischio è il backfill, che ha l'arresto a 7.000.
