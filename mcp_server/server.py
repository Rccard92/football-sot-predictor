"""Server MCP del Cecchino (dal 20/10/2026): accesso in SOLA LETTURA a dati e dashboard per gli audit.

Gira come servizio Railway separato. Espone strumenti MCP su HTTP (streamable HTTP, endpoint /mcp) e
chiama il backend:
- /api/audit/*  con la chiave AUDIT_API_TOKEN (letture in transazione READ ONLY, vedi backend);
- /api/...      solo GET, per leggere tutto quello che vede la dashboard.
Accesso al server protetto da MCP_ACCESS_TOKEN (header `Authorization: Bearer <token>`) oppure, dal
30/10/2026, dalla chiave API personale di un account del tool (`cck_...`, generata dal pannello utenti e
controllata sul backend). Con la chiave personale: niente SQL libero (vedrebbe anche la tabella degli
account) e le letture della dashboard passano con la chiave stessa, quindi con i permessi di quell'account.
Nessuno strumento puo' scrivere: niente POST/PUT/DELETE verso il backend, a parte la lettura SQL di
audit che il backend esegue in sola lettura.
"""

from __future__ import annotations

import contextvars
import hashlib
import hmac
import json
import os
import time
from typing import Any

import httpx
import uvicorn
from mcp.server.fastmcp import FastMCP
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

BACKEND_URL = os.environ.get("BACKEND_URL", "").rstrip("/")
AUDIT_API_TOKEN = os.environ.get("AUDIT_API_TOKEN", "")
MCP_ACCESS_TOKEN = os.environ.get("MCP_ACCESS_TOKEN", "")
PORT = int(os.environ.get("PORT", "8080"))
API_KEY_PREFIX = "cck_"
_KEY_CHECK_TTL = 60.0  # una chiave revocata smette di funzionare entro un minuto
_key_cache: dict[str, tuple[bool, float]] = {}
# chiave personale di chi sta chiamando ("" = proprietario con MCP_ACCESS_TOKEN)
_caller_key: contextvars.ContextVar[str | None] = contextvars.ContextVar("caller_key", default=None)
MAX_CHARS = 150_000  # oltre, la risposta viene tagliata (con avviso) per non saturare il contesto

_INSTRUCTIONS = (
    "Strumenti in sola lettura sul progetto Cecchino (pronostici calcio): dashboard, modelli, risultati, "
    "database, consumo API e job. Per domande sui numeri usa prima gli strumenti dedicati, poi "
    "cecchino_sql per analisi libere (solo SELECT). Date in formato YYYY-MM-DD, fuso Europe/Rome."
)


def _build_mcp() -> FastMCP:
    # Le versioni recenti dell'SDK rifiutano (421) gli Host diversi da localhost: protezione DNS-rebinding pensata
    # per server locali senza autenticazione. Qui il server e' pubblico su Railway e protetto da MCP_ACCESS_TOKEN.
    try:
        from mcp.server.transport_security import TransportSecuritySettings

        return FastMCP(
            "cecchino",
            instructions=_INSTRUCTIONS,
            stateless_http=True,
            transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
        )
    except (ImportError, TypeError):
        return FastMCP("cecchino", instructions=_INSTRUCTIONS, stateless_http=True)


mcp = _build_mcp()


def _client() -> httpx.Client:
    return httpx.Client(base_url=BACKEND_URL, timeout=120.0)


def _shape(payload: Any) -> str:
    text = json.dumps(payload, ensure_ascii=False, default=str)
    if len(text) > MAX_CHARS:
        return text[:MAX_CHARS] + f"\n... [risposta tagliata: {len(text)} caratteri in tutto; restringi la richiesta]"
    return text


def _audit_get(path: str, **params: Any) -> str:
    with _client() as c:
        r = c.get(f"/api/audit{path}", params={k: v for k, v in params.items() if v is not None},
                  headers={"Authorization": f"Bearer {AUDIT_API_TOKEN}"})
    if r.status_code >= 400:
        return _shape({"errore": r.status_code, "dettaglio": _safe_json(r)})
    return _shape(r.json())


def _safe_json(r: httpx.Response) -> Any:
    try:
        return r.json()
    except ValueError:
        return r.text[:2000]


@mcp.tool()
def cecchino_overview() -> str:
    """Panoramica: dimensione del database, righe delle tabelle principali, ultima scansione e quota API."""
    return _audit_get("/overview")


@mcp.tool()
def cecchino_sql(sql: str, limit: int = 500) -> str:
    """Esegue UNA query SQL di sola lettura (SELECT/WITH/EXPLAIN) sul database Postgres del Cecchino.
    Gira in una transazione READ ONLY con timeout di 20 s; massimo 2000 righe. Usa cecchino_tables e
    cecchino_table_columns per conoscere lo schema."""
    if _caller_key.get() != "":
        return _shape({"errore": "SQL libero non disponibile con la chiave personale: usa cecchino_get e gli altri strumenti"})
    with _client() as c:
        r = c.post("/api/audit/sql", json={"sql": sql, "limit": limit},
                   headers={"Authorization": f"Bearer {AUDIT_API_TOKEN}"})
    if r.status_code >= 400:
        return _shape({"errore": r.status_code, "dettaglio": _safe_json(r)})
    return _shape(r.json())


