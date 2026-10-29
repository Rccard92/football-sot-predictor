"""Controllo d'accesso per scheda (dal 29/10/2026), applicato a ogni indirizzo /api.

Regole:
- amministratore (account admin o accesso di emergenza): tutto;
- utente: solo LETTURE (GET/HEAD) degli indirizzi delle schede assegnate, piu' i pochi calcoli in POST che
  una scheda usa per leggere (Pattern Lab). Tutto il resto risponde 403, anche se si scrive l'indirizzo a mano;
- chiave di audit dell'MCP: tutte le letture (GET);
- con `auth_enforced` spento si riconosce chi chiama ma non si blocca nulla (passaggio graduale).
La mappa scheda -> indirizzi viene dalle chiamate reali delle pagine del frontend (29/10/2026): se una pagina
inizia a usare un indirizzo nuovo, va aggiunto qui, altrimenti agli utenti risponde 403.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.database import get_db
from app.core.user_auth import KIND_AUDIT, Principal, resolve_principal

ADMIN_TAB = "admin"

# Schede assegnabili, nello stesso ordine del menu (chiave = indirizzo della pagina senza "/").
TAB_CATALOG: list[dict[str, str]] = [
    {"key": "cecchino-today", "label": "Cecchino Today", "path": "/cecchino-today", "group": "Cecchino"},
    {"key": "cecchino-v4", "label": "Cecchino V4", "path": "/cecchino-v4", "group": "Cecchino"},
    {"key": "confronto-motori", "label": "Confronto motori", "path": "/confronto-motori", "group": "Cecchino"},
    {"key": "bet-builder", "label": "Bet Builder", "path": "/bet-builder", "group": "Cecchino"},
    {"key": "bet-builder-v3", "label": "Bet Builder V3", "path": "/bet-builder-v3", "group": "Cecchino"},
    {"key": "master-pattern", "label": "Master Pattern", "path": "/master-pattern", "group": "Cecchino"},
    {"key": "osservazione-live", "label": "Osservazione live", "path": "/osservazione-live", "group": "Cecchino"},
    {"key": "cecchino-lab", "label": "Cecchino Lab", "path": "/cecchino-lab", "group": "Cecchino"},
    {"key": "monitoraggio-moduli", "label": "Monitoraggio Moduli", "path": "/monitoraggio-moduli", "group": "Cecchino"},
    {"key": "monitoraggio-segno-1", "label": "Monitoraggio Segno 1", "path": "/monitoraggio-segno-1", "group": "Cecchino"},
    {"key": "monitoraggio-segnali", "label": "Monitoraggio Segnali", "path": "/monitoraggio-segnali", "group": "Cecchino"},
    {"key": "segnali-kpi", "label": "Segnali KPI", "path": "/segnali-kpi", "group": "Cecchino"},
    {"key": "diario-analisi", "label": "Diario analisi", "path": "/diario-analisi", "group": "Cecchino"},
    {"key": "bookmakers", "label": "Bookmakers", "path": "/bookmakers", "group": "Generale"},
    {"key": "changelog", "label": "Changelog", "path": "/changelog", "group": "Generale"},
    {"key": "roadmap", "label": "Roadmap", "path": "/roadmap", "group": "Generale"},
    {"key": "guida-modelli", "label": "Guida ai modelli", "path": "/guida-modelli", "group": "Generale"},
    {"key": "data-health", "label": "Data Health", "path": "/data-health", "group": "Strumenti tecnici"},
]
TAB_KEYS: frozenset[str] = frozenset(t["key"] for t in TAB_CATALOG)

_READ = frozenset({"GET", "HEAD"})
_POST = frozenset({"POST"})
_READ_WRITE = frozenset({"GET", "HEAD", "POST", "PATCH", "DELETE"})


@dataclass(frozen=True)
class Rule:
    methods: frozenset[str]
    prefix: str | None = None  # l'indirizzo stesso o quelli sotto ("/x" vale per "/x" e "/x/...", non "/x-y")
    pattern: re.Pattern[str] | None = None

    def matches(self, method: str, path: str) -> bool:
        if method not in self.methods:
            return False
        if self.prefix is not None:
            return path == self.prefix or path.startswith(self.prefix + "/")
        return bool(self.pattern and self.pattern.fullmatch(path))


def _get(*prefixes: str) -> list[Rule]:
    return [Rule(_READ, prefix=p) for p in prefixes]


def _get_re(*patterns: str) -> list[Rule]:
    return [Rule(_READ, pattern=re.compile(p)) for p in patterns]


# spiegazioni di una partita di Today, aperte anche da Bet Builder, Bet Builder V3 e Segno 1
_EXPLANATIONS = r"/api/cecchino/today/\d+/[a-z0-9-]+-explanations"

TAB_RULES: dict[str, list[Rule]] = {
    "cecchino-today": _get(
        "/api/cecchino/today",
        "/api/cecchino-live/fixture",
        "/api/cecchino/v5/today-fixture",
        "/api/admin/cecchino/today/scan-jobs",
        "/api/admin/cecchino/today/excluded",
        "/api/admin/cecchino/today/debug-search",
    ),
    "cecchino-v4": _get("/api/cecchino/v4"),
    "confronto-motori": _get("/api/cecchino/engines", "/api/cecchino/v5/plays"),
    "bet-builder": _get(
        "/api/cecchino/bet-builder/opportunities",
        "/api/cecchino/bet-builder/results",
        "/api/cecchino-live/observation",
    )
    + _get_re(_EXPLANATIONS),
    "bet-builder-v3": _get("/api/cecchino/bet-builder/v3")
    + _get_re(r"/api/cecchino/bet-builder/results/\d+/analysis-context", _EXPLANATIONS),
    "master-pattern": _get("/api/admin/cecchino/master-pattern"),
    "osservazione-live": _get("/api/cecchino-live/observation-dashboard"),
    "cecchino-lab": _get("/api/cecchino-lab", "/api/cecchino-run-v2", "/api/admin/cecchino/research/pattern-grid")
    + [
        Rule(_POST, prefix=p)
        for p in (
            "/api/cecchino-lab/pattern-lab/query",
            "/api/cecchino-lab/pattern-lab/bet-builder-replay",
            "/api/cecchino-lab/pattern-lab/export-discovery",
        )
    ],
    "monitoraggio-moduli": _get(
        "/api/cecchino/module-monitoring",
        "/api/admin/cecchino/research/purchasability",
        "/api/cecchino/kpi-signals/purchasability-validation",
        "/api/admin/cecchino/signals",
        "/api/admin/cecchino/signal-min-book-odds",
    ),
    "monitoraggio-segno-1": _get("/api/cecchino/home-wins") + _get_re(_EXPLANATIONS),
    "monitoraggio-segnali": _get("/api/admin/cecchino/signals", "/api/admin/cecchino/signal-min-book-odds"),
    "segnali-kpi": _get("/api/cecchino/kpi-signals"),
    # il diario e' l'unica scheda in cui un utente scrive: solo le sue giocate (controllato nelle rotte)
    "diario-analisi": [Rule(_READ_WRITE, prefix="/api/analyst-journal")],
    "bookmakers": _get("/api/admin/bookmakers") + _get_re(r"/api/admin/competitions/\d+/bookmakers(/.*)?"),
    "changelog": [],
    "roadmap": [],
    "guida-modelli": [],
    "data-health": _get("/api/admin/data-health"),
}

# letture usate dalla struttura di ogni pagina (selettore del campionato)
SHARED_RULES: list[Rule] = _get("/api/competitions")

# indirizzi senza controllo: d'ingresso, di stato del server, o con una chiave propria (audit)
_EXEMPT_PREFIXES = ("/api/auth/", "/api/admin/auth/", "/api/audit/")
_EXEMPT_PATHS = frozenset({"/api/ping", "/api/health", "/api/auth", "/api/audit"})


def is_exempt(path: str) -> bool:
    return path in _EXEMPT_PATHS or path.startswith(_EXEMPT_PREFIXES)


def is_path_allowed(tabs: frozenset[str], method: str, path: str) -> bool:
    method = method.upper()
    if any(r.matches(method, path) for r in SHARED_RULES):
        return True
    return any(r.matches(method, path) for tab in tabs if tab in TAB_RULES for r in TAB_RULES[tab])


def allowed_tab_keys(principal: Principal | None) -> list[str]:
    if principal is None:
        return []
    if principal.is_admin:
        return [t["key"] for t in TAB_CATALOG] + [ADMIN_TAB]
    return [t["key"] for t in TAB_CATALOG if t["key"] in principal.tabs]


def _principal(request: Request, db: Session, settings: Settings) -> Principal | None:
    if not hasattr(request.state, "principal"):
        request.state.principal = resolve_principal(request, db, settings)
    return request.state.principal


def enforce_api_access(
    request: Request,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> None:
    """Dipendenza di tutto /api. Con la protezione accesa: 401 senza accesso, 403 se la password va ancora
    cambiata o se l'indirizzo non appartiene alle schede dell'utente."""
    path = request.url.path
    method = request.method.upper()
    if method == "OPTIONS" or is_exempt(path):
        return
    principal = _principal(request, db, settings)
    if not settings.auth_enforced:
        return
    if principal is None:
        raise HTTPException(status_code=401, detail="login_required")
    if principal.must_change_password:
        raise HTTPException(status_code=403, detail="password_change_required")
    if principal.is_admin:
        return
    if principal.kind == KIND_AUDIT:
        return  # la chiave di audit vale solo per GET (controllato in resolve_principal)
    if not is_path_allowed(principal.tabs, method, path):
        raise HTTPException(status_code=403, detail="tab_not_allowed")


def require_principal(
    request: Request,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> Principal:
    """Chiunque abbia fatto l'accesso (anche con la protezione generale spenta): serve sapere chi scrive."""
    principal = _principal(request, db, settings)
    if principal is None or principal.kind == KIND_AUDIT and request.method.upper() not in ("GET", "HEAD"):
        raise HTTPException(status_code=401, detail="login_required")
    if principal.must_change_password:
        raise HTTPException(status_code=403, detail="password_change_required")
    return principal


def require_admin_principal(
    request: Request,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> Principal:
    """Solo amministratori (anche in lettura), con o senza protezione generale accesa: gestione utenti."""
    principal = _principal(request, db, settings)
    if principal is None:
        raise HTTPException(status_code=401, detail="Sessione admin assente o scaduta")
    if not principal.is_admin:
        raise HTTPException(status_code=403, detail="Serve un account amministratore")
    if principal.must_change_password:
        raise HTTPException(status_code=403, detail="password_change_required")
    return principal
