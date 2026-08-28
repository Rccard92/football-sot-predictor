"""Criteri run canonica Pattern Lab — READ-ONLY, no Historical Scan."""

from __future__ import annotations

from typing import Any

from sqlalchemy import Select, or_, select
from sqlalchemy.orm import Session

from app.models.cecchino_lab_historical_match_snapshot import (
    CecchinoLabHistoricalMatchSnapshot,
)
from app.models.cecchino_lab_historical_scan_run import CecchinoLabHistoricalScanRun
from app.schemas.cecchino_purchasability_v35_v2 import PURCHASABILITY_V35_V2_FORMULA_VERSION
from app.services.cecchino_data_lab.constants import (
    HISTORICAL_QUOTE_POLICY_VERSION_V4,
    HISTORICAL_SCAN_VERSION_V4,
)
from app.services.cecchino_data_lab.historical_purchasability_v36_adapter import (
    MODULE_VERSION as PURCH_V36_MODULE_VERSION,
)
from app.services.cecchino_data_lab.historical_scan_service import run_to_dict

CANONICAL_PURCHASABILITY_POLICY = "historical_v4_v35_v2_canonical"
CANONICAL_SOURCE_REVISION_STATUS = "resolved"
CANONICAL_RUN_SCOPE = "full"


def quote_policy_version(run: CecchinoLabHistoricalScanRun | dict[str, Any]) -> str | None:
    if isinstance(run, dict):
        qp = run.get("quote_policy_json") or run.get("quote_policy") or {}
    else:
        qp = run.quote_policy_json if isinstance(run.quote_policy_json, dict) else {}
    if not isinstance(qp, dict):
        return None
    ver = qp.get("version") or qp.get("quote_policy_version")
    return str(ver) if ver else None


def _module_policy(run: CecchinoLabHistoricalScanRun) -> dict[str, Any]:
    return run.module_policy_json if isinstance(run.module_policy_json, dict) else {}


def _run_scope(run: CecchinoLabHistoricalScanRun) -> str:
    policy = _module_policy(run)
    return str(policy.get("run_scope") or "full")


def _is_pilot_or_partial(run: CecchinoLabHistoricalScanRun) -> bool:
    policy = _module_policy(run)
    scope = _run_scope(run)
    return scope in ("pilot", "balanced_pilot") or bool(policy.get("is_partial_run"))


def _status_completed(status: str | None) -> bool:
    return str(status or "").startswith("completed")


def runs_with_purchasability_v36(
    db: Session, run_ids: list[int]
) -> set[int]:
    """Run con almeno uno snapshot che espone il blocco Acquistabilità V3.6."""
    if not run_ids:
        return set()
    module_path = CecchinoLabHistoricalMatchSnapshot.purchasability_compatibility_json.op(
        "->>"
    )("module_version")
    formula_path = CecchinoLabHistoricalMatchSnapshot.purchasability_compatibility_json.op(
        "->>"
    )("formula_version")
    q: Select[Any] = (
        select(CecchinoLabHistoricalMatchSnapshot.run_id)
        .where(
            CecchinoLabHistoricalMatchSnapshot.run_id.in_(run_ids),
            CecchinoLabHistoricalMatchSnapshot.purchasability_compatibility_json.isnot(None),
            or_(
                module_path == PURCH_V36_MODULE_VERSION,
                formula_path == PURCHASABILITY_V35_V2_FORMULA_VERSION,
            ),
        )
        .distinct()
    )
    return {int(x) for x in db.scalars(q).all()}


def runs_with_purchasability_v36_scores(
    db: Session, run_ids: list[int]
) -> set[int]:
    """Run con almeno uno score V3.6 valorizzato su snapshot eligible_core.

    La sola presenza del blocco JSON non basta per la canonicità Pattern Lab.
    """
    if not run_ids:
        return set()
    from sqlalchemy import bindparam, text

    stmt = text(
        """
        SELECT DISTINCT s.run_id
        FROM cecchino_lab_historical_match_snapshots s
        WHERE s.run_id IN :run_ids
          AND s.historical_eligibility_status = 'eligible_core'
          AND s.purchasability_compatibility_json IS NOT NULL
          AND EXISTS (
            SELECT 1
            FROM jsonb_array_elements(
              COALESCE(s.purchasability_compatibility_json->'markets', '[]'::jsonb)
            ) AS m
            WHERE m->>'score' IS NOT NULL
              AND m->>'score' <> 'null'
          )
        """
    ).bindparams(bindparam("run_ids", expanding=True))
    rows = db.execute(stmt, {"run_ids": [int(x) for x in run_ids]}).all()
    return {int(r[0]) for r in rows}


