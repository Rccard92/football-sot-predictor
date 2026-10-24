# Risultato — mappa dei 16 campionati e modelli dedicati (v1)

Calcolata il 24/10/2026 sul server (`GET /api/cecchino/v5/league-map`, sola lettura) con le regole di `MAPPA_V1_PREREGISTRAZIONE.md`, senza modifiche. 32.407 partite, 31.035 con le probabilità V3. Nota: i "12 mercati" della preregistrazione sono 15 selezioni (1, X, 2; 1X, 12, X2; Over e Under 1,5 · 2,5 · 3,5; 1, X, 2 primo tempo), come elencate lì.

## Famiglia R — regole del campionato

748 regole provate (campionato × mercato × fascia di quota). Candidate (ROI positivo in tutte e 4 le stagioni di sviluppo): **8**.

| Campionato | Mercato | Quote | ROI sviluppo 21/22 · 22/23 · 23/24 · 24/25 | 2025/26 | 2026/27 | Esito |
|---|---|---|---|---|---|---|
| Serie B (I2) | X | 2,50-3,49 | +3,8 · +13,6 · +14,7 · +13,8 (≈300 a stagione) | **+12,5%** (280) | −3,4% (62) | passa, smentita nel 2026/27 |
| Serie B (I2) | Over 1,5 | 1,40-1,69 | +6,4 · +2,7 · +5,4 · +4,8 | +5,2% (113) | n/d | passa |
| Liga (SP1) | 2 | 2,00-2,49 | +13,2 · +14,3 · +11,0 · +16,0 | +4,8% (37) | −18,1% (11) | passa, smentita nel 2026/27 |
| Portogallo (P1) | 2 | 1,40-1,69 | +21,8 · +19,5 · +0,9 · +8,5 | +0,3% (21) | 2 giocate | passa |
| Belgio (B1) | Under 2,5 | 1,70-1,99 | +11,0 · +4,7 · +4,2 · +9,6 | −5,1% (106) | −59,0% (18) | non passa |
| Belgio (B1) | 1 primo tempo | 1,70-1,99 | positivo 4/4 | −23,8% (31) | n/d | non passa |
| Serie A (I1) | 2 primo tempo | 2,00-2,49 | positivo 4/4 | −5,0% (43) | n/d | non passa |
| Olanda (N1) | 2 | 2,50-3,49 | positivo 4/4 | −22,2% (77) | +51,5% (13) | non passa |

Positive nella 2025/26: 4 su 8, esattamente quante ne darebbe il caso (test binomiale p = 0,64). **La famiglia R non è credibile**: per la regola nessuna si accende. Confermate nel 2026/27: 0.

L'eccezione da tenere d'occhio è **Serie B, pareggio a quota 2,50-3,49**: positiva in 5 stagioni su 5 con circa 300 giocate a stagione (circa +11,7% in media), poi −3,4% sulle prime 62 giocate del 2026/27, che sono ancora poche per smentirla.

## Famiglia M — modello dedicato per campionato

| Campionato | Dedicato sviluppo | Dedicato 2025/26 | Comune 2025/26 | Log-loss 2025/26 dedicato / comune | Esito |
|---|---|---|---|---|---|
| Bundesliga 2 (D2) | −0,8% (430) | **+5,5%** (128) | −3,7% | 0,6089 / 0,6099 | non passa (sviluppo negativo) |
| Serie A (I1) | −10,6% | −1,1% | +1,3% | 0,5978 / 0,5994 | non passa |
| Liga (SP1) | −13,0% | −1,0% | +1,7% | 0,5820 / 0,5820 | non passa |
| Ligue 1 (F1) | −14,4% | −4,1% | +1,2% | 0,6064 / 0,6059 | non passa |
| Premier (E0) | −8,4% | −3,3% | −1,2% | 0,6033 / 0,6033 | non passa |
| gli altri 11 | da −1,1% a −14,4% | da −2,4% a −21,9% | | | non passano |

Campionati positivi nella 2025/26: 1 su 16. **La famiglia M non è credibile e nessun campionato passa.** Ritarare il modello comune su un singolo campionato non cambia quasi niente: le probabilità migliorano di pochissimo (log-loss più basso in 9 campionati su 16) e il profitto resta negativo.

## Schede dei campionati (descrittive)

