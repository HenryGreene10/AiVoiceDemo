# Design Note: Per-tenant ElevenLabs voices (scope only)

## Current voice selection
- Global defaults from env `VOICE_ID`/`ELEVENLABS_VOICE` (see `main.py:420-459`).
- Per-tenant overrides only via in-memory `VOICE_TENANTS` map for `/api/article-audio` (see `main.py:2725-2765`).
- Most TTS endpoints accept `voice` query param and otherwise fall back to env:
  - `/tts` GET+POST (see `main.py:1337-1392`)
  - `/api/tts` (see `main.py:1396-1471`)
  - `/read` + `/read_chunked` (see `main.py:550-605` and `main.py:1504-1534`)
  - `/precache_text` (see `main.py:1973-1991`)

## Tenant storage
- Tenant model is in `app/tenant_store.py` (`Tenant` at `app/tenant_store.py:70-85`).
- Tenants are loaded for requests via `get_validated_tenant_record` (`main.py:166-179`).
- No per-tenant voice fields exist today.

## Cache impact
- Cache keys already include `voice_id`:
  - `_cache_key` includes voice + model + settings (`main.py:1830-1836`)
  - `_cache_key_simple` includes voice (`main.py:1838-1841`)
  - `compute_article_hash` includes voice (`main.py:1846-1854`)
- Per-tenant voices will not collide in cache; switching voices will create new cache entries.

## Proposed minimal design (no implementation yet)
- Schema: add nullable columns to `Tenant`:
  - `voice_id` (string, required for per-tenant override)
  - `voice_name` (optional)
  - `voice_provider` (optional; default "elevenlabs")
  - Update `_ensure_columns` in `app/tenant_store.py` to add these lazily.
- Resolution helper (new function, likely in `main.py`):
  - `resolve_tenant_voice(tenant) -> str` that returns `tenant.voice_id` if set, else env default.
  - Use `get_validated_tenant_record` in TTS endpoints and prefer tenant voice over the `voice` query param to avoid abuse.
- Admin-only API (future work, not implementing now):
  - `POST /admin/tenants/set_voice` with body `{tenant_key, voice_id}`; updates the tenant row.

## Validation strategy
- Because updates are admin-only, simplest is to trust input and log if synth fails.
- Optional: validate `voice_id` via `GET https://api.elevenlabs.io/v1/voices` once at update time.

## Risks / edge cases
- Invalid voice_id: should fall back to default and log a warning (avoid 500s).
- Voice changes will increase cache size (new keys); consider pruning policy if needed.
- If `voice` query param remains public, it can override per-tenant voice; recommend ignoring it for tenant traffic.
