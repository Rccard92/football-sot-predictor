"""Generatore insight pattern aggregati per persistenza run."""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

from app.services.backtest.v31_pattern_analysis_aggregators import (
    high_and_outlier_summary,
    losing_patterns,
    win_quality_summary,
)
from app.services.backtest.v31_pattern_analysis_recommendations import TOP3_KEYS


def _insight(
    *,
    insight_type: str,
    severity: str,
    title: str,
    description: str,
    evidence: dict[str, Any],
    recommended_action: str | None = None,
    strategy_key: str | None = None,
) -> dict[str, Any]:
    return {
        "insight_type": insight_type,
        "severity": severity,
        "title": title,
        "description": description,
        "evidence_json": evidence,
        "recommended_action": recommended_action,
        "strategy_key": strategy_key,
    }


def _team_bias_rows(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Squadre più sottostimate/sovrastimate (errore signed)."""
    team_err: dict[str, list[float]] = defaultdict(list)
    for r in rows:
        if r.get("prediction_status") != "ok":
            continue
        err = r.get("error")
        if err is None:
            continue
        match = str(r.get("match") or "")
        parts = match.split(" vs ")
        for team in parts:
            team_err[team.strip()].append(float(err))
    under: list[dict[str, Any]] = []
    over: list[dict[str, Any]] = []
    for team, errs in team_err.items():
        if len(errs) < 2:
            continue
        avg = sum(errs) / len(errs)
        entry = {"team": team, "avg_error": round(avg, 3), "fixtures": len(errs)}
        if avg < -1.0:
            under.append(entry)
        elif avg > 1.0:
            over.append(entry)
    under.sort(key=lambda x: x["avg_error"])
    over.sort(key=lambda x: -x["avg_error"])
    return under[:5], over[:5]


def generate_pattern_insights(
    *,
    enriched_by_strategy: dict[str, list[dict[str, Any]]],
    top3_cluster_summary: dict[str, Any],
    distribution: dict[str, Any],
    pattern_verdict: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Genera insight tipizzati da aggregati pattern."""
    insights: list[dict[str, Any]] = []
    verdict = pattern_verdict or {}
    main_warning = verdict.get("main_warning") or verdict.get("headline") or verdict.get("main_issue")
    if main_warning:
        insights.append(
            _insight(
                insight_type="main_warning",
                severity="warning",
                title="Warning principale",
                description=str(main_warning),
                evidence={"pattern_verdict": verdict},
                recommended_action=verdict.get("recommended_next_step"),
            ),
        )

    for key in TOP3_KEYS:
        rows = enriched_by_strategy.get(key) or []
        if not rows:
            continue
        wq = win_quality_summary(rows)
        lp = losing_patterns(rows)
        ha = high_and_outlier_summary(
            rows,
            p75=distribution.get("p75"),
            p90=distribution.get("p90"),
            p95=distribution.get("p95"),
        )

        high_missed = int(ha.get("missed_high") or 0)
        if high_missed > 0:
            insights.append(
                _insight(
                    insight_type="high_actual_not_predicted_high",
                    severity="warning" if high_missed >= 5 else "info",
                    title=f"High non previste ({key})",
                    description=f"{high_missed} partite con actual alto non catturate dalla predizione high.",
                    evidence={"count": high_missed, "summary": ha},
                    recommended_action="Rafforzare segnali high-total o boost dinamico.",
                    strategy_key=key,
                ),
            )

        false_high = int((lp.get("special_categories") or {}).get("false_high_prediction", {}).get("count") or 0)
        if false_high > 0:
            insights.append(
                _insight(
                    insight_type="false_high_prediction",
                    severity="warning" if false_high >= 5 else "info",
                    title=f"False high ({key})",
                    description=f"{false_high} falsi positivi high prediction.",
                    evidence={"count": false_high},
                    recommended_action="Stringere guardrail e cap predizione high.",
                    strategy_key=key,
                ),
            )

        understated = int((wq.get("counts") or {}).get("UNDERSTATED_WIN") or 0)
        if understated > 0:
            insights.append(
                _insight(
                    insight_type="understated_win",
                    severity="info",
                    title=f"Vittorie sottostimate ({key})",
                    description=f"{understated} vittorie coverage con sottostima marcata.",
                    evidence={"count": understated, "win_quality_summary": wq},
                    strategy_key=key,
                ),
            )

        under_teams, over_teams = _team_bias_rows(rows)
        if under_teams:
            insights.append(
                _insight(
                    insight_type="teams_underpredicted",
                    severity="info",
                    title=f"Squadre sottostimate ({key})",
                    description="Top squadre con errore medio negativo (modello troppo basso).",
                    evidence={"teams": under_teams},
                    strategy_key=key,
                ),
            )
        if over_teams:
            insights.append(
                _insight(
                    insight_type="teams_overpredicted",
                    severity="info",
                    title=f"Squadre sovrastimate ({key})",
                    description="Top squadre con errore medio positivo.",
                    evidence={"teams": over_teams},
                    strategy_key=key,
                ),
            )

    # Boost helped/hurt: hybrid vs bias per fixture
    hybrid_rows = enriched_by_strategy.get("v31_bias_dynamic_high_guard") or []
    bias_rows = enriched_by_strategy.get("v31_bias_corrected") or []
    if hybrid_rows and bias_rows:
        bias_by_fid = {int(r.get("fixture_id") or 0): r for r in bias_rows}
        helped = hurt = 0
        for hr in hybrid_rows:
            fid = int(hr.get("fixture_id") or 0)
            br = bias_by_fid.get(fid)
            if not br:
                continue
            h_ae = float(hr.get("abs_error") or 999)
            b_ae = float(br.get("abs_error") or 999)
            if h_ae < b_ae - 0.05:
                helped += 1
            elif h_ae > b_ae + 0.05:
                hurt += 1
        if helped or hurt:
            insights.append(
                _insight(
                    insight_type="boost_hybrid_vs_bias",
                    severity="info",
                    title="Boost hybrid vs bias corrected",
                    description=f"Hybrid migliora {helped} fixture e peggiora {hurt} rispetto a bias corrected.",
                    evidence={"helped": helped, "hurt": hurt},
                    recommended_action="Calibrare tier boost se hurt > helped.",
                    strategy_key="v31_bias_dynamic_high_guard",
                ),
            )

    counts = top3_cluster_summary.get("counts") or {}
    if counts:
        insights.append(
            _insight(
                insight_type="top3_cluster_summary",
                severity="info",
                title="Cluster top3 strategie",
                description="Conteggi confronto bias / hybrid / chaos su fixture comuni.",
                evidence={"counts": counts, "top3_cluster_summary": top3_cluster_summary},
            ),
        )

    return insights


def main_warning_from_insights(insights: list[dict[str, Any]]) -> str | None:
    for ins in insights:
        if ins.get("insight_type") == "main_warning":
            return ins.get("description")
    for ins in insights:
        if ins.get("severity") == "warning":
            return ins.get("title")
    return None


def best_mae_strategy_from_simulator(simulator_payload: dict[str, Any]) -> str | None:
    best = simulator_payload.get("best_by") or {}
    mae_block = best.get("best_mae") or {}
    return mae_block.get("strategy_key")
