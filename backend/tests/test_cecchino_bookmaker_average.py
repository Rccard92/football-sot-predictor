from app.services.cecchino.cecchino_bookmaker_derive import arithmetic_mean


def test_arithmetic_mean_three_bookmakers():
    assert arithmetic_mean([2.0, 2.2, 2.4]) == 2.2


def test_arithmetic_mean_partial():
    assert arithmetic_mean([2.0, None, 2.4]) == 2.2
