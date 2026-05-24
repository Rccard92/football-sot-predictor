"""Contesto arbitro vs squadre del match e precedenti diretti."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Fixture, FixtureReferee, Referee, Team
from app.models.referee_fixture_card_summary import RefereeFixtureCardSummary
from app.services.referee_cards_resolver import card_summary_to_dict
from app.services.referee_name_normalize import normalize_referee_name
from app.services.referee_severity_service import (
    aggregate_card_rows,
    classify_severity,
    sample_quality_from_count,
)


def _context_block(
    *,
    label: str,
    rows: list[RefereeFixtureCardSummary],
    team_api_id: int | None = None,
    team_internal_id: int | None = None,
) -> dict[str, Any]:
    if not rows:
        return {
            "available": False,
            "label": label,
            "message": "Nessun dato in cache. Usa «Importa storico stagione» nel Catalogo dati.",
        }

    fixtures_used = [card_summary_to_dict(r) for r in rows]
    agg = aggregate_card_rows(rows, team_api_id=team_api_id, team_internal_id=team_internal_id)
    mc = agg["matches_count"]
    avg_y = agg["avg_yellow_cards"]
    avg_r = agg["avg_red_cards"]
    sev, _ = classify_severity(avg_y, avg_r)
    return {
        "available": True,
        "label": label,
        "matches_count": mc,
        "avg_yellow_cards": avg_y,
        "avg_red_cards": avg_r,
        "avg_yellow_team": agg.get("avg_yellow_team"),
        "avg_red_team": agg.get("avg_red_team"),
        "severity_label": sev,
        "sample_quality": sample_quality_from_count(mc),
        "data_source": agg.get("data_source", "db_only"),
        "fixtures_used": fixtures_used,
    }


class RefereeMatchContextService:
    def build_match_context(self, db: Session, *, fixture_id: int) -> dict[str, Any]:
        fx = db.get(Fixture, int(fixture_id))
        if fx is None:
            return {"status": "error", "message": f"Fixture {fixture_id} non trovata"}

        home = db.get(Team, int(fx.home_team_id))
        away = db.get(Team, int(fx.away_team_id))
        home_name = home.name if home else "Casa"
        away_name = away.name if away else "Trasferta"
        match_label = f"{home_name} - {away_name}"

        link = db.scalar(
            select(FixtureReferee)
            .where(FixtureReferee.fixture_id == int(fx.id))
            .order_by(FixtureReferee.id.desc()),
        )
        referee_name = (link.referee_name if link and link.referee_name else None) or fx.referee
        if not referee_name:
            return {
                "status": "error",
                "message": "Arbitro non assegnato: eseguire sync arbitro fixture",
                "fixture": match_label,
            }

        ref_id = int(link.referee_id) if link and link.referee_id else None
        if ref_id is None:
            ref = db.scalar(
                select(Referee).where(Referee.normalized_name == normalize_referee_name(referee_name)),
            )
            ref_id = int(ref.id) if ref else None

        if ref_id is None:
            return {
                "status": "error",
                "message": "Arbitro non in anagrafica: sync o import storico",
                "fixture": match_label,
                "referee": referee_name,
            }

        cache_rows = list(
            db.scalars(
                select(RefereeFixtureCardSummary)
                .where(RefereeFixtureCardSummary.referee_id == ref_id)
                .order_by(RefereeFixtureCardSummary.kickoff_at.desc()),
            ).all(),
        )

        home_api = int(home.api_team_id) if home and home.api_team_id else None
        away_api = int(away.api_team_id) if away and away.api_team_id else None
        home_internal = int(fx.home_team_id)
        away_internal = int(fx.away_team_id)

        def team_rows(team_api: int | None, team_internal: int) -> list[RefereeFixtureCardSummary]:
            out: list[RefereeFixtureCardSummary] = []
            for row in cache_rows:
                if team_api is not None and (
                    row.home_team_api_id == team_api or row.away_team_api_id == team_api
                ):
                    out.append(row)
                    continue
                if row.fixture_id:
                    f = db.get(Fixture, int(row.fixture_id))
                    if f and (int(f.home_team_id) == team_internal or int(f.away_team_id) == team_internal):
                        out.append(row)
            return out

        home_rows = team_rows(home_api, home_internal)
        away_rows = team_rows(away_api, away_internal)

        direct_rows: list[RefereeFixtureCardSummary] = []
        pair_a, pair_b = sorted([home_internal, away_internal])
        for row in cache_rows:
            if row.fixture_id:
                f = db.get(Fixture, int(row.fixture_id))
                if f:
                    ids = sorted([int(f.home_team_id), int(f.away_team_id)])
                    if ids == [pair_a, pair_b]:
                        direct_rows.append(row)
                        continue
            if home_api and away_api:
                ids_api = {row.home_team_api_id, row.away_team_api_id}
                if ids_api == {home_api, away_api}:
                    direct_rows.append(row)

        return {
            "status": "success",
            "fixture": match_label,
            "fixture_id": int(fixture_id),
            "referee": referee_name,
            "referee_id": ref_id,
            "home_team_context": _context_block(
                label=f"{home_name} con questo arbitro",
                rows=home_rows,
                team_api_id=home_api,
                team_internal_id=home_internal,
            ),
            "away_team_context": _context_block(
                label=f"{away_name} con questo arbitro",
                rows=away_rows,
                team_api_id=away_api,
                team_internal_id=away_internal,
            ),
            "direct_h2h_context": _context_block(
                label=f"Precedenti diretti {home_name}–{away_name}",
                rows=direct_rows,
            ),
        }
