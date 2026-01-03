# EasyAudio

EasyAudio adds article-level text-to-speech to websites using a single script tag.

It injects a “Listen” button on article pages, extracts the article text, generates audio using ElevenLabs, caches the result, and serves it through a lightweight mini-player.

The system is designed to work without changes to an existing CMS or publishing workflow.

---

## Core behavior

- Automatically inserts a Listen button under article titles
- Extracts article text from the page or URL
- Generates high-quality TTS audio
- Caches audio per article (generated once, reused on future plays)
- Displays a minimal, mobile-friendly mini-player
- Works with Ghost and other CMS or static sites

---

## Backend features

- Multi-tenant system with per-tenant keys
- Per-tenant quotas and plan tiers
- Domain allow-listing for tenant access
- Stripe integration for subscription signup
- Webhook-based tenant provisioning
- Admin endpoints for tenant management
- Usage tracking and basic analytics
- Disk-based audio caching
- Health and debug endpoints for operations

---

## How it works

1) A site includes the EasyAudio script once in its template.  
2) The script adds a Listen button to article pages.  
3) On click, the backend:
   - Extracts article text  
   - Generates audio if not already cached  
   - Streams the audio to the client  
4) Subsequent plays use cached audio.

---

## Installation

Add this script tag to your site layout:

```html
<script
  src="https://hgtts.onrender.com/static/tts-widget.v1.js"
  data-ail-api-base="https://hgtts.onrender.com"
  data-ail-tenant="YOUR_TENANT_KEY"
  defer
></script>
```
