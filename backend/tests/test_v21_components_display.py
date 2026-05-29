"""Test mapping component tree v2.1 per display audit."""

from __future__ import annotations

from app.services.sot_fixture_explanation_service import (
    _components_v21,
    _resolve_v21_source_display,
)


def test_resolve_v21_source_display_prefers_path():
    assert _resolve_v21_source_display({"source_path": "team_stats.season_avg_sot_for", "status": "available"}) == (
        "team_stats.season_avg_sot_for"
    )


def test_resolve_v21_source_display_not_tracked():
    assert _resolve_v21_source_display({"status": "not_tracked_yet"}) == "not_tracked_yet"


def test_components_v21_macro_weight_and_micro_fields():
    raw = {
        "base_anchor_sot": 4.65,
        "final_multiplier": 1.04,
        "macroareas": [
            {
                "key": "offensive_production",
                "label": "Produzione offensiva composita",
                "macro_weight": 16,
                "macro_index": 1.07,
                "macro_contribution_to_multiplier": 17.11,
                "status": "available",
                "warnings": [],
                "micros": [
                    {
                        "key": "avg_sot_for",
                        "label": "Media tiri in porta fatti",
                        "micro_weight": 25,
                        "raw_value": 4.6875,
                        "normalized_value": 1.0579,
                        "source_path": "team_stats.season_avg_sot_for",
                        "sample_count": 28,
                        "status": "available",
                        "fallback_used": False,
                        "contribution": "positiva",
                    },
                    {
                        "key": "top_shots_share",
                        "label": "Quota tiri top",
                        "micro_weight": 8,
                        "raw_value": None,
                        "normalized_value": 1.0,
                        "source_path": "player_season_profiles.top_shooters_shots_share",
                        "status": "not_tracked_yet",
                        "fallback_used": False,
                        "contribution": "neutra",
                    },
                ],
            },
        ],
        "components": {},
    }
    comps = _components_v21(raw, 4.84)
    macro = next(c for c in comps if c.get("id") == "v21_macro_offensive_production")
    assert macro["weight"] == 16.0
    assert macro["weight_scale"] == "manifest_points"
    assert macro["value"] == 1.07
    assert macro["contribution"] == 17.11

    micros = macro["variables"]
    assert micros[0]["weight_internal"] == 25
    assert micros[0]["data_source"] == "team_stats.season_avg_sot_for"
    assert micros[0]["raw_value"] == 4.69
    assert micros[0]["normalized_value"] == 1.06

    assert micros[1]["data_source"] == "player_season_profiles.top_shooters_shots_share"
    assert micros[1]["weight_internal"] == 8
