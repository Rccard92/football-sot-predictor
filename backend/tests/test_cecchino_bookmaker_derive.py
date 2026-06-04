from app.services.cecchino.cecchino_bookmaker_derive import derive_double_chance_from_1x2


def test_derive_dc_from_1x2():
    out = derive_double_chance_from_1x2(2.0, 3.2, 4.0)
    assert out["ONE_X"] is not None
    assert out["X_TWO"] is not None
    assert out["ONE_TWO"] is not None
    assert out["ONE_X"] < 2.0


def test_derive_dc_incomplete():
    out = derive_double_chance_from_1x2(2.0, None, 4.0)
    assert out["ONE_X"] is None
