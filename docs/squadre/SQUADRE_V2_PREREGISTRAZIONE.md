# Preregistrazione — strato squadre v2: valore del giocatore dalla differenza reti

Scritta il 06/11/2026, prima di calcolare qualunque numero della v2. Origine: la v1 (`SQUADRE_V1_RISULTATO.md`) ha mostrato l'effetto nel verso giusto ma troppo debole, con un peso del giocatore grezzo (minuti × voto). Il risultato va in `SQUADRE_V2_RISULTATO.md`; questo file non si cambia dopo il calcolo.

## Dati disponibili e scelta del metodo

Per le stagioni passate ci sono minuti e titolari di ogni giocatore (circa 250.000 righe a stagione), ma non gli eventi minuto per minuto (gol e cambi): la differenza reti esatta "con lui in campo" non si può calcolare. Si usa il **plus-minus regolarizzato per partita**, il metodo standard quando mancano gli eventi.

## Valore del giocatore

- Per ogni partita: **residuo** = (gol casa − gol ospite) − (gol attesi casa − gol attesi ospite) della V3 (run 11), cioè quanto la partita è andata meglio o peggio del previsto.
- Ogni giocatore che ha giocato entra con l'esposizione minuti / 90, positiva per la casa e negativa per l'ospite.
- Valori dei giocatori stimati con una regressione ridge (tutti spinti verso zero con peso λ): un giocatore con poche partite resta vicino a zero.
- **Scelta di λ** tra 10, 30, 100 e 300: si stima sulle stagioni 2022/23-2023/24 e si sceglie il λ con la correlazione più alta tra la forza della formazione titolare e il residuo nella 2024/25.

## Indici della partita (per squadra)

- **Forza della formazione** = somma dei valori dei giocatori considerati.
- **F, formazione ufficiale**: forza dei titolari meno la forza media delle formazioni titolari della squadra nelle ultime 10 partite della stessa stagione (almeno 3).
- **A, assenze del mattino**: meno la somma dei valori dei giocatori della formazione abituale (gli 11 con più minuti nelle ultime 10 partite) presenti nell'elenco assenze della partita ("Missing Fixture").

## Correzione dei gol

log λ casa = log λ V3 + a · indice casa + b · indice ospite (e simmetrico per l'ospite), stimati per verosimiglianza di Poisson con penalità leggera.

- **Sviluppo**: valori dei giocatori stimati sul 2022/23-2023/24, a e b stimati sul 2024/25.
- **Esame**: valori dei giocatori stimati sul 2022/23-2024/25, stessi a e b, applicati alla 2025/26. I giocatori senza storico valgono zero.

## Esame (2025/26), separato per A e per F

Passa se tutte e tre (come la v1):
1. il log-loss medio di 1X2 e Over/Under 2,5 migliora rispetto alla V3, con la forbice al 90% della differenza per partita sopra zero;
2. a > 0 nello sviluppo: formazione più forte del solito → più gol;
3. con la regola di gioco della mappa (quota 1,50-2,50, probabilità × quota ≥ 1,05, una per partita) il ROI nella 2025/26 è migliore di quello della V3 senza correzione.

## Dopo

Se A o F passano: specialista "Squadre" in osservazione dal vivo (A al mattino, F dopo le formazioni ufficiali). Se non passano: lo strato squadre si ferma qui, salvo scaricare gli eventi minuto per minuto (circa 30.000 chiamate, due settimane) per una v3 con la differenza reti esatta.
