# Roadmap Cecchino V5

Versione 2, 22 ottobre 2026. Sostituisce la versione 1 (20/10, modello unico): la V5 diventa una famiglia di quattro specialisti verticali con una base comune. Bozza da rivedere insieme, nessuna riga di codice scritta. Gli esami sono fissati qui **prima** di vedere i risultati; si cambiano solo con una nuova versione di questo file, datata e motivata.

## 1. Perché la V5 e perché quattro specialisti

L'audit del 20/10/2026 (dati dal 16/09 al 19/10) dice tre cose:

- **Le probabilità sono già buone.** La V3 sbaglia circa il 5% in meno della V2 ed è tarata dal vivo. Eppure l'indice V3 rende −2,6% (946 giocate), la V2.5 −4,8% (3.521).
- **Il profitto si perde nella scelta.** La regola "quota ≥ quota minima" prende i casi in cui il modello esagera (In evidenza V2.5: 60% mostrato, 54% reale); il rating KPI va al contrario; sopra 2,20 tutte le versioni perdono di più.
- **Il momento conta.** Sulle previsioni V2.5 e V3 la quota del mattino è più alta della chiusura dello 0,7% (78 giocate); sulle statistiche V4 succede il contrario (−0,36%, 46 giocate).

Ogni mercato dipende da cose diverse: gli angoli dallo stile d'attacco, i cartellini soprattutto dall'arbitro, i tiri in porta dalle occasioni create. Per questo la V5 non è un modello unico ma **quattro specialisti**, ognuno con i suoi ingredienti, il suo esame e la sua lista, sopra una base comune.

## 2. La famiglia V5

| Specialista | Mercati | Ingredienti principali (mai quote) | Campionati | Riferimento da superare |
|---|---|---|---|---|
| **V5 Valore** | 17 mercati classici (1X2, doppia chance, over/under 0,5-3,5, primo tempo) a quota 1,80-2,20 | forza e gol attesi (base V3), forma, calendario, segnali V2.5 | tutti quelli giocabili in Cecchino Today (circa 600) | In evidenza V3 e V2.5, Combo |
| **V5 Angoli** | angoli totali e per squadra, over/under | angoli fatti e concessi in casa e fuori, tiri, possesso, chi è favorito, media del campionato | dove il book quota gli angoli (circa 150 questa settimana) | previsione semplice (medie squadra e campionato) e V4 |
| **V5 Tiri in porta** | tiri in porta totali e per squadra, over/under | tiri e tiri in porta fatti e concessi, gol attesi, specialista "Gioco" della V3 | dove il book li quota (circa 11) | V4 |
| **V5 Cartellini** | cartellini totali e per squadra, over/under | scheda dell'arbitro, falli e cartellini delle squadre, derby, posta in palio, severità del campionato | dove il book li quota (circa 16) | previsione semplice e V4 |

**Dati di partenza.** Statistiche per squadra (angoli, cartellini, falli, tiri, tiri in porta, possesso) per circa 24.500 partite in 141 competizioni; gol attesi per circa 15.500; nome dell'arbitro per circa 46.000 partite; storico football-data per i 16 campionati principali; uscite di V2.5, V3 e V4.

**Agente = modello statistico specializzato**, codice deterministico come la V3. Un modello di linguaggio non prevede le partite; può servire più avanti solo per scrivere il ragionamento o leggere notizie.

## 3. Regole fisse per tutti

| Regola | Contenuto |
|---|---|
| Due livelli separati | **Probabilità**: solo dati della partita, mai quote. **Decisione**: le quote entrano solo per decidere se giocare, quando (mattina o vicino al via) e quanto puntare. Un test automatico verifica che nessun ingrediente di probabilità contenga quote |
| Esami prima dei risultati | Un file di preregistrazione per specialista e per esame in `docs/v5/esami/`, committato prima di accendere la misura |
| Due tipi di esame | **Di sviluppo**, sullo storico in ordine di tempo: serve a decidere se mettere lo specialista in prova. **In avanti**, su partite giocate dopo il congelamento: è l'unico che giudica. La stagione 2025/26 può essere dato di allenamento, mai prova |
| Versioni congelate | Ogni versione in prova ha un'impronta di codice e parametri. Cambiare qualcosa = nuova versione, la misura riparte |
| Liste sigillate | Una lista al giorno per specialista, sigillata prima del primo calcio d'inizio; le giocate prese "vicino al via" si sigillano al momento della presa |
| Nessun dato cancellato | Solo tabelle e colonne nuove (`cecchino_v5_*`), migrazioni solo additive |
| Budget API | La V5 intera non supera 200 chiamate al giorno in media; si ferma da sola sopra 6.500 nel giorno |
| Risultati | Profitto a 1 unità, vinte, quota media, sempre con numero di giocate e forbice al 90% |

