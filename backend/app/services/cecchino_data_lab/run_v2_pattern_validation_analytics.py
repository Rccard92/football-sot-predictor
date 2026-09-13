"""Aggregati della verifica fuori campione, tutti in SQL.

Ogni tasso di riconferma e' accompagnato dal tasso atteso per puro caso
(media delle probabilita' nulle dei pattern testati): e' il confronto tra i
due, non la percentuale da sola, a dire se c'e' segnale.

Selezioni supportate:
- stagione di verifica (una delle verifiche completate dell'analisi corrente)
- divisione: tutte le leghe, prime divisioni, divisioni inferiori
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.models.cecchino_run_v2_pattern_insight import (
    STATUS_COMPLETED,
    CecchinoRunV2PatternValidationRun,
)
from app.services.cecchino_data_lab.run_v2_scope import TIER_LABELS, TIERS

TIER_ALL = "all"


def _rows(db: Session, sql: str, **params: Any) -> list[dict[str, Any]]:
    return [dict(r._mapping) for r in db.execute(text(sql), params)]


def _f(v: Any) -> float | None:
    return float(v) if v is not None else None


def _cols(tier: str) -> dict[str, str]:
    """Espressioni SQL per la divisione scelta: 'all' legge le colonne della
    riga, le divisioni leggono tier_json. `tier` e' sempre validato contro
    un elenco chiuso prima di arrivare qui."""
    if tier == TIER_ALL:
        return {
            "verdict": "v.verdict",
            "null": "v.null_confirm_prob",
            "roi": "v.roi_pct",
            "n": "v.n",
        }
    return {
        "verdict": f"(v.tier_json->'{tier}'->>'verdict')",
        "null": f"((v.tier_json->'{tier}'->>'null_confirm_prob')::double precision)",
        "roi": f"((v.tier_json->'{tier}'->>'roi_pct')::double precision)",
        "n": f"((v.tier_json->'{tier}'->>'n')::int)",
    }


def _rate_columns(c: dict[str, str]) -> str:
    return f"""
    count(*)                                                          AS total,
    count(*) FILTER (WHERE {c['verdict']} <> 'insufficient_sample')   AS tested,
    count(*) FILTER (WHERE {c['verdict']} = 'confirmed')              AS confirmed,
    count(*) FILTER (WHERE {c['verdict']} = 'attenuated')             AS attenuated,
    count(*) FILTER (WHERE {c['verdict']} = 'rejected')               AS rejected,
    count(*) FILTER (WHERE {c['verdict']} = 'insufficient_sample')    AS insufficient,
    sum({c['null']}) FILTER (WHERE {c['verdict']} <> 'insufficient_sample') AS expected
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


def _completed_validations(db: Session, insight_run_id: int) -> list[CecchinoRunV2PatternValidationRun]:
    runs = db.scalars(
        select(CecchinoRunV2PatternValidationRun)
        .where(
            CecchinoRunV2PatternValidationRun.insight_run_id == insight_run_id,
            CecchinoRunV2PatternValidationRun.status == STATUS_COMPLETED,
        )
        .order_by(
            CecchinoRunV2PatternValidationRun.season_label,
            CecchinoRunV2PatternValidationRun.completed_at.desc(),
        )
    ).all()
    latest_by_season: dict[str, CecchinoRunV2PatternValidationRun] = {}
    for r in runs:
        latest_by_season.setdefault(r.season_label or str(r.id), r)
    return sorted(latest_by_season.values(), key=lambda r: r.season_label or "")


