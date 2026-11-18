# Prova storica V5 Valore sull'Under 2,5 — 18/11/2026

Richiesta di Giovanni del 17/11/2026, regole decise il 18/11 **prima** di guardare i risultati e non cambiate dopo.
Nessun motore in produzione è stato toccato. Codice: `backend/app/services/cecchino_v5/valore_u25_exam.py`
(`GET /api/cecchino/v5/valore-u25-exam?start=true`). Giocate una per una: `VALORE_U25_PROVA_2026_11_18.csv`
(separatore `;`), tutto il risultato: `VALORE_U25_PROVA_2026_11_18.json`.

## Domanda 1: la 2025/26 è stata usata per costruire V5?

**Per costruirla o tararla no**: la taratura di V5 Valore (versione `v5_live_v1_20261022`) è stimata sulle stagioni
2021/22-2024/25. **Però la 2025/26 è già stata usata come esame**, due volte: per il V3 il 13/09 e per Valore v1 il
22/10 (dove l'Under 2,5 aveva già dato 338 giocate a −12,5% con una regola diversa). Per questo, come deciso:
**il verdetto lo dà la 2026/27** (mai usata), la 2025/26 vale solo come conferma.

## Regole (congelate)

- Dati: laboratorio, 16 campionati, gare con quota Bet365 Under/Over 2,5 prima della gara; entrambe le squadre con
  almeno 5 gare in stagione (idoneità del V3).
- Modello: probabilità V3 "finale" con i parametri del run 11, gare in ordine di data, ognuna solo con le gare
  precedenti; taratura per fasce di 5 punti; **probabilità prudente** = tarata − 1 errore standard.
  Per la 2026/27 le probabilità si ricalcolano con lo stesso codice del V3 dal vivo. Controllo: ricalcolate sulla
  2025/26 coincidono con quelle salvate del run 11 (5.290 gare, scarto 0).
- Regola: Under 2,5 se probabilità prudente × quota Bet365 pre − 1 è tra 10% e 30%, quota tra 1,80 e 2,20
  (fascia del protocollo V5). 1 unità a giocata.
- CLV = quota presa × probabilità di chiusura senza margine − 1 (Bet365 e Pinnacle).

## Risultato

| | 2026/27 (verdetto) | 2025/26 (conferma) |
|---|---|---|
| Giocate / giornate | 29 / 11 | 89 / 65 |
| Vinte | **31,0%** | **41,6%** |
| Probabilità prudente media | 55,6% | 54,8% |
| Quota media | 2,03 | 2,05 |
| ROI alla quota pre-gara | **−37,6%** | **−15,0%** |
| IC95 del ROI (bootstrap per giornata) | −66,3% / −12,9% | −36,4% / +6,3% |
| ROI alla quota di chiusura | −41,1% | −17,3% |
| CLV Bet365 medio (positivi) | −1,6% (31%) | −2,4% (30%) |
| CLV Pinnacle medio (positivi) | n.d. (il CSV 2026/27 non ha Pinnacle O/U) | −4,2% (22%) su 32 |

Confronto:

| | 2026/27 | 2025/26 |
|---|---|---|
| Tutti gli Under 2,5 senza filtro | 573 giocate, ROI −5,8% | 5.287 giocate, ROI −8,1% |
| Valore oltre il 30% (fuori dalla fascia 1,80-2,20) | 11 giocate, ROI −67,3% | 13 giocate, ROI +34,1% (campione minimo) |

Nella fascia 1,80-2,20 nessuna giocata ha valore oltre il 30%.

## Lettura

1. **V5 Valore sull'Under 2,5 non ha valore vero.** Nelle gare scelte V5 dice in media 55% e ne escono il 31%
   (2026/27) e il 42% (2025/26): la regola sceglie proprio le gare in cui il modello sopravvaluta l'Under. Le giocate
   scelte fanno peggio di tutti gli Under senza filtro, in tutte e due le stagioni.
2. Il CLV è negativo: il mercato si muove contro la nostra scelta, quindi non è sfortuna dei risultati.
3. Per mese, campionato e fascia di valore non c'è una zona che si salvi con numeri seri (vedi JSON).
4. **Limite**: la 2026/27 del laboratorio arriva al 21/10 (gli ultimi CSV di football-data importati). Con i CSV
   aggiornati la prova si rilancia uguale; con −37,6% e un intervallo tutto sotto zero è improbabile che cambi verso.
