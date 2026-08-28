"""Benchmark sintetico V3 vs V4 — rolling state / prior cache (no full run DB)."""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app.services.cecchino_data_lab.historical_context_builder import (
    build_lab_prematch_contexts,
    lab_match_to_proxy,
    sort_proxies,
)
from app.services.cecchino_data_lab.historical_rolling_state import (
    CompetitionRollingState,
    RunPriorModuleCache,
)


def _synthetic_matches(n: int, n_comp: int = 5) -> list[tuple[str, SimpleNamespace]]:
    base = datetime(2021, 8, 1, 15, 0, tzinfo=timezone.utc)
    out: list[tuple[str, SimpleNamespace]] = []
    for i in range(n):
        comp = f"Comp{i % n_comp}"
        ko = base + timedelta(hours=i * 6)
        m = SimpleNamespace(
            id=i + 1,
            home_team=f"H{i}",
            away_team=f"A{i}",
            kickoff_at=ko,
            match_date=ko.date(),
            match_time=ko.time(),
            source_row_number=i,
            ft_home_goals=1,
            ft_away_goals=0,
            ht_home_goals=0,
            ht_away_goals=0,
        )
        out.append((comp, lab_match_to_proxy(m, competition_id=abs(hash(comp)) % 10**9)))
    return out


def benchmark_v3_context_build(n_matches: int = 400) -> dict[str, float]:
    """Simula O(n²) build_lab_prematch_contexts per competizione."""
    items = _synthetic_matches(n_matches)
    by_comp: dict[str, list] = {}
    for comp, proxy in items:
        by_comp.setdefault(comp, []).append(proxy)
    for comp in by_comp:
        by_comp[comp] = sort_proxies(by_comp[comp])

    t0 = time.perf_counter()
    for comp, proxies in by_comp.items():
        for target in proxies:
            build_lab_prematch_contexts(competition_ordered=proxies, target=target)
    elapsed = time.perf_counter() - t0
    return {"matches": n_matches, "elapsed_seconds": elapsed, "strategy": "v3_naive_per_comp"}


def benchmark_v4_rolling_context(n_matches: int = 400) -> dict[str, float]:
    """Simula rolling state + commit per gruppo kickoff."""
    items = _synthetic_matches(n_matches)
    items.sort(key=lambda x: (x[1].kickoff_at, x[1].id))
    by_comp: dict[str, list] = {}
    for comp, proxy in items:
        by_comp.setdefault(comp, []).append(proxy)
    states = {
        c: CompetitionRollingState(competition_name=c, all_proxies=sort_proxies(ps))
        for c, ps in by_comp.items()
    }

    t0 = time.perf_counter()
    i = 0
    while i < len(items):
        ko = items[i][1].kickoff_at
        group: list[tuple[str, SimpleNamespace]] = []
        while i < len(items) and items[i][1].kickoff_at == ko:
            group.append(items[i])
            i += 1
        for comp, proxy in group:
            states[comp].contexts_for(proxy)
        for comp, proxy in group:
            states[comp].commit_group([proxy])
    elapsed = time.perf_counter() - t0
    return {"matches": n_matches, "elapsed_seconds": elapsed, "strategy": "v4_rolling_global"}


def benchmark_prior_cache_vs_naive(n_eligible: int = 400) -> dict[str, float]:
    """Confronto filtro prior rows: lista vs cache già filtrata."""
    base = datetime(2021, 8, 1, tzinfo=timezone.utc)
    rows = []
    for i in range(n_eligible):
        rows.append(
            {
                "kickoff_at": base + timedelta(days=i),
                "lab_match_id": i,
                "gi_feature_row": {"features": {"home_goals_scored_avg": 1.0 + i * 0.01}},
            }
        )
    target_ko = base + timedelta(days=n_eligible // 2)

    t0 = time.perf_counter()
    for _ in range(n_eligible):
        out = []
        for r in rows:
            if r["kickoff_at"] < target_ko:
                out.append(r["gi_feature_row"])
    naive_elapsed = time.perf_counter() - t0

    cache = RunPriorModuleCache()
    for r in rows:
        cache.append_eligible(
            kickoff_at=r["kickoff_at"],
            lab_match_id=r["lab_match_id"],
            gi_feature_row=r["gi_feature_row"],
            kpi_panel={},
        )

    t1 = time.perf_counter()
    for _ in range(n_eligible):
        cache.gi_rows_before(target_ko)
    cache_elapsed = time.perf_counter() - t1

    return {
        "eligible_rows": n_eligible,
        "naive_filter_seconds": naive_elapsed,
        "cache_lookup_seconds": cache_elapsed,
        "speedup_x": round(naive_elapsed / cache_elapsed, 2) if cache_elapsed > 0 else None,
    }


def benchmark_db_prior_load_simulation(n_eligible: int = 400) -> dict[str, float]:
    """Simula V3: reload+filter all eligible rows per match vs V4 cache lookup."""
    base = datetime(2021, 8, 1, tzinfo=timezone.utc)
    rows = [
        {
            "kickoff_at": base + timedelta(days=i),
            "lab_match_id": i,
            "gi_feature_row": {"features": {"home_goals_scored_avg": 1.0}},
            "kpi_panel": {"rows": [{"market_key": "HOME"}]},
        }
        for i in range(n_eligible)
    ]

    t0 = time.perf_counter()
    for target_i in range(n_eligible):
        target_ko = base + timedelta(days=target_i)
        for r in rows:
            if r["kickoff_at"] < target_ko:
                _ = r["gi_feature_row"]
                _ = r["kpi_panel"]
    v3_sim = time.perf_counter() - t0

    cache = RunPriorModuleCache()
    for r in rows:
        cache.append_eligible(
            kickoff_at=r["kickoff_at"],
            lab_match_id=r["lab_match_id"],
            gi_feature_row=r["gi_feature_row"],
            kpi_panel=r["kpi_panel"],
        )

    t1 = time.perf_counter()
    for target_i in range(n_eligible):
        target_ko = base + timedelta(days=target_i)
        cache.gi_rows_before(target_ko)
    v4_sim = time.perf_counter() - t1

    return {
        "eligible_rows": n_eligible,
        "v3_simulated_prior_scan_seconds": v3_sim,
        "v4_cache_prior_seconds": v4_sim,
        "speedup_x": round(v3_sim / v4_sim, 2) if v4_sim > 0 else None,
    }


def run_pilot_benchmark(n: int = 400) -> dict[str, object]:
    v3 = benchmark_v3_context_build(n)
    v4 = benchmark_v4_rolling_context(n)
    prior = benchmark_prior_cache_vs_naive(min(n, 200))
    db_prior = benchmark_db_prior_load_simulation(min(n, 400))
    speedup_ctx = v3["elapsed_seconds"] / v4["elapsed_seconds"] if v4["elapsed_seconds"] > 0 else 0
    return {
        "pilot_matches": n,
        "v3_naive_context_build": v3,
        "v4_rolling_context_build": v4,
        "context_build_speedup_x": round(speedup_ctx, 2),
        "prior_cache": prior,
        "db_prior_load_simulation": db_prior,
        "note": (
            "Benchmark sintetico in-process. Il guadagno dominante atteso in produzione "
            "viene da eliminazione _load_prior_module_rows O(n²) DB, doppio calcolo segnali "
            "e SELECT post-match — non solo context build CPU."
        ),
    }


if __name__ == "__main__":
    import json

    print(json.dumps(run_pilot_benchmark(400), indent=2))
