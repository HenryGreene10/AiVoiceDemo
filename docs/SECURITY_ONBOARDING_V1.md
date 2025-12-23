# EasyAudio Security Onboarding v1

## Terminology
- tenant_key: Public identifier for a tenant. It is not a secret and is safe to embed in widget HTML.
- allowed_domains: Hostname allowlist associated with a tenant. Exact match only after normalization.

## Request Acceptance Rules
1) Tenant must exist and be active.
2) Derive request_domain from headers:
   - Prefer the Origin hostname if present.
   - Else use the Referer hostname if present.
   - Else reject with `missing_origin` (unless demo_mode is true).
   - No custom widget headers are required; standard browser headers are used.
3) Normalize domain consistently (lowercase, strip scheme/path/query/fragment, strip port, strip trailing dot, trim whitespace).
4) Match exact hostname against the tenant's allowed domains (normalized).
5) Optional behavior: auto-expand apex/www at write time. Current behavior: no auto-expansion, so register both `example.com` and `www.example.com` if needed.
6) Quotas + trial limits remain enforced server-side regardless of domain.

## Failure Modes (Exact JSON Errors)
- tenant_not_found
  ```json
  {"error":"tenant_not_found","message":"Tenant not found."}
  ```
- missing_origin (neither Origin nor Referer)
  ```json
  {"error":"missing_origin","message":"Origin or Referer required"}
  ```
- domain_not_allowed
  ```json
  {
    "error":"domain_not_allowed",
    "message":"Domain not allowed for this tenant",
    "parsed_domain":"henry-1.ghost.io",
    "normalized_domain":"henry-1.ghost.io",
    "allowed_domains":["henry-1.ghost.io"]
  }
  ```
- quota_exceeded (if applicable)
  ```json
  {
    "error":"quota_exceeded",
    "message":"Monthly quota reached for the trial plan.",
    "plan":"trial",
    "limit_seconds":600,
    "used_seconds":600
  }
  ```

## Onboarding Checklist
1) Create or confirm a tenant_key (POST /admin/tenants; include tenant_key to upsert).
2) Register allowed domains (hostnames only, no paths).
3) Install the widget snippet on the client site.
4) Verify with the admin domain debug endpoint.

## Admin Diagnostics Auth
- /admin/* endpoints require the `x-admin-secret` header.
- The value must match the `ADMIN_SECRET` environment variable.

## cURL Recipes
- POST /admin/tenants creates a new tenant when tenant_key is omitted and upserts when tenant_key is provided.
- /debug/config
  ```bash
  curl -sS "https://YOUR_HOST/debug/config"
  ```
- /admin/tenant?tenant_key=...
  ```bash
  curl -sS \
    -H "x-admin-secret: $ADMIN_SECRET" \
    "https://YOUR_HOST/admin/tenant?tenant_key=TENANT_KEY"
  ```
- /admin/domain-debug?tenant_key=... (with Origin/Referer)
  ```bash
  curl -sS \
    -H "x-admin-secret: $ADMIN_SECRET" \
    -H "Origin: https://henry-1.ghost.io" \
    -H "Referer: https://henry-1.ghost.io/" \
    "https://YOUR_HOST/admin/domain-debug?tenant_key=TENANT_KEY"
  ```
- Tenant upsert/update domains
  ```bash
  curl -sS -X POST \
    -H "x-admin-secret: $ADMIN_SECRET" \
    -H "Content-Type: application/json" \
    -d '{"tenant_key":"TENANT_KEY","plan_tier":"trial","domains":["henry-1.ghost.io"],"status":"active"}' \
    "https://YOUR_HOST/admin/tenants"
  ```

## Security Rationale and v2 Ideas
- v1 uses standard browser headers (Origin/Referer) to enforce exact domain allowlists server-side.
- tenant_key is a public identifier, so domain enforcement and quotas are the real controls.
- v2 could add a signed install token (short-lived JWT or HMAC) to prove initial ownership during install, without changing the v1 runtime flow.
