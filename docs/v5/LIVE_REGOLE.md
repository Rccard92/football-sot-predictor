# V5 dal vivo — regole v1

Fissate il 22/10/2026, prima della prima lista. Cambiarle vuol dire una nuova versione e la misura riparte.

## Dove gira

- I 16 campionati della V4, partite non ancora iniziate.
- Dati delle squadre: storico football-data del Lab (`cecchino_lab_matches`, stagione in corso aggiornata a mano 1-2 volte a settimana). Gol attesi: motore gol della V4 (V3 Fase 4).
- Quote: istantanee Bet365 e Betfair registrate dalla V4 (mattina, pomeriggio). Per ogni linea si usa la quota migliore tra i due book, e si tiene il book scelto.
- Le liste si costruiscono nei job della V4 (08:00, 12:00, 16:00 ora di Roma e ogni 15 minuti prima delle partite), solo con le partite del giorno: la prima lista esce alle 08:00 con le quote del mattino. Una giocata pubblicata non cambia più (lista sigillata), si aggiungono solo partite nuove prima del calcio d'inizio, finché c'è posto nel massimo giornaliero.
- Confronto con tutti gli altri motori ogni giorno nella pagina "Confronto motori" (`/confronto-motori`).

## Specialisti

| Specialista | Stato | Modello (dall'esame) | Mercati |
|---|---|---|---|
| Tiri in porta v1 | **consigliato** (esame passato) | k = 20, γ = 0,25, dispersione squadra 32,31 / totale 87,64 | tiri in porta totale e per squadra, over e under |
| Angoli v1 | osservazione | k = 20, γ = 0,15, dispersione 12,51 / 67,27 | angoli totale e per squadra |
| Cartellini v1 | osservazione | k = 20, δ = 0,5 (arbitro), dispersione 22,76 / 16,13; cartellini = gialli + 2 × rossi | cartellini totale e per squadra |
| Valore v1 | osservazione (esame fallito) | taratura per fasce della V3 (sviluppo 2021/22-2024/25), probabilità prudente = tarata − 1 errore standard | 1X2, doppia chance, over/under 1,5-3,5, primo tempo, quota 1,80-2,20 |

## Regola di decisione

- Specialisti statistici: probabilità prudente = 0,5 + 0,8 × (probabilità − 0,5); quota tra 1,50 e 3,00; si gioca se probabilità prudente × quota ≥ 1,03. Una giocata per partita (la più alta per probabilità prudente × quota), massimo 5 al giorno per specialista.
- Valore: regola della preregistrazione (fascia 1,80-2,20, ≥ 1,03, una per partita, massimo 15 al giorno).
- Puntata 1 unità.

## Misura

- Esito con il regolamento della V4 sulle statistiche post-partita di API-Football.
- CLV = quota presa / quota di chiusura dello stesso book − 1, quando la chiusura esiste.
- Le giocate in osservazione si misurano come quelle consigliate, ma nella pagina sono marcate "non consigliata".