@mcp.tool()
def cecchino_tables() -> str:
    """Tutte le tabelle con peso (MB), righe stimate, letture dall'ultimo azzeramento statistiche, ultima manutenzione."""
    return _audit_get("/database/tables")


@mcp.tool()
def cecchino_table_columns(table: str) -> str:
    """Colonne (nome e tipo) di una tabella."""
    return _audit_get(f"/database/tables/{table}/columns")


@mcp.tool()
def cecchino_api_usage(days: int = 14) -> str:
    """Chiamate API-Football registrate per giorno ed endpoint negli ultimi N giorni."""
    return _audit_get("/api-usage", days=days)


@mcp.tool()
def cecchino_jobs(days: int = 7) -> str:
    """Scansioni di Cecchino Today e job della V4 degli ultimi N giorni: stato, durata, chiamate, quota residua."""
    return _audit_get("/jobs", days=days)


@mcp.tool()
def cecchino_data_health(days: int = 30) -> str:
    """Salute dei dati: per giorno eleggibili/escluse/concluse/ferme, giorni senza scansione, previsioni live aperte."""
    return _audit_get("/data-health", days=days)


@mcp.tool()
def cecchino_models_compare(date_from: str, date_to: str, group_by: str = "engine") -> str:
    """Confronto dei motori di previsione sullo stesso metro (giocate, vinte, ROI con forbice al 90%,
    probabilita' realistica). group_by: engine | engine_market | engine_band | engine_month | engine_league."""
    return _audit_get("/models/compare", date_from=date_from, date_to=date_to, group_by=group_by)


@mcp.tool()
def cecchino_get(path: str, query: dict[str, Any] | None = None) -> str:
    """Legge qualunque indirizzo GET del backend usato dalla dashboard, per esempio
    '/api/cecchino/today/days', '/api/cecchino/today?date=2026-10-18', '/api/cecchino/bet-builder/results',
    '/api/cecchino/bet-builder/v3', '/api/cecchino/v4/days'. Solo letture."""
    p = path if path.startswith("/") else f"/{path}"
    if not p.startswith("/api/") or p.startswith("/api/admin/auth"):
        return _shape({"errore": "percorso non ammesso: serve /api/... (escluso /api/admin/auth)"})
    with _client() as c:
        # la chiave di audit vale come accesso in sola lettura anche con il login del tool attivo (29/10/2026);
        # chi entra con la chiave personale legge con quella (stessi permessi del suo account, solo GET)
        token = _caller_key.get() or AUDIT_API_TOKEN
        r = c.get(p, params=query or None, headers={"Authorization": f"Bearer {token}"})
    if r.status_code >= 400:
        return _shape({"errore": r.status_code, "dettaglio": _safe_json(r)})
    if "application/json" not in r.headers.get("content-type", ""):
        return _shape({"content_type": r.headers.get("content-type"), "bytes": len(r.content)})
    return _shape(r.json())


async def _api_key_valid(key: str) -> bool:
    """Chiave personale ancora valida? La chiede al backend (/api/auth/me), con un minuto di memoria."""
    digest = hashlib.sha256(key.encode()).hexdigest()
    cached = _key_cache.get(digest)
    if cached and time.monotonic() - cached[1] < _KEY_CHECK_TTL:
        return cached[0]
    try:
        async with httpx.AsyncClient(base_url=BACKEND_URL, timeout=15.0) as c:
            r = await c.get("/api/auth/me", headers={"Authorization": f"Bearer {key}"})
        body = r.json() if r.status_code == 200 else {}
        ok = bool(body.get("authenticated")) and body.get("kind") == "api_key"
    except (httpx.HTTPError, ValueError):
        return False  # backend non raggiungibile: non si entra, ma non si memorizza il rifiuto
    _key_cache[digest] = (ok, time.monotonic())
    return ok


class BearerAuth(BaseHTTPMiddleware):
    """Accesso al server MCP con MCP_ACCESS_TOKEN o con una chiave API personale valida; /health resta
    libero per il controllo di Railway."""

    async def dispatch(self, request: Request, call_next):  # type: ignore[override]
        if request.url.path == "/health":
            return JSONResponse({"status": "ok", "backend": bool(BACKEND_URL), "audit": bool(AUDIT_API_TOKEN)})
        expected = MCP_ACCESS_TOKEN.strip()
        given = request.headers.get("authorization", "").removeprefix("Bearer ").strip()
        if expected and given and hmac.compare_digest(given.encode(), expected.encode()):
            caller = ""
        elif given.startswith(API_KEY_PREFIX) and await _api_key_valid(given):
            caller = given
        else:
            return JSONResponse({"error": "non autorizzato"}, status_code=401)
        reset = _caller_key.set(caller)
        try:
            return await call_next(request)
        finally:
            _caller_key.reset(reset)


def build_app():
    app = mcp.streamable_http_app()
    app.add_middleware(BearerAuth)
    return app


if __name__ == "__main__":
    uvicorn.run(build_app(), host="0.0.0.0", port=PORT, log_level="info")
