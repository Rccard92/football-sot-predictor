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
    version: '2.14.1',
    date: '2026-05-19',
    title: 'Fix configurazione job pre-match',
    type: 'patch',
    summary:
      'Allineata la configurazione del secret per il job pre-match e mantenuto il pulsante Admin come esecuzione manuale di fallback.',
    highlights: [
      'CRON_SECRET come variabile principale sul backend (fallback ADMIN_CRON_SECRET).',
      'Header X-Admin-Cron-Secret invariato per cron Railway e Admin.',
      'Pulsante «Esegui job ora» per test e forzatura manuale.',
      'Testi Admin aggiornati.',
      'Nessuna modifica al modello v2.0.',
    ],
    visible_to_user: true,
  },
  {
    version: '2.14.0',
    date: '2026-05-19',
    title: 'Ottimizzazione Prossima giornata e fix monitoraggio iniziale',
    type: 'minor',
    summary:
      'Ottimizzata la tab Prossima giornata con caricamento leggero e corretto il confronto tra previsione iniziale e post ufficiali nel Monitoraggio Giocate.',
    highlights: [
      'Corretta ricostruzione previsione iniziale vs post ufficiali.',
      'Sistemato esito iniziale su casi come Bologna–Inter.',
      'Prossima giornata resa più veloce con endpoint leggero.',
      'Dettagli partita caricati on-demand.',
      'Evitati ricalcoli e payload pesanti all’apertura pagina.',
      'Nessuna modifica al modello v2.0.',
    ],
    visible_to_user: true,
  },
  {
    version: '2.13.2',
    date: '2026-05-19',
    title: 'Restyling monitoraggio giocate',
    type: 'patch',
    summary:
      'Migliorata la resa grafica della tabella Monitoraggio Giocate, corretto il mapping tra previsione iniziale e previsione post formazioni ufficiali, e rimossa la scrollbar orizzontale.',
    highlights: [
      'Reintrodotti i loghi squadra nella colonna partita.',
      'Tabella monitoraggio resa più gradevole e leggibile.',
      'Corretto il mapping iniziale vs post ufficiali.',
      'Rimossa la scrollbar orizzontale su desktop.',
      'Nessuna modifica al modello v2.0.',
    ],
    visible_to_user: true,
  },
  {
    version: '2.13.1',
    date: '2026-05-19',
    title: 'Fix circular import monitoraggio',
    type: 'patch',
    summary:
      'Risolto un circular import nei servizi di Monitoraggio Giocate che impediva l’avvio del backend.',
    highlights: [
      'Spostate costanti stato partita in un modulo condiviso.',
      'Rimossa dipendenza circolare tra refresh risultati e dashboard monitoraggio.',
      'Backend di nuovo avviabile su Railway.',
      'Nessuna modifica a formule, modelli o prediction engine.',
    ],
    visible_to_user: true,
  },
  {
    version: '2.13.0',
    date: '2026-05-19',
    title: 'Monitoraggio doppia previsione SOT',
    type: 'minor',
    summary:
      'Rifatta la dashboard Monitoraggio Giocate per confrontare previsione iniziale, previsione post formazioni ufficiali, scommesse proposte ed esiti reali.',
    highlights: [
      'Nuova tabella monitoraggio in stile dashboard scommessa.',
      'Confronto tra SOT iniziali e SOT post formazioni ufficiali.',
      'Doppia valutazione esito: pronostico iniziale e pronostico aggiornato.',
      'Tiri in porta reali aggiornabili live da API-Sports.',
      'Partite live evidenziate con riga bold e bollino LIVE.',
      'Quote predisposte ma non inventate se non disponibili.',
    ],
    visible_to_user: true,
  },
  {
    version: '2.12.3',
    date: '2026-05-19',
    title: 'Refresh automatico Monitoraggio Giocate',
    type: 'patch',
    summary:
      'All’apertura di Monitoraggio Giocate i risultati si aggiornano automaticamente da API-Sports per partite non concluse o con dati live obsoleti.',
    highlights: [
      'Refresh automatico all’apertura della pagina (scope unfinished_or_recent).',
      'Riconciliazione partite ancora “live” nel DB dopo ore dal kickoff.',
      'Cooldown 2 minuti per evitare refresh ripetuti (Strict Mode / cambio tab).',
      'Pulsante «Aggiorna risultati» con force per aggiornare tutto.',
      'Auto-refresh ogni 5 min solo per partite realmente live.',
      'Nessuna modifica a modelli v2.0, betting advice o SportAPI formazioni.',
    ],
    visible_to_user: true,
  },
  {
    version: '2.12.2',
    date: '2026-05-19',
    title: 'Sidebar fissa durante lo scroll',
    type: 'patch',
    summary:
      'Migliorata la navigazione rendendo il menu laterale sempre visibile su desktop durante lo scroll.',
    highlights: [
      'Sidebar desktop resa sticky/fissa.',
      'Migliorata la navigazione nelle pagine lunghe.',
      'Mantenuto il comportamento hamburger su mobile.',
      'Nessuna modifica a modelli, API o prediction engine.',
    ],
    visible_to_user: true,
  },
  {
    version: '2.12.1',
    date: '2026-05-19',
    title: 'Fix SOT live monitoraggio',
    type: 'patch',
    summary:
      'Migliorato il recupero dei tiri in porta live/finali da API-Sports e ridotto l’auto-refresh live a 5 minuti.',
    highlights: [
      'Auto-refresh live portato a 5 minuti.',
      'Migliorato parser Shots on Goal / Shots on Target.',
      'Aggiunto debug statistiche per partite live.',
      'Migliorato matching home/away nelle statistiche API-Sports.',
      'Migliorata visualizzazione dei SOT live/finali nel monitoraggio.',
    ],
    visible_to_user: true,
  },
  {
    version: '2.12.0',
    date: '2026-05-19',
    title: 'Refresh ufficiale pre-match',
    type: 'minor',
    summary:
      'Aggiunto job automatico per aggiornare le formazioni circa 30 minuti prima del calcio d’inizio e sincronizzare le prediction definitive nel monitoraggio live.',
    highlights: [
      'Refresh automatico SportAPI solo per partite vicine al kickoff.',
      'Ricalcolo v2.0 dopo formazione ufficiale o probabile aggiornata.',
      'Sincronizzazione automatica con Monitoraggio Giocate.',
      'Aggiornamento della variazione pre/post formazione.',
      'Evitate chiamate inutili su tutto il turno.',
      'Preparazione all’esecuzione tramite cron Railway.',
    ],
    visible_to_user: true,
  },
  {
    version: '2.11.0',
    date: '2026-05-19',
    title: 'Monitoraggio live SOT',
    type: 'minor',
    summary:
      'Monitoraggio giocate più leggibile in live: SOT da API-Sports con parser robusto, auto-refresh ogni 60s sulle partite in corso e colonna SOT con messaggi espliciti quando i dati non sono disponibili.',
    highlights: [
      'Tabella monitoraggio semplificata: tipo e origine come badge nella colonna Pick.',
      'Righe live evidenziate con badge LIVE e aggiornamento automatico ogni 60 secondi.',
      'Parser SOT API-Sports migliorato (alias, fallback ordine squadre, valori "4.0").',
      'Colonna SOT con formato "4 + 2 = 6" o messaggio "SOT non disponibili" con tooltip.',
      'Refresh risultati con scope all / live / unfinished per ridurre chiamate API.',
      'Hint live e finali sulla linea Over (superata / mancano N SOT).',
    ],
    visible_to_user: true,
  },
  {
    version: '2.10.1',
    date: '2026-05-19',
    title: 'Fix scansione provider SOT',
    type: 'patch',
    summary:
      'Corretta la scansione dei provider SportAPI e migliorata la diagnostica quando i mercati SOT non sono esposti dal feed.',
    highlights: [
      'Risolto caso in cui la scansione controllava 0 provider.',
      'Aggiunta diagnostica provider salvati/controllati.',
      'Migliorata gestione canale app/web se disponibile.',
      'Aggiunta nota sulla differenza tra bookmaker reale e feed SportAPI.',
      'Migliorato messaggio quando nessun mercato SOT viene trovato.',
    ],
    visible_to_user: true,
  },
  {
    version: '2.10.0',
    date: '2026-05-19',
    title: 'Scansione provider per mercati SOT',
    type: 'minor',
    summary:
      'Migliorata la discovery SportAPI con raggruppamento corretto dei mercati e scansione dei provider italiani alla ricerca di mercati SOT.',
    highlights: [
      'I choice/outcome non vengono più mostrati come mercati separati.',
      'I mercati vengono raggruppati correttamente con linee e outcome.',
      'Aggiunta scansione dei provider italiani per cercare mercati SOT.',
      'I mercati corner non vengono più confusi con SOT.',
      'Migliorato il messaggio quando i SOT non sono disponibili.',
    ],
    visible_to_user: true,
  },
  {
    version: '2.9.0',
    date: '2026-05-19',
    title: 'Discovery mercati SOT bookmaker',
    type: 'minor',
    summary:
      'Ordinamento cronologico nel Monitoraggio Giocate e nuova discovery mercati SportAPI in Bookmakers con mapping SOT e test quote del turno.',
    highlights: [
      'Monitoraggio: partite ordinate per kickoff crescente (prima le più vicine).',
      'Bookmakers: scoperta di tutti i mercati odds per evento SportAPI.',
      'Rilevamento automatico candidati SOT (tiri in porta) con esclusione goals/BTTS/corners.',
      'Salvataggio mapping mercato raw → chiave normalizzata (match_total_sot, ecc.).',
      'Test batch Over/Under SOT sul prossimo turno usando i mapping salvati.',
      'Quote SOT solo informative: nessun impatto su pronostici, consiglio o monitoraggio.',
    ],
    visible_to_user: true,
  },
  {
    version: '2.8.0',
    date: '2026-05-19',
    title: 'Monitoraggio turno e risultati reali',
    type: 'minor',
    summary:
      'Migliorato il Monitoraggio Giocate con creazione manuale delle pick dal turno e aggiornamento dei risultati live/finali da API-Sports.',
    highlights: [
      'Aggiunto pulsante per creare il monitoraggio dal turno corrente.',
      'Le pick possono essere ricostruite dalle predizioni già disponibili.',
      'Aggiornamento risultati live/finali da API-Sports.',
      'Calcolo esito vinta/persa per Over SOT.',
      'Migliorata la gestione delle partite finite e live.',
      'Il monitoraggio non dipende più solo dal job pre-match.',
    ],
    visible_to_user: true,
  },
  {
    version: '2.7.1',
    date: '2026-05-19',
    title: 'Fix riconoscimento mercato 1X2 SportAPI',
    type: 'patch',
    summary:
      'Corretto il riconoscimento del mercato Full time come 1X2 nella discovery quote SportAPI.',
    highlights: [
      'Il mercato Full time viene ora normalizzato come 1X2.',
      'Migliorato il parser degli outcome 1 / X / 2.',
      'Migliorata la gestione dei campi quota con nomi diversi.',
      'Aggiunto debug raw del mercato quando la normalizzazione fallisce.',
      'Le quote restano solo informative e non influenzano ancora i pronostici.',
    ],
    visible_to_user: true,
  },
  {
    version: '2.7.0',
    date: '2026-05-19',
    title: 'SportAPI Bookmakers e quote 1X2',
    type: 'minor',
    summary:
      'La tab Bookmakers usa SportAPI come unica fonte visibile: sync provider Italia, dettaglio Sisal e recupero manuale quote 1X2 del prossimo turno.',
    highlights: [
      'Sync provider odds SportAPI (mercato IT, canale app).',
      'Dettaglio bookmaker Sisal con oddsProvider, oddsFrom e liveOddsFrom.',
      'Test quote per singolo evento con scelta automatica del provider_id funzionante.',
      'Batch manuale quote 1X2 per il prossimo turno Serie A.',
      'Quote e provider solo informativi: nessun impatto su pronostici o consiglio giocata.',
    ],
    visible_to_user: true,
  },
  {
    version: '2.6.1',
    date: '2026-05-19',
    title: 'SportAPI odds discovery',
    type: 'patch',
    summary:
      'Aggiunta la possibilità di testare le quote SportAPI per singola partita e confrontare la copertura con i bookmakers API-Sports.',
    highlights: [
      'Aggiunto test quote SportAPI per event_id/providerId.',
      'Aggiunta normalizzazione difensiva dei mercati odds SportAPI.',
      'Aggiunto raw payload consultabile.',
      'Aggiunto confronto iniziale tra fonte API-Sports e fonte SportAPI.',
      'Nessuna quota viene ancora usata nei pronostici.',
    ],
    visible_to_user: true,
  },
  {
    version: '2.6.0',
    date: '2026-05-19',
    title: 'Bookmakers discovery',
    type: 'minor',
    summary:
      'Aggiunta la nuova sezione Bookmakers per recuperare e consultare i bookmaker disponibili da API-Sports.',
    highlights: [
      'Aggiunta tab Bookmakers.',
      'Aggiunto recupero bookmakers da API-Sports.',
      'Aggiunto salvataggio bookmakers nel database.',
      'Aggiunta tabella consultabile con ricerca e filtri.',
      'Preparata la base per la futura integrazione quote e mercati.',
    ],
    visible_to_user: true,
  },
  {
    version: '2.5.0',
    date: '2026-05-19',
    title: 'Pronostico definitivo pre-match',
    type: 'minor',
    summary:
      'Aggiunto il job che aggiorna automaticamente le formazioni circa 30 minuti prima della partita e salva il pronostico definitivo da monitorare live.',
    highlights: [
      'Refresh automatico SportAPI vicino al calcio d\'inizio.',
      'Salvataggio snapshot definitiva del pronostico v2.0.',
      'Distinzione tra pronostico con formazione ufficiale e probabile.',
      'Integrazione con Monitoraggio Giocate.',
      'Riduzione del rischio di monitorare pronostici basati su formazioni vecchie.',
    ],
    visible_to_user: true,
  },
  {
    version: '2.4.1',
    date: '2026-05-19',
    title: 'Report rapido — fix UX',
    type: 'patch',
    summary:
      'Migliorata la tabella Report rapido: colonna Variazione più visibile, etichette formazione chiare, Affidabilità al posto di Confidence e refresh turno che traccia subito i delta v2.0.',
    highlights: [
      'Colonna Variazione spostata subito dopo Previsti (desktop e mobile).',
      'Stato formazione: Ufficiale, Aggiornata (≤6h), Da aggiornare, Mancante.',
      'Colonna rinominata in Affidabilità con tooltip sulla qualità dei dati.',
      'Refresh turno con tracciamento v2.0 quando il report usa previsioni 2.0.',
      'Delta pronostico mostrato subito dopo il refresh, prima del reload completo.',
      'Riepilogo refresh in accordion «Dettagli variazioni».',
    ],
    visible_to_user: true,
  },
  {
    version: '2.4.0',
    date: '2026-05-19',
    title: 'Layout più ampio e menu responsive',
    type: 'minor',
    summary:
      'Allargata la griglia principale del tool e migliorata la navigazione con sidebar comprimibile e menu mobile.',
    highlights: [
      'Aumentata la larghezza massima del contenuto a 1320px.',
      'Migliorata la leggibilità di card, tabelle e sezioni Audit.',
      'Aggiunta sidebar comprimibile su desktop.',
      'Aggiunte icone alle voci di menu.',
      'Su mobile la navigazione passa a menu hamburger.',
      'Migliorata la gestione responsive generale del tool.',
    ],
    visible_to_user: true,
  },
  {
    version: '2.3.0',
    date: '2026-05-19',
    title: 'Report rapido giocate',
    type: 'minor',
    summary:
      'In Prossima giornata compare una tabella sintetica con giocate statistiche e caute, stato formazione SportAPI e aggiornamento batch del turno.',
    highlights: [
      'Tabella «Report rapido giocate» sopra le card del prossimo turno.',
      'Colonne: data, match, mercato SOT totale, previsti, statistica, cauta, confidence e formazione.',
      'Link «Dettaglio» che porta alla card completa della partita.',
      'Pulsante per aggiornare le formazioni SportAPI di tutto il turno (con conferma).',
      'Le partite aggiornate negli ultimi 10 minuti vengono saltate per risparmiare chiamate API.',
      'Opzione di rigenerare le previsioni v2.0 dopo il refresh quando il modello in vista è 2.0.',
    ],
    visible_to_user: true,
  },
  {
    version: '2.3.1',
    date: '2026-05-19',
    title: 'Variazione pronostico dopo refresh formazioni',
    type: 'patch',
    summary:
      'Aggiunto il confronto pre/post aggiornamento SportAPI per capire subito se e perché il pronostico SOT è salito, sceso o rimasto stabile.',
    highlights: [
      'Salvato snapshot della previsione prima e dopo il refresh formazioni.',
      'Aggiunta freccia UP/DOWN/FLAT nella tabella Report rapido.',
      'Aggiunti motivi leggibili della variazione.',
      'Il refresh globale del turno mostra quante partite sono salite, scese o rimaste stabili.',
      'La variazione confronta anche cambi nei titolari, missingPlayers e fattori lineup.',
    ],
    visible_to_user: true,
  },
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
