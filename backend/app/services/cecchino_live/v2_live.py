"""Moduli V2 sulle partite del giorno, calcolati come nella RUN V2 (per accendere i Pattern Master V2).

Stessi passaggi di `run_v2/executor._process_one_match`, stesse funzioni, nessuna formula nuova.
Differenze dichiarate rispetto alla RUN storica:
- lo storico e' quello della competizione e stagione nel database live (tabella fixtures);
- le quote sono quelle reali Bet365 del pannello KPI di Cecchino Today, messe nelle stesse colonne
  che la RUN V2 legge dal Lab (bet365_*);
- i percentili dell'Intensita' Goal usano le partite eleggibili dell'ultima RUN V2 completata
  (stagione 2025/26 intera), congelati all'avvio: nella RUN erano progressivi dentro la stagione.
"""

from __future__ import annotations

import threading
from datetime import datetime
from types import SimpleNamespace
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models import Competition, Fixture
from app.services.cecchino.cecchino_constants import PICCHETTO_KEY_HOME_AWAY
from app.services.cecchino_data_lab.historical_context_builder import (
    build_input_snapshot,
    build_lab_prematch_contexts,
    compute_cecchino_from_contexts,
    compute_goal_markets_from_contexts,
    prior_proxies_strict,
)
from app.services.cecchino_data_lab.historical_eligibility import ELIGIBLE_CORE, evaluate_historical_eligibility
from app.services.cecchino_data_lab.historical_goal_intensity import (
    MIN_ECDF_TRAIN_N,
    build_historical_goal_intensity,
    fit_progressive_ecdfs,
)
from app.services.cecchino_data_lab.historical_modules_compat import (
    build_historical_balance_v5,
    rebuild_signals_with_under,
)
from app.services.cecchino_data_lab.historical_signal_extraction import build_market_signal_index
from app.services.cecchino_data_lab.historical_signal_models import build_historical_signal_models
from app.services.cecchino_data_lab.run_v2.constants import CORE_MARKETS, RUN_V2_VERSION
from app.services.cecchino_data_lab.run_v2.goal_markets_ext import compute_ht_1x2_markets, compute_ou_05_markets
from app.services.cecchino_data_lab.run_v2.kpi_panel_v2 import build_run_v2_kpi_panel
from app.services.cecchino_data_lab.run_v2.quotes import build_run_v2_quote_bundle
from app.services.cecchino_live.v25_live import _proxy, history_for, strict_quotes_from_kpi

MODULE_VERSION = "cecchino_live_v2_modules_v1"

# colonne "chiusura" lette dall'adapter legacy per 1X2 e O/U 2.5
_CLOSING_COLUMNS = {
    "HOME": "bet365_closing_home",
    "DRAW": "bet365_closing_draw",
    "AWAY": "bet365_closing_away",
    "OVER_2_5": "bet365_closing_over_25",
    "UNDER_2_5": "bet365_closing_under_25",
}

_gi_cache: dict[str, Any] | None = None
_gi_lock = threading.Lock()


def frozen_gi_training(db: Session) -> dict[str, Any]:
    """Righe di profilo Intensita' Goal delle partite eleggibili dell'ultima RUN V2 completata."""
    global _gi_cache
    with _gi_lock:
        if _gi_cache is not None:
            return _gi_cache
        run_id = db.execute(
            text(
                """
                SELECT id FROM cecchino_run_v2_runs
                WHERE run_version = :v AND status IN ('completed', 'completed_with_warnings')
                ORDER BY module_policy_json->>'season_label' DESC NULLS LAST, id DESC
                LIMIT 1
                """
            ),
            {"v": RUN_V2_VERSION},
        ).scalar()
        rows: list[dict[str, Any]] = []
        if run_id is not None:
            for (row,) in db.execute(
                text(
                    """
                    SELECT goal_intensity_json->'feature_row_for_profile'
                    FROM cecchino_run_v2_match_snapshots
                    WHERE run_id = :rid AND eligibility_status = :elig
                    """
                ),
                {"rid": int(run_id), "elig": ELIGIBLE_CORE},
            ):
                if isinstance(row, dict) and isinstance(row.get("features"), dict):
                    rows.append(row)
        _gi_cache = {"run_id": run_id, "rows": rows, "ecdfs": fit_progressive_ecdfs(rows) if rows else None}
        return _gi_cache


def quote_match_proxy(target: Fixture, kpi_panel: dict[str, Any] | None) -> SimpleNamespace:
    """Oggetto con le colonne bet365_* che la RUN V2 legge dal Lab, riempite con le quote reali di Today."""
    strict = strict_quotes_from_kpi(kpi_panel)
    attrs: dict[str, Any] = {
        "id": int(target.id),
        "kickoff_at": target.kickoff_at,
        "match_date": target.kickoff_at.date() if target.kickoff_at else None,
        "home_team": str(target.home_team_id),
        "away_team": str(target.away_team_id),
        "referee": target.referee,
    }
    for market in CORE_MARKETS:
        entry = strict.get(market.key) or {}
        value = entry.get("value")
        if value is None or entry.get("is_derived"):
            continue
        for col in market.strict_quote_columns or ():
            attrs[col] = float(value)
        if market.key in _CLOSING_COLUMNS:
            attrs[_CLOSING_COLUMNS[market.key]] = float(value)
    return SimpleNamespace(**attrs)


