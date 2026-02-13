# Hosting-Ready Security Plan (LEAPS Trader)

## Purpose
Keep the app safe when you decide to expose it beyond localhost. This is intentionally minimal and practical for a personal project.

## Phase 0: Local-Only (Current)
- Bind the server to `127.0.0.1`.
- Do not port-forward or open router ports.
- Avoid tunnels (Cloudflare Tunnel/ngrok) until auth is in place.

## Phase 1: Edge Access Control (Cloudflare)
- Use Cloudflare Zero Trust Access in front of the app.
- Create an Access policy that allows only your identity (email) or a small allowlist.
- Enable MFA if available.
- Require authenticated access for all routes.

## Phase 2: App-Level Guardrails (Defense in Depth)
- Add an API key or JWT check for high-risk endpoints:
  - `POST /api/v1/trading/*`
  - `PUT /api/v1/trading/mode`
  - `POST /restart`
- Store the key in environment variables (not in code).
- Return `401` for missing/invalid credentials.

## Phase 3: Rate Limits + Observability
- Apply rate limits for trading and restart endpoints.
- Log auth failures and trading actions with minimal sensitive data.
- Avoid logging secrets (database URL with credentials, API keys).

## Optional Enhancements (If Needed)
- IP allowlist at the edge (Cloudflare Access supports this).
- Separate “read-only” and “trade” API keys.
- Use a separate deployment profile for hosting (prod config file).

## Ready-to-Host Checklist
- Cloudflare Access policy in place
- App-level auth enforced for trading + restart
- Rate limits enabled for high-risk endpoints
- Secrets stored in environment variables
- Logs scrubbed of secrets
