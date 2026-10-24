# Preregistrazione — ordinamento della giocata principale del Bet Builder (v1)

Scritta il 24/10/2026, prima di calcolare qualunque numero delle varianti. Dopo il calcolo non si cambia nulla di questo file: il risultato va in `ESAME_ORDINAMENTO_V1_RISULTATO.md`.

## Perché

Il Bet Builder sceglie la giocata principale di ogni partita con l'Evidence Sort V2: prima l'origine (prezzo e segnali, poi segnali, poi prezzo), poi il punteggio di acquistabilità **V3.1**, poi i segnali. Nel confronto del 24/10 la V3.1 con punteggio alto è la versione di acquistabilità che perde di più (≥ 70: −40,6% su 47 mercati; 50-69: −12,1% su 247) e il Bet Builder è l'unico motore con perdita certa negli ultimi 30 giorni (−9,8% su 1.249 giocate). La domanda: un ordinamento diverso delle stesse opportunità avrebbe fatto meglio?

Cosa si sapeva già prima del test: il ROI complessivo del Bet Builder (variante A) e i ROI delle versioni di acquistabilità per fascia di punteggio, su tutti i mercati di Today (non sulle opportunità del Bet Builder). I ROI delle varianti B, C, D sulle opportunità del Bet Builder non sono mai stati calcolati.

## Dati

- Partite eleggibili di Cecchino Today dal 08/08/2026 (inizio dei risultati del Bet Builder) al 23/10/2026 compreso.
- Per ogni partita, le opportunità del Bet Builder come le salva oggi il sistema (stesso insieme per tutte le varianti: cambia solo l'ordine), con il loro esito.
- Quota: la quota Bet365 dell'opportunità (`price_value.quota_book`), la stessa che usa oggi la pagina Risultati. Puntata 1 unità.

## Varianti

| | Ordine |
|---|---|
| **A** (attuale) | origine → V3.1 → segnali superati → numero di sì → contesto disponibile → rating → edge |
| **B** senza V3.1 | origine → segnali superati → numero di sì → contesto disponibile → rating → edge |
| **C** V3.6 al posto di V3.1 | origine → V3.6 → segnali superati → numero di sì → contesto disponibile → rating → edge |
| **D** solo segnali | segnali superati → numero di sì → contesto disponibile → rating → edge |
| **R** riferimento | il caso: profitto medio di tutte le opportunità valutabili della partita |

In ogni variante, a parità su tutti i criteri vale la chiave dell'opportunità (come oggi). Si ordinano solo le opportunità con quota Bet365 (> 1), che si conosce prima della partita. La giocata della variante è la prima; se il suo esito non è vinta o persa (dato mancante, partita non conclusa), la partita non conta per quella variante.

## Misura

- Per ogni variante: giocate, vinte, quota media, profitto, ROI con forbice al 90%.
- Confronto con A **appaiato**: sulle partite dove sia la variante sia A hanno una giocata conclusa, differenza di profitto per partita (variante − A); media e forbice.
- Le partite in cui la variante sceglie la stessa giocata di A danno differenza zero: si riporta anche quante sono.
- Descrittivo, senza decisione: ROI per fascia di quota e per origine.

## Regola di decisione

Una variante **passa** se tutte e due:
1. la differenza appaiata con A è positiva con la forbice tutta sopra zero, al **96,7%** (tre varianti contro A: 90% corretto per tre confronti, z = 2,13);
2. il suo ROI non è sotto quello del riferimento R.

Se passano più varianti, si propone quella con la differenza media più alta. Se non passa nessuna, A resta com'è e il risultato si riporta comunque.

In ogni caso il cambio non è automatico: la variante che passa entra in osservazione nella pagina Confronto motori accanto al Bet Builder attuale per 4 settimane, poi decidono l'utente e Giovanni.

## Limiti dichiarati

- È un test sul passato recente (circa 11 settimane), non una stagione: serve a scegliere cosa osservare dal vivo, non a promettere profitto.
- Le partite di un giorno non sono indipendenti tra loro; la forbice per partita è un po' ottimista.
- Le opportunità sono quelle salvate oggi: se nel periodo il Bet Builder ne ha cambiato la costruzione, il test misura l'ordinamento sull'insieme attuale.
