# Preregistrazione — strato squadre: rose, formazioni e assenze (v1)

Scritta il 24/10/2026, prima di avere i dati: lo storico di giocatori (minuti, titolari, voti) e assenze dei 16 campionati si scarica dal 25/10/2026 con il job `history_players` (stagioni 2025/26, 2024/25, 2023/24, 2022/23, 2021/22 in quest'ordine, circa 2.500 partite al giorno). Il risultato va in `SQUADRE_V1_RISULTATO.md`; questo file non si cambia dopo il calcolo.

## Idea

Una squadra non è la media delle sue ultime partite: dipende da chi gioca. Si misura quanto pesa ogni giocatore e quanto pesa, partita per partita, la formazione rispetto a quella abituale.

## Peso del giocatore

Per ogni giocatore, solo con le partite precedenti della stessa stagione (dalla 4ª giornata della squadra):
- **presenza**: quota dei minuti giocati sul totale disponibile nelle ultime 10 partite della squadra;
- **qualità**: voto medio API-Football nelle partite giocate (almeno 3), centrato sulla media della squadra;
- **peso** = presenza × (1 + qualità / 2), con il voto in punti (es. 7,2 contro media 6,8 → +0,4).

**Formazione abituale** della squadra: gli 11 giocatori con più minuti nelle ultime 10 partite.

## Indici della partita (per squadra)

- **Assenze del mattino (A)**: somma dei pesi dei giocatori della formazione abituale nell'elenco assenze della partita (infortuni e squalifiche, tipo "Missing Fixture"), divisa per la somma dei pesi della formazione abituale. Si conosce il giorno prima: utile per giocare la mattina.
- **Formazione ufficiale (F)**: 1 − (somma dei pesi dei titolari / somma dei pesi della formazione abituale), limitata tra 0 e 1. Si conosce un'ora prima.

## Modello

Correzione dei gol attesi della V3 (run 11): log λ = log λ_V3 + β_att · indice della squadra + β_dif · indice dell'avversaria, con β stimati sullo sviluppo per verosimiglianza di Poisson (penalità leggera verso 0), separatamente per A e per F. Le probabilità di 1X2 e Over/Under si ricalcolano dalla distribuzione dei gol.

## Stagioni

**Sviluppo** 2023/24 e 2024/25; **esame** 2025/26. Se a inizio novembre sono disponibili anche 2022/23 e 2021/22 entrano nello sviluppo; la scelta si dichiara nel risultato prima di guardare l'esame.

## Esame (2025/26), separato per A e per F

Passa se tutte e tre:
1. il log-loss medio di 1X2 e Over/Under 2,5 migliora rispetto alla V3, con la forbice al 90% della differenza per partita sopra zero;
2. β_att (effetto delle proprie assenze sui propri gol) è negativo nello sviluppo: assenze importanti → meno gol;
3. con la regola di gioco della mappa (quota 1,50-2,50, probabilità × quota ≥ 1,05, una per partita) il ROI nella 2025/26 è migliore di quello della V3 senza correzione.

## Dopo

Se A o F passano: le probabilità corrette entrano nelle liste V5 come specialista "Squadre" in osservazione (A al mattino, F dopo le formazioni ufficiali), poi Confronto motori. Se non passano: si prova una v2 (peso del giocatore da minuti e differenza reti con lui in campo) con una nuova preregistrazione.
