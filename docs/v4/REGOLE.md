# Regole Cecchino V4

Regole fissate il 19 settembre 2026, prima di scrivere il codice. Valgono per ogni file sotto `backend/app/services/cecchino_v4`, `backend/app/jobs/cecchino_v4_*`, `backend/app/routes/cecchino_v4.py`, `frontend/src/components/cecchino-v4`, `frontend/src/pages/CecchinoV4Page.tsx`.

1. **Isolamento.** La V4 non modifica codice, tabelle, dati o pagine di V2, V2.5, V3, Cecchino Today, Bet Builder, Master Pattern. Le uniche modifiche a file esistenti sono le registrazioni: rotta in `routes/__init__.py`, modelli in `models/__init__.py`, pagina in `App.tsx`, voce di menu in `navItems.ts`, una migrazione Alembic additiva.
2. **Quote del book.** Mai dentro probabilità, gol attesi, statistiche attese, incertezza o indici. Entrano solo in `selection/` come prezzo e in `measure/` come metro.
3. **Stagione 2025/26.** Solo input walk-forward per il live. Nessun parametro, iperparametro, soglia, esame o calibrazione stimato su 2025/26. Nel codice: `HISTORY_SEASONS` per gli esami escludono sempre il lockbox.
4. **Esami pre-registrati.** Ogni esame ha un file `docs/v4/PREREGISTRAZIONE_FASE_N.md` scritto e committato prima del calcolo; il risultato va in `docs/v4/esami/`. Un esame fallito non si adotta, nemmeno come descrizione con soglie.
5. **Nessun minimo di partite giocate.** Ogni partita dei 16 campionati riceve una previsione; l'incertezza decide l'astensione.
6. **Budget API-Football.** Ogni job V4 registra le chiamate nella tabella eventi d'uso e si ferma da solo se il contatore del giorno supera 7.000.
7. **Interfaccia.** Base 16 px, nessun testo sotto i 14 px e nessuno a 10-12 px su Partite, Shortlist e Ragionamento. Quote con la virgola. Parole prima dei numeri.
8. **Riuso.** Il motore V3 si importa come libreria e non si modifica. Se serve una variante, si scrive in V4.
9. **Codice.** Funzioni pure per motori e regole; database solo nei servizi di persistenza; test per ogni regola di decisione.
