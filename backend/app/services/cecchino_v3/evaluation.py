"""Esame dei calcoli V3 contro V2, contro la fase precedente e contro la
quota di chiusura.

Confronto sempre sulle STESSE partite (idonee per la V3, presenti nella V2,
con quote di chiusura e, dalla Fase 2, previste anche dalla fase precedente).
Errore = Brier (media di (esito - probabilita')^2 per esito di mercato, come
nel blocco "Cecchino contro il mercato") e log-loss.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services.cecchino_data_lab.run_v2_market_scoreboard import _FAIR_PROB_SQL
from app.services.cecchino_data_lab.run_v2_scope import TOP_TIER_COMPETITIONS
from app.services.cecchino_v3.constants import (
    CALIBRATION_BINS,
    EXAM_CALIBRATION_FAMILIES,
    EXAM_FAMILIES,
    EXAM_MAX_CALIBRATION_ERROR_PCT,
    JUDGE_SEASONS,
    LOCKBOX,
    MARKET_FAMILY,
    WARMUP_SEASON,
)


def _quoted(values: list[str]) -> str:
    return ", ".join("'" + v.replace("'", "''") + "'" for v in values)


def _case(column: str, mapping: dict[str, str]) -> str:
    whens = "\n".join(f"WHEN '{k}' THEN {v}" for k, v in mapping.items())
    return f"(CASE {column} {whens} END)"


def _base_cte(with_baseline: bool) -> str:
    families = {k: f"'{v}'" for k, v in MARKET_FAMILY.items()}
    return f"""
    WITH v2_runs AS (
        SELECT DISTINCT ON (summary_json->>'season_label') id
        FROM cecchino_run_v2_runs
        WHERE status = 'completed' AND run_scope = 'full'
          AND summary_json->>'season_label' < :lockbox
        ORDER BY summary_json->>'season_label', completed_at DESC
    ),
    v2 AS MATERIALIZED (
        SELECT s.lab_match_id, r.market_key, r.probability::double precision AS p
        FROM cecchino_run_v2_market_results r
        JOIN v2_runs ON v2_runs.id = r.run_id
        JOIN cecchino_run_v2_match_snapshots s ON s.id = r.match_snapshot_id
        WHERE s.eligibility_status = 'eligible_core'
          AND r.observation_layer = 'core_strict'
          AND r.pre_match_input_safe IS TRUE
          AND r.probability IS NOT NULL
    ),
    {'''prev AS MATERIALIZED (
        SELECT lab_match_id, market_key, probability::double precision AS p
        FROM cecchino_v3_market_predictions
        WHERE run_id = :baseline_run_id
    ),''' if with_baseline else ''}
    base AS (
        SELECT mp.season_label,
               mp.competition_name,
               CASE WHEN mp.competition_name IN ({_quoted(sorted(TOP_TIER_COMPETITIONS))})
                    THEN 'top' ELSE 'lower' END AS tier,
               mp.phase,
               mk.market_key,
               {_case('mk.market_key', families)} AS family,
               mk.won::int AS won,
               mk.probability::double precision AS p3,
               v2.p AS p2,
               {'prev.p' if with_baseline else 'NULL::double precision'} AS pp,
               {_case('mk.market_key', _FAIR_PROB_SQL)}::double precision AS pb
        FROM cecchino_v3_market_predictions mk
        JOIN cecchino_v3_match_predictions mp ON mp.id = mk.match_prediction_id
        JOIN cecchino_lab_matches m ON m.id = mk.lab_match_id
        LEFT JOIN v2 ON v2.lab_match_id = mk.lab_match_id AND v2.market_key = mk.market_key
        {'LEFT JOIN prev ON prev.lab_match_id = mk.lab_match_id AND prev.market_key = mk.market_key'
         if with_baseline else ''}
        WHERE mk.run_id = :run_id AND mp.eval_eligible AND mk.won IS NOT NULL
    ),
    common AS (
        SELECT * FROM base
        WHERE p2 IS NOT NULL AND pb IS NOT NULL {'AND pp IS NOT NULL' if with_baseline else ''}
    )
    """


def _ll(col: str) -> str:
    p = f"least(greatest({col}, 1e-6), 1 - 1e-6)"
    return f"avg(-(won * ln({p}) + (1 - won) * ln(1 - {p})))"


_METRICS_COMMON = f"""
    count(*) AS n,
    avg(power(won - p3, 2)) AS brier_v3,
    avg(power(won - p2, 2)) AS brier_v2,
    avg(power(won - pp, 2)) AS brier_prev,
    avg(power(won - pb, 2)) AS brier_book,
    {_ll('p3')} AS log_loss_v3,
    {_ll('p2')} AS log_loss_v2,
    {_ll('pp')} AS log_loss_prev,
    {_ll('pb')} AS log_loss_book
