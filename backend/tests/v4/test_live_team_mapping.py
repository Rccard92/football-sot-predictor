"""Mappa squadre API-Football -> football-data: normalizzazione, alias, fuzzy, ambiguita', copertura sui CSV reali."""

from __future__ import annotations

import pytest

from app.services.cecchino_v4.constants import LEAGUES
from app.services.cecchino_v4.history.football_data import load_history
from app.services.cecchino_v4.history.team_mapping import (
    core_name,
    history_team_names,
    load_aliases,
    map_team,
    map_team_detail,
    normalize_name,
)

# Nomi come li scrive API-Football per le squadre 2025/26 dei 16 campionati (verificati al deploy con /teams).
API_NAMES_2526: dict[str, list[str]] = {
    "E0": ["Arsenal", "Aston Villa", "Bournemouth", "Brentford", "Brighton", "Burnley", "Chelsea", "Crystal Palace", "Everton", "Fulham", "Leeds", "Liverpool", "Manchester City", "Manchester United", "Newcastle", "Nottingham Forest", "Sunderland", "Tottenham", "West Ham", "Wolves"],
    "E1": ["Birmingham", "Blackburn", "Bristol City", "Charlton", "Coventry", "Derby", "Hull City", "Ipswich", "Leicester", "Middlesbrough", "Millwall", "Norwich", "Oxford United", "Portsmouth", "Preston", "QPR", "Sheffield Utd", "Sheffield Wednesday", "Southampton", "Stoke City", "Swansea", "Watford", "West Brom", "Wrexham"],
    "E2": ["AFC Wimbledon", "Barnsley", "Blackpool", "Bolton", "Bradford City", "Burton Albion", "Cardiff", "Doncaster", "Exeter City", "Huddersfield", "Leyton Orient", "Lincoln", "Luton", "Mansfield Town", "Northampton", "Peterborough", "Plymouth", "Port Vale", "Reading", "Rotherham", "Stevenage", "Stockport County", "Wigan", "Wycombe"],
    "E3": ["Accrington ST", "Barnet", "Barrow", "Bristol Rovers", "Bromley", "Cambridge United", "Cheltenham", "Chesterfield", "Colchester", "Crawley Town", "Crewe", "Fleetwood Town", "Gillingham", "Grimsby", "Harrogate Town", "MK Dons", "Newport County", "Notts County", "Oldham", "Salford City", "Shrewsbury", "Swindon Town", "Tranmere", "Walsall"],
    "I1": ["Atalanta", "Bologna", "Cagliari", "Como", "Cremonese", "Fiorentina", "Genoa", "Inter", "Juventus", "Lazio", "Lecce", "AC Milan", "Napoli", "Parma", "Pisa", "AS Roma", "Sassuolo", "Torino", "Udinese", "Verona"],
    "I2": ["Avellino", "Bari", "Carrarese", "Catanzaro", "Cesena", "Empoli", "Frosinone", "Juve Stabia", "Mantova", "Modena", "Monza", "Padova", "Palermo", "Pescara", "Reggiana", "Sampdoria", "Spezia", "Sudtirol", "Venezia", "Virtus Entella"],
    "SP1": ["Alaves", "Athletic Club", "Atletico Madrid", "Barcelona", "Real Betis", "Celta Vigo", "Elche", "Espanyol", "Getafe", "Girona", "Levante", "Mallorca", "Osasuna", "Real Oviedo", "Real Madrid", "Sevilla", "Real Sociedad", "Valencia", "Rayo Vallecano", "Villarreal"],
    "SP2": ["Albacete", "Almeria", "FC Andorra", "Burgos", "Cadiz", "Castellon", "Ceuta", "Cordoba", "Cultural Leonesa", "Eibar", "Granada CF", "Huesca", "Deportivo La Coruna", "Las Palmas", "Leganes", "Malaga", "Mirandes", "Racing Santander", "Real Sociedad II", "Sporting Gijon", "Real Valladolid", "Real Zaragoza"],
    "D1": ["FC Augsburg", "Bayern München", "Borussia Dortmund", "Eintracht Frankfurt", "1. FC Köln", "SC Freiburg", "Hamburger SV", "1. FC Heidenheim", "1899 Hoffenheim", "Bayer Leverkusen", "Borussia Mönchengladbach", "FSV Mainz 05", "RB Leipzig", "FC St. Pauli", "VfB Stuttgart", "Union Berlin", "Werder Bremen", "VfL Wolfsburg"],
    "D2": ["Arminia Bielefeld", "VfL Bochum", "Eintracht Braunschweig", "SV Darmstadt 98", "Dynamo Dresden", "SV Elversberg", "Fortuna Dusseldorf", "SpVgg Greuther Furth", "Hannover 96", "Hertha BSC", "Holstein Kiel", "1. FC Kaiserslautern", "Karlsruher SC", "1. FC Magdeburg", "1. FC Nurnberg", "SC Paderborn 07", "Preussen Munster", "FC Schalke 04"],
    "F1": ["Angers", "Auxerre", "Stade Brestois 29", "Le Havre", "Lens", "Lille", "Lorient", "Lyon", "Marseille", "Metz", "Monaco", "Nantes", "Nice", "Paris FC", "Paris Saint Germain", "Rennes", "Strasbourg", "Toulouse"],
    "F2": ["Amiens", "Annecy", "Bastia", "Boulogne", "Clermont Foot", "USL Dunkerque", "Grenoble", "Guingamp", "Laval", "Le Mans", "Montpellier", "Nancy", "Pau", "Red Star", "Reims", "Rodez", "Saint Etienne", "Troyes"],
    "N1": ["AZ Alkmaar", "Ajax", "Excelsior", "Feyenoord", "Fortuna Sittard", "GO Ahead Eagles", "FC Groningen", "Heerenveen", "Heracles", "NAC Breda", "NEC Nijmegen", "PSV Eindhoven", "Sparta Rotterdam", "Telstar", "Twente", "Utrecht", "FC Volendam", "PEC Zwolle"],
    "B1": ["Anderlecht", "Royal Antwerp", "Cercle Brugge", "Charleroi", "Club Brugge KV", "FCV Dender EH", "Genk", "Gent", "KV Mechelen", "OH Leuven", "RAAL La Louvière", "Sint-Truiden", "Union St. Gilloise", "Standard Liege", "Zulte Waregem", "Westerlo"],
    "P1": ["AVS", "Alverca", "Arouca", "Benfica", "Casa Pia", "Estoril", "Estrela", "Famalicao", "GIL Vicente", "Vitoria Guimaraes", "Moreirense", "Nacional", "FC Porto", "Rio Ave", "Santa Clara", "Sporting Braga", "Sporting CP", "Tondela"],
    "T1": ["Alanyaspor", "Antalyaspor", "Besiktas", "Istanbul Basaksehir", "Eyupspor", "Fenerbahce", "Galatasaray", "Gaziantep FK", "Genclerbirligi", "Goztepe", "Fatih Karagumruk", "Kasimpasa", "Kayserispor", "Kocaelispor", "Konyaspor", "Caykur Rizespor", "Samsunspor", "Trabzonspor"],
}


