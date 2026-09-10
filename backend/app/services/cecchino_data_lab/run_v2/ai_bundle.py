"""Pacchetto AI ZIP per RUN V2 — lossless, una sola generazione artefatti."""

from __future__ import annotations

import hashlib
import json
import logging
import tempfile
import zipfile
from pathlib import Path
from typing import Any, BinaryIO, Iterator

from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.models.cecchino_run_v2 import CecchinoRunV2Run
from app.services.cecchino_data_lab.run_v2.constants import (
    CORE_MARKETS,
    RUN_V2_EXPORT_SCHEMA_VERSION,
    RUN_V2_FEATURE_CONTRACT_VERSION,
    RUN_V2_QUOTE_POLICY_VERSION,
    RUN_V2_VERSION,
)
from app.services.cecchino_data_lab.run_v2.export import (
    FILE_DATA_DICTIONARY,
    FILE_FULL,
    FILE_MARKETS_LONG,
    FILE_RUN_SUMMARY,
    FILE_SOURCE_RAW,
    build_export_bundle,
)

logger = logging.getLogger(__name__)

SPOOL_MAX_SIZE = 64 * 1024 * 1024
STREAM_CHUNK = 1024 * 512

ZIP_README = "00_README_AI.md"
ZIP_MANIFEST = "01_MANIFEST.json"
ZIP_PROMPT = "02_ANALYSIS_PROMPT.md"
ZIP_DATA_FULL = f"data/{FILE_FULL}"
ZIP_DATA_LONG = f"data/{FILE_MARKETS_LONG}"
ZIP_DATA_RAW = f"data/{FILE_SOURCE_RAW}"
ZIP_META_SUMMARY = f"metadata/{FILE_RUN_SUMMARY}"
ZIP_META_DICT = f"metadata/{FILE_DATA_DICTIONARY}"

ZIP_MEMBERS = (
    ZIP_README,
    ZIP_MANIFEST,
    ZIP_PROMPT,
    ZIP_DATA_FULL,
    ZIP_DATA_LONG,
    ZIP_DATA_RAW,
    ZIP_META_SUMMARY,
    ZIP_META_DICT,
)


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while chunk := fh.read(1024 * 1024):
            h.update(chunk)
    return h.hexdigest()


def _count_csv_shape(path: Path) -> tuple[int, int]:
    """(rows_without_header, columns)."""
    import csv

    with path.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.reader(fh)
        try:
            header = next(reader)
        except StopIteration:
            return 0, 0
        rows = sum(1 for _ in reader)
    return rows, len(header)


def _season_slug(run: CecchinoRunV2Run) -> str:
    raw = (run.season_label or "UNKNOWN").strip().replace("/", "-").replace(" ", "_")
    return raw or "UNKNOWN"


