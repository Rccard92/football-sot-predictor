export type ChangelogType = 'major' | 'minor' | 'patch'

export type ChangelogEntry = {
  version: string
  date: string
  title: string
  type: ChangelogType
  summary: string
  highlights: string[]
  visible_to_user: boolean
}

export const MODEL_CHANGELOG: ChangelogEntry[] = [
  {
    version: '2.2.0',
    date: '2026-05-19',
    title: 'Consiglio giocata SOT',
    type: 'minor',
    summary:
      'Aggiunto il modulo che trasforma la previsione SOT in indicazioni operative su linee Over statistiche e più caute.',
    highlights: [
      'Aggiunta giocata statistica sulla linea più vicina alla previsione.',
      'Aggiunta giocata cauta con margine minimo di sicurezza.',
      'Aggiunto calcolo del margine rispetto alla linea.',
      'Aggiunto livello di rischio della giocata.',
      'Aggiunta distinzione tra totale match, casa e trasferta.',
      'Il consiglio usa il modello attualmente selezionato.',
    ],
    visible_to_user: true,
  },
  {
    version: '2.1.3',
    date: '2026-05-19',
    title: 'Calibrazione Overall XI e refresh formazioni',
    type: 'patch',
    summary:
      'Migliorata la leggibilità dell’ultimo aggiornamento SportAPI, corretto il calcolo della confidence e resa più realistica la valutazione della forza dell’XI titolare.',
    highlights: [
      'Data ultimo import SportAPI normalizzata in formato leggibile.',
      'Pulsante refresh formazione spostato accanto all’ultimo aggiornamento.',
      'Corretta incoerenza tra Confidence numerica e badge.',
      'Migliorato il calcolo Overall XI.',
      'Attacco SOT ora considera anche forza base squadra e titolari effettivi.',
      'Aggiunte spiegazioni sintetiche dei punteggi formazione.',
    ],
    visible_to_user: true,
  },
  {
    version: '2.1.2',
    date: '2026-05-19',
    title: 'Chiarita logica formazione nel modello 2.0',
    type: 'patch',
    summary:
      'Audit v2.0 più trasparente: formula base × fattori formazione, status Top 5 e ricalcolo automatico dopo aggiornamento SportAPI.',
    highlights: [
      'Sezione dedicata v2.0 con base v1.1, fattori offensivo/difensivo e formula moltiplicativa.',
      'Tabella Top 5 con status lineup (titolare, panchina, assente) e penalità.',
      'Nota esplicita: la rosa completa non entra nel moltiplicatore, solo lo XI SportAPI sui Top 5.',
      'Dopo «Aggiorna formazione SportAPI» in Audit si ricalcolano le predizioni v2.0 salvate.',
      'Metadati audit in raw_json (basis, fetched_at, conteggio titolari).',
    ],
    visible_to_user: true,
  },
  {
    version: '2.1.1',
    date: '2026-05-19',
    title: 'Migliorata disposizione tattica e Overall XI',
    type: 'patch',
    summary:
      'Corretta la disposizione dei giocatori in base al modulo e reso più robusto il calcolo dell’Overall della squadra in campo.',
    highlights: [
      'La formazione ora usa modulo e ordine originale SportAPI per disporre i titolari.',
      'Migliorata la gestione di moduli come 4-3-3, 3-5-2, 3-4-2-1, 3-5-1-1 e 4-2-3-1.',
      'L’Overall XI ora separa forza tecnica e confidence dato.',
      'Aggiunti componenti più leggibili: Attacco SOT, Presenza top shooter, Solidità difensiva, Continuità XI e Gestione assenze.',
      'Ridotti i punteggi sempre a 100 non informativi.',
    ],
    visible_to_user: true,
  },
  {
    version: '2.1.0',
    date: '2026-05-19',
    title: 'Analisi forza formazione',
    type: 'minor',
    summary:
      'Migliorata la sezione formazioni con visualizzazione tattica ordinata, overall della squadra in campo e tabella dei parametri dei titolari.',
    highlights: [
      'Aggiunto Overall XI 0-100 per la squadra che scende in campo.',
      'Aggiunti sotto-punteggi: forza offensiva SOT, solidità difensiva, equilibrio formazione e affidabilità dato.',
      'Migliorata la disposizione tattica per modulo.',
      'Aggiunta tabella dei titolari con SOT/90, tiri/90, quota SOT e impatti offensivi/difensivi.',
      'Migliorata la lettura degli indisponibili.',
      'Aggiornati i badge per distinguere dati usati in v2.0 e dati solo informativi in v1.1.',
    ],
    visible_to_user: true,
  },
  {
    version: '2.0.3',
    date: '2026-05-19',
    title: 'Fix spiegazione previsione',
    type: 'patch',
    summary:
      'Corretta la costruzione della spiegazione partita quando alcune versioni legacy del modello non sono disponibili.',
    highlights: [
      'Risolto errore su variabili legacy mancanti.',
      'Il confronto versioni ora ignora automaticamente i dati non disponibili.',
      'La pagina Audit non si blocca più se manca una versione storica.',
      'Migliorata la gestione dei fallback nella spiegazione previsione.',
    ],
    visible_to_user: true,
  },
  {
    version: '2.0.2',
    date: '2026-05-19',
    title: 'Pulizia Audit e confronto modelli',
    type: 'patch',
    summary:
      'Pagina Spiegazione previsione più chiara: solo partite upcoming, previsione compatta, SportAPI come unica fonte formazioni e confronto versioni con v2.0.',
    highlights: [
      'Dropdown partite limitato al prossimo turno (upcoming).',
      'Sezione «Previsione modello» a tre colonne senza esito reale.',
      'Player DB con default Top 5.',
      'Rimossa sezione formazioni API-Football dall’audit.',
      'Badge SportAPI coerente con v2.0; mapping giocatori in accordion chiuso.',
      'Confronto modelli da v2.0 a v0.1 con delta v2.0 vs v1.1.',
    ],
    visible_to_user: true,
  },
  {
    version: '2.0.1',
    date: '2026-05-19',
    title: 'Tracciabilità modello 2.0',
    type: 'patch',
    summary:
      'Collegata la tracciabilità variabili al modello Lineup Impact, con lettura dei fattori offensivi, difensivi e dei fallback dati.',
    highlights: [
      'Aggiunto manifest variabili per v2.0.',
      'Tracciati offensive factor e defensive weakness factor.',
      'Migliorata gestione dei dati mancanti nel modello 2.0.',
      'Evitato stato errore formula quando il modello usa fallback controllato.',
    ],
    visible_to_user: true,
  },
  {
    version: '2.0.0',
    date: '2026-05-19',
    title: 'v2.0 SOT Lineup Impact',
    type: 'major',
    summary:
      'Nuovo modello che applica l’impatto formazione (SportAPI) sulla base v1.1: fattore offensivo e debolezza difensiva avversaria.',
    highlights: [
      'Formula: base v1.1 × fattore offensivo × debolezza difensiva avversario',
      'Filtro rosa attuale (player_team_seasons) nei Top 5',
      'Fallback sicuro a v1.1 se lineups SportAPI assenti',
      'Pre-match readiness in payload upcoming',
    ],
    visible_to_user: true,
  },
  {
    version: '1.1.0',
    date: '2026-04-01',
    title: 'v1.1 SOT — modello stabile',
    type: 'minor',
    summary:
      'Versione stabile con 6 termini: offensiva, difensiva, split, forma, xG e player layer.',
    highlights: [
      'Nessuna chiamata API live in generazione',
      'Player layer con qualità e fallback tracciati',
      'Raccomandato quando coverage upcoming completa',
    ],
    visible_to_user: true,
  },
  {
    version: '1.0.0',
    date: '2025-12-01',
    title: 'v1.0 SOT (xG)',
    type: 'minor',
    summary: 'Versione parallela con correzione expected goals.',
    highlights: ['Allineamento opzionale con v0.4'],
    visible_to_user: false,
  },
  {
    version: '0.4.0',
    date: '2025-10-01',
    title: 'v0.4 offensive core',
    type: 'patch',
    summary: 'Core offensivo legacy.',
    highlights: [],
    visible_to_user: false,
  },
]

export function visibleChangelogEntries(): ChangelogEntry[] {
  return MODEL_CHANGELOG.filter((e) => e.visible_to_user)
}

export function legacyChangelogEntries(): ChangelogEntry[] {
  return MODEL_CHANGELOG.filter((e) => !e.visible_to_user)
}
