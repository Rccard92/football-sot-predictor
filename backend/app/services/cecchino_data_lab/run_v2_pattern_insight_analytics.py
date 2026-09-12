"""Aggregati analitici per la dashboard Pattern Insights.

Tutto calcolato in SQL sull'ultimo run completato: la tabella candidati
puo' superare le 25mila righe, quindi nessun aggregato viene fatto in
Python caricando l'intera lista.

Ogni funzione risponde a una domanda precisa della dashboard:
- dove si concentra il valore (per mercato)
- quali condizioni pre-partita pesano di piu' (frequenza dei fattori)
- se i pattern complessi rendono davvero piu' di quelli semplici
- come si distribuisce la qualita' (campione vs ROI) per distinguere
  segnale e rumore a colpo d'occhio
- quali situazioni (tiri/corner/cartellini) sono piu' prevedibili
- quanto e' solida la base dati Run V2 sottostante
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models.cecchino_run_v2 import CecchinoRunV2Run
from app.services.cecchino_data_lab.run_v2_grid_labels import COLUMN_LABELS


def _rows(db: Session, sql: str, **params: Any) -> list[dict[str, Any]]:
    result = db.execute(text(sql), params)
    return [dict(r._mapping) for r in result]


def _f(v: Any) -> float | None:
    return float(v) if v is not None else None


def by_market(db: Session, *, insight_run_id: int, min_n: int) -> list[dict[str, Any]]:
    rows = _rows(
        db,
        """
        SELECT target_key,
               target_label,
               count(*)                                          AS pattern_count,
               max(roi_pct)                                      AS best_roi_pct,
               percentile_cont(0.5) WITHIN GROUP (ORDER BY roi_pct) AS median_roi_pct,
               avg(n)                                            AS avg_n,
               max(n)                                            AS max_n,
               avg(avg_quota)                                    AS avg_quota
        FROM cecchino_run_v2_pattern_insight_candidates
        WHERE insight_run_id = :rid AND target_type = 'market' AND n >= :min_n
        GROUP BY target_key, target_label
        ORDER BY best_roi_pct DESC NULLS LAST
        """,
        rid=insight_run_id,
        min_n=min_n,
    )
    return [
        {
            "target_key": r["target_key"],
            "target_label": r["target_label"],
            "pattern_count": int(r["pattern_count"]),
            "best_roi_pct": _f(r["best_roi_pct"]),
            "median_roi_pct": _f(r["median_roi_pct"]),
            "avg_n": _f(r["avg_n"]),
            "max_n": int(r["max_n"]) if r["max_n"] is not None else None,
            "avg_quota": _f(r["avg_quota"]),
        }
        for r in rows
    ]


def factor_frequency(db: Session, *, insight_run_id: int, min_n: int) -> list[dict[str, Any]]:
    """Quante volte ciascuna condizione pre-partita compare nei pattern
    trovati: e' la misura piu' diretta di 'quali fattori contano'."""
    rows = _rows(
        db,
        """
        SELECT f->>'column'  AS column_key,
               count(*)      AS uses,
               avg(c.roi_pct) AS avg_roi_pct
        FROM cecchino_run_v2_pattern_insight_candidates c,
             jsonb_array_elements(c.filters_json) f
        WHERE c.insight_run_id = :rid AND c.n >= :min_n
        GROUP BY f->>'column'
        ORDER BY uses DESC
        """,
        rid=insight_run_id,
        min_n=min_n,
    )
    return [
        {
            "column_key": r["column_key"],
            "label": COLUMN_LABELS.get(r["column_key"], r["column_key"]),
            "uses": int(r["uses"]),
            "avg_roi_pct": _f(r["avg_roi_pct"]),
        }
        for r in rows
    ]


def by_complexity(db: Session, *, insight_run_id: int, min_n: int) -> list[dict[str, Any]]:
    """Pattern a 1, 2 o 3 condizioni: i piu' complessi rendono davvero di
    piu', o stanno solo sovra-adattandosi a campioni piccoli?"""
    rows = _rows(
        db,
        """
        SELECT jsonb_array_length(filters_json) AS atoms,
               count(*)                          AS pattern_count,
               avg(roi_pct)                      AS avg_roi_pct,
               avg(n)                            AS avg_n,
               avg(abs(deviation_pct))           AS avg_abs_deviation_pct
        FROM cecchino_run_v2_pattern_insight_candidates
        WHERE insight_run_id = :rid AND n >= :min_n
        GROUP BY 1
        ORDER BY 1
        """,
        rid=insight_run_id,
        min_n=min_n,
    )
    return [
        {
            "atoms": int(r["atoms"]),
            "pattern_count": int(r["pattern_count"]),
            "avg_roi_pct": _f(r["avg_roi_pct"]),
            "avg_n": _f(r["avg_n"]),
            "avg_abs_deviation_pct": _f(r["avg_abs_deviation_pct"]),
        }
        for r in rows
    ]