def _build_readme(run: CecchinoRunV2Run, summary: dict[str, Any]) -> str:
    comps = summary.get("competitions") or []
    eligible = summary.get("eligible_core") or summary.get("eligible") or None
    if eligible is None:
        eligible = sum(int(c.get("eligible_core") or 0) for c in comps if isinstance(c, dict))
    markets = ", ".join(m.export_key for m in CORE_MARKETS)
    return f"""# Cecchino RUN V2 — pacchetto AI

## Contesto run

- **run_id**: {run.id}
- **season**: {run.season_label or "n/d"}
- **scope**: {run.run_scope or "n/d"}
- **status**: {run.status}
- **run_version**: {run.run_version or RUN_V2_VERSION}
- **matches**: {(summary.get("matches") or run.matches_total or "n/d")}
- **eligible_core (aggregato)**: {eligible}
- **competizioni**: {len(comps)}
- **formula freeze CORE**: true (formule V1/CORE non modificate in questa export pipeline)
- **quote policy**: {RUN_V2_QUOTE_POLICY_VERSION} — Bet365 STRICT closing/pre-kickoff
- **export schema**: {RUN_V2_EXPORT_SCHEMA_VERSION}
- **feature contract**: {RUN_V2_FEATURE_CONTRACT_VERSION}

## 17 mercati CORE

{markets}

## Quote Bet365 STRICT

- Closing / pre-kickoff, `pre_match_input_safe=true` quando presenti.
- O/U (0.5/1.5/2.5/3.5): **solo REAL**, mai derivate.
- DC: REAL se presente enrichment Bet365; altrimenti fallback derivato da 1X2 ammesso.
- Nessun layer `economic_observation` nelle nuove RUN.

## Eligibility / warm-up

La performance operativa Cecchino richiede warm-up storico (eligibility). I moduli
osservazionali (Balance, Goal Intensity, Signals) **non** bloccano `eligible_core`.

## Pre-match blindness

Tutte le prediction usano solo dati noti prima del kickoff. I campi `actual_*` e
gli outcome di settlement sono post-match e non sono input di modello.

## is_predicted_selection

In `core_markets_long.csv` ogni famiglia ha una sola pick: la riga con
`is_predicted_selection == true` (market_key == prediction di famiglia).

## Settlement teorico vs vera pick

`outcome` / `won` / `flat_stake_profit` su una riga mercato sono lo settlement
teorico di quella selezione. **Non** confonderli con la pick Cecchino:
usa `is_predicted_selection`.

## BLOCCO 2

Feature extra pre-match (shots/SOT/corners/…) costruite solo dallo storico
precedente. Non sono il BLOCCO 1 CORE probabilities.

## actual_* post-match

Colonne `actual_*` = etichette note solo a partita conclusa. Vietato usarle come
feature pre-match o per overfitting.

## Walk-forward

La run e walk-forward cronologico: ogni match vede solo history con kickoff
strettamente precedente. Leakage audit deve essere 0.

## Data dictionary

Vedi `metadata/DATA_DICTIONARY.json` per layer, ammissibilita input e descrizione
di ogni colonna.

## Ordine consigliato dei file

1. `00_README_AI.md` (questo file)
2. `01_MANIFEST.json`
3. `metadata/run_summary.json`
4. `metadata/DATA_DICTIONARY.json`
5. `data/FULL.csv`
6. `data/core_markets_long.csv`
7. `data/SOURCE_RAW.csv` (solo se serve raw Football-Data)

---

# REGOLA FONDAMENTALE — performance Cecchino

Per valutare la performance del Cecchino usa **solo** le righe con:

```
eligibility_status == "eligible_core"
AND is_predicted_selection == true
```

**Non** sommare indiscriminatamente `flat_stake_profit` di tutte le market rows.
"""


def _build_prompt() -> str:
    return """# Analysis prompt (model-neutral)

Sei un analista quantitativo. Questo pacchetto proviene dalla Cecchino RUN V2.

## Ordine di lettura obbligatorio

1. `00_README_AI.md`
2. `01_MANIFEST.json`
3. `metadata/run_summary.json`
4. `metadata/DATA_DICTIONARY.json`
5. Solo dopo: `data/FULL.csv` e `data/core_markets_long.csv`
6. `data/SOURCE_RAW.csv` solo se necessario

## Divieti

- Vietato leakage temporale (usare dati post-kickoff come feature).
- Vietato overfitting su `actual_*` o settlement post-match.
- Vietato trattare tutte le market rows come pick.
- Distingui **BLOCCO 1** (CORE probabilities/KPI/buyability/signals) da **BLOCCO 2**
  (extra pre-match stats).
- Distingui settlement teorico di riga da `is_predicted_selection == true`.

## Regola performance

Analizza PnL / hit-rate solo su:

`eligibility_status == "eligible_core" AND is_predicted_selection == true`

## Output atteso

- Sintesi coverage e qualità quote
- Performance sulle pick eleggibili
- Eventuali anomalie di provenance (O/U deve essere REAL)
- Nessuna proposta di modifica formule CORE/V1
"""


def _file_inventory(path: Path, *, arcname: str) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "path": arcname,
        "bytes": path.stat().st_size,
        "sha256": _sha256_file(path),
    }
    if path.suffix.lower() == ".csv":
        rows, cols = _count_csv_shape(path)
        entry["rows"] = rows
        entry["columns"] = cols
    elif path.suffix.lower() == ".json":
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(payload, dict):
                entry["columns"] = len(payload.keys())
            elif isinstance(payload, list):
                entry["rows"] = len(payload)
        except Exception:
            pass
    return entry


