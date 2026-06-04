from app.services.cecchino.cecchino_kpi_panel import build_cecchino_kpi_panel


def test_kpi_panel_no_bookmaker_no_crash():
    panel = build_cecchino_kpi_panel(
        statistical={
            "status": "available",
            "odd_1": 2.29,
            "odd_x": 2.67,
            "odd_2": 5.52,
            "odd_1x": 1.23,
            "odd_x2": 1.8,
            "odd_12": 1.62,
            "delta_forza": 12.0,
            "match_analysis": "Neutro",
        },
        final_odds={
            "status": "available",
            "quota_1": 2.1,
            "quota_x": 3.2,
            "quota_2": 4.0,
            "prob_1": 0.48,
            "prob_x": 0.31,
            "prob_2": 0.25,
        },
        bookmaker_payload={"status": "not_available", "bookmakers": [], "bookmaker_average": {}, "warnings": []},
    )
    row1 = panel["rows"][0]
    assert row1["book"] is None
    assert row1["edge"] is None
