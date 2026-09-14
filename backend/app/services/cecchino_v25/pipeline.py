"""Pipeline completa V2.5, eseguita una sola volta alla fine dello sviluppo dei moduli.

1. RUN V2.5 stagione per stagione, in ordine: 2021/22, 2022/23, 2023/24, 2024/25, 2025/26
   (ogni stagione usa la calibrazione acquistabilita' della precedente);
2. ricerca pattern sul 2021/22 (stesso motore e stesse regole della V2, quota di chiusura);
3. verifica fuori campione su 2022/23, 2023/24, 2024/25 e 2025/26, in quest'ordine;
4. calcolo Master Pattern V2.5 (pattern vincenti 4 stagioni su 4).

Ogni passo gia' completato viene riusato: la pipeline si puo' rilanciare dopo un'interruzione.
"""

from __future__ import annotations

import logging
from typing import Any, Callable

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services.cecchino_v25.constants import RUN_V25_CONFIRM_TOKEN, RUN_V25_VERSION

logger = logging.getLogger(__name__)

SEASONS: tuple[str, ...] = ("2021/2022", "2022/2023", "2023/2024", "2024/2025", "2025/2026")
DISCOVERY_SEASON = SEASONS[0]
LOCKBOX_SEASON = "2025/2026"


def _completed_run(db: Session, season: str) -> int | None:
    return db.execute(
        text(
            """
            SELECT id FROM cecchino_run_v2_runs
            WHERE run_version = :v AND module_policy_json->>'season_label' = :s
              AND status IN ('completed', 'completed_with_warnings')
            ORDER BY id DESC LIMIT 1
            """
        ),
        {"v": RUN_V25_VERSION, "s": season},
    ).scalar()


def _completed_insight(db: Session, run_id: int) -> int | None:
    return db.execute(
        text(
            """
            SELECT id FROM cecchino_run_v2_pattern_insight_runs
            WHERE run_v2_run_id = :rid AND status = 'completed' AND odds_mode = 'closing'
            ORDER BY id DESC LIMIT 1
            """
        ),
        {"rid": run_id},
    ).scalar()


def _completed_validation(db: Session, insight_id: int, run_id: int) -> int | None:
    return db.execute(
        text(
            """
            SELECT id FROM cecchino_run_v2_pattern_validation_runs
            WHERE insight_run_id = :iid AND run_v2_run_id = :rid AND status = 'completed'
            ORDER BY id DESC LIMIT 1
            """
        ),
        {"iid": insight_id, "rid": run_id},
    ).scalar()


def run_full_pipeline(db: Session, log: Callable[[str], None] = print) -> dict[str, Any]:
    from app.services.cecchino_data_lab.run_v2_pattern_insight_service import start_pattern_insight_run
    from app.services.cecchino_data_lab.run_v2_pattern_validation_service import start_validation
    from app.services.cecchino_v25.run_service import start_run_v25
    from app.services.master_patterns.constants import MODEL_V25
    from app.services.master_patterns.service import start_build

    out: dict[str, Any] = {"runs": {}, "validations": {}}
    for season in SEASONS:
        run_id = _completed_run(db, season)
        if run_id is None:
            log(f"RUN V2.5 {season}: avvio")
            result = start_run_v25(db, confirm=RUN_V25_CONFIRM_TOKEN, season=season, background=False)
            log(f"RUN V2.5 {season}: {result['status']} ({result['matches_processed']} partite)")
            run_id = _completed_run(db, season)
            if run_id is None:
                raise RuntimeError(f"RUN V2.5 {season} non completata: {result.get('error')}")
        else:
            log(f"RUN V2.5 {season}: gia' completata (#{run_id})")
        out["runs"][season] = int(run_id)

    discovery_run = out["runs"][DISCOVERY_SEASON]
    insight_id = _completed_insight(db, discovery_run)
    if insight_id is None:
        log("Ricerca pattern 2021/22: avvio")
        insight = start_pattern_insight_run(db, run_v2_run_id=discovery_run, spawn=False)
        log(f"Ricerca pattern 2021/22: {insight['status']} {insight.get('summary')}")
        insight_id = _completed_insight(db, discovery_run)
        if insight_id is None:
            raise RuntimeError(f"Ricerca pattern non completata: {insight.get('error')}")
    out["insight_run_id"] = int(insight_id)

    for season in SEASONS[1:]:
        run_id = out["runs"][season]
        vid = _completed_validation(db, int(insight_id), run_id)
        if vid is None:
            log(f"Verifica pattern {season}: avvio")
            v = start_validation(
                db,
                run_v2_run_id=run_id,
                insight_run_id=int(insight_id),
                final_lockbox_test=(season == LOCKBOX_SEASON),
                spawn=False,
            )
            log(f"Verifica pattern {season}: {v['status']} {v.get('summary')}")
            vid = _completed_validation(db, int(insight_id), run_id)
            if vid is None:
                raise RuntimeError(f"Verifica {season} non completata: {v.get('error')}")
        out["validations"][season] = int(vid)

    log("Master Pattern V2.5: calcolo")
    build = start_build(db, MODEL_V25, spawn=False)
    log(f"Master Pattern V2.5: {build['status']} {(build.get('summary') or {}).get('winners')} vincenti")
    out["master_build"] = build
    return out
