# Preregistrazione — ricerca ampia dei pattern con contesto di partita (v1)

Scritta il 24/10/2026, prima di calcolare qualunque numero. Il risultato va in `PATTERN_V1_RISULTATO.md`; questo file non si cambia dopo il calcolo.

## Cosa cambia rispetto ai pattern del Lab

I pattern del Lab erano costruiti su quote e classi del Cecchino. Qui ogni pattern è **campionato × mercato × fascia di quota × fino a due condizioni di contesto della partita**, calcolate solo con le partite precedenti dello stesso campionato e stagione. Si provano tutti i 16 campionati e tutti i mercati con quota, senza partire da esempi.

## Contesto della partita (9 caratteristiche, 3 livelli ciascuna)

Ultime 5 partite di campionato della squadra (qualsiasi campo), almeno 3 giocate prima della partita, altrimenti la caratteristica non è definita:

| # | Caratteristica | Livelli |
|---|---|---|
| F1 / F2 | Forma casa / ospite: punti a partita | < 1,0 · 1,0-1,8 · > 1,8 |
| F3 / F4 | Attacco casa / ospite: gol fatti a partita rispetto alla media del campionato per squadra | < 0,8× · 0,8-1,2× · > 1,2× |
| F5 / F6 | Difesa casa / ospite: gol subiti a partita rispetto alla media | < 0,8× · 0,8-1,2× · > 1,2× |
| F7 | Dominio nei tiri in porta: (tiri in porta fatti − subiti) casa meno lo stesso per l'ospite | < −2 · −2 / +2 · > +2 |
| F8 | Distanza in classifica: punti a partita in stagione casa − ospite | < −0,5 · −0,5 / +0,5 · > +0,5 |
| F9 | Fase della stagione: agosto-ottobre · novembre-marzo · aprile-giugno | |

Condizioni: ognuna delle 27 singole e tutte le coppie di caratteristiche diverse (324), più il pattern senza condizioni: 352 per base.

## Basi

16 campionati × 15 selezioni con quota (1, X, 2; 1X, 12, X2; Over e Under 1,5 · 2,5 · 3,5; 1, X, 2 primo tempo) × 4 fasce di quota Bet365 (1,40-1,69 · 1,70-1,99 · 2,00-2,49 · 2,50-3,49).

## Regole

- Stagioni: **sviluppo** 2021/22-2024/25, **esame** 2025/26, **controllo** 2026/27 fino ad oggi (solo 1X2 e Over/Under 2,5).
- **Candidato**: ROI > 0 in tutte e 4 le stagioni di sviluppo, almeno 20 giocate in ognuna.
- **Passa**: ROI > 0 nella 2025/26 con almeno 20 giocate. **Confermato**: passa e ROI > 0 nel 2026/27 (almeno 10 giocate) dove ci sono le quote.
- Pattern quasi uguali contano una volta sola: tra candidati con la stessa base e le stesse partite per oltre l'80%, resta quello con più giocate nello sviluppo.
- **La famiglia è credibile** solo se i candidati positivi nella 2025/26 sono significativamente più della metà (binomiale a una coda, p < 0,05). Altrimenti nessun pattern si accende, nemmeno quelli che passano.

## Dopo

- Se credibile: i pattern confermati (o passati, dove il 2026/27 non ha quote) vanno in osservazione dal vivo nella lista V5 (specialista "Pattern"), 4 settimane o 100 giocate.
- Se non credibile: si riporta il risultato e nessun pattern si accende.

## Limiti dichiarati

- Moltissime prove (circa 337.000 pattern): per questo contano il test di famiglia e la conferma 2026/27, non il singolo pattern.
- La 2025/26 è stata vista in modo aggregato in analisi precedenti, mai con queste condizioni.
- Mancano ancora formazioni e assenze (lo storico si sta scaricando): verranno provate in una versione successiva.