| Campionato | 1 / X / 2 (%) | Gol | Over 2,5 | Tiri in porta | Angoli | Cartellini |
|---|---|---|---|---|---|---|
| Premier (E0) | 44,5 / 23,0 / 32,4 | 2,97 | 57,0% | 9,2 | 10,4 | 4,0 |
| Championship (E1) | 44,0 / 26,0 / 30,0 | 2,52 | 46,8% | 7,9 | 10,2 | 4,0 |
| League One (E2) | 43,5 / 25,0 / 31,5 | 2,61 | 49,0% | 8,1 | 10,1 | 4,0 |
| League Two (E3) | 42,6 / 27,2 / 30,2 | 2,57 | 47,1% | 8,0 | 9,8 | 4,0 |
| Serie A (I1) | 40,7 / 27,5 / 31,8 | 2,65 | 49,7% | 8,4 | 9,5 | 4,7 |
| Serie B (I2) | 39,3 / **32,2** / 28,4 | 2,45 | 44,2% | 8,1 | 9,6 | 5,6 |
| Liga (SP1) | 44,9 / 26,6 / 28,5 | 2,57 | 46,7% | 8,3 | 9,5 | 5,4 |
| Segunda (SP2) | 45,2 / 30,3 / 24,5 | 2,31 | 41,2% | 7,8 | 9,3 | 5,3 |
| Bundesliga (D1) | 44,1 / 25,0 / 30,9 | 3,16 | 60,3% | 9,6 | 9,7 | 4,2 |
| Bundesliga 2 (D2) | 42,9 / 25,8 / 31,3 | 2,99 | 59,4% | 9,5 | 10,2 | 4,7 |
| Ligue 1 (F1) | 42,9 / 24,6 / 32,6 | 2,82 | 53,7% | 9,0 | 9,5 | 4,2 |
| Ligue 2 (F2) | 43,3 / 27,0 / 29,7 | 2,43 | 44,7% | 8,0 | 9,1 | 4,1 |
| Eredivisie (N1) | 44,1 / 23,7 / 32,2 | 3,04 | 58,4% | 9,6 | 10,2 | 3,2 |
| Portogallo (P1) | 43,8 / 24,2 / 32,0 | 2,64 | 50,2% | 8,4 | 10,0 | 6,0 |
| Belgio (B1) | 43,6 / 24,8 / 31,6 | 2,89 | 54,9% | 9,1 | 10,1 | 4,5 |
| Turchia (T1) | 46,5 / 23,8 / 29,6 | 2,89 | 55,5% | 9,0 | 9,6 | 4,9 |

Sviluppo 2021/22-2024/25; cartellini = gialli + 2 × rossi.

### Dove la realtà si scosta dai prezzi nello stesso verso in entrambi i periodi

Frequenza reale meno probabilità prezzata da Bet365 senza margine, in punti, sviluppo e 2025/26 (oltre 1,5 punti in entrambi). È **descrittivo e non deciso prima**: indica dove guardare, non dove giocare. Per guadagnare lo scarto deve superare il margine del book.

| Campionato | Mercato | Sviluppo | 2025/26 |
|---|---|---|---|
| Bundesliga (D1) | Over 1,5 | +4,2 | +3,5 |
| Bundesliga (D1) | Over 3,5 | +2,5 | +3,2 |
| Serie B (I2) | X | +3,7 | +2,8 |
| Serie B (I2) | Over 1,5 | +1,8 | +4,9 |
| Premier (E0) | Over 1,5 | +2,7 | +2,1 |
| Serie A (I1) | Under 3,5 | +2,6 | +3,8 |
| Serie A (I1) | 1 | −2,3 | −3,2 |
| Championship (E1) | Under 3,5 | +3,3 | +3,1 |
| Liga (SP1) | Under 3,5 | +2,5 | +3,9 |
| Turchia (T1) | Under 3,5 | +3,5 | +7,1 |
| Belgio (B1) | Under 3,5 | +1,8 | +6,5 |
| Bundesliga 2 (D2) | Under 3,5 | +2,1 | +5,4 |

## Conclusione

- Con le regole fissate prima, **nessun modello dedicato e nessuna regola di campionato si accende**: le famiglie R e M non superano il caso.
- La mappa resta come scheda dei 16 campionati.
- Le piste vere sono poche e precise: pareggio in Serie B a quota alta; Under 3,5 in Serie A, Championship, Liga, Turchia, Belgio e Bundesliga 2; Over 1,5 in Bundesliga, Premier e Serie B. Si possono provare solo **in avanti**, con le quote dal vivo che la V4 registra già sui 16 campionati (anche Over/Under 1,5 e 3,5 e doppia chance), in osservazione e con regole scritte prima.
