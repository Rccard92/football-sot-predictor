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
      { text: 'Pagina con 3 riquadri (V2 · V2.5 in costruzione · V3), filtri e tabella dei pattern 4/4', status: 'fatto' },
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
    goal: "Togliere dal menu e dal codice le pagine di test, lasciando un tool ordinato.",
    status: 'da_fare',
    dependsOn: [1],
    tasks: [
      { text: "Elenco delle pagine da togliere, da confermare con l'utente", status: 'da_fare' },
      { text: 'Rimozione da menu e codice (i dati storici restano nel database)', status: 'da_fare' },
    ],
    doneWhen: 'Nel menu restano solo Cecchino Today, Bet Builder, Master Pattern, Roadmap e le pagine scelte.',
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
    goal: 'Stessa struttura e stesse schede della V2, con moduli riscritti per essere piu precisi.',
    status: 'da_fare',
    dependsOn: [3],
    tasks: [
      { text: 'Analisi dei moduli V2: cosa dovrebbero fare, cosa fanno, dove sbagliano (con i numeri dello storico)', status: 'da_fare' },
      { text: "Progetto dei moduli migliorati, approvato dall'utente prima del codice", status: 'da_fare' },
      { text: 'Implementazione modulo per modulo con esame di precisione fissato prima dei risultati', status: 'da_fare' },
      { text: 'RUN V2.5 sulle 5 stagioni', status: 'da_fare' },
      { text: 'Ricerca pattern V2.5 (con e senza quota) e inserimento nella Master Pattern', status: 'da_fare' },
    ],
    doneWhen: 'La V2.5 ha previsioni storiche, pattern 4/4 in pagina e confronto di precisione con V2 e V3.',
  },
  {
    id: 5,
    title: 'Motori in live e registro previsioni',
    goal: 'V2, V2.5 e V3 analizzano le partite del giorno; ogni previsione e salvata prima del calcio di inizio.',
    status: 'da_fare',
    dependsOn: [3, 4],
    tasks: [
      { text: 'Calcolo giornaliero di V2.5 e V3 sulle partite scansionate da Cecchino Today', status: 'da_fare' },
      { text: 'Registro previsioni pre-partita con versione del motore ed esito a partita finita', status: 'da_fare' },
    ],
    doneWhen: 'Ogni partita del giorno ha tre previsioni salvate e, a fine partita, i loro esiti.',
  },
  {
    id: 6,
    title: 'Cecchino Today e Bet Builder',
    goal: "Vedere le tre analisi separate su ogni partita e i pattern Master che si accendono.",
    status: 'da_fare',
    dependsOn: [1, 5],
    tasks: [
      { text: 'Dettaglio analisi con 3 tab: V2, V2.5, V3', status: 'da_fare' },
      { text: 'Segnalazione dei pattern Master attivati durante la scansione, con link al pattern', status: 'da_fare' },
      { text: 'Bet Builder: pattern accesi in osservazione (visibili e registrati, non giocate automatiche)', status: 'da_fare' },
    ],
    doneWhen: 'Su ogni partita vedi tre analisi e i segnali dei pattern, anche per i mercati senza quota.',
  },
  {
    id: 7,
    title: 'Osservazione in live',
    goal: 'Misurare nel tempo motori e pattern sulle partite reali.',
    status: 'da_fare',
    dependsOn: [5, 6],
    tasks: [
      { text: 'Rendimento di ogni motore (precisione) nel tempo', status: 'da_fare' },
      { text: 'Rendimento di ogni pattern Master acceso in live (giocate, vinte, ROI)', status: 'da_fare' },
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
      { text: 'Valutazione API: copertura, dati disponibili, costi', status: 'da_fare' },
      { text: 'Integrazione nelle schede e, se utile, nei motori (come nuova versione misurata in live)', status: 'da_fare' },
    ],
    doneWhen: 'Statistiche e formazioni disponibili nelle schede partita.',
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
]
