# Risultato — V5 Angoli, Tiri in porta, Cartellini v1 (esame sulla 2025/26)

Calcolato il 22/10/2026 con le regole di `STATISTICI_V1_PREREGISTRAZIONE.md`. 5.290 partite della 2025/26 (quelle valide per la V3).

**Nota di trasparenza.** Durante la scelta dei parametri di Angoli due prove hanno stampato anche le righe della 2025/26 accanto a quelle di sviluppo. I parametri sono comunque quelli migliori sullo sviluppo, come da regola (k = 20, γ = 0,15), e coincidono con quelli che si sarebbero scelti senza vederle. Per Tiri in porta e Cartellini le scelte sono state fatte solo sullo sviluppo.

| Specialista | Parametri (scelti sullo sviluppo) | Log-loss V5 | Semplice | Base | Miglioramento sul Semplice | Taratura peggiore | Esito |
|---|---|---|---|---|---|---|---|
| **Tiri in porta** | k = 20, γ = 0,25 | 0,6432 | 0,6624 | 0,6465 | **2,9%** | 1,5 punti | **PASSA** |
| Angoli | k = 20, γ = 0,15 | 0,6581 | 0,6688 | 0,6604 | 1,6% (serve 2%) | 2,2 punti (ospite 4,5) | non passa |
| Cartellini | k = 20, δ = 0,5, ε = 0 | 0,6367 | 0,6412 | 0,6374 | 0,7% (serve 2%) | 1,8 punti | non passa |

## Cosa dicono

- **Tiri in porta**: lo specialista prevede tiri in porta di casa, ospite e totale meglio della media del campionato e del modello senza gol attesi della V3 su tutte le 7 linee. È l'unico che passa.
- **Angoli**: aiuta sugli angoli della singola squadra (casa 4,5: 0,6604 contro 0,6805, −3%), ma sul totale della partita non fa meglio della media del campionato. La media sulle 8 linee resta sotto la soglia.
- **Cartellini**: il guadagno sulla media del campionato è piccolo. Il fattore arbitro però funziona: nei campionati inglesi (unici con l'arbitro nello storico) lo specialista batte il modello base su tutte e 7 le linee. In Inghilterra la 2025/26 ha avuto più cartellini del previsto (casa 1,5: 50,5% stimato, 54,4% reale).

## Cosa succede adesso

- Tiri in porta v1 va in lista sigillata dal vivo nei campionati dove Bet365 o Betfair quotano i tiri in porta, con la regola di decisione comune (probabilità prudente × quota ≥ 1,03).
- Angoli e Cartellini v1, insieme a Valore v1, restano in osservazione: le loro giocate si calcolano e si misurano ogni giorno, ma non sono consigliate.
