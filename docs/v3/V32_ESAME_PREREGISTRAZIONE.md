# Preregistrazione — V3.2 (correzioni dei gol) sulla stagione 2025 fuori dai 16 campionati

Scritta il 24/10/2026, prima di calcolare qualunque numero sulla stagione 2025. Diagnosi di partenza: `DIAGNOSI_V25_V3_LIVE.md`. Il risultato va in `V32_ESAME_RISULTATO.md`; questo file non si cambia dopo il calcolo.

## Cosa si prova

Due correzioni ai gol attesi della V3 estesa (motore dal vivo, parametri congelati della run 11), nessuna quota nel calcolo:

- **A — livello dei gol del campionato.** Per ogni partita, fattore R calcolato solo sulle partite del campionato già finite prima del giorno della partita, nella stessa stagione:
  R = (gol reali + K · g) / (gol attesi + K · g), con g = media dei gol attesi di quelle partite (R = 1 se non ce ne sono), limitato tra 0,75 e 1,33. I gol attesi di casa e ospite si moltiplicano per R.
- **B — forma della distribuzione.** Correzione dei risultati bassi (ρ di Dixon-Coles) come stimata dal motore, oppure ρ = 0 (gol di casa e ospite indipendenti).

Candidati: K ∈ {spento, 20, 50, 100} partite × ρ ∈ {stimato, 0}: 8 combinazioni. "Spento + ρ stimato" è la V3 attuale.

## Dati

- Campionati API-Football con stagione 2025, esclusi i 16 campionati principali, dove la V3 estesa si calcola (almeno 30 partite della stagione con tiri e tiri in porta, come dal vivo).
- Previsioni walk-forward del motore V3 estesa (stessa funzione usata dal vivo), una sola volta per campionato; le combinazioni cambiano solo il passo finale (fattore R e ρ).
- Partite valutate: finite, della stagione 2025, con previsione e con il marchio `eval_eligible` del motore (fuori dalle prime giornate, regola del Lab).
- **Sviluppo**: campionati con id API-Football pari. **Verifica**: id dispari. La divisione è fissata qui, prima di vedere i dati.

## Misure

- **Principale**: log-loss medio dei tre Over/Under (1,5 · 2,5 · 3,5) per partita.
- Secondaria: log-loss 1X2 (tre esiti).
- Taratura: Over 2,5 previsto medio contro reale.

## Scelta (solo sullo sviluppo)

Si sceglie la combinazione con il log-loss principale più basso tra quelle il cui log-loss 1X2 non peggiora di più di 0,002 rispetto alla V3 attuale.

## Esame (solo sulla verifica, una volta)

La combinazione scelta passa se tutte e tre:
1. migliora il log-loss principale rispetto alla V3 attuale, con la forbice al 90% della differenza per partita tutta sopra zero;
2. il log-loss 1X2 non peggiora di più di 0,002;
3. lo scarto di taratura dell'Over 2,5 è al massimo 1,5 punti ed è più piccolo di quello della V3 attuale.

Se la scelta sullo sviluppo è la V3 attuale, o l'esame non passa, A e B restano spente.

## V3.2 dal vivo e osservazione

- La V3.2 si registra dal vivo accanto alla V3 su ogni partita dove si calcola la V3: con A e B se l'esame passa, altrimenti con le probabilità della V3.
- **C — In evidenza V3.2**: tra 1, X, 2 finali e Over/Under 1,5-2,5-3,5, quota Bet365 tra 1,41 e 2,20 e non sotto la quota minima (1 / probabilità), la più probabile. Niente doppia chance, niente primo tempo.
- **D — V2.5 senza doppione**: la giocata in evidenza della V2.5 si misura a parte solo sulle partite senza V3.
- Osservazione nel Confronto motori per 4 settimane dal 26/10/2026 al 22/11/2026, accanto a V2.5 e V3 in evidenza attuali (che non cambiano). Poi decidono l'utente e Giovanni.

## Limiti dichiarati

- Un solo anno (2025) e solo i campionati con statistiche di tiro (gli altri non hanno la V3).
- Le partite dello stesso campionato e giorno non sono indipendenti: la forbice per partita è un po' ottimista.
- Le correzioni migliorano le probabilità; non creano da sole un vantaggio sul book (diagnosi, punto 1).
