"""Balance v5 monitoring — snapshot compatto, resolve, dataset (read-only).

Non modifica formule di ``build_cecchino_balance_v5``.
Coorti canoniche: prospective_persisted | historical_* | unusable.
"""

from __future__ import annotations

import csv
import io
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.cecchino_today_fixture import (
    ELIGIBILITY_ELIGIBLE,
    CecchinoTodayFixture,
)
from app.services.cecchino.cecchino_balance_v5 import VERSION as BALANCE_V5_VERSION
from app.services.cecchino.cecchino_balance_v5 import build_cecchino_balance_v5
from app.services.cecchino.cecchino_monitoring_cohorts import (
    COHORT_HISTORICAL_DIAGNOSTIC,
    COHORT_HISTORICAL_PERSISTED_VERIFIED,
    COHORT_HISTORICAL_RECONSTRUCTED_VERIFIED,
    COHORT_PROSPECTIVE,
)
from app.services.cecchino.cecchino_purchasability_audit import make_json_safe

BALANCE_MONITORING_SNAPSHOT_VERSION = "cecchino_balance_v5_monitoring_snapshot_v1"
BALANCE_MONITORING_KEY = "balance_v5_monitoring"

ResolveMode = Literal[
    "persisted",
    "derived_read_only_from_stored_pre_match",
    "unavailable",
]
SourceCohort = Literal[
    "prospective_persisted",
    "historical_persisted_verified",
    "historical_reconstructed_verified",
    "historical_diagnostic",
]

BALANCE_ROW_FIELDS: list[str] = [
    "today_fixture_id",
    "provider_fixture_id",
    "local_fixture_id",
    "scan_date",
    "competition_id",
    "league_name",
    "home_team_name",
    "away_team_name",
    "kickoff",
    "snapshot_version",
    "balance_version",
    "source_mode",
    "source_cohort",
    "pre_match_verified",
    "snapshot_timestamp",
    "f36_index",
    "f36_class",
    "dominance_index",
    "dominance_class",
    "dominance_selection",
    "draw_credibility_index",
    "draw_credibility_class",
    "gap_index",
    "gap_class",
    "prob_1_norm",
    "prob_x_norm",
    "prob_2_norm",
    "book_prob_1",
    "book_prob_x",
    "book_prob_2",
    "book_verified",
    "generated_at",
    "ft_home",
    "ft_away",
    "ht_home",
    "ht_away",
    "outcome_1x2",
    "is_draw",
    "total_goals",
    "absolute_goal_difference",
    "dominance_selection_hit",
    "dominance_selection_result",
    "result_available",
    "is_settled",
    "warning_codes",
]


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _pillar(payload: dict[str, Any], key: str) -> dict[str, Any]:
    pillars = payload.get("pillars") if isinstance(payload, dict) else None
    if not isinstance(pillars, dict):
        return {}
    p = pillars.get(key)
    return p if isinstance(p, dict) else {}


def _inputs(payload: dict[str, Any]) -> dict[str, Any]:
    inp = payload.get("inputs") if isinstance(payload, dict) else None
    return inp if isinstance(inp, dict) else {}


