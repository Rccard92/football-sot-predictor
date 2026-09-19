# Contratto dati e API Cecchino V4

Vale per backend e frontend. Chi cambia una forma aggiorna questo file nello stesso commit.

## Chiavi di mercato (`market_key`)

- Classici: `HOME`, `DRAW`, `AWAY`, `ONE_X`, `X_TWO`, `ONE_TWO`, `OVER_0_5` … `UNDER_3_5`, `HOME_PT`, `DRAW_PT`, `AWAY_PT`.
- Handicap asiatico: `AH_HOME:<linea>` e `AH_AWAY:<linea>` con linea in formato `-0.5`, `+0.25`, `0.0` (segno dal punto di vista della squadra di casa: `AH_HOME:-0.5` = casa −0,5; `AH_AWAY:-0.5` = ospite parte da −0,5, cioe' casa +0,5).
- Statistiche: `STAT:<stat>:<lato>:<verso>:<linea>` con stat in `shots|sot|corners|cards|fouls`, lato in `home|away|total`, verso in `over|under`, linea con mezzo (`6.5`). Esempio: `STAT:sot:away:over:6.5`.

Le stesse chiavi identificano le quote nel registro (`markets_json` di `cecchino_v4_odds_snapshots`: `{market_key: quota}`).

## Payload della previsione gol (`cecchino_v4_predictions.kind = "goals"`)

```json
{
  "engine_version": "cecchino_v4_goals_v1",
  "lambda_home": 1.62, "lambda_away": 1.10, "rho": -0.05, "ht_share": 0.44,
  "dispersion": {"home": null, "away": null},
  "uncertainty": {"score": 0.22, "level": "bassa", "home_evidence": 34.2, "away_evidence": 12.1, "disagreement": 0.08,
                  "new_team_home": false, "new_team_away": false},
  "markets": {"HOME": {"p": 0.51, "lo": 0.46, "hi": 0.56}, "AH_HOME:-0.5": {"p": 0.51, "lo": 0.46, "hi": 0.56}},
  "ratings": {"home": {"attack": 0.21, "defence": -0.05, "attack_rank": 3, "defence_rank": 6, "teams_in_division": 20, "home_advantage": 0.18},
              "away": {"attack": 0.30, "defence": -0.12, "attack_rank": 1, "defence_rank": 2, "teams_in_division": 20, "home_advantage": 0.15}},
  "specialists": {"forza": {"home": 1.5, "away": 1.2}, "sot": {"home": 1.6, "away": 1.1}, "shots": {"home": 1.7, "away": 1.0},
                  "weights": {"forza": 0.5, "sot": 0.2, "shots": 0.3},
                  "form": {"goals_home": 0.02, "goals_away": -0.05, "shots_home": 0.1, "shots_away": -0.02, "matches_home": 5, "matches_away": 5},
                  "calendar": {"rest_days_home": 7, "rest_days_away": 4, "final_phase": false}},
  "calibration": {"applied": true, "season": "2024/2025"}
}
```

`p` e' la probabilita' calibrata; `lo`/`hi` l'intervallo al 90% dall'incertezza.
`uncertainty.level` in `bassa|media|alta`.

## Payload della previsione statistiche (`kind = "stats"`)

```json
{
  "engine_version": "cecchino_v4_stats_v1",
  "stats": {
    "sot": {
      "exam": "superato",
      "home":  {"mean": 4.9, "dispersion": null, "division_mean": 4.6, "rank_for": 8, "rank_against": 11, "teams_in_division": 20,
                "lines": {"3.5": {"over": 0.71, "lo": 0.66, "hi": 0.76}, "4.5": {"over": 0.55, "lo": 0.5, "hi": 0.6}}},
      "away":  {"mean": 6.8, "...": "..."},
      "total": {"mean": 11.7, "...": "..."}
    },
    "corners": {"exam": "non_superato", "...": "..."}
  }
}
```

`exam` in `superato|non_superato|in_attesa`: se non superato, la statistica e' `solo_descrittivo` nella selezione.
`under` = 1 − `over` sulla stessa linea.

## Verdetti (`verdict`)

`giocabile`, `prezzo_giusto`, `incertezza_alta`, `non_quotato`, `solo_descrittivo`, `formazioni_non_note`. Etichette in `constants.VERDICT_LABELS`.

## Riga di mercato (usata nel Ragionamento e nella shortlist)

```json
{"market_key": "STAT:sot:away:over:6.5", "family": "STAT_sot", "label": "Inter over 6,5 tiri in porta",
 "p": 0.61, "lo": 0.55, "hi": 0.66, "p_prudent": 0.57,
 "quota_bet365": 1.85, "quota_betfair": 1.9, "quota_used": 1.85, "bookmaker_used": "Bet365",
 "expected_profit": 0.13, "verdict": "giocabile", "verdict_label": "Giocabile"}
```

`expected_profit = p_prudent × quota_used − 1`. Giocabile se `expected_profit ≥ 0.03`, quota ≥ 1,20, statistica non descrittiva.

## Scheda partita (`FixtureCard`)

```json
{"id": 12, "api_fixture_id": 1234567, "league_code": "I1", "competition": "Serie A", "season_label": "2025/2026",
 "kickoff_at": "2026-09-21T18:45:00Z", "home_team": "Milan", "away_team": "Inter", "status": "NS",
 "most_likely": {"market_key": "AWAY", "label": "2", "p": 0.42},
 "expected_goals": {"home": 1.2, "away": 1.6},
 "uncertainty": {"score": 0.22, "level": "bassa"},
 "lineups_status": "non_note",
 "best_play": {"...": "riga di mercato"} ,
 "no_play_reason": null,
 "result": null}
```

`lineups_status` in `non_note|probabili|ufficiali`. `status` API-Football (`NS`, `1H`, `FT`, `PST`…). `result` = `{"ft_home": 1, "ft_away": 2, "ht_home": 0, "ht_away": 1}` quando finita.

## Dettaglio partita: il Ragionamento (`FixtureDetail`)

```json
{"fixture": "FixtureCard",
 "blocks": {
   "who":      {"sentence": "...", "home": {"attack": 0.21, "defence": -0.05, "attack_rank": 3, "defence_rank": 6, "teams_in_division": 20, "evidence": 34.2, "known": "bene", "home_advantage": 0.18, "inherited": "..."}, "away": {"...": "..."}},
   "how":      {"sentence": "...", "rows": [{"stat": "sot", "label": "tiri in porta", "home_for": 4.9, "home_against": 5.1, "away_for": 6.8, "away_against": 4.2, "division_mean": 4.6}]},
   "context":  {"sentence": "...", "form": {"...": "..."}, "rest": {"home_days": 7, "away_days": 4}, "motivation": null, "lineups": {"status": "non_note", "absences": []}, "referee": null},
   "predicts": {"sentence": "...", "score_matrix": [[0.08, 0.1], [0.12, 0.14]], "max_goals": 5, "markets": ["riga di mercato"]},
   "why":      {"play": "riga di mercato", "sentences": ["..."], "would_change": ["..."]},
   "aftermath": null
 }}
```

`why` e `aftermath` possono essere `null`. Tutte le frasi sono generate da regole fisse in `explain/`.

## Endpoint lettura (prefisso `/api/cecchino/v4`)

| Metodo e percorso | Risposta |
|---|---|
| `GET /days?from=YYYY-MM-DD&days=7` | `{"days": [{"date": "…", "fixtures": 12, "plays": 3, "finished": 0}]}` |
| `GET /fixtures?date=YYYY-MM-DD[&league=I1][&only_plays=true][&only_lineups=true][&sort=kickoff|profit]` | `{"date": "…", "items": [FixtureCard], "abstentions": {"prezzo_giusto": 5, "incertezza_alta": 2}}` |
| `GET /fixtures/{id}` | `FixtureDetail` |
| `GET /shortlist?date=YYYY-MM-DD` | `{"date": "…", "status": "provvisoria|confermata|regolata", "sealed_at": "…", "digest": "sha256…", "items": [ShortlistItem], "abstentions": [{"reason": "…", "count": 5, "examples": ["Milan - Inter"]}]}` |
| `GET /measure/summary?from&to` | `{"by_league": [...], "by_market": [...], "totals": {"plays": 0, "roi": null, "roi_lo": null, "roi_hi": null, "clv": null}, "alerts": []}` |
| `GET /engine/exams` | `{"items": [{"code": "E1", "title": "…", "passed": true, "preregistration": "docs/v4/…", "result": {...}, "computed_at": "…"}]}` |
| `GET /engine/challengers` | `{"items": [{"name": "…", "status": "candidato|superato|non_superato", "exam": {...}}]}` |
| `GET /engine/data` | `{"coverage": [{"league_code": "I1", "markets": {"STAT:sot": true}}], "quality": [{"league_code": "I1", "fixtures": 30, "missing_stats_pct": 1.2, "missing_lineups_pct": 4.0, "missing_odds_pct": 0}], "api_budget": {"date": "…", "calls": 412, "stop_at": 7000}, "odds_registry": {"snapshots_today": 96, "last_taken_at": "…"}}` |

`ShortlistItem` = riga di mercato + `{"fixture_id": 12, "home_team": "…", "away_team": "…", "kickoff_at": "…", "rank": 1, "top": true, "status": "provvisoria|confermata|ritirata|regolata", "withdraw_reason": null, "result": "vinta|persa|void|null", "clv": 0.04}`.

## Endpoint admin (prefisso `/api/admin/cecchino/v4`, sessione admin obbligatoria)

| Metodo e percorso | Effetto |
|---|---|
| `POST /jobs/{name}/run` | Avvia un job (`fixtures`, `post_match`, `lineups`, `injuries`, `standings`, `odds_snapshot`, `odds_closing`, `predict`, `shortlist`, `settle`, `coverage_scan`, `backfill`). Risposta `202 {"job_id": "…"}` |
| `GET /jobs` | Stato job recenti |
| `POST /shortlist/{date}/seal` | Sigilla la shortlist del giorno |
| `POST /exams/{code}/run` | Ricalcola un esame storico dai CSV |

Tutti gli endpoint rispondono `{"status": "error", "message": "…"}` in caso di errore, con codice HTTP coerente.

## Appendice Fase 4 (20 settembre 2026): campi aggiunti da selezione, spiegazione e misura

Solo aggiunte; le forme sopra restano valide.

### Riga di mercato: campi in più

- `provisional` (bool): formazioni non note al momento del calcolo; la giocata nasce `provvisoria`. Non e' un verdetto.
- `advised` (bool): `false` quando l'esame E4 della famiglia non e' superato (docs/v4/PREREGISTRAZIONE_FASE_4.md, par. 2.3). La riga resta visibile con il suo verdetto; la Shortlist mostra il banner "Esame E4 non superato: giocate classiche in osservazione, non consigliate".
- `bookmaker_id` (int|null): id API-Football del book di `quota_used` (8 Bet365, 3 Betfair).
- `base_rate` (float): tasso base usato dalla probabilita' prudente.
- `stat_exam` (`superato|non_superato|in_attesa`|null): esame E2 della statistica; null per i mercati non statistici.

### Esiti del regolamento

`result` di una voce puo' valere anche `mezza_vinta` e `mezza_persa` (handicap asiatico a quarti). `profit_units` a puntata piatta 1: vinta `q − 1`, persa `−1`, void `0`, mezza vinta `(q − 1)/2`, mezza persa `−0,5`.

### `GET /shortlist?date=`: campi in più

- Risposta: `advised` (bool), `banner` (string|null).
- `ShortlistItem`: `advised`, `league_code`, `profit_units`, `closing_quota`, `reason` (frasi del blocco 5 se salvate), `id` (id della voce, per ritiro e regolamento).
- `abstentions[]`: anche `label` (etichetta italiana del motivo).

### `FixtureDetail.blocks`: campi in più

- `who.home|away`: anche `team`, `trend` (`in crescita|in calo|stabile`|null), `known` in `bene|abbastanza|poco` (soglie: ≥ 15 partite equivalenti "bene", < 5 "poco").
- `how.rows[]`: anche `exam`, `home_rank_for`, `away_rank_for`, `total`. `home_against`/`away_against` vengono dal campo opzionale `mean_against` del payload statistiche; null se assente.
- `context.form`: `{"home": {"trend","goals_delta","shots_delta","matches"}, "away": {...}}`; `context.rest` anche `final_phase`.
- `predicts`: anche `most_likely_score` `{"home","away","p"}`, `most_likely` (segno 1X2), `expected_goals`. `score_matrix` e' 6×6 (0-5 gol), `max_goals` 5.
- `why`: anche `reason` (verdetto bloccante quando `play` e' null); in quel caso `sentences` contiene la frase "Nessuna giocata: …" e `would_change` e' vuoto.
- `aftermath`: `{"sentence", "result", "goals": {"expected_home","expected_away","actual_home","actual_away"}, "stats": [{"stat","label","expected_home","expected_away","actual_home","actual_away"}], "play": {"label","market_key","outcome","profit_units"}|null, "luck": "…"}`.

### `GET /measure/summary`: forma dettagliata

- `by_league[]`: `{"league_code","plays","profit_units","roi","roi_lo","roi_hi","clv","alarm"}`.
- `by_market[]`: `{"market_family","label","plays","profit_units","roi","roi_lo","roi_hi","clv","alarm"}`.
- `totals`: anche `profit_units`.
- `alerts[]`: `{"scope": "league|market", "key", "plays", "alarm_at", "roi", "sentence"}` da CUSUM a un lato (`k` = 0,03, `h` = 6 unita') sui gruppi con almeno 30 giocate regolate.
- CLV = quota presa / quota di chiusura − 1 (positivo: prezzo migliore della chiusura). Intervalli ROI: bootstrap a blocchi per giornata al 90%.
