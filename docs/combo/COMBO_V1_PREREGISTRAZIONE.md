# Preregistrazione — combo sulla stessa partita (v1)

Scritta il 24/10/2026, prima di calcolare qualunque numero delle combo. Il risultato va in `COMBO_V1_RISULTATO.md`; questo file non si cambia dopo il calcolo.

## Idea

Due o tre giocate "semplici" della stessa partita, tutte nella stessa direzione (stesso scenario di gara), arrivano insieme a una quota intorno a 2. Le giocate legate escono insieme più spesso del semplice prodotto delle probabilità: il modello deve stimare bene questa probabilità congiunta. Mai giocate opposte o a forbice (es. Over 1,5 + Under 3,5).

## Scenari (giocate ammesse, tutte coerenti tra loro)

| Scenario | Giocate |
|---|---|
| **Partita aperta** | Over gol totali · Over tiri in porta totali · Over angoli totali |
| **Partita chiusa** | Under gol totali · Under tiri in porta totali · Under angoli totali |
| **Dominio casa** | 1X · Over tiri in porta casa · Over angoli casa · Under tiri in porta ospite |
| **Dominio ospite** | X2 · Over tiri in porta ospite · Over angoli ospite · Under tiri in porta casa |

- Una combo usa 2 o 3 giocate dello stesso scenario, al massimo una per statistica e lato.
- Linea di ogni giocata: la più impegnativa con probabilità del modello almeno 65%, tra le linee quotate dal vivo (gol 1,5-3,5; tiri in porta e angoli entro le linee valide della V5).
- Cartellini esclusi dalla v1 (nessuno scenario coerente chiaro).

## Modello

- Attese per partita, solo con dati precedenti (walk-forward): gol di casa e ospite dalla V3 (run 11); tiri in porta e angoli di casa e ospite dal modello della V5 (esame del 22/10).
- Distribuzioni: gol Poisson; tiri in porta e angoli binomiale negativa con le dispersioni dell'esame V5.
- **Legami tra le statistiche**: copula gaussiana su sei variabili (gol, tiri in porta, angoli; casa e ospite), con correlazioni stimate solo sullo sviluppo dai residui (posizione del valore reale nella distribuzione prevista). La probabilità della combo si calcola simulando 2.000 partite per incontro.
- Confronto: **modello indipendente** (prodotto delle probabilità delle giocate).

## Dati e stagioni

16 campionati del Lab. **Sviluppo** 2022/23-2024/25 (la 2021/22 serve da storico per le attese). **Esame** 2025/26. **Controllo** 2026/27 fino ad oggi, solo combo senza giocate sui gol (le probabilità V3 della run 11 si fermano alla 2025/26).

## Combo scelta per partita

Tra le combo della partita con quota equa (1 / probabilità) tra 1,90 e 2,60, quella con la probabilità più alta. Una combo per partita.

## Esame (2025/26)

La v1 **passa** se tutte e due:
1. sulle combo scelte, la frequenza reale è entro 2,5 punti dalla probabilità media prevista;
2. su tutte le combo candidate, il Brier della copula è più basso di quello del modello indipendente.

Si riportano anche: taratura per scenario, frequenza reale delle combo scelte (e quindi la quota di pareggio, 100 / frequenza), numero di combo per giornata.

## Profitto: cosa si può e non si può misurare

Lo storico non ha le quote delle combo (né di tiri in porta e angoli). Il risultato dice quanto spesso escono le combo scelte e quindi **sopra quale quota guadagnano**: 1,05 / probabilità è la quota minima consigliata. Dal vivo la lista mostra la quota minima; il confronto con la quota MyCombo di Sisal lo fa l'utente, finché non avremo esempi reali di prezzi MyCombo per misurare la riduzione che applica Sisal.

## Dopo l'esame

Se passa: lista sigillata "Combo" nella V5, in osservazione, sulle partite dei 16 campionati, con quota minima per ogni combo; si misurano frequenza reale contro probabilità e, dove la V4 ha le quote delle singole giocate, il prodotto delle quote Bet365/Betfair come riferimento. Se non passa: nessuna lista, si corregge il modello con una nuova versione e un nuovo esame.
