from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from fastapi.encoders import jsonable_encoder
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.constants import (
    BASELINE_SOT_MODEL_VERSION,
    BASELINE_SOT_MODEL_VERSION_V02,
    BASELINE_SOT_MODEL_VERSION_V02_PLAYER_ADJUSTED,
    BASELINE_SOT_MODEL_VERSION_V03_CORE_SOT,
    BASELINE_SOT_MODEL_VERSION_V04_OFFENSIVE_CORE_SOT,
    BASELINE_SOT_MODEL_VERSION_V10_SOT,
    FINISHED_STATUSES,
)
from app.models import Fixture, League, Season, Team, TeamSotPrediction
from app.services.ingestion_service import IngestionService


PREFERRED_MODEL_ORDER: list[str] = [
    BASELINE_SOT_MODEL_VERSION_V04_OFFENSIVE_CORE_SOT,
    BASELINE_SOT_MODEL_VERSION_V10_SOT,
    BASELINE_SOT_MODEL_VERSION_V03_CORE_SOT,
    BASELINE_SOT_MODEL_VERSION_V02_PLAYER_ADJUSTED,
    BASELINE_SOT_MODEL_VERSION_V02,
    BASELINE_SOT_MODEL_VERSION,
]


def _safe_details(exc: Exception) -> str:
    msg = f"{exc.__class__.__name__}: {exc}"
    lowered = msg.lower()
    if "postgresql://" in lowered or "mysql://" in lowered or "mongodb://" in lowered:
        return f"{exc.__class__.__name__}: [redacted]"
    if "database_url" in lowered or "apikey" in lowered or "api_key" in lowered or "secret" in lowered:
        return f"{exc.__class__.__name__}: [redacted]"
    return msg[:800]


def _round2(x: float | None) -> float | None:
    if x is None:
        return None
    return round(float(x), 2)


def _label_for_status(st: str) -> str:
    return {"stable": "Stabile", "inspect": "Da controllare", "red_flag": "Red flag"}.get(st, st)


def _status_from_abs_delta(abs_delta: float) -> tuple[str, str]:
    # Regole A
    if abs_delta < 0.25:
        return "stable", "Differenza contenuta rispetto alla baseline v0.1."
    if abs_delta <= 0.50:
        return "inspect", "Differenza moderata rispetto alla baseline v0.1."
    if abs_delta <= 0.80:
        return "inspect", "Differenza rilevante rispetto alla baseline v0.1: da controllare."
    return "red_flag", "Differenza molto elevata rispetto alla baseline v0.1: red flag."


def _range_status(rng: float) -> tuple[str, str]:
    # Regola D
    if rng <= 0.40:
        return "stable", "Modelli coerenti: range contenuto."
    if rng <= 0.80:
        return "inspect", "Moderata divergenza tra modelli."
    return "red_flag", "Forte divergenza tra modelli: audit manuale consigliato."


def _max_abs(values: list[float]) -> float:
    return max(abs(v) for v in values) if values else 0.0


def _compute_range(values: list[float]) -> float | None:
    if not values:
        return None
    return float(max(values) - min(values))


def _model_prev_map(order: list[str]) -> dict[str, str | None]:
    out: dict[str, str | None] = {}
    prev: str | None = None
    for mv in order:
        out[mv] = prev
        prev = mv
    return out


def _pick_active_model_for_fixture(preds: dict[str, dict[str, float | None]]) -> str | None:
    # serve home+away presenti per lo stesso modello
    for mv in PREFERRED_MODEL_ORDER:
        row = preds.get(mv) or {}
        if row.get("home") is not None and row.get("away") is not None:
            return mv
    # fallback: qualunque modello con almeno un lato
    for mv, row in preds.items():
        if row.get("home") is not None or row.get("away") is not None:
            return mv
    return None


