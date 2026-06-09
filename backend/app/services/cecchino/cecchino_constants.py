"""Costanti Cecchino (indipendenti da model_version SOT)."""

from __future__ import annotations

CECCHINO_VERSION = "cecchino_v0_4_bookmaker_kpi"

CECCHINO_DELTA_LINEAR_THRESHOLD = 17
CECCHINO_DELTA_STRONG_THRESHOLD = 31

PROVIDER_API_FOOTBALL = "api_football"

CECCHINO_BOOKMAKER: dict[str, str | int] = {
    "provider_source": PROVIDER_API_FOOTBALL,
    "provider_bookmaker_id": 3,
    "name": "Betfair",
}

CECCHINO_REQUIRED_BOOKMAKER_IDS: list[int] = [3]

CECCHINO_TODAY_BOOKMAKERS: list[dict[str, str | int]] = [CECCHINO_BOOKMAKER]

# Cecchino classico / sync competizione (3 bookmaker)
CECCHINO_BOOKMAKERS: list[dict[str, str | int]] = [
    {"provider_source": PROVIDER_API_FOOTBALL, "provider_bookmaker_id": "8", "name": "Bet365"},
    {"provider_source": PROVIDER_API_FOOTBALL, "provider_bookmaker_id": "3", "name": "Betfair"},
    {"provider_source": PROVIDER_API_FOOTBALL, "provider_bookmaker_id": "4", "name": "Pinnacle"},
]

# Solo tab debug globale /bookmakers
BOOKMAKER_DEBUG_IDS: list[int] = [8, 3, 4]

PICCHETTO_KEY_HOME_AWAY = "home_away"
PICCHETTO_KEY_TOTALS = "totals"
PICCHETTO_KEY_LAST5_HOME_AWAY = "last5_home_away"
PICCHETTO_KEY_LAST6_TOTALS = "last6_totals"

# Chiavi contesto dati (8 slice)
KEY_HOME_CONTEXT = "home_context"
KEY_AWAY_CONTEXT = "away_context"
KEY_HOME_TOTAL = "home_total"
KEY_AWAY_TOTAL = "away_total"
KEY_HOME_RECENT_CONTEXT_5 = "home_recent_context_5"
KEY_AWAY_RECENT_CONTEXT_5 = "away_recent_context_5"
KEY_HOME_RECENT_TOTAL_6 = "home_recent_total_6"
KEY_AWAY_RECENT_TOTAL_6 = "away_recent_total_6"

INPUT_SNAPSHOT_CONTEXT_KEYS: tuple[str, ...] = (
    KEY_HOME_CONTEXT,
    KEY_AWAY_CONTEXT,
    KEY_HOME_TOTAL,
    KEY_AWAY_TOTAL,
    KEY_HOME_RECENT_CONTEXT_5,
    KEY_AWAY_RECENT_CONTEXT_5,
    KEY_HOME_RECENT_TOTAL_6,
    KEY_AWAY_RECENT_TOTAL_6,
)

CONTEXT_SLICE_LABELS: dict[str, str] = {
    KEY_HOME_CONTEXT: "Casa split casalinghe",
    KEY_AWAY_CONTEXT: "Trasferta split esterne",
    KEY_HOME_TOTAL: "Totali casa",
    KEY_AWAY_TOTAL: "Totali trasferta",
    KEY_HOME_RECENT_CONTEXT_5: "Ultime 5 casalinghe",
    KEY_AWAY_RECENT_CONTEXT_5: "Ultime 5 esterne",
    KEY_HOME_RECENT_TOTAL_6: "Ultime 6 totali casa",
    KEY_AWAY_RECENT_TOTAL_6: "Ultime 6 totali trasferta",
}

TARGET_RECENT_CONTEXT = 5
TARGET_RECENT_TOTAL = 6

CECCHINO_1X2_WEIGHTS_VERSION = "1x2_weights_30_30_20_20"
CECCHINO_GOAL_WEIGHTS_VERSION = "goal_weights_20_30_20_30"

