"""Costanti della V5 dal vivo (docs/v5/LIVE_REGOLE.md). I numeri vengono dagli esami in docs/v5/esami/."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date

VERSION = "v5_live_v1_20261022"

STATUS_ADVISED = "consigliata"
STATUS_OBSERVATION = "osservazione"

BOOKMAKER_BET365_ID = 8
BOOKMAKER_BETFAIR_ID = 3
BOOKMAKERS = (BOOKMAKER_BET365_ID, BOOKMAKER_BETFAIR_ID)


@dataclass(frozen=True)
class StatSpecialist:
    key: str
    label: str
    stat: str  # chiave della statistica nelle quote V4 (STAT:<stat>:...) e nello storico
    status: str
    k: float  # restringimento della forza delle squadre verso 1 (partite)
    gamma: float  # peso dei gol attesi V3
    delta: float  # peso del fattore arbitro (solo cartellini)
    r_team: float  # dispersione binomiale negativa per squadra
    r_total: float  # dispersione per il totale


# Parametri scelti sulle stagioni di sviluppo (docs/v5/esami/STATISTICI_V1_RISULTATO.md).
STAT_SPECIALISTS: tuple[StatSpecialist, ...] = (
    StatSpecialist("tiri_porta", "Tiri in porta", "sot", STATUS_ADVISED, 20.0, 0.25, 0.0, 32.31, 87.64),
    StatSpecialist("angoli", "Angoli", "corners", STATUS_OBSERVATION, 20.0, 0.15, 0.0, 12.51, 67.27),
    StatSpecialist("cartellini", "Cartellini", "cards", STATUS_OBSERVATION, 20.0, 0.0, 0.5, 22.76, 16.13),
)
STAT_SPECIALIST_BY_KEY = {s.key: s for s in STAT_SPECIALISTS}

VALORE_KEY = "valore"
VALORE_LABEL = "Valore"

# Finestra della forza delle squadre e minimi dell'esame.
TEAM_WINDOW = 30
LEAGUE_MIN_MATCHES = 20  # partite precedenti nel campionato-stagione per valutare
LEAGUE_FALLBACK_BELOW = 30  # sotto, la media del campionato usa tutto lo storico della divisione
REFEREE_SHRINK = 10.0

# Regola di decisione degli specialisti statistici.
STAT_PRUDENCE = 0.8  # probabilita' prudente = 0.5 + 0.8 * (p - 0.5)
STAT_MIN_QUOTA = 1.50
STAT_MAX_QUOTA = 3.00
MIN_EDGE = 1.03
STAT_MAX_PER_DAY = 5

# Linee ammesse per statistica e lato (fuori da qui le quote V4 non sono affidabili: Multicorners, Range, ...).
VALID_LINES: dict[tuple[str, str], tuple[float, float]] = {
    ("sot", "total"): (4.5, 14.5),
    ("sot", "home"): (1.5, 8.5),
    ("sot", "away"): (1.5, 8.5),
    ("corners", "total"): (6.5, 13.5),
    ("corners", "home"): (1.5, 9.5),
    ("corners", "away"): (1.5, 9.5),
    ("cards", "total"): (1.5, 8.5),
    ("cards", "home"): (0.5, 4.5),
    ("cards", "away"): (0.5, 4.5),
}

# Valore v1 (osservazione): fascia di quota, massimo giornaliero.
VALORE_MIN_QUOTA = 1.80
VALORE_MAX_QUOTA = 2.20
VALORE_MAX_PER_DAY = 15
VALORE_SMOOTH = 50.0  # peso della lisciatura verso il centro della fascia
VALORE_MARKETS = (
    "HOME", "DRAW", "AWAY", "ONE_X", "ONE_TWO", "X_TWO",
    "OVER_1_5", "UNDER_1_5", "OVER_2_5", "UNDER_2_5", "OVER_3_5", "UNDER_3_5",
    "HOME_PT", "DRAW_PT", "AWAY_PT",
)

# Taratura Valore: per mercato, fascia (larga 5 punti, indice 0-19) -> (partite, vinte), V3 run 11 su 2021/22-2024/25.
_VALORE_RAW = {
    "AWAY": "0:68:2,1:362:21,2:964:82,3:2074:304,4:3486:699,5:4379:1157,6:3736:1146,7:2671:1068,8:1683:764,9:989:495,10:568:326,11:340:231,12:176:124,13:119:88,14:53:37,15:18:13,16:7:6",
    "AWAY_PT": "1:193:16,2:1087:135,3:3924:651,4:6714:1434,5:5129:1408,6:2596:891,7:1199:494,8:507:245,9:222:113,10:80:46,11:33:22,12:8:2,13:1:1",
    "DRAW": "1:51:3,2:272:29,3:1156:197,4:6249:1507,5:11301:3126,6:2575:781,7:89:29",
    "DRAW_PT": "3:5:0,4:41:12,5:207:53,6:1140:372,7:5745:2164,8:9617:4070,9:4379:2012,10:529:263,11:30:18",
    "HOME": "0:1:0,1:38:2,2:167:20,3:380:50,4:818:160,5:1474:361,6:2486:748,7:3392:1222,8:3723:1628,9:3284:1575,10:2351:1239,11:1513:918,12:867:605,13:541:388,14:307:241,15:210:176,16:87:73,17:43:41,18:11:11",
    "HOME_PT": "1:6:0,2:159:17,3:734:107,4:2355:502,5:4894:1330,6:5549:1800,7:3984:1487,8:2116:949,9:1002:501,10:469:268,11:260:160,12:95:59,13:49:36,14:18:13,15:3:3",
    "ONE_TWO": "12:89:60,13:2575:1794,14:11301:8175,15:6249:4742,16:1156:959,17:272:243,18:51:48",
    "ONE_X": "3:7:1,4:18:5,5:53:16,6:119:31,7:176:52,8:340:109,9:568:242,10:989:494,11:1683:919,12:2671:1603,13:3736:2590,14:4379:3222,15:3486:2787,16:2074:1770,17:964:882,18:362:341,19:68:66",
    "OVER_1_5": "9:24:13,10:102:57,11:444:289,12:1669:1130,13:3732:2616,14:5279:3801,15:5265:4048,16:3535:2890,17:1420:1198,18:214:199,19:9:9",
    "OVER_2_5": "4:44:15,5:247:79,6:917:370,7:2357:979,8:3714:1618,9:4168:1986,10:3850:2018,11:3006:1727,12:1860:1120,13:990:636,14:376:260,15:119:95,16:37:28,17:8:6",
    "OVER_3_5": "1:51:8,2:724:100,3:2979:608,4:4751:1149,5:4716:1287,6:3634:1092,7:2421:859,8:1337:531,9:643:282,10:270:138,11:104:54,12:43:27,13:14:10,14:5:4,15:1:0",
    "UNDER_1_5": "0:9:0,1:214:15,2:1420:222,3:3535:645,4:5265:1217,5:5279:1478,6:3732:1116,7:1669:539,8:444:155,9:102:45,10:24:11",
    "UNDER_2_5": "2:8:2,3:37:9,4:119:24,5:376:116,6:990:354,7:1860:740,8:3006:1279,9:3850:1832,10:4168:2182,11:3714:2096,12:2357:1378,13:917:547,14:247:168,15:44:29",
    "UNDER_3_5": "4:1:1,5:5:1,6:14:4,7:43:16,8:104:50,9:270:132,10:643:361,11:1337:806,12:2421:1562,13:3634:2542,14:4716:3429,15:4751:3602,16:2979:2371,17:724:624,18:51:43",
    "X_TWO": "1:11:0,2:43:2,3:87:14,4:210:34,5:307:66,6:541:153,7:867:262,8:1513:595,9:2351:1112,10:3283:1708,11:3724:2096,12:3392:2170,13:2486:1738,14:1474:1113,15:818:658,16:380:330,17:167:147,18:38:36,19:1:1",
}


def _parse_calibration(raw: dict[str, str]) -> dict[str, dict[int, tuple[int, int]]]:
    out: dict[str, dict[int, tuple[int, int]]] = {}
    for market, text in raw.items():
        bins: dict[int, tuple[int, int]] = {}
        for part in text.split(","):
            b, n, w = (int(x) for x in part.split(":"))
            bins[b] = (n, w)
        out[market] = bins
    return out


VALORE_CALIBRATION = _parse_calibration(_VALORE_RAW)


# Piste dei campionati in osservazione (docs/campionati/PISTE_V1_PREREGISTRAZIONE.md): solo quota Bet365, nessun massimo.
LEAGUE_LEADS_FROM = date(2026, 10, 25)

@dataclass(frozen=True)
class LeagueLead:
    key: str
    label: str
    market: str  # chiave classica V4 (DRAW, UNDER_3_5, OVER_1_5)
    leagues: dict[str, float]  # campionato -> frequenza reale 2021/22-2025/26
    min_quota: float | None = None  # fascia fissa; senza, la quota minima e' 1 / frequenza
    max_quota: float | None = None

    def quota_range(self, league: str) -> tuple[float, float]:
        if self.min_quota is not None:
            return self.min_quota, self.max_quota or 100.0
        rate = self.leagues[league]
        return math.ceil(100.0 / rate - 1e-9) / 100.0, 100.0


LEAGUE_LEADS: tuple[LeagueLead, ...] = (
    LeagueLead("camp_pareggio_i2", "Pareggio Serie B", "DRAW", {"I2": 0.321}, 2.50, 3.49),
    LeagueLead(
        "camp_under35",
        "Under 3,5 campionati",
        "UNDER_3_5",
        {"I1": 0.737, "E1": 0.759, "SP1": 0.752, "T1": 0.693, "B1": 0.681, "D2": 0.663},
    ),
    LeagueLead("camp_over15", "Over 1,5 campionati", "OVER_1_5", {"D1": 0.836, "E0": 0.799, "I2": 0.724}),
)

# Combo sulla stessa partita (docs/combo/COMBO_V1_*.md): osservazione dal 25/10/2026, una per partita.
COMBO_KEY = "combo"
COMBO_LABEL = "Combo"
COMBO_FROM = date(2026, 10, 25)

SPECIALIST_LABELS: dict[str, str] = {
    **{s.key: s.label for s in STAT_SPECIALISTS},
    VALORE_KEY: VALORE_LABEL,
    **{lead.key: lead.label for lead in LEAGUE_LEADS},
    COMBO_KEY: COMBO_LABEL,
}