def _extract_v04_component(raw: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    comp = raw.get("offensive_production_component")
    if not isinstance(comp, dict):
        return None
    fallbacks = comp.get("fallbacks_used")
    return {
        "value": comp.get("value"),
        "fallbacks_used": fallbacks if isinstance(fallbacks, list) else [],
        "cap_applied": bool(comp.get("cap_applied")) if comp.get("cap_applied") is not None else None,
        "explanation": comp.get("explanation"),
    }


@dataclass(frozen=True)
class FixtureContext:
    fixture: Fixture
    home: Team
    away: Team


def load_fixture_context(db: Session, fixture_id: int, *, season: int | None = None) -> dict[str, Any]:
    fx = db.get(Fixture, int(fixture_id))
    if fx is None:
        return {
            "status": "error",
            "failed_step": "load_fixture",
            "message": "Fixture non trovata.",
            "details": f"fixture_id={int(fixture_id)}",
            "fixture_id": int(fixture_id),
        }
    if season is not None and fx.season is not None and int(fx.season.year) != int(season):
        return {
            "status": "error",
            "failed_step": "season_mismatch",
            "message": "La fixture non appartiene alla stagione richiesta.",
            "details": f"fixture_season={int(fx.season.year)} requested={int(season)}",
            "fixture_id": int(fixture_id),
        }
    home = db.get(Team, int(fx.home_team_id))
    away = db.get(Team, int(fx.away_team_id))
    if home is None or away is None:
        return {
            "status": "error",
            "failed_step": "load_teams",
            "message": "Impossibile caricare le squadre della fixture.",
            "details": f"home_team_id={int(fx.home_team_id)} away_team_id={int(fx.away_team_id)}",
            "fixture_id": int(fixture_id),
        }
    return {"status": "success", "fixture": fx, "home": home, "away": away}


def build_model_comparison_for_fixture(
    db: Session,
    fixture_id: int,
    *,
    season: int | None = None,
    include_raw: bool = False,
) -> dict[str, Any]:
    try:
        ctx = load_fixture_context(db, fixture_id, season=season)
        if ctx.get("status") != "success":
            return ctx
        fx: Fixture = ctx["fixture"]
        home: Team = ctx["home"]
        away: Team = ctx["away"]

        rows = list(
            db.scalars(select(TeamSotPrediction).where(TeamSotPrediction.fixture_id == int(fx.id))).all(),
        )

        # model_version -> {"home": x, "away": y}
        preds: dict[str, dict[str, float | None]] = {}
        raw_by: dict[tuple[str, str], dict[str, Any] | None] = {}
        for r in rows:
            mv = str(r.model_version)
            if mv not in preds:
                preds[mv] = {"home": None, "away": None}
            side = "home" if int(r.team_id) == int(fx.home_team_id) else "away" if int(r.team_id) == int(fx.away_team_id) else None
            if side is None:
                continue
            preds[mv][side] = float(r.predicted_sot) if r.predicted_sot is not None else None
            raw_by[(mv, side)] = r.raw_json if isinstance(r.raw_json, dict) else None

        available_models = sorted(list(preds.keys()), key=lambda mv: (PREFERRED_MODEL_ORDER.index(mv) if mv in PREFERRED_MODEL_ORDER else 999, mv))
        active_mv = _pick_active_model_for_fixture(preds)

        prev_map = _model_prev_map(PREFERRED_MODEL_ORDER)

        def side_series(side: str) -> list[dict[str, Any]]:
            out: list[dict[str, Any]] = []
            v01 = preds.get(BASELINE_SOT_MODEL_VERSION, {}).get(side)
            for mv in available_models:
                v = preds.get(mv, {}).get(side)
                prev = prev_map.get(mv)
                prev_v = preds.get(prev, {}).get(side) if prev else None
                item: dict[str, Any] = {
                    "model_version": mv,
                    "expected_sot": _round2(v),
                    "difference_from_v01": _round2((v - v01) if (v is not None and v01 is not None) else (0.0 if mv == BASELINE_SOT_MODEL_VERSION and v is not None else None)),
                    "difference_from_previous_version": _round2((v - prev_v) if (v is not None and prev_v is not None) else None),
                }
                if mv == BASELINE_SOT_MODEL_VERSION_V04_OFFENSIVE_CORE_SOT:
                    comp = _extract_v04_component(raw_by.get((mv, side)))
                    if comp is not None:
                        item["component_hint"] = comp if include_raw else {k: comp.get(k) for k in ("value", "fallbacks_used", "cap_applied")}
                out.append(item)
            return out

        def total_series() -> list[dict[str, Any]]:
            out: list[dict[str, Any]] = []
            v01h = preds.get(BASELINE_SOT_MODEL_VERSION, {}).get("home")
            v01a = preds.get(BASELINE_SOT_MODEL_VERSION, {}).get("away")
            v01t = (v01h + v01a) if (v01h is not None and v01a is not None) else None
            for mv in available_models:
                h = preds.get(mv, {}).get("home")
                a = preds.get(mv, {}).get("away")
                t = (h + a) if (h is not None and a is not None) else None
                out.append(
                    {
                        "model_version": mv,
                        "total_expected_sot": _round2(t),
                        "difference_from_v01": _round2((t - v01t) if (t is not None and v01t is not None) else (0.0 if mv == BASELINE_SOT_MODEL_VERSION and t is not None else None)),
                    }
                )
            return out

        home_series = side_series("home")
        away_series = side_series("away")
        match_total_series = total_series()

        # DIAGNOSTICS (principale: v0.4 vs v0.1 / v0.3 / range)
        v01_home = preds.get(BASELINE_SOT_MODEL_VERSION, {}).get("home")
        v01_away = preds.get(BASELINE_SOT_MODEL_VERSION, {}).get("away")
        v03_home = preds.get(BASELINE_SOT_MODEL_VERSION_V03_CORE_SOT, {}).get("home")
        v03_away = preds.get(BASELINE_SOT_MODEL_VERSION_V03_CORE_SOT, {}).get("away")
        v04_home = preds.get(BASELINE_SOT_MODEL_VERSION_V04_OFFENSIVE_CORE_SOT, {}).get("home")
        v04_away = preds.get(BASELINE_SOT_MODEL_VERSION_V04_OFFENSIVE_CORE_SOT, {}).get("away")

        red_flags: list[str] = []
        confidence_notes: list[str] = []

        # Component flags (E/F/G) — v0.4
        v04_home_comp = _extract_v04_component(raw_by.get((BASELINE_SOT_MODEL_VERSION_V04_OFFENSIVE_CORE_SOT, "home")))
        v04_away_comp = _extract_v04_component(raw_by.get((BASELINE_SOT_MODEL_VERSION_V04_OFFENSIVE_CORE_SOT, "away")))
        comps = {"home": v04_home_comp, "away": v04_away_comp}
        for side, comp in comps.items():
            if not comp:
                continue
            if comp.get("fallbacks_used"):
                red_flags.append("fallback usati")
                confidence_notes.append("La previsione usa fallback per dati mancanti: affidabilità ridotta.")
            if comp.get("cap_applied") is True:
                red_flags.append("cap applicato")
                confidence_notes.append("Il componente offensivo è stato cappato: verificare segnali offensivi.")

        # Team status
        def team_diag(side: str, v04: float | None, v01: float | None, v03: float | None, comp: dict[str, Any] | None) -> dict[str, Any]:
            if v04 is None or v01 is None:
                return {
                    "status": "inspect",
                    "summary": "Dati insufficienti per confronto completo (manca v0.4 o v0.1).",
                    "main_delta_driver": "offensive_production_component" if comp else None,
                    "red_flags": list(dict.fromkeys(red_flags)),
                }
            delta = float(v04 - v01)
            abs_delta = abs(delta)
            st, _ = _status_from_abs_delta(abs_delta)
            extra: list[str] = []

            # Regola B
            if v03 is not None:
                d43 = float(v04 - v03)
                if d43 <= -0.50:
                    extra.append("v0.4 molto più bassa di v0.3 (prudente)")
                elif d43 >= 0.50:
                    extra.append("v0.4 molto più alta di v0.3 (aggressiva)")

            if ("fallback usati" in red_flags) or ("cap applicato" in red_flags):
                st = "inspect" if st == "stable" else st

            if abs_delta > 0.80:
                st = "red_flag"
                extra.append("scostamento > 0.80 vs v0.1")

            # Human summary
            if st == "stable":
                summary = "La v0.4 è coerente con la baseline: differenza contenuta e nessun segnale critico."
            else:
                if delta < 0 and (v03 is not None and v04 < v03 - 0.50):
                    summary = "La v0.4 riduce sensibilmente la previsione rispetto a v0.1 e v0.3: possibile modello troppo prudente."
                elif delta > 0 and (v03 is not None and v04 > v03 + 0.50):
                    summary = "La v0.4 aumenta sensibilmente la previsione rispetto a v0.1 e v0.3: possibile modello troppo aggressivo."
                else:
                    summary = "Differenza rilevante rispetto alla baseline: partita da controllare."

            return {
                "status": "too_conservative" if any("prudente" in x for x in extra) else "too_aggressive" if any("aggressiva" in x for x in extra) else st,
                "summary": summary,
                "main_delta_driver": "offensive_production_component" if comp else None,
                "red_flags": list(dict.fromkeys(extra + red_flags)),
            }

        home_td = team_diag("home", v04_home, v01_home, v03_home, v04_home_comp)
        away_td = team_diag("away", v04_away, v01_away, v03_away, v04_away_comp)

        # Total diagnostics (Regola C)
        v01_total = (v01_home + v01_away) if (v01_home is not None and v01_away is not None) else None
        v04_total = (v04_home + v04_away) if (v04_home is not None and v04_away is not None) else None
        delta_total = (v04_total - v01_total) if (v04_total is not None and v01_total is not None) else None
        if delta_total is not None and abs(delta_total) > 1.00:
            red_flags.append("red flag totale match: |v0.4 - v0.1| > 1.00")

        # Range diagnostics (Regola D) per totale match
        totals: list[float] = []
        for mv in available_models:
            h = preds.get(mv, {}).get("home")
            a = preds.get(mv, {}).get("away")
            if h is not None and a is not None:
                totals.append(float(h + a))
        rng = _compute_range(totals)
        range_status = None
        if rng is not None:
            range_status = _range_status(float(rng))
            if range_status[0] == "red_flag":
                red_flags.append("modelli discordanti: range > 0.80")

        # Overall status
        overall = "stable"
        if "red flag" in " ".join(red_flags).lower() or any("red_flag" in x for x in (home_td.get("status"), away_td.get("status"))):
            overall = "red_flag"
        if overall != "red_flag" and (home_td.get("status") not in ("stable") or away_td.get("status") not in ("stable")):
            overall = "inspect"
        if overall != "red_flag" and red_flags:
            overall = "inspect"

        # Summary text (Regola 3)
        if overall == "stable":
            summary = "La v0.4 è coerente con la baseline: differenza contenuta e nessun fallback rilevante."
        else:
            if rng is not None and rng > 0.80:
                summary = "Le versioni modello non sono allineate: il range tra minimo e massimo supera 0.80 tiri. Questo match richiede audit manuale."
            elif "fallback usati" in red_flags:
                summary = "La previsione usa fallback per dati mancanti. Il numero è calcolabile ma meno affidabile."
            else:
                summary = "Differenze significative tra versioni modello: partita da controllare."

        component_breakdown: dict[str, Any] = {
            "home": v04_home_comp,
            "away": v04_away_comp,
        }
        if include_raw:
            component_breakdown["raw_json"] = {
                "home": raw_by.get((BASELINE_SOT_MODEL_VERSION_V04_OFFENSIVE_CORE_SOT, "home")),
                "away": raw_by.get((BASELINE_SOT_MODEL_VERSION_V04_OFFENSIVE_CORE_SOT, "away")),
            }

        payload = {
            "status": "success",
            "fixture": {
                "fixture_id": int(fx.id),
                "api_fixture_id": int(fx.api_fixture_id),
                "round": fx.round,
                "kickoff_at": fx.kickoff_at,
                "home_team": {"id": int(home.id), "name": home.name, "logo_url": home.logo_url},
                "away_team": {"id": int(away.id), "name": away.name, "logo_url": away.logo_url},
            },
            "available_models": available_models,
            "active_model_version": active_mv,
            "model_comparison": {
                "home": home_series,
                "away": away_series,
                "match_total": match_total_series,
            },
            "diagnostics": {
                "overall_status": overall,
                "overall_label": _label_for_status(overall),
                "summary": summary,
                "red_flags": list(dict.fromkeys(red_flags)),
                "confidence_notes": list(dict.fromkeys(confidence_notes)),
                "range_total": _round2(rng) if rng is not None else None,
                "range_total_status": range_status[0] if range_status else None,
            },
            "team_diagnostics": {"home": home_td, "away": away_td},
            "component_breakdown": component_breakdown,
        }
        return jsonable_encoder(payload)
    except Exception as exc:  # noqa: BLE001
        return jsonable_encoder(
            {
                "status": "error",
                "failed_step": "unexpected_error",
                "message": "Errore durante il confronto modelli per la fixture.",
                "details": _safe_details(exc),
                "fixture_id": int(fixture_id),
            }
        )


def _serie_a_season_row(db: Session, season_year: int) -> tuple[League, Season] | None:
    league = db.scalar(select(League).where(League.name == IngestionService.SERIE_A_LEAGUE_NAME))
    if league is None:
        return None
    season = db.scalar(select(Season).where(Season.league_id == league.id, Season.year == int(season_year)))
    if season is None:
        return None
    return league, season


def build_model_comparison_for_upcoming(
    db: Session,
    season_year: int,
    *,
    limit: int = 200,
) -> dict[str, Any]:
    try:
        season_tuple = _serie_a_season_row(db, int(season_year))
        if season_tuple is None:
            return {
                "status": "error",
                "failed_step": "load_season",
                "message": "Impossibile caricare Serie A / stagione richiesta.",
                "details": f"season={int(season_year)}",
                "season": int(season_year),
            }
        _league, season = season_tuple

        fixtures = list(
            db.scalars(
                select(Fixture)
                .where(Fixture.season_id == season.id, ~Fixture.status.in_(FINISHED_STATUSES))
                .order_by(Fixture.kickoff_at.asc(), Fixture.id.asc())
            ).all()
        )[: max(1, min(int(limit), 500))]

        matches: list[dict[str, Any]] = []
        stable_n = inspect_n = red_flag_n = 0
        deltas: list[float] = []
        max_abs_total_delta: float | None = None

        for fx in fixtures:
            cmp = build_model_comparison_for_fixture(db, int(fx.id), include_raw=False)
            if cmp.get("status") != "success":
                continue

            diag = (cmp.get("diagnostics") or {}) if isinstance(cmp, dict) else {}
            st = str(diag.get("overall_status") or "inspect")
            if st == "stable":
                stable_n += 1
            elif st == "red_flag":
                red_flag_n += 1
            else:
                inspect_n += 1

            # totals
            totals = cmp.get("model_comparison", {}).get("match_total", [])
            v01_total = None
            v04_total = None
            delta_total = None
            if isinstance(totals, list):
                for row in totals:
                    if not isinstance(row, dict):
                        continue
                    if row.get("model_version") == BASELINE_SOT_MODEL_VERSION:
                        v01_total = row.get("total_expected_sot")
                    if row.get("model_version") == BASELINE_SOT_MODEL_VERSION_V04_OFFENSIVE_CORE_SOT:
                        v04_total = row.get("total_expected_sot")
                        delta_total = row.get("difference_from_v01")
            if isinstance(delta_total, (int, float)):
                deltas.append(float(delta_total))
                if max_abs_total_delta is None or abs(float(delta_total)) > max_abs_total_delta:
                    max_abs_total_delta = abs(float(delta_total))

            fixture_block = cmp.get("fixture") or {}
            matches.append(
                {
                    "fixture_id": int(fixture_block.get("fixture_id")),
                    "home_team": str((fixture_block.get("home_team") or {}).get("name") or ""),
                    "away_team": str((fixture_block.get("away_team") or {}).get("name") or ""),
                    "status": st,
                    "status_label": _label_for_status(st),
                    "v01_total": v01_total,
                    "v04_total": v04_total,
                    "delta_total": delta_total,
                    "main_reason": str(diag.get("summary") or ""),
                    "red_flags": diag.get("red_flags") or [],
                }
            )

        def order_key(m: dict[str, Any]) -> tuple[int, float]:
            st = str(m.get("status") or "inspect")
            pr = 0 if st == "red_flag" else 1 if st == "inspect" else 2
            dt = m.get("delta_total")
            return (pr, -abs(float(dt)) if isinstance(dt, (int, float)) else 0.0)

        matches.sort(key=order_key)

        avg_delta = (sum(deltas) / len(deltas)) if deltas else None
        payload = {
            "status": "success",
            "season": int(season_year),
            "fixtures_analyzed": len(matches),
            "summary": {
                "stable_matches": stable_n,
                "inspect_matches": inspect_n,
                "red_flag_matches": red_flag_n,
                "avg_v04_vs_v01_delta": _round2(avg_delta) if avg_delta is not None else None,
                "max_match_total_delta": _round2(max_abs_total_delta) if max_abs_total_delta is not None else None,
            },
            "matches": matches,
        }
        return jsonable_encoder(payload)
    except Exception as exc:  # noqa: BLE001
        return jsonable_encoder(
            {
                "status": "error",
                "failed_step": "unexpected_error",
                "message": "Errore durante il confronto modelli per la prossima giornata.",
                "details": _safe_details(exc),
                "season": int(season_year),
            }
        )

