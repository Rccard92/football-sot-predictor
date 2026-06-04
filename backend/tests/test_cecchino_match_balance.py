from app.services.cecchino.cecchino_match_balance import classify_match_balance


def test_equilibrio():
    assert classify_match_balance(0.35, 0.30, 0.35) == "Equilibrio"


def test_squilibrio():
    assert classify_match_balance(0.55, 0.20, 0.15) == "Squilibrio"


def test_neutro():
    assert classify_match_balance(0.40, 0.25, 0.35) == "Neutro"
