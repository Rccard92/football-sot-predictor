"""Test normalizzazione nomi arbitro."""

from __future__ import annotations

from app.services.referee_name_normalize import (
    MATCH_WARNING_LIKELY,
    compare_referee_names,
    normalize_referee_name,
    referee_names_match,
)


def test_normalize_referee_name_strips_and_lowercases():
    assert normalize_referee_name("  Marco Guida  ") == "marco guida"


def test_referee_names_match_initial_vs_full():
    assert referee_names_match("M. Guida", "Marco Guida")
    assert referee_names_match("Marco Guida", "marco guida")


def test_compare_likely_match_warning():
    r = compare_referee_names("M. Guida", "Marco Guida")
    assert r.matches
    assert r.confidence in ("exact", "likely")
    if r.confidence == "likely":
        assert r.match_warning == MATCH_WARNING_LIKELY


def test_compare_inverted_order():
    assert referee_names_match("Guida M.", "Marco Guida")


def test_referee_names_match_empty():
    assert not referee_names_match(None, "Guida")
    assert not referee_names_match("Guida", "")
