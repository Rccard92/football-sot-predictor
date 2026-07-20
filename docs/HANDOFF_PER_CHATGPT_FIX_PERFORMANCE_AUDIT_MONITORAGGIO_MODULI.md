# HANDOFF PER CHATGPT — FIX PERFORMANCE AUDIT MONITORAGGIO MODULI

**Repository:** Rccard92/football-sot-predictor  
**Scope:** solo client FE card/API + cache/logging backend audit. Nessuna modifica a formule, candidate, export ZIP, coorti, backfill, DB, migrazioni, CORS.

---

## 1. Richieste prima / dopo

| Prima | Dopo |
|-------|------|
| Fino a 3 GET audit concorrenti (useEffect + filtri + Riverifica) | **0** fetch al mount / cambio filtro |
| Timeout client 90s → toast «Timeout operazione dopo 90 s» | Timeout dedicato **240s** solo per audit |
| Ogni cambio data/competizione/coorte rilancia audit | Solo click **Riverifica** / **Riprova** |

---

## 2. Auto-run rimosso

In `MonitoringPackQualityCard.tsx` eliminato:

```ts
useEffect(() => { void load() }, [load])
```

Al mount: messaggio «Clicca Riverifica…». Nessun fetch automatico.

---

## 3. Single-flight

Helper `createAuditRequestGuard()` (`auditRequestGuard.ts`):

- una sola Promise attiva;
- doppio click → secondo `begin()` ritorna `null`;
- `AbortController` + generation id: risposte stale ignorate;
- cleanup unmount: `abort()`.

---

## 4. Timeout dedicato

`getAnalysisPacksAudit(..., { timeoutMs: 240_000, signal })`  
Costante: `ANALYSIS_PACKS_AUDIT_TIMEOUT_MS = 240_000`  
Default globale `adminGetJson` resta **90s**.

Messaggio timeout UX:  
«La verifica completa richiede più tempo del previsto. I dati precedenti restano disponibili.»

---

## 5. Gestione stale

Al cambio `dateFrom|dateTo|competitionId|sourceCohort` con risultati già presenti:

- badge **«Filtri modificati — riverifica necessaria»**;
- card precedenti **non** cancellate;
- dopo Riverifica riuscita: `filtersStale=false`.

Loading UX: «Verifica forensic in corso…» + dopo 30s «non chiudere la pagina».

---

## 6. Cache TTL backend

`build_modules_analysis_packs_audit`:

- chiave: export_version, date_from/to, competition_id, market_key, include_rows/debug, source_cohort;
- TTL **300s**, max **32** entry, `threading.Lock`;
- hit → log `module_audit_cache_hit`;
- errori all-failed **non** cacheati;
- `clear_module_audit_cache()` per test;
- ZIP download **non** usa questa cache.

Log: `module_audit_started`, `module_audit_completed`, `module_audit_cache_hit` (range, cohort, elapsed_ms, module_count, cache_hit).

---

## 7. Test

- Backend: 78 monitoring tests passed (inclusi 4 nuovi cache).
- FE: `auditRequestGuard.test.ts` (single-flight, timeout constant).
- `npm run build` OK.
- Linter IDE: nessun errore sui file toccati.

---

## 8. Conferme

- [x] Nessun dato / backfill / formula modificati
- [x] Nessuna migrazione / CORS
- [x] Export ZIP invariato
