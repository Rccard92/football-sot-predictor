# Preregistrazione — V5 Angoli, Tiri in porta, Cartellini v1

Scritta il 22/10/2026 **prima** di calcolare qualsiasi risultato sulla 2025/26.

## Perché l'esame misura la precisione e non il profitto

Lo storico (football-data, 16 campionati) ha le statistiche partita per partita ma non le quote di angoli, cartellini e tiri in porta. Sulla 2025/26 si misura quindi quanto bene ogni specialista prevede le linee più giocate, contro due riferimenti. Il profitto si misura solo in avanti, con le quote che la V4 registra dal 20/09/2026.

## Dati

- `cecchino_lab_matches`, 16 campionati, 2021/22-2025/26: angoli, tiri in porta, gialli e rossi per squadra, arbitro (solo campionati inglesi).
- Gol attesi della V3 finale (run 11, `lambda_home`, `lambda_away`), calcolati in ordine di tempo.
- Sviluppo 2021/22-2024/25, esame 2025/26 una sola volta.
- Partite valutate: entrambe le squadre con almeno 5 partite precedenti nella stessa stagione e campionato.

## Modello comune (per ogni statistica X)

1. Medie del campionato nella stagione fino al giorno prima: μ_casa e μ_trasferta di X.
2. Per ogni squadra, rapporto tra X fatto e la media del campionato per quel lato, e tra X concesso e la media del lato avversario, sulle partite precedenti della stagione. Forza in attacco e in difesa = media dei rapporti ristretta verso 1 con peso k partite.
3. Attese: λ_casa = μ_casa × attacco_casa × difesa_ospite; λ_ospite = μ_trasferta × attacco_ospite × difesa_casa.
4. Ingrediente specifico:
   - **Angoli**: rapporto dei gol attesi V3, λ_casa × (gol attesi casa / gol attesi ospite)^γ e simmetrico per l'ospite.
   - **Tiri in porta**: gol attesi V3, λ_casa × (gol attesi casa / media gol casa del campionato)^γ e simmetrico.
   - **Cartellini** (punti: giallo 1, rosso 2): fattore arbitro = media cartellini delle sue partite precedenti / media del campionato, ristretta verso 1 con peso 10 partite (solo dove l'arbitro è noto), elevato a δ; partita equilibrata: × (1 + ε × (1 − |differenza gol attesi| / 2)), con differenza limitata a 2.
5. Distribuzione: binomiale negativa con dispersione stimata sulle stagioni di sviluppo, separata per totale e per squadra.
6. Parametri (k ∈ {5, 10, 20}; γ, δ ∈ {0; 0,25; 0,5}; ε ∈ {0; 0,1; 0,2}) scelti sulle stagioni di sviluppo con l'errore quadratico medio delle attese. Nessuna quota entra nel modello.

## Riferimenti

- **Semplice**: media del campionato nella stagione fino al giorno prima, stessa distribuzione.
- **Base**: modello comune senza ingrediente specifico (γ = δ = ε = 0).

## Linee valutate

- Angoli: totale 8,5 / 9,5 / 10,5 / 11,5; casa 4,5 / 5,5; ospite 3,5 / 4,5.
- Tiri in porta: totale 7,5 / 8,5 / 9,5; casa 3,5 / 4,5; ospite 2,5 / 3,5.
- Cartellini (punti): totale 3,5 / 4,5 / 5,5; casa 1,5 / 2,5; ospite 1,5 / 2,5.

## Esame sulla 2025/26 — ogni specialista passa se valgono tutte e tre

1. Log-loss media sulle sue linee almeno il 2% sotto quella del riferimento Semplice.
2. Log-loss media non peggiore di quella del riferimento Base (l'ingrediente specifico non deve peggiorare).
3. Scarto tra probabilità media e frequenza reale ≤ 2 punti su ogni linea.

Per i Cartellini il fattore arbitro si giudica solo sui campionati inglesi (unici con l'arbitro nello storico); fuori dall'Inghilterra lo specialista usa il resto del modello.

## Dopo l'esame

Chi passa va in lista sigillata dal vivo sui 16 campionati, con le quote Bet365/Betfair registrate dalla V4: si gioca se probabilità prudente × quota ≥ 1,03, una giocata per partita per specialista, massimo 5 al giorno per specialista. Chi non passa resta solo in osservazione (lista calcolata ma non consigliata).
