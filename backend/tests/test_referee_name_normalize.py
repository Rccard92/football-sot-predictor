"""Test normalizzazione nomi arbitro."""

from __future__ import annotations

from app.services.referee_name_normalize import normalize_referee_name, referee_names_match


def test_normalize_referee_name_strips_and_lowercases():
    assert normalize_referee_name("  Marco Guida  ") == "marco guida"


def test_normalize_referee_name_accented():
    assert normalize_referee_name("D. Orsato") == "d orsato"


def test_referee_names_match_initial_vs_full():
    assert referee_names_match("M. Mariani", "M. Mariani")
    assert referee_names_match("Marco Guida", "marco guida")


def test_referee_names_match_empty():
    assert not referee_names_match(None, "Guida")
    assert not referee_names_match("Guida", "")