## 4. Base comune (Fase 0)

Si costruisce una volta e serve a tutti e quattro.

1. **Quote.** Alla lettura del mattino già esistente si aggiunge una lettura **poco prima del calcio d'inizio** (60-15 minuti) per le sole giocate candidate di ogni specialista. I mercati angoli, cartellini e tiri in porta vengono letti dalle quote che Cecchino Today già scarica e oggi non usa.
2. **Tabella unica delle giocate.** Specialista, partita, mercato, linea, quota del mattino, quota pre-partita (stesso bookmaker), esito, ingredienti usati, versione.
3. **Schede arbitri.** Cartellini medi a partita, differenza casa/fuori, numero di partite, costruite dai nomi già presenti nelle partite salvate.
4. **Livello di decisione comune.**
   - Probabilità prudente: la stima viene avvicinata alla media del mercato tanto più quanto più se ne allontana; la forza della correzione si fissa una volta per specialista.
   - Si gioca se probabilità prudente × quota ≥ 1,03.
   - Quando: regola per famiglia finché la Fase "Momento" non la migliora (classici la mattina, statistiche vicino al via).
   - Puntata: 1 unità fissa.
   - Limiti: massimo 15 giocate al giorno per tutta la V5, una per partita per specialista, al massimo 2 per partita in totale, al massimo 2 per campionato per specialista.
5. **Pagina "Misura V5".** Per ogni specialista: giocate, ROI con forbice, CLV, scarto di taratura, confronto con il suo riferimento sugli stessi giorni.

**Esame 0 (tecnico, 14 giorni consecutivi).**
1. Almeno il 90% delle giocate candidate ha quota del mattino e quota pre-partita dello stesso bookmaker.
2. Nessuna lettura dopo il calcio d'inizio.
3. Mercati speciali letti correttamente: 100 quote estratte a caso confrontate con il dato grezzo del bookmaker, nessuna differenza.
4. Media chiamate V5 ≤ 200 al giorno; la scansione del mattino non ritarda oltre 5 minuti.
5. Schede arbitri disponibili per almeno l'80% delle partite candidate dei campionati con cartellini quotati.

Passa se valgono tutte e cinque.

## 5. Gli specialisti

Per ognuno: cosa si costruisce, esame di sviluppo, esame in avanti, esame finale. I numeri minimi di giocate sono diversi perché i campionati quotati sono diversi.

### 5.1 V5 Valore (primo)

