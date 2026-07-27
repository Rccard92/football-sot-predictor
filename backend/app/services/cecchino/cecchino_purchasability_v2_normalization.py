"""Normalizzazione storica Acquistabilità v2 — profilo congelato pre-match."""

from __future__ import annotations

import hashlib
import json
import math
import threading
from datetime import date, datetime
from typing import Any

from app.schemas.cecchino_purchasability_v2 import (
    PURCHASABILITY_V2_NORM_PROFILE_CUTOFF,
    PURCHASABILITY_V2_NORM_PROFILE_VERSION,
)
from app.services.cecchino.cecchino_purchasability_audit import make_json_safe
from app.services.cecchino.cecchino_purchasability_v2_opposition import (
    SCOPE_GOALS_FT_2_5,
    SCOPE_GOALS_HT_1_5,
    SCOPE_OUTCOMES,
    PROB_SUBGROUP_DOUBLE_CHANCE,
    PROB_SUBGROUP_GOALS_FT,
    PROB_SUBGROUP_GOALS_HT,
    PROB_SUBGROUP_MATCH_WINNER,
    competitors_for_market,
    decision_group_for_market,
    is_v2_supported_market,
    probability_competitors_for_market,
    probability_subgroup_for_market,
    resolve_opposite_selection,
)

# Cap provvisori versionati (±)
PROVISIONAL_CAPS: dict[str, float] = {
    "edge_pct": 20.0,
    "vantaggio_prob_pp": 20.0,
    "dominance_rating": 20.0,
    "dominance_edge_pct": 10.0,
    "dominance_probability_pp": 15.0,
    "shift_book_cecchino_pp": 20.0,
    "opposite_contrast_pp": 20.0,
}

NORM_COMPONENTS = tuple(PROVISIONAL_CAPS.keys())

PROFILE_SCOPES = (
    SCOPE_OUTCOMES,
    SCOPE_GOALS_FT_2_5,
    SCOPE_GOALS_HT_1_5,
)

PROB_SCOPES = (
    PROB_SUBGROUP_MATCH_WINNER,
    PROB_SUBGROUP_DOUBLE_CHANCE,
    PROB_SUBGROUP_GOALS_FT,
    PROB_SUBGROUP_GOALS_HT,
)

COMPONENT_SCOPE_MAP: dict[str, tuple[str, ...]] = {
    "edge_pct": PROFILE_SCOPES,
    "vantaggio_prob_pp": PROFILE_SCOPES,
    "dominance_rating": PROFILE_SCOPES,
    "dominance_edge_pct": PROFILE_SCOPES,
    "dominance_probability_pp": PROB_SCOPES,
    "shift_book_cecchino_pp": PROFILE_SCOPES,
    "opposite_contrast_pp": PROFILE_SCOPES,
}

MIN_SIDE_SAMPLES = 15
GLOBAL_SCOPE = "GLOBAL"

_cache_lock = threading.Lock()
_profile_cache: dict[str, dict[str, Any]] = {}


def invalidate_v2_norm_profile_cache() -> None:
    """Invalida cache process-local (test / reload esplicito)."""
    with _cache_lock:
        _profile_cache.clear()


def nearest_rank_percentile(values: list[float], percentile: float = 0.95) -> float | None:
    """Percentile nearest-rank deterministico: rank = ceil(p × n)."""
    if not values:
        return None
    if percentile <= 0:
        return sorted(values)[0]
    if percentile >= 1:
        return sorted(values)[-1]
    sorted_vals = sorted(float(v) for v in values)
    n = len(sorted_vals)
    rank = int(math.ceil(percentile * n))
    rank = max(1, min(n, rank))
    return sorted_vals[rank - 1]


def clamp01_100(value: float) -> float:
    return max(0.0, min(100.0, float(value)))


def zero_anchored_normalize(
    raw: float,
    *,
    positive_cap: float,
    negative_cap: float,
) -> tuple[float, bool]:
    """Restituisce (normalized 0–100, clipping_applied)."""
    x = float(raw)
    clipping = False
    if x == 0.0:
        return 50.0, False
    if x > 0:
        if positive_cap <= 0:
            return 50.0, False
        ratio = x / positive_cap
        if ratio > 1.0:
            clipping = True
            ratio = 1.0
        return clamp01_100(50.0 + 50.0 * ratio), clipping
    if negative_cap <= 0:
        return 50.0, False
    ratio = abs(x) / negative_cap
    if ratio > 1.0:
        clipping = True
        ratio = 1.0
    return clamp01_100(50.0 - 50.0 * ratio), clipping


