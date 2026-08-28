"""Aggregazioni Pattern Lab — streaming accumulator, nessuna lista completa in RAM."""

from __future__ import annotations

from typing import Any, Iterable


def _empty_bucket() -> dict[str, Any]:
    return {
        "selections": 0,
        "wins": 0,
        "losses": 0,
        "void": 0,
        "profit_1u": 0.0,
        "quota_sum": 0.0,
        "quota_n": 0,
    }


def _bump(bucket: dict[str, Any], row: dict[str, Any]) -> None:
    bucket["selections"] += 1
    if row.get("target_won") is True:
        bucket["wins"] += 1
    elif row.get("target_lost") is True:
        bucket["losses"] += 1
    elif row.get("target_void") is True:
        bucket["void"] += 1
    profit = row.get("target_profit_1u")
    if profit is not None:
        bucket["profit_1u"] += float(profit)
    quota = row.get("pre_quota_bet365")
    if quota is not None:
        bucket["quota_sum"] += float(quota)
        bucket["quota_n"] += 1


def _finalize(bucket: dict[str, Any], *, key: str | None = None) -> dict[str, Any]:
    decided = int(bucket["wins"]) + int(bucket["losses"])
    win_rate = (float(bucket["wins"]) / decided) if decided else None
    avg_quota = (
        float(bucket["quota_sum"]) / float(bucket["quota_n"]) if bucket["quota_n"] else None
    )
    selections = int(bucket["selections"])
    profit = float(bucket["profit_1u"])
    roi = (profit / selections) if selections else None
    out = {
        "selections": selections,
        "wins": int(bucket["wins"]),
        "losses": int(bucket["losses"]),
        "void": int(bucket["void"]),
        "win_rate": win_rate,
        "avg_quota": avg_quota,
        "profit_1u": profit,
        "roi": roi,
    }
    if key is not None:
        out["key"] = key
    return out


class PatternLabAccumulator:
    """Accumula summary + breakdown mentre scorre le righe."""

    def __init__(self) -> None:
        self.summary = _empty_bucket()
        self.by_season: dict[str, dict[str, Any]] = {}
        self.by_competition: dict[str, dict[str, Any]] = {}
        self.by_market: dict[str, dict[str, Any]] = {}
        self.match_ids: set[tuple[int, int]] = set()

    def add(self, row: dict[str, Any]) -> None:
        _bump(self.summary, row)
        season = str(row.get("season") or "unknown")
        comp = str(row.get("competition") or "unknown")
        market = str(row.get("market_key") or "unknown")
        if season not in self.by_season:
            self.by_season[season] = _empty_bucket()
        if comp not in self.by_competition:
            self.by_competition[comp] = _empty_bucket()
        if market not in self.by_market:
            self.by_market[market] = _empty_bucket()
        _bump(self.by_season[season], row)
        _bump(self.by_competition[comp], row)
        _bump(self.by_market[market], row)
        run_id = row.get("run_id")
        lab_match_id = row.get("lab_match_id")
        if run_id is not None and lab_match_id is not None:
            self.match_ids.add((int(run_id), int(lab_match_id)))

    def result(self) -> dict[str, Any]:
        return {
            "summary": _finalize(self.summary),
            "breakdown": {
                "by_season": [
                    _finalize(b, key=k) for k, b in sorted(self.by_season.items())
                ],
                "by_competition": [
                    _finalize(b, key=k) for k, b in sorted(self.by_competition.items())
                ],
                "by_market": [
                    _finalize(b, key=k) for k, b in sorted(self.by_market.items())
                ],
            },
            "match_count": len(self.match_ids),
            "market_row_count": int(self.summary["selections"]),
        }


def accumulate_rows(rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    acc = PatternLabAccumulator()
    for row in rows:
        acc.add(row)
    return acc.result()
