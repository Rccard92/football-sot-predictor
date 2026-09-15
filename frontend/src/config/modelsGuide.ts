/**
 * Guida ai modelli Cecchino (pagina /guida-modelli).
 * Testi pensati per chi non ha mai usato il tool. Numeri aggiornati al 15/09/2026:
 * vanno rivisti quando cambiano le RUN, i Master Pattern o i risultati dell'osservazione live.
 */

export const GUIDE_UPDATED_AT = '15/09/2026'

export type GlossaryItem = { term: string; text: string }

export const GUIDE_GLOSSARY: GlossaryItem[] = [
  { term: 'Quota', text: 'Il prezzo pagato dal bookmaker (Bet365). Quota 2,00 = giochi 1 € e se vinci ne ricevi 2.' },
  {
    term: 'Probabilità',
    text: 'Quante volte su 100 il modello si aspetta che un esito accada. 50% = una volta su due.',
  },
  {
    term: 'Quota minima',
    text: 'La quota sotto la quale una giocata non rende nel lungo periodo: 100 diviso la percentuale di riuscita. Con il 50% di riuscita serve almeno quota 2,00.',
  },
  {
    term: 'Valore atteso',
    text: 'Quanto si guadagna (o si perde) in media per ogni euro giocato, se la probabilità è giusta: probabilità × quota − 1. +5% = 5 centesimi guadagnati ogni euro, in media.',
  },
  {
    term: 'ROI',
    text: 'Il guadagno reale ottenuto su tutte le giocate, diviso quanto si è giocato. È il numero che conta: dice se nel passato una scelta ha fatto guadagnare.',
  },
  {
    term: 'Modulo',
    text: 'Un pezzo del modello che guarda la partita da un punto di vista: equilibrio tra le squadre, quanti gol aspettarsi, forma recente, ecc.',
  },
  {
    term: 'Pattern',
    text: 'Una combinazione di condizioni dei moduli (per esempio "partita equilibrata + tanti gol attesi") che nello storico ha portato a un risultato ripetuto.',
  },
  {
    term: 'Master Pattern',
    text: 'I pattern che hanno funzionato in tutte e 4 le stagioni di verifica (2022/23, 2023/24, 2024/25, 2025/26): per i mercati con quota, ROI positivo in ognuna.',
  },
  {
    term: 'RUN',
    text: 'Il modello fatto girare su un\'intera stagione passata, partita per partita, usando solo le informazioni disponibili prima di ogni partita. Serve a vedere come avrebbe funzionato davvero.',
  },
  {
    term: 'Precisione (Brier)',
    text: 'Misura quanto le probabilità si avvicinano ai risultati veri. Più è bassa, meglio è. Si usa per confrontare i modelli tra loro e con il bookmaker.',
  },
  {
    term: 'Per caso',
    text: 'Su migliaia di combinazioni provate, alcune "funzionano" solo per fortuna. Ogni conteggio di pattern vincenti va confrontato con quanti ne uscirebbero per puro caso.',
  },
]

export const GUIDE_FLOW: { title: string; text: string }[] = [
  {
    title: '1. Scansione alle 06:00',
    text: 'Ogni mattina il tool scarica le partite del giorno da API-Football con le quote Bet365.',
  },
  {
    title: '2. Partite eleggibili',
    text: 'Entra solo la partita che ha le quote reali Bet365 di 1X2 e Over/Under 2.5 e abbastanza storico delle due squadre.',
  },
  {
    title: '3. Tre modelli, tre schede',
    text: 'Ogni partita viene letta da V2, V2.5 e V3. Sono tre modi diversi di fare la stessa cosa: vanno confrontati, non sommati.',
  },
  {
    title: '4. La predizione',
    text: 'In cima a ogni scheda ci sono i Master Pattern con quota che si accendono: sono la giocata indicata dal modello, con riuscita storica, quota minima e quota di oggi.',
  },
  {
    title: '5. Il controllo dei moduli',
    text: 'Sotto ogni pattern i moduli dicono, ragionando da soli, se sono d\'accordo (confermato), contrari (smentito) o divisi (discordanti).',
  },
  {
    title: '6. Registro e risultati',
    text: 'Le predizioni vengono salvate prima della partita e non si cambiano più. Dopo la partita si segna l\'esito: così si misura se i modelli fanno guadagnare davvero (pagina Osservazione live).',
  },
]

export type ModelCard = {
  key: 'V2' | 'V2.5' | 'V3'
  name: string
  status: string
  inOneLine: string
  shouldDo: string[]
  howItWorks: string[]
  reallyDoes: string[]
}

