# Recupero giornata 2026-08-08 (post-deploy)

Dopo il deploy di `fix: restore eligibility and remove scan API guards`:

## A) Rivalidazione senza API

```bash
curl -X POST "$BASE_URL/api/admin/cecchino/today/revalidate-day" \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"date":"2026-08-08"}'
```

Raccogliere: `checked`, reasons (`excluded_kpi_not_calculable` prima/dopo), `kept_eligible` / moved.

## B) Verifica lista

```bash
curl "$BASE_URL/api/cecchino/today?date=2026-08-08" \
  -H "Authorization: Bearer $ADMIN_TOKEN"
```

## C) Force rescan completo (fixture mai raggiunte)

```bash
curl -X POST "$BASE_URL/api/admin/cecchino/today/scan-day/start" \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"date":"2026-08-08","timezone":"Europe/Rome","force_rescan":true}'
```

La scan non si ferma più a ~1000 chiamate locali. Termina a fine lista o su `provider_quota_exhausted`.
