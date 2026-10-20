# Server MCP del Cecchino

Servizio Railway separato che dà a Claude accesso **in sola lettura** a dati, dashboard e audit del Cecchino.

- Endpoint MCP: `https://<dominio>/mcp` (streamable HTTP). Accesso con `Authorization: Bearer <MCP_ACCESS_TOKEN>`.
- `/health` libero per il controllo di Railway.
- Variabili: `BACKEND_URL`, `AUDIT_API_TOKEN` (uguale a quella del backend), `MCP_ACCESS_TOKEN`.
- Avvio: `python server.py`.

Strumenti: panoramica, SQL di sola lettura, tabelle e colonne, consumo API, job, salute dei dati,
confronto dei motori, lettura GET di qualunque indirizzo `/api/...` della dashboard.
Nessuno strumento scrive: il backend esegue le letture di audit in transazioni READ ONLY.

Collegamento da Claude Code:

```bash
claude mcp add --transport http cecchino https://<dominio>/mcp --header "Authorization: Bearer <MCP_ACCESS_TOKEN>"
```