**Cosa si costruisce.**
- **Passo 1, selezione onesta:** regole del livello di decisione comune sopra le probabilità V3 (V2.5 dove la V3 non c'è), solo quote 1,80-2,20.
- **Passo 2, modello di probabilità:** impara dagli altri moduli (forza, tiri, forma, calendario V3; segnali V2.5; contesto del campionato). Due candidati dichiarati prima, regressione logistica con regolarizzazione e gradient boosting; se ne sceglie uno sullo sviluppo con la log-loss, poi si congela. Taratura finale.

**Esame di sviluppo (storico in ordine di tempo).** Errore (Brier) del modello più basso della V3 di almeno l'1% sui mercati classici, migliore in almeno 3 stagioni su 4, taratura entro 2 punti per fascia.

**Esame in avanti (minimo 600 giocate e 6 settimane).**
1. Scarto tra probabilità mostrata e vinte reali ≤ 2 punti.
2. CLV medio con limite basso della forbice ≥ −0,5%.
3. Profitto non peggiore di In evidenza V3 + V2.5 sulla stessa fascia di quota di oltre 2 punti.

**Quote sopra 2,20.** Escluse. Si riaprono solo se la V5 Valore è promossa e un esame separato, scritto prima, sulla fascia 2,21-3,00 passa.

### 5.2 V5 Angoli (secondo)

**Cosa si costruisce.** Un modello degli angoli attesi per squadra (fatti e concessi, casa e fuori, ristretti verso la media del campionato quando le partite sono poche), corretto per chi è favorito secondo la base V3, con una distribuzione che regge partite molto aperte o molto chiuse. Probabilità per ogni linea quotata.

**Esame di sviluppo.** Sulle stagioni 2024/25 e 2025/26 in ordine di tempo: log-loss sulle linee più comuni migliore della previsione semplice di almeno il 2% e del motore V4 di almeno l'1%; taratura entro 2 punti.

**Esame in avanti (minimo 400 giocate e 8 settimane).** Taratura ≤ 2 punti; CLV con limite basso ≥ −0,5%; profitto non peggiore della V4 angoli di oltre 2 punti sugli stessi giorni.

### 5.3 V5 Tiri in porta (terzo)

**Cosa si costruisce.** Tiri in porta attesi per squadra da tiri creati e concessi e gol attesi, con lo specialista "Gioco" della V3 come ingrediente. Le formazioni (attaccanti in campo) entrano in una versione successiva, solo per la decisione vicino al via.

**Esame di sviluppo.** Come per gli angoli: log-loss migliore della previsione semplice di almeno il 2% e della V4 di almeno l'1%; taratura entro 2 punti.

**Esame in avanti (minimo 300 giocate e 8 settimane).** Stessi tre criteri degli angoli, confronto con la V4 tiri in porta.

### 5.4 V5 Cartellini (quarto)

**Prerequisito.** Schede arbitri (Esame 0, punto 5).

**Cosa si costruisce.** Cartellini attesi da arbitro, falli e cartellini delle squadre, derby (stessa città o regione), posta in palio (ultime giornate, lotta salvezza o titolo), severità del campionato.

**Esame di sviluppo.** Log-loss migliore della previsione semplice di almeno il 2%; peso dell'arbitro con lo stesso segno in tutte le stagioni; taratura entro 2 punti.

**Esame in avanti (minimo 300 giocate e 8 settimane).** Stessi tre criteri, confronto con la V4 cartellini.

## 6. Momento della giocata (comune, dopo 300 giocate con doppia quota)

Una regola per giocata che decide se prenderla alla quota del mattino o vicino al via, usando la differenza tra probabilità prudente e quota del mattino, la famiglia di mercato, il campionato e le ore al calcio d'inizio.

**Esame (minimo 300 giocate per famiglia).** CLV della regola maggiore sia di "sempre la mattina" sia di "sempre vicino al via", con limite basso della forbice ≥ 0. Se non passa, resta la regola per famiglia della base comune.

## 7. Giudizio finale (per specialista)

- **Durata:** minimo 3 mesi di lista sigillata, massimo 6.
- **Giocate minime:** Valore 1.350, Angoli 900, Tiri in porta e Cartellini 600.
- **Controlli ogni 300 giocate.** Arresto se dopo almeno 600 giocate (300 per Tiri e Cartellini) il limite alto della forbice del ROI è sotto −5%, o scatta l'allarme CUSUM.
- **Promosso** se: ROI ≥ quello del suo riferimento sugli stessi giorni, CLV medio con limite basso > 0, ROI ≥ 0.
- **Profitto dimostrato** solo quando il limite basso della forbice al 90% del ROI è sopra zero (circa 2.700 giocate per un +3% a quota 1,90).
- **Esclusione di un campionato:** dopo almeno 150 giocate dello specialista con limite alto della forbice sotto −10%; rientra solo con una nuova versione.

## 8. Ordine e tempi indicativi

| Passo | Costruzione | Prima lista sigillata | Giudizio non prima di |
|---|---|---|---|
| Base comune | settimane 1-2 | — | Esame 0 a fine settimana 4 |
| V5 Valore | settimane 2-4 | inizio settimana 4 (passo 1) | fine febbraio 2027 |
| V5 Angoli | settimane 4-6 | settimana 7 | fine marzo 2027 |
| V5 Tiri in porta | settimane 6-8 | settimana 9 | metà aprile 2027 |
| V5 Cartellini | settimane 8-10 | settimana 11 | fine aprile 2027 |
| Momento | dopo 300 giocate con doppia quota | — | — |

Perché questo ordine: **Valore** ha la base più solida (V3), copre tutti i campionati e sfrutta subito il vantaggio della quota del mattino; **Angoli** è il mercato speciale quotato nel maggior numero di campionati; **Tiri in porta** ha il segnale storico più forte ma pochi campionati quotati; **Cartellini** richiede prima le schede arbitri.

## 9. Decisioni ancora aperte (con la mia raccomandazione)

| Tema | Raccomandazione |
|---|---|
| Durata della prova | Minimo 3, massimo 6 mesi per specialista, con arresto anticipato |
| Formazioni e assenze | Fuori dalla prima versione; entrano dopo, solo nella decisione vicino al via |
| Puntata a scalini | Solo descrittiva, calcolata sulle stesse giocate; esame separato dopo la promozione |
| Margine della regola di scelta | 1,03 per tutti, mai cambiato in prova; se passano meno di 5 giocate al giorno si allunga la prova, non si abbassa il margine |
| Limiti giornalieri | 15 in totale per la V5, una per partita per specialista, al massimo 2 per partita |
| Fascia di quota della V5 Valore | 1,80-2,20 all'inizio; sopra solo con esame separato |
