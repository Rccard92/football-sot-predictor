"""Ordine display gruppi segnali Cecchino — Monitoraggio / Lab."""

from __future__ import annotations

SIGNAL_GROUP_DISPLAY_ORDER: tuple[str, ...] = (
    "HOME",
    "DRAW",
    "AWAY",
    "ONE_X",
    "X_TWO",
    "ONE_TWO",
    "DRAW_PT",
    "UNDER_UNDER_PT",
    "OVER_OVER_PT",
)

SIGNAL_GROUP_DISPLAY_LABELS: dict[str, str] = {
    "HOME": "1",
    "DRAW": "X",
    "AWAY": "2",
    "ONE_X": "1X",
    "X_TWO": "X2",
    "ONE_TWO": "1/2",
    "DRAW_PT": "X PT",
    "UNDER_UNDER_PT": "Under",
    "OVER_OVER_PT": "Over",
}


def signal_group_sort_key(signal_group: str) -> tuple[int, str]:
    try:
        return (SIGNAL_GROUP_DISPLAY_ORDER.index(signal_group), signal_group)
    except ValueError:
        return (len(SIGNAL_GROUP_DISPLAY_ORDER), signal_group)


def display_label_for_signal_group(signal_group: str, fallback: str | None = None) -> str:
    return SIGNAL_GROUP_DISPLAY_LABELS.get(signal_group, fallback or signal_group)
