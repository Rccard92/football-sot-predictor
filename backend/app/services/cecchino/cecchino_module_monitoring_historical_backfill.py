"""Backfill storico unificato per il Monitoraggio Moduli (gate Fase 1/3).

Il servizio ricostruisce soltanto dati ottenibili da snapshot già persistiti.
Non effettua chiamate esterne e non promuove osservazioni storiche a coorti
prospettiche.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any, Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.cecchino_goal_intensity_v5_preview import (
    PREVIEW_BUNDLE_VERSION,
    CecchinoGoalIntensityV5PreviewBundle,
    CecchinoGoalIntensityV5PreviewSnapshot,
)
from app.models.cecchino_purchasability_evaluation import (
    DEFAULT_STAKE_UNITS,
    EVAL_LOST,
    EVAL_NOT_EVALUABLE,
    EVAL_PENDING,
    EVAL_RESULT_MISSING,
    EVAL_WON,
    SOURCE_LEGACY_BACKFILL,
    SOURCE_LEGACY_DERIVED,
    SOURCE_PROSPECTIVE,
    CecchinoPurchasabilityEvaluation,
)
from app.models.cecchino_signal_activation import CecchinoSignalActivation
from app.models.cecchino_today_fixture import (
    ELIGIBILITY_ELIGIBLE,
    CecchinoTodayFixture,
)
from app.schemas.cecchino_purchasability_preview import (
    PURCHASABILITY_CANDIDATE_VERSION,
    PURCHASABILITY_FEATURE_VERSION,
    PURCHASABILITY_SNAPSHOT_VERSION,
)
from app.services.cecchino.cecchino_balance_v5 import VERSION as BALANCE_V5_VERSION
from app.services.cecchino.cecchino_balance_v5_monitoring import (
    BALANCE_MONITORING_SNAPSHOT_VERSION,
    build_balance_monitoring_rows,
    resolve_balance_v5_monitoring_snapshot,
)
from app.services.cecchino.cecchino_monitoring_cohorts import (
    COHORT_HISTORICAL_DIAGNOSTIC,
    COHORT_HISTORICAL_PERSISTED_VERIFIED,
    COHORT_HISTORICAL_RECONSTRUCTED_VERIFIED,
    COHORT_PROSPECTIVE,
    COHORT_UNUSABLE,
    normalize_cohort,
    storage_cohort_for_purchasability,
)
from app.services.cecchino.cecchino_purchasability_audit import make_json_safe
from app.services.cecchino.cecchino_purchasability_fair_book import (
    resolve_fair_book_for_panel_rows,
)
from app.services.cecchino.cecchino_purchasability_snapshot import (
    build_candidate_and_compact_snapshot,
)
from app.services.cecchino.cecchino_purchasability_validation import (
    evaluate_purchasability_validation_for_fixture,
)

CECCHINO_MODULE_HISTORICAL_BACKFILL_VERSION = (
    "cecchino_module_historical_backfill_v1"
)
MODULE_HISTORICAL_BACKFILL_CONFIRM_TOKEN = (
    "IMPORT_CECCHINO_HISTORICAL_MONITORING"
)
VALID_MODULE_KEYS = frozenset(
    {"purchasability", "balance-v5", "goal-intensity-v5", "signals"}
)

_TIMESTAMP_FIELDS = (
    "odds_fetched_at",
    "fetched_at",
    "snapshot_at",
    "odds_cached_at",
    "last_betfair_refresh_at",
    "odds_updated_at",
)


def _as_date(value: date | datetime | str, field_name: str) -> date:
    """Converte una data API e produce un errore leggibile."""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} deve essere una data ISO valida") from exc


def _as_utc(value: Any) -> datetime | None:
    """Normalizza un timestamp in UTC senza inventare valori mancanti."""
    if value is None:
        return None
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, date):
        parsed = datetime.combine(value, datetime.min.time())
    else:
        try:
            parsed = datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
        except (TypeError, ValueError):
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _first_timestamp(payload: Any) -> datetime | None:
    """Cerca un timestamp noto nei metadati di uno snapshot."""
    if not isinstance(payload, dict):
        return None
    containers = [payload]
    for key in ("meta", "odds_meta", "snapshot_meta", "metadata"):
        nested = payload.get(key)
        if isinstance(nested, dict):
            containers.append(nested)
    for container in containers:
        for field in _TIMESTAMP_FIELDS:
            parsed = _as_utc(container.get(field))
            if parsed is not None:
                return parsed
    return None


def _fixture_snapshot_timestamp(row: CecchinoTodayFixture) -> datetime | None:
    """Legge il timestamp solo dagli snapshot pre-match persistiti."""
    return _first_timestamp(row.odds_snapshot_json) or _first_timestamp(
        row.kpi_panel_json
    )


def _fixture_timestamp_class(row: CecchinoTodayFixture) -> str:
    """Classifica la verificabilità temporale dello snapshot della fixture."""
    snapshot_at = _fixture_snapshot_timestamp(row)
    kickoff = _as_utc(getattr(row, "kickoff", None))
    if snapshot_at is None or kickoff is None:
        return "unverifiable"
    if snapshot_at < kickoff:
        return "verified_pre_match"
    return "post_kickoff"


def _normalise_modules(module_keys: Iterable[str] | str) -> list[str]:
    """Valida e de-duplica le chiavi preservando l'ordine richiesto."""
    raw = [module_keys] if isinstance(module_keys, str) else list(module_keys or [])
    result: list[str] = []
    unknown: list[str] = []
    for value in raw:
        key = str(value).strip().lower()
        if key not in VALID_MODULE_KEYS:
            unknown.append(key)
        elif key not in result:
            result.append(key)
    if unknown:
        raise ValueError(
            "module_keys non validi: "
            + ", ".join(unknown)
            + "; validi: "
            + ", ".join(sorted(VALID_MODULE_KEYS))
        )
    if not result:
        raise ValueError("module_keys non può essere vuoto")
    return result