def compact_balance_v5_monitoring_snapshot(
    balance_v5: dict[str, Any],
    *,
    scan_date: Any,
    kickoff: Any,
    snapshot_timestamp: Any = None,
    generated_at: Any = None,
    pre_match_verified: bool | None = None,
    source_mode: str = "prospective_scan",
    book_probs: dict[str, Any] | None = None,
    book_verified: bool | None = None,
) -> dict[str, Any]:
    """Compact pre-match snapshot — no FT/results."""
    if not isinstance(balance_v5, dict) or balance_v5.get("status") == "unavailable":
        return {
            "status": "unavailable",
            "snapshot_version": BALANCE_MONITORING_SNAPSHOT_VERSION,
            "balance_version": BALANCE_V5_VERSION,
            "source_mode": source_mode,
        }

    f36 = _pillar(balance_v5, "f36")
    dom = _pillar(balance_v5, "dominance")
    draw = _pillar(balance_v5, "draw_credibility")
    gap = _pillar(balance_v5, "gap_coherence")
    inp = _inputs(balance_v5)
    book = book_probs or {}
    warnings = list(balance_v5.get("warnings") or [])

    def _iso(v: Any) -> str | None:
        if v is None:
            return None
        if isinstance(v, datetime):
            return v.isoformat()
        if isinstance(v, date):
            return v.isoformat()
        return str(v)

    return make_json_safe(
        {
            "status": "ok",
            "snapshot_version": BALANCE_MONITORING_SNAPSHOT_VERSION,
            "balance_version": str(balance_v5.get("version") or BALANCE_V5_VERSION),
            "scan_date": _iso(scan_date),
            "kickoff": _iso(kickoff),
            "snapshot_timestamp": _iso(snapshot_timestamp),
            "generated_at": _iso(generated_at) if generated_at is not None else None,
            "pre_match_verified": pre_match_verified,
            "source_mode": source_mode,
            "f36_index": f36.get("index"),
            "f36_class": f36.get("class_label") or f36.get("class_key"),
            "dominance_index": dom.get("index"),
            "dominance_class": dom.get("class_label") or dom.get("class_key"),
            "dominance_selection": dom.get("direction"),
            "draw_credibility_index": draw.get("index"),
            "draw_credibility_class": draw.get("class_label") or draw.get("class_key"),
            "gap_index": gap.get("index"),
            "gap_class": gap.get("class_label") or gap.get("class_key"),
            "prob_1_norm": inp.get("prob_1_norm"),
            "prob_x_norm": inp.get("prob_x_norm"),
            "prob_2_norm": inp.get("prob_2_norm"),
            "book_prob_1": book.get("prob_1") or book.get("book_prob_1"),
            "book_prob_x": book.get("prob_x") or book.get("book_prob_x"),
            "book_prob_2": book.get("prob_2") or book.get("book_prob_2"),
            "book_verified": book_verified,
            "warning_codes": warnings,
        }
    )


def build_balance_v5_from_stored_row(row: CecchinoTodayFixture) -> dict[str, Any] | None:
    """Ricalcolo read-only da input già storati (stesso builder del detail)."""
    output = row.cecchino_output_json if isinstance(row.cecchino_output_json, dict) else {}
    final = output.get("final")
    if not isinstance(final, dict) or not final:
        return None
    kpi = row.kpi_panel_json if isinstance(row.kpi_panel_json, dict) else None
    try:
        bal = build_cecchino_balance_v5(
            cecchino_final=final,
            goal_markets=output.get("goal_markets")
            if isinstance(output.get("goal_markets"), dict)
            else None,
            kpi_panel=kpi,
            identity_consistency=None,
        )
    except Exception:
        return None
    if not isinstance(bal, dict) or bal.get("status") == "unavailable":
        return None
    return bal


def _parse_iso_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    try:
        if isinstance(value, datetime):
            return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        raw = str(value).replace("Z", "+00:00")
        dt = datetime.fromisoformat(raw)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def _extract_odds_snapshot_at(row: CecchinoTodayFixture) -> str | None:
    """Timestamp reale odds/snapshot — mai datetime.now."""
    odds = row.odds_snapshot_json if isinstance(row.odds_snapshot_json, dict) else {}
    meta = odds.get("meta") if isinstance(odds.get("meta"), dict) else {}
    snap_at = None
    for fld in ("odds_fetched_at", "fetched_at", "snapshot_at"):
        if meta.get(fld):
            snap_at = meta.get(fld)
            break
        if odds.get(fld):
            snap_at = odds.get(fld)
            break
    if snap_at is None:
        kpi = row.kpi_panel_json if isinstance(row.kpi_panel_json, dict) else {}
        kmeta = kpi.get("meta") if isinstance(kpi.get("meta"), dict) else {}
        for fld in ("snapshot_at", "fetched_at", "odds_fetched_at"):
            if kmeta.get(fld):
                snap_at = kmeta.get(fld)
                break
    dt = _parse_iso_datetime(snap_at)
    return dt.isoformat() if dt else None


