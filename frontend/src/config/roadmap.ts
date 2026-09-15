/** Roadmap di sviluppo Cecchino V2 · V2.5 · V3. Aggiornata a ogni deploy. */

export type RoadmapStatus = 'da_fare' | 'in_corso' | 'fatto'

export type RoadmapTask = {
  text: string
  status: RoadmapStatus
}

export type RoadmapStep = {
  id: number
  title: string
  goal: string
  status: RoadmapStatus
  dependsOn: number[]
  tasks: RoadmapTask[]
  doneWhen: string
}

export type RoadmapUpdate = {
  date: string
  text: string
}

export const ROADMAP_RULES: string[] = [
  "Si lavora solo su staging; la produzione si fa una sola volta, alla fine, quando tutto e' finito e verificato.",
  "La stagione 2025/26 e' gia' stata usata: da ora l'unico banco di prova pulito e' la live (2026/27 in avanti).",
  "Pattern vincente = profitto (o scostamento confermato, per i mercati senza quota) in tutte e 4 le stagioni 2022/23-2025/26, con almeno 20 partite per stagione.",
  "Ogni motore e ogni pattern hanno una versione congelata: una modifica crea una versione nuova.",
  "Nessun passo irreversibile senza conferma esplicita dell'utente.",
]

export const ROADMAP_STEPS: RoadmapStep[] = [
  {
    id: 1,
    title: 'Master Pattern (V2 e V3)',
    goal: 'Una pagina unica per consultare i pattern vincenti 4/4 di ogni modello, con tutti i dettagli fino alle singole partite.',
    status: 'fatto',
    dependsOn: [],
    tasks: [
      { text: 'Salvare il risultato di ogni pattern V3 sul 2025/26 (per la V2 i dati ci sono gia)', status: 'fatto' },
      { text: 'Ricerca pattern V3 sui mercati senza quota (tiri, corner, cartellini) con lo stesso metodo della V2', status: 'fatto' },
      { text: 'Pagina con 3 riquadri (V2 · V2.5 · V3), filtri e tabella dei pattern 4/4', status: 'fatto' },
      { text: 'Mercati con quota (profitto, ROI, quota media) e senza quota (frequenza e scostamento dalla media)', status: 'fatto' },
      { text: 'Confronto con quanti pattern vincenti darebbe il caso', status: 'fatto' },
      { text: 'Dettaglio al clic: stagione per stagione ed elenco partite', status: 'fatto' },
      { text: 'Ogni pattern salvato con la versione del motore che lo ha generato', status: 'fatto' },
    ],
    doneWhen: 'Scegli il modello, vedi i pattern 4/4 e arrivi con un clic alle singole partite.',
  },
  {
    id: 2,
    title: 'Pulizia delle pagine di test',
    goal: "Togliere dal menu e dal codice (frontend e backend) pagine e funzioni che non servono piu', lasciando un tool ordinato.",
    status: 'in_corso',
    dependsOn: [1],
    tasks: [
      { text: "Elenco delle pagine da tenere confermato dall'utente", status: 'fatto' },
      { text: 'Rimossi Pattern Insights e le 4 pagine V3 di test: pagine, API e servizi dedicati (i dati restano nel database)', status: 'fatto' },
      { text: "Analisi del resto del codice non piu' usato, elenco confermato dall'utente", status: 'fatto' },
      { text: "Pagina Cecchino (analisi singola) tolta: /cecchino porta a Cecchino Today, motore e dati intatti", status: 'fatto' },
      { text: 'Rimosse le parti sicure: file frontend mai usati, 15 gruppi di API senza chiamanti, moduli orfani, test e script una tantum, file spazzatura', status: 'fatto' },
      { text: 'Tolti il pannello debug SportAPI rotto della pagina Admin e la rotta classifiche doppia', status: 'fatto' },
      { text: "Parti 'da verificare' decise con l'utente: tolte le API di ricerca Goal Intensity v5, le dashboard della vecchia Historical Scan V4 e gli export Acquistabilità V3.5 (restano anteprima GI v5, export V3.1/V3.6 e tutti i dati)", status: 'fatto' },
      { text: 'Backfill SportAPI tenuto: si decide insieme alla scelta della nuova fonte per formazioni e infortuni', status: 'da_fare' },
      { text: 'Vecchio motore SOT staccato dalla scansione di Cecchino Today (salvataggio squadre/partite spostato in un modulo Cecchino identico); codice e dati SOT lasciati intatti', status: 'fatto' },
    ],
    doneWhen: 'Nel menu e nel codice restano solo le pagine scelte e cio che serve a loro e ai motori.',
  },
  {
    id: 3,
    title: 'Verifica dei dati live',
    goal: 'Sapere, campionato per campionato, quali dati delle partite gia giocate abbiamo in live e quindi quali motori possono girare.',
    status: 'fatto',
    dependsOn: [],
    tasks: [
      { text: 'Cosa fornisce oggi la fonte di Cecchino Today: gol, tiri, tiri in porta, corner, cartellini', status: 'fatto' },
      { text: 'Allineamento nomi squadra e calendario con lo storico', status: 'fatto' },
      { text: 'Tabella campionato → dati disponibili → motori che possono girare', status: 'fatto' },
    ],
    doneWhen: 'Tabella di copertura approvata: sappiamo dove V2, V2.5 e V3 possono lavorare in live.',
  },
  {
    id: 4,
    title: 'Cecchino V2.5',
    goal: 'Stessa struttura e stessi calcoli della V2, con gli errori corretti (la V2 resta congelata).',
    status: 'fatto',
    dependsOn: [3],
    tasks: [
      { text: 'Analisi dei moduli V2: cosa dovrebbero fare, cosa fanno, dove sbagliano (con i numeri dello storico)', status: 'fatto' },
      { text: "Progetto dei moduli corretti, approvato dall'utente prima del codice", status: 'fatto' },
      { text: 'Moduli V2.5 scritti e testati: picchetti, gol, KPI, Equilibrio, Intensita Goal, Acquistabilita, segnali', status: 'fatto' },
      { text: 'Taratura una tantum sul solo 2021/22 (costanti e scale congelate, nessun risultato nelle scale)', status: 'fatto' },
      { text: 'RUN V2.5 sulle 5 stagioni (una sola volta, alla fine)', status: 'fatto' },
      { text: 'Ricerca pattern V2.5 (scoperta 2021/22, verifiche 2022/23-2025/26) e inserimento nella Master Pattern', status: 'fatto' },
    ],
    doneWhen: 'La V2.5 ha previsioni storiche, pattern 4/4 in pagina e confronto di precisione con V2 e V3.',
  },
  {
    id: 5,
    title: 'Motori in live e registro previsioni',
    goal: 'V2, V2.5 e V3 analizzano le partite del giorno; ogni previsione e salvata prima del calcio di inizio.',
    status: 'in_corso',
    dependsOn: [3, 4],
    tasks: [
      { text: 'Calcolo V2.5 dopo ogni scansione di Cecchino Today (storico della competizione, quote del pannello KPI)', status: 'fatto' },
      { text: 'Registro previsioni V2 e V2.5: congelate prima del calcio di inizio, esiti a partita finita, riepilogo precisione e rendimento', status: 'fatto' },
      { text: "V3 estesa (decisione utente): modello V3 del Lab con parametri congelati, su tutti i campionati dove API-Football dà tiri e tiri in porta", status: 'fatto' },
      { text: 'V3 estesa · dati: partite e statistiche squadra da API-Football (stagione in corso e precedente), squadre riconosciute per id, nessun abbinamento nomi', status: 'fatto' },
      { text: 'V3 estesa · prova di identità: sulle partite del Lab il nuovo calcolo rifà la run finale #11 (1.372 partite, differenza massima 0,000005)', status: 'fatto' },
      { text: 'V3 estesa · registro previsioni, anteprima, esiti a fine partita, Osservazione live con confronto a tre motori', status: 'fatto' },
      { text: 'V3 estesa · scheda in Cecchino Today con la grafica di V2 e V2.5 (Pannello KPI, Specialisti, Indici)', status: 'fatto' },
      { text: 'V3 estesa · Pattern Master V3 accesi in live con le soglie salvate della ricerca Lab (la condizione "livello" non è verificabile fuori dai 16 campionati del Lab)', status: 'fatto' },
    ],
    doneWhen: 'Ogni partita del giorno ha tre previsioni salvate e, a fine partita, i loro esiti.',
  },
  {
    id: 6,
    title: 'Cecchino Today e Bet Builder',
    goal: "Vedere le tre analisi separate su ogni partita e i pattern Master che si accendono.",
    status: 'in_corso',
    dependsOn: [1, 5],
    tasks: [
      { text: 'Dettaglio analisi con 3 schede: V2, V2.5 (dal registro o anteprima), V3 in attesa del collegamento API', status: 'fatto' },
      { text: 'Pattern Master V2.5 accesi su ogni partita, registrati prima del calcio di inizio (solo se tutte le condizioni sono verificabili)', status: 'fatto' },
      { text: 'Pattern Master V2 accesi in live (Cecchino Today e Bet Builder): moduli V2 ricalcolati con le stesse funzioni della RUN V2, quote reali Bet365, percentili Intensità Goal dell\'ultima RUN V2', status: 'fatto' },
      { text: "Statistiche squadra (tiri, corner, cartellini) per tutte le competizioni: oggi presenti solo per poche partite, la maggior parte dei pattern resta non verificabile", status: 'da_fare' },
      { text: 'Bet Builder: sezione pattern accesi in osservazione con esito a fine partita (non giocate automatiche)', status: 'fatto' },
      { text: 'Scansione notturna: i rifiuti per troppe richieste (429) non escludono piu partite, quote del giorno lette a pagine, secondo passaggio di recupero', status: 'fatto' },
      { text: 'Scansione automatica spostata alle 06:00 sulla giornata in corso (staging con recupero alle 06:45, produzione alle 06:00); scansione delle 23:00 spenta', status: 'fatto' },
      { text: 'Scheda V2.5 con la stessa grafica della V2: Acquistabilità, Pannello KPI, pilastri Equilibrio, Intensità Goal e pattern con guida alla lettura', status: 'fatto' },
      { text: 'Predizione in cima alle schede: pattern con quota, controllo dei moduli senza quote del book, pattern che usano la quota come condizione mostrati a parte', status: 'fatto' },
      { text: 'Nuovo Indice di Acquistabilità V2.5 e V3 come orchestratore: legge tutti i moduli, stima quanto la giocata può vincere e solo alla fine guarda la quota per decidere se e quanto investire (progetto da approvare)', status: 'in_corso' },
    ],
    doneWhen: 'Su ogni partita vedi tre analisi e i segnali dei pattern, anche per i mercati senza quota.',
  },
  {
    id: 7,
    title: 'Osservazione in live',
    goal: 'Misurare nel tempo motori e pattern sulle partite reali.',
    status: 'in_corso',
    dependsOn: [5, 6],
    tasks: [
      { text: 'Pagina Osservazione live: precisione di ogni motore giorno per giorno sulle stesse partite, con Bet365 come metro di paragone', status: 'fatto' },
      { text: 'Rendimento dei pattern Master accesi in live, raggruppati per mercato (segnali, vinti, % live contro storico, ROI)', status: 'fatto' },
      { text: 'Pattern accesi raggruppati anche in Cecchino Today e Bet Builder (un segnale per mercato con i pattern concordi)', status: 'fatto' },
      { text: 'Verifica con alcune settimane di dati reali: i pattern confermano lo storico?', status: 'da_fare' },
    ],
    doneWhen: 'Una pagina mostra, giornata dopo giornata, chi conferma e chi no.',
  },
  {
    id: 8,
    title: 'Statistiche pre-match complete e formazioni',
    goal: 'Tutte le statistiche pre-partita per squadra e formazioni/infortuni.',
    status: 'da_fare',
    dependsOn: [5],
    tasks: [
      { text: 'Valutazione API: copertura, dati disponibili, costi (piano Pro 7.500 chiamate al giorno, blocchi da 20 partite)', status: 'fatto' },
      { text: 'Collegamento notturno: copertura campionati, stagione precedente, statistiche squadra e arbitro a blocchi, linee Bet365 a .5', status: 'fatto' },
      { text: "Possibile seconda lettura quote Bet365 qualche ora prima del calcio d'inizio (mercati tiri/corner/cartellini che escono tardi): da valutare dopo i primi dati", status: 'da_fare' },
      { text: 'Nuovo cron formazioni pre-match (staging, ogni 10 minuti): formazioni ufficiali e assenti da API-Football per tutte le partite eleggibili che iniziano entro 75 minuti', status: 'fatto' },
      { text: 'Mostrare formazioni e assenti nelle schede partita', status: 'da_fare' },
      { text: "Formazioni e infortuni da una fonte dedicata: API-Football copre male gli infortuni (assenti in quasi tutti i campionati minori). Valutare un'altra API", status: 'da_fare' },
      { text: 'Integrazione nelle schede e, se utile, nei motori (come nuova versione misurata in live)', status: 'da_fare' },
    ],
    doneWhen: 'Statistiche e formazioni disponibili nelle schede partita.',
  },
  {
    id: 10,
    title: 'Dashboard home',
    goal: 'Una home piu strutturata con le partite da analizzare e le statistiche dei risultati (per ora la home resta Cecchino Today).',
    status: 'da_fare',
    dependsOn: [7],
    tasks: [
      { text: "Definire con l'utente contenuti e metriche della dashboard", status: 'da_fare' },
      { text: 'Realizzazione della dashboard', status: 'da_fare' },
    ],
    doneWhen: 'Entrando nel tool si vedono partite del giorno e andamento dei risultati in un colpo solo.',
  },
  {
    id: 9,
    title: 'Messa in produzione',
    goal: 'Uscita unica del tool completo, dopo verifica su staging.',
    status: 'da_fare',
    dependsOn: [1, 2, 4, 5, 6, 7],
    tasks: [
      { text: 'Migrazioni database, dati storici necessari, calcoli giornalieri programmati', status: 'da_fare' },
      { text: 'Verifica completa su staging', status: 'da_fare' },
      { text: "Pubblicazione in produzione solo con conferma esplicita dell'utente", status: 'da_fare' },
    ],
    doneWhen: 'Il tool gira in produzione con i tre motori, Master Pattern e osservazione live.',
  },
]

