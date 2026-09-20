# Regole Cecchino V4

Regole fissate il 19 settembre 2026, prima di scrivere il codice. Valgono per ogni file sotto `backend/app/services/cecchino_v4`, `backend/app/jobs/cecchino_v4_*`, `backend/app/routes/cecchino_v4.py`, `frontend/src/components/cecchino-v4`, `frontend/src/pages/CecchinoV4Page.tsx`.

1. **Isolamento.** La V4 non modifica codice, tabelle, dati o pagine di V2, V2.5, V3, Cecchino Today, Bet Builder, Master Pattern. Le uniche modifiche a file esistenti sono le registrazioni: rotta in `routes/__init__.py`, modelli in `models/__init__.py`, pagina in `App.tsx`, voce di menu in `navItems.ts`, una migrazione Alembic additiva.
2. **Quote del book.** Mai dentro probabilità, gol attesi, statistiche attese, incertezza o indici. Entrano solo in `selection/` come prezzo e in `measure/` come metro.
3. **Stagione 2025/26.** Solo input walk-forward per il live. Nessun parametro, iperparametro, soglia, esame o calibrazione stimato su 2025/26. Nel codice: `HISTORY_SEASONS` per gli esami escludono sempre il lockbox.
4. **Esami pre-registrati.** Ogni esame ha un file `docs/v4/PREREGISTRAZIONE_FASE_N.md` scritto e committato prima del calcolo; il risultato va in `docs/v4/esami/`. Un esame fallito non si adotta, nemmeno come descrizione con soglie.
5. **Nessun minimo di partite giocate.** Ogni partita dei 16 campionati riceve una previsione; l'incertezza decide l'astensione.
6. **Budget API-Football.** Ogni job V4 registra le chiamate nella tabella eventi d'uso e si ferma da solo se il contatore del giorno supera 7.000.
7. **Interfaccia.** A specchio di Cecchino Today: stessa tipografia (testo 14 px, etichette 13 px, titoli 16-24 px), stesse card e badge. Regola aggiornata il 20/09/2026 su richiesta dell'utente (il 16 px iniziale era troppo grande). Poche informazioni in lista, tutto il resto nel Ragionamento. Quote con la virgola. Parole prima dei numeri.
8. **Riuso.** Il motore V3 si importa come libreria e non si modifica. Se serve una variante, si scrive in V4.
9. **Codice.** Funzioni pure per motori e regole; database solo nei servizi di persistenza; test per ogni regola di decisione.

## Decisioni dell'utente del 20/09/2026 (prevalgono sulle regole sopra dove indicato)

- **Focus sui mercati statistici.** Si giocano solo tiri, tiri in porta, corner e cartellini (totali, casa, fuori). I mercati classici (1X2, doppia chance, over/under gol, primo tempo, handicap) restano nel Ragionamento con il verdetto "in osservazione" e non entrano mai in scheda o shortlist. Coerente con l'esame E4 (non superato).
- **Corner e cartellini giocabili nonostante E2(a).** L'esame E2 li ha bocciati per scarti minimi sulla sola precisione contro le medie ingenue (parte a), mentre la parte (b), informazione oltre il mercato, e' superata in ogni stagione. L'utente ha deciso di giocarli: e' una deroga esplicita alla regola 4, e il giudizio arriva dal paper trading (G6), non da un'altra riesecuzione dell'esame. I falli restano descrittivi (Bet365 non li quota).
- **Solo linee a meta'** (0,5 · 1,5 · 2,5 ...) per handicap e statistiche: quarti, interi e linea zero non si calcolano e non si registrano.
- **Campionati senza mercati statistici** (nessuna quota STAT nelle ultime 10 giornate di istantanee, con almeno 3 istantanee) escono dalle letture delle quote per non consumare chiamate; rientrano appena una lettura li mostra quotati. La copertura e' nella vista Motore, sezione Dati.