def quality_scatter(db: Session, *, insight_run_id: int, min_n: int) -> list[dict[str, Any]]:
    """Campione (N) vs ROI, campionamento deterministico: serve a vedere a
    colpo d'occhio che i ROI piu' alti stanno quasi tutti sui campioni piu'
    piccoli — cioe' dove il rumore statistico e' massimo."""
    rows = _rows(
        db,
        """
        SELECT n, roi_pct, avg_quota, target_label
        FROM cecchino_run_v2_pattern_insight_candidates
        WHERE insight_run_id = :rid AND target_type = 'market'
          AND n >= :min_n AND roi_pct IS NOT NULL AND (id % 13) = 0
        ORDER BY id
        LIMIT 900
        """,
        rid=insight_run_id,
        min_n=min_n,
    )
    return [
        {
            "n": int(r["n"]),
            "roi_pct": _f(r["roi_pct"]),
            "avg_quota": _f(r["avg_quota"]),
            "target_label": r["target_label"],
        }
        for r in rows
    ]


def synthetic_directions(db: Session, *, insight_run_id: int, min_n: int) -> list[dict[str, Any]]:
    """Per ogni situazione senza quota: quanto il profilo di partita puo'
    spingere la probabilita' verso l'alto e quanto verso il basso."""
    rows = _rows(
        db,
        """
        SELECT target_label,
               target_key,
               threshold,
               count(*)                                              AS pattern_count,
               max(deviation_pct) FILTER (WHERE deviation_pct > 0)   AS best_up_pct,
               min(deviation_pct) FILTER (WHERE deviation_pct < 0)   AS best_down_pct,
               max(baseline_win_rate_pct)                            AS baseline_pct
        FROM cecchino_run_v2_pattern_insight_candidates
        WHERE insight_run_id = :rid AND target_type = 'synthetic' AND n >= :min_n
        GROUP BY target_label, target_key, threshold
        ORDER BY greatest(
            coalesce(max(deviation_pct) FILTER (WHERE deviation_pct > 0), 0),
            coalesce(-min(deviation_pct) FILTER (WHERE deviation_pct < 0), 0)
        ) DESC
        """,
        rid=insight_run_id,
        min_n=min_n,
    )
    return [
        {
            "target_key": r["target_key"],
            "target_label": r["target_label"],
            "threshold": _f(r["threshold"]),
            "pattern_count": int(r["pattern_count"]),
            "best_up_pct": _f(r["best_up_pct"]),
            "best_down_pct": _f(r["best_down_pct"]),
            "baseline_pct": _f(r["baseline_pct"]),
        }
        for r in rows
    ]


def sample_buckets(db: Session, *, insight_run_id: int, min_n: int) -> list[dict[str, Any]]:
    """Distribuzione dei pattern per fascia di campione: quanta parte del
    totale sta sulle fasce fragili."""
    rows = _rows(
        db,
        """
        SELECT CASE
                 WHEN n < 50   THEN '20-49'
                 WHEN n < 100  THEN '50-99'
                 WHEN n < 200  THEN '100-199'
                 WHEN n < 500  THEN '200-499'
                 ELSE '500+'
               END AS bucket,
               count(*)     AS pattern_count,
               avg(roi_pct) AS avg_roi_pct
        FROM cecchino_run_v2_pattern_insight_candidates
        WHERE insight_run_id = :rid AND n >= :min_n
        GROUP BY 1
        """,
        rid=insight_run_id,
        min_n=min_n,
    )
    order = {"20-49": 0, "50-99": 1, "100-199": 2, "200-499": 3, "500+": 4}
    out = [
        {
            "bucket": r["bucket"],
            "pattern_count": int(r["pattern_count"]),
            "avg_roi_pct": _f(r["avg_roi_pct"]),
        }
        for r in rows
    ]
    out.sort(key=lambda x: order.get(x["bucket"], 99))
    return out


def source_coverage(db: Session, *, run_v2_run_id: int) -> dict[str, Any]:
    """Qualita' della base dati Run V2 sotto l'analisi: copertura quote per
    mercato, campionatura per campionato, audit anti-leakage."""
    run = db.get(CecchinoRunV2Run, run_v2_run_id)
    if not run or not run.summary_json:
        return {}
    s = run.summary_json
    leakage = s.get("leakage_audit") or {}
    progress = s.get("progress") or {}
    extra = s.get("extra_stats_coverage") or {}
    return {
        "season_label": s.get("season_label"),
        "matches": s.get("matches"),
        "date_range": s.get("date_range"),
        "elapsed_seconds": progress.get("elapsed_seconds"),
        "avg_ms_per_match": progress.get("avg_ms_per_match"),
        "market_rows_written": progress.get("market_rows_written"),
        "leakage_ok": leakage.get("leakage_ok"),
        "leakage_violations": leakage.get("leakage_violations"),
        "matches_audited": leakage.get("matches_audited"),
        "referee_coverage_pct": extra.get("referee_coverage_pct"),
        "quote_policy_version": s.get("quote_policy_version"),
        "competitions": [
            {
                "competition": c.get("competition"),
                "matches": c.get("matches"),
                "eligible_core": c.get("eligible_core"),
            }
            for c in (s.get("competitions") or [])
        ],
        "market_coverage": [
            {
                "market_key": m.get("market_key"),
                "rows": m.get("rows"),
                "rows_with_quote": m.get("rows_with_quote"),
                "quote_coverage_pct": m.get("quote_coverage_pct"),
            }
            for m in (s.get("market_coverage") or [])
        ],
    }
