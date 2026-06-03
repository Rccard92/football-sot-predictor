"""Confidence tier per simulatore v3.1."""

from __future__ import annotations

from typing import Any

from app.services.backtest.v31_calibration_simulator_feature_engine import FixtureSignals


def _lineup_ok(signals: FixtureSignals) -> bool:
    dq = signals.data_quality
    st = str(dq.get("lineup_status") or "")
    if st in ("ok", "available", "partial_low_sample"):
        return True
    lu = signals.lineups.get("home") if isinstance(signals.lineups, dict) else {}
    if isinstance(lu, dict) and lu.get("lineup_available"):
        return True
    return False


def _player_layer_coverage(signals: FixtureSignals) -> float:
    pl = signals.player_layer if isinstance(signals.player_layer, dict) else {}
    home = pl.get("home") if isinstance(pl.get("home"), dict) else {}
    away = pl.get("away") if isinstance(pl.get("away"), dict) else {}
    scores = []
    for side in (home, away):
        idx = side.get("player_layer_index_existing")
        if idx is not None:
            scores.append(1.0 if float(idx) >= 0.85 else 0.5)
        elif side.get("starting_xi_available"):
            scores.append(0.9)
    if not scores:
        return 0.5
    return sum(scores) / len(scores)


def _avg_sample_count(signals: FixtureSignals) -> int | None:
    counts = []
    for side in (signals.home.team_raw, signals.away.team_raw):
        sc = side.get("sample_count")
        if sc is not None:
            try:
                counts.append(int(sc))
            except (TypeError, ValueError):
                pass
    if not counts:
        return None
    return int(sum(counts) / len(counts))


def compute_confidence_tier(
    signals: FixtureSignals,
    *,
    predicted_total: float | None,
    selected_line: float | None,
) -> str:
    dq = signals.data_quality
    fallback = int(dq.get("fallback_count") or 0)
    warnings = int(dq.get("warning_count") or signals.warning_count)
    ts = str(dq.get("team_stats_status") or signals.team_stats_status)
    margin = (
        float(predicted_total) - float(selected_line)
        if predicted_total is not None and selected_line is not None
        else 0.0
    )
    pl_cov = _player_layer_coverage(signals)
    sample = _avg_sample_count(signals)
    lineup_ok = _lineup_ok(signals)
    unav = str(dq.get("unavailable_status") or "ok")

    if (
        ts == "ok"
        and fallback == 0
        and warnings <= 1
        and lineup_ok
        and pl_cov >= 0.90
        and (sample is None or sample >= 10)
        and margin >= 1.0
    ):
        return "high"

    if (
        ts in ("ok", "partial")
        and fallback <= 1
        and warnings <= 3
        and pl_cov >= 0.70
        and margin >= 0.6
        and unav not in ("missing", "failed")
    ):
        return "medium"

    return "low"
