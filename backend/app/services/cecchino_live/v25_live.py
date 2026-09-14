"""Cecchino V2.5 sulle partite del giorno: stessi moduli della RUN V2.5, storico dal database live.

Differenze dal replay storico (dichiarate, non nascoste):
- lo storico e' quello ingerito per la competizione e stagione (tabella fixtures), non il Lab;
- le quote book sono quelle del pannello KPI di Cecchino Today (Betfair), non Bet365 storico;
- la calibrazione dell'Acquistabilita' e' quella stimata sulle RUN V2.5 storiche, congelata
  all'avvio del processo.
"""

from __future__ import annotations

import threading
from datetime import datetime
from types import SimpleNamespace
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.constants import FINISHED_STATUSES
from app.models import Fixture
from app.services.cecchino_data_lab.historical_context_builder import build_lab_prematch_contexts
from app.services.cecchino_data_lab.run_v2.constants import CORE_MARKET_BY_KEY
from app.services.cecchino_v25.constants import ENGINE_VERSION, RUN_V25_VERSION
from app.services.cecchino_v25.executor import _add_stored_rows
from app.services.cecchino_v25.league import build_reference, counts_from_matches
from app.services.cecchino_v25.purchasability import PurchasabilityCalibrator

_calibrator: PurchasabilityCalibrator | None = None
_calibrator_lock = threading.Lock()


def _proxy(f: Fixture) -> SimpleNamespace:
    return SimpleNamespace(
        id=int(f.id),
        home_team_id=int(f.home_team_id),
        away_team_id=int(f.away_team_id),
        goals_home=f.goals_home,
        goals_away=f.goals_away,
        kickoff_at=f.kickoff_at,
        match_date=f.kickoff_at.date() if f.kickoff_at else None,
        match_time=None,
        source_row_number=int(f.id),
        raw_json=f.raw_json if isinstance(f.raw_json, dict) else {},
    )


def live_calibrator(db: Session) -> PurchasabilityCalibrator:
    """Calibrazione Acquistabilita' dalle RUN V2.5 storiche del motore corrente (tutte le stagioni)."""
    global _calibrator
    with _calibrator_lock:
        if _calibrator is not None:
            return _calibrator
        from sqlalchemy import text

        cal = PurchasabilityCalibrator()
        run_ids = db.execute(
            text(
                """
                SELECT DISTINCT ON (module_policy_json->>'season_label') id
                FROM cecchino_run_v2_runs
                WHERE run_version = :v AND module_policy_json->>'engine_version' = :e
                  AND status IN ('completed', 'completed_with_warnings')
                ORDER BY module_policy_json->>'season_label', id DESC
                """
            ),
            {"v": RUN_V25_VERSION, "e": ENGINE_VERSION},
        ).scalars().all()
        for rid in sorted(run_ids):
            _add_stored_rows(db, cal, run_id=int(rid), lab_match_ids=None)
        cal.refresh()
        _calibrator = cal
        return cal


def history_for(db: Session, target: Fixture) -> list[SimpleNamespace]:
    """Partite finite della stessa competizione e stagione, prima del calcio d'inizio."""
    rows = db.scalars(
        select(Fixture).where(
            Fixture.competition_id == target.competition_id,
            Fixture.season_id == target.season_id,
            Fixture.status.in_(FINISHED_STATUSES),
            Fixture.kickoff_at < target.kickoff_at,
            Fixture.id != target.id,
        )
    ).all()
    return [_proxy(f) for f in rows]


def strict_quotes_from_kpi(kpi_panel: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for row in (kpi_panel or {}).get("rows") or []:
        key = row.get("market_key")
        if key not in CORE_MARKET_BY_KEY:
            continue
        derived = bool(row.get("derived_quote") or row.get("not_real_book_quote") or row.get("book_fallback_used"))
        out[str(key)] = {"value": row.get("quota_book"), "is_derived": derived}
    return out


def compute_v25_live(db: Session, target: Fixture, kpi_panel: dict[str, Any] | None) -> dict[str, Any]:
    from app.services.cecchino_v25.executor import compute_prematch_v25

    history = history_for(db, target)
    target_proxy = _proxy(target)
    ordered = sorted(history + [target_proxy], key=lambda p: (p.kickoff_at or datetime.min, p.id))
    contexts = build_lab_prematch_contexts(competition_ordered=ordered, target=target_proxy)
    league = build_reference(current=counts_from_matches(history), previous=None, global_pool=None)
    quote_bundle = {"strict_by_market": strict_quotes_from_kpi(kpi_panel)}
    item = SimpleNamespace(match=SimpleNamespace(home_team="home", away_team="away", kickoff_at=target.kickoff_at))
    pre = compute_prematch_v25(
        item=item,  # type: ignore[arg-type]
        contexts=contexts,
        league=league,
        quote_bundle=quote_bundle,
        calibrator=live_calibrator(db),
    )
    pre["history_matches"] = len(history)
    pre["league_reference"] = league.to_dict()
    return pre