export const GUIDE_MODELS: ModelCard[] = [
  {
    key: 'V2',
    name: 'Cecchino V2 · il modello originale',
    status: 'Congelato: non si modifica, serve come termine di paragone',
    inOneLine: 'Stima le probabilità dagli esiti delle partite passate delle due squadre e le confronta con le quote Bet365.',
    shouldDo: [
      'Dare per ogni mercato (1X2, doppia chance, primo tempo, Over/Under) una probabilità e una "quota Cecchino".',
      'Trovare i mercati dove la quota Bet365 è più alta di quanto dovrebbe.',
      'Accendere segnali SI/NO e un indice di acquistabilità per dire cosa comprare.',
    ],
    howItWorks: [
      'Picchetti: in quattro finestre di partite (totali, casa/trasferta, recenti) conta quante volte le squadre hanno vinto, pareggiato e perso.',
      'Modello gol: stima i gol delle due squadre (65% modello di Poisson, 35% frequenze reali).',
      'Moduli: Equilibrio/Squilibrio, Intensità Goal, Indice di Acquistabilità V3.6, Segnali Excel, Pannello KPI con rating.',
    ],
    reallyDoes: [
      'È meno preciso di Bet365 in ogni tipo di mercato, in ogni stagione e in ogni campionato provato.',
      'Master Pattern V2 con quota: 78 vincenti in tutte le 4 stagioni, contro circa 69 attesi per puro caso.',
      'Ha diversi errori di calcolo, elencati più sotto: sono stati lasciati apposta per poter confrontare "prima" e "dopo".',
    ],
  },
  {
    key: 'V2.5',
    name: 'Cecchino V2.5 · la V2 con i calcoli corretti',
    status: 'Attivo in osservazione live',
    inOneLine: 'Stessa struttura e stessi moduli della V2, ma con gli errori corretti.',
    shouldDo: [
      'Fare esattamente quello che doveva fare la V2, senza gli errori di calcolo.',
      'Permettere un confronto pulito: se la V2.5 rende più della V2, il merito è delle correzioni.',
    ],
    howItWorks: [
      'Picchetti: media delle probabilità (sommano sempre a 100%) e poche partite "virtuali" con le medie del campionato quando lo storico è corto.',
      'Gol, attacco, difesa e ritmo sempre rapportati alla media del proprio campionato.',
      'Scale delle classi fissate una volta sola sulla stagione 2021/22: "alta" vuol dire la stessa cosa in ogni stagione e in ogni campionato.',
      'Indice di acquistabilità: il valore atteso alla quota Bet365, corretto con quanto il Cecchino ha davvero aggiunto al book nelle partite già giocate.',
    ],
    reallyDoes: [
      'Più preciso della V2 in ogni stagione: 1X2 dall\'1% all\'1,3% meglio, Over/Under dall\'1,1% all\'1,9%. Resta però meno preciso di Bet365.',
      'Circa 700 partite in più per stagione diventano analizzabili (la V2 le scartava per un errore).',
      'Intensità Goal: più alta è la classe, più partite finiscono Over 2.5 (dal 41,9% al 60,0%). Il modulo misura quello che deve misurare.',
      'Master Pattern V2.5 con quota: 87 vincenti contro circa 79 attesi per caso.',
      'Indice di acquistabilità: nelle stagioni di verifica nessuna classe ha chiuso in profitto (Media −2,9%, Bassa −6,0%). Consiglia solo da 60/100 in su, dove il valore atteso stimato è positivo.',
    ],
  },
  {
    key: 'V3',
    name: 'Cecchino V3 estesa · il modello nuovo',
    status: 'Attivo in osservazione live, solo nei campionati con tiri e tiri in porta',
    inOneLine: 'Un modello ricostruito da zero: più "specialisti" stimano i gol attesi e un orchestratore li combina.',
    shouldDo: [
      'Stimare le probabilità meglio di V2 e V2.5, usando anche il gioco (tiri) e non solo i risultati.',
      'Avvicinarsi il più possibile alla precisione di Bet365.',
    ],
    howItWorks: [
      'Specialista Forza: attacco e difesa delle squadre stimati sui gol.',
      'Specialista Gioco: tiri e tiri in porta attesi, tradotti in gol.',
      'Forma (ultime 5 partite rispetto alle attese) e Calendario (giorni di riposo, ultime giornate).',
      'Orchestratore: combina gli specialisti con pesi imparati sulle stagioni passate e poi congelati.',
      'Indici: Equilibrio, Pareggio, Intensità goal e Forma, sempre confrontati con lo stesso campionato.',
    ],
    reallyDoes: [
      'È di gran lunga il modello più preciso. Sulla stagione 2025/26, usata una sola volta come esame finale: 1X2 5,1% meglio della V2, Over/Under 2,5% meglio.',
      'La distanza da Bet365 sull\'1X2 scende a +1,7% (la V2 è a +7,2%).',
      'Però alle quote Bet365 non ha trovato un vantaggio: quando V3 e bookmaker non sono d\'accordo, di solito ha ragione il bookmaker. Per questo l\'indice di acquistabilità V3 non è attivo.',
      'Master Pattern V3 con quota: 24 vincenti contro circa 28 attesi per caso.',
      'Dal vivo funziona solo dove API-Football fornisce tiri e tiri in porta: il 15/09 in 13 partite eleggibili su 25.',
    ],
  },
]