def build_ai_bundle_artifacts(
    db: Session,
    *,
    run_id: int,
    work_dir: Path,
) -> dict[str, Any]:
    """Genera i 5 artefatti una sola volta + README/MANIFEST/PROMPT."""
    run = db.get(CecchinoRunV2Run, int(run_id))
    if run is None:
        raise ValueError(f"run_v2 {run_id} inesistente")

    export_dir = work_dir / "export"
    export_dir.mkdir(parents=True, exist_ok=True)
    bundle = build_export_bundle(db, run_id=int(run_id), output_dir=export_dir)
    files = bundle["files"]

    summary = json.loads(Path(files[FILE_RUN_SUMMARY]).read_text(encoding="utf-8"))
    readme_path = work_dir / ZIP_README
    prompt_path = work_dir / ZIP_PROMPT
    manifest_path = work_dir / ZIP_MANIFEST
    readme_path.write_text(_build_readme(run, summary), encoding="utf-8")
    prompt_path.write_text(_build_prompt(), encoding="utf-8")

    mapped = {
        ZIP_DATA_FULL: Path(files[FILE_FULL]),
        ZIP_DATA_LONG: Path(files[FILE_MARKETS_LONG]),
        ZIP_DATA_RAW: Path(files[FILE_SOURCE_RAW]),
        ZIP_META_SUMMARY: Path(files[FILE_RUN_SUMMARY]),
        ZIP_META_DICT: Path(files[FILE_DATA_DICTIONARY]),
        ZIP_README: readme_path,
        ZIP_PROMPT: prompt_path,
    }

    inventory = [_file_inventory(p, arcname=name) for name, p in mapped.items()]
    # Manifest dopo inventory dei data/meta; poi si aggiunge se stesso senza sha ricorsivo.
    leakage = summary.get("leakage_audit") or {}
    manifest_body = {
        "run_id": int(run.id),
        "season": run.season_label,
        "scope": run.run_scope,
        "versions": {
            "run_version": run.run_version or RUN_V2_VERSION,
            "export_schema_version": RUN_V2_EXPORT_SCHEMA_VERSION,
            "feature_contract_version": RUN_V2_FEATURE_CONTRACT_VERSION,
            "quote_policy_version": RUN_V2_QUOTE_POLICY_VERSION,
        },
        "matches": summary.get("matches") or run.matches_total,
        "eligible": summary.get("eligible_core")
        or sum(
            int(c.get("eligible_core") or 0)
            for c in (summary.get("competitions") or [])
            if isinstance(c, dict)
        ),
        "competitions": len(summary.get("competitions") or []),
        "leakage": leakage,
        "formula_freeze": True,
        "quote_policy": RUN_V2_QUOTE_POLICY_VERSION,
        "file_inventory": inventory,
    }
    manifest_path.write_text(
        json.dumps(manifest_body, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )
    mapped[ZIP_MANIFEST] = manifest_path
    inventory.append(_file_inventory(manifest_path, arcname=ZIP_MANIFEST))
    manifest_body["file_inventory"] = [
        e for e in inventory if e["path"] != ZIP_MANIFEST
    ] + [_file_inventory(manifest_path, arcname=ZIP_MANIFEST)]
    # Riscrivi con inventory completo incluso il manifest stesso.
    manifest_path.write_text(
        json.dumps(manifest_body, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )

    season = _season_slug(run)
    filename = f"CECCHINO_RUN_V2_{season}_RUN_{int(run.id)}_AI_BUNDLE.zip"
    return {
        "run": run,
        "filename": filename,
        "mapped": mapped,
        "export_counts": bundle.get("counts") or {},
        "manifest": manifest_body,
    }


def write_ai_bundle_zip(
    db: Session,
    run_id: int,
    dest: BinaryIO,
) -> tuple[str, int]:
    with tempfile.TemporaryDirectory(prefix=f"run_v2_ai_{run_id}_") as tmp:
        work = Path(tmp)
        built = build_ai_bundle_artifacts(db, run_id=int(run_id), work_dir=work)
        with zipfile.ZipFile(dest, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
            for arcname in ZIP_MEMBERS:
                path = built["mapped"][arcname]
                zf.write(path, arcname=arcname)
        dest.seek(0, 2)
        size = int(dest.tell())
        dest.seek(0)
        return built["filename"], size


def build_ai_bundle_response(db: Session, run_id: int) -> StreamingResponse:
    spool = tempfile.SpooledTemporaryFile(max_size=SPOOL_MAX_SIZE)
    try:
        filename, size = write_ai_bundle_zip(db, int(run_id), spool)
    except Exception:
        spool.close()
        raise

    def _iter() -> Iterator[bytes]:
        try:
            while True:
                chunk = spool.read(STREAM_CHUNK)
                if not chunk:
                    break
                yield chunk
        finally:
            spool.close()

    logger.info("run_v2 ai-bundle run_id=%s bytes=%s", run_id, size)
    return StreamingResponse(
        _iter(),
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-AI-Bundle-Bytes": str(size),
        },
    )
