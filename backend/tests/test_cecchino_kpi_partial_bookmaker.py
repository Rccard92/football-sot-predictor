from app.services.cecchino.cecchino_kpi_panel import build_cecchino_kpi_panel


def test_partial_only_bet365():
    panel = build_cecchino_kpi_panel(
        statistical={"status": "available", "odd_1": 2.0, "odd_x": 3.0, "odd_2": 5.0, "odd_1x": 1.2, "odd_x2": 1.8, "odd_12": 1.5, "delta_forza": 10, "match_analysis": "Neutro"},
        final_odds={"status": "available", "quota_1": 2.1, "quota_x": 3.1, "quota_2": 4.5, "prob_1": 0.45, "prob_x": 0.30, "prob_2": 0.25},
        bookmaker_payload={
            "status": "partial",
            "bookmakers": [
                {
                    "bookmaker_name": "Bet365",
                    "status": "available",
                    "markets": {"MATCH_WINNER_1X2": {"HOME": 2.0, "DRAW": 3.0, "AWAY": 5.0}},
                },
                {"bookmaker_name": "Betfair", "status": "missing", "markets": {}},
                {"bookmaker_name": "Pinnacle", "status": "missing", "markets": {}},
            ],
            "bookmaker_average": {"MATCH_WINNER_1X2": {"HOME": 2.0, "DRAW": 3.0, "AWAY": 5.0}},
            "warnings": [],
        },
    )
    assert panel["bookmaker_status"] == "partial"
    assert panel["rows"][0]["book"] == 2.0
