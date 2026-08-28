"""Aggregazioni Pattern Lab — streaming accumulator, nessuna lista completa in RAM."""

from __future__ import annotations

from collections import defaultdict
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
        "rating_sum": 0.0,
        "rating_n": 0,
        "purch_v36_sum": 0.0,
        "purch_v36_n": 0,
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
    rating = row.get("pre_rating")
    if rating is not None:
        bucket["rating_sum"] += float(rating)
        bucket["rating_n"] += 1
    purch = row.get("pre_purch_v36_score")
    if purch is not None:
        bucket["purch_v36_sum"] += float(purch)
        bucket["purch_v36_n"] += 1


def _finalize(bucket: dict[str, Any], *, key: str | None = None) -> dict[str, Any]:
    decided = int(bucket["wins"]) + int(bucket["losses"])
    win_rate = (float(bucket["wins"]) / decided) if decided else None
    avg_quota = (
        float(bucket["quota_sum"]) / float(bucket["quota_n"]) if bucket["quota_n"] else None
    )
    avg_rating = (
        float(bucket["rating_sum"]) / float(bucket["rating_n"]) if bucket["rating_n"] else None
    )
    avg_purch = (
        float(bucket["purch_v36_sum"]) / float(bucket["purch_v36_n"])
        if bucket["purch_v36_n"]
        else None
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
        "avg_rating": avg_rating,
        "avg_purchasability_v36": avg_purch,
        "profit_1u": profit,
        "roi": roi,
    }
    if key is not None:
        out["key"] = key
    return out


def _rating_band(rating: Any) -> str:
    if rating is None:
        return "unavailable"
    try:
        r = int(rating)
    except (TypeError, ValueError):
        return "unavailable"
    if r < 50:
        return "lt_50"
    if r <= 59:
        return "50-59"
    if r <= 69:
        return "60-69"
    if r <= 79:
        return "70-79"
    if r <= 89:
        return "80-89"
    if r <= 99:
        return "90-99"
    return "100"


def _purch_band(score: Any) -> str:
    if score is None:
        return "unavailable"
    try:
        s = float(score)
    except (TypeError, ValueError):
        return "unavailable"
    if s < 0:
        return "unavailable"
    bucket = int(s // 10) * 10
    if bucket >= 100:
        return "100"
    return f"{bucket}-{bucket + 9}"


def _hist_list(counter: dict[str, int]) -> list[dict[str, Any]]:
    return [{"key": k, "count": int(v)} for k, v in sorted(counter.items(), key=lambda x: x[0])]


class PatternLabAccumulator:
    """Accumula summary + breakdown + module insights mentre scorre le righe."""

    def __init__(self) -> None:
        self.summary = _empty_bucket()
        self.by_season: dict[str, dict[str, Any]] = {}
        self.by_competition: dict[str, dict[str, Any]] = {}
        self.by_market: dict[str, dict[str, Any]] = {}
        self.match_ids: set[tuple[int, int]] = set()

        self._edge_sum = 0.0
        self._edge_n = 0
        self._value_true = 0
        self._value_false = 0
        self._signal_active = 0
        self._signal_count_hist: dict[str, int] = defaultdict(int)
        self._signal_excel = {"D": 0, "E": 0, "F": 0, "G": 0}
        self._rating_band_hist: dict[str, int] = defaultdict(int)
        self._balance_class_hist: dict[str, int] = defaultdict(int)
        self._geometry_sum = 0.0
        self._geometry_n = 0
        self._goal_class_hist: dict[str, int] = defaultdict(int)
        self._goal_direction_hist: dict[str, int] = defaultdict(int)
        self._goal_composite_sum = 0.0
        self._goal_composite_n = 0
        self._v36_class_hist: dict[str, int] = defaultdict(int)
        self._v36_band_hist: dict[str, int] = defaultdict(int)

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

        band = _rating_band(row.get("pre_rating"))
        self._rating_band_hist[band] += 1

        edge = row.get("pre_edge_pct")
        if edge is not None:
            self._edge_sum += float(edge)
            self._edge_n += 1
        if row.get("pre_value_positive") is True:
            self._value_true += 1
        elif row.get("pre_value_positive") is False:
            self._value_false += 1

        if row.get("pre_signal_active") is True:
            self._signal_active += 1
        sig_n = int(row.get("pre_signal_count") or 0)
        self._signal_count_hist[str(sig_n)] += 1
        for col in ("d", "e", "f", "g"):
            if row.get(f"pre_signal_excel_{col}") is True:
                self._signal_excel[col.upper()] += 1

        bal_class = row.get("pre_balance_structural_class")
        if bal_class:
            self._balance_class_hist[str(bal_class)] += 1
        geom = row.get("pre_balance_geometry")
        if geom is not None:
            self._geometry_sum += float(geom)
            self._geometry_n += 1

        gclass = row.get("pre_goal_v4_compat_final_class")
        if gclass:
            self._goal_class_hist[str(gclass)] += 1
        gdir = row.get("pre_goal_v4_compat_direction")
        if gdir:
            self._goal_direction_hist[str(gdir)] += 1
        gcomp = row.get("pre_goal_v4_compat_composite")
        if gcomp is not None:
            self._goal_composite_sum += float(gcomp)
            self._goal_composite_n += 1

        v36_class = row.get("pre_purch_v36_class")
        if v36_class:
            self._v36_class_hist[str(v36_class)] += 1
        self._v36_band_hist[_purch_band(row.get("pre_purch_v36_score"))] += 1

    def result(self) -> dict[str, Any]:
        n = int(self.summary["selections"])
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
            "module_insights": {
                "kpi": {
                    "rating_bands": _hist_list(self._rating_band_hist),
                    "value_positive_count": self._value_true,
                    "value_negative_count": self._value_false,
                    "avg_edge_pct": (self._edge_sum / self._edge_n) if self._edge_n else None,
                    "edge_sample_n": self._edge_n,
                },
                "signals": {
                    "active_count": self._signal_active,
                    "active_rate": (self._signal_active / n) if n else None,
                    "count_distribution": _hist_list(self._signal_count_hist),
                    "excel_column_frequency": dict(self._signal_excel),
                },
                "balance": {
                    "structural_class_distribution": _hist_list(self._balance_class_hist),
                    "avg_geometry": (
                        self._geometry_sum / self._geometry_n if self._geometry_n else None
                    ),
                    "geometry_sample_n": self._geometry_n,
                },
                "goal_v4_compat": {
                    "final_class_distribution": _hist_list(self._goal_class_hist),
                    "direction_distribution": _hist_list(self._goal_direction_hist),
                    "avg_composite": (
                        self._goal_composite_sum / self._goal_composite_n
                        if self._goal_composite_n
                        else None
                    ),
                    "composite_sample_n": self._goal_composite_n,
                },
                "purchasability_v36": {
                    "class_distribution": _hist_list(self._v36_class_hist),
                    "score_bands": _hist_list(self._v36_band_hist),
                },
            },
            "match_count": len(self.match_ids),
            "market_row_count": n,
        }


def accumulate_rows(rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    acc = PatternLabAccumulator()
    for row in rows:
        acc.add(row)
    return acc.result()