"""


def _f(v: Any, nd: int = 5) -> float | None:
    return round(float(v), nd) if v is not None else None


def _rows(db: Session, sql: str, run_id: int, baseline_run_id: int | None) -> list[dict[str, Any]]:
    params: dict[str, Any] = {"run_id": run_id, "lockbox": LOCKBOX}
    if baseline_run_id is not None:
        params["baseline_run_id"] = baseline_run_id
    return [
        dict(r._mapping)
        for r in db.execute(text(_base_cte(baseline_run_id is not None) + sql), params)
    ]


def _metric_row(r: dict[str, Any], keys: tuple[str, ...]) -> dict[str, Any]:
    out = {k: r[k] for k in keys}
    out["n"] = int(r["n"])
    for k in (
        "brier_v3",
        "brier_v2",
        "brier_prev",
        "brier_book",
        "log_loss_v3",
        "log_loss_v2",
        "log_loss_prev",
        "log_loss_book",
    ):
        if k in r:
            out[k] = _f(r[k])
    if out.get("brier_v3") is not None and out.get("brier_prev"):
        out["v3_vs_prev_pct"] = round(
            (out["brier_v3"] - out["brier_prev"]) / out["brier_prev"] * 100.0, 2
        )
    if out.get("brier_v3") is not None and out.get("brier_v2"):
        out["v3_vs_v2_pct"] = round((out["brier_v3"] - out["brier_v2"]) / out["brier_v2"] * 100.0, 2)
    if out.get("brier_v3") is not None and out.get("brier_book"):
        out["v3_vs_book_pct"] = round(
            (out["brier_v3"] - out["brier_book"]) / out["brier_book"] * 100.0, 2
        )
    return out


def build_evaluation(db: Session, run_id: int, *, baseline_run_id: int | None = None) -> dict[str, Any]:
    def rows(sql: str) -> list[dict[str, Any]]:
        return _rows(db, sql, run_id, baseline_run_id)

    by_season = [
        _metric_row(r, ("season_label", "family"))
        for r in rows(f"SELECT season_label, family, {_METRICS_COMMON} FROM common GROUP BY 1, 2 ORDER BY 1, 2")
    ]
    by_tier = [
        _metric_row(r, ("season_label", "family", "tier"))
        for r in rows(f"SELECT season_label, family, tier, {_METRICS_COMMON} FROM common GROUP BY 1, 2, 3 ORDER BY 1, 2, 3")
    ]
    by_phase = [
        _metric_row(r, ("season_label", "family", "phase"))
        for r in rows(f"SELECT season_label, family, phase, {_METRICS_COMMON} FROM common GROUP BY 1, 2, 3 ORDER BY 1, 2, 3")
    ]
    judge = _quoted(list(JUDGE_SEASONS))
    by_competition = [
        _metric_row(r, ("competition_name", "tier"))
        for r in rows(f"""SELECT competition_name, tier, {_METRICS_COMMON} FROM common
                WHERE family = 'FT_1X2' AND season_label IN ({judge})
                GROUP BY 1, 2 ORDER BY 1""")
    ]
    # tutte le partite idonee della V3 (anche quelle che la V2 non copre)
    v3_only = [
        _metric_row(r, ("season_label", "family"))
        for r in rows(f"""SELECT season_label, family, count(*) AS n,
                       avg(power(won - p3, 2)) AS brier_v3,
                       avg(power(won - pb, 2)) AS brier_book,
                       {_ll('p3')} AS log_loss_v3,
                       {_ll('pb')} AS log_loss_book
                FROM base WHERE pb IS NOT NULL GROUP BY 1, 2 ORDER BY 1, 2""")
    ]
    coverage = [
        {
            "season_label": r["season_label"],
            "v3_eligible_matches": int(r["v3"]),
            "common_matches": int(r["common"]),
        }
        for r in rows("""SELECT season_label,
                      count(*) FILTER (WHERE market_key = 'HOME') AS v3,
                      count(*) FILTER (WHERE market_key = 'HOME' AND p2 IS NOT NULL AND pb IS NOT NULL) AS common
               FROM base GROUP BY season_label ORDER BY 1""")
    ]

    calibration: list[dict[str, Any]] = []
    calibration_error: dict[str, dict[str, float | None]] = {}
    for family in EXAM_CALIBRATION_FAMILIES:
        bins = rows(f"""SELECT least(floor(p3 * {CALIBRATION_BINS})::int, {CALIBRATION_BINS - 1}) AS bin,
                       count(*) AS n, avg(p3) AS avg_p3, avg(won) AS won_rate,
                       avg(p2) AS avg_p2, avg(pb) AS avg_pb
                FROM common WHERE family = '{family}' AND season_label IN ({judge})
                GROUP BY 1 ORDER BY 1""")
        total = sum(int(b["n"]) for b in bins)
        ece = (
            sum(int(b["n"]) * abs(float(b["avg_p3"]) - float(b["won_rate"])) for b in bins) / total * 100.0
            if total
            else None
        )
        calibration_error[family] = {"v3_pct": round(ece, 3) if ece is not None else None}
        for b in bins:
            calibration.append(
                {
                    "family": family,
                    "bin": int(b["bin"]),
                    "n": int(b["n"]),
                    "avg_probability_v3": _f(b["avg_p3"], 4),
                    "won_rate": _f(b["won_rate"], 4),
                    "avg_probability_v2": _f(b["avg_p2"], 4),
                    "avg_probability_book": _f(b["avg_pb"], 4),
                }
            )

    reference = "prev" if baseline_run_id is not None else "v2"
    exam = _exam(by_season, calibration_error, reference=reference)
    return {
        "warmup_season": WARMUP_SEASON,
        "judge_seasons": list(JUDGE_SEASONS),
        "baseline_run_id": baseline_run_id,
        "comparison_set": (
            "partite idonee V3 (>=5 partite giocate) presenti anche nella V2, con quota di chiusura"
            + (" e previste dalla fase precedente" if baseline_run_id is not None else "")
        ),
        "exam": exam,
        "by_season": by_season,
        "by_tier": by_tier,
        "by_phase": by_phase,
        "by_competition": by_competition,
        "v3_all_eligible": v3_only,
        "coverage": coverage,
        "calibration": calibration,
        "calibration_error": calibration_error,
    }


_REFERENCE_LABELS = {"v2": "della V2", "prev": "della fase precedente"}


def _exam(
    by_season: list[dict[str, Any]],
    calibration_error: dict[str, dict[str, float | None]],
    *,
    reference: str,
) -> dict[str, Any]:
    ref_key = "brier_v2" if reference == "v2" else "brier_prev"
    families: list[dict[str, Any]] = []
    for family in EXAM_FAMILIES:
        seasons = []
        for season in JUDGE_SEASONS:
            row = next(
                (r for r in by_season if r["family"] == family and r["season_label"] == season), None
            )
            better = (
                row is not None
                and row.get("brier_v3") is not None
                and row.get(ref_key) is not None
                and row["brier_v3"] < row[ref_key]
            )
            seasons.append(
                {
                    "season_label": season,
                    "passed": better,
                    "brier_v3": row.get("brier_v3") if row else None,
                    "brier_v2": row.get("brier_v2") if row else None,
                    "brier_reference": row.get(ref_key) if row else None,
                    "brier_book": row.get("brier_book") if row else None,
                }
            )
        families.append(
            {"family": family, "passed": all(s["passed"] for s in seasons), "seasons": seasons}
        )
    calibration = [
        {
            "family": family,
            "calibration_error_pct": calibration_error.get(family, {}).get("v3_pct"),
            "max_allowed_pct": EXAM_MAX_CALIBRATION_ERROR_PCT,
            "passed": (calibration_error.get(family, {}).get("v3_pct") or 99.0)
            <= EXAM_MAX_CALIBRATION_ERROR_PCT,
        }
        for family in EXAM_CALIBRATION_FAMILIES
    ]
    return {
        "passed": all(f["passed"] for f in families) and all(c["passed"] for c in calibration),
        "reference": reference,
        "accuracy_vs_v2": families,
        "calibration": calibration,
        "rules": [
            f"In ogni famiglia di mercato, errore V3 piu' basso {_REFERENCE_LABELS[reference]} "
            "in tutte le stagioni di giudizio",
            f"Errore di calibrazione V3 <= {EXAM_MAX_CALIBRATION_ERROR_PCT} punti su 1X2 finale e Over/Under",
        ],
    }
