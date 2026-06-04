from app.services.cecchino.cecchino_kpi_panel import _edge


def test_edge_formula():
    # book=2.2, cecchino=2.0 => (2.2/2.0)-1 = 0.1 => 10%
    assert _edge(2.2, 2.0) == 10.0


def test_edge_null_when_missing():
    assert _edge(None, 2.0) is None
    assert _edge(2.0, None) is None
