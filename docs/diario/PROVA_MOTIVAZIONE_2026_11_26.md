# Prova storica degli avvisi di motivazione (26/11/2026)

Richiesta di Giovanni del 26/11/2026: il centro classifica deciso conta come «senza obiettivi», ma solo nelle ultime
8 giornate e quando la squadra è a più di 6 punti sia dalla zona Europa/promozione sia dalla zona
retrocessione/playout. Prima e dopo la modifica: quanto rendono «casa motivata» e «ipotesi 2», e quante gare in più
fanno scattare.

## Dati

- Stagioni complete del Lab (football-data): 15 campionati europei (E0 E1 E2 E3 I1 I2 SP1 SP2 D1 D2 F1 F2 N1 P1 T1),
  dal 2021/22 al 2025/26: 75 stagioni. Il Belgio è escluso (la stagione finisce nei play-off).
- Per ogni gara in cui a una delle due squadre restano 8 gare o meno: classifica del giorno prima, gare che restano a
  ogni squadra, motivazione con la regola del 24/11 («prima») e del 26/11 («dopo»): 6.160 gare.
- Zone: posti di Europa/promozione dall'alto e di retrocessione/playout dal basso con la struttura di oggi di ogni
  campionato (nelle stagioni passate può essere cambiata di un posto).
- «Casa motivata» = 1 alla quota Bet365 di apertura; «ipotesi 2» = 2. ROI a 1 unità.
- Codice: `backend/app/services/analyst/motivation_exam.py`, endpoint `/api/analyst-journal/motivation-exam?start=true`.

## Risultati

| Avviso | Prima: gare | Prima: ROI | Dopo: gare | Dopo: vinte | Dopo: unità | Dopo: ROI | Gare in più | ROI delle gare in più |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| casa motivata (1) | 7 | −65,6% | 270 | 146 | −21,87 | −8,1% | 263 | −6,6% |
| ipotesi 2 (2) | 2 | +10,0% | 250 | 117 | +28,30 | +11,3% | 248 | +11,3% |

Altri avvisi (solo quante gare): «gara senza motivazioni» 665 prima e 665 dopo; «P27» 417 prima e 285 dopo.

## Lettura

- Con la regola del 24/11 «senza obiettivi» non scattava quasi mai (7 e 2 gare in 5 anni): la modifica fa partire
  i due avvisi su circa 250-270 gare.
- «Casa motivata»: l'1 perde −8,1%, in linea con lo studio di Giovanni (−5,2%): il book lo sa già.
- «Ipotesi 2»: +11,3% su 250 gare, in linea con lo studio di Giovanni (+8,9% su 380). Non è ancora una prova:
  l'errore standard su 250 giocate a quota media circa 2,4 è di circa ±7,5 punti, quindi +11,3% sta a circa 1,5
  errori standard da zero. Resta un'ipotesi in prova, registrata sulla carta.
- P27 scatta meno (417 → 285): la favorita a centro classifica decisa, lontana dalle zone, ora è «senza
  obiettivi» e non più «posizione decisa», e P27 conta solo la posizione decisa.

## P27 nei due casi (seconda prova, 26/11/2026)

Giovanni: P27 conta anche la favorita «senza obiettivi» (contro una squadra in lotta), tenuta distinta dalla
favorita a «posizione decisa». Stesse 6.160 gare; favorita secca (1 o 2) e in doppia chance (1X o X2) alla quota
Bet365 di apertura (la doppia chance solo dove il CSV ha la quota).

| Caso | Gare | Favorita secca: vinte | unità | ROI | Doppia chance: gare | vinte | unità | ROI |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| P27 · posizione decisa | 285 | 157 | −16,06 | −5,6% | 275 | 219 | −8,03 | −2,9% |
| P27 · senza obiettivi | 134 | 57 | −8,62 | −6,4% | 129 | 86 | −13,67 | −10,6% |

Prima della regola del 26/11 la favorita «senza obiettivi» non c'era quasi mai (2 gare): i due casi insieme fanno
419 gare, quasi le stesse 417 di prima, divise in due.

Lettura: in entrambi i casi la favorita perde, quindi l'avviso «non giocare la favorita» regge. Con la posizione
decisa la favorita secca perde circa quanto il margine del book (−5,6%) e la doppia chance meno (−2,9%); con la
favorita senza obiettivi la doppia chance perde molto di più (−10,6%). Sono numeri piccoli (134 gare): da seguire
nel pannello, riga per riga.
