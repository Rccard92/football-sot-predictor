"""Test parser e validazioni Cecchino Lab CSV."""

from __future__ import annotations

from decimal import Decimal

from app.services.cecchino_data_lab.csv_encoding import decode_csv_bytes
from app.services.cecchino_data_lab.csv_parser import parse_football_data_csv
from app.services.cecchino_data_lab.constants import PARSER_VERSION

SAMPLE_CSV = (
    "Div,Date,Time,HomeTeam,AwayTeam,FTHG,FTAG,FTR,HTHG,HTAG,HTR,"
    "HS,AS,HST,AST,HF,AF,HC,AC,HY,AY,HR,AR,"
    "B365H,B365D,B365A,B365>2.5,B365<2.5,AHh,B365AHH,B365AHA,"
    "B365CH,B365CD,B365CA,B365C>2.5,B365C<2.5,AHCh,B365CAHH,B365CAHA,Referee\n"
    "E0,10/08/2024,15:00,Arsenal,Wolves,2,0,H,1,0,H,"
    "14,5,6,2,10,12,7,3,1,2,0,0,"
    "1.45,4.50,7.00,1.80,2.00,-1.0,1.95,1.95,"
    "1.40,4.80,7.50,1.75,2.10,-1.0,1.90,2.00,M Oliver\n"
    "E0,11/08/2024,16:30,Chelsea,Man City,1,1,D,0,1,A,"
    "8,12,3,5,11,9,4,6,2,1,0,0,"
    "3.40,3.50,2.10,1.85,1.95,0.25,1.90,2.00,"
    "3.60,3.40,2.05,1.80,2.00,0.25,1.88,2.02,A Taylor\n"
)


def test_decode_utf8_and_cp1252_fallback():
    decoded = decode_csv_bytes(SAMPLE_CSV.encode("utf-8"))
    assert decoded.encoding == "utf-8"
    assert not decoded.used_fallback

    bom = b"\xef\xbb\xbf" + SAMPLE_CSV.encode("utf-8")
    decoded_bom = decode_csv_bytes(bom)
    assert decoded_bom.encoding == "utf-8-sig"

    # Euro sign that is invalid in strict contexts — CP1252 path
    weird = "Div,Date,HomeTeam,AwayTeam\nE0,01/01/2024,Caf\xe9,Bar\n".encode("cp1252")
    decoded_cp = decode_csv_bytes(weird)
    assert decoded_cp.encoding == "cp1252"
    assert decoded_cp.used_fallback


def test_parse_valid_csv_bet365_and_raw():
    result = parse_football_data_csv(SAMPLE_CSV.encode("utf-8"), timezone_name="Europe/London")
    assert result.parser_version == PARSER_VERSION
    assert result.rows_total == 2
    assert result.rows_importable == 2
    assert result.missing_required_columns == []
    m0 = result.matches[0]
    assert m0.home_team == "Arsenal"
    assert m0.ft_home_goals == 2
    assert m0.bet365_home == Decimal("1.45")
    assert m0.bet365_1x2_pre_ready is True
    assert m0.statistics_ready is True
    assert m0.raw["B365H"] == "1.45"
    assert result.bet365_coverage["1x2_pre_pct"] == 100.0


def test_empty_file():
    result = parse_football_data_csv(b"   \n")
    assert result.rows_total == 0
    assert any(i.issue_code == "empty_file" for i in result.issues)


def test_invalid_header():
    result = parse_football_data_csv(b"Foo,Bar\n1,2\n")
    assert "Div" in result.missing_required_columns
    assert any(i.issue_code == "invalid_header" for i in result.issues)


def test_ft_result_inconsistent():
    bad = (
        "Div,Date,HomeTeam,AwayTeam,FTHG,FTAG,FTR\n"
        "E0,10/08/2024,A,B,2,0,A\n"
    )
    result = parse_football_data_csv(bad.encode("utf-8"))
    assert result.matches[0].importable is True  # inconsistent FT is error but not blocking identity
    assert any(i.issue_code == "ft_result_inconsistent" for i in result.matches[0].issues)


def test_odds_lte_one_and_ah_line():
    bad = (
        "Div,Date,HomeTeam,AwayTeam,B365H,B365D,B365A,AHh\n"
        "E0,10/08/2024,A,B,0.95,3.0,4.0,0.10\n"
    )
    result = parse_football_data_csv(bad.encode("utf-8"))
    codes = {i.issue_code for i in result.matches[0].issues}
    assert "odds_lte_one" in codes
    assert "ah_line_not_quarter" in codes


def test_same_team_blocks_import():
    bad = (
        "Div,Date,HomeTeam,AwayTeam,FTHG,FTAG,FTR\n"
        "E0,10/08/2024,Arsenal,Arsenal,1,0,H\n"
    )
    result = parse_football_data_csv(bad.encode("utf-8"))
    assert result.matches[0].importable is False
    assert any(i.issue_code == "same_team_home_away" for i in result.matches[0].issues)


def test_null_not_zero_for_missing_stats():
    csv = (
        "Div,Date,HomeTeam,AwayTeam,FTHG,FTAG,FTR,HS,AS\n"
        "E0,10/08/2024,A,B,1,0,H,,\n"
    )
    result = parse_football_data_csv(csv.encode("utf-8"))
    m = result.matches[0]
    assert m.home_shots is None
    assert m.away_shots is None
    assert m.bet365_home is None


def test_duplicate_match_flagged():
    dup = (
        "Div,Date,HomeTeam,AwayTeam,FTHG,FTAG,FTR\n"
        "E0,10/08/2024,A,B,1,0,H\n"
        "E0,10/08/2024,A,B,1,0,H\n"
    )
    result = parse_football_data_csv(dup.encode("utf-8"))
    assert any(i.issue_code == "duplicate_match" for i in result.matches[1].issues)


def test_unexpected_columns_preserved_in_raw():
    csv = (
        "Div,Date,HomeTeam,AwayTeam,FTHG,FTAG,FTR,PSH,WeirdCol\n"
        "E0,10/08/2024,A,B,1,0,H,2.10,xyz\n"
    )
    result = parse_football_data_csv(csv.encode("utf-8"))
    assert "PSH" in result.unexpected_columns
    assert "WeirdCol" in result.unexpected_columns
    assert result.matches[0].raw["PSH"] == "2.10"
    assert result.matches[0].raw["WeirdCol"] == "xyz"
