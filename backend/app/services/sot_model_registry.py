"""Registry metadati modelli SOT — versioni visibili in UI vs legacy."""

from __future__ import annotations

from dataclasses import dataclass

from app.core.constants import (
    BASELINE_SOT_MODEL_VERSION,
    BASELINE_SOT_MODEL_VERSION_V02,
    BASELINE_SOT_MODEL_VERSION_V02_PLAYER_ADJUSTED,
    BASELINE_SOT_MODEL_VERSION_V03_CORE_SOT,
    BASELINE_SOT_MODEL_VERSION_V04_OFFENSIVE_CORE_SOT,
    BASELINE_SOT_MODEL_VERSION_V10_SOT,
    BASELINE_SOT_MODEL_VERSION_V11_SOT,
    BASELINE_SOT_MODEL_VERSION_V20_LINEUP_IMPACT,
)


@dataclass(frozen=True)
class ModelDisplayInfo:
    model_id: str
    label: str
    short_label: str
    stage_badge: str
    description: str
    is_stable: bool = False
    visible_in_ui: bool = True


MODEL_REGISTRY: dict[str, ModelDisplayInfo] = {
    BASELINE_SOT_MODEL_VERSION_V20_LINEUP_IMPACT: ModelDisplayInfo(
        model_id=BASELINE_SOT_MODEL_VERSION_V20_LINEUP_IMPACT,
        label="v2.0 SOT Lineup Impact",
        short_label="v2.0",
        stage_badge="Lineup Impact",
        description=(
            "Modello SOT con impatto formazioni, indisponibili, sostituti e filtro rosa attuale. "
            "Base v1.1 moltiplicata per fattore offensivo e debolezza difensiva avversaria."
        ),
    ),
    BASELINE_SOT_MODEL_VERSION_V11_SOT: ModelDisplayInfo(
        model_id=BASELINE_SOT_MODEL_VERSION_V11_SOT,
        label="v1.1 SOT",
        short_label="v1.1",
        stage_badge="stabile",
        description=(
            "Versione stabile: produzione offensiva, difensiva, split casa/trasferta, "
            "forma recente, xG e player layer (6 termini)."
        ),
        is_stable=True,
    ),
    BASELINE_SOT_MODEL_VERSION_V10_SOT: ModelDisplayInfo(
        model_id=BASELINE_SOT_MODEL_VERSION_V10_SOT,
        label="v1.0 SOT (xG)",
        short_label="v1.0",
        stage_badge="legacy",
        description="Versione parallela con correzione xG.",
        visible_in_ui=False,
    ),
    BASELINE_SOT_MODEL_VERSION_V04_OFFENSIVE_CORE_SOT: ModelDisplayInfo(
        model_id=BASELINE_SOT_MODEL_VERSION_V04_OFFENSIVE_CORE_SOT,
        label="v0.4 offensive core",
        short_label="v0.4",
        stage_badge="legacy",
        description="Core offensivo migliorato.",
        visible_in_ui=False,
    ),
    BASELINE_SOT_MODEL_VERSION_V03_CORE_SOT: ModelDisplayInfo(
        model_id=BASELINE_SOT_MODEL_VERSION_V03_CORE_SOT,
        label="v0.3 core SOT",
        short_label="v0.3",
        stage_badge="legacy",
        visible_in_ui=False,
    ),
    BASELINE_SOT_MODEL_VERSION_V02_PLAYER_ADJUSTED: ModelDisplayInfo(
        model_id=BASELINE_SOT_MODEL_VERSION_V02_PLAYER_ADJUSTED,
        label="v0.2 player adjusted",
        short_label="v0.2",
        stage_badge="legacy",
        visible_in_ui=False,
    ),
    BASELINE_SOT_MODEL_VERSION_V02: ModelDisplayInfo(
        model_id=BASELINE_SOT_MODEL_VERSION_V02,
        label="v0.2 context",
        short_label="v0.2",
        stage_badge="legacy",
        visible_in_ui=False,
    ),
    BASELINE_SOT_MODEL_VERSION: ModelDisplayInfo(
        model_id=BASELINE_SOT_MODEL_VERSION,
        label="v0.1 SOT",
        short_label="v0.1",
        stage_badge="legacy",
        visible_in_ui=False,
    ),
}

USER_VISIBLE_MODEL_VERSIONS: tuple[str, ...] = (
    BASELINE_SOT_MODEL_VERSION_V20_LINEUP_IMPACT,
    BASELINE_SOT_MODEL_VERSION_V11_SOT,
)

LEGACY_MODEL_VERSIONS: frozenset[str] = frozenset(
    {
        BASELINE_SOT_MODEL_VERSION,
        BASELINE_SOT_MODEL_VERSION_V02,
        BASELINE_SOT_MODEL_VERSION_V02_PLAYER_ADJUSTED,
        BASELINE_SOT_MODEL_VERSION_V03_CORE_SOT,
        BASELINE_SOT_MODEL_VERSION_V04_OFFENSIVE_CORE_SOT,
        BASELINE_SOT_MODEL_VERSION_V10_SOT,
    }
)


def user_visible_model_versions() -> list[str]:
    return list(USER_VISIBLE_MODEL_VERSIONS)


def is_user_visible_model(model_version: str) -> bool:
    return model_version in USER_VISIBLE_MODEL_VERSIONS


def get_model_display(model_version: str) -> ModelDisplayInfo | None:
    return MODEL_REGISTRY.get(model_version)


def label_for_model(model_version: str) -> str:
    info = get_model_display(model_version)
    return info.label if info else model_version


def stage_badge_for_model(model_version: str) -> str:
    info = get_model_display(model_version)
    return info.stage_badge if info else "—"
