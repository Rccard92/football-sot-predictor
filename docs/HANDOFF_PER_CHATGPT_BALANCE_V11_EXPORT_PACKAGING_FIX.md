# Handoff — Balance v11 export packaging fix

## Problema
Il pacchetto `SOT_MONITOR_balance-v5_*.zip` (export v11) non era autosufficiente: file readiness con `TypeError`, CSV history/governance assenti, audit `fail`.

## Causa root
1. **`date` non serializzabile**: `build_balance_readiness_overview` includeva `filters` con oggetti `date`; il dossier usava `jsonable_encoder`, il forensic pack usava `_json_bytes`/`make_json_safe` (senza supporto `date`) → `TypeError`.
2. **Gate CSV**: `"|".join(reason_codes)` falliva con elementi non-string.
3. **Fail-soft esterno**: eccezione post-report sostituiva tutto con placeholder incompleti (senza CSV).

## Fix
- Builder condiviso `build_balance_readiness_pack_payload` + `build_balance_readiness_forensic_file_payload`
- Dossier e forensic pack usano lo stesso payload canonico
- `_serialize_filters()` per JSON-safe
- Placeholder schema-complete con CSV header-only
- Audit Balance: `partial_collecting` quando prospective>0 e settled=0
- `last_snapshot_at` da max `snapshot_timestamp` prospettico verificato

## Commit
`fix: complete Balance v5 readiness export pack`
