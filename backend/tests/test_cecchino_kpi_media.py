from app.services.cecchino.cecchino_kpi_panel import _kpi_average


def test_media_ignores_null():
    assert _kpi_average(2.29, 2.1, None) == round((2.29 + 2.1) / 2, 2)


def test_media_all_null():
    assert _kpi_average(None, "—", None) is None
