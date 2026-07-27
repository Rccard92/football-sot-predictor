"""Analisi storiche betting read-only per Cecchino Lab Overview.

Nessuna formula Cecchino, nessuna predizione, nessun ML.
Calcoli esclusivamente sui dati già importati (FT/HT + quote Bet365).
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from decimal import Decimal
from statistics import median
from typing import Any, Literal

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.cecchino_lab_data_issue import CecchinoLabDataIssue
from app.models.cecchino_lab_dataset import CecchinoLabDataset
from app.models.cecchino_lab_import import CecchinoLabImport
from app.models.cecchino_lab_match import CecchinoLabMatch

Selection = Literal["H", "D", "A"]

FAVORITE_BUCKETS: list[tuple[str, float | None, float | None]] = [
    ("<=1.50", None, 1.50),
    ("1.51-1.80", 1.51, 1.80),
    ("1.81-2.20", 1.81, 2.20),
    ("2.21-2.75", 2.21, 2.75),
    (">2.75", 2.76, None),
]

MOVEMENT_BUCKETS: list[tuple[str, float | None, float | None]] = [
    ("strong_shorten", None, -10.0),
    ("shorten", -10.0, -3.0),
    ("stable", -3.0, 3.0),
    ("lengthen", 3.0, 10.0),
    ("strong_lengthen", 10.0, None),
]


def _r1(v: float | None) -> float | None:
    if v is None:
        return None
    return round(v, 1)


def _r2(v: float | None) -> float | None:
    if v is None:
        return None
    return round(v, 2)


def _f(v: Decimal | float | int | None) -> float | None:
    if v is None:
        return None
    return float(v)


def build_metric(
    count: int,
    denominator: int,
    *,
    numerator: int | None = None,
    sample_size: int | None = None,
) -> dict[str, Any]:
    """Metrica standard: count/percentage/denominator; NULL non conta come zero."""
    pct = None
    if denominator > 0:
        pct = _r1(100.0 * count / denominator)
    out: dict[str, Any] = {
        "count": count,
        "percentage": pct,
        "denominator": denominator,
    }
    if numerator is not None:
        out["numerator"] = numerator
    if sample_size is not None:
        out["sample_size"] = sample_size
    return out


def unique_favorite(
    home: float | None, draw: float | None, away: float | None
) -> Selection | None:
    """Favorita = quota pre-closing minima univoca tra 1/X/2."""
    if home is None or draw is None or away is None:
        return None
    if home <= 0 or draw <= 0 or away <= 0:
        return None
    pairs: list[tuple[Selection, float]] = [("H", home), ("D", draw), ("A", away)]
    min_odds = min(o for _, o in pairs)
    winners = [s for s, o in pairs if o == min_odds]
    if len(winners) != 1:
        return None
    return winners[0]


def unique_longest(
    home: float | None, draw: float | None, away: float | None
) -> Selection | None:
    """Selezione con quota pre-closing massima univoca."""
    if home is None or draw is None or away is None:
        return None
    if home <= 0 or draw <= 0 or away <= 0:
        return None
    pairs: list[tuple[Selection, float]] = [("H", home), ("D", draw), ("A", away)]
    max_odds = max(o for _, o in pairs)
    winners = [s for s, o in pairs if o == max_odds]
    if len(winners) != 1:
        return None
    return winners[0]


def normalized_implied(
    home: float | None, draw: float | None, away: float | None
) -> dict[Selection, float] | None:
    if home is None or draw is None or away is None:
        return None
    if home <= 0 or draw <= 0 or away <= 0:
        return None
    raw_h, raw_d, raw_a = 1.0 / home, 1.0 / draw, 1.0 / away
    total = raw_h + raw_d + raw_a
    if total <= 0:
        return None
    return {"H": raw_h / total, "D": raw_d / total, "A": raw_a / total}


def margin_pct(home: float | None, draw: float | None, away: float | None) -> float | None:
    if home is None or draw is None or away is None:
        return None
    if home <= 0 or draw <= 0 or away <= 0:
        return None
    overround = (1.0 / home) + (1.0 / draw) + (1.0 / away)
    return (overround - 1.0) * 100.0


def movement_pct(closing: float | None, pre: float | None) -> float | None:
    if closing is None or pre is None or pre <= 0:
        return None
    return ((closing / pre) - 1.0) * 100.0


def flat_roi_from_results(profits: list[float]) -> tuple[float | None, float | None, int]:
    """Profitto totale e ROI % su flat 1u. Restituisce (profit, roi_pct, n)."""
    n = len(profits)
    if n == 0:
        return None, None, 0
    total = sum(profits)
    return _r2(total), _r1(100.0 * total / n), n


def selection_odds(sel: Selection, h: float | None, d: float | None, a: float | None) -> float | None:
    if sel == "H":
        return h
    if sel == "D":
        return d
    return a


def favorite_bucket_key(odds: float) -> str | None:
    for key, lo, hi in FAVORITE_BUCKETS:
        if lo is None and hi is not None and odds <= hi:
            return key
        if hi is None and lo is not None and odds >= lo:
            return key
        if lo is not None and hi is not None and lo <= odds <= hi:
            return key
    return None


def movement_bucket_key(mov: float) -> str:
    if mov <= -10.0:
        return "strong_shorten"
    if mov < -3.0:
        return "shorten"
    if mov <= 3.0:
        return "stable"
    if mov < 10.0:
        return "lengthen"
    return "strong_lengthen"


@dataclass
class _OutcomeAcc:
    count: int = 0
    odds_sum: float = 0.0
    odds_n: int = 0
    profits: list[float] = field(default_factory=list)


@dataclass
class _LeagueAcc:
    competition_name: str
    country: str
    matches: int = 0
    home: int = 0
    draw: int = 0
    away: int = 0
    over_25: int = 0
    under_25: int = 0
    btts: int = 0
    goals_sum: int = 0
    goals_n: int = 0
    ht_draw: int = 0
    ht_n: int = 0
    fav_unique: int = 0
    fav_wins: int = 0
    margin_sum: float = 0.0
    margin_n: int = 0
    home_profits: list[float] = field(default_factory=list)
    draw_profits: list[float] = field(default_factory=list)
    away_profits: list[float] = field(default_factory=list)
    over_profits: list[float] = field(default_factory=list)
    under_profits: list[float] = field(default_factory=list)
    warnings: int = 0
    errors: int = 0


def _apply_dataset_filters(
    q: Any,
    *,
    season_label: str | None,
    country: str | None,
    competition: str | None,
    dataset_id: int | None,
) -> Any:
    if season_label:
        q = q.filter(CecchinoLabDataset.season_label == season_label)
    if country:
        q = q.filter(CecchinoLabDataset.country == country)
    if competition:
        q = q.filter(CecchinoLabDataset.competition_name == competition)
    if dataset_id is not None:
        q = q.filter(CecchinoLabDataset.id == dataset_id)
    return q


def _available_filters(db: Session) -> dict[str, Any]:
    rows = (
        db.query(
            CecchinoLabDataset.season_label,
            CecchinoLabDataset.country,
            CecchinoLabDataset.competition_name,
        )
        .distinct()
        .all()
    )
    seasons = sorted({r[0] for r in rows if r[0]}, reverse=True)
    countries = sorted({r[1] for r in rows if r[1]})
    competitions = sorted(
        [{"name": r[2], "country": r[1]} for r in rows if r[2]],
        key=lambda x: (x["country"], x["name"]),
    )
    # dedupe competitions
    seen: set[tuple[str, str]] = set()
    comps_unique: list[dict[str, str]] = []
    for c in competitions:
        key = (c["name"], c["country"])
        if key in seen:
            continue
        seen.add(key)
        comps_unique.append(c)
    return {
        "seasons": seasons,
        "countries": countries,
        "competitions": comps_unique,
    }


def _empty_payload(
    *,
    available: dict[str, Any],
    applied: dict[str, Any],
) -> dict[str, Any]:
    empty_outcome = {
        "count": 0,
        "percentage": None,
        "denominator": 0,
        "average_bet365_pre_odds": None,
        "flat_profit_units": None,
        "flat_roi_pct": None,
        "sample_size": 0,
    }
    empty_goal = build_metric(0, 0)
    return {
        "available_filters": available,
        "applied_filters": applied,
        "sample": {"matches_total": 0, "competitions_count": 0, "seasons_count": 0},
        "summary": {
            "matches_total": 0,
            "competitions_count": 0,
            "seasons_count": 0,
            "total_goals": 0,
            "average_goals_per_match": None,
            "average_home_goals": None,
            "average_away_goals": None,
            "favorite_hit_rate": None,
            "bet365_1x2_coverage_pct": None,
            "anomalies_errors": 0,
            "anomalies_warnings": 0,
            "completeness_pct": None,
        },
        "outcomes_1x2": {
            "home": dict(empty_outcome),
            "draw": dict(empty_outcome),
            "away": dict(empty_outcome),
        },
        "goals": {
            "over_15": empty_goal,
            "over_25": {**empty_goal, "average_bet365_pre_odds": None, "flat_profit_units": None, "flat_roi_pct": None, "sample_size": 0},
            "under_25": {**empty_goal, "average_bet365_pre_odds": None, "flat_profit_units": None, "flat_roi_pct": None, "sample_size": 0},
            "under_35": empty_goal,
            "btts_yes": empty_goal,
            "btts_no": empty_goal,
            "score_0_0": empty_goal,
            "team_blank": empty_goal,
            "goals_ge_4": empty_goal,
            "goals_ge_5": empty_goal,
        },
        "first_half": {
            "draw": empty_goal,
            "over_05": empty_goal,
            "over_15": empty_goal,
            "under_15": empty_goal,
            "score_0_0": empty_goal,
            "average_goals": None,
            "pct_of_ft_goals": None,
            "sample_size": 0,
        },
        "favorite": {
            "unique_count": 0,
            "wins": 0,
            "losses": 0,
            "hit_rate": None,
            "average_odds": None,
            "home_favorite_pct": None,
            "away_favorite_pct": None,
            "draw_favorite_pct": None,
            "buckets": [],
        },
        "margins": {
            "average_pre_closing_margin_pct": None,
            "median_pre_closing_margin_pct": None,
            "average_closing_margin_pct": None,
            "median_closing_margin_pct": None,
            "average_pre_to_closing_delta_pp": None,
            "by_competition": [],
            "sample_size_pre": 0,
            "sample_size_closing": 0,
        },
        "odds_movement": {
            "average_home_movement_pct": None,
            "average_draw_movement_pct": None,
            "average_away_movement_pct": None,
            "favorite_shortened_pct": None,
            "winning_selection_shortened_pct": None,
            "average_winner_movement_pct": None,
            "sample_size": 0,
            "distribution": [],
        },
        "longest_odds_hit": {
            "count": 0,
            "percentage": None,
            "average_winning_odds": None,
            "top_competition": None,
            "record_match": None,
            "sample_size": 0,
        },
        "leagues": [],
        "insights": [],
        "is_empty": True,
    }


def get_analytics_overview(
    db: Session,
    *,
    season_label: str | None = None,
    country: str | None = None,
    competition: str | None = None,
    dataset_id: int | None = None,
) -> dict[str, Any]:
    available = _available_filters(db)
    applied = {
        "season_label": season_label,
        "country": country,
        "competition": competition,
        "dataset_id": dataset_id,
    }

    # Lean projection — no raw_json, no full ORM
    cols = (
        CecchinoLabMatch.id,
        CecchinoLabMatch.match_date,
        CecchinoLabMatch.home_team,
        CecchinoLabMatch.away_team,
        CecchinoLabMatch.ft_home_goals,
        CecchinoLabMatch.ft_away_goals,
        CecchinoLabMatch.ft_result,
        CecchinoLabMatch.ht_home_goals,
        CecchinoLabMatch.ht_away_goals,
        CecchinoLabMatch.ht_result,
        CecchinoLabMatch.bet365_home,
        CecchinoLabMatch.bet365_draw,
        CecchinoLabMatch.bet365_away,
        CecchinoLabMatch.bet365_over_25,
        CecchinoLabMatch.bet365_under_25,
        CecchinoLabMatch.bet365_closing_home,
        CecchinoLabMatch.bet365_closing_draw,
        CecchinoLabMatch.bet365_closing_away,
        CecchinoLabMatch.bet365_1x2_pre_ready,
        CecchinoLabMatch.bet365_1x2_closing_ready,
        CecchinoLabMatch.bet365_ou25_pre_ready,
        CecchinoLabMatch.result_ft_ready,
        CecchinoLabMatch.result_ht_ready,
        CecchinoLabMatch.row_quality_status,
        CecchinoLabMatch.dataset_id,
        CecchinoLabDataset.competition_name,
        CecchinoLabDataset.country,
        CecchinoLabDataset.season_label,
    )
    q = db.query(*cols).join(
        CecchinoLabDataset, CecchinoLabDataset.id == CecchinoLabMatch.dataset_id
    )
    q = _apply_dataset_filters(
        q,
        season_label=season_label,
        country=country,
        competition=competition,
        dataset_id=dataset_id,
    )
    rows = q.all()

    if not rows:
        return _empty_payload(available=available, applied=applied)

    # Issue counts for filtered datasets
    ds_ids = {r[24] for r in rows}  # dataset_id index
    issue_q = (
        db.query(CecchinoLabDataIssue.severity, func.count(CecchinoLabDataIssue.id))
        .join(CecchinoLabImport, CecchinoLabImport.id == CecchinoLabDataIssue.import_id)
        .filter(CecchinoLabImport.dataset_id.in_(ds_ids))
        .group_by(CecchinoLabDataIssue.severity)
    )
    issue_counts = {sev: n for sev, n in issue_q.all()}
    anomalies_errors = int(issue_counts.get("error", 0))
    anomalies_warnings = int(issue_counts.get("warning", 0))

    # Per-dataset issue counts for league rows
    ds_issue_q = (
        db.query(
            CecchinoLabImport.dataset_id,
            CecchinoLabDataIssue.severity,
            func.count(CecchinoLabDataIssue.id),
        )
        .join(CecchinoLabImport, CecchinoLabImport.id == CecchinoLabDataIssue.import_id)
        .filter(CecchinoLabImport.dataset_id.in_(ds_ids))
        .group_by(CecchinoLabImport.dataset_id, CecchinoLabDataIssue.severity)
        .all()
    )
    ds_err: dict[int, int] = defaultdict(int)
    ds_warn: dict[int, int] = defaultdict(int)
    for did, sev, n in ds_issue_q:
        if sev == "error":
            ds_err[did] += int(n)
        elif sev == "warning":
            ds_warn[did] += int(n)

    competitions_set: set[str] = set()
    seasons_set: set[str] = set()
    countries_set: set[str] = set()

    ft_n = 0
    total_goals = 0
    home_goals_sum = 0
    away_goals_sum = 0
    complete_n = 0
    with_1x2 = 0

    outcomes: dict[str, _OutcomeAcc] = {
        "home": _OutcomeAcc(),
        "draw": _OutcomeAcc(),
        "away": _OutcomeAcc(),
    }

    over_15 = over_25 = under_25 = under_35 = 0
    btts_yes = btts_no = score_00 = team_blank = ge4 = ge5 = 0
    over_odds_sum = over_odds_n = 0.0
    under_odds_sum = under_odds_n = 0.0
    over_profits: list[float] = []
    under_profits: list[float] = []

    ht_n = 0
    ht_draw = ht_o05 = ht_o15 = ht_u15 = ht_00 = 0
    ht_goals_sum = 0
    ft_goals_for_ht = 0

    fav_unique = 0
    fav_wins = 0
    fav_odds_sum = 0.0
    fav_home = fav_away = fav_draw = 0
    bucket_stats: dict[str, dict[str, Any]] = {
        k: {"matches": 0, "wins": 0, "odds_sum": 0.0, "implied_sum": 0.0}
        for k, _, _ in FAVORITE_BUCKETS
    }

    pre_margins: list[float] = []
    closing_margins: list[float] = []
    margin_by_comp: dict[str, list[float]] = defaultdict(list)

    mov_home: list[float] = []
    mov_draw: list[float] = []
    mov_away: list[float] = []
    fav_shortened_n = fav_mov_n = 0
    win_shortened_n = win_mov_n = 0
    winner_movs: list[float] = []
    mov_dist: dict[str, int] = {k: 0 for k, _, _ in MOVEMENT_BUCKETS}
    mov_sample = 0

    longest_hits = 0
    longest_eligible = 0
    longest_odds_sum = 0.0
    longest_by_comp: dict[str, list[int]] = defaultdict(lambda: [0, 0])  # hits, eligible
    record_match: dict[str, Any] | None = None

    leagues: dict[str, _LeagueAcc] = {}
    # Map competition -> dataset ids seen (for issue rollup)
    comp_dataset_ids: dict[str, set[int]] = defaultdict(set)

    for row in rows:
        (
            mid,
            match_date,
            home_team,
            away_team,
            fthg,
            ftag,
            ftr,
            hthg,
            htag,
            _htr,
            b365h,
            b365d,
            b365a,
            b365o,
            b365u,
            b365ch,
            b365cd,
            b365ca,
            pre_ready,
            closing_ready,
            ou_ready,
            ft_ready,
            ht_ready,
            row_quality,
            did,
            comp_name,
            comp_country,
            season,
        ) = row

        bh = _f(b365h)
        bd = _f(b365d)
        ba = _f(b365a)
        bo = _f(b365o)
        bu = _f(b365u)
        ch = _f(b365ch)
        cd = _f(b365cd)
        ca = _f(b365ca)

        competitions_set.add(comp_name)
        seasons_set.add(season)
        countries_set.add(comp_country)
        if row_quality == "complete":
            complete_n += 1
        if pre_ready:
            with_1x2 += 1

        if comp_name not in leagues:
            leagues[comp_name] = _LeagueAcc(competition_name=comp_name, country=comp_country)
        lg = leagues[comp_name]
        lg.matches += 1
        comp_dataset_ids[comp_name].add(did)

        # FT goals / outcomes
        if ft_ready and fthg is not None and ftag is not None and ftr in ("H", "D", "A"):
            ft_n += 1
            tg = int(fthg) + int(ftag)
            total_goals += tg
            home_goals_sum += int(fthg)
            away_goals_sum += int(ftag)
            lg.goals_sum += tg
            lg.goals_n += 1

            if ftr == "H":
                outcomes["home"].count += 1
                lg.home += 1
            elif ftr == "D":
                outcomes["draw"].count += 1
                lg.draw += 1
            else:
                outcomes["away"].count += 1
                lg.away += 1

            # Goal markets
            if tg >= 2:
                over_15 += 1
            if tg >= 3:
                over_25 += 1
                lg.over_25 += 1
            if tg <= 2:
                under_25 += 1
                lg.under_25 += 1
            if tg <= 3:
                under_35 += 1
            if int(fthg) > 0 and int(ftag) > 0:
                btts_yes += 1
                lg.btts += 1
            else:
                btts_no += 1
            if tg == 0:
                score_00 += 1
            if int(fthg) == 0 or int(ftag) == 0:
                team_blank += 1
            if tg >= 4:
                ge4 += 1
            if tg >= 5:
                ge5 += 1

            # Flat ROI 1X2 (needs pre odds)
            if bh is not None and bd is not None and ba is not None:
                for key, sel, odds in (
                    ("home", "H", bh),
                    ("draw", "D", bd),
                    ("away", "A", ba),
                ):
                    if odds is None or odds <= 0:
                        continue
                    outcomes[key].odds_sum += odds
                    outcomes[key].odds_n += 1
                    profit = (odds - 1.0) if ftr == sel else -1.0
                    outcomes[key].profits.append(profit)
                    if key == "home":
                        lg.home_profits.append(profit)
                    elif key == "draw":
                        lg.draw_profits.append(profit)
                    else:
                        lg.away_profits.append(profit)

            # O/U ROI
            if bo is not None and bo > 0:
                over_odds_sum += bo
                over_odds_n += 1
                p = (bo - 1.0) if tg >= 3 else -1.0
                over_profits.append(p)
                lg.over_profits.append(p)
            if bu is not None and bu > 0:
                under_odds_sum += bu
                under_odds_n += 1
                p = (bu - 1.0) if tg <= 2 else -1.0
                under_profits.append(p)
                lg.under_profits.append(p)

            # Favorite
            fav: Selection | None = unique_favorite(bh, bd, ba)
            if fav is not None:
                fav_odds = selection_odds(fav, bh, bd, ba)
                implied = normalized_implied(bh, bd, ba)
                fav_unique += 1
                lg.fav_unique += 1
                assert fav_odds is not None
                fav_odds_sum += fav_odds
                if fav == "H":
                    fav_home += 1
                elif fav == "A":
                    fav_away += 1
                else:
                    fav_draw += 1
                won = fav == ftr
                if won:
                    fav_wins += 1
                    lg.fav_wins += 1
                bkey = favorite_bucket_key(fav_odds)
                if bkey and implied:
                    bucket_stats[bkey]["matches"] += 1
                    bucket_stats[bkey]["odds_sum"] += fav_odds
                    bucket_stats[bkey]["implied_sum"] += implied[fav]
                    if won:
                        bucket_stats[bkey]["wins"] += 1

            # Longest odds hit
            long_sel = unique_longest(bh, bd, ba)
            if long_sel is not None:
                long_odds = selection_odds(long_sel, bh, bd, ba)
                assert long_odds is not None
                longest_eligible += 1
                longest_by_comp[comp_name][1] += 1
                if long_sel == ftr:
                    longest_hits += 1
                    longest_odds_sum += long_odds
                    longest_by_comp[comp_name][0] += 1
                    if record_match is None or long_odds > record_match["odds"]:
                        record_match = {
                            "match_id": mid,
                            "match_date": match_date.isoformat() if match_date else None,
                            "competition_name": comp_name,
                            "season_label": season,
                            "home_team": home_team,
                            "away_team": away_team,
                            "result": f"{fthg}-{ftag}",
                            "selection": long_sel,
                            "odds": _r2(long_odds),
                        }

            # Margins
            m_pre = margin_pct(bh, bd, ba)
            if m_pre is not None:
                pre_margins.append(m_pre)
                margin_by_comp[comp_name].append(m_pre)
                lg.margin_sum += m_pre
                lg.margin_n += 1
            m_cl = margin_pct(ch, cd, ca)
            if m_cl is not None:
                closing_margins.append(m_cl)

            # Movement
            mh = movement_pct(ch, bh)
            md = movement_pct(cd, bd)
            ma = movement_pct(ca, ba)
            if mh is not None:
                mov_home.append(mh)
            if md is not None:
                mov_draw.append(md)
            if ma is not None:
                mov_away.append(ma)
            if mh is not None and md is not None and ma is not None:
                mov_sample += 1
                # distribution on favorite movement if unique, else on home
                ref_mov = mh
                if fav is not None:
                    ref_mov = {"H": mh, "D": md, "A": ma}[fav]
                    fav_mov_n += 1
                    if ref_mov < 0:
                        fav_shortened_n += 1
                mov_dist[movement_bucket_key(ref_mov)] += 1
                win_odds_mov = {"H": mh, "D": md, "A": ma}.get(ftr)  # type: ignore[arg-type]
                if win_odds_mov is not None:
                    win_mov_n += 1
                    winner_movs.append(win_odds_mov)
                    if win_odds_mov < 0:
                        win_shortened_n += 1

        # First half (only HT fields)
        if ht_ready and hthg is not None and htag is not None:
            ht_n += 1
            htg = int(hthg) + int(htag)
            ht_goals_sum += htg
            if int(hthg) == int(htag):
                ht_draw += 1
                lg.ht_draw += 1
            lg.ht_n += 1
            if htg >= 1:
                ht_o05 += 1
            if htg >= 2:
                ht_o15 += 1
            if htg <= 1:
                ht_u15 += 1
            if htg == 0:
                ht_00 += 1
            if ft_ready and fthg is not None and ftag is not None:
                ft_goals_for_ht += int(fthg) + int(ftag)

    matches_total = len(rows)
    competitions_count = len(competitions_set)
    seasons_count = len(seasons_set)

    # Rollup issues onto leagues by dataset ids
    for comp_name, dids in comp_dataset_ids.items():
        lg = leagues[comp_name]
        for did in dids:
            lg.errors += ds_err.get(did, 0)
            lg.warnings += ds_warn.get(did, 0)

    def _outcome_payload(acc: _OutcomeAcc, denom: int) -> dict[str, Any]:
        profit, roi, n = flat_roi_from_results(acc.profits)
        avg_odds = _r2(acc.odds_sum / acc.odds_n) if acc.odds_n else None
        return {
            **build_metric(acc.count, denom, sample_size=n),
            "average_bet365_pre_odds": avg_odds,
            "flat_profit_units": profit,
            "flat_roi_pct": roi,
        }

    outcomes_payload = {
        "home": _outcome_payload(outcomes["home"], ft_n),
        "draw": _outcome_payload(outcomes["draw"], ft_n),
        "away": _outcome_payload(outcomes["away"], ft_n),
    }

    def _goal_metric(count: int) -> dict[str, Any]:
        return build_metric(count, ft_n, sample_size=ft_n)

    over_profit, over_roi, over_n = flat_roi_from_results(over_profits)
    under_profit, under_roi, under_n = flat_roi_from_results(under_profits)

    goals_payload = {
        "over_15": _goal_metric(over_15),
        "over_25": {
            **_goal_metric(over_25),
            "average_bet365_pre_odds": _r2(over_odds_sum / over_odds_n) if over_odds_n else None,
            "flat_profit_units": over_profit,
            "flat_roi_pct": over_roi,
            "sample_size": over_n,
        },
        "under_25": {
            **_goal_metric(under_25),
            "average_bet365_pre_odds": _r2(under_odds_sum / under_odds_n) if under_odds_n else None,
            "flat_profit_units": under_profit,
            "flat_roi_pct": under_roi,
            "sample_size": under_n,
        },
        "under_35": _goal_metric(under_35),
        "btts_yes": _goal_metric(btts_yes),
        "btts_no": _goal_metric(btts_no),
        "score_0_0": _goal_metric(score_00),
        "team_blank": _goal_metric(team_blank),
        "goals_ge_4": _goal_metric(ge4),
        "goals_ge_5": _goal_metric(ge5),
    }

    first_half = {
        "draw": build_metric(ht_draw, ht_n, sample_size=ht_n),
        "over_05": build_metric(ht_o05, ht_n, sample_size=ht_n),
        "over_15": build_metric(ht_o15, ht_n, sample_size=ht_n),
        "under_15": build_metric(ht_u15, ht_n, sample_size=ht_n),
        "score_0_0": build_metric(ht_00, ht_n, sample_size=ht_n),
        "average_goals": _r2(ht_goals_sum / ht_n) if ht_n else None,
        "pct_of_ft_goals": _r1(100.0 * ht_goals_sum / ft_goals_for_ht) if ft_goals_for_ht > 0 else None,
        "sample_size": ht_n,
    }

    fav_hit = _r1(100.0 * fav_wins / fav_unique) if fav_unique else None
    buckets = []
    for key, _, _ in FAVORITE_BUCKETS:
        st = bucket_stats[key]
        m = st["matches"]
        if m == 0:
            buckets.append(
                {
                    "bucket": key,
                    "matches": 0,
                    "average_odds": None,
                    "normalized_implied_probability": None,
                    "actual_win_rate": None,
                    "calibration_gap_pp": None,
                }
            )
            continue
        avg_odds = st["odds_sum"] / m
        avg_implied = st["implied_sum"] / m
        actual = st["wins"] / m
        buckets.append(
            {
                "bucket": key,
                "matches": m,
                "average_odds": _r2(avg_odds),
                "normalized_implied_probability": _r2(avg_implied * 100.0),  # as %
                "actual_win_rate": _r1(actual * 100.0),
                "calibration_gap_pp": _r1((actual - avg_implied) * 100.0),
            }
        )

    favorite_payload = {
        "unique_count": fav_unique,
        "wins": fav_wins,
        "losses": fav_unique - fav_wins,
        "hit_rate": fav_hit,
        "average_odds": _r2(fav_odds_sum / fav_unique) if fav_unique else None,
        "home_favorite_pct": _r1(100.0 * fav_home / fav_unique) if fav_unique else None,
        "away_favorite_pct": _r1(100.0 * fav_away / fav_unique) if fav_unique else None,
        "draw_favorite_pct": _r1(100.0 * fav_draw / fav_unique) if fav_unique else None,
        "buckets": buckets,
    }

    avg_pre_m = _r1(sum(pre_margins) / len(pre_margins)) if pre_margins else None
    med_pre_m = _r1(float(median(pre_margins))) if pre_margins else None
    avg_cl_m = _r1(sum(closing_margins) / len(closing_margins)) if closing_margins else None
    med_cl_m = _r1(float(median(closing_margins))) if closing_margins else None
    delta_m = None
    if avg_pre_m is not None and avg_cl_m is not None:
        delta_m = _r1(avg_cl_m - avg_pre_m)

    margins_by_comp = []
    for cname, vals in sorted(margin_by_comp.items()):
        margins_by_comp.append(
            {
                "competition_name": cname,
                "average_pre_closing_margin_pct": _r1(sum(vals) / len(vals)),
                "sample_size": len(vals),
            }
        )

    margins_payload = {
        "average_pre_closing_margin_pct": avg_pre_m,
        "median_pre_closing_margin_pct": med_pre_m,
        "average_closing_margin_pct": avg_cl_m,
        "median_closing_margin_pct": med_cl_m,
        "average_pre_to_closing_delta_pp": delta_m,
        "by_competition": margins_by_comp,
        "sample_size_pre": len(pre_margins),
        "sample_size_closing": len(closing_margins),
    }

    distribution = [
        {"bucket": k, "count": mov_dist[k], "percentage": _r1(100.0 * mov_dist[k] / mov_sample) if mov_sample else None}
        for k, _, _ in MOVEMENT_BUCKETS
    ]
    odds_movement = {
        "average_home_movement_pct": _r2(sum(mov_home) / len(mov_home)) if mov_home else None,
        "average_draw_movement_pct": _r2(sum(mov_draw) / len(mov_draw)) if mov_draw else None,
        "average_away_movement_pct": _r2(sum(mov_away) / len(mov_away)) if mov_away else None,
        "favorite_shortened_pct": _r1(100.0 * fav_shortened_n / fav_mov_n) if fav_mov_n else None,
        "winning_selection_shortened_pct": _r1(100.0 * win_shortened_n / win_mov_n) if win_mov_n else None,
        "average_winner_movement_pct": _r2(sum(winner_movs) / len(winner_movs)) if winner_movs else None,
        "sample_size": mov_sample,
        "distribution": distribution,
    }

    top_long_comp = None
    best_long_pct = -1.0
    for cname, (hits, elig) in longest_by_comp.items():
        if elig < 100:
            continue
        pct = 100.0 * hits / elig
        if pct > best_long_pct:
            best_long_pct = pct
            top_long_comp = {"competition_name": cname, "percentage": _r1(pct), "sample_size": elig}

    longest_odds_hit = {
        "count": longest_hits,
        "percentage": _r1(100.0 * longest_hits / longest_eligible) if longest_eligible else None,
        "average_winning_odds": _r2(longest_odds_sum / longest_hits) if longest_hits else None,
        "top_competition": top_long_comp,
        "record_match": record_match,
        "sample_size": longest_eligible,
    }

    # League rows
    league_rows: list[dict[str, Any]] = []
    for lg in sorted(leagues.values(), key=lambda x: x.competition_name):
        n = lg.matches
        ft_denom = lg.home + lg.draw + lg.away
        hp, hr, _ = flat_roi_from_results(lg.home_profits)
        dp, dr, _ = flat_roi_from_results(lg.draw_profits)
        ap, ar, _ = flat_roi_from_results(lg.away_profits)
        op, oroi, _ = flat_roi_from_results(lg.over_profits)
        up, uroi, _ = flat_roi_from_results(lg.under_profits)
        league_rows.append(
            {
                "competition_name": lg.competition_name,
                "country": lg.country,
                "matches": n,
                "home_win_pct": _r1(100.0 * lg.home / ft_denom) if ft_denom else None,
                "draw_pct": _r1(100.0 * lg.draw / ft_denom) if ft_denom else None,
                "away_win_pct": _r1(100.0 * lg.away / ft_denom) if ft_denom else None,
                "over_25_pct": _r1(100.0 * lg.over_25 / ft_denom) if ft_denom else None,
                "under_25_pct": _r1(100.0 * lg.under_25 / ft_denom) if ft_denom else None,
                "btts_pct": _r1(100.0 * lg.btts / ft_denom) if ft_denom else None,
                "average_goals": _r2(lg.goals_sum / lg.goals_n) if lg.goals_n else None,
                "first_half_draw_pct": _r1(100.0 * lg.ht_draw / lg.ht_n) if lg.ht_n else None,
                "favorite_hit_pct": _r1(100.0 * lg.fav_wins / lg.fav_unique) if lg.fav_unique else None,
                "average_pre_margin_pct": _r1(lg.margin_sum / lg.margin_n) if lg.margin_n else None,
                "roi_home_pct": hr,
                "roi_draw_pct": dr,
                "roi_away_pct": ar,
                "roi_over_25_pct": oroi,
                "roi_under_25_pct": uroi,
                "warnings_count": lg.warnings,
                "errors_count": lg.errors,
            }
        )

    # Best flat ROI market for summary / insights
    roi_markets = [
        ("1 (casa)", outcomes_payload["home"]["flat_roi_pct"], outcomes_payload["home"]["sample_size"]),
        ("X (pareggio)", outcomes_payload["draw"]["flat_roi_pct"], outcomes_payload["draw"]["sample_size"]),
        ("2 (trasferta)", outcomes_payload["away"]["flat_roi_pct"], outcomes_payload["away"]["sample_size"]),
        ("Over 2.5", over_roi, over_n),
        ("Under 2.5", under_roi, under_n),
    ]
    best_roi = None
    for label, roi, n in roi_markets:
        if roi is None or not n:
            continue
        if best_roi is None or roi > best_roi["roi"]:
            best_roi = {"label": label, "roi": roi, "sample_size": n}

    coverage_pct = _r1(100.0 * with_1x2 / matches_total) if matches_total else None
    completeness_pct = _r1(100.0 * complete_n / matches_total) if matches_total else None

    summary = {
        "matches_total": matches_total,
        "competitions_count": competitions_count,
        "seasons_count": seasons_count,
        "total_goals": total_goals,
        "average_goals_per_match": _r2(total_goals / ft_n) if ft_n else None,
        "average_home_goals": _r2(home_goals_sum / ft_n) if ft_n else None,
        "average_away_goals": _r2(away_goals_sum / ft_n) if ft_n else None,
        "favorite_hit_rate": fav_hit,
        "bet365_1x2_coverage_pct": coverage_pct,
        "anomalies_errors": anomalies_errors,
        "anomalies_warnings": anomalies_warnings,
        "completeness_pct": completeness_pct,
        "best_flat_roi": best_roi,
        "average_pre_closing_margin_pct": avg_pre_m,
    }

    insights = _build_insights(
        league_rows=league_rows,
        outcomes=outcomes_payload,
        over_roi=over_roi,
        under_roi=under_roi,
        over_n=over_n,
        under_n=under_n,
        longest=longest_odds_hit,
        odds_movement=odds_movement,
        margins=margins_payload,
        best_roi=best_roi,
    )

    return {
        "available_filters": available,
        "applied_filters": applied,
        "sample": {
            "matches_total": matches_total,
            "competitions_count": competitions_count,
            "seasons_count": seasons_count,
        },
        "summary": summary,
        "outcomes_1x2": outcomes_payload,
        "goals": goals_payload,
        "first_half": first_half,
        "favorite": favorite_payload,
        "margins": margins_payload,
        "odds_movement": odds_movement,
        "longest_odds_hit": longest_odds_hit,
        "leagues": league_rows,
        "insights": insights,
        "is_empty": False,
    }


def _build_insights(
    *,
    league_rows: list[dict[str, Any]],
    outcomes: dict[str, Any],
    over_roi: float | None,
    under_roi: float | None,
    over_n: int,
    under_n: int,
    longest: dict[str, Any],
    odds_movement: dict[str, Any],
    margins: dict[str, Any],
    best_roi: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    eligible = [r for r in league_rows if r["matches"] >= 100]
    insights: list[dict[str, Any]] = []

    def add(
        key: str,
        title: str,
        value: str,
        description: str,
        *,
        competition_name: str | None = None,
        sample_size: int,
        tone: str,
    ) -> None:
        if len(insights) >= 8:
            return
        insights.append(
            {
                "key": key,
                "title": title,
                "value": value,
                "description": description,
                "competition_name": competition_name,
                "sample_size": sample_size,
                "tone": tone,
            }
        )

    def pick(metric: str, *, reverse: bool = True) -> dict[str, Any] | None:
        pool = [r for r in eligible if r.get(metric) is not None]
        if not pool:
            return None
        return sorted(pool, key=lambda r: r[metric], reverse=reverse)[0]

    r = pick("home_win_pct")
    if r:
        add(
            "most_home_wins",
            "Più vittorie casa",
            f"{r['home_win_pct']}%",
            f"Storicamente, nel campione selezionato, {r['competition_name']} ha la quota più alta di vittorie interne.",
            competition_name=r["competition_name"],
            sample_size=r["matches"],
            tone="accent",
        )
    r = pick("draw_pct")
    if r:
        add(
            "most_draws",
            "Più pareggi",
            f"{r['draw_pct']}%",
            f"Nel periodo analizzato, {r['competition_name']} registra la percentuale di pareggi più elevata.",
            competition_name=r["competition_name"],
            sample_size=r["matches"],
            tone="neutral",
        )
    r = pick("away_win_pct")
    if r:
        add(
            "most_away_wins",
            "Più vittorie trasferta",
            f"{r['away_win_pct']}%",
            f"Storicamente, {r['competition_name']} mostra la maggiore frequenza di vittorie in trasferta.",
            competition_name=r["competition_name"],
            sample_size=r["matches"],
            tone="accent",
        )
    r = pick("over_25_pct")
    if r:
        add(
            "most_over_25",
            "Più Over 2.5",
            f"{r['over_25_pct']}%",
            f"Nel periodo analizzato, {r['competition_name']} è il campionato con più partite Over 2.5.",
            competition_name=r["competition_name"],
            sample_size=r["matches"],
            tone="positive",
        )
    r = pick("under_25_pct")
    if r and len(insights) < 8:
        add(
            "most_under_25",
            "Più Under 2.5",
            f"{r['under_25_pct']}%",
            f"Storicamente, {r['competition_name']} concentra la maggiore quota di Under 2.5.",
            competition_name=r["competition_name"],
            sample_size=r["matches"],
            tone="neutral",
        )
    r = pick("average_goals")
    if r and len(insights) < 8:
        add(
            "highest_avg_goals",
            "Goal medi più alti",
            f"{r['average_goals']}",
            f"Nel periodo analizzato, {r['competition_name']} ha la media goal più elevata.",
            competition_name=r["competition_name"],
            sample_size=r["matches"],
            tone="positive",
        )
    r = pick("average_goals", reverse=False)
    if r and len(insights) < 8:
        add(
            "lowest_avg_goals",
            "Goal medi più bassi",
            f"{r['average_goals']}",
            f"Storicamente, {r['competition_name']} è il campionato con media goal più contenuta.",
            competition_name=r["competition_name"],
            sample_size=r["matches"],
            tone="warning",
        )
    r = pick("favorite_hit_pct")
    if r and len(insights) < 8:
        add(
            "most_reliable_favorite",
            "Favorita più affidabile",
            f"{r['favorite_hit_pct']}%",
            f"Nel periodo analizzato, la favorita Bet365 ha centrato più spesso in {r['competition_name']}.",
            competition_name=r["competition_name"],
            sample_size=r["matches"],
            tone="positive",
        )
    r = pick("average_pre_margin_pct", reverse=False)
    if r and len(insights) < 8:
        add(
            "lowest_margin",
            "Margine Bet365 più basso",
            f"{r['average_pre_margin_pct']}%",
            f"Storicamente, {r['competition_name']} presenta il margine pre-closing medio più contenuto (non implica profitto).",
            competition_name=r["competition_name"],
            sample_size=r["matches"],
            tone="neutral",
        )

    if best_roi and len(insights) < 8:
        add(
            "best_flat_roi",
            "Miglior ROI flat storico",
            f"{best_roi['roi']}% · {best_roi['label']}",
            "Nel periodo analizzato, questo è il mercato flat 1u con ROI storico migliore. Non è una strategia futura.",
            sample_size=int(best_roi["sample_size"]),
            tone="positive" if best_roi["roi"] >= 0 else "warning",
        )

    if longest.get("count") and longest.get("percentage") is not None and len(insights) < 8:
        add(
            "longest_odds_hit",
            "Esito più quotato centrato",
            f"{longest['percentage']}%",
            "Storicamente, la selezione con quota pre-closing più alta (univoca) ha coinciso con il risultato FT in questa percentuale del campione.",
            competition_name=(longest.get("top_competition") or {}).get("competition_name"),
            sample_size=int(longest.get("sample_size") or 0),
            tone="accent",
        )

    if odds_movement.get("average_winner_movement_pct") is not None and len(insights) < 8:
        mov = odds_movement["average_winner_movement_pct"]
        add(
            "winner_movement",
            "Variazione pre → closing sul vincente",
            f"{mov:+.2f}%",
            "Nel periodo analizzato, movimento medio della quota Bet365 dell’esito effettivamente vincente (pre-closing → closing).",
            sample_size=int(odds_movement.get("sample_size") or 0),
            tone="neutral",
        )

    return insights[:8]
