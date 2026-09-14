"""Segnali V2.5: le stesse regole Excel della V2 (matrice SI/NO e consenso), su quote
riportate alla scala della V2.

Le soglie delle regole (es. quota X >= 4,8, differenza 1-2 > 1,5) sono state tarate sulle
quote V2, che erano medie di quote e quindi piu' alte e piu' distanti tra loro. Le quote
V2.5 (1/probabilita' normalizzata) sono su un'altra scala: applicando le soglie cosi'
com'erano, molti segnali non si accenderebbero piu' o si accenderebbero a caso.
Ogni quota V2.5 viene quindi portata alla quota V2 con lo stesso percentile nella
stagione 2021/22 (solo valori pre-partita): l'ordine delle partite resta quello della
V2.5, la selettivita' delle regole resta quella che l'utente ha costruito.
"""

from __future__ import annotations

from typing import Any

from app.services.cecchino.cecchino_signals_matrix import build_signals_matrix
from app.services.cecchino_data_lab.historical_signal_extraction import build_market_signal_index
from app.services.cecchino_v25 import scales

MODULE_VERSION = "cecchino_v25_signals_v1"

QUOTA_SCALES = {
    "q1": ("sig_v25_q1", "sig_v2_q1"),
    "qx": ("sig_v25_qx", "sig_v2_qx"),
    "q2": ("sig_v25_q2", "sig_v2_q2"),
    "under_2_5": ("sig_v25_under_2_5", "sig_v2_under_2_5"),
}


def mapped_quotas(final: dict[str, Any], under_2_5_odd: float | None) -> dict[str, float | None]:
    raw = {"q1": final.get("quota_1"), "qx": final.get("quota_x"), "q2": final.get("quota_2"), "under_2_5": under_2_5_odd}
    return {name: scales.map_distribution(raw[name], src, dst) for name, (src, dst) in QUOTA_SCALES.items()}


def build_signals_v25(
    *,
    final: dict[str, Any],
    under_2_5_odd: float | None,
    sample_home_away_split: int,
) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    mapped = mapped_quotas(final, under_2_5_odd)
    q1, qx, q2 = mapped["q1"], mapped["qx"], mapped["q2"]
    matrix = build_signals_matrix(
        q1=q1,
        qx=qx,
        q2=q2,
        sample_home_away_split=sample_home_away_split,
        prob_1=1.0 / q1 if q1 else None,
        prob_x=1.0 / qx if qx else None,
        prob_2=1.0 / q2 if q2 else None,
        under_2_5_cecchino_odd=mapped["under_2_5"],
    )
    payload = {
        "module_version": MODULE_VERSION,
        "scales_version": scales.scales_version(),
        "v25_quotas": {
            "q1": final.get("quota_1"),
            "qx": final.get("quota_x"),
            "q2": final.get("quota_2"),
            "under_2_5": under_2_5_odd,
        },
        "v2_scale_quotas": {k: round(v, 4) if v is not None else None for k, v in mapped.items()},
        "default_matrix": matrix,
    }
    return payload, build_market_signal_index(matrix)