def test_normalize_name_strips_accents_sigle_and_punctuation():
    assert normalize_name("Borussia Mönchengladbach") == "borussia monchengladbach"
    assert normalize_name("1. FC Köln") == "1 koln"
    assert normalize_name("AC Milan") == "milan"
    assert normalize_name("AS Roma") == "roma"
    assert normalize_name("SSC Napoli") == "napoli"
    assert normalize_name("Nott'm Forest") == "nott m forest"
    assert normalize_name("Preußen Münster") == "preussen munster"
    assert normalize_name("Beşiktaş") == "besiktas"
    assert normalize_name("") == ""
    assert core_name("Hull City") == "hull" and core_name("Real Betis") == "betis" and core_name("Paris SG") == "paris sg"


def test_alias_file_loads_and_covers_required_pairs():
    glob, per_league = load_aliases()
    required = {
        "Manchester United": "Man United", "Manchester City": "Man City", "Wolverhampton Wanderers": "Wolves",
        "Nottingham Forest": "Nott'm Forest", "Sheffield Utd": "Sheffield United", "AC Milan": "Milan", "AS Roma": "Roma",
        "Hellas Verona": "Verona", "Atletico Madrid": "Ath Madrid", "Athletic Club": "Ath Bilbao", "Real Betis": "Betis",
        "Celta Vigo": "Celta", "Rayo Vallecano": "Vallecano", "Bayern München": "Bayern Munich", "Borussia Dortmund": "Dortmund",
        "Bayer Leverkusen": "Leverkusen", "Borussia Mönchengladbach": "M'gladbach", "Eintracht Frankfurt": "Ein Frankfurt",
        "FC Koln": "FC Koln", "Paris Saint Germain": "Paris SG", "Olympique Marseille": "Marseille", "Olympique Lyonnais": "Lyon",
        "Saint Etienne": "St Etienne", "PSV Eindhoven": "PSV Eindhoven", "Club Brugge KV": "Club Brugge", "Sporting CP": "Sp Lisbon",
        "SL Benfica": "Benfica", "FC Porto": "Porto", "Istanbul Basaksehir": "Buyuksehyr", "Galatasaray": "Galatasaray",
    }
    for api, hist in required.items():
        assert glob.get(normalize_name(api)) == hist, api
    assert per_league["SP2"][normalize_name("Sociedad")] == "Sociedad B"


