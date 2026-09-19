# Stato lavori Cecchino V4

Aggiornato ad ogni passo. Serve a riprendere il lavoro senza contesto.

## Vincoli operativi di questa sessione
- Nessun accesso a database online, chiavi API o segreti: gli esami storici usano i CSV pubblici football-data.co.uk (16 campionati, 5 stagioni) in `backend/app/data/v4/football_data/`, identici alla fonte del Lab.
- Le pipeline live API-Football sono scritte e testate con risposte registrate; si accendono al deploy con `CECCHINO_V4_ENABLED=true`.
- Nessuna migrazione eseguita su database online; la migrazione V4 è additiva e gira al deploy.

## Avanzamento
- [x] Ramo `feature/cecchino-v4` da `cleanup/sot-removal`
- [x] `docs/v4/ROADMAP.md`, `docs/v4/REGOLE.md`
- [x] CSV storici scaricati (80 file, 0 errori) + stagione in corso 2026/27 (16 file) + fixtures.csv pubblico (partite in programma con quote Bet365/Betfair classiche)
- [x] Caricatori `history/football_data.py` (24.945 partite di giudizio, identiche al Lab) e `history/fixtures_csv.py`; test verdi
- [~] Fase 0: modelli e migrazione fatti; rotte lettura e pagina in lavorazione (agenti paralleli: motore gol/E1, motore statistiche/E2, pipeline live, selezione/spiegazione/misura, frontend)
- [ ] Fase 1: motore gol V4 + esame E1
- [ ] Fase 2: motore statistiche + esame E2
- [ ] Fase 3: pipeline live + registro quote (test con risposte registrate)
- [ ] Fase 4: selezione, shortlist sigillata, perché, esame E4
- [ ] Fase 5: contesto e arena (struttura + primi sfidanti)
- [ ] Fase 6: viste Misura e Come è andata (infrastruttura; il verdetto richiede calendario)
- [ ] Test backend e frontend verdi, lint, build
- [ ] Push su GitHub
