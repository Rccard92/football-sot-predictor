"""Test catalogo campionati, Div check, anomalie, AH parziale."""

from __future__ import annotations

import os
from io import BytesIO
from unittest.mock import MagicMock, patch

os.environ.setdefault("DATABASE_URL", "postgresql://user:pass@localhost:5432/test")

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routes import cecchino_lab
from app.services.cecchino_data_lab.competition_catalog import get_competition, list_competitions
from app.services.cecchino_data_lab.constants import IMPORT_CONFIRM_TOKEN, ISSUE_PARTIAL_BET365_AH
from app.services.cecchino_data_lab.csv_parser import parse_football_data_csv
from app.services.cecchino_data_lab.import_helpers import parse_with_catalog
from app.services.cecchino_data_lab.preview_service import preview_csv_bytes
from app.core.database import get_db


def test_catalog_has_championship_and_league_two():
    ch = get_competition("championship")
    assert ch is not None
    assert ch.division_code == "E1"
    assert ch.country == "England"
    assert ch.timezone == "Europe/London"

    e3 = get_competition("league_two")
    assert e3 is not None
    assert e3.division_code == "E3"

    items = list_competitions()
    assert len(items) == 16
    # Ordinato per paese, nome
    countries = [c.country for c in items]
    assert countries == sorted(countries, key=str.lower)


def test_championship_accepts_e1():
    csv = (
        "Div,Date,HomeTeam,AwayTeam,FTHG,FTAG,FTR,B365H,B365D,B365A\n"
        "E1,10/08/2024,Leeds,Norwich,2,0,H,1.80,3.50,4.20\n"
    )
    entry, parsed = parse_with_catalog(
        csv.encode("utf-8"),
        competition_key="championship",
        season_label="2024/2025",
    )
    assert entry.division_code == "E1"
    assert parsed.summary["importable"] is True
    assert not any(i.issue_code == "division_mismatch" for i in parsed.issues)


def test_league_two_accepts_e3():
    csv = (
        "Div,Date,HomeTeam,AwayTeam,FTHG,FTAG,FTR\n"
        "E3,10/08/2024,A,B,1,0,H\n"
    )
    entry, parsed = parse_with_catalog(
        csv.encode("utf-8"),
        competition_key="league_two",
        season_label="2024/2025",
    )
    assert entry.division_code == "E3"
    assert parsed.summary["importable"] is True


def test_division_mismatch_blocks():
    csv = (
        "Div,Date,HomeTeam,AwayTeam,FTHG,FTAG,FTR\n"
        "E3,10/08/2024,A,B,1,0,H\n"
    )
    entry, parsed = parse_with_catalog(
        csv.encode("utf-8"),
        competition_key="championship",
        season_label="2024/2025",
    )
    assert entry.division_code == "E1"
    assert parsed.summary["importable"] is False
    assert parsed.summary.get("division_mismatch") is True
    assert any(i.issue_code == "division_mismatch" for i in parsed.issues)


def test_preview_metadata_from_catalog():
    csv = (
        "Div,Date,HomeTeam,AwayTeam,FTHG,FTAG,FTR,B365H,B365D,B365A\n"
        "I1,10/08/2024,Inter,Milan,1,0,H,2.10,3.20,3.50\n"
    )
    out = preview_csv_bytes(
        csv.encode("utf-8"),
        competition_key="serie_a",
        season_label="2025/2026",
        source_filename="I1.csv",
    )
    assert out["competition_name"] == "Serie A"
    assert out["country"] == "Italy"
    assert out["division_code"] == "I1"
    assert out["timezone"] == "Europe/Rome"
    assert out["competition_key"] == "serie_a"


def test_partial_ah_warning_not_blocking_and_complete_1x2():
    csv = (
        "Div,Date,HomeTeam,AwayTeam,FTHG,FTAG,FTR,"
        "HS,AS,HST,AST,HF,AF,HC,AC,HY,AY,HR,AR,"
        "B365H,B365D,B365A,AHh,B365AHH\n"
        "E0,10/08/2024,A,B,2,0,H,"
        "10,5,4,2,8,9,5,3,1,1,0,0,"
        "1.50,4.00,6.00,-0.5,1.90\n"
    )
    result = parse_football_data_csv(csv.encode("utf-8"))
    m = result.matches[0]
    assert m.importable is True
    assert m.bet365_1x2_pre_ready is True
    assert m.row_quality_status == "complete"
    assert any(i.issue_code == ISSUE_PARTIAL_BET365_AH for i in m.issues)
    assert m.bet365_ah_away is None
    assert m.asian_handicap_home_line is not None


def test_catalog_endpoint():
    app = FastAPI()
    app.include_router(cecchino_lab.router, prefix="/api")
    client = TestClient(app)
    res = client.get("/api/cecchino-lab/catalog/competitions")
    assert res.status_code == 200
    items = res.json()["items"]
    assert len(items) == 16
    keys = {i["key"] for i in items}
    assert "championship" in keys
    assert "serie_a" in keys


def test_overview_anomalies_exclude_info():
    from app.services.cecchino_data_lab.query_service import get_overview

    db = MagicMock()
    # datasets empty
    db.query.return_value.all.return_value = []

    # Sequence of scalar() calls in get_overview:
    # total_matches, complete, errors, warnings, with_1x2, with_ou
    scalars = iter([0, 0, 2, 1, 0, 0])

    def scalar_side():
        return next(scalars)

    # Also recent imports query uses order_by.limit.all
    q = MagicMock()
    q.filter.return_value = q
    q.order_by.return_value = q
    q.limit.return_value = q
    q.all.return_value = []
    q.scalar.side_effect = scalar_side
    db.query.return_value = q

    out = get_overview(db)
    assert out["anomalies_errors"] == 2
    assert out["anomalies_warnings"] == 1
    assert out["anomalies_total"] == 3  # non include info


def test_preview_api_uses_competition_key():
    app = FastAPI()
    app.include_router(cecchino_lab.admin_router, prefix="/api")
    client = TestClient(app)
    csv = (
        "Div,Date,HomeTeam,AwayTeam,FTHG,FTAG,FTR,B365H,B365D,B365A\n"
        "E1,10/08/2024,Leeds,Norwich,2,0,H,1.80,3.50,4.20\n"
    )
    files = {"file": ("E1.csv", BytesIO(csv.encode("utf-8")), "text/csv")}
    data = {"competition_key": "championship", "season_label": "2024/2025"}
    res = client.post("/api/admin/cecchino-lab/imports/preview", files=files, data=data)
    assert res.status_code == 200
    body = res.json()
    assert body["division_code"] == "E1"
    assert body["summary"]["importable"] is True