CECCHINO_1X2_WEIGHTS: dict[str, float] = {
    PICCHETTO_KEY_TOTALS: 0.30,
    PICCHETTO_KEY_HOME_AWAY: 0.30,
    PICCHETTO_KEY_LAST6_TOTALS: 0.20,
    PICCHETTO_KEY_LAST5_HOME_AWAY: 0.20,
}

CECCHINO_GOAL_MARKET_WEIGHTS: dict[str, float] = {
    PICCHETTO_KEY_TOTALS: 0.20,
    PICCHETTO_KEY_HOME_AWAY: 0.30,
    PICCHETTO_KEY_LAST6_TOTALS: 0.20,
    PICCHETTO_KEY_LAST5_HOME_AWAY: 0.30,
}

# Alias retrocompatibile per engine 1X2 e debug picchetti 1/X/2
FINAL_QUOTA_WEIGHTS: dict[str, float] = dict(CECCHINO_1X2_WEIGHTS)

# Modelli backtest pesi 1X2 (Monitoraggio Segnali — confronto A–F)
CECCHINO_WEIGHT_MODELS: dict[str, dict[str, object]] = {
    "A": {
        "label": "A – Forma Recente Predominante",
        "short_label": "Modello A",
        "totals": 0.20,
        "home_away": 0.20,
        "last6_totals": 0.35,
        "last5_home_away": 0.25,
    },
    "B": {
        "label": "B – Forma Recente",
        "short_label": "Modello B",
        "description": "Primo modello utilizzato",
        "totals": 0.25,
        "home_away": 0.20,
        "last6_totals": 0.35,
        "last5_home_away": 0.20,
    },
    "C": {
        "label": "C – Forma Recente Bilanciata",
        "short_label": "Modello C",
        "totals": 0.20,
        "home_away": 0.20,
        "last6_totals": 0.30,
        "last5_home_away": 0.30,
    },
    "D": {
        "label": "D – Compromesso",
        "short_label": "Modello D",
        "totals": 0.20,
        "home_away": 0.25,
        "last6_totals": 0.30,
        "last5_home_away": 0.25,
    },
    "E": {
        "label": "E – Equilibrato",
        "short_label": "Modello E",
        "totals": 0.30,
        "home_away": 0.25,
        "last6_totals": 0.25,
        "last5_home_away": 0.20,
    },
    "F": {
        "label": "F – Conservativo",
        "short_label": "Modello F",
        "description": "Modello attuale",
        "totals": 0.30,
        "home_away": 0.30,
        "last6_totals": 0.20,
        "last5_home_away": 0.20,
    },
}

CECCHINO_WEIGHT_MODEL_KEYS: tuple[str, ...] = ("A", "B", "C", "D", "E", "F")
CECCHINO_DEFAULT_WEIGHT_MODEL_KEY = "F"

_WEIGHT_MODEL_TO_PICCHETTO: dict[str, str] = {
    "totals": PICCHETTO_KEY_TOTALS,
    "home_away": PICCHETTO_KEY_HOME_AWAY,
    "last6_totals": PICCHETTO_KEY_LAST6_TOTALS,
    "last5_home_away": PICCHETTO_KEY_LAST5_HOME_AWAY,
}


def get_cecchino_weight_model(model_key: str) -> dict[str, object]:
    key = str(model_key).upper()
    if key not in CECCHINO_WEIGHT_MODELS:
        raise KeyError(f"Unknown Cecchino weight model: {model_key}")
    return dict(CECCHINO_WEIGHT_MODELS[key])


def model_weights_json(model_key: str) -> dict[str, float]:
    model = get_cecchino_weight_model(model_key)
    return {
        "totals": float(model["totals"]),  # type: ignore[arg-type]
        "home_away": float(model["home_away"]),  # type: ignore[arg-type]
        "last6_totals": float(model["last6_totals"]),  # type: ignore[arg-type]
        "last5_home_away": float(model["last5_home_away"]),  # type: ignore[arg-type]
    }


def model_weights_to_picchetto_map(model_key: str) -> dict[str, float]:
    weights = model_weights_json(model_key)
    return {
        _WEIGHT_MODEL_TO_PICCHETTO[k]: v
        for k, v in weights.items()
    }


