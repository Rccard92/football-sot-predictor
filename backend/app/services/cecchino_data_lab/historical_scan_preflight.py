"""Preflight stagione per scansione storica Cecchino Lab (read-only)."""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.cecchino_lab_dataset import CecchinoLabDataset
from app.models.cecchino_lab_match import CecchinoLabMatch
from app.services.cecchino.cecchino_market_opposition import PANEL_MARKET_KEYS
from app.services.cecchino_data_lab.historical_bet365_adapter import (
    DERIVABLE_MARKETS,
    NON_DERIVABLE_MARKETS,
    REAL_BOOK_MARKETS,
    build_match_quote_bundle,
)

STATUS_READY = "ready"
STATUS_READY_WITH_WARNINGS = "ready_with_warnings"
STATUS_BLOCKED = "blocked"


def _sort_key(m: CecchinoLabMatch) -> tuple:
    return (
        m.kickoff_at is None,
        m.kickoff_at or 0,
        m.match_date is None,
        m.match_date or 0,
        m.match_time is None,
        str(m.match_time) if m.match_time else "",
        int(m.source_row_number or 0),
        int(m.id),
    )


def run_historical_scan_preflight(db: Session, *, season_label: str) -> dict[str, Any]:
    """Analizza dataset della stagione senza scritture."""
    datasets = list(
        db.scalars(
            select(CecchinoLabDataset).where(CecchinoLabDataset.season_label == season_label)
        ).all()
    )
    blocking: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []

    if not datasets:
        return {
            "season_label": season_label,
            "status": STATUS_BLOCKED,
            "datasets_found": [],
            "competitions_found": [],
            "matches_total": 0,
            "blocking_anomalies": [
                {
                    "code": "no_datasets",
                    "message": f"Nessun dataset per la stagione {season_label}",
                }
            ],
            "warnings": [],
            "module_availability": {},
            "market_availability": {},
            "quote_counts": {
                "real": 0,
                "derived": 0,
                "not_available": 0,
            },
        }

    dataset_ids = [int(d.id) for d in datasets]
    matches = list(
        db.scalars(
            select(CecchinoLabMatch).where(CecchinoLabMatch.dataset_id.in_(dataset_ids))
        ).all()
    )

    ds_by_id = {int(d.id): d for d in datasets}
    competitions = sorted({d.competition_name for d in datasets})

    with_kickoff = 0
    with_ft = 0
    with_ht = 0
    missing_teams = 0
    missing_dates = 0
    bet365_1x2_pre = 0
    bet365_1x2_closing = 0
    bet365_ou_pre = 0
    bet365_ou_closing = 0
    real_quotes = 0
    derived_quotes = 0
    unavailable_quotes = 0
    ambiguous_identity = 0
    teams_by_comp: dict[str, set[str]] = defaultdict(set)
    identity_keys: Counter[str] = Counter()
    sortable = 0

    for m in matches:
        ds = ds_by_id.get(int(m.dataset_id))
        comp = ds.competition_name if ds else "?"
        if m.kickoff_at is not None:
            with_kickoff += 1
        if m.ft_home_goals is not None and m.ft_away_goals is not None:
            with_ft += 1
        if m.ht_home_goals is not None and m.ht_away_goals is not None:
            with_ht += 1
        if not (m.home_team and m.away_team):
            missing_teams += 1
        if m.match_date is None and m.kickoff_at is None:
            missing_dates += 1
        if m.bet365_1x2_pre_ready:
            bet365_1x2_pre += 1
        if m.bet365_1x2_closing_ready:
            bet365_1x2_closing += 1
        if m.bet365_ou25_pre_ready:
            bet365_ou_pre += 1
        if m.bet365_ou25_closing_ready:
            bet365_ou_closing += 1

        if m.home_team:
            teams_by_comp[comp].add(m.home_team)
        if m.away_team:
            teams_by_comp[comp].add(m.away_team)

        if m.home_team and m.away_team and (m.kickoff_at or m.match_date):
            ik = f"{comp}|{m.match_date}|{m.home_team}|{m.away_team}"
            identity_keys[ik] += 1
            sortable += 1
        else:
            ambiguous_identity += 1

        bundle = build_match_quote_bundle(m)
        real_quotes += int(bundle["counts"]["real_quote_markets_count"])
        derived_quotes += int(bundle["counts"]["derived_quote_markets_count"])
        unavailable_quotes += int(bundle["counts"]["unavailable_quote_markets_count"])

    duplicates = sum(1 for c in identity_keys.values() if c > 1)
    potential_dup_rows = sum(c for c in identity_keys.values() if c > 1)

    if len(matches) == 0:
        blocking.append(
            {"code": "no_matches", "message": "Nessuna partita nei dataset della stagione"}
        )
    if with_kickoff == 0 and sortable == 0:
        blocking.append(
            {
                "code": "not_orderable",
                "message": "Impossibile ordinare cronologicamente i record",
            }
        )
    if len(matches) > 0 and ambiguous_identity / max(len(matches), 1) > 0.25:
        blocking.append(
            {
                "code": "ambiguous_identity_rate",
                "message": "Identità partita ambigua su una quota significativa (>25%)",
            }
        )

    if missing_teams:
        warnings.append(
            {
                "code": "missing_teams",
                "message": f"{missing_teams} righe con squadre mancanti (escluse per reason code)",
            }
        )
    if missing_dates:
        warnings.append(
            {
                "code": "missing_dates",
                "message": f"{missing_dates} righe senza data/kickoff",
            }
        )
    if duplicates:
        warnings.append(
            {
                "code": "potential_duplicates",
                "message": f"{duplicates} chiavi identità duplicate ({potential_dup_rows} righe)",
            }
        )
    if with_ft < len(matches):
        warnings.append(
            {
                "code": "partial_ft",
                "message": f"FT disponibile su {with_ft}/{len(matches)} partite",
            }
        )

    n = max(len(matches), 1)
    market_availability = {}
    for mk in PANEL_MARKET_KEYS:
        if mk in REAL_BOOK_MARKETS:
            if mk in ( "HOME", "DRAW", "AWAY"):
                cov = max(bet365_1x2_pre, bet365_1x2_closing)
            else:
                cov = max(bet365_ou_pre, bet365_ou_closing)
            market_availability[mk] = {
                "status": "real_quote_expected" if cov > 0 else "often_unavailable",
                "expected_coverage_pct": round(100.0 * cov / n, 1),
            }
        elif mk in DERIVABLE_MARKETS:
            cov = max(bet365_1x2_pre, bet365_1x2_closing)
            market_availability[mk] = {
                "status": "derived_from_1x2_expected" if cov > 0 else "often_unavailable",
                "expected_coverage_pct": round(100.0 * cov / n, 1),
            }
        else:
            market_availability[mk] = {
                "status": "not_derivable",
                "expected_coverage_pct": 0.0,
            }

    module_availability = {
        "cecchino_engine": {
            "status": "available" if with_kickoff > 0 else "blocked",
            "note": "Richiede campioni minimi; prime giornate escluse",
        },
        "kpi_bet365": {
            "status": "available" if max(bet365_1x2_pre, bet365_1x2_closing) > 0 else "partial",
        },
        "signals": {"status": "available"},
        "balance_v5": {"status": "available"},
        "goal_intensity_v5": {
            "status": "historical_partial",
            "note": "cecchino_lab_goal_intensity_historical_v1 parity_partial",
        },
        "purchasability": {
            "status": "historical_bet365_progressive",
            "note": "cecchino_lab_purchasability_historical_v1 observational",
        },
        "signal_models": {
            "status": "available",
            "note": "models_A_F default_F",
        },
        "settlement_14_markets": {
            "status": "available" if with_ft > 0 else "partial",
        },
    }

    if blocking:
        status = STATUS_BLOCKED
    elif warnings:
        status = STATUS_READY_WITH_WARNINGS
    else:
        status = STATUS_READY

    # Verifica ordinabilità deterministica
    try:
        sorted(matches, key=_sort_key)
        orderable = True
    except Exception:
        orderable = False
        blocking.append(
            {"code": "sort_failed", "message": "Ordinamento deterministico fallito"}
        )
        status = STATUS_BLOCKED

    return {
        "season_label": season_label,
        "status": status,
        "datasets_found": [
            {
                "id": int(d.id),
                "dataset_key": d.dataset_key,
                "competition_name": d.competition_name,
                "country": d.country,
                "matches_count": int(d.matches_count or 0),
                "data_quality_status": d.data_quality_status,
            }
            for d in datasets
        ],
        "competitions_found": competitions,
        "matches_total": len(matches),
        "matches_with_valid_kickoff": with_kickoff,
        "matches_with_ft": with_ft,
        "matches_with_ht": with_ht,
        "bet365_1x2_pre_coverage": bet365_1x2_pre,
        "bet365_1x2_closing_coverage": bet365_1x2_closing,
        "bet365_ou25_pre_coverage": bet365_ou_pre,
        "bet365_ou25_closing_coverage": bet365_ou_closing,
        "rows_missing_teams": missing_teams,
        "rows_missing_dates": missing_dates,
        "duplicate_or_potential_duplicate_keys": duplicates,
        "duplicate_row_count": potential_dup_rows,
        "ambiguous_match_identities": ambiguous_identity,
        "distinct_teams_by_competition": {
            k: len(v) for k, v in sorted(teams_by_comp.items())
        },
        "matches_orderable_deterministically": orderable and sortable > 0,
        "blocking_anomalies": blocking,
        "warnings": warnings,
        "module_availability": module_availability,
        "market_availability": market_availability,
        "quote_counts": {
            "real": real_quotes,
            "derived": derived_quotes,
            "not_available": unavailable_quotes,
        },
        "real_book_markets": sorted(REAL_BOOK_MARKETS),
        "derivable_markets": sorted(DERIVABLE_MARKETS),
        "non_derivable_markets": sorted(NON_DERIVABLE_MARKETS),
    }