def _fixtures(
    db: Session,
    *,
    date_from: date,
    date_to: date,
    competition_id: int | None,
) -> list[CecchinoTodayFixture]:
    query = select(CecchinoTodayFixture).where(
        CecchinoTodayFixture.scan_date >= date_from,
        CecchinoTodayFixture.scan_date <= date_to,
    )
    if competition_id is not None:
        query = query.where(
            CecchinoTodayFixture.competition_id == int(competition_id)
        )
    return list(
        db.scalars(
            query.order_by(
                CecchinoTodayFixture.scan_date, CecchinoTodayFixture.id
            )
        ).all()
    )


def _base_report(
    module_key: str,
    rows: list[CecchinoTodayFixture],
    *,
    date_from: date,
    date_to: date,
) -> dict[str, Any]:
    """Crea il contratto di conteggi comune a tutti i moduli."""
    eligible = [r for r in rows if r.eligibility_status == ELIGIBILITY_ELIGIBLE]
    exclusions = Counter(
        str(r.eligibility_status or "eligibility_unknown")
        for r in rows
        if r.eligibility_status != ELIGIBILITY_ELIGIBLE
    )
    return {
        "module_key": module_key,
        "total_fixtures": len(rows),
        "eligible_fixtures": len(eligible),
        "fixtures_with_kpi": sum(
            1 for r in eligible if isinstance(r.kpi_panel_json, dict)
        ),
        "fixtures_with_cecchino_output": sum(
            1 for r in eligible if isinstance(r.cecchino_output_json, dict)
        ),
        "fixtures_with_snapshot_timestamp": sum(
            1 for r in eligible if _fixture_snapshot_timestamp(r) is not None
        ),
        "verified_pre_match": sum(
            1 for r in eligible if _fixture_timestamp_class(r) == "verified_pre_match"
        ),
        "unverifiable_timestamps": sum(
            1 for r in eligible if _fixture_timestamp_class(r) == "unverifiable"
        ),
        "post_kickoff": sum(
            1 for r in eligible if _fixture_timestamp_class(r) == "post_kickoff"
        ),
        "results_available": sum(
            1
            for r in eligible
            if r.score_fulltime_home is not None
            and r.score_fulltime_away is not None
        ),
        "rows_generatable": 0,
        "already_present": 0,
        "new": 0,
        "updatable": 0,
        "duplicates": 0,
        "unusable": 0,
        "cohort_distribution": {},
        "exclusion_reasons": dict(exclusions),
        "first_date": (
            min((r.scan_date for r in rows), default=None).isoformat()
            if rows
            else None
        ),
        "last_date": (
            max((r.scan_date for r in rows), default=None).isoformat()
            if rows
            else None
        ),
        "requested_date_from": date_from.isoformat(),
        "requested_date_to": date_to.isoformat(),
        "source_versions": {},
    }