export const ROADMAP_UPDATES: RoadmapUpdate[] = [
  {
    date: '2026-09-15',
    text: "Verifica quota del bookmaker: l'obiettivo è vincere, non battere il book. Tolto dal controllo dei moduli il calcolo sulla quota, pattern con condizioni sulla quota separati (14 su 24 V3, 2 su 87 V2.5), Indice di Acquistabilità V2.5 segnato in rifacimento e V3 in costruzione come orchestratore dei moduli, Guida ai modelli riscritta. V2 congelata, non toccata.",
  },
  {
    date: '2026-09-15',
    text: "Cecchino Today ripulito (pulsanti, testata partita, V3.1, audit, diagnostica xG, indice affidabilità segnali), predizione dei pattern con controllo dei moduli in cima alle schede, Intensità Goal V2 con i valori della RUN V2. Nuova pagina Guida ai modelli: come lavorano V2, V2.5 e V3, cosa fanno davvero e gli errori della V2 (tra cui l'Intensità Goal che mescola i campionati, corretta in V2.5 e V3).",
  },
  {
    date: '2026-09-15',
    text: 'Step 6: Pattern Master V2 accesi in live nella scheda V2 di Cecchino Today e nel Bet Builder. Ora tutti e tre i motori (V2, V2.5, V3) accendono i propri pattern Master sulle partite del giorno.',
  },
  {
    date: '2026-09-15',
    text: "V3 estesa online su staging: modello V3 del Lab (parametri congelati, identico alla run finale) calcolato su tutti i campionati con tiri e tiri in porta di API-Football. Sulle partite del 15/09: 13 su 25 coperte, le altre in campionati senza statistiche. Registro previsioni e Osservazione live includono la V3.",
  },
  {
    date: '2026-09-14',
    text: "Step 7 avviato: pagina Osservazione live (motori giorno per giorno contro Bet365, pattern per mercato con esito live e storico, concordanza). Scansione delle 23:00 corretta: le partite venivano escluse quando API-Football rifiutava le richieste (limite al minuto condiviso tra produzione e staging) e le quote si leggevano una partita alla volta.",
  },
  {
    date: '2026-09-14',
    text: "Quote: Bet365 fonte principale per tutti i modelli, Betfair riferimento. Eleggibili solo partite con quote reali Bet365 su 1X2 e Over/Under 2.5. Collegamento dati notturno attivo: statistiche squadra a blocchi da 20 partite e linee Bet365 a .5 salvate per ogni partita.",
  },
  {
    date: '2026-09-14',
    text: "Step 5 avviato: registro previsioni live attivo (V2 e V2.5 congelate prima del calcio d'inizio, esiti a fine partita), primo giorno 9 partite. Acquistabilita' V2.5 corretta (doppia chance e peso del Cecchino) e RUN V2.5 ricalcolata: 87 pattern con quota (79 attesi dal caso). V3 in live in attesa di decisione sui dati.",
  },
  {
    date: '2026-09-14',
    text: 'Step 4 fatto: RUN V2.5 sulle 5 stagioni, piu precisa della V2 in ogni stagione (errore -1/-2,5%) e con circa 700 partite analizzabili in piu a stagione. Master Pattern V2.5: 86 pattern con quota (82 attesi dal caso), 12.234 senza quota (39 attesi dal caso).',
  },
  {
    date: '2026-09-14',
    text: "Step 4: V2.5 scritta con gli stessi calcoli della V2 corretti. Trovati nella RUN V2: Equilibrio con 3 pilastri su 4 vuoti, Acquistabilita' senza classe sul 90% delle righe, 11% delle partite escluse per probabilita' zero, Under 0.5 primo tempo di campionato sempre 0. V2 congelata.",
  },
  {
    date: '2026-09-14',
    text: "Roadmap concordata con l'utente e pubblicata. Produzione una sola volta alla fine; Master Pattern con mercati con e senza quota.",
  },
  {
    date: '2026-09-14',
    text: 'Step 3 fatto: fonte live API-Football; tiri, tiri in porta, corner e cartellini completi in 12 campionati, parziali in 7, assenti in circa 90; manca il collegamento nomi squadra tra live e storico.',
  },
  {
    date: '2026-09-14',
    text: 'Step 1 fatto: pagina Master Pattern con V2 (78 pattern con quota, 5.259 senza quota) e V3 (24 con quota, 2.959 senza quota), dettaglio partite al clic.',
  },
  {
    date: '2026-09-14',
    text: 'Step 2 avviato: rimossi Pattern Insights e le pagine V3 di test (frontend, API e servizi). Aggiunti alla roadmap la dashboard home e la decisione sulla pagina Cecchino.',
  },
  {
    date: '2026-09-14',
    text: 'Step 2: pagina Cecchino tolta, rimosse le parti sicure (circa 160 file tra frontend, API, servizi, test e script), cron formazioni disattivato in staging. Restano da verificare le parti dubbie.',
  },
]
