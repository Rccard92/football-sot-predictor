# Diagnosi V2.5 e V3 dal vivo e piano della V3.2

24/10/2026. Dati: registro live di Cecchino Today (`cecchino_live_predictions`), partite concluse dal 14/09 (V2.5: 1.641 partite, V3: 413), 17 mercati per partita; storico V3 run 11 (16 campionati, 5 stagioni). Solo lettura, nessun dato modificato.

## Cosa funziona

**Le probabilità sono tarate.** Quando V2.5 o V3 dicono X%, succede circa X% delle volte, su tutte le fasce (scarto massimo 1,3 punti, su 27.000 righe V2.5 e 6.900 V3).

## Cosa non funziona

### 1. Il modello non sa più del book
Sui mercati 1X2 e Over/Under il book (tolto il margine) sbaglia meno di entrambi i modelli (Brier 1X2: book 0,199, V3 0,203, V2.5 0,206). Quando il modello si discosta dal book, la realtà dà ragione al book:

| Scarto modello − book | V2.5: modello / book / reale | V3: modello / book / reale |
|---|---|---|
| oltre +8 punti | 49,1 / 37,5 / **37,3** | 58,4 / 47,3 / **49,3** |
| da +3 a +8 | 46,4 / 41,3 / **39,8** | 53,3 / 48,3 / **49,0** |

La V2.5 non aggiunge nulla al book; la V3 aggiunge pochissimo (circa 2 punti su 11 di scarto). Ogni regola che gioca "dove il modello vede più del book" gioca soprattutto i suoi errori.

### 2. I gol sono sottostimati fuori dai 16 campionati
| | V2.5 previsto / reale | V3 previsto / reale |
|---|---|---|
| Over 2,5, campionati fuori dai 16 | 51,9 / 55,3 | 51,5 / **56,8** |
| Over 2,5, 16 campionati | 50,7 / 50,0 | 49,6 / 50,0 |

Due cause, entrambe misurate:
- **livello dei gol del campionato**: per paese lo scarto va da −0,4 gol a partita (Finlandia, Giappone, Corea) a +0,15 (Cina); la V3 dal vivo usa i pesi stimati solo sui 16 campionati;
- **forma della distribuzione**: anche dove la media è giusta il modello mette troppe partite su pochi gol (Norvegia: 3,76 gol attesi contro 3,73 reali, ma Over 2,5 al 65,6% contro 70,7% reale).

Conseguenza: gli Under vengono spinti e perdono; gli Over vengono scartati.

### 3. "In evidenza" sceglie la doppia chance, dove il book guadagna di più
La giocata in evidenza è la più probabile tra quelle con quota ≥ 1,41 e ≥ quota minima: quasi sempre una doppia chance. Sul 12 i bookmaker prezzano in media 80,7% contro 75,2% reale.

| In evidenza V2.5 | Giocate | ROI |
|---|---|---|
| X2 | 281 | −13,1% |
| 1X | 263 | −13,2% |
| Under 3,5 | 254 | −4,7% |
| Over 1,5 | 64 | +32,0% (campione piccolo) |

Lo stesso per la V3 (1X −13,2%, X2 −11,1%).

### 4. Primo tempo e quote alte perdono di più
"2 primo tempo" in evidenza V2.5: −38,8% (36 giocate); indice ≥ 70: −15,5% (290). Sopra quota 2,20 perdono tutti i motori (audit del 19/10).

### 5. Gli indici ≥ 70 perdono quanto il margine
V2.5 indice ≥ 70: −3,8% (2.986 giocate), V3: −3,0% (859): selezionano partite più probabili ma non più convenienti.

## Piano: V3.2 (correzioni, nessuna quota nel ragionamento)

| # | Errore | Correzione | Come si prova |
|---|---|---|---|
| A | Livello dei gol del campionato | Correzione per campionato calcolata solo sulle partite già giocate del campionato (rapporto gol reali / gol attesi, ristretto verso 1 con peso fisso), applicata ai gol attesi | Esame preregistrato sulla stagione 2025 dei 332 campionati fuori dai 16 (79.926 partite finite, mai usate per queste verifiche): log-loss degli Over/Under e scarto di taratura per gruppo di campionati |
| B | Forma della distribuzione dei gol | Scelta, sullo sviluppo, tra distribuzione attuale, senza correzione per i pareggi bassi e distribuzione del totale gol tarata | Stesso esame, la scelta si fa su metà dei campionati e si verifica sull'altra metà |
| C | In evidenza sulla doppia chance | In evidenza solo tra 1X2 finale e Over/Under 1,5-2,5-3,5; niente doppia chance e niente primo tempo; quota tra 1,41 e 2,20; resta "la più probabile" (decisione del 13/10) | Osservazione dal vivo 4 settimane nel Confronto motori accanto alle versioni attuali |
| D | V2.5 doppione peggiore della V3 | La V2.5 resta visibile ma non produce più giocate in evidenza dove c'è la V3 | Confronto motori |

### Cosa non promette
Le correzioni A-D riducono le perdite dovute a errori del modello; non creano da sole un vantaggio sul book, perché sui mercati classici il modello non sa più del book (punto 1). Per il profitto servono informazioni che il book prezza peggio: formazioni e assenze dell'ultima ora, specialisti V5 (Tiri in porta ha passato l'esame), mercati statistici nei campionati minori.