def _fixture_meta(row: CecchinoTodayFixture) -> dict[str, Any]:
    return {
        "today_fixture_id": int(row.id),
        "local_fixture_id": row.local_fixture_id,
        "provider_fixture_id": row.provider_fixture_id,
        "competition_id": row.competition_id,
        "scan_date": row.scan_date,
        "kickoff": row.kickoff,
        "country_name": row.country_name,
        "league_name": row.league_name,
        "home_team_name": row.home_team_name,
        "away_team_name": row.away_team_name,
    }


def _build_purchasability_snapshot(
    row: CecchinoTodayFixture,
) -> tuple[dict[str, Any] | None, str | None]:
    """Ricostruisce candidate e compatto esclusivamente in memoria."""
    timestamp_class = _fixture_timestamp_class(row)
    if timestamp_class == "post_kickoff":
        return None, "snapshot_post_kickoff"
    if not isinstance(row.kpi_panel_json, dict):
        return None, "kpi_panel_missing"
    snapshot_at = _fixture_snapshot_timestamp(row)
    try:
        _candidate, compact = build_candidate_and_compact_snapshot(
            kpi_panel=row.kpi_panel_json,
            fixture_meta=_fixture_meta(row),
            snapshot_info={
                "snapshot_at": snapshot_at,
                "snapshot_timestamp_verified": (
                    timestamp_class == "verified_pre_match"
                ),
            },
            context_meta=None,
            source_mode="historical_reconstruction",
        )
    except Exception as exc:
        return None, f"candidate_build_error:{type(exc).__name__}"
    if not isinstance(compact, dict):
        return None, "candidate_snapshot_invalid"
    compact["source_snapshot_at"] = (
        snapshot_at.isoformat() if snapshot_at is not None else None
    )
    compact["source_snapshot_verified"] = (
        timestamp_class == "verified_pre_match"
    )
    compact["source_snapshot_before_kickoff"] = (
        True if timestamp_class == "verified_pre_match" else None
    )
    return compact, None


def _eligible_purchasability_items(
    snapshot: dict[str, Any],
) -> list[dict[str, Any]]:
    items = snapshot.get("items")
    if not isinstance(items, list):
        return []
    result: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        market_key = str(
            item.get("market_key") or item.get("selection") or ""
        ).strip().upper()
        status = str(item.get("status") or "")
        if market_key and status in ("available", "partial") and item.get(
            "score"
        ) is not None:
            result.append(item)
    return result


def _current_evaluations(
    db: Session, fixture_id: int, candidate_version: str
) -> dict[str, list[CecchinoPurchasabilityEvaluation]]:
    grouped: dict[str, list[CecchinoPurchasabilityEvaluation]] = defaultdict(list)
    evaluations = db.scalars(
        select(CecchinoPurchasabilityEvaluation).where(
            CecchinoPurchasabilityEvaluation.today_fixture_id == fixture_id,
            CecchinoPurchasabilityEvaluation.candidate_version
            == candidate_version,
            CecchinoPurchasabilityEvaluation.is_current.is_(True),
        )
    ).all()
    for evaluation in evaluations:
        grouped[str(evaluation.market_key or "").strip().upper()].append(
            evaluation
        )
    return grouped


def _dec(value: Any, places: int = 4) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(round(float(value), places)))
    except (TypeError, ValueError):
        return None


