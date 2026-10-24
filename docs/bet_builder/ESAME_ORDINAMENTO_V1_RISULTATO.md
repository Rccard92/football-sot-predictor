# Risultato — ordinamento della giocata principale del Bet Builder (v1)

Calcolato il 24/10/2026 sul server (`GET /api/cecchino/bet-builder/sort-exam`, sola lettura) con le regole di `ESAME_ORDINAMENTO_V1_PREREGISTRAZIONE.md`, senza modifiche.

Periodo 08/08/2026 – 23/10/2026: 4.245 partite eleggibili, 3.582 con almeno un'opportunità quotata. Quota Bet365, 1 unità a giocata.

## Varianti

| | Variante | Giocate | Vinte | Quota media | Profitto | ROI | Forbice 90% |
|---|---|---|---|---|---|---|---|
| A | Attuale: origine → V3.1 → segnali | 3.506 | 50,7% | 2,31 | −260,1 | −7,4% | −10,5 / −4,3% |
| **B** | **Senza V3.1: origine → segnali** | 3.505 | 51,7% | 2,42 | −171,5 | **−4,9%** | −8,2 / −1,5% |
| C | V3.6 al posto di V3.1 | 3.507 | 53,3% | 2,20 | −250,4 | −7,1% | −10,1 / −4,2% |
| D | Solo segnali | 3.505 | 51,6% | 2,43 | −173,4 | −4,9% | −8,3 / −1,6% |
| R | Riferimento: opportunità a caso | 3.510 partite | | | | −6,1% | −8,7 / −3,5% |

## Confronto appaiato con A (forbice al 96,7%)

| Variante | Differenza media per partita | Forbice | Stessa giocata di A | Regola 1 (sopra zero) | Regola 2 (ROI ≥ R) | Esito |
|---|---|---|---|---|---|---|
| **B** | **+2,57 punti** | +0,30 / +4,83 | 3.035 su 3.505 | sì | sì (−4,9 ≥ −6,1) | **passa** |
| C | +0,31 | −1,87 / +2,48 | 2.997 su 3.506 | no | no | non passa |
| D | +2,51 | +0,15 / +4,88 | 2.963 su 3.505 | sì | sì | passa |

Passano B e D; per la regola si propone **B** (differenza media più alta).

## Cosa dice

- **L'ordinamento attuale sceglie peggio del caso**: A −7,4% contro −6,1% di un'opportunità presa a caso nella stessa partita. Il punteggio V3.1 sposta la scelta verso giocate peggiori.
- **Togliere la V3.1 migliora**: B cambia la giocata in 470 partite su 3.505 (13%) e recupera circa 89 unità sul periodo. Il miglioramento viene dalle partite di origine "prezzo" (−8,0% → −4,2%) e dalle quote sopra 2,20 (−10,9% → −5,9%).
- **La V3.6 al posto della V3.1 non cambia quasi nulla** (C ≈ A).
- **Nessuna variante fa profitto**: anche B resta in perdita (−4,9%, forbice tutta sotto zero). Il cambio riduce la perdita, non la trasforma in guadagno.
- Unica fascia in positivo per tutte le varianti: quote 2,01-2,20 (A +10,4% su 194, B +9,3% su 159), osservazione descrittiva e non decisa prima.

## Limiti

- La forbice di B sfiora lo zero (+0,30) ed è un po' ottimista perché le partite dello stesso giorno non sono indipendenti.
- Undici settimane, una sola finestra: serve la conferma dal vivo.

## Prossimo passo (dalla preregistrazione)

B entra in osservazione nella pagina Confronto motori accanto al Bet Builder attuale per 4 settimane. Il Bet Builder non cambia finché l'utente e Giovanni non decidono.
