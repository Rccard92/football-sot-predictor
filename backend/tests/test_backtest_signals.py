from app.services.backtest_signals import actual_over_line, line_hit, line_signal


def test_line_signal_no_bet_within_band():
    assert line_signal(3.5, 3.5) == "no_bet"
    assert line_signal(3.6, 3.5) == "no_bet"
    assert line_signal(3.25, 3.5) == "no_bet"


def test_line_signal_over_under_outside_band():
    assert line_signal(4.0, 3.5) == "over"
    assert line_signal(2.0, 3.5) == "under"


def test_line_signal_boundary_plus_25():
    assert line_signal(3.76, 3.5) == "over"
    assert line_signal(3.75, 3.5) == "no_bet"
    assert line_signal(3.24, 3.5) == "under"


def test_actual_over_line():
    assert actual_over_line(4.0, 3.5) is True
    assert actual_over_line(3.0, 3.5) is False
    assert actual_over_line(3, 3) is None


def test_line_hit():
    assert line_hit("no_bet", True) is None
    assert line_hit("over", True) is True
    assert line_hit("over", False) is False
    assert line_hit("under", False) is True
    assert line_hit("under", True) is False
    assert line_hit("over", None) is None
