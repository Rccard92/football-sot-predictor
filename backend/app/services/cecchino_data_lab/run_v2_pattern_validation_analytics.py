"""Aggregati della verifica fuori campione, tutti in SQL.

Ogni tasso di riconferma e' accompagnato dal tasso atteso per puro caso
(media delle probabilita' nulle dei pattern testati): e' il confronto tra i
due, non la percentuale da sola, a dire se c'e' segnale.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.models.cecchino_run_v2_pattern_insight import (
    STATUS_COMPLETED,
    CecchinoRunV2PatternValidationRun,
)


def _rows(db: Session, sql: str, **params: Any) -> list[dict[str, Any]]:
    return [dict(r._mapping) for r in db.execute(text(sql), params)]


def _f(v: Any) -> float | None:
    return float(v) if v is not None else None


_RATE_COLUMNS = """
    count(*)                                                        AS total,
    count(*) FILTER (WHERE v.verdict <> 'insufficient_sample')      AS tested,
    count(*) FILTER (WHERE v.verdict = 'confirmed')                 AS confirmed,
    count(*) FILTER (WHERE v.verdict = 'attenuated')                AS attenuated,
    count(*) FILTER (WHERE v.verdict = 'rejected')                  AS rejected,
    count(*) FILTER (WHERE v.verdict = 'insufficient_sample')       AS insufficient,
    sum(v.null_confirm_prob) FILTER (WHERE v.verdict <> 'insufficient_sample') AS expected
"""


def _rate(r: dict[str, Any]) -> dict[str, Any]:
    tested = int(r["tested"] or 0)
    confirmed = int(r["confirmed"] or 0)
    expected = float(r["expected"] or 0.0)
    return {
        "total": int(r["total"] or 0),
        "tested": tested,
        "confirmed": confirmed,
        "attenuated": int(r["attenuated"] or 0),
        "rejected": int(r["rejected"] or 0),
        "insufficient": int(r["insufficient"] or 0),
        "confirmed_rate_pct": round(confirmed / tested * 100.0, 2) if tested else None,
        "expected_rate_pct": round(expected / tested * 100.0, 2) if tested else None,
        "lift": round(confirmed / expected, 3) if expected > 0 else None,
    }


def get_validation_analytics(db: Session, *, min_n: int = 20) -> dict[str, Any]:
    vrun = db.scalars(
        select(CecchinoRunV2PatternValidationRun)
        .where(CecchinoRunV2PatternValidationRun.status == STATUS_COMPLETED)
        .order_by(CecchinoRunV2PatternValidationRun.completed_at.desc())
    ).first()
    if not vrun:
        return {"validation": None}

    rid = int(vrun.id)
    base = """
        FROM cecchino_run_v2_pattern_validations v
        JOIN cecchino_run_v2_pattern_insight_candidates c ON c.id = v.candidate_id
        WHERE v.validation_run_id = :rid AND c.n >= :min_n
    """

    headline = {
        r["target_type"]: _rate(r)
        for r in _rows(
            db,
            f"SELECT c.target_type, {_RATE_COLUMNS} {base} GROUP BY c.target_type",
            rid=rid,
            min_n=min_n,
        )
    }

    bucket_order = ["20-49", "50-99", "100-199", "200-499", "500+"]
    by_bucket = [
        {"bucket": r["bucket"], "target_type": r["target_type"], **_rate(r)}
        for r in _rows(
            db,
            f"""
            SELECT c.target_type,
                   CASE WHEN c.n < 50 THEN '20-49' WHEN c.n < 100 THEN '50-99'
                        WHEN c.n < 200 THEN '100-199' WHEN c.n < 500 THEN '200-499'
                        ELSE '500+' END AS bucket,
                   {_RATE_COLUMNS}
            {base}
            GROUP BY 1, 2
            """,
            rid=rid,
            min_n=min_n,
        )
    ]
    by_bucket.sort(key=lambda x: (x["target_type"], bucket_order.index(x["bucket"])))

    by_complexity = [
        {"atoms": int(r["atoms"]), "target_type": r["target_type"], **_rate(r)}
        for r in _rows(
            db,
            f"""
            SELECT c.target_type, jsonb_array_length(c.filters_json) AS atoms, {_RATE_COLUMNS}
            {base}
            GROUP BY 1, 2 ORDER BY 1, 2
            """,
            rid=rid,
            min_n=min_n,
        )
    ]

    by_target = [
        {
            "target_type": r["target_type"],
            "target_key": r["target_key"],
            "target_label": r["target_label"],
            "disc_avg_roi_pct": _f(r["disc_avg_roi"]),
            "oos_avg_roi_pct": _f(r["oos_avg_roi"]),
            **_rate(r),
        }
        for r in _rows(
            db,
            f"""
            SELECT c.target_type, c.target_key, c.target_label,
                   avg(c.roi_pct) FILTER (WHERE v.verdict <> 'insufficient_sample') AS disc_avg_roi,
                   avg(v.roi_pct) FILTER (WHERE v.verdict <> 'insufficient_sample') AS oos_avg_roi,
                   {_RATE_COLUMNS}
            {base}
            GROUP BY 1, 2, 3
            ORDER BY 1, 3
            """,
            rid=rid,
            min_n=min_n,
        )
    ]

    shrinkage = [
        {
            "bucket": r["bucket"],
            "disc_avg_roi_pct": _f(r["disc_avg_roi"]),
            "oos_avg_roi_pct": _f(r["oos_avg_roi"]),
            "patterns": int(r["patterns"]),
        }
        for r in _rows(
            db,
            f"""
            SELECT CASE WHEN c.roi_pct < 5 THEN '0-5%' WHEN c.roi_pct < 10 THEN '5-10%'
                        WHEN c.roi_pct < 20 THEN '10-20%' WHEN c.roi_pct < 40 THEN '20-40%'
                        ELSE '40%+' END AS bucket,
                   avg(c.roi_pct) AS disc_avg_roi,
                   avg(v.roi_pct) AS oos_avg_roi,
                   count(*)       AS patterns
            {base} AND c.target_type = 'market' AND v.verdict <> 'insufficient_sample'
            GROUP BY 1
            """,
            rid=rid,
            min_n=min_n,
        )
    ]
    roi_order = ["0-5%", "5-10%", "10-20%", "20-40%", "40%+"]
    shrinkage.sort(key=lambda x: roi_order.index(x["bucket"]))

    scatter = [
        {
            "disc_roi_pct": _f(r["disc_roi"]),
            "oos_roi_pct": _f(r["oos_roi"]),
            "n": int(r["n"]),
            "verdict": r["verdict"],
        }
        for r in _rows(
            db,
            f"""
            SELECT c.roi_pct AS disc_roi, v.roi_pct AS oos_roi, c.n, v.verdict
            {base} AND c.target_type = 'market' AND v.verdict <> 'insufficient_sample'
                   AND (c.id % 11) = 0
            ORDER BY c.id LIMIT 1200
            """,
            rid=rid,
            min_n=min_n,
        )
    ]

    return {
        "validation": {
            "id": rid,
            "season_label": vrun.season_label,
            "completed_at": vrun.completed_at.isoformat() if vrun.completed_at else None,
            "summary": vrun.summary_json,
        },
        "min_n": min_n,
        "headline": headline,
        "by_bucket": by_bucket,
        "by_complexity": by_complexity,
        "by_target": by_target,
        "shrinkage": shrinkage,
        "scatter": scatter,
    }
