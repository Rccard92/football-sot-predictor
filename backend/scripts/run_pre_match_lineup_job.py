#!/usr/bin/env python3
"""
Railway Cron: trigger job formazioni ufficiali pre-match.

Root Directory Railway: backend

Variabili d'ambiente obbligatorie:
  BACKEND_URL  — base URL del backend (es. https://xxx.up.railway.app)
  CRON_SECRET  — stesso valore di ADMIN_CRON_SECRET sul backend

Comando Railway Cron:
  python scripts/run_pre_match_lineup_job.py
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

JOB_PATH = "/api/admin/jobs/pre-match-official-lineups/run"
REQUEST_TIMEOUT_SEC = 120


def normalize_backend_url(raw: str) -> str:
    """Rimuove slash finale e aggiunge https:// se manca il protocollo."""
    url = raw.strip().rstrip("/")
    if not url:
        return ""
    lower = url.lower()
    if not (lower.startswith("http://") or lower.startswith("https://")):
        url = f"https://{url}"
    return url.rstrip("/")


def main() -> int:
    raw_backend_url = (os.environ.get("BACKEND_URL") or "").strip()
    backend_url = normalize_backend_url(raw_backend_url)
    cron_secret = (os.environ.get("CRON_SECRET") or "").strip()

    if not backend_url:
        print("ERRORE: BACKEND_URL non impostata.", file=sys.stderr)
        return 1
    if not cron_secret:
        print("ERRORE: CRON_SECRET non impostata.", file=sys.stderr)
        return 1

    url = f"{backend_url}{JOB_PATH}"
    print(f"BACKEND_URL normalizzato: {backend_url}")
    print(f"endpoint: {url}")
    body = json.dumps(
        {
            "minutes_before": 30,
            "window_minutes": 10,
            "force": False,
            "dry_run": False,
        },
    ).encode("utf-8")

    request = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "X-Admin-Cron-Secret": cron_secret,
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )

    try:
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SEC) as response:
            status_code = response.getcode()
            raw = response.read()
    except urllib.error.HTTPError as exc:
        status_code = exc.code
        raw = exc.read()
    except urllib.error.URLError as exc:
        print(f"ERRORE: richiesta fallita: {exc}", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"ERRORE: {exc}", file=sys.stderr)
        return 1

    try:
        response_text = raw.decode("utf-8")
    except UnicodeDecodeError:
        response_text = repr(raw)

    print(f"status code: {status_code}")
    print(f"response body: {response_text}")

    if 200 <= status_code < 300:
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
