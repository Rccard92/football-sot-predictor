"""Accesso per scheda (29/10/2026): un utente legge solo gli indirizzi delle sue schede."""

from __future__ import annotations

import os

os.environ.setdefault("DATABASE_URL", "postgresql://user:pass@localhost:5432/test")

from app.core.access_control import TAB_KEYS, TAB_RULES, allowed_tab_keys, is_exempt, is_path_allowed
from app.core.user_auth import Principal, generate_password, hash_password, password_problem, verify_password_hash


def test_today_reads_only():
    tabs = frozenset({"cecchino-today"})
    assert is_path_allowed(tabs, "GET", "/api/cecchino/today")
    assert is_path_allowed(tabs, "GET", "/api/cecchino/today/12/kpi-explanations")
    assert is_path_allowed(tabs, "GET", "/api/admin/cecchino/today/scan-jobs/latest")
    assert not is_path_allowed(tabs, "GET", "/api/cecchino/today-other")
    assert not is_path_allowed(tabs, "POST", "/api/admin/cecchino/today/scan-day/start")
    assert not is_path_allowed(tabs, "GET", "/api/cecchino/v4/days")


def test_shared_and_cross_tab_rules():
    assert is_path_allowed(frozenset(), "GET", "/api/competitions/default")
    assert not is_path_allowed(frozenset(), "GET", "/api/cecchino/today")
    assert is_path_allowed(frozenset({"bet-builder"}), "GET", "/api/cecchino/today/5/signal-explanations")
    assert not is_path_allowed(frozenset({"bet-builder"}), "GET", "/api/cecchino/today/5")
    assert is_path_allowed(frozenset({"bookmakers"}), "GET", "/api/admin/competitions/3/bookmakers/coverage")
    assert not is_path_allowed(frozenset({"bookmakers"}), "GET", "/api/admin/competitions/3")
    assert is_path_allowed(frozenset({"cecchino-lab"}), "POST", "/api/cecchino-lab/pattern-lab/query")
    assert not is_path_allowed(frozenset({"cecchino-lab"}), "POST", "/api/admin/cecchino-lab/imports")


def test_catalog_and_exemptions():
    assert set(TAB_RULES) == set(TAB_KEYS)
    assert is_exempt("/api/auth/login") and is_exempt("/api/audit/overview") and is_exempt("/api/health")
    assert not is_exempt("/api/admin/users")
    admin = Principal(kind="user", is_admin=True)
    assert "admin" in allowed_tab_keys(admin)
    user = Principal(kind="user", is_admin=False, tabs=frozenset({"cecchino-v4", "sconosciuta"}))
    assert allowed_tab_keys(user) == ["cecchino-v4"]


def test_passwords():
    stored = hash_password("Prova12345")
    assert verify_password_hash("Prova12345", stored)
    assert not verify_password_hash("prova12345", stored)
    assert not verify_password_hash("x", "rotto")
    pw = generate_password()
    assert len(pw) == 12 and password_problem(pw + "xx") is None
    assert password_problem("corta1") is not None
    assert password_problem("senzanumeri") is not None
