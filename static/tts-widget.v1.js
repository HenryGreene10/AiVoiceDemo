// v106 - metrics OFF, open-first flow, hard-guard against unhandled rejections
console.log('[AIL] widget v106 LIVE', new Date().toISOString());

// Never let metric calls block or throw
const __AIL_METRICS_ON__ = false;
function metricsSafePing(){ /* no-op */ }

// Swallow any promise rejections from legacy metric code (safety belt)
window.addEventListener('unhandledrejection', (e)=>{
  try {
    const msg = String(e.reason || '');
    if (msg.includes('/metric')) { e.preventDefault(); return; }
  } catch {}
}, true);

/* v23 — minimal widget: safe CORS, no-block metrics, auto-load mini, open-first */

(() => {
  "use strict";
  if (window.__ttsWidgetLoaded) return;
  window.__ttsWidgetLoaded = true;

  // ---------- tiny DOM helper ----------
  const $ = (s, r = document) => r.querySelector(s);

  // ---------- read attributes from our <script> tag ----------
  function getScriptTag() {
    // prefer the currently executing script; fallback to a selector
    return document.currentScript || $('script[src*="tts-widget.v1.js"]');
  }

  function readDataset(script) {
    const d = (script && script.dataset) || {};
    return {
      apiBase: (d.base || "").trim(),
      voiceId: d.voice || "",
      tenant: d.tenant || "",
      selector: d.selector || "article",
      preset: d.preset || "news",
      metrics: (d.metrics || "off") !== "off", // default OFF (flip to 'on' later)
      ui: {
        variant: d.variant || "floating",       // "floating" | "inline"
        position: d.position || "bottom-right", // top-left|top-right|bottom-left|bottom-right
        labelIdle: d.labelIdle || "Listen",
        labelLoading: d.labelLoading || "Loading…",
        labelPause: d.labelPause || "Pause",
        labelError: d.labelError || "Error",
        className: d.class || "",
        style: d.style || "",
        autoTheme: (d.autotheme || "true") !== "false"
      }
    };
  }

  // ---------- normalize API base (force https, strip trailing slash) ----------
  function normalizeBase(raw) {
    let base = (raw || "").trim().replace(/\s+/g, "");
    if (!/^https?:\/\//i.test(base)) {
      // fall back to same-origin if user forgot scheme
      console.warn("[AIL] invalid data-base, using same-origin:", base);
      base = location.origin;
    }
    base = base.replace(/^http:\/\//i, "https://"); // Render supports https
    base = base.replace(/\/+$/g, "");
    return base;
  }

  // ---------- extract content to read ----------
  function pickMeta(selArr) {
    for (const s of selArr) {
      const el = document.querySelector(s);
      if (!el) continue;
      const c = el.content || el.getAttribute?.("content") || el.textContent;
      if (c && String(c).trim()) return String(c).trim();
    }
    return "";
  }

  function getTitle() {
    return (
      pickMeta([
      'meta[property="og:title"]',
      'meta[name="twitter:title"]',
      'meta[name="title"]'
      ]) ||
      document.querySelector("h1")?.innerText ||
      document.title ||
      ""
    ).trim();
  }

  function getAuthor() {
    return (
      pickMeta([
      'meta[name="author"]',
      'meta[property="article:author"]',
      '[rel="author"]',
      '[itemprop="author"]',
      '.byline, .author, .c-byline, .post-author'
      ]) || ""
    ).trim();
  }

  function getBody(selector) {
    const roots = [
      selector,
      "article [itemprop='articleBody']",
      "article",
      "main",
      "[role='main']",
      ".article-body, .post-content, .story-body, .entry-content"
    ].map(s => document.querySelector(s)).filter(Boolean);

    const root = roots[0] || document.body;
    const clone = root.cloneNode(true);

    clone.querySelectorAll(
      [
      "nav","header","footer","aside","form",
        "script","style","noscript","svg","video","audio","canvas",
        ".share",".ads,.advert,.sponsor",".subscribe",".paywall",
        "#ai-fab","#ai-listen-btn","#ai-listen-audio"
      ].join(",")
    ).forEach(n => n.remove());

    let text = "";
    clone.querySelectorAll("h1,h2,h3,p,li,blockquote").forEach(n => {
      const s = (n.innerText || "").replace(/\s+/g, " ").trim();
      if (s) text += s + " ";
    });

    // clean + cap
    text = text.replace(/[^\x09\x0A\x0D\x20-\x7E\u00A0-\u024F]/g, " ");
    return text.slice(0, 2000).trim();
  }

  function buildPrompt(selector) {
    const title  = getTitle();
    const author = getAuthor();
    const body   = getBody(selector);
    const parts = [];
    if (title)  parts.push(title);
    if (author) parts.push(`By ${author}.`);
    if (body)   parts.push(body);
    const out = parts.join(" ").replace(/\s+/g, " ").trim();
    return out.slice(0, 1200) || "This article has no readable text.";
  }

  // ---------- non-blocking metrics helper ----------
  function metricsSafePing(baseUrl, payload, on) {
    /* no-op - metrics disabled */
  }

  // ---------- ensure mini-player is present ----------
  async function ensureMiniLoaded(scriptSrc) {
    if (window.AiMini) return;
    await new Promise((resolve, reject) => {
      const s = document.createElement("script");
      s.src = new URL("mini-player.js", scriptSrc).toString() + "?v=23";
      s.onload = resolve;
      s.onerror = reject;
      document.head.appendChild(s);
    });
  }

  // ---------- place floating button ----------
  function placeFloating(btn, position) {
    btn.style.position = "fixed";
    btn.style.zIndex = "999999";
    btn.style.right = btn.style.left = btn.style.top = btn.style.bottom = "";
    const [v, h] = position.split("-");
    if (v === "top") btn.style.top = "16px"; else btn.style.bottom = "16px";
    if (h === "left") btn.style.left = "16px"; else btn.style.right = "16px";
  }

  // ---------- simple auto-theme ----------
  function applyAutoTheme(btn, allow) {
    if (!allow) return;
    // use link color as brand; otherwise body color
    const a = $("a");
    const body = getComputedStyle(document.body);
    const color = a ? getComputedStyle(a).color : body.color || "#111";
    btn.style.background = color;
    btn.style.color = "#fff";
    btn.style.border = "1px solid rgba(0,0,0,.15)";
    btn.style.borderRadius = "9999px";
    btn.style.padding = "10px 14px";
    btn.style.font = "500 14px/1 system-ui, -apple-system, Segoe UI, Roboto, sans-serif";
    btn.style.boxShadow = "0 8px 24px rgba(0,0,0,.15)";
  }

  // ---------- TTS API ----------
  async function getAudioUrl(apiBase, tenant, voiceId, text, preset) {
    const headers = { "content-type": "application/json" };
    if (tenant) headers["x-tenant-key"] = tenant;

    // Try JSON body API (recommended)
    const payload = { text, voice_id: voiceId || undefined, preset: preset || undefined };
    const r = await fetch(apiBase + "/api/tts", {
      method: "POST",
      headers,
      body: JSON.stringify(payload)
    });
    const raw = await r.text();
    if (!r.ok) throw new Error(`TTS ${r.status}: ${raw}`);
    const j = JSON.parse(raw);
    let url = j.audioUrl || j.audio_url || j.url;
    if (!url) throw new Error("No audioUrl returned");
    // If server returns a relative path, prefix apiBase
    if (!/^https?:\/\//i.test(url)) url = apiBase + url;
    return url;
  }

  // ---------- public init ----------
  window.AiListen = {
    init(opts = {}) {
      const script = getScriptTag();
      const ds = readDataset(script);

      const apiBase = normalizeBase(opts.apiBase || ds.apiBase || location.origin);
      const voiceId = opts.voiceId || ds.voiceId || "";
      const tenant  = opts.tenant  || ds.tenant  || "";
      const preset  = opts.preset  || ds.preset  || "news";
      const selector= opts.selector|| ds.selector;
      const ui      = Object.assign({}, ds.ui, opts.ui || {});
      const metrics = !!(opts.metrics ?? ds.metrics);

      // Expose for quick console sanity
      window._AIL_DEBUG = { base: apiBase, tenant, voiceId, preset };

      // Create or reuse FAB
      let btn = $("#ai-listen-btn");
      if (!btn) {
        btn = document.createElement("button");
        btn.id = "ai-listen-btn";
        btn.type = "button";
        btn.textContent = ui.labelIdle;
        if (ui.className) btn.className = ui.className;
        if (ui.style) btn.setAttribute("style", ui.style);
        else applyAutoTheme(btn, ui.autoTheme);
        
        if (ui.variant === "inline") {
          ( $(selector) || document.body ).appendChild(btn);
      } else {
          document.body.appendChild(btn);
          placeFloating(btn, ui.position);
        }
      }

      // Ensure a singleton audio element exists (mini will reuse it)
      let audioEl = $("#ai-listen-audio");
      if (!audioEl) {
        audioEl = document.createElement("audio");
        audioEl.id = "ai-listen-audio";
        audioEl.preload = "none";
        document.body.appendChild(audioEl);
      }

      // Button behavior: open mini immediately, then fetch & play
      let busy = false;
      const setLabel = (t) => (btn.textContent = t);

      btn.addEventListener('click', async (ev) => {
        ev.preventDefault();
        if (busy) return;
        busy = true; btn.disabled = true; setLabel(ui.labelLoading);
        
        try {
          // 1) load mini code if needed
          if (!window.AiMini) {
            await new Promise((resolve, reject)=>{
              const s = document.createElement('script');
              // load relative to this widget file
              const base = (document.currentScript && document.currentScript.src) || location.href;
              s.src = new URL('mini-player.js', base).toString() + '?v=106';
              s.onload = resolve; s.onerror = reject;
              document.head.appendChild(s);
            });
          }

          // 2) open mini BEFORE any network
          const title = (document.querySelector('h1')?.innerText || document.title || 'AI Listen').trim();
          const author = (document.querySelector('meta[name="author"]')?.content || '').trim();
          window.AiMini.open({ title, subtitle: author ? `By ${author}` : location.hostname });

          // 3) build text to send
          const text = (() => {
            const t = document.querySelector('h1')?.innerText || document.title || '';
            let b = '';
            document.querySelectorAll('article,main,p,li,blockquote').forEach(n=>{
              const s=(n.innerText||'').replace(/\s+/g,' ').trim(); if(s) b+=s+' ';
            });
            const out = [t, b].join(' ').replace(/\s+/g,' ').trim();
            return out.slice(0,1200) || 'This article has no readable text.';
          })();

          // 4) request TTS (JSON API); hand off to the mini's audio
          const headers = { 'content-type':'application/json' };
          if (tenant) headers['x-tenant-key'] = tenant;

          const r = await fetch(apiBase + '/api/tts', {
            method: 'POST', headers,
            body: JSON.stringify({ text, voice_id: voiceId || undefined, preset })
          });
          const raw = await r.text();
          if (!r.ok) throw new Error(`TTS ${r.status}: ${raw}`);
          const j = JSON.parse(raw);
          let url = j.audioUrl || j.audio_url || j.url;
          if (url && !/^https?:\/\//i.test(url)) url = apiBase + url;

          const a = (window.AiMini.audio?.() || document.getElementById('ai-listen-audio'));
          if (a && url) { a.src = url; a.autoplay = true; try{ await a.play(); }catch{} setLabel(ui.labelPause); }
        } catch (e) {
          console.error('[AIL] click failed', e);
          setLabel(ui.labelError);
        } finally {
          busy = false; btn.disabled = false;
        }
      });

      // Update label on play/pause/end (for the singleton audio)
      audioEl.addEventListener("play",  () => setLabel(ui.labelPause));
      audioEl.addEventListener("pause", () => setLabel(ui.labelIdle));
      audioEl.addEventListener("ended", () => setLabel(ui.labelIdle));
    }
  };

  // Auto-init if the page just includes the script
  try { window.AiListen.init(); } catch (e) { console.error("[AIL] init error", e); }
})();
  