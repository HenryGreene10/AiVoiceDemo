# EasyAudio 
Turn every article on your site into audio with *one script tag.*

EasyAudio adds a **Listen** button and a clean **mini-player** to every article on your site.  
No exporting MP3s, no uploads, no changing your publishing workflow.

Paste one script tag → we do the rest.

---

## 🚀 Features

- **Automatic Listen button** injected under your `<h1>`
- **Instant mini-player** (bottom-right, mobile-friendly full-width)
- **Automatic text extraction**
- **Cached audio** (TTS generated once per article)
- **Unlimited plays** (you only pay for *new* articles)
- **Zero CMS changes** — works on any static or CMS-based blog
- **One-time installation** — set it once in your template

---

## 🧩 How It Works

1. You paste the AI Listen script into your site template.  
2. A Listen button appears under every article title.  
3. When a visitor clicks:
   - Your page sends the article URL to the AI Listen backend.
   - We generate narration using a high-quality TTS engine (cached forever).
   - The mini-player appears and plays the audio immediately.

---

## 📦 Installation

Paste this once into your site layout (above `</body>`):

```html
<script
  src="https://hgtts.onrender.com/static/tts-widget.v1.js"
  data-ail-api-base="https://hgtts.onrender.com"
  data-ail-tenant="_____"
  defer
></script>
```