def _extract_book_probs_from_row(row: CecchinoTodayFixture) -> tuple[dict[str, Any], bool | None]:
    """Probabilità book da snapshot storici salvati — null se assenti."""
    book_probs: dict[str, Any] = {}
    odds = row.odds_snapshot_json if isinstance(row.odds_snapshot_json, dict) else {}
    markets = odds.get("markets") if isinstance(odds.get("markets"), dict) else {}
    for mk, payload in markets.items():
        if not isinstance(payload, dict):
            continue
        key = str(mk).upper()
        prob = payload.get("prob") or payload.get("probability")
        if prob is None:
            continue
        if key in {"1", "HOME", "1X2_1"}:
            book_probs["prob_1"] = prob
        elif key in {"X", "DRAW", "1X2_X"}:
            book_probs["prob_x"] = prob
        elif key in {"2", "AWAY", "1X2_2"}:
            book_probs["prob_2"] = prob
    if not book_probs:
        kpi = row.kpi_panel_json if isinstance(row.kpi_panel_json, dict) else {}
        for prow in kpi.get("rows") or []:
            if not isinstance(prow, dict):
                continue
            mk = str(prow.get("market_key") or "").upper()
            pb = prow.get("prob_book")
            if pb is None:
                continue
            if mk in ("1", "HOME", "1X2_1"):
                book_probs["prob_1"] = pb
            elif mk in ("X", "DRAW", "1X2_X"):
                book_probs["prob_x"] = pb
            elif mk in ("2", "AWAY", "1X2_2"):
                book_probs["prob_2"] = pb
    verified = _odds_meta_verified_pre_kickoff(row) if book_probs else None
    return book_probs, verified


def _odds_meta_verified_pre_kickoff(row: CecchinoTodayFixture) -> bool:
    """True se odds/snapshot timestamp esiste e risulta prima del kickoff."""
    odds = row.odds_snapshot_json if isinstance(row.odds_snapshot_json, dict) else {}
    meta = odds.get("meta") if isinstance(odds.get("meta"), dict) else {}
    snap_at = None
    for fld in ("odds_fetched_at", "fetched_at", "snapshot_at"):
        if meta.get(fld):
            snap_at = meta.get(fld)
            break
        if odds.get(fld):
            snap_at = odds.get(fld)
            break
    if snap_at is None or row.kickoff is None:
        return False
    try:
        if isinstance(snap_at, datetime):
            snap_dt = snap_at if snap_at.tzinfo else snap_at.replace(tzinfo=timezone.utc)
        else:
            raw = str(snap_at).replace("Z", "+00:00")
            snap_dt = datetime.fromisoformat(raw)
            if snap_dt.tzinfo is None:
                snap_dt = snap_dt.replace(tzinfo=timezone.utc)
        kick = row.kickoff
        if kick.tzinfo is None:
            kick = kick.replace(tzinfo=timezone.utc)
        return snap_dt < kick
    except Exception:
        return False


