# Risultato — ricerca ampia dei pattern con contesto di partita (v1)

Calcolata il 24/10/2026 sul server (`GET /api/cecchino/v5/pattern-search`, sola lettura, circa 1 minuto) con le regole di `PATTERN_V1_PREREGISTRAZIONE.md`, senza modifiche.

## Numeri

| | |
|---|---|
| Partite | 32.407 (16 campionati, 2021/22-2026/27) |
| Basi (campionato × mercato × fascia di quota con partite) | 748 |
| Pattern provati | **263.296** |
| Candidati (profitto in tutte e 4 le stagioni di sviluppo, ≥ 20 giocate ciascuna) | 341, **210** tolti i quasi doppioni |
| Candidati con esame (≥ 20 giocate nella 2025/26) | 186 |
| In profitto nella 2025/26 | **77 su 186 (41%)** |
| Test di famiglia (più della metà?) | p = 0,99: **non credibile** |
| Confermati anche nel 2026/27 | 2 |

**Esito: la famiglia non è credibile e nessun pattern si accende.** Un pattern che avesse davvero trovato qualcosa resterebbe in profitto più di una volta su due nella stagione nuova; qui succede il 41% delle volte, meno di quanto farebbe il caso senza margine. I pattern che sembrano forti nello sviluppo sono, in grande maggioranza, fortuna selezionata tra 263.000 prove.

## I primi della lista (solo per trasparenza, non si giocano)

| Esito | Campionato | Mercato | Quote | Condizione | ROI sviluppo (4 stagioni) | 2025/26 | 2026/27 |
|---|---|---|---|---|---|---|---|
| confermato | League Two | X | 2,50-3,49 | difesa casa nella media e tiri in porta in equilibrio | +0,2 · +3,2 · +38,4 · +29,1 | +17,9% (53) | +11,3% (15) |
| confermato | Ligue 1 | Over 2,5 | 1,40-1,69 | squadre vicine in classifica | +2,4 · +14,0 · +25,5 · +13,9 | +2,1% (40) | +31,1% (10) |
| passa | League One | 2 primo tempo | 2,50-3,49 | forma casa media e difesa ospite nella media | +42,0 · +6,3 · +32,3 · +2,8 | +42,1% (28) | n/d |
| passa | Portogallo | Over 2,5 | 1,70-1,99 | novembre-marzo | +10,8 · +2,3 · +17,9 · +22,5 | +33,3% (36) | n/d |
| passa | Liga | X | 2,50-3,49 | casa in cattiva forma e con molti gol subiti | +33,7 · +22,1 · +18,0 · +2,5 | +29,7% (50) | +39,3% (7) |

Con campioni di 20-50 giocate a stagione, ROI del 20-40% escono spesso per caso: è proprio quello che il test di famiglia misura.

## Cosa resta

- Il contesto calcolato dai soli risultati e tiri (forma, attacco, difesa, classifica, fase) non aggiunge profitto stabile: lo conferma anche la mappa dei campionati (`MAPPA_V1_RISULTATO.md`).
- Le strade aperte sono quelle con informazione nuova: **combo coerenti** (esame passato, `docs/combo/COMBO_V1_RISULTATO.md`), **specialista tiri in porta** (esame passato), **formazioni e assenze** (storico in scarico dal 25/10/2026, esame preregistrato in `docs/squadre/SQUADRE_V1_PREREGISTRAZIONE.md`).