def evaluate_canonical_flags(
    run: CecchinoLabHistoricalScanRun,
    *,
    has_v36: bool,
    has_v36_scores: bool = False,
) -> dict[str, Any]:
    """Valuta i criteri canonici senza query aggiuntive."""
    status_ok = _status_completed(run.status)
    scope = _run_scope(run)
    scope_ok = scope == CANONICAL_RUN_SCOPE and not _is_pilot_or_partial(run)
    scan_ok = str(run.scan_version or "") == HISTORICAL_SCAN_VERSION_V4
    quote_ok = quote_policy_version(run) == HISTORICAL_QUOTE_POLICY_VERSION_V4
    revision_ok = str(getattr(run, "source_revision_status", None) or "") == (
        CANONICAL_SOURCE_REVISION_STATUS
    )
    policy = _module_policy(run)
    policy_ok = str(policy.get("purchasability") or "") == CANONICAL_PURCHASABILITY_POLICY
    v36_ok = bool(has_v36) and bool(has_v36_scores)
    incomplete_v36 = bool(has_v36) and not bool(has_v36_scores)
    is_canonical = bool(
        status_ok
        and scope_ok
        and scan_ok
        and quote_ok
        and revision_ok
        and v36_ok
    )
    return {
        "is_canonical": is_canonical,
        "is_pilot": _is_pilot_or_partial(run),
        "is_legacy": not is_canonical,
        "incomplete_v36": incomplete_v36,
        "canonical_checks": {
            "status_completed": status_ok,
            "run_scope_full": scope_ok,
            "scan_version_v4": scan_ok,
            "quote_policy_bet365_pre_reference_v1": quote_ok,
            "source_revision_resolved": revision_ok,
            "purchasability_v36_present": bool(has_v36),
            "purchasability_v36_scores_present": bool(has_v36_scores),
            "purchasability_policy_v4": policy_ok,
        },
        "quote_policy_version": quote_policy_version(run),
        "source_revision_status": getattr(run, "source_revision_status", None),
        "run_scope": scope,
    }


def list_pattern_lab_runs(
    db: Session,
    *,
    season_label: str | None = None,
    include_legacy: bool = False,
    include_pilots: bool = False,
) -> list[dict[str, Any]]:
    """Lista run Pattern Lab. Default: solo canoniche FULL V4 + policy + V3.6."""
    show_non_canonical = bool(include_legacy or include_pilots)
    q = select(CecchinoLabHistoricalScanRun).order_by(
        CecchinoLabHistoricalScanRun.id.desc()
    )
    if season_label:
        q = q.where(CecchinoLabHistoricalScanRun.season_label == season_label)
    runs = list(db.scalars(q).all())
    completed = [r for r in runs if _status_completed(r.status)]
    completed_ids = [int(r.id) for r in completed]
    v36_ids = runs_with_purchasability_v36(db, completed_ids)
    v36_score_ids = runs_with_purchasability_v36_scores(db, completed_ids)

    out: list[dict[str, Any]] = []
    for run in completed:
        flags = evaluate_canonical_flags(
            run,
            has_v36=int(run.id) in v36_ids,
            has_v36_scores=int(run.id) in v36_score_ids,
        )
        if not flags["is_canonical"] and not show_non_canonical:
            continue
        d = run_to_dict(run)
        out.append(
            {
                "run_id": d["id"],
                "season_label": d["season_label"],
                "status": d["status"],
                "scan_version": d["scan_version"],
                "run_scope": flags["run_scope"],
                "is_partial_run": d.get("is_partial_run"),
                "is_pilot": flags["is_pilot"],
                "is_canonical": flags["is_canonical"],
                "is_legacy": flags["is_legacy"],
                "incomplete_v36": flags.get("incomplete_v36"),
                "quote_policy_version": flags["quote_policy_version"],
                "source_revision_status": flags["source_revision_status"],
                "canonical_checks": flags["canonical_checks"],
                "matches_eligible_core": d.get("matches_eligible_core"),
                "matches_processed": d.get("matches_processed"),
                "completed_at": d.get("completed_at"),
                "source_git_commit": d.get("source_git_commit"),
            }
        )
    return out


