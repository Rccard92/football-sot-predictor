# Preregistrazione — V5 Valore v1

Scritta il 22/10/2026 **prima** di calcolare qualsiasi risultato sulla stagione 2025/26. Le regole sotto non si cambiano dopo aver visto i numeri; una regola diversa è una nuova versione con una nuova preregistrazione.

## Dati

- Probabilità di partenza: V3 "finale" (run 11 di `cecchino_v3_runs`, motore Fase 4, identico al riferimento #5), calcolate in ordine di tempo per ogni partita dei 16 campionati, 2021/22-2025/26, 17 mercati.
- Quote: Bet365 da `cecchino_lab_matches`. Quota di gioco = quota "pre" (raccolta prima del giorno della partita, la più vicina alla quota del mattino); per 1X2 e over/under 2,5 si riporta anche il risultato alla quota di chiusura.
- Partite: solo `eval_eligible` della V3 (entrambe le squadre con abbastanza partite nella stagione).
- Sviluppo: 2021/22-2024/25. Esame: 2025/26, usata una sola volta.

## Modello

1. **Taratura.** Per ogni mercato, le probabilità V3 delle stagioni di sviluppo si dividono in fasce larghe 5 punti. In ogni fascia: frequenza reale con lisciatura verso il centro della fascia (peso 50 partite). Probabilità tarata = valore della fascia in cui cade la probabilità V3.
2. **Probabilità prudente** = probabilità tarata − 1 errore standard della fascia: √(p(1−p)/(n+50)).
3. Nessuna quota entra nel calcolo delle probabilità.

## Regola di gioco (livello di decisione)

- Mercati: 1, X, 2, 1X, 12, X2, over/under 1,5-2,5-3,5, 1-X-2 primo tempo.
- Quota pre tra 1,80 e 2,20 compresi.
- Si gioca se probabilità prudente × quota ≥ 1,03.
- Una giocata per partita (la più alta per probabilità prudente × quota), massimo 15 al giorno (le più alte), puntata 1 unità.

## Esame sulla 2025/26 — passa se valgono tutte e quattro

1. Almeno 300 giocate.
2. ROI alla quota pre ≥ 0.
3. ROI almeno 5 punti sopra il "caso": tutte le giocate possibili della 2025/26 negli stessi mercati e nella stessa fascia 1,80-2,20, una per partita scelta a caso (media su tutte).
4. Scarto tra probabilità tarata media e vinte reali ≤ 2 punti.

Si riportano sempre: giocate, vinte, quota media, ROI con forbice al 90%, ROI alla chiusura dove esiste, risultato per mercato e per campionato (solo descrittivo).

## Se non passa

La V5 Valore v1 non va in lista sigillata. Si dice con i numeri e si passa allo specialista successivo; una v2 richiede una nuova preregistrazione e non può usare la 2025/26 come esame.
