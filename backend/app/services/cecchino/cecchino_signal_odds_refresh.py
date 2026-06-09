"""Refresh offline quote book segnali da KPI salvati — Cecchino Fase 42."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.cecchino_signal_activation import CecchinoSignalActivation
from app.models.cecchino_today_fixture import CecchinoTodayFixture
from app.services.cecchino.cecchino_signal_target_mapping import (
    market_key_for_signal_group,
)


def _num(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (TypeError, ValueError):
        return None


def _kpi_row_for_market(kpi_panel: dict[str, Any] | None, market_key: str) -> dict[str, Any] | None:
    if not kpi_panel or not isinstance(kpi_panel, dict):
        return None
    rows = kpi_panel.get("rows") or []
    if not isinstance(rows, list):
        return None
    for row in rows:
        if not isinstance(row, dict):
            continue
        if row.get("market_key") == market_key or row.get("segno") == market_key:
            return row
    return None


def resolve_kpi_odds_for_activation(
    kpi_panel: dict[str, Any] | None,
    *,
    signal_group: str,
    target_market_key: str | None = None,
) -> dict[str, Any]:
    """Risolve quote KPI per activation; lookup primario su target_market_key."""
    market_key = target_market_key or market_key_for_signal_group(signal_group)
    if not market_key:
        return {}
    row = _kpi_row_for_market(kpi_panel, market_key)
    if not row:
        return {}
    return {
        "quota_book": row.get("quota_book"),
        "quota_cecchino": row.get("quota_cecchino"),
        "prob_book": row.get("prob_book"),
        "prob_cecchino": row.get("prob_cecchino"),
        "edge_pct": row.get("edge_pct"),
        "rating": row.get("rating"),
    }


def apply_kpi_odds_to_activation(
    activation: CecchinoSignalActivation,
    kpi_panel: dict[str, Any] | None,
) -> bool:
    """Applica quote KPI all'activation. Ritorna True se almeno un campo aggiornato."""
    ctx = resolve_kpi_odds_for_activation(
        kpi_panel,
        signal_group=activation.signal_group,
        target_market_key=activation.target_market_key,
    )
    if not ctx:
        return False

    changed = False
    mapping = [
        ("quota_book", _num(ctx.get("quota_book"))),
        ("quota_cecchino", _num(ctx.get("quota_cecchino"))),
        ("prob_book", _num(ctx.get("prob_book"))),
        ("prob_cecchino", _num(ctx.get("prob_cecchino"))),
        ("edge_pct", _num(ctx.get("edge_pct"))),
    ]
    for attr, value in mapping:
        if getattr(activation, attr) != value:
            setattr(activation, attr, value)
            changed = True
    rating_val = ctx.get("rating")
    new_rating = int(rating_val) if rating_val is not None else None
    if activation.rating != new_rating:
        activation.rating = new_rating
        changed = True
    return changed


def refresh_activation_odds_from_kpi(
    db: Session,
    *,
    date_from: date,
    date_to: date,
    only_null: bool = False,
    only_current: bool = True,
) -> dict[str, int]:
    """Ripopola quote activation da kpi_panel_json fixture — zero API esterne."""
    activations = list(
        db.scalars(
            select(CecchinoSignalActivation).where(
                CecchinoSignalActivation.scan_date >= date_from,
                CecchinoSignalActivation.scan_date <= date_to,
                CecchinoSignalActivation.signal_value.is_(True),
            ),
        ).all(),
    )
    activations = [a for a in activations if isinstance(a, CecchinoSignalActivation)]
    if only_current:
        activations = [a for a in activations if a.is_current]

    fixture_ids = {int(a.today_fixture_id) for a in activations if a.today_fixture_id is not None}
    fixtures_by_id: dict[int, CecchinoTodayFixture] = {}
    if fixture_ids:
        fixtures = list(
            db.scalars(
                select(CecchinoTodayFixture).where(CecchinoTodayFixture.id.in_(fixture_ids)),
            ).all(),
        )
        fixtures_by_id = {
            int(f.id): f for f in fixtures if isinstance(f, CecchinoTodayFixture)
        }

    refreshed = 0
    still_missing = 0
    skipped_no_kpi = 0

    for activation in activations:
        if only_null and activation.quota_book is not None:
            continue
        fixture = fixtures_by_id.get(int(activation.today_fixture_id))
        if fixture is None:
            still_missing += 1
            continue
        kpi_panel = fixture.kpi_panel_json if isinstance(fixture.kpi_panel_json, dict) else None
        if not kpi_panel:
            skipped_no_kpi += 1
            continue
        if apply_kpi_odds_to_activation(activation, kpi_panel):
            refreshed += 1
        if activation.quota_book is None:
            still_missing += 1

    if refreshed:
        db.flush()
    return {
        "odds_refreshed": refreshed,
        "odds_still_missing": still_missing,
        "odds_skipped_no_kpi": skipped_no_kpi,
    }