def model_weights_version(model_key: str) -> str:
    w = model_weights_json(model_key)
    pct = lambda x: int(round(float(x) * 100))  # noqa: E731
    return (
        f"model_{model_key.upper()}_{pct(w['totals'])}_{pct(w['home_away'])}_"
        f"{pct(w['last6_totals'])}_{pct(w['last5_home_away'])}"
    )


def format_model_weights_display(model_key: str) -> str:
    w = model_weights_json(model_key)
    pct = lambda x: int(round(float(x) * 100))  # noqa: E731
    return (
        f"{pct(w['totals'])} / {pct(w['home_away'])} / "
        f"{pct(w['last6_totals'])} / {pct(w['last5_home_away'])}"
    )


def format_model_weights_subtitle(model_key: str) -> str:
    w = model_weights_json(model_key)
    pct = lambda x: int(round(float(x) * 100))  # noqa: E731
    return (
        f"Pesi: Totali {pct(w['totals'])}%, Casa/Trasferta {pct(w['home_away'])}%, "
        f"Ultime 6 {pct(w['last6_totals'])}%, Ultime 5 C/F {pct(w['last5_home_away'])}%"
    )


def model_meta_for_key(model_key: str) -> dict[str, object]:
    model = get_cecchino_weight_model(model_key)
    weights = model_weights_json(model_key)
    return {
        "model_key": model_key.upper(),
        "model_label": str(model["label"]),
        "weights_version": model_weights_version(model_key),
        "weights_json": weights,
    }


def validate_cecchino_weight_models() -> None:
    expected = set(CECCHINO_WEIGHT_MODEL_KEYS)
    if set(CECCHINO_WEIGHT_MODELS.keys()) != expected:
        raise ValueError(
            f"CECCHINO_WEIGHT_MODELS must contain exactly {sorted(expected)}",
        )
    for key in CECCHINO_WEIGHT_MODEL_KEYS:
        weights = model_weights_json(key)
        total = sum(weights.values())
        if abs(total - 1.0) > 1e-9:
            raise ValueError(f"Model {key} weights must sum to 1.0, got {total}")
    f_map = model_weights_to_picchetto_map("F")
    for pic_key, live_weight in CECCHINO_1X2_WEIGHTS.items():
        if abs(f_map[pic_key] - live_weight) > 1e-9:
            raise ValueError(f"Model F picchetto {pic_key} must match CECCHINO_1X2_WEIGHTS")


def validate_cecchino_weight_sets() -> None:
    """Verifica che i pesi 1X2 e goal market sommino a 1.0."""
    for name, weights in (
        ("CECCHINO_1X2_WEIGHTS", CECCHINO_1X2_WEIGHTS),
        ("CECCHINO_GOAL_MARKET_WEIGHTS", CECCHINO_GOAL_MARKET_WEIGHTS),
    ):
        total = sum(weights.values())
        if abs(total - 1.0) > 1e-9:
            raise ValueError(f"{name} must sum to 1.0, got {total}")
    validate_cecchino_weight_models()


validate_cecchino_weight_sets()

STATUS_AVAILABLE = "available"
STATUS_INSUFFICIENT_DATA = "insufficient_data"
STATUS_PARTIAL_LOW_SAMPLE = "partial_low_sample"
STATUS_ERROR = "error"
STATUS_PENDING_FORMULA = "pending_formula_extraction"

WARNING_ZERO_MATCHES = "zero_matches_in_context"
WARNING_ZERO_PROBABILITY = "zero_probability"
WARNING_PARTIAL_RECENT_SAMPLE = "partial_recent_sample"
WARNING_LOW_SAMPLE = "low_sample"

LEAKAGE_PASSED = "passed"
LEAKAGE_FAILED = "failed"
LEAKAGE_UNDEFINED = "undefined"

PLACEHOLDER_SIGNALS = {"status": STATUS_PENDING_FORMULA}
PLACEHOLDER_RELIABILITY = {"status": "not_implemented_yet"}
PLACEHOLDER_BOOKMAKER = {"status": "pending_bookmaker_odds"}

# Picchetti utilizzabili per quota finale (incluso campione parziale)
PICCHETTO_STATUSES_FOR_FINAL = frozenset({STATUS_AVAILABLE, STATUS_PARTIAL_LOW_SAMPLE})
