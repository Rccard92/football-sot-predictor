# HANDOFF PER CHATGPT — BALANCE V5 FASE 2A DATASET EMPIRICO

**Repository:** Rccard92/football-sot-predictor  
**Commit base atteso:** `ad0554a018988d93fffe48d5cb5bd09a9ee7555b`  
**Scope:** contratto empirico + persistenza + sync + settlement + API/UI/export v6.  
**Invariato:** formule Balance, soglie, classi, pesi, Signals, Acquistabilità candidate, backfill storico generico.

---

## 1. Cosa è stato aggiunto

| Layer | Artefatto |
|-------|-----------|
| Model | `CecchinoBalanceV5Evaluation` → `cecchino_balance_v5_evaluations` |
| Migration | `20260720120000` (`down_revision=20260719190000`) |
| Service | `cecchino_balance_v5_empirical.py` |
| Pipeline | upsert su scan/recompute; settle su update-results (fail-soft) |
| Admin API | `POST …/balance-v5/empirical-sync/plan|run` |
| Read API | `GET …/balance-v5/empirical/{health,summary,rows,target-contract,cardinality}` |
| Export | `cecchino_module_monitoring_exports_v6` + file `empirical_*` |
| FE | vista `empirical-dataset` + sync dry-run→confirm→run |

---

## 2. Token e versioni

- Confirm run: `SYNC_BALANCE_V5_EMPIRICAL_DATASET`  
- Dataset: `cecchino_balance_v5_empirical_dataset_v1`  
- Target contract: `cecchino_balance_v5_empirical_target_contract_v1`  
- Overview maturity: `empirical_dataset_collecting` / label «Dataset empirico in raccolta»  
- Stato operativo Balance: resta «Ufficiale monitorato»

---

## 3. Unique key e settlement

Unique: `(today_fixture_id, balance_version, snapshot_hash)`  
Nuovo hash → `is_current=false` sulle vecchie + insert corrente.  
Settle: solo campi risultato; **non** ritocca snapshot/hash.

---

## 4. Report §21 — verifiche

| Check | Esito |
|-------|--------|
| Pre-flight git / modello / migrazione | Implementato |
| Hash stabile / esclusione settlement | Test unit |
| Upsert idempotente + flip `is_current` | Test unit |
| Settlement HOME/DRAW/AWAY + dominance hit/miss | Test unit |
| Sync dry-run + confirm errata | Test unit |
| Export v6 file empirici in ZIP | Test unit (mock) |
| FE token sync | Vitest |
| Runtime sync run su DB locale | Verificato se DB disponibile; altrimenti solo dry-run/test |
| Conteggio 964/876 hardcodati | Non usati negli assert di servizio |

---

## 5. Non fare

- Non rieseguire «Importa storico» generico per questo step  
- Non interpretare diagnostic come promotion-eligible  
- Non aggiungere win-rate/calibrazione (Step 2B)

---

## 6. Next

Step 2B — metriche empiriche / calibrazione sui target del contract, senza promuovere diagnostic.
