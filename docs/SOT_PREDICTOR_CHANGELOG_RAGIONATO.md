# SOT Predictor — Changelog ragionato

## Cecchino — Fase 2 — Recupero dati reali e tracciabilità input (2026-06-04)

- Rimossi dalla UI i testi descrittivi sul modulo separato da SOT (il modulo resta tecnicamente isolato).
- Introdotto `cecchino_v0_2_real_records`: nuove righe in `cecchino_predictions`; le cache `cecchino_v0_1_excel_parity` con `input_snapshot` nullo o formato legacy non vengono più servite.
- Recupero W/D/L da fixture finite (competition-scoped, PIT su kickoff) tramite `cecchino_fixture_history` e helper condivisi solo su tabelle fixture (`_prior_fixtures_for_team`, `team_split_fixtures`, `last_n`).
- **Non** usa `team_sot_predictions`, output v2.0/v2.1, `model_version` SOT, audit o pick SOT.
- `input_snapshot` con 8 slice (`label`, `wdl`, `sample_count`, `status`, …) e `data_quality.leakage_check` come oggetto con `status`, `target_kickoff`, `max_source_fixture_date`, `checked_at`.
- Endpoint invariati; query `recalculate` / `force_recalculate` per forzare ricalcolo singola fixture.
- v2.0 e v2.1: nessuna modifica.

Vedi anche [SOT_PREDICTOR_CECCHINO.md](./SOT_PREDICTOR_CECCHINO.md).