def get_validation_analytics(
    db: Session,
    *,
    min_n: int = 20,
    validation_id: int | None = None,
    tier: str = TIER_ALL,
) -> dict[str, Any]:
    from app.services.cecchino_data_lab.run_v2_pattern_insight_service import _latest_completed_run

    if tier not in (TIER_ALL, *TIERS):
        tier = TIER_ALL

    insight = _latest_completed_run(db)
    if insight is None:
        return {"validation": None, "validations": []}

    validations = _completed_validations(db, int(insight.id))
    if not validations:
        return {"validation": None, "validations": []}

    vrun = next((v for v in validations if int(v.id) == validation_id), validations[-1])
    rid = int(vrun.id)
    c = _cols(tier)
    base = f"""
        FROM cecchino_run_v2_pattern_validations v
        JOIN cecchino_run_v2_pattern_insight_candidates c ON c.id = v.candidate_id
        WHERE v.validation_run_id = :rid AND c.n >= :min_n
    """
    rate_cols = _rate_columns(c)

    headline = {
        r["target_type"]: _rate(r)
        for r in _rows(
            db, f"SELECT c.target_type, {rate_cols} {base} GROUP BY c.target_type", rid=rid, min_n=min_n
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
                   {rate_cols}
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
            SELECT c.target_type, jsonb_array_length(c.filters_json) AS atoms, {rate_cols}
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
                   avg(c.roi_pct) FILTER (WHERE {c['verdict']} <> 'insufficient_sample') AS disc_avg_roi,
                   avg({c['roi']}) FILTER (WHERE {c['verdict']} <> 'insufficient_sample') AS oos_avg_roi,
                   {rate_cols}
            {base}
            GROUP BY 1, 2, 3
            ORDER BY 1, 3
            """,
            rid=rid,
            min_n=min_n,
        )
    ]

    roi_order = ["0-5%", "5-10%", "10-20%", "20-40%", "40%+"]
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
                   avg({c['roi']}) AS oos_avg_roi,
                   count(*)       AS patterns
            {base} AND c.target_type = 'market' AND {c['verdict']} <> 'insufficient_sample'
            GROUP BY 1
            """,
            rid=rid,
            min_n=min_n,
        )
    ]
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
            SELECT c.roi_pct AS disc_roi, {c['roi']} AS oos_roi, c.n, {c['verdict']} AS verdict
            {base} AND c.target_type = 'market' AND {c['verdict']} <> 'insufficient_sample'
                   AND (c.id % 11) = 0
            ORDER BY c.id LIMIT 1200
            """,
            rid=rid,
            min_n=min_n,
        )
    ]

    return {
        "insight": {
            "id": int(insight.id),
            "odds_mode": insight.odds_mode,
            "engine_version": insight.engine_version,
        },
        "validations": [
            {"id": int(v.id), "season_label": v.season_label} for v in validations
        ],
        "validation": {
            "id": rid,
            "season_label": vrun.season_label,
            "completed_at": vrun.completed_at.isoformat() if vrun.completed_at else None,
            "summary": vrun.summary_json,
        },
        "tier": tier,
        "tiers": [{"key": TIER_ALL, "label": "Tutte le leghe"}]
        + [{"key": t, "label": TIER_LABELS[t]} for t in TIERS],
        "min_n": min_n,
        "headline": headline,
        "by_bucket": by_bucket,
        "by_complexity": by_complexity,
        "by_target": by_target,
        "shrinkage": shrinkage,
        "scatter": scatter,
        "persistence": get_persistence(db, validations=validations, min_n=min_n, tier=tier),
    }


def get_persistence(
    db: Session,
    *,
    validations: list[CecchinoRunV2PatternValidationRun],
    min_n: int,
    tier: str,
) -> dict[str, Any] | None:
    """Tenuta su piu' stagioni: pattern confermati in TUTTE le stagioni di
    verifica, contro quanti ne attenderebbe il caso. Le stagioni usano partite
    diverse, quindi la probabilita' nulla di essere confermati in tutte e' il
    prodotto delle probabilita' di ciascuna."""
    if len(validations) < 2:
        return None
    c = _cols(tier)
    ids = [int(v.id) for v in validations]
    k = len(ids)
    rows = _rows(
        db,
        f"""
        WITH per_pattern AS (
            SELECT c.id, c.target_type, c.target_key, c.target_label,
                   count(*) FILTER (WHERE {c['verdict']} <> 'insufficient_sample') AS tested_seasons,
                   count(*) FILTER (WHERE {c['verdict']} = 'confirmed')            AS confirmed_seasons,
                   exp(sum(ln(greatest({c['null']}, 1e-9))))                      AS p_all_by_chance
            FROM cecchino_run_v2_pattern_validations v
            JOIN cecchino_run_v2_pattern_insight_candidates c ON c.id = v.candidate_id
            WHERE v.validation_run_id = ANY(:ids) AND c.n >= :min_n
            GROUP BY c.id, c.target_type, c.target_key, c.target_label
        )
        SELECT target_type, target_key, target_label,
               count(*) FILTER (WHERE tested_seasons = :k)                             AS tested_all,
               count(*) FILTER (WHERE tested_seasons = :k AND confirmed_seasons = :k)  AS confirmed_all,
               sum(p_all_by_chance) FILTER (WHERE tested_seasons = :k)                 AS expected_all
        FROM per_pattern
        GROUP BY 1, 2, 3
        ORDER BY 1, 3
        """,
        ids=ids,
        min_n=min_n,
        k=k,
    )

    def summarize(items: list[dict[str, Any]]) -> dict[str, Any]:
        tested = sum(int(i["tested_all"] or 0) for i in items)
        confirmed = sum(int(i["confirmed_all"] or 0) for i in items)
        expected = sum(float(i["expected_all"] or 0.0) for i in items)
        return {
            "tested": tested,
            "confirmed": confirmed,
            "confirmed_rate_pct": round(confirmed / tested * 100.0, 2) if tested else None,
            "expected": round(expected, 1),
            "expected_rate_pct": round(expected / tested * 100.0, 2) if tested else None,
            "lift": round(confirmed / expected, 3) if expected > 0 else None,
        }

    return {
        "seasons": [v.season_label for v in validations],
        "headline": {
            t: summarize([r for r in rows if r["target_type"] == t]) for t in ("market", "synthetic")
        },
        "by_target": [
            {
                "target_type": r["target_type"],
                "target_key": r["target_key"],
                "target_label": r["target_label"],
                **summarize([r]),
            }
            for r in rows
        ],
    }
