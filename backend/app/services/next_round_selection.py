"""Selezione prossimo turno basata su fixture future eleggibili (multi-campionato)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from app.core.constants import fixture_eligible_for_upcoming_sot
from app.models import Fixture
from app.services.sot_prediction_service import _fixture_round_display

FALLBACK_ROUND_WARNING = (
    "Fallback next round: round iniziale senza fixture future, usata prima data futura disponibile."
)


def _round_key(fx: Fixture) -> str | None:
    label = _fixture_round_display(fx)
    if label:
        return str(label).strip()
    if fx.round and str(fx.round).strip():
        return str(fx.round).strip()
    return None


def _same_round(fx: Fixture, round_label: str | None) -> bool:
    if not round_label:
        return False
    return _round_key(fx) == round_label


@dataclass
class NextRoundSelectionResult:
    fixtures: list[Fixture]
    final_round: str | None
    future_fixtures_count: int
    initially_selected_round: str | None = None
    initially_selected_round_count: int = 0
    first_future_fixture_id: int | None = None
    first_future_kickoff: datetime | None = None
    first_future_round: str | None = None
    final_next_round_fixtures_count: int = 0
    fallback_used: bool = False
    warnings: list[str] = field(default_factory=list)
    error_code: str | None = None

    def as_log_dict(self, *, competition_id: int | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "competition_id": competition_id,
            "future_fixtures_count": self.future_fixtures_count,
            "initially_selected_round": self.initially_selected_round,
            "initially_selected_round_count": self.initially_selected_round_count,
            "first_future_fixture_id": self.first_future_fixture_id,
            "first_future_kickoff": self.first_future_kickoff.isoformat()
            if self.first_future_kickoff
            else None,
            "first_future_round": self.first_future_round,
            "final_selected_round": self.final_round,
            "final_next_round_fixtures_count": self.final_next_round_fixtures_count,
            "fallback_used": self.fallback_used,
        }
        if self.warnings:
            payload["warnings"] = list(self.warnings)
        if self.error_code:
            payload["error_code"] = self.error_code
        return payload


def _future_pool(fixtures: list[Fixture]) -> list[Fixture]:
    pool = [
        f
        for f in fixtures
        if fixture_eligible_for_upcoming_sot(f.status, f.kickoff_at)
    ]
    pool.sort(key=lambda f: (f.kickoff_at, int(f.id)))
    return pool


def select_next_round_fixtures(
    fixtures: list[Fixture],
    *,
    limit: int = 100,
    only_next_round: bool = True,
    fallback_batch_size: int = 10,
) -> NextRoundSelectionResult:
    pool = _future_pool(fixtures)
    future_count = len(pool)

    if not pool:
        return NextRoundSelectionResult(
            fixtures=[],
            final_round=None,
            future_fixtures_count=0,
            final_next_round_fixtures_count=0,
            error_code="no_future_fixtures",
        )

    cap = max(1, min(int(limit), 100))
    first_future = pool[0]
    first_id = int(first_future.id)
    first_kickoff = first_future.kickoff_at
    first_round = _round_key(first_future)

    if not only_next_round:
        selected = pool[:cap]
        final_round = _round_key(selected[0]) if selected else first_round
        return NextRoundSelectionResult(
            fixtures=selected,
            final_round=final_round,
            future_fixtures_count=future_count,
            first_future_fixture_id=first_id,
            first_future_kickoff=first_kickoff,
            first_future_round=first_round,
            final_next_round_fixtures_count=len(selected),
        )

    initially_selected_round = first_round
    selected = [f for f in pool if _same_round(f, initially_selected_round)]
    initially_selected_round_count = len(selected)
    warnings: list[str] = []
    fallback_used = False

    if not selected and initially_selected_round:
        fallback_used = True
        warnings.append(FALLBACK_ROUND_WARNING)
        alt_round = first_future.round
        if alt_round and str(alt_round).strip():
            initially_selected_round = str(alt_round).strip()
            selected = [f for f in pool if _same_round(f, initially_selected_round)]

    if not selected:
        d0 = first_kickoff.date()
        selected = [f for f in pool if f.kickoff_at.date() == d0]
        if selected and not fallback_used:
            fallback_used = True
            warnings.append(FALLBACK_ROUND_WARNING)

    if not selected:
        selected = pool[: max(1, min(int(fallback_batch_size), cap))]
        fallback_used = True
        if FALLBACK_ROUND_WARNING not in warnings:
            warnings.append(FALLBACK_ROUND_WARNING)

    selected = selected[:cap]
    final_round = _round_key(selected[0]) if selected else initially_selected_round

    return NextRoundSelectionResult(
        fixtures=selected,
        final_round=final_round,
        future_fixtures_count=future_count,
        initially_selected_round=initially_selected_round,
        initially_selected_round_count=initially_selected_round_count,
        first_future_fixture_id=first_id,
        first_future_kickoff=first_kickoff,
        first_future_round=first_round,
        final_next_round_fixtures_count=len(selected),
        fallback_used=fallback_used,
        warnings=warnings,
    )