def test_map_team_exact_alias_fuzzy_and_none():
    names = {"Milan", "Inter", "Juventus", "Napoli", "Verona", "Roma"}
    assert map_team("I1", "Inter", names) == ("Inter", 1.0)
    assert map_team("I1", "AC Milan", names) == ("Milan", 1.0)  # sigla tolta -> uguaglianza
    assert map_team("I1", "Hellas Verona", names) == ("Verona", 1.0)  # alias
    assert map_team_detail("I1", "AS Roma", names).method in {"alias", "exact"}
    assert map_team("I1", "Bologna", names)[0] is None  # squadra assente dallo storico: nessuna mappa
    assert map_team("I1", "Inter", set()) == (None, 0.0)


def test_map_team_generic_words_and_containment():
    english = {"Hull", "Stoke", "Bristol City", "Bristol Rvs", "Sheffield United", "Sheffield Weds", "Paris SG", "Paris FC"}
    assert map_team("E1", "Hull City", english)[0] == "Hull"
    assert map_team("E1", "Stoke City", english)[0] == "Stoke"
    assert map_team("E1", "Sheffield Wednesday", english)[0] == "Sheffield Weds"
    assert map_team("E1", "Sheffield Utd", english)[0] == "Sheffield United"
    # "Paris" non deve scivolare su "Paris SG": la parola in piu' non e' generica
    assert map_team("F1", "Paris FC", english)[0] == "Paris FC"
    assert map_team("F1", "Paris Saint Germain", english)[0] == "Paris SG"


def test_map_team_ambiguous_gets_low_confidence():
    names = {"Sociedad", "Sociedad B"}
    detail = map_team_detail("SP1", "Real Sociedad", names)
    assert detail.history_name == "Sociedad"  # alias del campionato risolve
    # due candidati quasi uguali -> ambiguo, confidenza <= 0,5 (il job non applica la mappa, la segnala)
    detail = map_team_detail("XX", "Atletic Madrid", {"Atletico Madrid", "Athletic Madrid"}, aliases_path="C:/nonexistent_aliases.json")
    assert detail.ambiguous is True and detail.confidence <= 0.5 and len(detail.candidates) == 2
    assert map_team("XX", "Atletic Madrid", {"Atletico Madrid", "Athletic Madrid"})[1] <= 0.5


def test_unknown_name_fails_safely_instead_of_wrong_match():
    turkish = {"Istanbulspor", "Buyuksehyr", "Antalyaspor"}
    detail = map_team_detail("T1", "Istanbul Basaksehir", turkish, aliases_path="C:/nonexistent_aliases.json")
    assert detail.history_name is None  # meglio nessuna mappa che Istanbulspor
    assert map_team("T1", "Istanbul Basaksehir", turkish) == ("Buyuksehyr", 1.0)  # con alias


def test_coverage_on_real_csv_names_all_16_leagues():
    """Ogni squadra 2025/26 dei 16 campionati (nome API-Football) trova il suo nome football-data nei CSV."""
    history = load_history(include_lockbox=True)
    names = history_team_names(history)
    current = history_team_names(load_history(include_lockbox=True, seasons=["2025/2026"]))
    assert set(names) == {lg.code for lg in LEAGUES}
    misses = []
    fuzzy_only_misses = []
    for lg in LEAGUES:
        for api_name in API_NAMES_2526[lg.code]:
            detail = map_team_detail(lg.code, api_name, names[lg.code])
            if detail.history_name not in current[lg.code] or detail.confidence < 0.8:
                misses.append((lg.code, api_name, detail.history_name, detail.confidence))
            no_alias = map_team_detail(lg.code, api_name, names[lg.code], aliases_path="C:/nonexistent_aliases.json")
            if no_alias.history_name is not None and no_alias.confidence >= 0.8 and no_alias.history_name not in current[lg.code]:
                fuzzy_only_misses.append((lg.code, api_name, no_alias.history_name))
    assert misses == []
    assert fuzzy_only_misses == []  # il fuzzy da solo non produce mai un abbinamento sbagliato
    assert sum(len(v) for v in API_NAMES_2526.values()) == 316