def resolve_balance_v5_monitoring_snapshot(
    today_fixture: CecchinoTodayFixture,
) -> dict[str, Any]:
    """Resolve canonico monitoring Balance.

    1. persisted ``balance_v5_monitoring`` (prospective se pre_match_verified)
    2. legacy ``balance_v5`` — mai prospective se pre_match_verified null
    3. derived_read_only_from_stored_pre_match
    4. unavailable
    """
    output = (
        today_fixture.cecchino_output_json
        if isinstance(today_fixture.cecchino_output_json, dict)
        else {}
    )
    verified_ts = _odds_meta_verified_pre_kickoff(today_fixture)
    source_snapshot_at = _extract_odds_snapshot_at(today_fixture)
    book_probs, book_verified = _extract_book_probs_from_row(today_fixture)

    persisted = output.get(BALANCE_MONITORING_KEY)
    if isinstance(persisted, dict) and persisted:
        status = str(persisted.get("status") or "").strip().lower()
        if status != "unavailable" and (
            persisted.get("f36_index") is not None
            or persisted.get("prob_1_norm") is not None
            or persisted.get("pillars")
        ):
            pmv = persisted.get("pre_match_verified")
            if pmv is True or (
                pmv is None and verified_ts and persisted.get("source_mode") == "prospective_scan"
            ):
                cohort = COHORT_PROSPECTIVE
            elif verified_ts or pmv is True:
                cohort = COHORT_HISTORICAL_PERSISTED_VERIFIED
            else:
                cohort = COHORT_HISTORICAL_DIAGNOSTIC
            payload = dict(persisted)
            if not payload.get("snapshot_timestamp") and source_snapshot_at:
                payload["snapshot_timestamp"] = source_snapshot_at
            if book_probs and payload.get("book_prob_1") is None:
                payload["book_prob_1"] = book_probs.get("prob_1")
                payload["book_prob_x"] = book_probs.get("prob_x")
                payload["book_prob_2"] = book_probs.get("prob_2")
                payload["book_verified"] = book_verified
            return {
                "mode": "persisted",
                "payload": payload,
                "source_cohort": cohort,
            }

    # Legacy full balance_v5 — NEVER auto-classify as prospective
    legacy_full = output.get("balance_v5")
    if isinstance(legacy_full, dict) and legacy_full.get("status") != "unavailable":
        compact = compact_balance_v5_monitoring_snapshot(
            legacy_full,
            scan_date=today_fixture.scan_date,
            kickoff=today_fixture.kickoff,
            snapshot_timestamp=source_snapshot_at,
            source_mode="legacy_persisted_balance_v5",
            pre_match_verified=verified_ts if verified_ts else None,
            book_probs=book_probs or None,
            book_verified=book_verified,
        )
        cohort = (
            COHORT_HISTORICAL_PERSISTED_VERIFIED
            if verified_ts
            else COHORT_HISTORICAL_DIAGNOSTIC
        )
        return {
            "mode": "persisted",
            "payload": compact,
            "source_cohort": cohort,
        }

    derived = build_balance_v5_from_stored_row(today_fixture)
    if derived is not None:
        derived_source_mode = (
            "derived_read_only_from_stored_pre_match"
            if verified_ts
            else "derived_read_only_from_stored_inputs_unverified_timestamp"
        )
        compact = compact_balance_v5_monitoring_snapshot(
            derived,
            scan_date=today_fixture.scan_date,
            kickoff=today_fixture.kickoff,
            snapshot_timestamp=source_snapshot_at,
            source_mode=derived_source_mode,
            pre_match_verified=verified_ts if verified_ts else None,
            book_probs=book_probs or None,
            book_verified=book_verified,
        )
        cohort = (
            COHORT_HISTORICAL_RECONSTRUCTED_VERIFIED
            if verified_ts
            else COHORT_HISTORICAL_DIAGNOSTIC
        )
        return {
            "mode": derived_source_mode,
            "payload": compact,
            "source_cohort": cohort,
        }

    return {"mode": "unavailable", "payload": None, "source_cohort": None}