def _int_or_none(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _panel_rows(panel: Any) -> list[dict[str, Any]]:
    if not isinstance(panel, dict) or not isinstance(panel.get("rows"), list):
        return []
    return [row for row in panel["rows"] if isinstance(row, dict)]


def _plan_purchasability(
    db: Session,
    rows: list[CecchinoTodayFixture],
    report: dict[str, Any],
    *,
    include_unverified_diagnostic: bool,
) -> dict[str, Any]:
    cohorts: Counter[str] = Counter()
    reasons: Counter[str] = Counter(report["exclusion_reasons"])
    for row in rows:
        if row.eligibility_status != ELIGIBILITY_ELIGIBLE:
            continue
        timestamp_class = _fixture_timestamp_class(row)
        if timestamp_class == "post_kickoff":
            cohorts[COHORT_UNUSABLE] += 1
            report["unusable"] += 1
            reasons["snapshot_post_kickoff"] += 1
            continue
        if timestamp_class == "unverifiable" and not include_unverified_diagnostic:
            reasons["unverified_diagnostic_disabled"] += 1
            continue
        snapshot, reason = _build_purchasability_snapshot(row)
        if snapshot is None:
            report["unusable"] += 1
            cohorts[COHORT_UNUSABLE] += 1
            reasons[reason or "candidate_unavailable"] += 1
            continue
        cohort = (
            COHORT_HISTORICAL_RECONSTRUCTED_VERIFIED
            if timestamp_class == "verified_pre_match"
            else COHORT_HISTORICAL_DIAGNOSTIC
        )
        cohorts[cohort] += 1
        items = _eligible_purchasability_items(snapshot)
        report["rows_generatable"] += len(items)
        candidate_version = str(
            snapshot.get("candidate_version")
            or PURCHASABILITY_CANDIDATE_VERSION
        )
        existing = _current_evaluations(db, int(row.id), candidate_version)
        for item in items:
            market_key = str(
                item.get("market_key") or item.get("selection")
            ).strip().upper()
            matches = existing.get(market_key, [])
            if matches:
                report["already_present"] += 1
                report["updatable"] += 1
                report["duplicates"] += max(0, len(matches) - 1)
            else:
                report["new"] += 1
    report["cohort_distribution"] = dict(cohorts)
    report["exclusion_reasons"] = dict(reasons)
    report["source_versions"] = {
        "snapshot": PURCHASABILITY_SNAPSHOT_VERSION,
        "feature": PURCHASABILITY_FEATURE_VERSION,
        "candidate": PURCHASABILITY_CANDIDATE_VERSION,
    }
    return report


def _plan_balance(
    rows: list[CecchinoTodayFixture], report: dict[str, Any]
) -> dict[str, Any]:
    cohorts: Counter[str] = Counter()
    reasons: Counter[str] = Counter(report["exclusion_reasons"])
    for row in rows:
        if row.eligibility_status != ELIGIBILITY_ELIGIBLE:
            continue
        resolved = resolve_balance_v5_monitoring_snapshot(row)
        if resolved.get("mode") == "unavailable":
            report["unusable"] += 1
            reasons["balance_snapshot_unavailable"] += 1
            cohorts[COHORT_UNUSABLE] += 1
            continue
        report["rows_generatable"] += 1
        report["already_present"] += int(resolved.get("mode") == "persisted")
        report["new"] += int(resolved.get("mode") != "persisted")
        cohort = normalize_cohort(resolved.get("source_cohort"))
        cohorts[str(cohort or COHORT_HISTORICAL_DIAGNOSTIC)] += 1
    report["cohort_distribution"] = dict(cohorts)
    report["exclusion_reasons"] = dict(reasons)
    report["source_versions"] = {
        "balance": BALANCE_V5_VERSION,
        "monitoring_snapshot": BALANCE_MONITORING_SNAPSHOT_VERSION,
    }
    report["note"] = (
        "Resolve-on-read: il backfill non persiste snapshot Balance."
    )
    return report


def _goal_snapshots(
    db: Session,
    *,
    date_from: date,
    date_to: date,
    competition_id: int | None,
) -> list[tuple[CecchinoGoalIntensityV5PreviewSnapshot, CecchinoGoalIntensityV5PreviewBundle]]:
    query = (
        select(
            CecchinoGoalIntensityV5PreviewSnapshot,
            CecchinoGoalIntensityV5PreviewBundle,
        )
        .join(
            CecchinoGoalIntensityV5PreviewBundle,
            CecchinoGoalIntensityV5PreviewBundle.id
            == CecchinoGoalIntensityV5PreviewSnapshot.bundle_id,
        )
        .where(
            CecchinoGoalIntensityV5PreviewSnapshot.scan_date >= date_from,
            CecchinoGoalIntensityV5PreviewSnapshot.scan_date <= date_to,
        )
    )
    if competition_id is not None:
        query = query.where(
            CecchinoGoalIntensityV5PreviewSnapshot.competition_id
            == int(competition_id)
        )
    return list(db.execute(query).all())


def _plan_goal(
    db: Session,
    rows: list[CecchinoTodayFixture],
    report: dict[str, Any],
    *,
    date_from: date,
    date_to: date,
    competition_id: int | None,
) -> dict[str, Any]:
    snapshots = _goal_snapshots(
        db,
        date_from=date_from,
        date_to=date_to,
        competition_id=competition_id,
    )
    cohorts: Counter[str] = Counter()
    versions: set[str] = set()
    with_timestamp = verified = unverifiable = post_kickoff = 0
    for snapshot, bundle in snapshots:
        versions.add(str(bundle.version))
        source_at = _as_utc(snapshot.source_snapshot_at)
        kickoff = _as_utc(snapshot.kickoff)
        frozen_at = _as_utc(bundle.frozen_at)
        if source_at is None:
            unverifiable += 1
            cohorts[COHORT_HISTORICAL_DIAGNOSTIC] += 1
        elif kickoff is not None and source_at >= kickoff:
            with_timestamp += 1
            post_kickoff += 1
            cohorts[COHORT_UNUSABLE] += 1
            report["unusable"] += 1
        elif kickoff is None:
            with_timestamp += 1
            unverifiable += 1
            cohorts[COHORT_HISTORICAL_DIAGNOSTIC] += 1
        elif frozen_at is not None and source_at > frozen_at:
            with_timestamp += 1
            verified += 1
            cohorts[COHORT_PROSPECTIVE] += 1
        else:
            with_timestamp += 1
            verified += 1
            cohorts[COHORT_HISTORICAL_PERSISTED_VERIFIED] += 1
    report["fixtures_with_snapshot_timestamp"] = with_timestamp
    report["verified_pre_match"] = verified
    report["unverifiable_timestamps"] = unverifiable
    report["post_kickoff"] = post_kickoff
    report["rows_generatable"] = len(snapshots)
    report["already_present"] = len(snapshots)
    report["new"] = 0
    report["cohort_distribution"] = dict(cohorts)
    report["source_versions"] = {
        "preview_model": PREVIEW_BUNDLE_VERSION,
        "bundle_versions": sorted(versions),
    }
    report["note"] = (
        "Solo snapshot esistenti; nessuna creazione o mutazione del bundle."
    )
    return report


def _signal_activations(
    db: Session,
    *,
    date_from: date,
    date_to: date,
    competition_id: int | None,
) -> list[CecchinoSignalActivation]:
    query = select(CecchinoSignalActivation).where(
        CecchinoSignalActivation.scan_date >= date_from,
        CecchinoSignalActivation.scan_date <= date_to,
        CecchinoSignalActivation.signal_value.is_(True),
    )
    if competition_id is not None:
        query = query.join(
            CecchinoTodayFixture,
            CecchinoTodayFixture.id
            == CecchinoSignalActivation.today_fixture_id,
        ).where(CecchinoTodayFixture.competition_id == int(competition_id))
    return list(db.scalars(query).all())


def _plan_signals(
    db: Session,
    report: dict[str, Any],
    *,
    date_from: date,
    date_to: date,
    competition_id: int | None,
) -> dict[str, Any]:
    activations = _signal_activations(
        db,
        date_from=date_from,
        date_to=date_to,
        competition_id=competition_id,
    )
    cohorts: Counter[str] = Counter()
    versions: set[str] = set()
    distinct_fixtures: set[int] = set()
    duplicates: Counter[tuple[Any, ...]] = Counter()
    with_timestamp = verified = unverifiable = post_kickoff = 0
    for activation in activations:
        distinct_fixtures.add(int(activation.today_fixture_id))
        if activation.weights_version:
            versions.add(str(activation.weights_version))
        created_at = _as_utc(getattr(activation, "created_at", None))
        kickoff = _as_utc(activation.kickoff)
        if created_at is None or kickoff is None:
            if created_at is not None:
                with_timestamp += 1
            unverifiable += 1
            cohorts[COHORT_HISTORICAL_DIAGNOSTIC] += 1
        elif created_at < kickoff:
            with_timestamp += 1
            verified += 1
            cohorts[COHORT_HISTORICAL_PERSISTED_VERIFIED] += 1
        else:
            with_timestamp += 1
            post_kickoff += 1
            cohorts[COHORT_UNUSABLE] += 1
            report["unusable"] += 1
        duplicates[
            (
                activation.today_fixture_id,
                activation.model_key,
                activation.signal_group,
                activation.source_column,
                activation.is_current,
            )
        ] += 1
    report["fixtures_with_snapshot_timestamp"] = with_timestamp
    report["verified_pre_match"] = verified
    report["unverifiable_timestamps"] = unverifiable
    report["post_kickoff"] = post_kickoff
    report["rows_generatable"] = len(activations)
    report["already_present"] = len(activations)
    report["duplicates"] = sum(max(0, count - 1) for count in duplicates.values())
    report["cohort_distribution"] = dict(cohorts)
    report["source_versions"] = {"weights_versions": sorted(versions)}
    report["distinct_fixtures_with_activations"] = len(distinct_fixtures)
    report["note"] = (
        "Solo ricontaggio delle attivazioni persistite; nessuna rigenerazione."
    )
    return report


def plan_module_historical_backfill(
    db: Session,
    *,
    module_keys: Iterable[str] | str,
    date_from: date,
    date_to: date,
    competition_id: int | None = None,
    include_unverified_diagnostic: bool = True,
) -> dict[str, Any]:
    """Pianifica il backfill in sola lettura, senza flush né commit."""
    modules = _normalise_modules(module_keys)
    start = _as_date(date_from, "date_from")
    end = _as_date(date_to, "date_to")
    if start > end:
        raise ValueError("date_from non può essere successiva a date_to")
    rows = _fixtures(
        db, date_from=start, date_to=end, competition_id=competition_id
    )
    reports: dict[str, dict[str, Any]] = {}
    for module_key in modules:
        report = _base_report(
            module_key, rows, date_from=start, date_to=end
        )
        if module_key == "purchasability":
            reports[module_key] = _plan_purchasability(
                db,
                rows,
                report,
                include_unverified_diagnostic=include_unverified_diagnostic,
            )
        elif module_key == "balance-v5":
            reports[module_key] = _plan_balance(rows, report)
        elif module_key == "goal-intensity-v5":
            reports[module_key] = _plan_goal(
                db,
                rows,
                report,
                date_from=start,
                date_to=end,
                competition_id=competition_id,
            )
        else:
            reports[module_key] = _plan_signals(
                db,
                report,
                date_from=start,
                date_to=end,
                competition_id=competition_id,
            )
    return make_json_safe(
        {
            "status": "planned",
            "version": CECCHINO_MODULE_HISTORICAL_BACKFILL_VERSION,
            "read_only": True,
            "module_keys": modules,
            "date_from": start.isoformat(),
            "date_to": end.isoformat(),
            "competition_id": competition_id,
            "include_unverified_diagnostic": include_unverified_diagnostic,
            "modules": reports,
        }
    )


def _upsert_purchasability_fixture(
    db: Session,
    row: CecchinoTodayFixture,
    *,
    include_unverified_diagnostic: bool,
    evaluate_after: bool,
) -> dict[str, Any]:
    timestamp_class = _fixture_timestamp_class(row)
    if timestamp_class == "post_kickoff":
        return {"skipped": 1, "reason": "snapshot_post_kickoff"}
    if timestamp_class == "unverifiable" and not include_unverified_diagnostic:
        return {"skipped": 1, "reason": "unverified_diagnostic_disabled"}
    snapshot, reason = _build_purchasability_snapshot(row)
    if snapshot is None:
        return {"skipped": 1, "reason": reason or "candidate_unavailable"}

    canonical_cohort = (
        COHORT_HISTORICAL_RECONSTRUCTED_VERIFIED
        if timestamp_class == "verified_pre_match"
        else COHORT_HISTORICAL_DIAGNOSTIC
    )
    source_cohort = storage_cohort_for_purchasability(canonical_cohort)
    candidate_version = str(
        snapshot.get("candidate_version") or PURCHASABILITY_CANDIDATE_VERSION
    )
    current = _current_evaluations(db, int(row.id), candidate_version)
    panel_rows = _panel_rows(row.kpi_panel_json)
    panel_by_market = {
        str(r.get("market_key") or r.get("selection") or "").strip().upper(): r
        for r in panel_rows
    }
    snapshot_at = _fixture_snapshot_timestamp(row)
    fair_by_market = resolve_fair_book_for_panel_rows(
        panel_rows,
        today_fixture_id=int(row.id),
        snapshot_at=snapshot_at.isoformat() if snapshot_at else None,
    )
    created = updated = duplicate_count = 0
    for item in _eligible_purchasability_items(snapshot):
        market_key = str(
            item.get("market_key") or item.get("selection")
        ).strip().upper()
        matches = current.get(market_key, [])
        existing = matches[0] if matches else None
        duplicate_count += max(0, len(matches) - 1)
        panel_row = panel_by_market.get(market_key, {})
        fair = fair_by_market.get(market_key, {})
        payload = {
            **_fixture_meta(row),
            "snapshot_version": snapshot.get("snapshot_version"),
            "snapshot_hash": snapshot.get("full_candidate_payload_sha256"),
            "source_snapshot_at": snapshot_at,
            "snapshot_timestamp_verified": (
                timestamp_class == "verified_pre_match"
            ),
            "snapshot_before_kickoff": (
                True if timestamp_class == "verified_pre_match" else None
            ),
            "source_cohort": source_cohort,
            "candidate_version": candidate_version,
            "candidate_name": snapshot.get("candidate_name"),
            "feature_version": snapshot.get("feature_version"),
            "market_key": market_key,
            "selection": str(item.get("selection") or market_key),
            "calculation_status": item.get("status"),
            "calculation_quality": item.get("calculation_quality"),
            "purchasability_score": _int_or_none(item.get("score")),
            "raw_score": _dec(item.get("raw_score")),
            "purchasability_class": item.get("class"),
            "phase_1_score": _dec(item.get("phase_1_score")),
            "phase_2_score": _dec(item.get("phase_2_score")),
            "reading": item.get("reading"),
            "quota_book": _dec(panel_row.get("quota_book")),
            "quota_cecchino": _dec(panel_row.get("quota_cecchino")),
            "fair_book_probability": _dec(
                fair.get("fair_book_probability"), places=6
            ),
            "prob_cecchino": _dec(
                panel_row.get("prob_cecchino"), places=6
            ),
            "edge_pct": _dec(panel_row.get("edge_pct")),
            "rating_score": _int_or_none(panel_row.get("rating")),
            "score_acquisto": _dec(
                panel_row.get("score_acquisto"), places=6
            ),
            "promotion_eligible": False,
            "is_current": True,
            "deactivated_at": None,
            "stake_units": DEFAULT_STAKE_UNITS,
        }
        if existing is None:
            db.add(
                CecchinoPurchasabilityEvaluation(
                    evaluation_status=EVAL_PENDING, **payload
                )
            )
            created += 1
        else:
            for field, value in payload.items():
                setattr(existing, field, value)
            updated += 1
        for duplicate in matches[1:]:
            duplicate.is_current = False
            duplicate.deactivated_at = datetime.now(timezone.utc)
    db.flush()
    evaluated = 0
    if (
        evaluate_after
        and row.score_fulltime_home is not None
        and row.score_fulltime_away is not None
    ):
        evaluation = evaluate_purchasability_validation_for_fixture(
            db, int(row.id)
        )
        evaluated = int(evaluation.get("evaluated") or 0)
    return {
        "created": created,
        "updated": updated,
        "duplicates_deactivated": duplicate_count,
        "evaluated": evaluated,
        "cohort": canonical_cohort,
    }


def run_module_historical_backfill(
    db: Session,
    *,
    module_keys: Iterable[str] | str,
    date_from: date,
    date_to: date,
    competition_id: int | None = None,
    evaluate_after: bool = True,
    include_unverified_diagnostic: bool = True,
    confirm: str | None = None,
) -> dict[str, Any]:
    """Esegue il backfill confermato con savepoint per ogni fixture."""
    if confirm != MODULE_HISTORICAL_BACKFILL_CONFIRM_TOKEN:
        raise ValueError(
            "Conferma non valida: usare MODULE_HISTORICAL_BACKFILL_CONFIRM_TOKEN"
        )
    modules = _normalise_modules(module_keys)
    start = _as_date(date_from, "date_from")
    end = _as_date(date_to, "date_to")
    if start > end:
        raise ValueError("date_from non può essere successiva a date_to")
    plan = plan_module_historical_backfill(
        db,
        module_keys=modules,
        date_from=start,
        date_to=end,
        competition_id=competition_id,
        include_unverified_diagnostic=include_unverified_diagnostic,
    )
    run_reports: dict[str, dict[str, Any]] = {}
    if "purchasability" in modules:
        rows = _fixtures(
            db,
            date_from=start,
            date_to=end,
            competition_id=competition_id,
        )
        counters: Counter[str] = Counter()
        errors: list[dict[str, Any]] = []
        for row in rows:
            if row.eligibility_status != ELIGIBILITY_ELIGIBLE:
                continue
            try:
                with db.begin_nested():
                    result = _upsert_purchasability_fixture(
                        db,
                        row,
                        include_unverified_diagnostic=include_unverified_diagnostic,
                        evaluate_after=evaluate_after,
                    )
                    for key in (
                        "created",
                        "updated",
                        "duplicates_deactivated",
                        "evaluated",
                        "skipped",
                    ):
                        counters[key] += int(result.get(key) or 0)
            except Exception as exc:
                errors.append(
                    {
                        "today_fixture_id": int(row.id),
                        "error": f"{type(exc).__name__}: {str(exc)[:250]}",
                    }
                )
        run_reports["purchasability"] = {
            **dict(counters),
            "errors": errors[:100],
            "error_count": len(errors),
            "cecchino_output_json_mutated": False,
        }
    for module_key in modules:
        if module_key == "purchasability":
            continue
        run_reports[module_key] = {
            "read_only": True,
            "rows_covered": plan["modules"][module_key]["rows_generatable"],
            "note": plan["modules"][module_key].get("note"),
        }
    db.commit()
    return make_json_safe(
        {
            "status": "completed",
            "version": CECCHINO_MODULE_HISTORICAL_BACKFILL_VERSION,
            "module_keys": modules,
            "date_from": start.isoformat(),
            "date_to": end.isoformat(),
            "competition_id": competition_id,
            "evaluate_after": evaluate_after,
            "include_unverified_diagnostic": include_unverified_diagnostic,
            "plan": plan,
            "run": run_reports,
        }
    )


def build_module_historical_backfill_status(
    db: Session,
    *,
    date_from: date,
    date_to: date,
    competition_id: int | None = None,
) -> dict[str, Any]:
    """Restituisce lo stato aggregato del backfill per tutti i moduli."""
    plan = plan_module_historical_backfill(
        db,
        module_keys=(
            "purchasability",
            "balance-v5",
            "goal-intensity-v5",
            "signals",
        ),
        date_from=date_from,
        date_to=date_to,
        competition_id=competition_id,
        include_unverified_diagnostic=True,
    )
    modules = plan["modules"]
    return make_json_safe(
        {
            "status": "ok",
            "version": CECCHINO_MODULE_HISTORICAL_BACKFILL_VERSION,
            "date_from": plan["date_from"],
            "date_to": plan["date_to"],
            "competition_id": competition_id,
            "module_count": len(modules),
            "totals": {
                key: sum(
                    int(module.get(key) or 0) for module in modules.values()
                )
                for key in (
                    "total_fixtures",
                    "eligible_fixtures",
                    "rows_generatable",
                    "already_present",
                    "new",
                    "updatable",
                    "duplicates",
                    "unusable",
                )
            },
            "modules": modules,
        }
    )
