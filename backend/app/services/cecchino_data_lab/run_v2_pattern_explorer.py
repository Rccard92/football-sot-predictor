"""Tabella "Esplora i pattern": ogni pattern con i numeri stagione per stagione
(scoperta + tutte le verifiche) e il totale su tutte le stagioni.

Filtro di tenuta:
- "positive_total" (default): solo pattern che sul totale delle stagioni hanno
  ROI positivo (mercati) o spostano ancora la frequenza nella direzione
  trovata in scoperta (situazioni senza quota). Nasconde il rumore.
- "confirmed_all": confermati in OGNI stagione di verifica (la scoperta li ha
  gia' promossi per costruzione).
- "all": nessun filtro.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import Float, and_, case, cast, func, or_, select
from sqlalchemy.orm import Session

from app.models.cecchino_run_v2 import CecchinoRunV2Run
from app.models.cecchino_run_v2_pattern_insight import (
    TARGET_TYPE_MARKET,
    VERDICT_CONFIRMED,
    VERDICT_INSUFFICIENT,
    CecchinoRunV2PatternInsightCandidate as C,
    CecchinoRunV2PatternValidation as V,
)

HOLD_POSITIVE_TOTAL = "positive_total"
HOLD_CONFIRMED_ALL = "confirmed_all"
HOLD_ALL = "all"
HOLDS = (HOLD_POSITIVE_TOTAL, HOLD_CONFIRMED_ALL, HOLD_ALL)


def _f(v: Any) -> float | None:
    return float(v) if v is not None else None


def list_candidates(
    db: Session,
    *,
    target_type: str | None = None,
    target_key: str | None = None,
    threshold: float | None = None,
    min_n: int = 20,
    verdict: str | None = None,
    validation_id: int | None = None,
    hold: str = HOLD_POSITIVE_TOTAL,
    sort: str = "total_profit_desc",
    limit: int = 100,
    offset: int = 0,
) -> dict[str, Any]:
    from app.services.cecchino_data_lab.run_v2_pattern_insight_service import (
        _d,
        _latest_completed_run,
        candidate_row_to_dict,
        run_to_dict,
    )
    from app.services.cecchino_data_lab.run_v2_pattern_validation_analytics import (
        _completed_validations,
    )

    run = _latest_completed_run(db)
    if not run:
        return {"run": None, "validation": None, "validations": [], "seasons": [], "total": 0, "items": []}
    if hold not in HOLDS:
        hold = HOLD_POSITIVE_TOTAL

    vruns = _completed_validations(db, int(run.id))
    ids = [int(v.id) for v in vruns]
    k = len(ids)
    vrun = next((v for v in vruns if int(v.id) == validation_id), vruns[-1] if vruns else None)
    disc_run = db.get(CecchinoRunV2Run, int(run.run_v2_run_id))
    disc_season = (disc_run.summary_json or {}).get("season_label") if disc_run else None

    # Totali delle stagioni di verifica per pattern
    agg = (
        select(
            V.candidate_id.label("cid"),
            func.count().label("seasons"),
            func.sum(V.n).label("n"),
            func.sum(V.wins).label("wins"),
            func.sum(func.coalesce(V.profit_units, 0)).label("profit"),
            func.sum(func.coalesce(V.n_priced, 0)).label("n_priced"),
            func.sum(V.n * V.baseline_win_rate_pct).label("baseline_weighted"),
            func.count().filter(V.verdict == VERDICT_CONFIRMED).label("confirmed"),
            func.count().filter(V.verdict != VERDICT_INSUFFICIENT).label("tested"),
        )
        .where(V.validation_run_id.in_(ids or [-1]))
        .group_by(V.candidate_id)
        .subquery()
    )

    tot_n = C.n + func.coalesce(agg.c.n, 0)
    tot_wins = C.wins + func.coalesce(agg.c.wins, 0)
    tot_profit = func.coalesce(C.profit_units, 0) + func.coalesce(agg.c.profit, 0)
    tot_priced = func.coalesce(C.n_priced, 0) + func.coalesce(agg.c.n_priced, 0)
    tot_roi = cast(tot_profit, Float) * 100.0 / func.nullif(tot_priced, 0)
    tot_win_rate = cast(tot_wins, Float) * 100.0 / func.nullif(tot_n, 0)
    tot_baseline = (
        cast(C.n * C.baseline_win_rate_pct + func.coalesce(agg.c.baseline_weighted, 0), Float)
        / func.nullif(tot_n, 0)
    )
    tot_dev = tot_win_rate - tot_baseline
    direction = case((C.deviation_pct < 0, -1.0), else_=1.0)

    sel_v = V
    filters = [C.insight_run_id == run.id, C.n >= min_n]
    if target_type:
        filters.append(C.target_type == target_type)
    if target_key:
        filters.append(C.target_key == target_key)
    if threshold is not None:
        filters.append(C.threshold == _d(threshold))
    if hold == HOLD_POSITIVE_TOTAL:
        filters.append(
            or_(
                and_(C.target_type == TARGET_TYPE_MARKET, tot_profit > 0),
                and_(C.target_type != TARGET_TYPE_MARKET, tot_dev * direction > 0),
            )
        )
    elif hold == HOLD_CONFIRMED_ALL:
        filters.append(func.coalesce(agg.c.confirmed, 0) == (k if k else -1))

    join_on = (
        (sel_v.candidate_id == C.id) & (sel_v.validation_run_id == vrun.id)
        if vrun is not None
        else sel_v.id == -1
    )
    if vrun is not None and verdict:
        filters.append(sel_v.verdict == verdict)

    base_from = select(C).select_from(C).outerjoin(agg, agg.c.cid == C.id).outerjoin(sel_v, join_on)
    total = int(
        db.scalar(
            select(func.count(C.id))
            .select_from(C)
            .outerjoin(agg, agg.c.cid == C.id)
            .outerjoin(sel_v, join_on)
            .where(*filters)
        )
        or 0
    )

    query = base_from.add_columns(
        tot_n.label("t_n"),
        tot_wins.label("t_wins"),
        tot_profit.label("t_profit"),
        tot_priced.label("t_priced"),
        tot_roi.label("t_roi"),
        tot_win_rate.label("t_wr"),
        tot_dev.label("t_dev"),
        func.coalesce(agg.c.confirmed, 0).label("t_confirmed"),
        func.coalesce(agg.c.tested, 0).label("t_tested"),
    ).where(*filters)

    order = {
        "total_profit_desc": [tot_profit.desc()],
        "total_roi_desc": [tot_roi.desc().nulls_last()],
        "total_n_desc": [tot_n.desc()],
        "total_deviation_desc": [(tot_dev * direction).desc().nulls_last()],
        "roi_desc": [C.roi_pct.desc().nulls_last()],
        "deviation_desc": [func.abs(C.deviation_pct).desc().nulls_last()],
        "oos_roi_desc": [sel_v.roi_pct.desc().nulls_last()],
        "oos_n_desc": [sel_v.n.desc().nulls_last()],
    }.get(sort)
    if order is None:
        # "best": profitto totale per i mercati, scarto totale per le situazioni
        order = [tot_profit.desc(), (tot_dev * direction).desc().nulls_last()]
    rows = db.execute(query.order_by(*order, C.id).limit(limit).offset(offset)).all()

    items: list[dict[str, Any]] = []
    for row in rows:
        cand = row[0]
        item = candidate_row_to_dict(cand)
        item["profit_units"] = _f(cand.profit_units)
        item["n_priced"] = cand.n_priced
        t_n = int(row.t_n or 0)
        t_wins = int(row.t_wins or 0)
        item["total"] = {
            "seasons": 1 + k,
            "n": t_n,
            "wins": t_wins,
            "losses": t_n - t_wins,
            "win_rate_pct": round(float(row.t_wr), 2) if row.t_wr is not None else None,
            "roi_pct": round(float(row.t_roi), 2) if row.t_roi is not None else None,
            "profit_units": round(float(row.t_profit), 2) if row.t_profit is not None else None,
            "n_priced": int(row.t_priced or 0),
            "deviation_pct": round(float(row.t_dev), 2) if row.t_dev is not None else None,
            "validations_confirmed": int(row.t_confirmed or 0),
            "validations_tested": int(row.t_tested or 0),
            "validations_total": k,
        }
        items.append(item)

    # stagione per stagione per le righe della pagina
    if items:
        by_candidate: dict[int, dict[int, V]] = {}
        if ids:
            for val in db.scalars(
                select(V).where(
                    V.validation_run_id.in_(ids), V.candidate_id.in_([it["id"] for it in items])
                )
            ).all():
                by_candidate.setdefault(int(val.candidate_id), {})[int(val.validation_run_id)] = val
        for it in items:
            seasons = [
                {
                    "role": "discovery",
                    "validation_id": None,
                    "season_label": disc_season,
                    "n": it["n"],
                    "wins": it["wins"],
                    "losses": it["losses"],
                    "win_rate_pct": it["win_rate_pct"],
                    "roi_pct": it["roi_pct"],
                    "profit_units": it["profit_units"],
                    "avg_quota": it["avg_quota"],
                    "deviation_pct": it["deviation_pct"],
                    "verdict": None,
                    "null_confirm_prob": None,
                    "tier_json": None,
                }
            ]
            for v in vruns:
                val = by_candidate.get(it["id"], {}).get(int(v.id))
                seasons.append(
                    {
                        "role": "validation",
                        "validation_id": int(v.id),
                        "season_label": v.season_label,
                        "n": val.n if val else 0,
                        "wins": val.wins if val else 0,
                        "losses": val.losses if val else 0,
                        "win_rate_pct": _f(val.win_rate_pct) if val else None,
                        "roi_pct": _f(val.roi_pct) if val else None,
                        "profit_units": _f(val.profit_units) if val else None,
                        "avg_quota": _f(val.avg_quota) if val else None,
                        "deviation_pct": _f(val.deviation_pct) if val else None,
                        "verdict": val.verdict if val else None,
                        "null_confirm_prob": _f(val.null_confirm_prob) if val else None,
                        "tier_json": val.tier_json if val else None,
                    }
                )
            it["seasons"] = seasons
            sel = next((s for s in seasons if s["validation_id"] == (int(vrun.id) if vrun else -1)), None)
            it["oos"] = sel if sel and sel["verdict"] is not None else None

    return {
        "run": run_to_dict(run),
        "validation": (
            {"id": int(vrun.id), "season_label": vrun.season_label} if vrun is not None else None
        ),
        "validations": [{"id": int(v.id), "season_label": v.season_label} for v in vruns],
        "seasons": [disc_season] + [v.season_label for v in vruns],
        "hold": hold,
        "total": total,
        "items": items,
    }
