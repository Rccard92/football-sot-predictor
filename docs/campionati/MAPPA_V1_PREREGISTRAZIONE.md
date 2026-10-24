# Preregistrazione — mappa dei 16 campionati e modelli dedicati (v1)

Scritta il 24/10/2026, prima di calcolare qualunque numero di questa mappa. Il risultato va in `MAPPA_V1_RISULTATO.md`; questo file non si cambia dopo il calcolo.

## Obiettivo

Per ognuno dei 16 campionati del Lab: cosa guadagna, su quale mercato, a che quote, quante giocate. Si gioca solo dove un campionato ha dimostrato di guadagnare; dove non c'è niente, non si gioca.

Guadagnare = profitto a puntata piatta di 1 unità sulla quota Bet365 prima della partita (percentuale di vinte × quota media sopra 1).

## Dati

- `cecchino_lab_matches`, 16 campionati (football-data), quote Bet365 prima della partita.
- Probabilità del modello comune: V3 run 11 (walk-forward, 17 mercati), dal 2021/22 al 2025/26.
- Stagioni (taglio al 1° luglio): **sviluppo** 2021/22, 2022/23, 2023/24, 2024/25; **esame** 2025/26; **controllo** 2026/27 fino ad oggi (solo 1X2 e Over/Under 2,5, gli unici con quote nei file della stagione in corso).
- Mercati con quota (12): 1, X, 2; 1X, 12, X2; Over e Under 1,5 · 2,5 · 3,5; 1, X, 2 primo tempo.

## Famiglia R — regole del campionato (senza modello)

Una regola = campionato × mercato × fascia di quota Bet365: 1,40-1,69 · 1,70-1,99 · 2,00-2,49 · 2,50-3,49. Si gioca ogni partita del campionato in cui la quota del mercato cade nella fascia.

- **Candidata** se nello sviluppo ha ROI > 0 in **tutte e 4** le stagioni, con almeno 20 giocate in ognuna.
- **Passa** se nella 2025/26 ha ROI > 0 con almeno 20 giocate.
- **Confermata** se passa e, dove ci sono le quote (1X2, Over/Under 2,5), ha ROI > 0 anche nella 2026/27 fino ad oggi (almeno 10 giocate).

Senza alcun vantaggio, una candidata è positiva nella 2025/26 meno di una volta su due (il margine del book spinge sotto zero). **La famiglia R è credibile** solo se le candidate positive nella 2025/26 sono significativamente più della metà (test binomiale a una coda contro 50%, p < 0,05). Altrimenti anche le regole che passano si trattano come caso e non si accendono.

## Famiglia M — modello dedicato per campionato

Per ogni campionato e mercato, ritaratura della probabilità V3 su quel campionato:
logit(p) = a + b · logit(p_V3), stimata con penalità verso a = 0, b = 1 (peso 50 partite), cioè il modello comune finché il campionato non mostra una differenza stabile. p_V3 limitata tra 0,01 e 0,99.

- **Sviluppo walk-forward**: la stagione s usa una ritaratura stimata solo sulle stagioni di sviluppo precedenti (prima valutata: 2022/23).
- **Esame**: ritaratura stimata su tutte e 4 le stagioni di sviluppo, applicata alla 2025/26.

Regola di gioco (uguale per tutti i campionati, fissata qui): tra i mercati della partita con quota tra 1,50 e 2,50 e probabilità dedicata × quota ≥ 1,05, si gioca quello con il prodotto più alto; al massimo una giocata per partita. La stessa regola con la probabilità V3 non ritarata è il confronto ("modello comune").

Un campionato **passa** con il modello dedicato se tutte e quattro:
1. ROI dello sviluppo walk-forward (2022/23-2024/25 insieme) > 0;
2. ROI 2025/26 > 0 con almeno 30 giocate;
3. ROI 2025/26 del dedicato ≥ ROI 2025/26 del modello comune;
4. log-loss medio dei 12 mercati nella 2025/26 del dedicato ≤ quello della V3.

**La famiglia M è credibile** se i campionati che passano sono significativamente più di quelli attesi per caso: il conteggio dei campionati con ROI 2025/26 > 0 si confronta con 50% (binomiale a una coda, p < 0,05).

## Scheda per campionato (descrittiva, senza decisione)

Partite, % 1-X-2, gol medi, % Over 2,5, tiri in porta, angoli e cartellini medi; per ogni mercato con quota: probabilità media prezzata da Bet365 (senza margine) contro frequenza reale, sviluppo e 2025/26. Tiri in porta, angoli e cartellini: lo storico non ha quote, quindi solo frequenze (il profitto si misura dal vivo con lo specialista V5).

## Cosa si accende dopo

- Solo regole R confermate (o passate, se la 2026/27 non ha quote per quel mercato) e campionati M che passano, e solo se la loro famiglia è credibile.
- Dal vivo come lista sigillata della V5 (specialista "Campionati"), in osservazione per 4 settimane o 100 giocate, nel Confronto motori.
- Se nessuna famiglia è credibile, la mappa resta descrittiva e non si gioca nulla di nuovo: anche questo è un risultato.

## Limiti dichiarati

- 2025/26 è stata vista in modo aggregato in analisi precedenti (pattern del Lab, esami V5); non per campionato × mercato × fascia di quota.
- Le probabilità V3 della run 11 hanno iperparametri scelti per la stagione 2025/26 (calcolo finale): piccolo vantaggio del modello comune nell'esame, non del dedicato.
- Molte regole provate (16 × 12 × 4): per questo valgono i test di famiglia e la conferma 2026/27.
