# Risultato — strato squadre: rose, formazioni e assenze (v1)

Calcolato il 04/11/2026 sul server (`GET /api/cecchino/v5/squad-exam`, sola lettura) con le regole di `SQUADRE_V1_PREREGISTRAZIONE.md`.

**Sviluppo dichiarato prima dell'esame**: 2023/24 e 2024/25. La 2022/23 è completa, ma la 2021/22 no (628 partite su circa 6.000): la regola chiedeva entrambe, quindi restano fuori.

**Trasparenza**: un primo lancio si è fermato per un errore di programma (`Decimal * float`) prima di produrre qualsiasi numero. Corretto solo quello; nessuna regola né parametro è cambiato.

## Dati

| Stagione | Partite con giocatori | Assenze | Collegate al Lab |
|---|---|---|---|
| 2023/24 | 6.299 | 21.189 | 6.096 |
| 2024/25 | 6.188 | 22.006 | 5.958 |
| 2025/26 (esame) | 6.145 | 25.235 | 5.979 |

Partite d'esame con gli indici calcolabili: 5.504.

## Esame 2025/26

| | A: assenze del mattino | F: formazione ufficiale | V3 senza correzione |
|---|---|---|---|
| Effetto delle proprie assenze sui propri gol (β_att) | −0,33 | −0,25 | |
| Effetto delle assenze dell'avversaria sui propri gol (β_dif) | +0,27 | +0,22 | |
| Differenza di log-loss per partita (positivo = meglio) | −0,00046 | +0,00037 | |
| Forbice al 90% | −0,00085 / −0,00007 | −0,00014 / +0,00088 | |
| Giocate con la regola della mappa | 1.413 | 1.433 | 1.400 |
| Vinte | 47,4% | 48,3% | 47,3% |
| ROI | −6,2% | −4,5% | −6,6% |
| Forbice ROI al 90% | −10,6 / −1,8% | −8,8 / −0,1% | −11,0 / −2,2% |

| Regola | A | F |
|---|---|---|
| 1. Log-loss migliore, forbice sopra zero | **no** (peggiora) | **no** (la forbice comprende lo zero) |
| 2. Le proprie assenze riducono i propri gol | sì | sì |
| 3. ROI migliore della V3 | sì | sì |

**Esito: né A né F passano.** Nessuno specialista "Squadre" entra dal vivo.

## Cosa dice

- **L'effetto esiste ed è nel verso giusto**: quando manca una parte importante della formazione abituale la squadra segna meno e l'avversaria segna di più. Con la formazione ufficiale il ROI sale di 2,1 punti rispetto alla V3.
- **Non basta**: le probabilità non migliorano in modo dimostrabile e tutte e tre le varianti restano in perdita. Il peso dei giocatori calcolato da minuti e voto medio è probabilmente troppo grezzo.
- **Limite del dato A**: non verificato che l'elenco API-Football delle assenze per le stagioni passate contenga solo ciò che era noto prima della partita. Le assenze pesano sopra soglia in appena il 28% delle partite.

## Prossimo passo previsto dalle regole

Una v2 con una nuova preregistrazione: peso del giocatore da minuti e differenza reti con lui in campo. Lo storico per farla c'è già (minuti di 5 stagioni, la 2021/22 si completa da sola).
