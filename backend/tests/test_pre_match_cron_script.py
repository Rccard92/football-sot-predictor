"""Test normalizzazione BACKEND_URL nello script cron pre-match."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "run_pre_match_lineup_job.py"
_spec = importlib.util.spec_from_file_location("run_pre_match_lineup_job", _SCRIPT_PATH)
_mod = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(_mod)

normalize_backend_url = _mod.normalize_backend_url


def test_normalize_adds_https_without_protocol():
    assert (
        normalize_backend_url("backend-production-5f140.up.railway.app")
        == "https://backend-production-5f140.up.railway.app"
    )


def test_normalize_keeps_https_and_strips_trailing_slash():
    assert normalize_backend_url("https://example.com/") == "https://example.com"


def test_normalize_keeps_http():
    assert normalize_backend_url("http://localhost:8000") == "http://localhost:8000"