def filter_options_for_runs(db: Session, run_ids: list[int]) -> dict[str, Any]:
    """Valori distinct da snapshot/market delle run selezionate (read-only)."""
    from app.models.cecchino_lab_historical_market_result import (
        CecchinoLabHistoricalMarketResult,
    )
    from app.services.cecchino.cecchino_kpi_panel_v2_betfair import KPI_V2_ROW_DEFS
    from app.services.cecchino_data_lab.historical_analytics_agg import (
        BALANCE_CANONICAL_PILLARS,
        BALANCE_PILLAR_LABELS,
        GI_PILLARS,
        GI_PILLAR_LABELS,
    )

    if not run_ids:
        return {
            "competitions": [],
            "markets": [],
            "balance_classes": [],
            "goal_final_classes": [],
            "purchasability_v36_classes": [],
            "purchasability_v36_statuses": [],
            "purchasability_v36_gates": [],
            "consensus_statuses": [],
            "balance_pillars": [
                {"key": k, "label": BALANCE_PILLAR_LABELS.get(k, k)}
                for k in BALANCE_CANONICAL_PILLARS
            ],
            "goal_pillars": [
                {"key": k, "label": GI_PILLAR_LABELS.get(k, k)} for k in GI_PILLARS
            ],
            "signal_columns": ["D", "E", "F", "G"],
        }

    comps = sorted(
        {
            str(x)
            for x in db.scalars(
                select(CecchinoLabHistoricalMatchSnapshot.competition_name)
                .where(CecchinoLabHistoricalMatchSnapshot.run_id.in_(run_ids))
                .distinct()
            ).all()
            if x
        }
    )
    market_rows = db.execute(
        select(
            CecchinoLabHistoricalMarketResult.market_key,
            CecchinoLabHistoricalMarketResult.market_label,
        )
        .where(CecchinoLabHistoricalMarketResult.run_id.in_(run_ids))
        .distinct()
    ).all()
    label_by_key = {k: lab for k, lab in KPI_V2_ROW_DEFS}
    markets_map: dict[str, str] = {}
    for mk, lab in market_rows:
        key = str(mk)
        markets_map[key] = str(lab or label_by_key.get(key) or key)
    for mk, lab in KPI_V2_ROW_DEFS:
        markets_map.setdefault(mk, lab)
    markets = [{"key": k, "label": markets_map[k]} for k in sorted(markets_map.keys())]

    # Distinct classi da un sample di snapshot (evita full table scan pesante)
    sample_ids = list(
        db.scalars(
            select(CecchinoLabHistoricalMatchSnapshot.id)
            .where(CecchinoLabHistoricalMatchSnapshot.run_id.in_(run_ids))
            .order_by(CecchinoLabHistoricalMatchSnapshot.id.asc())
            .limit(400)
        ).all()
    )
    balance_classes: set[str] = set()
    goal_classes: set[str] = set()
    purch_classes: set[str] = set()
    purch_statuses: set[str] = set()
    purch_gates: set[str] = set()
    consensus_statuses: set[str] = set()

    if sample_ids:
        snaps = db.scalars(
            select(CecchinoLabHistoricalMatchSnapshot).where(
                CecchinoLabHistoricalMatchSnapshot.id.in_(sample_ids)
            )
        ).all()
        for snap in snaps:
            bal = snap.balance_v5_json if isinstance(snap.balance_v5_json, dict) else {}
            struct = bal.get("structural_summary") if isinstance(bal, dict) else {}
            if isinstance(struct, dict) and struct.get("class"):
                balance_classes.add(str(struct["class"]))
            gi = (
                snap.goal_intensity_compatibility_json
                if isinstance(snap.goal_intensity_compatibility_json, dict)
                else {}
            )
            final = gi.get("final_class") if isinstance(gi, dict) else {}
            if isinstance(final, dict):
                key = final.get("key") or final.get("label")
                if key:
                    goal_classes.add(str(key))
            purch = (
                snap.purchasability_compatibility_json
                if isinstance(snap.purchasability_compatibility_json, dict)
                else {}
            )
            for mk in purch.get("markets") or []:
                if not isinstance(mk, dict):
                    continue
                if mk.get("class"):
                    purch_classes.add(str(mk["class"]))
                if mk.get("status"):
                    purch_statuses.add(str(mk["status"]))
                if mk.get("gate_status"):
                    purch_gates.add(str(mk["gate_status"]))

        markets_sample = db.scalars(
            select(CecchinoLabHistoricalMarketResult)
            .where(CecchinoLabHistoricalMarketResult.match_snapshot_id.in_(sample_ids))
            .limit(2000)
        ).all()
        for m in markets_sample:
            src = m.signal_sources_json if isinstance(m.signal_sources_json, dict) else {}
            st = src.get("acquisition_status")
            if st:
                consensus_statuses.add(str(st))

    return {
        "competitions": comps,
        "markets": markets,
        "balance_classes": sorted(balance_classes),
        "goal_final_classes": sorted(goal_classes),
        "purchasability_v36_classes": sorted(purch_classes),
        "purchasability_v36_statuses": sorted(purch_statuses),
        "purchasability_v36_gates": sorted(purch_gates),
        "consensus_statuses": sorted(consensus_statuses),
        "balance_pillars": [
            {"key": k, "label": BALANCE_PILLAR_LABELS.get(k, k)}
            for k in BALANCE_CANONICAL_PILLARS
        ],
        "goal_pillars": [
            {"key": k, "label": GI_PILLAR_LABELS.get(k, k)} for k in GI_PILLARS
        ],
        "signal_columns": ["D", "E", "F", "G"],
    }
