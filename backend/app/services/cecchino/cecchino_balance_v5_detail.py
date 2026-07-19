"""Helpers read-only per Balance v5 sul dettaglio Today (current vs storico).

Nessuna scrittura DB; nessuna modifica alle formule di cecchino_balance_v5.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from app.models.cecchino_today_fixture import CecchinoTodayFixture
from app.models.fixture import Fixture
from app.services.cecchino.cecchino_fixture_identity_consistency import (
    KICKOFF_TOLERANCE,
    _extract_calculation_target_kickoff,
    _kickoffs_match,
    _parse_iso_dt,
    build_fixture_identity_consistency,
    build_historical_fixture_identity_consistency,
)
from app.services.cecchino.cecchino_today_odds_meta import read_odds_meta
from app.services.datetime_utils import ensure_datetime_utc, safe_isoformat

MODE_CURRENT = "current_strict"
MODE_HISTORICAL = "historical_snapshot"

SOURCE_STORED = "stored_pre_match_snapshot"

META_VERIFIED = "verified"
META_PARTIAL = "partial"
META_BLOCKED = "blocked"

BOOK_VERIFIED = "verified"
BOOK_PARTIAL = "partial"
BOOK_UNAVAILABLE = "unavailable"
BOOK_BLOCKED = "blocked"


def resolve_balance_detail_mode(scan_date: date | None, today: date) -> str:
    """historical_snapshot se scan_date < oggi (Europe/Rome), altrimenti current_strict."""
    if scan_date is None:
        return MODE_CURRENT
    if scan_date < today:
        return MODE_HISTORICAL
    return MODE_CURRENT


def _adapt_historical_identity(raw: dict[str, Any]) -> dict[str, Any]:
    """Adatta lo status storico al contratto pubblico consistent/inconsistent."""
    hist_status = str(raw.get("status") or "")
    if hist_status == "static_identity_verified":
        public = "consistent"
        static_ok = True
    else:
        # static_identity_failed | static_identity_unavailable | altro
        public = "inconsistent"
        static_ok = False

    out = dict(raw)
    out["status"] = public
    out["historical_identity_status"] = hist_status
    out["verification_mode"] = MODE_HISTORICAL
    out["status_match_blocking"] = False
    out["score_match_blocking"] = False
    out["static_identity_verified"] = static_ok
    return out


def _enrich_current_identity(raw: dict[str, Any]) -> dict[str, Any]:
    out = dict(raw)
    out["verification_mode"] = MODE_CURRENT
    out["status_match_blocking"] = True
    out["score_match_blocking"] = True
    out["static_identity_verified"] = raw.get("status") == "consistent"
    out["historical_identity_status"] = None
    return out


def build_balance_identity_for_detail(
    *,
    mode: str,
    today_row: CecchinoTodayFixture,
    local_fixture: Fixture | None,
    cecchino_output: dict[str, Any] | None,
    expected_goal_diagnostics: dict[str, Any] | None,
    local_home_team_name: str | None,
    local_away_team_name: str | None,
) -> dict[str, Any]:
    """Seleziona identity strict o storica e adatta al contratto pubblico."""
    if mode == MODE_HISTORICAL:
        raw = build_historical_fixture_identity_consistency(
            today_row=today_row,
            local_fixture=local_fixture,
            local_home_team_name=local_home_team_name,
            local_away_team_name=local_away_team_name,
        )
        return _adapt_historical_identity(raw)

    raw = build_fixture_identity_consistency(
        today_row=today_row,
        local_fixture=local_fixture,
        cecchino_output=cecchino_output,
        expected_goal_diagnostics=expected_goal_diagnostics,
        local_home_team_name=local_home_team_name,
        local_away_team_name=local_away_team_name,
    )
    return _enrich_current_identity(raw)


def _parse_odds_ts(value: Any) -> datetime | None:
    if value is None:
        return None
    return _parse_iso_dt(value)


def classify_book_snapshot_status(
    *,
    kickoff: datetime | None,
    odds_meta: dict[str, Any] | None,
    has_book_odds: bool,
) -> tuple[str, list[str]]:
    """Classifica lo snapshot Book storico rispetto al kickoff."""
    warnings: list[str] = []
    if not has_book_odds:
        return BOOK_UNAVAILABLE, warnings

    meta = odds_meta or {}
    ts_keys = ("odds_fetched_at", "odds_cached_at", "last_betfair_refresh_at")
    timestamps = [_parse_odds_ts(meta.get(k)) for k in ts_keys]
    available_ts = [t for t in timestamps if t is not None]

    if not available_ts:
        warnings.append("historical_book_timestamp_unverifiable")
        return BOOK_PARTIAL, warnings

    if kickoff is not None:
        post = [t for t in available_ts if t > kickoff]
        if post:
            warnings.append("historical_book_snapshot_not_pre_match")
            return BOOK_BLOCKED, warnings

    return BOOK_VERIFIED, warnings


def _kpi_has_book_odds(kpi_panel: dict[str, Any] | None) -> bool:
    if not isinstance(kpi_panel, dict):
        return False
    rows = kpi_panel.get("rows") or []
    if not isinstance(rows, list):
        return False
    for r in rows:
        if isinstance(r, dict) and r.get("quota_book") is not None:
            return True
    return False


def strip_book_odds_from_kpi(kpi_panel: dict[str, Any] | None) -> dict[str, Any] | None:
    """Rimuove quote Book dal panel (pilastri Cecchino restano utilizzabili)."""
    if not isinstance(kpi_panel, dict):
        return kpi_panel
    out = dict(kpi_panel)
    rows = out.get("rows")
    if not isinstance(rows, list):
        return out
    cleaned: list[dict[str, Any]] = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        row = dict(r)
        row["quota_book"] = None
        row["prob_book"] = None
        cleaned.append(row)
    out["rows"] = cleaned
    return out


def evaluate_balance_v5_snapshot_meta(
    *,
    mode: str,
    today_row: CecchinoTodayFixture,
    identity: dict[str, Any],
    cecchino_output: dict[str, Any] | None,
    kpi_panel: dict[str, Any] | None,
    book_status: str,
    book_warnings: list[str],
) -> dict[str, Any]:
    """Costruisce balance_v5_snapshot_meta (read-only)."""
    warnings: list[str] = list(identity.get("warnings") or [])
    warnings.extend(book_warnings)

    today_ko = None
    if today_row.kickoff:
        today_ko = ensure_datetime_utc(today_row.kickoff, field_name="today.kickoff")
    today_ko_iso = safe_isoformat(today_ko, field_name="today.kickoff") if today_ko else None

    target_raw = _extract_calculation_target_kickoff(
        cecchino_output if isinstance(cecchino_output, dict) else None
    )
    target_dt = _parse_iso_dt(target_raw) if target_raw else None

    odds_meta = read_odds_meta(
        today_row.odds_snapshot_json if isinstance(today_row.odds_snapshot_json, dict) else None
    )
    odds_fetched_at = odds_meta.get("odds_fetched_at")

    static_ok = bool(identity.get("static_identity_verified"))
    if mode == MODE_CURRENT:
        static_ok = identity.get("status") == "consistent"

    status = META_VERIFIED
    blocking_flags = {
        "status_match_blocking": bool(identity.get("status_match_blocking")),
        "score_match_blocking": bool(identity.get("score_match_blocking")),
    }

    if mode == MODE_CURRENT:
        if identity.get("status") == "inconsistent":
            status = META_BLOCKED
            warnings.append("current_identity_inconsistent")
        elif identity.get("status") != "consistent":
            status = META_PARTIAL
            warnings.append("current_identity_unavailable")
        meta = {
            "mode": mode,
            "status": status,
            "source": SOURCE_STORED,
            "scan_date": today_row.scan_date.isoformat() if today_row.scan_date else None,
            "kickoff": today_ko_iso,
            "calculation_target_kickoff": target_raw,
            "odds_fetched_at": odds_fetched_at,
            "static_identity_verified": static_ok,
            **blocking_flags,
            "book_snapshot_status": book_status,
            "warnings": warnings,
        }
        return meta

    # --- historical_snapshot ---
    if not static_ok:
        status = META_BLOCKED
        if identity.get("historical_identity_status") == "static_identity_unavailable":
            warnings.append("historical_local_fixture_missing")
        else:
            warnings.append("historical_static_identity_failed")

    output_ok = isinstance(cecchino_output, dict) and bool(cecchino_output)
    final = cecchino_output.get("final") if output_ok else None
    final_ok = isinstance(final, dict) and final.get("status") == "available"
    if not output_ok:
        status = META_BLOCKED
        warnings.append("historical_cecchino_output_absent")
    elif not final_ok:
        status = META_BLOCKED
        warnings.append("historical_cecchino_final_unavailable")

    # target_kickoff: se presente deve matchare kickoff Today
    if target_dt is not None and today_ko is not None:
        if not _kickoffs_match(today_ko, target_dt):
            status = META_BLOCKED
            warnings.append("historical_target_kickoff_mismatch")
    elif target_raw is None and status != META_BLOCKED:
        # metadato legacy assente → partial (non verified artificiale)
        status = META_PARTIAL
        warnings.append("historical_target_kickoff_unverifiable")

    # timestamp Book non verificabili → partial se non già blocked
    if status == META_VERIFIED and book_status == BOOK_PARTIAL:
        status = META_PARTIAL
    if status == META_VERIFIED and odds_fetched_at is None and book_status != BOOK_UNAVAILABLE:
        status = META_PARTIAL
        warnings.append("historical_odds_timestamp_unverifiable")

    return {
        "mode": mode,
        "status": status,
        "source": SOURCE_STORED,
        "scan_date": today_row.scan_date.isoformat() if today_row.scan_date else None,
        "kickoff": today_ko_iso,
        "calculation_target_kickoff": target_raw,
        "odds_fetched_at": odds_fetched_at,
        "static_identity_verified": static_ok,
        **blocking_flags,
        "book_snapshot_status": book_status,
        "warnings": warnings,
    }


def identity_for_balance_build(
    identity: dict[str, Any],
    snapshot_meta: dict[str, Any],
) -> dict[str, Any]:
    """Se snapshot storico blocked, forza inconsistent per fail-closed su Balance."""
    if snapshot_meta.get("mode") != MODE_HISTORICAL:
        return identity
    if snapshot_meta.get("status") != META_BLOCKED:
        return identity
    out = dict(identity)
    out["status"] = "inconsistent"
    merged = list(out.get("warnings") or [])
    for w in snapshot_meta.get("warnings") or []:
        if w not in merged:
            merged.append(w)
    out["warnings"] = merged
    return out


def prepare_kpi_for_historical_balance(
    kpi_panel: dict[str, Any] | None,
    *,
    book_status: str,
) -> dict[str, Any] | None:
    """Rimuove Book da KPI se post-kickoff o non usabile; lascia pilastri Cecchino."""
    if book_status in (BOOK_BLOCKED, BOOK_UNAVAILABLE):
        return strip_book_odds_from_kpi(kpi_panel)
    return kpi_panel


def apply_market_deviation_book_gate(
    balance_v5: dict[str, Any],
    *,
    book_status: str,
    book_warnings: list[str],
) -> dict[str, Any]:
    """Dopo build: se Book non pre-match, market unavailable senza inventare quote."""
    if book_status not in (BOOK_BLOCKED, BOOK_UNAVAILABLE):
        return balance_v5
    if balance_v5.get("status") == "unavailable":
        return balance_v5
    out = dict(balance_v5)
    md = dict(out.get("market_deviation") or {})
    md["status"] = "unavailable"
    md["pairs"] = []
    if book_status == BOOK_BLOCKED:
        md["reading"] = "Scostamento dal mercato storico non disponibile: quote successive al kickoff."
    else:
        md["reading"] = "Scostamento dal mercato storico non disponibile."
    warns = list(md.get("warnings") or [])
    for w in book_warnings:
        if w not in warns:
            warns.append(w)
    if book_status == BOOK_UNAVAILABLE and "historical_book_snapshot_absent" not in warns:
        warns.append("historical_book_snapshot_absent")
    md["warnings"] = warns
    out["market_deviation"] = md
    bw = list(out.get("warnings") or [])
    for w in warns:
        if w not in bw:
            bw.append(w)
    out["warnings"] = bw
    return out


# Esporta helper usati dal service senza riesporre _kickoffs_match
__all__ = [
    "MODE_CURRENT",
    "MODE_HISTORICAL",
    "META_VERIFIED",
    "META_PARTIAL",
    "META_BLOCKED",
    "BOOK_VERIFIED",
    "BOOK_PARTIAL",
    "BOOK_UNAVAILABLE",
    "BOOK_BLOCKED",
    "KICKOFF_TOLERANCE",
    "resolve_balance_detail_mode",
    "build_balance_identity_for_detail",
    "classify_book_snapshot_status",
    "_kpi_has_book_odds",
    "strip_book_odds_from_kpi",
    "evaluate_balance_v5_snapshot_meta",
    "identity_for_balance_build",
    "prepare_kpi_for_historical_balance",
    "apply_market_deviation_book_gate",
]
