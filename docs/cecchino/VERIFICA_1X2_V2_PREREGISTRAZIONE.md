# Verifica Cecchino 1-X-2 v2 — regole scritte prima (09/11/2026)

Dal 09/11/2026 la quota Cecchino 1-X-2 si calcola con la versione `1x2_v2_20261109`
(back test: `docs/cecchino/BACKTEST_1X2_2026-11-09.md`):

1. probabilità = media pesata delle probabilità dei picchetti (0,3 / 0,3 / 0,2 / 0,2): somma al 100%;
2. fattore campo: 1 × 1,25, X × 1,05, 2 invariata, poi di nuovo somma al 100%;
3. quota = 1 / probabilità.

Su ogni partita il JSON del Cecchino (`cecchino_output_json.final`) salva `version`, `home_factor`,
`raw_probs` (il solo punto 1, prima del fattore campo), `sum_prob` e `v1` (la quota di prima, media delle quote).
Le partite calcolate prima del 09/11 restano come erano: non si ricalcolano.

## La verifica (scritta prima di vedere i dati)

- **Quando:** il 10/12/2026, oppure appena ci sono almeno 1.000 partite finite con la versione v2.
- **Dati:** solo partite calcolate con `final.version = '1x2_v2_20261109'`, con risultato finale.
- **Confronto:** v2 (punti 1 e 2) contro il solo punto 1 (`raw_probs` riportate al 100%), sulle stesse partite.
- **Regola:** se il LogLoss di v2 **non** è più basso di quello del solo punto 1, il fattore campo si spegne
  mettendo `CECCHINO_HOME_FACTOR_1=1.0` e `CECCHINO_HOME_FACTOR_X=1.0` nei servizi Railway che calcolano il
  Cecchino (backend e cecchino-auto-scan). Resta il punto 1. Nessuna nuova stima del fattore sugli stessi dati.
- Si riportano anche favorito azzeccato e Brier, ma la decisione si prende solo sul LogLoss.

## Query (sola lettura, strumento cecchino_sql)

```sql
with t as (
  select distinct on (t.local_fixture_id) t.local_fixture_id fid, t.cecchino_output_json->'final' f
  from cecchino_today_fixtures t
  where t.scan_date >= '2026-11-10' and t.eligibility_status = 'eligible'
    and t.cecchino_output_json->'final'->>'version' = '1x2_v2_20261109'
  order by t.local_fixture_id, t.scan_date desc
), r as (
  select case when x.goals_home > x.goals_away then 1 when x.goals_home = x.goals_away then 2 else 3 end res,
    (f->>'prob_1')::float p1, (f->>'prob_x')::float px, (f->>'prob_2')::float p2,
    (f->'raw_probs'->>'1')::float r1, (f->'raw_probs'->>'x')::float rx, (f->'raw_probs'->>'2')::float r2
  from t join fixtures x on x.id = t.fid and x.status in ('FT', 'AET', 'PEN')
)
select count(*) partite,
  round(avg(-ln(greatest(case res when 1 then p1 when 2 then px else p2 end, 0.001)))::numeric, 4) logloss_v2,
  round(avg(-ln(greatest(case res when 1 then r1 when 2 then rx else r2 end / (r1 + rx + r2), 0.001)))::numeric, 4) logloss_punto1,
  round(avg(power(p1 - (res = 1)::int, 2) + power(px - (res = 2)::int, 2) + power(p2 - (res = 3)::int, 2))::numeric, 4) brier_v2,
  round(avg(power(r1 / (r1 + rx + r2) - (res = 1)::int, 2) + power(rx / (r1 + rx + r2) - (res = 2)::int, 2)
            + power(r2 / (r1 + rx + r2) - (res = 3)::int, 2))::numeric, 4) brier_punto1,
  round(100.0 * avg(((res = 1 and p1 >= px and p1 >= p2) or (res = 2 and px > p1 and px >= p2)
                     or (res = 3 and p2 > p1 and p2 > px))::int), 1) favorito_v2_pct
from r
```
