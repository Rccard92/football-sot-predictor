# Risultato — strato squadre v2: valore del giocatore dalla differenza reti

Calcolato il 06/11/2026 sul server (`GET /api/cecchino/v5/squad-exam-v2`, sola lettura) con le regole di `SQUADRE_V2_PREREGISTRAZIONE.md`, senza modifiche. Partite collegate: 2022/23 6.120, 2023/24 6.096, 2024/25 5.958, 2025/26 5.979 (esame).

## Scelta di λ (sviluppo)

| λ | 10 | **30** | 100 | 300 |
|---|---|---|---|---|
| Correlazione forza titolari / residuo nel 2024/25 | 0,027 | **0,029** | 0,027 | 0,022 |

Scelto λ = 30. Anche il migliore spiega pochissimo: la differenza reti di una partita, divisa tra 22 giocatori, è quasi tutta rumore. Giocatori con un valore nell'esame: 13.397.

## Esame 2025/26

| | A: assenze del mattino | F: formazione ufficiale | V3 senza correzione |
|---|---|---|---|
| a (effetto della propria formazione) | −0,016 | +0,0004 | |
| b (effetto della formazione avversaria) | −0,021 | −0,074 | |
| Differenza di log-loss per partita | −0,000001 (−0,00004 / +0,00004) | −0,00011 (−0,00037 / +0,00015) | |
| Giocate | 1.395 | 1.441 | 1.396 |
| ROI | −6,7% (−11,1 / −2,2) | −6,7% (−11,1 / −2,4) | −6,6% (−11,0 / −2,2) |

| Regola | A | F |
|---|---|---|
| 1. Log-loss migliore, forbice sopra zero | no | no |
| 2. Formazione più forte → più gol | no | sì (ma a ≈ 0) |
| 3. ROI migliore della V3 | no | no |

**Esito: né A né F passano.** La v2 fa peggio della v1: con questo metodo il valore dei giocatori non aggiunge niente ai gol attesi della V3.

## Cosa dice

- Con i soli minuti, senza sapere quando si segna e quando un giocatore entra o esce, non si riesce a separare il contributo dei singoli dal risultato della squadra.
- La V3 contiene già la forza della squadra; scostarsi dalla formazione abituale, misurato così, non cambia le probabilità.
- La v1 (peso da minuti e voto) aveva almeno l'effetto nel verso giusto e +2,1 punti di ROI con la formazione ufficiale, senza superare l'esame.

## Come da regole

Lo strato squadre si ferma qui. L'unica strada rimasta è una v3 con la differenza reti esatta minuto per minuto: servono gli eventi (gol e cambi) di circa 30.000 partite, una chiamata ciascuna, cioè due settimane di scarico con lo stesso limite giornaliero.
