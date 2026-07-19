"""Test contratto Acquistabilità V1 Preview — FASE 1/5 (nessuna formula)."""

from __future__ import annotations

from app.schemas.cecchino_purchasability_preview import (
    PURCHASABILITY_FEATURE_VERSION,
    PURCHASABILITY_PREVIEW_CONTRACT_VERSION,
    CecchinoPurchasabilityPreviewContract,
    build_purchasability_preview_not_calculated,
)


def test_preview_contract_version():
    assert (
        PURCHASABILITY_PREVIEW_CONTRACT_VERSION
        == "cecchino_purchasability_v1_preview_contract"
    )
    assert PURCHASABILITY_FEATURE_VERSION == "cecchino_purchasability_features_v1"


def test_preview_not_calculated_score_null():
    payload = build_purchasability_preview_not_calculated(
        market_key="HOME",
        selection="HOME",
    )
    assert payload["version"] == PURCHASABILITY_PREVIEW_CONTRACT_VERSION
    assert payload["feature_version"] == PURCHASABILITY_FEATURE_VERSION
    assert payload["status"] == "not_calculated"
    assert payload["score"] is None
    assert payload["class"] is None
    assert payload["reading"] is None
    assert payload["market_key"] == "HOME"
    assert payload["selection"] == "HOME"
    assert payload["reason_codes"] == ["formula_not_implemented_phase_1"]
    assert payload["phase_1_value"]["status"] == "not_calculated"
    assert payload["phase_1_value"]["score"] is None
    assert payload["phase_1_value"]["inputs"]["prob_cecchino"] is None
    assert payload["phase_1_value"]["inputs"]["rating"] is None
    assert payload["phase_1_value"]["dependency_metadata"]["rating_is_derived"] is True
    assert payload["phase_2_quality"]["status"] == "not_calculated"
    assert payload["phase_2_quality"]["score"] is None
    assert payload["phase_2_quality"]["comparator_selections"] == []
    assert payload["context_hooks"]["balance_v5"]["status"] == "not_connected"
    assert payload["context_hooks"]["balance_v5"]["payload"] is None
    assert payload["context_hooks"]["goal_intensity_v5"]["status"] == "not_connected"
    assert payload["data_quality"]["pre_match_only"] is True
    assert payload["data_quality"]["no_post_match_features"] is True
    assert payload["data_quality"]["contains_settlement_fields"] is False


def test_preview_pydantic_roundtrip():
    payload = build_purchasability_preview_not_calculated(market_key="DRAW")
    model = CecchinoPurchasabilityPreviewContract.model_validate(payload)
    assert model.status == "not_calculated"
    assert model.score is None
    dumped = model.model_dump(by_alias=True)
    assert dumped["class"] is None
    assert "score" in dumped


def test_preview_no_random_placeholder_scores():
    for _ in range(5):
        p = build_purchasability_preview_not_calculated(market_key="AWAY")
        assert p["score"] is None
        assert p["phase_1_value"]["score"] is None
        assert p["phase_2_quality"]["score"] is None
