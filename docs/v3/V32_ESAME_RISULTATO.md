# Risultato — esame V3.2 (correzioni dei gol) sulla stagione 2025

Calcolato il 24/10/2026 sul server (`GET /api/cecchino/v3/v32-exam`, sola lettura, circa 2 minuti) con le regole di `V32_ESAME_PREREGISTRAZIONE.md`, senza modifiche.

Campionati con stagione 2025 fuori dai 16: 339; con la V3 estesa calcolabile (almeno 30 partite con tiri e tiri in porta): **46**. Partite valutate: 4.598 nello sviluppo (id pari), 5.898 nella verifica (id dispari). Nessun campionato in errore.

## Sviluppo (scelta)

| Combinazione | Log-loss Over/Under | Log-loss 1X2 | Over 2,5 previsto / reale |
|---|---|---|---|
| V3 attuale (K spento, ρ stimato) | 0,61042 | 1,03562 | 48,4 / 49,7 |
| **K spento, ρ = 0** | **0,61022** | 1,03414 | 48,4 / 49,7 |
| K = 20, ρ stimato | 0,61139 | 1,03586 | 49,7 / 49,7 |
| K = 50, ρ stimato | 0,61100 | 1,03578 | 49,5 / 49,7 |
| K = 100, ρ stimato | 0,61071 | 1,03572 | 49,3 / 49,7 |
| K = 100, ρ = 0 | 0,61041 | 1,03445 | 49,3 / 49,7 |

Scelta per la regola: **K spento, ρ = 0** (log-loss Over/Under più basso, 1X2 non peggiora).

## Verifica (esame)

| | V3 attuale | Scelta (ρ = 0) |
|---|---|---|
| Log-loss Over/Under | 0,61569 | 0,61575 |
| Log-loss 1X2 | 1,00772 | 1,00624 |
| Over 2,5 previsto / reale | 50,7 / 52,4 (scarto 1,8) | 50,7 / 52,4 (scarto 1,8) |

Differenza per partita (attuale − scelta) sul log-loss Over/Under: −0,00007, forbice al 90% da −0,00028 a +0,00015.

| Regola | Esito |
|---|---|
| 1. Over/Under migliore, forbice sopra zero | **no** |
| 2. 1X2 non peggiora più di 0,002 | sì (migliora di 0,0015) |
| 3. Taratura Over 2,5 entro 1,5 punti e migliore dell'attuale | **no** (1,8, uguale) |

**Esito: non passa. A e B restano spente.**

## Cosa dice

- **La correzione del livello dei gol (A) sistema la media ma peggiora le singole partite.** Con K = 20 l'Over 2,5 previsto coincide con il reale (scarto da 1,3 a 0), ma il log-loss peggiora: il fattore per campionato aggiunge più rumore di quanto tolga.
- **Togliere la correzione dei pareggi bassi (B) non cambia gli Over/Under**; migliora appena l'1X2 (−0,0015 nella verifica, −0,0015 nello sviluppo): da tenere d'occhio, non basta per l'esame che era fissato sugli Over/Under.
- **Nel 2025 la sottostima dei gol della V3 è piccola** (1,3-1,8 punti di Over 2,5), molto meno dei 5 punti visti dal vivo da settembre (`DIAGNOSI_V25_V3_LIVE.md`). Lo scarto dal vivo dipende quindi soprattutto dal periodo e dai campionati di queste settimane, non da un difetto fisso del modello. Si continua a misurarlo nel Confronto motori.

## Cosa entra dal vivo

- V3.2 = probabilità della V3 (A e B spente) con la **giocata in evidenza C** (1X2 finale e Over/Under 1,5-3,5, quota 1,41-2,20, la più probabile); in osservazione con la regola D sulla V2.5, dal 26/10 al 22/11/2026.
