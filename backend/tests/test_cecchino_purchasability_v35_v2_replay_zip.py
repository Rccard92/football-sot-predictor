"""Replay ZIP reale Structural V2 — anti-inflation + freeze + outcome diagnostic."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.services.cecchino.cecchino_purchasability_v35_v2_replay import (
    POST_MATCH_FIELDS,
    load_analysis_rows_from_zip,
    replay_structural_v2_from_v1_analysis_csv,
    run_full_replay_with_freeze,
    strip_post_match_fields,
)

ZIP_PATH = Path(
    r"c:\Users\anton\Downloads\purchasability-v35-analysis-2026-08-20_2026-08-26.zip"
)


pytestmark = pytest.mark.skipif(
    not ZIP_PATH.exists(), reason="ZIP analysis 20-26 non disponibile localmente"
)


def test_strip_removes_all_post_match_fields():
    rows = load_analysis_rows_from_zip(ZIP_PATH)
    stripped = strip_post_match_fields(rows[0])
    for k in POST_MATCH_FIELDS:
        assert k not in stripped


def test_replay_zip_anti_inflation_and_pt_s():
    rows = load_analysis_rows_from_zip(ZIP_PATH)
    result = replay_structural_v2_from_v1_analysis_csv(rows)
    assert result["post_match_fields_in_replay_payload"] == 0
    assert result["anti_inflation"]["passed"], result["anti_inflation"]
    assert result["pt_s_availability_when_family_complete"]["all_complete_100pct"]
    assert result["ft_s_availability_when_family_complete"]["all_complete_100pct"]
    assert result["scored_rows"] > 0


def test_full_replay_freeze_and_outcome_report():
    report = run_full_replay_with_freeze(ZIP_PATH)
    assert report["freeze_unchanged"] is True
    assert report["V2_FORMULA_FREEZE_SHA256"]
    assert (
        report["V2_FORMULA_FREEZE_SHA256"]
        == report["freeze_sha_after_replay"]
        == report["freeze_sha_after_outcome"]
    )
    bands = report["outcome_diagnostic"]["bands"]
    assert len(bands) == 6
    # Persist key metrics for the Phase A human report via assertion messages
    dist = report["replay"]["distribution"]
    assert dist["n"] > 0
