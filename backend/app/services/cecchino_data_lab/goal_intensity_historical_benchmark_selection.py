"""Selezione pilot deterministica per benchmark storico GI."""

from __future__ import annotations

import hashlib
import json
import math
import random
from collections import defaultdict
from datetime import datetime
from typing import Any

from app.models.cecchino_lab_historical_match_snapshot import (
    CecchinoLabHistoricalMatchSnapshot,
)

SELECTION_PROTOCOL = "gi_historical_benchmark_pilot_proportional_temporal_v1"
DEFAULT_SEED = 42
DEFAULT_PILOT_SIZE = 300


def _sha256_canonical(payload: Any) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _kickoff_key(s: CecchinoLabHistoricalMatchSnapshot) -> tuple:
    ko = s.kickoff_at or datetime.min
    return (ko, int(s.chronological_order or 0), int(s.id))


def select_pilot_snapshots(
    snapshots: list[CecchinoLabHistoricalMatchSnapshot],
    *,
    pilot_size: int = DEFAULT_PILOT_SIZE,
    random_seed: int = DEFAULT_SEED,
) -> dict[str, Any]:
    """Selezione deterministica: proporzionale per competizione + copertura temporale.

    Non usa gol, esiti, errori, probabilità, score, profitto o mercati.
    """
    eligible = sorted(snapshots, key=_kickoff_key)
    n = len(eligible)
    requested = max(0, int(pilot_size))
    if n == 0 or requested == 0:
        return {
            "algorithm": SELECTION_PROTOCOL,
            "random_seed": int(random_seed),
            "requested": requested,
            "selected": 0,
            "selection_hash": _sha256_canonical([]),
            "snapshot_ids": [],
            "lab_match_ids": [],
            "competition_distribution": {},
            "month_distribution": {},
            "kickoff_range": {"min": None, "max": None},
            "selection_protocol": SELECTION_PROTOCOL,
        }

    target_n = min(requested, n)
    by_comp: dict[str, list[CecchinoLabHistoricalMatchSnapshot]] = defaultdict(list)
    for s in eligible:
        by_comp[str(s.competition_name or "unknown")].append(s)

    # At least one per competition when possible
    selected: list[CecchinoLabHistoricalMatchSnapshot] = []
    selected_ids: set[int] = set()
    rng = random.Random(int(random_seed))

    comps = sorted(by_comp.keys())
    for comp in comps:
        rows = by_comp[comp]
        if not rows:
            continue
        # temporal uniform pick within competition: middle of deterministic shuffle strata
        pick = rows[len(rows) // 2]
        if pick.id not in selected_ids:
            selected.append(pick)
            selected_ids.add(int(pick.id))

    remaining_slots = max(0, target_n - len(selected))
    # Proportional allocation of remaining slots
    remaining_pool = [s for s in eligible if int(s.id) not in selected_ids]
    if remaining_slots > 0 and remaining_pool:
        # Group remaining by competition
        rem_by_comp: dict[str, list[CecchinoLabHistoricalMatchSnapshot]] = defaultdict(list)
        for s in remaining_pool:
            rem_by_comp[str(s.competition_name or "unknown")].append(s)
        total_rem = len(remaining_pool)
        allocations: dict[str, int] = {}
        allocated = 0
        for comp in sorted(rem_by_comp.keys()):
            share = len(rem_by_comp[comp]) / total_rem
            k = int(math.floor(share * remaining_slots))
            allocations[comp] = k
            allocated += k
        # Distribute leftover by largest remainder
        remainders = sorted(
            (
                (
                    (len(rem_by_comp[c]) / total_rem) * remaining_slots - allocations[c],
                    c,
                )
                for c in rem_by_comp
            ),
            reverse=True,
        )
        leftover = remaining_slots - allocated
        for i in range(leftover):
            allocations[remainders[i % len(remainders)][1]] += 1

        for comp in sorted(allocations.keys()):
            k = allocations[comp]
            rows = rem_by_comp[comp]
            if k <= 0 or not rows:
                continue
            # Uniform temporal: pick evenly spaced indices, tie-break with seed
            if k >= len(rows):
                picks = list(rows)
            else:
                idxs = []
                for i in range(k):
                    pos = int(round((i + 0.5) * (len(rows) / k) - 0.5))
                    pos = max(0, min(len(rows) - 1, pos))
                    idxs.append(pos)
                # resolve collisions with seeded walk
                used: set[int] = set()
                picks = []
                for pos in idxs:
                    p = pos
                    while p in used and p + 1 < len(rows):
                        p += 1
                    while p in used and p - 1 >= 0:
                        p -= 1
                    if p in used:
                        # fallback random among unused
                        unused = [i for i in range(len(rows)) if i not in used]
                        p = rng.choice(unused) if unused else pos
                    used.add(p)
                    picks.append(rows[p])
            for pick in picks:
                if int(pick.id) not in selected_ids and len(selected) < target_n:
                    selected.append(pick)
                    selected_ids.add(int(pick.id))

    # If still short (edge cases), fill temporally evenly from leftover
    if len(selected) < target_n:
        leftover = [s for s in eligible if int(s.id) not in selected_ids]
        need = target_n - len(selected)
        if leftover:
            step = max(1, len(leftover) // need)
            for i in range(0, len(leftover), step):
                if len(selected) >= target_n:
                    break
                s = leftover[i]
                if int(s.id) not in selected_ids:
                    selected.append(s)
                    selected_ids.add(int(s.id))

    selected = sorted(selected, key=_kickoff_key)[:target_n]
    snapshot_ids = [int(s.id) for s in selected]
    lab_match_ids = [int(s.lab_match_id) for s in selected if s.lab_match_id is not None]

    comp_dist: dict[str, int] = defaultdict(int)
    month_dist: dict[str, int] = defaultdict(int)
    kickoffs: list[datetime] = []
    for s in selected:
        comp_dist[str(s.competition_name or "unknown")] += 1
        if s.kickoff_at is not None:
            kickoffs.append(s.kickoff_at)
            month_dist[s.kickoff_at.strftime("%Y-%m")] += 1

    return {
        "algorithm": SELECTION_PROTOCOL,
        "selection_protocol": SELECTION_PROTOCOL,
        "random_seed": int(random_seed),
        "requested": requested,
        "selected": len(snapshot_ids),
        "selection_hash": _sha256_canonical(
            {
                "protocol": SELECTION_PROTOCOL,
                "seed": int(random_seed),
                "requested": requested,
                "snapshot_ids": snapshot_ids,
            }
        ),
        "snapshot_ids": snapshot_ids,
        "lab_match_ids": lab_match_ids,
        "competition_distribution": dict(sorted(comp_dist.items())),
        "month_distribution": dict(sorted(month_dist.items())),
        "kickoff_range": {
            "min": min(kickoffs).isoformat() if kickoffs else None,
            "max": max(kickoffs).isoformat() if kickoffs else None,
        },
    }
