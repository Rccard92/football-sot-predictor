"""Parser nullable player match stats (nessun 0 fittizio per null)."""

from app.services.player_data.api_player_parsing import (
    parse_float_nullable,
    parse_int_nullable,
    parse_percent_nullable,
)


def test_parse_int_nullable_preserves_none():
    assert parse_int_nullable(None) is None
    assert parse_int_nullable("") is None
    assert parse_int_nullable("-") is None
    assert parse_int_nullable("12") == 12
    assert parse_int_nullable(0) == 0


def test_parse_float_nullable_rating_string():
    assert parse_float_nullable("6.9") == 6.9
    assert parse_float_nullable(None) is None


def test_parse_percent_nullable():
    assert parse_percent_nullable("84%") == 84.0
    assert parse_percent_nullable(84) == 84.0
    assert parse_percent_nullable(None) is None
    assert parse_percent_nullable("") is None