def _empty_side_bucket() -> dict[str, list[float]]:
    return {"positive": [], "negative_abs": []}


def _new_accumulator() -> dict[str, Any]:
    acc: dict[str, Any] = {
        "by_component_scope": {},
        "by_component_global": {},
    }
    for comp in NORM_COMPONENTS:
        acc["by_component_global"][comp] = _empty_side_bucket()
        scopes = COMPONENT_SCOPE_MAP.get(comp, PROFILE_SCOPES)
        for scope in scopes:
            key = f"{comp}::{scope}"
            acc["by_component_scope"][key] = _empty_side_bucket()
    return acc


def _push_value(bucket: dict[str, list[float]], value: float | None) -> None:
    if value is None:
        return
    try:
        v = float(value)
    except (TypeError, ValueError):
        return
    if not math.isfinite(v) or v == 0.0:
        return
    if v > 0:
        bucket["positive"].append(v)
    else:
        bucket["negative_abs"].append(abs(v))


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(f):
        return None
    return f


def _panel_rows(kpi_panel: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(kpi_panel, dict):
        return []
    rows = kpi_panel.get("rows")
    if not isinstance(rows, list):
        return []
    return [r for r in rows if isinstance(r, dict)]


def _index_rows(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        mk = row.get("market_key") or row.get("segno")
        if isinstance(mk, str) and mk:
            out[mk] = row
    return out


def collect_fixture_component_observations(
    kpi_panel: dict[str, Any] | None,
    *,
    fair_book_by_market: dict[str, dict[str, Any] | None] | None = None,
    model_context_by_market: dict[str, float | None] | None = None,
) -> list[dict[str, Any]]:
    """Estrae osservazioni pre-match per costruire il profilo (no post-match)."""
    rows = _panel_rows(kpi_panel)
    by_mk = _index_rows(rows)
    fair_map = fair_book_by_market or {}
    model_map = model_context_by_market or {}
    fair_probs: dict[str, float | None] = {}
    for mk, info in fair_map.items():
        if isinstance(info, dict):
            fair_probs[mk] = _safe_float(info.get("fair_book_probability"))
        else:
            fair_probs[mk] = _safe_float(info)

    observations: list[dict[str, Any]] = []
    for mk, row in by_mk.items():
        if not is_v2_supported_market(mk):
            continue
        scope = decision_group_for_market(mk)
        prob_scope = probability_subgroup_for_market(mk)
        if scope is None:
            continue

        edge = _safe_float(row.get("edge_pct"))
        vant = _safe_float(row.get("vantaggio_prob"))
        vant_pp = None if vant is None else vant * 100.0
        rating = _safe_float(row.get("rating"))
        model_p = _safe_float(model_map.get(mk))
        if model_p is None:
            model_p = _safe_float(row.get("prob_cecchino"))
        fair_p = fair_probs.get(mk)

        observations.append(
            {
                "component": "edge_pct",
                "scope": scope,
                "value": edge,
            }
        )
        observations.append(
            {
                "component": "vantaggio_prob_pp",
                "scope": scope,
                "value": vant_pp,
            }
        )

        # Dominanza Rating / Edge nel gruppo decisionale
        comps = competitors_for_market(mk)
        if rating is not None:
            best_r = None
            for c in comps:
                cr = _safe_float((by_mk.get(c) or {}).get("rating"))
                if cr is None:
                    continue
                if best_r is None or cr > best_r:
                    best_r = cr
            if best_r is not None:
                observations.append(
                    {
                        "component": "dominance_rating",
                        "scope": scope,
                        "value": rating - best_r,
                    }
                )
        if edge is not None:
            best_e = None
            for c in comps:
                ce = _safe_float((by_mk.get(c) or {}).get("edge_pct"))
                if ce is None:
                    continue
                if best_e is None or ce > best_e:
                    best_e = ce
            if best_e is not None:
                observations.append(
                    {
                        "component": "dominance_edge_pct",
                        "scope": scope,
                        "value": edge - best_e,
                    }
                )

        # Dominanza probabilità nel sottogruppo
        if model_p is not None and prob_scope is not None:
            pcomps = probability_competitors_for_market(mk)
            best_p = None
            for c in pcomps:
                cp = _safe_float(model_map.get(c))
                if cp is None:
                    cp = _safe_float((by_mk.get(c) or {}).get("prob_cecchino"))
                if cp is None:
                    continue
                if best_p is None or cp > best_p:
                    best_p = cp
            if best_p is not None:
                observations.append(
                    {
                        "component": "dominance_probability_pp",
                        "scope": prob_scope,
                        "value": (model_p - best_p) * 100.0,
                    }
                )

        if model_p is not None and fair_p is not None:
            observations.append(
                {
                    "component": "shift_book_cecchino_pp",
                    "scope": scope,
                    "value": (model_p - fair_p) * 100.0,
                }
            )

        opp = resolve_opposite_selection(mk, fair_book_by_market=fair_probs)
        opp_fair = _safe_float(opp.get("opposite_fair_book_probability"))
        if model_p is not None and opp_fair is not None:
            observations.append(
                {
                    "component": "opposite_contrast_pp",
                    "scope": scope,
                    "value": (model_p - opp_fair) * 100.0,
                }
            )

    return observations


def _ingest_observations(acc: dict[str, Any], observations: list[dict[str, Any]]) -> None:
    for obs in observations:
        comp = obs.get("component")
        scope = obs.get("scope")
        value = obs.get("value")
        if comp not in NORM_COMPONENTS or not isinstance(scope, str):
            continue
        _push_value(acc["by_component_global"][comp], _safe_float(value))
        key = f"{comp}::{scope}"
        if key in acc["by_component_scope"]:
            _push_value(acc["by_component_scope"][key], _safe_float(value))


def _caps_from_bucket(bucket: dict[str, list[float]]) -> dict[str, Any]:
    pos = list(bucket.get("positive") or [])
    neg = list(bucket.get("negative_abs") or [])
    return {
        "positive_cap": nearest_rank_percentile(pos, 0.95),
        "negative_cap": nearest_rank_percentile(neg, 0.95),
        "sample_positive": len(pos),
        "sample_negative": len(neg),
        "sample_total": len(pos) + len(neg),
    }


def finalize_profile_from_accumulator(
    acc: dict[str, Any],
    *,
    version: str = PURCHASABILITY_V2_NORM_PROFILE_VERSION,
    cutoff: str = PURCHASABILITY_V2_NORM_PROFILE_CUTOFF,
    fixtures_seen: int = 0,
) -> dict[str, Any]:
    components: dict[str, Any] = {}
    for comp in NORM_COMPONENTS:
        scopes = COMPONENT_SCOPE_MAP.get(comp, PROFILE_SCOPES)
        scope_caps: dict[str, Any] = {}
        for scope in scopes:
            key = f"{comp}::{scope}"
            scope_caps[scope] = _caps_from_bucket(
                acc["by_component_scope"].get(key, _empty_side_bucket())
            )
        components[comp] = {
            "scopes": scope_caps,
            "global": _caps_from_bucket(acc["by_component_global"][comp]),
            "provisional_cap": PROVISIONAL_CAPS[comp],
        }

    profile = {
        "version": version,
        "cutoff": cutoff,
        "fixtures_seen": fixtures_seen,
        "components": components,
        "min_side_samples": MIN_SIDE_SAMPLES,
        "method": "nearest_rank_p95_zero_anchored",
        "source": "cecchino_today_pre_match_kpi_panel",
        "excludes_post_match": True,
        "excludes_cecchino_lab": True,
    }
    profile["hash"] = compute_profile_hash(profile)
    profile["summary"] = {
        "version": version,
        "cutoff": cutoff,
        "fixtures_seen": fixtures_seen,
        "components": list(NORM_COMPONENTS),
        "hash": profile["hash"],
    }
    return make_json_safe(profile)


def compute_profile_hash(profile: dict[str, Any]) -> str:
    payload = {
        "version": profile.get("version"),
        "cutoff": profile.get("cutoff"),
        "min_side_samples": profile.get("min_side_samples"),
        "method": profile.get("method"),
        "components": profile.get("components"),
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def build_empty_provisional_profile(
    *,
    version: str = PURCHASABILITY_V2_NORM_PROFILE_VERSION,
    cutoff: str = PURCHASABILITY_V2_NORM_PROFILE_CUTOFF,
) -> dict[str, Any]:
    return finalize_profile_from_accumulator(
        _new_accumulator(),
        version=version,
        cutoff=cutoff,
        fixtures_seen=0,
    )


def resolve_caps_for_component(
    profile: dict[str, Any],
    *,
    component: str,
    scope: str,
) -> dict[str, Any]:
    """Risolve cap positivo/negativo con fallback documentato."""
    provisional = float(PROVISIONAL_CAPS.get(component, 20.0))
    components = profile.get("components") if isinstance(profile, dict) else None
    if not isinstance(components, dict) or component not in components:
        return {
            "positive_cap": provisional,
            "negative_cap": provisional,
            "cap_source": "provisional_versioned_fallback",
            "sample_positive": 0,
            "sample_negative": 0,
            "sample_total": 0,
            "profile_scope": scope,
            "profile_version": profile.get("version") if isinstance(profile, dict) else None,
        }

    entry = components[component]
    scope_data = (entry.get("scopes") or {}).get(scope) or {}
    global_data = entry.get("global") or {}

    pos_cap = None
    neg_cap = None
    pos_src = "provisional_versioned_fallback"
    neg_src = "provisional_versioned_fallback"
    sample_pos = int(scope_data.get("sample_positive") or 0)
    sample_neg = int(scope_data.get("sample_negative") or 0)

    # Positivo
    if sample_pos >= MIN_SIDE_SAMPLES and scope_data.get("positive_cap") is not None:
        pos_cap = float(scope_data["positive_cap"])
        pos_src = "historical_scope"
    elif int(global_data.get("sample_positive") or 0) >= MIN_SIDE_SAMPLES and global_data.get(
        "positive_cap"
    ) is not None:
        pos_cap = float(global_data["positive_cap"])
        pos_src = "historical_global_fallback"
        sample_pos = int(global_data.get("sample_positive") or 0)
    else:
        pos_cap = provisional
        pos_src = "provisional_versioned_fallback"

    # Negativo
    if sample_neg >= MIN_SIDE_SAMPLES and scope_data.get("negative_cap") is not None:
        neg_cap = float(scope_data["negative_cap"])
        neg_src = "historical_scope"
    elif int(global_data.get("sample_negative") or 0) >= MIN_SIDE_SAMPLES and global_data.get(
        "negative_cap"
    ) is not None:
        neg_cap = float(global_data["negative_cap"])
        neg_src = "historical_global_fallback"
        sample_neg = int(global_data.get("sample_negative") or 0)
    else:
        neg_cap = provisional
        neg_src = "provisional_versioned_fallback"

    # Cap source aggregato: peggiore priorità (provisional > global > scope)
    priority = {
        "historical_scope": 0,
        "historical_global_fallback": 1,
        "provisional_versioned_fallback": 2,
    }
    cap_source = pos_src if priority[pos_src] >= priority[neg_src] else neg_src

    return {
        "positive_cap": pos_cap,
        "negative_cap": neg_cap,
        "cap_source": cap_source,
        "sample_positive": sample_pos,
        "sample_negative": sample_neg,
        "sample_total": sample_pos + sample_neg,
        "profile_scope": scope,
        "profile_version": profile.get("version"),
    }


def normalize_component_value(
    raw_value: float | None,
    *,
    component: str,
    scope: str,
    profile: dict[str, Any],
) -> dict[str, Any]:
    if raw_value is None:
        return {
            "raw_value": None,
            "normalized_value": None,
            "positive_cap": None,
            "negative_cap": None,
            "profile_scope": scope,
            "profile_version": profile.get("version") if isinstance(profile, dict) else None,
            "sample_total": None,
            "sample_positive": None,
            "sample_negative": None,
            "cap_source": None,
            "clipping_applied": None,
            "status": "missing",
        }
    caps = resolve_caps_for_component(profile, component=component, scope=scope)
    norm, clipping = zero_anchored_normalize(
        float(raw_value),
        positive_cap=float(caps["positive_cap"]),
        negative_cap=float(caps["negative_cap"]),
    )
    return {
        "raw_value": float(raw_value),
        "normalized_value": round(norm, 4),
        "positive_cap": caps["positive_cap"],
        "negative_cap": caps["negative_cap"],
        "profile_scope": caps["profile_scope"],
        "profile_version": caps["profile_version"],
        "sample_total": caps["sample_total"],
        "sample_positive": caps["sample_positive"],
        "sample_negative": caps["sample_negative"],
        "cap_source": caps["cap_source"],
        "clipping_applied": clipping,
        "status": "available",
    }


def _parse_cutoff(cutoff: str) -> date:
    return date.fromisoformat(cutoff)


def build_normalization_profile_from_db(
    db: Any,
    *,
    version: str = PURCHASABILITY_V2_NORM_PROFILE_VERSION,
    cutoff: str = PURCHASABILITY_V2_NORM_PROFILE_CUTOFF,
    use_cache: bool = True,
) -> dict[str, Any]:
    """Costruisce profilo da Cecchino Today pre-match fino al cutoff incluso."""
    cache_key = f"{version}::{cutoff}"
    if use_cache:
        with _cache_lock:
            cached = _profile_cache.get(cache_key)
            if cached is not None:
                return cached

    from app.models.cecchino_today_fixture import CecchinoTodayFixture
    from app.services.cecchino.cecchino_purchasability_fair_book import (
        resolve_fair_book_for_panel_rows,
    )
    from app.services.cecchino.cecchino_purchasability_features import (
        build_model_context_probability_map,
    )
    from sqlalchemy import select

    cutoff_date = _parse_cutoff(cutoff)
    acc = _new_accumulator()
    fixtures_seen = 0

    stmt = select(CecchinoTodayFixture).where(
        CecchinoTodayFixture.scan_date <= cutoff_date,
        CecchinoTodayFixture.kpi_panel_json.is_not(None),
    )
    rows = db.scalars(stmt).all()
    for row in rows:
        panel = row.kpi_panel_json
        if not isinstance(panel, dict):
            continue
        # Solo eligible / con panel rows
        panel_rows = _panel_rows(panel)
        if not panel_rows:
            continue
        try:
            fair_by = resolve_fair_book_for_panel_rows(panel_rows)
            model_by = build_model_context_probability_map(panel_rows)
        except Exception:
            fair_by = {}
            model_by = {}
        # model_by può essere dict market -> meta
        model_probs: dict[str, float | None] = {}
        if isinstance(model_by, dict):
            for mk, meta in model_by.items():
                if isinstance(meta, dict):
                    model_probs[mk] = _safe_float(meta.get("model_context_probability"))
                else:
                    model_probs[mk] = _safe_float(meta)
        obs = collect_fixture_component_observations(
            panel,
            fair_book_by_market=fair_by if isinstance(fair_by, dict) else {},
            model_context_by_market=model_probs,
        )
        if obs:
            _ingest_observations(acc, obs)
            fixtures_seen += 1

    profile = finalize_profile_from_accumulator(
        acc,
        version=version,
        cutoff=cutoff,
        fixtures_seen=fixtures_seen,
    )
    if use_cache:
        with _cache_lock:
            _profile_cache[cache_key] = profile
    return profile


def get_or_build_normalization_profile(
    db: Any | None = None,
    *,
    profile: dict[str, Any] | None = None,
    version: str = PURCHASABILITY_V2_NORM_PROFILE_VERSION,
    cutoff: str = PURCHASABILITY_V2_NORM_PROFILE_CUTOFF,
) -> dict[str, Any]:
    if isinstance(profile, dict) and profile.get("version"):
        return profile
    cache_key = f"{version}::{cutoff}"
    with _cache_lock:
        cached = _profile_cache.get(cache_key)
        if cached is not None:
            return cached
    if db is not None:
        return build_normalization_profile_from_db(
            db, version=version, cutoff=cutoff, use_cache=True
        )
    # Senza DB: profilo provvisorio (test / derive offline)
    provisional = build_empty_provisional_profile(version=version, cutoff=cutoff)
    with _cache_lock:
        _profile_cache[cache_key] = provisional
    return provisional


def parse_cutoff_date(value: str | date | datetime | None) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            return None
    return None
