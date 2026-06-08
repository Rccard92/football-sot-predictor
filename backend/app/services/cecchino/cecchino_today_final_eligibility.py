"""Validatore finale eleggibilità Cecchino Today — gate post-calcolo."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.models.cecchino_today_fixture import (
    ELIGIBILITY_ELIGIBLE,
    ELIGIBILITY_ERROR,
    ELIGIBILITY_EXCLUDED_CECCHINO_NOT_CALCULABLE,
    ELIGIBILITY_EXCLUDED_INSUFFICIENT_STATS,
    ELIGIBILITY_EXCLUDED_KPI_NOT_CALCULABLE,
    ELIGIBILITY_EXCLUDED_LEAKAGE_FAILED,
    ELIGIBILITY_EXCLUDED_MISSING_1X2,
    ELIGIBILITY_EXCLUDED_MISSING_BOOKMAKER,
    ELIGIBILITY_EXCLUDED_MISSING_PICCHETTO,
    ELIGIBILITY_EXCLUDED_ZERO_PROBABILITY,
)
from app.services.cecchino.cecchino_constants import (
    KEY_AWAY_CONTEXT,
    KEY_AWAY_RECENT_CONTEXT_5,
    KEY_AWAY_RECENT_TOTAL_6,
    KEY_AWAY_TOTAL,
    KEY_HOME_CONTEXT,
    KEY_HOME_RECENT_CONTEXT_5,
    KEY_HOME_RECENT_TOTAL_6,
    KEY_HOME_TOTAL,
    LEAKAGE_FAILED,
    LEAKAGE_UNDEFINED,
    PICCHETTO_KEY_HOME_AWAY,
    PICCHETTO_KEY_LAST5_HOME_AWAY,
    PICCHETTO_KEY_LAST6_TOTALS,
    PICCHETTO_KEY_TOTALS,
    STATUS_AVAILABLE,
    STATUS_INSUFFICIENT_DATA,
    WARNING_LOW_SAMPLE,
    WARNING_ZERO_PROBABILITY,
)
from app.services.cecchino.cecchino_selection_keys import SEL_AWAY, SEL_DRAW, SEL_HOME
from app.services.cecchino.cecchino_today_constants import (
    MIN_AWAY_CONTEXT,
    MIN_AWAY_TOTAL,
    MIN_HOME_CONTEXT,
    MIN_HOME_TOTAL,
    MIN_RECENT_CONTEXT_5,
    MIN_RECENT_TOTAL_6,
)

_REQUIRED_BOOKMAKERS = ("Betfair",)
_REQUIRED_SELECTIONS = ("HOME", "DRAW", "AWAY")
_REQUIRED_PICCHETTI = (
    PICCHETTO_KEY_HOME_AWAY,
    PICCHETTO_KEY_TOTALS,
    PICCHETTO_KEY_LAST5_HOME_AWAY,
    PICCHETTO_KEY_LAST6_TOTALS,
)
_KPI_1X2_KEYS = (SEL_HOME, SEL_DRAW, SEL_AWAY)

_STATS_THRESHOLDS: dict[str, int] = {
    KEY_HOME_CONTEXT: MIN_HOME_CONTEXT,
    KEY_AWAY_CONTEXT: MIN_AWAY_CONTEXT,
    KEY_HOME_TOTAL: MIN_HOME_TOTAL,
    KEY_AWAY_TOTAL: MIN_AWAY_TOTAL,
    KEY_HOME_RECENT_CONTEXT_5: MIN_RECENT_CONTEXT_5,
    KEY_AWAY_RECENT_CONTEXT_5: MIN_RECENT_CONTEXT_5,
    KEY_HOME_RECENT_TOTAL_6: MIN_RECENT_TOTAL_6,
    KEY_AWAY_RECENT_TOTAL_6: MIN_RECENT_TOTAL_6,
}

_IMPORT_INFO_PREFIXES = ("fixtures_ft_imported:",)

_BLOCKING_WARNING_PREFIXES = (
    f"{WARNING_LOW_SAMPLE}:",
    "missing_picchetto_quotas",
    f"{WARNING_ZERO_PROBABILITY}:",
)


@dataclass
class FinalEligibilityResult:
    is_eligible: bool
    eligibility_status: str
    eligibility_reason: str
    blocking_reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    import_info: list[str] = field(default_factory=list)


def partition_scan_warnings(warnings: list[str] | None) -> tuple[list[str], list[str], list[str]]:
    """Separa import_info, blocking da warning string e non-blocking."""
    import_info: list[str] = []
    blocking: list[str] = []
    non_blocking: list[str] = []
    for raw in warnings or []:
        w = str(raw).strip()
        if not w:
            continue
        if any(w.startswith(p) for p in _IMPORT_INFO_PREFIXES):
            import_info.append(w)
            continue
        if _is_blocking_warning(w):
            blocking.append(w)
            continue
        non_blocking.append(w)
    return import_info, blocking, non_blocking


def _is_blocking_warning(w: str) -> bool:
    return any(w.startswith(p) for p in _BLOCKING_WARNING_PREFIXES)


def _num(v: Any) -> float | None:
    if v is None or isinstance(v, str):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _check_bookmaker(odds_snapshot: dict[str, Any] | None) -> tuple[list[str], str | None]:
    blocking: list[str] = []
    if not odds_snapshot:
        for name in _REQUIRED_BOOKMAKERS:
            blocking.append(f"missing_bookmaker:{name}")
        return blocking, ELIGIBILITY_EXCLUDED_MISSING_BOOKMAKER

    books = odds_snapshot.get("bookmakers") or {}
    missing_list = list(odds_snapshot.get("missing") or [])
    any_raw = bool(odds_snapshot.get("raw_by_bookmaker_id"))

    for name in _REQUIRED_BOOKMAKERS:
        if name not in books:
            if name in missing_list or not any_raw:
                blocking.append(f"missing_bookmaker:{name}")
            else:
                blocking.append(f"missing_bookmaker:{name}")
            continue
        vals = books[name]
        if not isinstance(vals, dict):
            blocking.append(f"missing_bookmaker:{name}")
            continue
        for sel in _REQUIRED_SELECTIONS:
            if vals.get(sel) is None:
                blocking.append(f"missing_selection:{name}:{sel}")

    if not blocking:
        return [], None

    if any(b.startswith("missing_bookmaker:") for b in blocking):
        if not any_raw and all(b.startswith("missing_bookmaker:") for b in blocking):
            return blocking, ELIGIBILITY_EXCLUDED_MISSING_BOOKMAKER
        if not books and not any_raw:
            return blocking, ELIGIBILITY_EXCLUDED_MISSING_BOOKMAKER
        if all(b.startswith("missing_bookmaker:") for b in blocking):
            return blocking, ELIGIBILITY_EXCLUDED_MISSING_BOOKMAKER

    return blocking, ELIGIBILITY_EXCLUDED_MISSING_1X2


def _check_stats_samples(stats_snapshot: dict[str, Any] | None) -> list[str]:
    blocking: list[str] = []
    snap = stats_snapshot or {}
    input_snap = snap.get("input_snapshot") or snap
    for key, min_n in _STATS_THRESHOLDS.items():
        block = input_snap.get(key) or {}
        sample = int(block.get("sample_count") or 0) if isinstance(block, dict) else 0
        if sample < min_n:
            blocking.append(f"low_sample:{key}")
    return blocking


def _collect_low_sample_from_output(cecchino_output: dict[str, Any] | None) -> list[str]:
    blocking: list[str] = []
    if not cecchino_output:
        return blocking
    for w in cecchino_output.get("warnings") or []:
        ws = str(w)
        if ws.startswith(f"{WARNING_LOW_SAMPLE}:"):
            blocking.append(ws)
    picchetti = cecchino_output.get("picchetti") or {}
    for pic_key, block in picchetti.items():
        if not isinstance(block, dict):
            continue
        for w in block.get("warnings") or []:
            ws = str(w)
            if ws.startswith(f"{WARNING_LOW_SAMPLE}:"):
                blocking.append(ws)
        if block.get("status") == STATUS_INSUFFICIENT_DATA:
            blocking.append(f"picchetto_insufficient:{pic_key}")
    return blocking


def _check_picchetti(cecchino_output: dict[str, Any] | None) -> list[str]:
    blocking: list[str] = []
    if not cecchino_output:
        blocking.append("missing_picchetto_quotas:all")
        return blocking

    picchetti = cecchino_output.get("picchetti") or {}
    final = cecchino_output.get("final") or {}
    for w in final.get("warnings") or []:
        ws = str(w)
        if ws.startswith("missing_picchetto_quotas"):
            blocking.append(ws if ":" in ws else "missing_picchetto_quotas")

    for w in cecchino_output.get("warnings") or []:
        ws = str(w)
        if ws.startswith("missing_picchetto_quotas"):
            blocking.append(ws)

    for pic_key in _REQUIRED_PICCHETTI:
        block = picchetti.get(pic_key)
        if block is None:
            blocking.append(f"missing_picchetto:{pic_key}")
            continue
        if not isinstance(block, dict):
            blocking.append(f"missing_picchetto:{pic_key}")
            continue
        status = block.get("status")
        if status == STATUS_INSUFFICIENT_DATA:
            blocking.append(f"missing_picchetto:{pic_key}")
            continue
        for outcome in ("outcome_1", "outcome_x", "outcome_2"):
            oc = block.get(outcome) or {}
            if not isinstance(oc, dict) or oc.get("quota") is None:
                blocking.append(f"missing_picchetto_quota:{pic_key}:{outcome}")

    return list(dict.fromkeys(blocking))


def _check_zero_probability(
    cecchino_output: dict[str, Any] | None,
    extra_warnings: list[str],
) -> list[str]:
    blocking: list[str] = []
    sources: list[str] = list(extra_warnings)
    if cecchino_output:
        sources.extend(str(w) for w in cecchino_output.get("warnings") or [])
        final = cecchino_output.get("final") or {}
        sources.extend(str(w) for w in final.get("warnings") or [])
        picchetti = cecchino_output.get("picchetti") or {}
        for block in picchetti.values():
            if isinstance(block, dict):
                sources.extend(str(w) for w in block.get("warnings") or [])

    for w in sources:
        if w.startswith(f"{WARNING_ZERO_PROBABILITY}:"):
            blocking.append(w)

    if cecchino_output:
        final = cecchino_output.get("final") or {}
        for prob_key in ("prob_1", "prob_x", "prob_2"):
            p = _num(final.get(prob_key))
            if p is not None and p <= 0:
                sel = prob_key.replace("prob_", "").upper()
                if sel == "1":
                    blocking.append(f"{WARNING_ZERO_PROBABILITY}:1")
                elif sel == "X":
                    blocking.append(f"{WARNING_ZERO_PROBABILITY}:X")
                elif sel == "2":
                    blocking.append(f"{WARNING_ZERO_PROBABILITY}:2")

    return list(dict.fromkeys(blocking))


def _check_final_odds_complete(final: dict[str, Any] | None) -> tuple[bool, list[str]]:
    if not final:
        return False, ["final_odds_missing"]
    if final.get("status") != STATUS_AVAILABLE:
        return False, [f"final_odds_status:{final.get('status') or 'missing'}"]
    missing: list[str] = []
    for key in ("quota_1", "quota_x", "quota_2", "prob_1", "prob_x", "prob_2"):
        if _num(final.get(key)) is None:
            missing.append(f"missing_final_odds:{key}")
    if missing:
        return False, missing
    return True, []


def _check_kpi_1x2_complete(kpi_panel: dict[str, Any] | None) -> tuple[bool, list[str], str]:
    if not kpi_panel:
        return False, ["kpi_panel_missing"], "insufficient_data"

    rows = kpi_panel.get("rows") or []
    row_by_key = {r.get("market_key"): r for r in rows if isinstance(r, dict)}
    missing_rows: list[str] = []
    is_v2 = kpi_panel.get("version") == "cecchino_kpi_v2_betfair"

    for key in _KPI_1X2_KEYS:
        row = row_by_key.get(key)
        if row is None:
            missing_rows.append(key)
            continue
        if is_v2:
            cec = _num(row.get("quota_cecchino"))
            book = _num(row.get("quota_book"))
            edge = row.get("edge_pct")
            if cec is None:
                missing_rows.append(f"{key}:quota_cecchino")
            if book is None:
                missing_rows.append(f"{key}:quota_book")
            if edge is None and (cec is None or book is None):
                missing_rows.append(f"{key}:edge_pct")
        else:
            cec = _num(row.get("cecchino"))
            book = _num(row.get("book"))
            edge = row.get("edge")
            if cec is None:
                missing_rows.append(f"{key}:cecchino")
            if book is None:
                missing_rows.append(f"{key}:book")
            if edge is None and (cec is None or book is None):
                missing_rows.append(f"{key}:edge")

    if missing_rows:
        bm_status = kpi_panel.get("bookmaker_status") or "unknown"
        return False, missing_rows, bm_status

    return True, [], kpi_panel.get("bookmaker_status") or "available"


def build_cecchino_debug(cecchino_output: dict[str, Any] | None) -> dict[str, Any]:
    final = (cecchino_output or {}).get("final") or {}
    missing_picchetto: list[str] = []
    zero_prob: list[str] = []
    missing_final: list[str] = []

    for w in final.get("warnings") or []:
        ws = str(w)
        if ws.startswith("missing_picchetto_quotas"):
            missing_picchetto.append(ws)
        if ws.startswith(f"{WARNING_ZERO_PROBABILITY}:"):
            zero_prob.append(ws)

    if cecchino_output:
        for w in cecchino_output.get("warnings") or []:
            ws = str(w)
            if ws.startswith("missing_picchetto_quotas"):
                missing_picchetto.append(ws)
            if ws.startswith(f"{WARNING_ZERO_PROBABILITY}:"):
                zero_prob.append(ws)

    _, final_missing = _check_final_odds_complete(final if final else None)
    missing_final = final_missing

    return {
        "missing_picchetto_quotas": list(dict.fromkeys(missing_picchetto)),
        "zero_probability": list(dict.fromkeys(zero_prob)),
        "final_odds_status": final.get("status"),
        "missing_final_odds": missing_final,
    }


def build_kpi_debug(kpi_panel: dict[str, Any] | None) -> dict[str, Any]:
    ok, missing_rows, kpi_status = _check_kpi_1x2_complete(kpi_panel)
    return {
        "kpi_status": "available" if ok else (kpi_status if kpi_status != "available" else "insufficient_data"),
        "missing_rows": missing_rows,
    }


def _reason_message(status: str, blocking: list[str]) -> str:
    messages = {
        ELIGIBILITY_EXCLUDED_MISSING_BOOKMAKER: "Bookmaker obbligatorio mancante",
        ELIGIBILITY_EXCLUDED_MISSING_1X2: "Mercato 1X2 incompleto su Betfair",
        ELIGIBILITY_EXCLUDED_INSUFFICIENT_STATS: "Statistiche o campioni insufficienti",
        ELIGIBILITY_EXCLUDED_LEAKAGE_FAILED: "Leakage check non superato",
        ELIGIBILITY_EXCLUDED_MISSING_PICCHETTO: "Picchetto Cecchino obbligatorio mancante o incompleto",
        ELIGIBILITY_EXCLUDED_ZERO_PROBABILITY: "Probabilità zero su esito 1/X/2",
        ELIGIBILITY_EXCLUDED_CECCHINO_NOT_CALCULABLE: "Quote finali Cecchino non calcolabili",
        ELIGIBILITY_EXCLUDED_KPI_NOT_CALCULABLE: "KPI 1X2 non calcolabile",
        ELIGIBILITY_ERROR: "Errore durante il calcolo Cecchino",
        ELIGIBILITY_ELIGIBLE: "Eleggibile",
    }
    base = messages.get(status, status)
    if blocking:
        return f"{base}: {blocking[0]}"
    return base


def validate_cecchino_today_final_eligibility(
    *,
    odds_snapshot: dict[str, Any] | None,
    stats_snapshot: dict[str, Any] | None,
    cecchino_output: dict[str, Any] | None,
    kpi_panel: dict[str, Any] | None,
    warnings: list[str] | None,
    leakage_status: str | None,
    calc_status: str | None = None,
) -> FinalEligibilityResult:
    import_info, warning_blocking, non_blocking = partition_scan_warnings(warnings)
    all_blocking: list[str] = list(warning_blocking)
    soft_warnings: list[str] = list(non_blocking)

    if calc_status == "error":
        return FinalEligibilityResult(
            is_eligible=False,
            eligibility_status=ELIGIBILITY_ERROR,
            eligibility_reason=_reason_message(ELIGIBILITY_ERROR, all_blocking),
            blocking_reasons=all_blocking or ["calculation_error"],
            warnings=soft_warnings,
            import_info=import_info,
        )

    bm_blocking, bm_status = _check_bookmaker(odds_snapshot)
    if bm_blocking:
        status = bm_status or ELIGIBILITY_EXCLUDED_MISSING_BOOKMAKER
        merged = list(dict.fromkeys(all_blocking + bm_blocking))
        return FinalEligibilityResult(
            is_eligible=False,
            eligibility_status=status,
            eligibility_reason=_reason_message(status, merged),
            blocking_reasons=merged,
            warnings=soft_warnings,
            import_info=import_info,
        )

    stats_blocking = _check_stats_samples(stats_snapshot)
    stats_blocking.extend(_collect_low_sample_from_output(cecchino_output))
    stats_blocking = list(dict.fromkeys(stats_blocking + [w for w in all_blocking if w.startswith(f"{WARNING_LOW_SAMPLE}:")]))
    if stats_blocking:
        return FinalEligibilityResult(
            is_eligible=False,
            eligibility_status=ELIGIBILITY_EXCLUDED_INSUFFICIENT_STATS,
            eligibility_reason=_reason_message(ELIGIBILITY_EXCLUDED_INSUFFICIENT_STATS, stats_blocking),
            blocking_reasons=stats_blocking,
            warnings=soft_warnings,
            import_info=import_info,
        )

    if leakage_status == LEAKAGE_FAILED:
        blocking = ["leakage_check_failed"]
        return FinalEligibilityResult(
            is_eligible=False,
            eligibility_status=ELIGIBILITY_EXCLUDED_LEAKAGE_FAILED,
            eligibility_reason=_reason_message(ELIGIBILITY_EXCLUDED_LEAKAGE_FAILED, blocking),
            blocking_reasons=blocking,
            warnings=soft_warnings,
            import_info=import_info,
        )

    if leakage_status in (LEAKAGE_UNDEFINED, "undefined", None, ""):
        soft_warnings.append("leakage_check:undefined")

    pic_blocking = _check_picchetti(cecchino_output)
    pic_blocking.extend([w for w in all_blocking if "missing_picchetto" in w])
    pic_blocking = list(dict.fromkeys(pic_blocking))
    if pic_blocking:
        return FinalEligibilityResult(
            is_eligible=False,
            eligibility_status=ELIGIBILITY_EXCLUDED_MISSING_PICCHETTO,
            eligibility_reason=_reason_message(ELIGIBILITY_EXCLUDED_MISSING_PICCHETTO, pic_blocking),
            blocking_reasons=pic_blocking,
            warnings=soft_warnings,
            import_info=import_info,
        )

    zero_blocking = _check_zero_probability(cecchino_output, all_blocking)
    if zero_blocking:
        return FinalEligibilityResult(
            is_eligible=False,
            eligibility_status=ELIGIBILITY_EXCLUDED_ZERO_PROBABILITY,
            eligibility_reason=_reason_message(ELIGIBILITY_EXCLUDED_ZERO_PROBABILITY, zero_blocking),
            blocking_reasons=zero_blocking,
            warnings=soft_warnings,
            import_info=import_info,
        )

    final = (cecchino_output or {}).get("final") or {}
    final_ok, final_blocking = _check_final_odds_complete(final)
    if not final_ok:
        return FinalEligibilityResult(
            is_eligible=False,
            eligibility_status=ELIGIBILITY_EXCLUDED_CECCHINO_NOT_CALCULABLE,
            eligibility_reason=_reason_message(ELIGIBILITY_EXCLUDED_CECCHINO_NOT_CALCULABLE, final_blocking),
            blocking_reasons=final_blocking,
            warnings=soft_warnings,
            import_info=import_info,
        )

    kpi_ok, kpi_missing, _ = _check_kpi_1x2_complete(kpi_panel)
    if not kpi_ok:
        return FinalEligibilityResult(
            is_eligible=False,
            eligibility_status=ELIGIBILITY_EXCLUDED_KPI_NOT_CALCULABLE,
            eligibility_reason=_reason_message(ELIGIBILITY_EXCLUDED_KPI_NOT_CALCULABLE, kpi_missing),
            blocking_reasons=[f"kpi_missing:{m}" for m in kpi_missing],
            warnings=soft_warnings,
            import_info=import_info,
        )

    return FinalEligibilityResult(
        is_eligible=True,
        eligibility_status=ELIGIBILITY_ELIGIBLE,
        eligibility_reason=_reason_message(ELIGIBILITY_ELIGIBLE, []),
        blocking_reasons=[],
        warnings=soft_warnings,
        import_info=import_info,
    )
