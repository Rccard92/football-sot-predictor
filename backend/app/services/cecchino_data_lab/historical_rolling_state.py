"""Rolling state incrementale per Historical Scan V4 (anti-leakage, order-independent)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from types import SimpleNamespace
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.cecchino_lab_historical_match_snapshot import CecchinoLabHistoricalMatchSnapshot
from app.services.cecchino.cecchino_goal_intensity_v5_candidate_indices import TrainEcdf
from app.services.cecchino.cecchino_goal_intensity_v5_preview import BUNDLE_FEATURE_KEYS
from app.services.cecchino_data_lab.historical_context_builder import (
    build_lab_prematch_contexts,
    prior_proxies_strict,
    sort_proxies,
)
from app.services.cecchino_data_lab.historical_eligibility import ELIGIBLE_CORE
from app.services.cecchino_data_lab.historical_kickoff_group import group_work_by_kickoff

CACHE_STRATEGY_VERSION = "cecchino_lab_rolling_state_v1"


@dataclass
class PriorModuleRow:
    kickoff_at: datetime | None
    lab_match_id: int
    gi_feature_row: dict[str, Any]
    kpi_panel: dict[str, Any]


@dataclass
class RunPriorModuleCache:
    """Cache incrementale eligible_core per Goal Intensity ECDF (cross-campionato)."""

    rows: list[PriorModuleRow] = field(default_factory=list)

    def gi_rows_before(self, before_kickoff: datetime | None) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for row in self.rows:
            if before_kickoff is not None and row.kickoff_at is not None:
                if not (row.kickoff_at < before_kickoff):
                    continue
            out.append(row.gi_feature_row)
        return out

    def append_eligible(
        self,
        *,
        kickoff_at: datetime | None,
        lab_match_id: int,
        gi_feature_row: dict[str, Any] | None,
        kpi_panel: dict[str, Any] | None,
    ) -> None:
        if not isinstance(gi_feature_row, dict) or not gi_feature_row.get("features"):
            return
        self.rows.append(
            PriorModuleRow(
                kickoff_at=kickoff_at,
                lab_match_id=int(lab_match_id),
                gi_feature_row=gi_feature_row,
                kpi_panel=kpi_panel if isinstance(kpi_panel, dict) else {},
            )
        )

    @classmethod
    def rebuild_from_db(cls, db: Session, *, run_id: int) -> RunPriorModuleCache:
        cache = cls()
        q = (
            select(
                CecchinoLabHistoricalMatchSnapshot.kickoff_at,
                CecchinoLabHistoricalMatchSnapshot.lab_match_id,
                CecchinoLabHistoricalMatchSnapshot.goal_intensity_compatibility_json,
                CecchinoLabHistoricalMatchSnapshot.historical_kpi_json,
            )
            .where(
                CecchinoLabHistoricalMatchSnapshot.run_id == run_id,
                CecchinoLabHistoricalMatchSnapshot.historical_eligibility_status == ELIGIBLE_CORE,
            )
            .order_by(
                CecchinoLabHistoricalMatchSnapshot.kickoff_at.asc(),
                CecchinoLabHistoricalMatchSnapshot.lab_match_id.asc(),
            )
        )
        for kickoff_at, lab_match_id, gi_json, kpi_json in db.execute(q).all():
            gi = gi_json if isinstance(gi_json, dict) else {}
            feat = gi.get("feature_row_for_profile")
            cache.append_eligible(
                kickoff_at=kickoff_at,
                lab_match_id=int(lab_match_id),
                gi_feature_row=feat if isinstance(feat, dict) else None,
                kpi_panel=kpi_json if isinstance(kpi_json, dict) else None,
            )
        return cache


@dataclass
class GiEcdfAccumulator:
    """ECDF incrementale — evita refit O(n²) su prior rows."""

    _values: dict[str, list[float]] = field(default_factory=dict)

    def ingest_feature_row(self, row: dict[str, Any]) -> None:
        feats = row.get("features") if isinstance(row, dict) else None
        if not isinstance(feats, dict):
            return
        for key in BUNDLE_FEATURE_KEYS:
            v = feats.get(key)
            if v is None:
                continue
            try:
                self._values.setdefault(key, []).append(float(v))
            except (TypeError, ValueError):
                continue

    def ecdfs(self) -> dict[str, TrainEcdf]:
        return {k: TrainEcdf(list(vals)) for k, vals in self._values.items()}

    def train_n(self) -> int:
        if not self._values:
            return 0
        return max(len(v) for v in self._values.values())


class CompetitionRollingState:
    """Storico committed per competizione — same-kickoff safe."""

    def __init__(self, *, competition_name: str, all_proxies: list[SimpleNamespace]) -> None:
        self.competition_name = competition_name
        self._all = sort_proxies(list(all_proxies))
        self._committed: list[SimpleNamespace] = []

    def contexts_for(self, target: SimpleNamespace):
        ordered = sort_proxies(self._committed + [target])
        return build_lab_prematch_contexts(competition_ordered=ordered, target=target)

    def priors_for(self, target: SimpleNamespace) -> list[SimpleNamespace]:
        return prior_proxies_strict(self._committed, target)

    def commit_group(self, proxies: list[SimpleNamespace]) -> None:
        self._committed = sort_proxies(self._committed + list(proxies))

    @property
    def all_proxies(self) -> list[SimpleNamespace]:
        return list(self._all)


class GlobalRollingStateRegistry:
    """Registry rolling state per competizione + cache prior globale."""

    def __init__(self) -> None:
        self.competitions: dict[str, CompetitionRollingState] = {}
        self.prior_cache = RunPriorModuleCache()
        self.gi_ecdf = GiEcdfAccumulator()

    def get_competition(self, name: str) -> CompetitionRollingState | None:
        return self.competitions.get(name)

    def register_competition(self, name: str, proxies: list[SimpleNamespace]) -> None:
        if name not in self.competitions:
            self.competitions[name] = CompetitionRollingState(
                competition_name=name,
                all_proxies=proxies,
            )

    @classmethod
    def from_resume(
        cls,
        db: Session,
        *,
        run_id: int,
        comp_proxies: dict[str, list],
        complete_lab_match_ids: set[int] | None = None,
    ) -> GlobalRollingStateRegistry:
        """Rebuild da snapshot di gruppi kickoff completi soltanto."""
        reg = cls()
        reg.prior_cache = RunPriorModuleCache.rebuild_from_db(db, run_id=run_id)
        for row in reg.prior_cache.rows:
            reg.gi_ecdf.ingest_feature_row(row.gi_feature_row)

        q = (
            select(
                CecchinoLabHistoricalMatchSnapshot.competition_name,
                CecchinoLabHistoricalMatchSnapshot.lab_match_id,
                CecchinoLabHistoricalMatchSnapshot.kickoff_at,
            )
            .where(CecchinoLabHistoricalMatchSnapshot.run_id == run_id)
            .order_by(
                CecchinoLabHistoricalMatchSnapshot.kickoff_at.asc(),
                CecchinoLabHistoricalMatchSnapshot.lab_match_id.asc(),
            )
        )
        rows = db.execute(q).all()
        if complete_lab_match_ids is not None:
            rows = [r for r in rows if int(r[1]) in complete_lab_match_ids]

        grouped: list[list[tuple[str, int, datetime | None]]] = group_work_by_kickoff(
            rows,
            kickoff_at_getter=lambda r: r[2],
        )
        for group in grouped:
            by_comp: dict[str, list[SimpleNamespace]] = {}
            for comp_name, lab_match_id, _kickoff_at in group:
                reg.register_competition(str(comp_name), comp_proxies.get(str(comp_name), []))
                state = reg.competitions[str(comp_name)]
                proxy = next((p for p in state.all_proxies if int(p.id) == int(lab_match_id)), None)
                if proxy is None:
                    continue
                by_comp.setdefault(str(comp_name), []).append(proxy)
            for comp_name, proxies in by_comp.items():
                state = reg.competitions.get(comp_name)
                if state and proxies:
                    state.commit_group(proxies)
        return reg
