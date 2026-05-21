"""Test integrazione leggera filtro rosa nel Top 5 Lineup Impact."""

from unittest.mock import MagicMock

from app.services.player_data.active_roster_resolver import TeamRosterContext
from app.services.sportapi.sportapi_lineup_impact_service import LineupImpactSimulationService


def test_resolve_top5_excludes_lookman_scenario():
    svc = LineupImpactSimulationService()
    resolver = MagicMock()

    ctx = TeamRosterContext(
        season_year=2025,
        league_id=135,
        api_team_id=499,
        internal_team_id=20,
        active_api_player_ids={1001},
        all_team_rows_count=25,
        has_squad_data=True,
        active_on_other_teams={},
    )
    resolver.load_team_context.return_value = ctx
    resolver.roster_sync_hint.return_value = "ok"

    def _filter(candidates, ctx, top_n=5, **kwargs):
        top = [c for c in candidates if c["api_player_id"] == 1001]
        excluded = [c for c in candidates if c["api_player_id"] == 9999]
        for e in excluded:
            e["exclusion_reason"] = "Non più in rosa attuale (API-Sports)"
            e["roster_status"] = "NOT_IN_CURRENT_SQUAD"
        return top, excluded

    def _collect(candidates, ctx, **kwargs):
        return [
            {
                "player_id": 50,
                "player_name": "Lookman",
                "api_player_id": 9999,
                "team_sot_share_pct": 12.9,
                "exclusion_reason": "Non più in rosa attuale (API-Sports)",
                "roster_status": "NOT_IN_CURRENT_SQUAD",
            },
        ]

    resolver.filter_top_candidates.side_effect = _filter
    resolver.collect_excluded_players.side_effect = _collect

    pl_lookman = MagicMock()
    pl_lookman.id = 50
    pl_lookman.api_player_id = 9999
    pl_lookman.name = "Ademola Lookman"
    pl_lookman.team_id = 20

    pl_kean = MagicMock()
    pl_kean.id = 51
    pl_kean.api_player_id = 1001
    pl_kean.name = "Moise Kean"
    pl_kean.team_id = 20

    pr_lookman = MagicMock()
    pr_lookman.team_id = 20
    pr_lookman.shots_on_target_per90 = 1.8
    pr_lookman.team_sot_share_pct = 12.9

    pr_kean = MagicMock()
    pr_kean.team_id = 20
    pr_kean.shots_on_target_per90 = 2.1
    pr_kean.team_sot_share_pct = 27.0

    profiles = {50: (pl_lookman, pr_lookman), 51: (pl_kean, pr_kean)}

    top5, excluded, meta = svc._resolve_top5_for_team(profiles, 20, resolver, ctx)

    assert 50 not in top5
    assert 51 in top5
    assert any(ex.get("player_name") == "Lookman" for ex in excluded)
    assert meta[51]["included_as_unknown"] is False
