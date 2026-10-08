# XFINLAB architecture (public overview)

XFINLAB is a financial-intelligence platform delivered as a consumer web app, a REST API, SDKs and a hosted MCP server. This repository contains the **public interface layer**; the engines and data pipelines behind it are proprietary and run as a private service.

## Layers

```
 Consumer UI (static HTML/JS/CSS)  ─┐
 SDKs: Python · JS · LangChain · LlamaIndex ─┼─►  Public HTTPS API  ─►  Private core (not in this repo)
 MCP clients (Claude, Cursor, …)   ─┘      api.xfinlab.com            engines · data · scoring · memory
```

- **Public (this repo):** web UI and localisation, SDKs, examples, API/MCP documentation, `server.json`, `llms.txt`.
- **Private core:** the API implementation, research and scoring engines, data collection, storage, billing and authentication.
- **Dependency rule:** public code talks to the core only through the HTTP API; it never imports core modules.

## Design principles

- **No fabricated data.** Every field is a real computation or an official-source value, otherwise `null` with an explanation.
- **Server-side entitlements.** API keys, quotas and plan checks are enforced on the server, never in client code.
- **Stateless edge, durable core.** The UI is a static deployment on a CDN; the API is a separately deployed service with replicated storage.
- **Multi-language.** UI and content are localised across many languages.

## Access

Free-tier API keys are issued at <https://www.xfinlab.com/intelligence-api.html>. The MCP endpoint is `https://api.xfinlab.com/api/mcp` (Streamable HTTP, `X-API-Key` header).

This document intentionally omits implementation details of the proprietary core.