export const GUIDE_PATTERN_RULES: string[] = [
  'La ricerca parte dalla stagione 2021/22: si provano migliaia di combinazioni di condizioni dei moduli.',
  'Ogni pattern trovato viene poi verificato, in ordine, su 2022/23, 2023/24, 2024/25 e 2025/26, stagioni che non ha mai "visto".',
  'Diventa Master Pattern solo se funziona in tutte e 4, con almeno 20 partite per stagione.',
  'Mercati con quota (1X2, doppia chance, Over/Under...): ROI positivo alla quota Bet365 in ogni stagione.',
  'Mercati senza quota (tiri, tiri in porta, corner, cartellini): almeno 5 punti sopra o sotto la media, sempre nella stessa direzione. Restano in fondo alla scheda, solo in osservazione, perché senza quota non si può misurare il profitto.',
  'Attenzione: su migliaia di tentativi qualche pattern passa anche per fortuna. Per questo il numero dei vincenti va sempre confrontato con quelli attesi per caso, e ogni pattern va seguito dal vivo prima di fidarsi.',
]

export const GUIDE_MODULE_CHECK: string[] = [
  'Confermato dai moduli: almeno un modulo va nella stessa direzione del pattern e nessuno va contro.',
  'Smentito dai moduli: almeno un modulo va contro e nessuno a favore.',
  'Moduli discordanti: ci sono moduli a favore e moduli contro.',
  'Moduli senza indicazione: nessun modulo si sbilancia.',
  'Controlli usati: esito più probabile per il modello, credibilità del pareggio, coerenza tra picchetti e modello gol, Intensità Goal (Over/Under), valore alla quota Bet365.',
  'Il controllo è una prima versione: nei prossimi mesi l\'osservazione live dirà se i pattern confermati rendono più di quelli smentiti.',
]

export type V2Bug = { module: string; problem: string; effect: string; fix: string }

