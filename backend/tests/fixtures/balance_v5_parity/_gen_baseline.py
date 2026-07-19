"""One-shot generator — run before refactor; keep resulting JSON committed."""
from __future__ import annotations

import json
from pathlib import Path

from app.services.cecchino.cecchino_balance_analysis import (
    build_cecchino_balance_analysis,
    compute_dominance_pp,
)
from app.services.cecchino.cecchino_icm_analysis import build_cecchino_icm_analysis

SCENARIOS = {
    "equilibrio_forte_x_dominante": dict(
        quota_cecchino_1=2.50,
        quota_cecchino_x=3.20,
        quota_cecchino_2=2.90,
        prob_cecchino_1=31.0,
        prob_cecchino_x=42.0,
        prob_cecchino_2=27.0,
    ),
    "equilibrio_forte_1_dominante": dict(
        quota_cecchino_1=2.50,
        quota_cecchino_x=3.40,
        quota_cecchino_2=2.90,
        prob_cecchino_1=45.0,
        prob_cecchino_x=25.0,
        prob_cecchino_2=30.0,
    ),
    "transizione": dict(
        quota_cecchino_1=2.20,
        quota_cecchino_x=3.50,
        quota_cecchino_2=3.40,
        prob_cecchino_1=40.0,
        prob_cecchino_x=28.0,
        prob_cecchino_2=32.0,
    ),
    "squilibrio_verso_1": dict(
        quota_cecchino_1=1.80,
        quota_cecchino_x=3.80,
        quota_cecchino_2=4.50,
        prob_cecchino_1=55.0,
        prob_cecchino_x=22.0,
        prob_cecchino_2=23.0,
    ),
    "squilibrio_verso_2": dict(
        quota_cecchino_1=4.20,
        quota_cecchino_x=3.60,
        quota_cecchino_2=1.90,
        prob_cecchino_1=22.0,
        prob_cecchino_x=23.0,
        prob_cecchino_2=55.0,
    ),
    "x_prima": dict(
        quota_cecchino_1=2.60,
        quota_cecchino_x=3.10,
        quota_cecchino_2=2.70,
        prob_cecchino_1=30.0,
        prob_cecchino_x=40.0,
        prob_cecchino_2=30.0,
    ),
    "x_seconda": dict(
        quota_cecchino_1=2.40,
        quota_cecchino_x=3.30,
        quota_cecchino_2=2.80,
        prob_cecchino_1=42.0,
        prob_cecchino_x=30.0,
        prob_cecchino_2=28.0,
    ),
    "x_terza": dict(
        quota_cecchino_1=2.10,
        quota_cecchino_x=4.50,
        quota_cecchino_2=3.20,
        prob_cecchino_1=48.0,
        prob_cecchino_x=18.0,
        prob_cecchino_2=34.0,
    ),
    "dati_mancanti": dict(
        quota_cecchino_1=None,
        quota_cecchino_x=3.40,
        quota_cecchino_2=3.60,
        prob_cecchino_1=0.42,
        prob_cecchino_x=0.28,
        prob_cecchino_2=0.30,
    ),
}


def main() -> None:
    out: dict = {}
    for name, kw in SCENARIOS.items():
        bal = build_cecchino_balance_analysis(**kw)
        slice_ = {
            "balance_status": bal.get("status"),
            "balance_version": bal.get("version"),
            "f36": bal.get("f36"),
            "dominance": bal.get("dominance"),
            "draw": bal.get("draw"),
            "inputs": bal.get("inputs"),
            "operational_class_key": (bal.get("operational") or {}).get("class_key"),
            "dominance_pp_fn": compute_dominance_pp(
                kw.get("prob_cecchino_1"),
                kw.get("prob_cecchino_x"),
                kw.get("prob_cecchino_2"),
            ),
        }
        icm = build_cecchino_icm_analysis(balance_analysis=bal, kpi_panel=None)
        slice_["icm"] = {
            "status": icm.get("status"),
            "score": icm.get("score"),
            "class_label": icm.get("class_label") or icm.get("class"),
            "version": icm.get("version"),
        }
        out[name] = slice_

    path = Path(__file__).with_name("live_consumer_slices.json")
    path.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {path} scenarios={len(out)}")


if __name__ == "__main__":
    main()
