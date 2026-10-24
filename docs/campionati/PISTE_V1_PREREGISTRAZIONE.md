# Preregistrazione — piste dei campionati in osservazione dal vivo (v1)

Scritta il 24/10/2026, prima della prima giocata. Origine: `MAPPA_V1_RISULTATO.md` (scostamenti stabili tra frequenza reale e prezzo, e la regola Serie B). Le famiglie della mappa non hanno passato l'esame: queste piste si misurano **solo in avanti**, in osservazione (non consigliate).

## Piste

Frequenza di riferimento = frequenza reale 2021/22-2025/26 nel campionato (32.000 partite del Lab). Quota minima = 100 / frequenza: sotto, la giocata perderebbe anche se la frequenza restasse quella storica.

| Specialista V5 | Campionati | Mercato | Frequenza di riferimento | Si gioca se la quota Bet365 è |
|---|---|---|---|---|
| `camp_pareggio_i2` | Serie B | X | 32,1% (pareggi di tutta la Serie B) | tra 2,50 e 3,49 (regola R della mappa) |
| `camp_under35` | Serie A | Under 3,5 | 73,7% | ≥ 1,36 |
| | Championship | Under 3,5 | 75,9% | ≥ 1,32 |
| | Liga | Under 3,5 | 75,2% | ≥ 1,33 |
| | Turchia | Under 3,5 | 69,3% | ≥ 1,45 |
| | Belgio | Under 3,5 | 68,1% | ≥ 1,47 |
| | Bundesliga 2 | Under 3,5 | 66,3% | ≥ 1,51 |
| `camp_over15` | Bundesliga | Over 1,5 | 83,6% | ≥ 1,20 |
| | Premier | Over 1,5 | 79,9% | ≥ 1,26 |
| | Serie B | Over 1,5 | 72,4% | ≥ 1,39 |

## Come si gioca

- Partite dei 16 campionati registrate dalla V4, solo del giorno, non ancora iniziate, dalle 08:00 (stessa regola delle liste V5).
- Quota: **solo Bet365** (come lo storico), l'ultima istantanea del giorno della partita. Senza quota Bet365, niente giocata.
- Una giocata per partita per pista, puntata 1 unità, lista sigillata. Nessun massimo giornaliero.
- Esito, quota di chiusura Bet365 e CLV come per gli altri specialisti V5.

## Quando si decide

- Osservazione dal 25/10/2026 a fine stagione 2026/27, visibile ogni giorno nel Confronto motori.
- **Fermata** in anticipo una pista con ROI sotto −15% dopo almeno 80 giocate.
- **Promossa a consigliata** una pista con almeno 150 giocate, ROI > 0 e CLV medio ≥ 0. Decidono l'utente e Giovanni.
- Le soglie non si cambiano durante l'osservazione: una pista diversa è una nuova versione e riparte da zero.