export const GUIDE_V2_BUGS: V2Bug[] = [
  {
    module: 'Picchetti 1X2',
    problem: 'Fa la media delle quote invece che delle probabilità.',
    effect: 'Gli esiti incerti (soprattutto la X) risultano gonfiati e le tre probabilità non sommano a 100%.',
    fix: 'Media delle probabilità: sommano sempre a 100%.',
  },
  {
    module: 'Picchetti 1X2',
    problem: 'Se in una finestra un esito non è mai capitato, la partita diventa non calcolabile.',
    effect: 'Nella RUN V2 705 partite su 6.308 sono state scartate per questo motivo.',
    fix: 'Poche partite "virtuali" con le frequenze del campionato: nessun esito vale mai 0.',
  },
  {
    module: 'Modello gol',
    problem: 'Con 1-2 partite giocate il valore della squadra viene preso così com\'è, e l\'affidabilità arriva al massimo già dopo 5-10 partite.',
    effect: 'Stime estreme a inizio stagione; la correzione verso la media del campionato sparisce troppo presto.',
    fix: 'La stima parte dalla media del campionato e si sposta verso la squadra man mano che giocano partite.',
  },
  {
    module: 'Modello gol',
    problem: 'Casa e trasferta confrontate con la media generica del campionato; frequenza di campionato dell\'Under 0.5 primo tempo sempre 0.',
    effect: 'Stime distorte per le squadre forti in casa o fuori; un mercato del primo tempo sempre sbagliato.',
    fix: 'Media gol in casa o in trasferta del campionato; frequenze di campionato corrette per tutti i mercati.',
  },
  {
    module: 'Pannello KPI',
    problem: 'Il "vantaggio" è calcolato contro la probabilità del bookmaker con il suo margine dentro, e l\'edge è quota book / quota Cecchino − 1.',
    effect: 'Il vantaggio sembra più piccolo di quello che è e l\'edge non è il guadagno atteso reale della giocata.',
    fix: 'Vantaggio contro la probabilità Bet365 senza margine; valore atteso = probabilità × quota − 1.',
  },
  {
    module: 'Equilibrio / Squilibrio',
    problem: 'La geometria (F36) è la differenza tra le quote di 1 e 2 con soglie fisse, corretta con la quota X del bookmaker.',
    effect: 'Tra 1,50 e 2,00 e tra 4,00 e 4,50 la differenza è la stessa, ma l\'equilibrio no. E il modulo dipende dalle quote del book.',
    fix: 'Distanza tra le probabilità di 1 e 2 calcolate solo dal Cecchino.',
  },
  {
    module: 'Equilibrio / Squilibrio',
    problem: 'La "coerenza" confronta le quote con un indice ricavato dalle stesse quote; nella RUN V2 tre pilastri su quattro non hanno mai una classe salvata.',
    effect: 'La coerenza risulta sempre coerente con se stessa; Convinzione, Credibilità X e Coerenza erano vuoti per tutte le partite e i pattern non potevano usarli.',
    fix: 'La coerenza confronta due motori diversi (picchetti e modello gol); tutti e quattro i pilastri hanno la loro classe.',
  },
  {
    module: 'Intensità Goal',
    problem: 'Mette tutti i campionati nello stesso calderone: i gol di una partita vengono confrontati con quelli di tutti i 16 campionati insieme, non con quelli del suo campionato.',
    effect: 'La classe dice soprattutto in quale campionato si gioca. Nella RUN V2 2025/26 in Bundesliga l\'83% delle partite è "alta" o "molto alta" e nessuna è "bassa"; in Serie A solo il 7,7% è "alta" e il 54,9% è "bassa".',
    fix: 'Attacco, difesa e ritmo rapportati alla media del proprio campionato.',
  },
  {
    module: 'Intensità Goal',
    problem: 'La produzione offensiva guarda solo i gol fatti in casa dalla squadra di casa; la stabilità è la variabilità dei gol (che cresce con i gol) e la classe finale è la media dei pilastri.',
    effect: 'L\'attacco dell\'ospite non conta; "stabilità" diventa un altro modo di contare i gol; la classe finale non è la reale attesa di gol della partita.',
    fix: 'Attacchi di entrambe le squadre; costanza nel segnare; classe finale = probabilità Over 2.5 del modello gol.',
  },
  {
    module: 'Intensità Goal',
    problem: 'Le classi vengono ricalcolate durante la stagione, e il pannello Today usa un metro diverso (453 partite estive) da quello della RUN V2 (4.423 partite).',
    effect: 'Classi mancanti a inizio anno e con significato che cambia nel tempo; sulla stessa partita pannello e pattern potevano dire due classi diverse.',
    fix: 'Scale congelate sulla stagione 2021/22, uguali per tutti. Nella scheda V2 il pannello ora mostra i valori della RUN V2, quelli letti dai pattern.',
  },
  {
    module: 'Indice di Acquistabilità V3.6',
    problem: 'Dà un punteggio solo quando il Cecchino vede valore sulla quota e premia la distanza dal bookmaker come se fosse sempre un vantaggio; usa la probabilità grezza non normalizzata.',
    effect: 'Nella RUN V2 circa il 90% delle righe è senza classe e le altre sono quasi tutte "Molto bassa". Ma il bookmaker è mediamente più preciso: una grande distanza è spesso un errore del Cecchino, non un\'occasione.',
    fix: 'Punteggio per ogni mercato quotato, dal valore atteso corretto con lo storico delle partite già giocate.',
  },
  {
    module: 'Segnali Cecchino',
    problem: 'Le regole SI/NO usano soglie sulle quote V2, che sono medie di quote e quindi gonfiate. L\'"Indice affidabilità" è solo il numero di partite casa/fuori diviso 20.',
    effect: 'Le soglie dipendono dall\'errore dei picchetti. L\'indice affidabilità non dice se i segnali vincono e il suo "NO BET" non blocca nulla.',
    fix: 'Stesse regole su quote riportate alla scala V2, mantenendo la stessa selettività. Indice affidabilità tolto dalla scheda V2.',
  },
]

export const GUIDE_GI_LEAGUES: { league: string; goals: string; over: string; high: string; low: string }[] = [
  { league: 'Bundesliga', goals: '3,31', over: '63,9%', high: '83,3%', low: '0,0%' },
  { league: 'Eredivisie', goals: '3,06', over: '57,9%', high: '84,3%', low: '0,0%' },
  { league: 'Premier League', goals: '2,73', over: '55,0%', high: '42,6%', low: '9,9%' },
  { league: 'Serie B', goals: '2,58', over: '48,0%', high: '14,6%', low: '41,1%' },
  { league: 'Serie A', goals: '2,50', over: '48,0%', high: '7,7%', low: '54,9%' },
]

export const GUIDE_NEXT: string[] = [
  'Osservazione live per alcuni mesi: le predizioni salvate prima delle partite diranno quale modello e quali pattern fanno guadagnare davvero.',
  'Verificare se i pattern confermati dai moduli rendono più di quelli smentiti.',
  'Capire se i pattern trovati sui 16 campionati europei del Lab funzionano anche nei campionati minori che entrano ogni giorno in Cecchino Today.',
  'Aggiungere formazioni e infortuni da una fonte dedicata (API-Football non li fornisce bene per i campionati minori).',
]
