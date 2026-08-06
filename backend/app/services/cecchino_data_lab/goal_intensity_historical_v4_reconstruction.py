"""Ricostruzione certificata V4 da input pre-match storici congelati.

Applica la formula V4 corrente agli input storici già disponibili.
Non modifica snapshot/run. Zero API esterne.
"""

from __future__ import annotations

import hashlib
import json
from types import SimpleNamespace
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.cecchino_lab_dataset import CecchinoLabDataset
from app.models.cecchino_lab_match import CecchinoLabMatch
from app.services.cecchino.cecchino_goal_intensity_analysis import (
    VERSION as V4_FORMULA_VERSION,
    _lambda_from_goal_markets,
    build_cecchino_goal_intensity_analysis_from_expected_goals,
)
from app.services.cecchino.cecchino_goal_intensity_v5_statistics_helpers import safe_float
from app.services.cecchino.cecchino_goal_poisson_v2 import FORMULA_DRAW_PT_V1, FORMULA_V2
from app.services.cecchino_data_lab.historical_context_builder import (
    build_input_snapshot,
    build_lab_prematch_contexts,
    compute_goal_markets_from_contexts,
    lab_match_to_proxy,
    sort_proxies,
)

RECONSTRUCTION_VERSION = "cecchino_goal_intensity_v4_historical_reconstruction_v1"
CONTEXT_BUILDER_VERSION = "cecchino_lab_historical_context_builder_v1"

V4_SOURCE_PERSISTED_PAYLOAD = "persisted_v4_payload"
V4_SOURCE_PERSISTED_EXPECTED_GOALS = "persisted_expected_goals_total"
V4_SOURCE_PERSISTED_GOAL_MARKETS_LAMBDA = "persisted_goal_markets_lambda"
V4_SOURCE_RECONSTRUCTED = "reconstructed_current_v4_from_frozen_historical_inputs"
V4_SOURCE_UNAVAILABLE = "unavailable"

REASON_INPUT_MISMATCH = "v4_reconstruction_input_mismatch"
REASON_KPI_MISMATCH = "v4_reconstruction_historical_kpi_mismatch"
REASON_MISSING_CONTEXT = "v4_missing_context_data"
REASON_MISSING_LAMBDA = "v4_reconstruction_lambda_unavailable"
REASON_MISSING_PERSISTED = "missing_persisted_v4_expected_goals"

SCIENTIFIC_DESCRIPTION_RECONSTRUCTED = (
    "current V4 formula applied to frozen historical prematch inputs"
)
SCIENTIFIC_DESCRIPTION_PERSISTED = "persisted at original scan time"

INPUT_CONTEXT_KEYS = (
    "home_context",
    "away_context",
    "home_total",
    "away_total",
    "home_recent_context_5",
    "away_recent_context_5",
    "home_recent_total_6",
    "away_recent_total_6",
)

KPI_COMPARE_MARKETS = ("OVER_1_5", "OVER_2_5")
KPI_ODD_TOLERANCE = 0.01
KPI_PROB_TOLERANCE = 0.00015

GOAL_MARKET_FORMULA_VERSIONS = {
    "ft_pt": FORMULA_V2,
    "draw_pt": FORMULA_DRAW_PT_V1,
}


def _sha256_canonical(payload: Any) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def empty_v4_extract_result(
    *,
    reason: str = REASON_MISSING_PERSISTED,
    v4_source: str = V4_SOURCE_UNAVAILABLE,
) -> dict[str, Any]:
    return {
        "v4_payload": None,
        "v4_source": v4_source,
        "reason": reason,
        "reconstruction_version": None,
        "expected_goals_total": None,
        "input_hash": None,
        "reconstruction_hash": None,
        "goal_market_formula_versions": None,
        "historical_kpi_consistency": None,
        "anti_leakage": None,
        "source_code_commit": None,
        "v4_formula_version": V4_FORMULA_VERSION,
        "context_builder_version": CONTEXT_BUILDER_VERSION,
        "scientific_description": None,
        "persisted_or_reconstructed": None,
    }


