# Risultato — combo sulla stessa partita (v1)

Calcolato il 24/10/2026 sul server (`GET /api/cecchino/v5/combo-exam`, sola lettura) con le regole di `COMBO_V1_PREREGISTRAZIONE.md`, senza modifiche. 24.345 partite dei 16 campionati (2022/23-2026/27).

## Esame 2025/26: passa

| Regola | Esito |
|---|---|
| 1. Combo scelte: frequenza reale entro 2,5 punti dalla probabilità prevista | **sì**: 51,77% previsto, 51,82% reale (5.749 combo) |
| 2. Brier della copula migliore del modello indipendente (117.702 combo candidate) | **sì**: 0,24444 contro 0,24552 |

## Combo scelte (una per partita, quota equa tra 1,90 e 2,60)

| Periodo | Combo | Previsto | Reale | Prodotto delle probabilità singole | Quota di pareggio |
|---|---|---|---|---|---|
| Sviluppo 2022/23-2024/25 | 17.569 | 51,7% | 51,5% | 50,2% | 1,94 |
| **Esame 2025/26** | **5.749** | **51,8%** | **51,8%** | 50,2% | **1,93** |
| Controllo 2026/27 (senza gol) | 1.027 | 51,2% | 51,0% | 49,9% | 1,96 |

Circa 23 combo per giornata sui 16 campionati.

### Per scenario (2025/26)

| Scenario | Combo | Previsto | Reale |
|---|---|---|---|
| Partita aperta | 1.207 | 51,7% | 52,5% |
| Partita chiusa | 1.178 | 51,7% | 51,4% |
| Dominio casa | 2.007 | 51,8% | 52,5% |
| Dominio ospite | 1.357 | 51,8% | 50,6% |

### Per numero di giocate (2025/26)

| | Combo | Previsto | Reale | Prodotto delle singole |
|---|---|---|---|---|
| 2 giocate | 5.338 | 51,8% | 51,9% | 50,4% |
| **3 giocate** | 411 | 51,2% | 50,9% | **47,9%** |

## Cosa dice

- Il modello stima bene quanto spesso esce una combo coerente: lo scarto è sotto mezzo punto in ogni periodo.
- **Le giocate coerenti escono insieme più del prodotto delle probabilità**: +1,5 punti con 2 giocate, **+3 punti con 3 giocate**. Una quota costruita moltiplicando le singole sottostima la combo: con 3 giocate la quota "indipendente" sarebbe 2,09 contro una quota di pareggio reale di 1,97.
- Legami misurati (sviluppo): gol e tiri in porta della stessa squadra 0,46; tiri in porta e angoli della stessa squadra 0,19; angoli di casa e ospite −0,19 (chi attacca toglie angoli all'altro).
- **Profitto**: le combo scelte guadagnano se la quota pagata supera circa **1,95** (quota di pareggio 1,93-1,96). La lista dal vivo mostra per ogni combo la quota minima (1,05 / probabilità).

## Cosa entra dal vivo

Lista sigillata "Combo" nella V5 dal 25/10/2026, in osservazione: una combo per partita dei 16 campionati con probabilità, quota equa e quota minima. Come prezzo di riferimento si registra il prodotto delle quote singole Bet365/Betfair quando tutte le giocate sono quotate. Il confronto con la quota MyCombo di Sisal resta all'utente finché non avremo esempi reali dei prezzi MyCombo.
