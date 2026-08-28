"""Gate export Pattern Discovery su Run #15 — READ-ONLY.

Uso:
  set DATABASE_URL=...
  python -m scripts.gate_pattern_lab_export_run15

Esce 0 se il gate passa. Non modifica Run #15.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker


def main() -> int:
    # Carica .env/.env.local se presenti (senza stampare i valori)
    root = Path(__file__).resolve().parents[1]
    try:
        from dotenv import load_dotenv

        load_dotenv(root / ".env")
        load_dotenv(root / ".env.local", override=True)
    except Exception:
        pass

    db_url = os.environ.get("DATABASE_PUBLIC_URL") or os.environ.get("DATABASE_URL")
    if not db_url:
        print("ERROR: DATABASE_URL (or DATABASE_PUBLIC_URL) missing")
        print("Suggerimento: metti DATABASE_PUBLIC_URL in backend/.env.local oppure esportala in questa shell.")
        return 2
    if "railway.internal" in db_url:
        print(
            "ERROR: DATABASE_URL punta a host interno Railway non raggiungibile in locale. "
            "Imposta DATABASE_PUBLIC_URL (TCP proxy pubblico) e rilancia."
        )
        return 2
    os.environ["DATABASE_URL"] = db_url

    # Ensure backend package importable
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

    from app.services.cecchino_data_lab.pattern_lab_constants import EXPORT_MODE_FULL
    from app.services.cecchino_data_lab.pattern_lab_discovery_export import (
        validate_export_gate_artifacts,
        write_discovery_dataset_files,
    )

    engine = create_engine(db_url)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    with SessionLocal() as db:
        run_row = db.execute(
            text(
                """
                SELECT id, season_label, status, scan_version,
                       module_policy_json->>'run_scope' AS run_scope,
                       matches_eligible_core, matches_processed
                FROM cecchino_lab_historical_scan_runs
                WHERE id = 15
                """
            )
        ).mappings().first()
        if not run_row:
            print("ERROR: Run #15 not found")
            return 2
        print("Run #15:", dict(run_row))

        market_count = db.execute(
            text(
                """
                SELECT COUNT(*) AS n
                FROM cecchino_lab_historical_market_results m
                JOIN cecchino_lab_historical_match_snapshots s
                  ON s.id = m.match_snapshot_id
                WHERE m.run_id = 15
                  AND s.historical_eligibility_status = 'eligible_core'
                """
            )
        ).scalar_one()
        print("eligible_core market_results:", market_count)

        # fingerprint pre-export (immutability check)
        snap_hash = db.execute(
            text(
                """
                SELECT COUNT(*) AS n,
                       COUNT(DISTINCT pre_match_payload_sha256) AS hashes
                FROM cecchino_lab_historical_match_snapshots
                WHERE run_id = 15
                """
            )
        ).mappings().one()
        print("pre-export snapshot fingerprint:", dict(snap_hash))

        with tempfile.TemporaryDirectory(prefix="gate_pl15_") as tmp:
            dest = Path(tmp)
            info = write_discovery_dataset_files(
                db,
                run_ids=[15],
                mode=EXPORT_MODE_FULL,
                filters={"eligibility": "eligible_core"},
                include_observational_only=True,
                dest_dir=dest,
            )
            print("export rows:", info["row_count"])
            errors = validate_export_gate_artifacts(dest, expected_min_rows=int(market_count))
            if info["row_count"] != int(market_count):
                errors.append(
                    f"row_count_vs_market_results: export={info['row_count']} db={market_count}"
                )

            # post-export immutability
            snap_hash_after = db.execute(
                text(
                    """
                    SELECT COUNT(*) AS n,
                           COUNT(DISTINCT pre_match_payload_sha256) AS hashes
                    FROM cecchino_lab_historical_match_snapshots
                    WHERE run_id = 15
                    """
                )
            ).mappings().one()
            if dict(snap_hash_after) != dict(snap_hash):
                errors.append("run15_mutated_after_export")

            if errors:
                print("GATE FAILED:")
                for e in errors:
                    print(" -", e)
                return 1

            print("GATE PASSED")
            print("metadata keys:", list(info["metadata"].keys()))
            return 0


if __name__ == "__main__":
    raise SystemExit(main())