class CompetitionProxyCache:
    """Proxy ordinati precaricati per competizione (lookup target O(1))."""

    def __init__(self) -> None:
        self.season_label: str | None = None
        self._by_competition: dict[str, list[SimpleNamespace]] = {}
        self._proxy_by_id: dict[int, SimpleNamespace] = {}
        self._competition_by_match_id: dict[int, str] = {}
        self._load_counts: dict[str, int] = {}
        self.external_api_calls: int = 0

    @classmethod
    def build(cls, db: Session, *, season_label: str) -> CompetitionProxyCache:
        cache = cls()
        cache.season_label = season_label
        datasets = list(
            db.scalars(
                select(CecchinoLabDataset).where(CecchinoLabDataset.season_label == season_label)
            ).all()
        )
        if not datasets:
            return cache

        by_comp: dict[str, list[int]] = {}
        for d in datasets:
            by_comp.setdefault(str(d.competition_name), []).append(int(d.id))

        for comp, ds_ids in by_comp.items():
            matches = list(
                db.scalars(
                    select(CecchinoLabMatch).where(CecchinoLabMatch.dataset_id.in_(ds_ids))
                ).all()
            )
            competition_id = abs(hash(comp)) % (10**9) + 1
            proxies = sort_proxies(
                [lab_match_to_proxy(m, competition_id=competition_id) for m in matches]
            )
            cache._by_competition[comp] = proxies
            cache._load_counts[comp] = len(proxies)
            for p in proxies:
                pid = int(p.id)
                cache._proxy_by_id[pid] = p
                cache._competition_by_match_id[pid] = comp
        return cache

    def get_ordered(self, competition_name: str) -> list[SimpleNamespace]:
        return self._by_competition.get(str(competition_name), [])

    def get_proxy(self, lab_match_id: int) -> SimpleNamespace | None:
        return self._proxy_by_id.get(int(lab_match_id))

    def competitions_loaded(self) -> int:
        return len(self._by_competition)

    def cache_hit_stats(self) -> dict[str, Any]:
        return {
            "season_label": self.season_label,
            "competitions": self.competitions_loaded(),
            "matches_indexed": len(self._proxy_by_id),
            "per_competition": dict(self._load_counts),
            "external_api_calls": self.external_api_calls,
        }


def _normalize_fixture_ids(raw: Any) -> dict[str, list[int]]:
    if not isinstance(raw, dict):
        return {}
    out: dict[str, list[int]] = {}
    for k, v in raw.items():
        if isinstance(v, list):
            try:
                out[str(k)] = [int(x) for x in v]
            except (TypeError, ValueError):
                out[str(k)] = []
        else:
            out[str(k)] = []
    return out


def _normalize_wdl(block: Any) -> dict[str, int] | None:
    if not isinstance(block, dict):
        return None
    wdl = block.get("wdl") if isinstance(block.get("wdl"), dict) else block
    if not isinstance(wdl, dict):
        return None
    try:
        return {
            "wins": int(wdl.get("wins", 0)),
            "draws": int(wdl.get("draws", 0)),
            "losses": int(wdl.get("losses", 0)),
        }
    except (TypeError, ValueError):
        return None


def certify_reconstructed_input_snapshot(
    reconstructed: dict[str, Any],
    frozen: Any,
) -> dict[str, Any]:
    """Confronto semantico input ricostruito vs snapshot.input_snapshot_json."""
    mismatches: list[str] = []
    if not isinstance(frozen, dict):
        return {
            "ok": False,
            "mismatches": ["missing_frozen_input_snapshot"],
            "input_hash": None,
            "reconstruction_hash": _sha256_canonical(reconstructed),
        }

    recon_hash = _sha256_canonical(reconstructed)
    frozen_hash = _sha256_canonical(frozen)

    for key in INPUT_CONTEXT_KEYS:
        left = reconstructed.get(key) if isinstance(reconstructed.get(key), dict) else {}
        right = frozen.get(key) if isinstance(frozen.get(key), dict) else {}
        lw = _normalize_wdl(left)
        rw = _normalize_wdl(right)
        if lw != rw:
            mismatches.append(f"wdl:{key}")
        ls = left.get("sample") if isinstance(left, dict) else None
        rs = right.get("sample") if isinstance(right, dict) else None
        try:
            if int(ls) != int(rs):
                mismatches.append(f"sample:{key}")
        except (TypeError, ValueError):
            if ls != rs:
                mismatches.append(f"sample:{key}")

    if _normalize_fixture_ids(reconstructed.get("fixture_ids")) != _normalize_fixture_ids(
        frozen.get("fixture_ids")
    ):
        mismatches.append("fixture_ids")

    try:
        if int(reconstructed.get("prior_count") or -1) != int(frozen.get("prior_count") or -2):
            mismatches.append("prior_count")
    except (TypeError, ValueError):
        mismatches.append("prior_count")

    if bool(reconstructed.get("leakage_ok")) != bool(frozen.get("leakage_ok")):
        mismatches.append("leakage_ok")

    if _sha256_canonical(reconstructed.get("sample_meta") or {}) != _sha256_canonical(
        frozen.get("sample_meta") or {}
    ):
        mismatches.append("sample_meta")

    return {
        "ok": len(mismatches) == 0,
        "mismatches": mismatches,
        "input_hash": frozen_hash,
        "reconstruction_hash": recon_hash,
        "hashes_equal": frozen_hash == recon_hash,
    }