def compute_v2_live(db: Session, target: Fixture, kpi_panel: dict[str, Any] | None) -> dict[str, Any]:
    history = history_for(db, target)
    target_proxy = _proxy(target)
    ordered = sorted(history + [target_proxy], key=lambda p: (p.kickoff_at or datetime.min, p.id))
    contexts = build_lab_prematch_contexts(competition_ordered=ordered, target=target_proxy)
    priors = prior_proxies_strict(ordered, target_proxy)

    cecchino_output = compute_cecchino_from_contexts(contexts)
    goal_markets = compute_goal_markets_from_contexts(contexts)
    under_odd = None
    under_block = (goal_markets or {}).get("UNDER_2_5") or {}
    if under_block.get("final_odd") is not None:
        under_odd = float(under_block["final_odd"])
        meta = contexts.sample_meta.get(PICCHETTO_KEY_HOME_AWAY) or {}
        sample_split = int(meta.get("home_sample_count") or 0) + int(meta.get("away_sample_count") or 0)
        cecchino_output["signals_matrix"] = rebuild_signals_with_under(
            final=cecchino_output.get("final") or {},
            sample_home_away_split=sample_split,
            under_2_5_cecchino_odd=under_odd,
        )
    ou_05_markets = compute_ou_05_markets(contexts, priors)
    ht_1x2_markets = compute_ht_1x2_markets(contexts, priors)

    match = quote_match_proxy(target, kpi_panel)
    quote_bundle = build_run_v2_quote_bundle(match)
    final = cecchino_output.get("final") or {}
    kpi = build_run_v2_kpi_panel(
        final_odds=final,
        match=match,
        goal_markets=goal_markets,
        ou_05_markets=ou_05_markets,
        ht_1x2_markets=ht_1x2_markets,
        quote_bundle=quote_bundle,
    )
    comp = db.get(Competition, int(target.competition_id)) if target.competition_id else None
    balance = build_historical_balance_v5(
        cecchino_final=final,
        goal_markets=goal_markets,
        kpi_panel=kpi,
        identity={
            "home_team": match.home_team,
            "away_team": match.away_team,
            "competition": comp.name if comp else None,
            "season_label": str(comp.season) if comp else None,
        },
    )
    training = frozen_gi_training(db)
    gi_payload = build_historical_goal_intensity(
        input_snapshot=build_input_snapshot(contexts),
        contexts=contexts,
        competition_ordered=ordered,
        target=target_proxy,
        prior_feature_rows=training["rows"],
        prefitted_ecdfs=training["ecdfs"] if len(training["rows"]) >= MIN_ECDF_TRAIN_N else None,
    )
    signals = build_historical_signal_models(
        cecchino_output=cecchino_output,
        quote_bundle=quote_bundle["strict_v1_bundle"],
        under_2_5_cecchino_odd=under_odd,
        contexts=contexts,
        match=None,
        settle=False,
    )
    signal_index = build_market_signal_index(signals)
    elig = evaluate_historical_eligibility(
        home_team=match.home_team,
        away_team=match.away_team,
        kickoff_at=target.kickoff_at,
        contexts=contexts,
        cecchino_output=cecchino_output,
    )
    return {
        "kpi": kpi,
        "balance": balance,
        "gi": gi_payload,
        "signal_index": signal_index,
        "eligibility": elig,
        "history_matches": len(history),
        "gi_training": {"run_id": training["run_id"], "rows": len(training["rows"])},
    }


def v2_modules(pre: dict[str, Any]) -> dict[str, Any]:
    gi = pre["gi"] or {}
    balance = pre["balance"] or {}
    return {
        "module_version": MODULE_VERSION,
        "goal_intensity_classes": {k: (v or {}).get("class_key") for k, v in (gi.get("pillars") or {}).items()},
        "goal_intensity_final": (gi.get("final_class") or {}).get("key"),
        # dettaglio per la scheda V2 (stessi valori che leggono i pattern) — solo lettura
        "goal_intensity_pillars": {
            k: {f: (v or {}).get(f) for f in ("score", "raw_value", "class_key", "label")}
            for k, v in (gi.get("pillars") or {}).items()
        },
        "goal_intensity_final_detail": gi.get("final_class"),
        "balance_classes": balance.get("pillar_classes") or {},
        "signal_markets": sorted(k for k, v in (pre.get("signal_index") or {}).items() if (v or {}).get("signal_active")),
        "eligibility": (pre.get("eligibility") or {}).get("status"),
        "history_matches": pre.get("history_matches"),
        "gi_training": pre.get("gi_training"),
    }


def v2_pattern_signals(
    db: Session, fixture: Fixture, markets: dict[str, Any], modules: dict[str, Any]
) -> dict[str, Any]:
    """Pattern Master V2 accesi: stesse colonne della ricerca V2 (moduli V2 + statistiche squadra)."""
    from app.services.cecchino_live.live_extra_stats import delta_classes, live_extra_features
    from app.services.cecchino_live.pattern_signals import evaluate_patterns, load_winners, v25_features

    build_id, patterns, discovery_run = load_winners(db, "V2")
    if build_id is None or discovery_run is None:
        return {"status": "master_pattern_missing"}
    active_signals = set(modules.get("signal_markets") or [])
    markets_with_signals = {
        k: {**(v or {}), "signal_active": k in active_signals, "buyability_class": None} for k, v in markets.items()
    }
    extra = live_extra_features(db, fixture)
    delta = delta_classes(extra, discovery_run_id=discovery_run)
    result = evaluate_patterns(patterns, features=v25_features(modules, delta), markets=markets_with_signals)
    return {
        "status": "ok",
        "master_build_id": build_id,
        "extra_stats": {
            "prior_matches": extra.get("prior_matches"),
            "prior_matches_with_stats": extra.get("prior_matches_with_stats"),
            "delta_classes_available": sum(1 for v in delta.values() if v is not None),
        },
        **result,
    }