def attach_balance_v5_monitoring_to_output(
    *,
    cecchino_output: dict[str, Any],
    kpi_panel: dict[str, Any] | None,
    fixture_meta: dict[str, Any],
    snapshot_info: dict[str, Any] | None = None,
    existing_monitoring: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Scrive balance_v5_monitoring su cecchino_output (pre-match). Nessun FT."""
    if not isinstance(cecchino_output, dict):
        return cecchino_output

    snap = snapshot_info or {}
    verified = bool(snap.get("snapshot_timestamp_verified"))
    preserved = (
        existing_monitoring
        if isinstance(existing_monitoring, dict) and existing_monitoring
        else None
    )
    if preserved is None:
        prev = cecchino_output.get(BALANCE_MONITORING_KEY)
        if isinstance(prev, dict) and prev:
            preserved = prev

    final = cecchino_output.get("final")
    if not isinstance(final, dict) or not final:
        if preserved is not None:
            cecchino_output[BALANCE_MONITORING_KEY] = preserved
        return cecchino_output

    try:
        bal = build_cecchino_balance_v5(
            cecchino_final=final,
            goal_markets=cecchino_output.get("goal_markets")
            if isinstance(cecchino_output.get("goal_markets"), dict)
            else None,
            kpi_panel=kpi_panel,
            identity_consistency=None,
        )
    except Exception:
        if preserved is not None:
            cecchino_output[BALANCE_MONITORING_KEY] = preserved
        return cecchino_output

    book_probs: dict[str, Any] = {}
    book_verified = None
    if isinstance(kpi_panel, dict):
        # best-effort book probs from panel rows if present
        for row in kpi_panel.get("rows") or []:
            if not isinstance(row, dict):
                continue
            mk = str(row.get("market_key") or "").upper()
            pb = row.get("prob_book")
            if pb is None:
                continue
            if mk in ("1", "HOME", "1X2_1"):
                book_probs["prob_1"] = pb
            elif mk in ("X", "DRAW", "1X2_X"):
                book_probs["prob_x"] = pb
            elif mk in ("2", "AWAY", "1X2_2"):
                book_probs["prob_2"] = pb
        if book_probs:
            book_verified = verified

    compact = compact_balance_v5_monitoring_snapshot(
        bal,
        scan_date=fixture_meta.get("scan_date"),
        kickoff=fixture_meta.get("kickoff"),
        snapshot_timestamp=snap.get("snapshot_at"),
        pre_match_verified=verified if verified else None,
        source_mode="prospective_scan",
        book_probs=book_probs or None,
        book_verified=book_verified,
    )
    cecchino_output[BALANCE_MONITORING_KEY] = compact
    return cecchino_output


def _row_from_resolve(
    fx: CecchinoTodayFixture, resolved: dict[str, Any]
) -> dict[str, Any] | None:
    payload = resolved.get("payload")
    if not isinstance(payload, dict):
        return None
    ft_h = fx.score_fulltime_home
    ft_a = fx.score_fulltime_away
    ht_h = fx.score_halftime_home
    ht_a = fx.score_halftime_away
    settled = ft_h is not None and ft_a is not None
    result_available = settled
    outcome_1x2 = None
    is_draw = None
    total_goals = None
    abs_diff = None
    if settled:
        if ft_h > ft_a:
            outcome_1x2 = "1"
        elif ft_h < ft_a:
            outcome_1x2 = "2"
        else:
            outcome_1x2 = "X"
        is_draw = outcome_1x2 == "X"
        total_goals = int(ft_h) + int(ft_a)
        abs_diff = abs(int(ft_h) - int(ft_a))
    dom_sel = str(payload.get("dominance_selection") or "").strip().upper() or None
    dom_hit = None
    dom_result = None
    if settled and dom_sel in {"1", "X", "2"}:
        dom_hit = dom_sel == outcome_1x2
        dom_result = "hit" if dom_hit else "miss"
    warnings = [str(w) for w in (payload.get("warning_codes") or [])]
    cohort = resolved.get("source_cohort")
    book_null = (
        payload.get("book_prob_1") is None
        and payload.get("book_prob_x") is None
        and payload.get("book_prob_2") is None
    )
    if book_null and (
        cohort == "historical_diagnostic"
        or str(cohort or "").endswith("diagnostic")
    ):
        warnings.append("book_probabilities_unavailable_historical_diagnostic")
    return {
        "today_fixture_id": fx.id,
        "provider_fixture_id": fx.provider_fixture_id,
        "local_fixture_id": fx.local_fixture_id,
        "scan_date": fx.scan_date.isoformat() if fx.scan_date else None,
        "competition_id": fx.competition_id,
        "league_name": fx.league_name,
        "home_team_name": fx.home_team_name,
        "away_team_name": fx.away_team_name,
        "kickoff": fx.kickoff.isoformat() if fx.kickoff else None,
        "snapshot_version": payload.get("snapshot_version")
        or BALANCE_MONITORING_SNAPSHOT_VERSION,
        "balance_version": payload.get("balance_version") or BALANCE_V5_VERSION,
        "source_mode": resolved.get("mode"),
        "source_cohort": resolved.get("source_cohort"),
        "pre_match_verified": payload.get("pre_match_verified"),
        "snapshot_timestamp": payload.get("snapshot_timestamp"),
        "generated_at": _utcnow(),
        "f36_index": payload.get("f36_index"),
        "f36_class": payload.get("f36_class"),
        "dominance_index": payload.get("dominance_index"),
        "dominance_class": payload.get("dominance_class"),
        "dominance_selection": payload.get("dominance_selection"),
        "draw_credibility_index": payload.get("draw_credibility_index"),
        "draw_credibility_class": payload.get("draw_credibility_class"),
        "gap_index": payload.get("gap_index"),
        "gap_class": payload.get("gap_class"),
        "prob_1_norm": payload.get("prob_1_norm"),
        "prob_x_norm": payload.get("prob_x_norm"),
        "prob_2_norm": payload.get("prob_2_norm"),
        "book_prob_1": payload.get("book_prob_1"),
        "book_prob_x": payload.get("book_prob_x"),
        "book_prob_2": payload.get("book_prob_2"),
        "book_verified": payload.get("book_verified"),
        "ft_home": ft_h,
        "ft_away": ft_a,
        "ht_home": ht_h,
        "ht_away": ht_a,
        "outcome_1x2": outcome_1x2,
        "is_draw": is_draw,
        "total_goals": total_goals,
        "absolute_goal_difference": abs_diff,
        "dominance_selection_hit": dom_hit,
        "dominance_selection_result": dom_result,
        "result_available": result_available,
        "is_settled": settled,
        "warning_codes": "|".join(warnings),
    }


def iter_eligible_fixtures(
    db: Session,
    *,
    date_from: date,
    date_to: date,
    competition_id: int | None = None,
) -> list[CecchinoTodayFixture]:
    q = select(CecchinoTodayFixture).where(
        CecchinoTodayFixture.scan_date >= date_from,
        CecchinoTodayFixture.scan_date <= date_to,
        CecchinoTodayFixture.eligibility_status == ELIGIBILITY_ELIGIBLE,
    )
    if competition_id is not None:
        q = q.where(CecchinoTodayFixture.competition_id == int(competition_id))
    return list(db.scalars(q).all())


def build_balance_monitoring_rows(
    db: Session,
    *,
    date_from: date,
    date_to: date,
    competition_id: int | None = None,
) -> list[dict[str, Any]]:
    rows_out: list[dict[str, Any]] = []
    for fx in iter_eligible_fixtures(
        db, date_from=date_from, date_to=date_to, competition_id=competition_id
    ):
        resolved = resolve_balance_v5_monitoring_snapshot(fx)
        if resolved.get("mode") == "unavailable":
            continue
        row = _row_from_resolve(fx, resolved)
        if row:
            rows_out.append(row)
    return rows_out


def _dist_csv(rows: list[dict[str, Any]], class_key: str, index_key: str) -> bytes:
    counter: Counter[str] = Counter()
    for r in rows:
        label = str(r.get(class_key) or "unknown")
        counter[label] += 1
    out_rows = [
        {"class": k, "count": v, "share": (v / len(rows) if rows else 0)}
        for k, v in sorted(counter.items(), key=lambda x: (-x[1], x[0]))
    ]
    return _csv_bom_bytes(
        out_rows, ["class", "count", "share"]
    )


def _csv_bom_bytes(rows: list[dict[str, Any]], fieldnames: list[str]) -> bytes:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow({k: row.get(k) for k in fieldnames})
    return ("\ufeff" + buf.getvalue()).encode("utf-8")


def build_balance_monthly_timeseries(rows: list[dict[str, Any]]) -> bytes:
    by_month: dict[str, dict[str, int]] = defaultdict(
        lambda: {
            "fixtures": 0,
            "settled": 0,
            "prospective": 0,
            "historical_verified": 0,
            "historical_diagnostic": 0,
        }
    )
    for r in rows:
        sd = str(r.get("scan_date") or "")[:7] or "unknown"
        by_month[sd]["fixtures"] += 1
        if r.get("is_settled"):
            by_month[sd]["settled"] += 1
        cohort = str(r.get("source_cohort") or "")
        if cohort == COHORT_PROSPECTIVE:
            by_month[sd]["prospective"] += 1
        elif cohort in (
            COHORT_HISTORICAL_PERSISTED_VERIFIED,
            COHORT_HISTORICAL_RECONSTRUCTED_VERIFIED,
        ):
            by_month[sd]["historical_verified"] += 1
        elif cohort == COHORT_HISTORICAL_DIAGNOSTIC:
            by_month[sd]["historical_diagnostic"] += 1
    out = [
        {
            "month": m,
            "fixtures": v["fixtures"],
            "settled": v["settled"],
            "prospective_persisted": v["prospective"],
            "historical_verified": v["historical_verified"],
            "historical_diagnostic": v["historical_diagnostic"],
        }
        for m, v in sorted(by_month.items())
    ]
    return _csv_bom_bytes(
        out,
        [
            "month",
            "fixtures",
            "settled",
            "prospective_persisted",
            "historical_verified",
            "historical_diagnostic",
        ],
    )


def build_balance_export_files(
    db: Session,
    *,
    date_from: date,
    date_to: date,
    competition_id: int | None = None,
) -> dict[str, bytes]:
    """File set Balance per ZIP — header sempre presenti."""
    eligible_list = iter_eligible_fixtures(
        db, date_from=date_from, date_to=date_to, competition_id=competition_id
    )
    rows = build_balance_monitoring_rows(
        db, date_from=date_from, date_to=date_to, competition_id=competition_id
    )
    cohort_counts: Counter[str] = Counter(
        str(r.get("source_cohort") or "unknown") for r in rows
    )
    prospective = cohort_counts.get(COHORT_PROSPECTIVE, 0)
    hist_verified = (
        cohort_counts.get(COHORT_HISTORICAL_PERSISTED_VERIFIED, 0)
        + cohort_counts.get(COHORT_HISTORICAL_RECONSTRUCTED_VERIFIED, 0)
    )
    hist_diag = cohort_counts.get(COHORT_HISTORICAL_DIAGNOSTIC, 0)
    settled = sum(1 for r in rows if r.get("is_settled"))
    timestamp_verified = sum(
        1
        for r in rows
        if r.get("snapshot_timestamp")
        and r.get("pre_match_verified") is True
        and r.get("generated_at") != r.get("snapshot_timestamp")
    )
    eligible_n = len(eligible_list)

    health: dict[str, Any] = {
        "eligible_scanned": eligible_n,
        "covered_rows": len(rows),
        "settled_covered": settled,
        "prospective_persisted": prospective,
        "historical_persisted_or_reconstructed_verified": hist_verified,
        "historical_diagnostic": hist_diag,
        "legacy_derived_diagnostic": hist_diag,  # alias report
        "timestamp_verified_rows": timestamp_verified,
        "coverage": (len(rows) / eligible_n) if eligible_n else None,
        "warnings": [],
    }
    if eligible_n and not rows:
        health["warnings"].append("Balance non disponibile (né persistito né derivabile)")
    elif prospective == 0 and (hist_verified + hist_diag) > 0:
        health["warnings"].append(
            "Solo coorti storiche — nessuna riga prospective_persisted"
        )

    version_def = {
        "balance_version": BALANCE_V5_VERSION,
        "snapshot_version": BALANCE_MONITORING_SNAPSHOT_VERSION,
        "monitoring_key": BALANCE_MONITORING_KEY,
    }

    try:
        from app.services.cecchino.cecchino_draw_credibility_research import (
            build_draw_credibility_coverage_audit,
        )

        draw_research = build_draw_credibility_coverage_audit(
            db,
            date_from=date_from,
            date_to=date_to,
            competition_id=competition_id,
            only_eligible=True,
        )
        if not draw_research.get("counts"):
            draw_research = {
                "status": "unavailable",
                "reason": "coverage_audit_empty_for_selected_range",
                "date_from": date_from.isoformat(),
                "date_to": date_to.isoformat(),
            }
        else:
            draw_research = {
                "status": "ok",
                **draw_research,
                "date_from": date_from.isoformat(),
                "date_to": date_to.isoformat(),
            }
    except Exception as exc:
        draw_research = {
            "status": "unavailable",
            "reason": f"coverage_audit_failed:{type(exc).__name__}",
            "date_from": date_from.isoformat(),
            "date_to": date_to.isoformat(),
        }

    files: dict[str, bytes] = {
        "balance_rows.csv": _csv_bom_bytes(rows, BALANCE_ROW_FIELDS),
        "f36_distribution.csv": _dist_csv(rows, "f36_class", "f36_index"),
        "dominance_distribution.csv": _dist_csv(
            rows, "dominance_class", "dominance_index"
        ),
        "draw_credibility_distribution.csv": _dist_csv(
            rows, "draw_credibility_class", "draw_credibility_index"
        ),
        "gap_distribution.csv": _dist_csv(rows, "gap_class", "gap_index"),
        "monthly_timeseries.csv": build_balance_monthly_timeseries(rows),
        "snapshot_health.json": (
            __import__("json")
            .dumps(make_json_safe(health), ensure_ascii=False, indent=2, allow_nan=False)
            .encode("utf-8")
        ),
        "source_cohort_distribution.json": (
            __import__("json")
            .dumps(
                make_json_safe(dict(cohort_counts)),
                ensure_ascii=False,
                indent=2,
                allow_nan=False,
            )
            .encode("utf-8")
        ),
        "version_definition.json": (
            __import__("json")
            .dumps(make_json_safe(version_def), ensure_ascii=False, indent=2, allow_nan=False)
            .encode("utf-8")
        ),
        "draw_credibility_research.json": (
            __import__("json")
            .dumps(
                make_json_safe(draw_research),
                ensure_ascii=False,
                indent=2,
                allow_nan=False,
            )
            .encode("utf-8")
        ),
    }
    return files


def build_balance_module_overview_v2(
    db: Session,
    *,
    date_from: date,
    date_to: date,
    competition_id: int | None = None,
) -> dict[str, Any]:
    fixtures = iter_eligible_fixtures(
        db, date_from=date_from, date_to=date_to, competition_id=competition_id
    )
    eligible = len(fixtures)
    covered = 0
    settled_covered = 0
    prospective = 0
    hist_verified = 0
    hist_diag = 0
    reconstructed = 0
    timestamp_verified = 0
    for fx in fixtures:
        resolved = resolve_balance_v5_monitoring_snapshot(fx)
        if resolved.get("mode") == "unavailable":
            continue
        covered += 1
        cohort = resolved.get("source_cohort")
        payload = resolved.get("payload") if isinstance(resolved.get("payload"), dict) else {}
        snap_ts = payload.get("snapshot_timestamp")
        if snap_ts and (_odds_meta_verified_pre_kickoff(fx) or payload.get("pre_match_verified") is True):
            timestamp_verified += 1
        if cohort == COHORT_PROSPECTIVE:
            prospective += 1
        elif cohort in (
            COHORT_HISTORICAL_PERSISTED_VERIFIED,
            COHORT_HISTORICAL_RECONSTRUCTED_VERIFIED,
        ):
            hist_verified += 1
            if cohort == COHORT_HISTORICAL_RECONSTRUCTED_VERIFIED:
                reconstructed += 1
        elif cohort == COHORT_HISTORICAL_DIAGNOSTIC:
            hist_diag += 1
        if (
            fx.score_fulltime_home is not None
            and fx.score_fulltime_away is not None
        ):
            settled_covered += 1

    coverage = (covered / eligible) if eligible else None
    warnings: list[str] = []
    if eligible == 0:
        warnings.append("Nessuna fixture eleggibile nel periodo")
    elif covered == 0:
        warnings.append("Balance non disponibile nello snapshot persistito né derivabile")
    elif prospective == 0 and (hist_verified + hist_diag) > 0:
        warnings.append(
            "Coverage da coorti storiche — snapshot prospectivo assente"
        )
    warnings.append(
        "Monitoraggio descrittivo — validazione empirica avanzata in preparazione"
    )
    return make_json_safe(
        {
            "module_key": "balance-v5",
            "status": "official_monitored",
            "scientific_maturity": "validazione_empirica_da_avviare",
            "version": BALANCE_V5_VERSION,
            "coverage": coverage,
            "coverage_descriptive": coverage,
            "coverage_descriptive_ratio": (
                f"{covered}/{eligible}" if eligible else None
            ),
            "timestamp_verified_coverage": (
                (timestamp_verified / covered) if covered else None
            ),
            "timestamp_verified_ratio": (
                f"{timestamp_verified}/{covered}" if covered else None
            ),
            "prospective_coverage": (prospective / covered) if covered else None,
            "prospective_snapshots": prospective,
            "fixtures": covered if eligible else None,
            "settled": settled_covered if eligible else None,
            "eligible_fixtures": eligible,
            "covered_fixtures": covered,
            "settled_covered_fixtures": settled_covered,
            "reconstructed_fixtures": reconstructed,
            "timestamp_verified_fixtures": timestamp_verified,
            "coverage_numerator": covered if eligible else None,
            "coverage_denominator": eligible if eligible else None,
            "prospective_persisted": prospective,
            "historical_persisted_or_reconstructed_verified": hist_verified,
            "historical_diagnostic": hist_diag,
            "legacy_derived_diagnostic": hist_diag,
            "source_cohorts": {
                COHORT_PROSPECTIVE: prospective,
                COHORT_HISTORICAL_PERSISTED_VERIFIED: hist_verified,
                COHORT_HISTORICAL_DIAGNOSTIC: hist_diag,
            },
            "last_snapshot_at": None,
            "next_review_at": None,
            "warnings": warnings,
        }
    )