def _kpi_rows_by_market(historical_kpi_json: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(historical_kpi_json, dict):
        return {}
    rows = historical_kpi_json.get("rows")
    if not isinstance(rows, list):
        return {}
    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        mk = row.get("market_key")
        if mk:
            out[str(mk)] = row
    return out


def check_historical_kpi_consistency(
    goal_markets: dict[str, Any],
    historical_kpi_json: Any,
    *,
    odd_tolerance: float = KPI_ODD_TOLERANCE,
    prob_tolerance: float = KPI_PROB_TOLERANCE,
) -> dict[str, Any]:
    """Controllo diagnostico quote/prob vs KPI storico (non sorgente lambda)."""
    kpi_by_mk = _kpi_rows_by_market(historical_kpi_json)
    compared: list[dict[str, Any]] = []
    failures: list[str] = []

    for mk in KPI_COMPARE_MARKETS:
        kpi_row = kpi_by_mk.get(mk)
        if kpi_row is None:
            continue
        kpi_odd = safe_float(kpi_row.get("quota_cecchino"))
        kpi_prob = safe_float(kpi_row.get("prob_cecchino"))
        if kpi_odd is None and kpi_prob is None:
            continue

        gm = goal_markets.get(mk) if isinstance(goal_markets.get(mk), dict) else {}
        summary = gm.get("summary") if isinstance(gm.get("summary"), dict) else {}
        recon_odd = safe_float(gm.get("final_odd"))
        if recon_odd is None:
            recon_odd = safe_float(summary.get("final_odd"))
        recon_prob = safe_float(summary.get("final_probability"))
        if recon_prob is None:
            recon_prob = safe_float(summary.get("final_probability_capped"))

        odd_diff = None
        prob_diff = None
        odd_ok = True
        prob_ok = True
        if kpi_odd is not None and recon_odd is not None:
            odd_diff = abs(float(recon_odd) - float(kpi_odd))
            odd_ok = odd_diff <= odd_tolerance + 1e-12
        elif kpi_odd is not None and recon_odd is None:
            odd_ok = False
            failures.append(f"{mk}:missing_reconstructed_odd")
        if kpi_prob is not None and recon_prob is not None:
            prob_diff = abs(float(recon_prob) - float(kpi_prob))
            # KPI panel often stores prob from odd (2dp); allow either raw or odd-derived.
            if not (prob_diff <= prob_tolerance + 1e-12):
                # retry vs 1/odd rounded path used by panel
                if recon_odd and recon_odd > 0:
                    derived = round(1.0 / float(recon_odd), 4)
                    alt = abs(derived - float(kpi_prob))
                    if alt <= 0.00015 + 1e-12:
                        prob_diff = alt
                        prob_ok = True
                    else:
                        prob_ok = False
                else:
                    prob_ok = False
            else:
                prob_ok = True
        elif kpi_prob is not None and recon_prob is None and kpi_odd is None:
            prob_ok = False

        entry = {
            "market_key": mk,
            "quota_cecchino": kpi_odd,
            "prob_cecchino": kpi_prob,
            "reconstructed_odd": recon_odd,
            "reconstructed_prob": recon_prob,
            "absolute_odd_diff": odd_diff,
            "absolute_prob_diff": prob_diff,
            "odd_ok": odd_ok,
            "prob_ok": prob_ok,
            "pass": odd_ok and prob_ok,
        }
        compared.append(entry)
        if not entry["pass"]:
            failures.append(mk)

    if not compared:
        status = "skipped_no_kpi_rows"
        passed = True
    elif failures:
        status = "fail"
        passed = False
    else:
        status = "pass"
        passed = True

    return {
        "historical_kpi_consistency_status": status,
        "compared_markets": compared,
        "tolerance": {"odd": odd_tolerance, "prob": prob_tolerance},
        "pass": passed,
        "failures": failures,
    }


def reconstruct_v4_from_frozen_historical_inputs(
    snapshot_like: Any,
    *,
    proxy_cache: CompetitionProxyCache,
    source_code_commit: str | None = None,
) -> dict[str, Any]:
    """Fallback D: V4 da contesti ricostruiti e certificati (solo prior pre-match)."""
    lab_match_id = getattr(snapshot_like, "lab_match_id", None)
    competition_name = getattr(snapshot_like, "competition_name", None)
    if lab_match_id is None or not competition_name:
        return empty_v4_extract_result(reason=REASON_MISSING_CONTEXT)

    target = proxy_cache.get_proxy(int(lab_match_id))
    ordered = proxy_cache.get_ordered(str(competition_name))
    if target is None or not ordered:
        return empty_v4_extract_result(reason=REASON_MISSING_CONTEXT)

    contexts = build_lab_prematch_contexts(competition_ordered=ordered, target=target)
    if not contexts.leakage_ok:
        out = empty_v4_extract_result(reason=REASON_INPUT_MISMATCH)
        out["anti_leakage"] = {
            "leakage_ok": False,
            "target_excluded": True,
            "same_kickoff_excluded": True,
            "result_not_used": True,
        }
        return out

    reconstructed_input = build_input_snapshot(contexts)
    cert = certify_reconstructed_input_snapshot(
        reconstructed_input,
        getattr(snapshot_like, "input_snapshot_json", None),
    )
    if not cert["ok"]:
        out = empty_v4_extract_result(reason=REASON_INPUT_MISMATCH)
        out["input_hash"] = cert.get("input_hash")
        out["reconstruction_hash"] = cert.get("reconstruction_hash")
        out["anti_leakage"] = {
            "leakage_ok": bool(contexts.leakage_ok),
            "target_excluded": True,
            "same_kickoff_excluded": True,
            "result_not_used": True,
            "certification_mismatches": cert.get("mismatches"),
        }
        return out

    goal_markets = compute_goal_markets_from_contexts(contexts)
    lam = _lambda_from_goal_markets(goal_markets)
    if lam is None or lam <= 0:
        out = empty_v4_extract_result(reason=REASON_MISSING_LAMBDA)
        out["input_hash"] = cert.get("input_hash")
        out["reconstruction_hash"] = cert.get("reconstruction_hash")
        out["anti_leakage"] = {
            "leakage_ok": True,
            "target_excluded": True,
            "same_kickoff_excluded": True,
            "result_not_used": True,
        }
        return out

    kpi_check = check_historical_kpi_consistency(
        goal_markets,
        getattr(snapshot_like, "historical_kpi_json", None),
    )
    if not kpi_check.get("pass"):
        out = empty_v4_extract_result(reason=REASON_KPI_MISMATCH)
        out["input_hash"] = cert.get("input_hash")
        out["reconstruction_hash"] = cert.get("reconstruction_hash")
        out["historical_kpi_consistency"] = kpi_check
        out["anti_leakage"] = {
            "leakage_ok": True,
            "target_excluded": True,
            "same_kickoff_excluded": True,
            "result_not_used": True,
        }
        return out

    v4 = build_cecchino_goal_intensity_analysis_from_expected_goals(float(lam))
    return {
        "v4_payload": v4,
        "v4_source": V4_SOURCE_RECONSTRUCTED,
        "reason": None,
        "reconstruction_version": RECONSTRUCTION_VERSION,
        "expected_goals_total": float(lam),
        "input_hash": cert.get("input_hash"),
        "reconstruction_hash": cert.get("reconstruction_hash"),
        "goal_market_formula_versions": dict(GOAL_MARKET_FORMULA_VERSIONS),
        "historical_kpi_consistency": kpi_check,
        "anti_leakage": {
            "leakage_ok": True,
            "target_excluded": True,
            "same_kickoff_excluded": True,
            "result_not_used": True,
            "result_json_not_read_for_prediction": True,
        },
        "source_code_commit": source_code_commit,
        "v4_formula_version": V4_FORMULA_VERSION,
        "context_builder_version": CONTEXT_BUILDER_VERSION,
        "scientific_description": SCIENTIFIC_DESCRIPTION_RECONSTRUCTED,
        "persisted_or_reconstructed": "reconstructed",
    }


def extract_persisted_v4_with_source(
    snapshot_like: Any,
) -> dict[str, Any]:
    """Ordine A→B→C su payload già persistiti (nessuna ricostruzione)."""
    candidates: list[dict[str, Any]] = []
    for attr in (
        "cecchino_output_json",
        "goal_intensity_compatibility_json",
        "module_availability_json",
        "balance_v5_json",
        "historical_kpi_json",
        "input_snapshot_json",
    ):
        block = getattr(snapshot_like, attr, None)
        if isinstance(block, dict):
            candidates.append(block)

    for payload in candidates:
        for key in ("goal_intensity_analysis", "goal_intensity_v4"):
            block = payload.get(key)
            if isinstance(block, dict):
                eg = safe_float(block.get("expected_goals_total"))
                if eg is not None and eg > 0:
                    v4 = build_cecchino_goal_intensity_analysis_from_expected_goals(eg)
                    return {
                        **empty_v4_extract_result(reason="", v4_source=V4_SOURCE_PERSISTED_PAYLOAD),
                        "v4_payload": v4,
                        "v4_source": V4_SOURCE_PERSISTED_PAYLOAD,
                        "reason": None,
                        "expected_goals_total": float(eg),
                        "scientific_description": SCIENTIFIC_DESCRIPTION_PERSISTED,
                        "persisted_or_reconstructed": "persisted",
                        "reconstruction_version": None,
                    }

        eg_direct = safe_float(payload.get("expected_goals_total"))
        if (
            eg_direct is not None
            and eg_direct > 0
            and payload.get("version") == V4_FORMULA_VERSION
        ):
            v4 = build_cecchino_goal_intensity_analysis_from_expected_goals(eg_direct)
            return {
                **empty_v4_extract_result(
                    reason="", v4_source=V4_SOURCE_PERSISTED_EXPECTED_GOALS
                ),
                "v4_payload": v4,
                "v4_source": V4_SOURCE_PERSISTED_EXPECTED_GOALS,
                "reason": None,
                "expected_goals_total": float(eg_direct),
                "scientific_description": SCIENTIFIC_DESCRIPTION_PERSISTED,
                "persisted_or_reconstructed": "persisted",
                "reconstruction_version": None,
            }

        gm = payload.get("goal_markets")
        if isinstance(gm, dict):
            lam = _lambda_from_goal_markets(gm)
            if lam is not None and lam > 0:
                v4 = build_cecchino_goal_intensity_analysis_from_expected_goals(lam)
                return {
                    **empty_v4_extract_result(
                        reason="", v4_source=V4_SOURCE_PERSISTED_GOAL_MARKETS_LAMBDA
                    ),
                    "v4_payload": v4,
                    "v4_source": V4_SOURCE_PERSISTED_GOAL_MARKETS_LAMBDA,
                    "reason": None,
                    "expected_goals_total": float(lam),
                    "goal_market_formula_versions": dict(GOAL_MARKET_FORMULA_VERSIONS),
                    "scientific_description": SCIENTIFIC_DESCRIPTION_PERSISTED,
                    "persisted_or_reconstructed": "persisted",
                    "reconstruction_version": None,
                }
            for _mk, v in gm.items():
                if not isinstance(v, dict):
                    continue
                summary = v.get("summary") if isinstance(v.get("summary"), dict) else v
                lam2 = safe_float(summary.get("lambda") if isinstance(summary, dict) else None)
                if lam2 is not None and lam2 > 0:
                    v4 = build_cecchino_goal_intensity_analysis_from_expected_goals(lam2)
                    return {
                        **empty_v4_extract_result(
                            reason="",
                            v4_source=V4_SOURCE_PERSISTED_GOAL_MARKETS_LAMBDA,
                        ),
                        "v4_payload": v4,
                        "v4_source": V4_SOURCE_PERSISTED_GOAL_MARKETS_LAMBDA,
                        "reason": None,
                        "expected_goals_total": float(lam2),
                        "goal_market_formula_versions": dict(GOAL_MARKET_FORMULA_VERSIONS),
                        "scientific_description": SCIENTIFIC_DESCRIPTION_PERSISTED,
                        "persisted_or_reconstructed": "persisted",
                        "reconstruction_version": None,
                    }

    return empty_v4_extract_result(reason=REASON_MISSING_PERSISTED)


def extract_v4_certified(
    snapshot_like: Any,
    *,
    proxy_cache: CompetitionProxyCache | None = None,
    source_code_commit: str | None = None,
) -> dict[str, Any]:
    """Ordine certificato A→B→C→D. Non sostituisce mai una V4 realmente persistita."""
    persisted = extract_persisted_v4_with_source(snapshot_like)
    if persisted.get("v4_payload") is not None:
        if source_code_commit and not persisted.get("source_code_commit"):
            persisted["source_code_commit"] = source_code_commit
        return persisted

    if proxy_cache is None:
        return persisted

    return reconstruct_v4_from_frozen_historical_inputs(
        snapshot_like,
        proxy_cache=proxy_cache,
        source_code_commit=source_code_commit,
    )


def is_persisted_v4_source(v4_source: str | None) -> bool:
    return v4_source in {
        V4_SOURCE_PERSISTED_PAYLOAD,
        V4_SOURCE_PERSISTED_EXPECTED_GOALS,
        V4_SOURCE_PERSISTED_GOAL_MARKETS_LAMBDA,
    }


def is_reconstructed_v4_source(v4_source: str | None) -> bool:
    return v4_source == V4_SOURCE_RECONSTRUCTED
