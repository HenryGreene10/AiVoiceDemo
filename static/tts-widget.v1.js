// v107 — inline button friendly, toggle mini, narration shaping, clean start
console.log('[AIL] widget v107 LIVE', new Date().toISOString());

(() => {
  "use strict";
  if (window.__ttsWidgetLoaded) return;
  window.__ttsWidgetLoaded = true;

  // ---------- tiny DOM helper ----------
  const $ = (s, r = document) => r.querySelector(s);

  // ---------- script data ----------
  function getScriptTag() {
    return document.currentScript || $('script[src*="tts-widget"]');
  }
  function readDataset(script) {
    const d = (script && script.dataset) || {};
    return {
      apiBase: (d.base || "").trim(),
      voiceId: d.voice || "",
      tenant: d.tenant || "",
      selector: d.selector || "article",
      preset: d.preset || "news",
      ui: {
        variant: d.variant || "inline",        // default inline
        position: d.position || "bottom-right",
        labelIdle: d.labelIdle || "Listen",
        className: d.class || "",
        style: d.style || "",
        autoTheme: (d.autotheme || "true") !== "false"
      }
    };
  }
  function normalizeBase(raw) {
    let base = (raw || "").trim().replace(/\s+/g, "");
    if (!/^https?:\/\//i.test(base)) base = location.origin;
    base = base.replace(/^http:\/\//i, "https://").replace(/\/+$/g, "");
    return base;
  }

  // ---------- meta helpers ----------
  function pickMeta(arr) {
    for (const s of arr) {
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
      $("h1")?.innerText ||
      document.title ||
      ""
    ).trim();
  }
  function getSubtitle() {
    return (
      pickMeta([
        'meta[property="og:description"]',
        'meta[name="twitter:description"]',
        'meta[name="description"]'
      ]) ||
      $(".dek, .subtitle, h2")?.innerText ||
      ""
    ).trim();
  }
  function getAuthor() {
    // favor explicit author markers, then byline text
    const explicit =
      pickMeta([
        'meta[name="author"]',
        'meta[property="article:author"]',
      ]) ||
      $('[rel="author"]')?.textContent ||
      $('[itemprop="author"]')?.textContent ||
      "";
    const byline = $(".byline, .post-byline, .c-byline, .author")?.innerText || "";
    const raw = (explicit || byline || "").replace(/^By\s*/i, "").trim();
    return raw;
  }

  // ---------- body extraction (skip captions/refs/embeds/etc) ----------
  function getBody(selector) {
    const roots = [
      selector, "article [itemprop='articleBody']",
      "article", "main", "[role='main']",
      ".article-body, .post-content, .story-body, .entry-content"
    ].map(s => document.querySelector(s)).filter(Boolean);

    const root = roots[0] || document.body;
    const clone = root.cloneNode(true);

    clone.querySelectorAll(
      [
        "nav,header,footer,aside,form",
        "script,style,noscript,svg,canvas",
        "video,audio,iframe,picture,source",
        "figure,figcaption,.caption,.credit,.media,.gallery,.photo",
        ".share,.social,.subscribe,.newsletter",
        ".ads,.ad,.advert,.sponsor,.paywall",
        ".related,.more,.read-more,.recommended",
        "[role='doc-footnote'], .footnotes, .references, sup, sub",
        "#ai-fab,#ai-listen-btn,#ai-listen-audio"
      ].join(",")
    ).forEach(n => n.remove());

    // collect readable blocks
    const blocks = [];
    clone.querySelectorAll("h1,h2,h3,p,li,blockquote").forEach(n => {
      const s = (n.innerText || "").replace(/\s+/g, " ").trim();
      if (s) blocks.push(s);
    });
    let text = blocks.join(" ");

    // normalize
    text = text.replace(/[^\x09\x0A\x0D\x20-\x7E\u00A0-\u024F]/g, " ");
    return text.trim();
  }

  // ---------- narration shaping ----------
  function buildNarration(selector) {
    const title = getTitle();
    const subtitle = getSubtitle();
    const author = getAuthor();
    let body = getBody(selector);

    // de-dup title if body starts with it
    if (title && body.toLowerCase().startsWith(title.toLowerCase())) {
      body = body.slice(title.length).trim();
    }

    // Build plain text with intentional pauses via blank lines
    // (swap to SSML later if your backend supports it)
    const parts = [];
    if (title)   parts.push(title);
    if (subtitle)parts.push(subtitle);
    if (author)  parts.push(`By ${author}`);
    if (body)    parts.push(body);

    const plain = parts.join("\n\n"); // TTS will naturally pause on paragraph breaks
    return { plain, title, subtitle, author, body };
  }

  // ---------- ensure mini-player code ----------
  async function ensureMiniLoaded(scriptSrc) {
    if (window.AiMini) return;
    await new Promise((resolve, reject) => {
      const s = document.createElement("script");
      s.src = new URL("mini-player.js", scriptSrc).toString() + "?v=24";
      s.onload = resolve;
      s.onerror = reject;
      document.head.appendChild(s);
    });
  }

  // ---------- API ----------
  async function getAudioUrl(apiBase, tenant, voiceId, text, preset) {
    const headers = { "content-type": "application/json" };
    if (tenant) headers["x-tenant-key"] = tenant;

    const payload = { text, voice_id: voiceId || undefined, preset: preset || undefined };
    const r = await fetch(apiBase + "/api/tts", { method: "POST", headers, body: JSON.stringify(payload) });
    const raw = await r.text();
    if (!r.ok) throw new Error(`TTS ${r.status}: ${raw}`);
    const j = JSON.parse(raw);
    let url = j.audioUrl || j.audio_url || j.url;
    if (!url) throw new Error("No audioUrl returned");
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

      // Expose for console sanity checks
      window._AIL_DEBUG = { base: apiBase, tenant, voiceId, preset };

      // Use existing inline button if present; otherwise create one
      let btn = $("#ai-listen-btn");
      if (!btn) {
        btn = document.createElement("button");
        btn.id = "ai-listen-btn";
        btn.type = "button";
        btn.textContent = ui.labelIdle || "Listen";
        if (ui.className) btn.className = ui.className;
        if (ui.style) btn.setAttribute("style", ui.style);

        if (ui.variant === "inline") {
          ( $(selector) || document.body ).appendChild(btn);
        } else {
          // fallback: floating
          btn.style.position = "fixed";
          btn.style.zIndex = "999999";
          const [v,h] = (ui.position || "bottom-right").split("-");
          if (v === "top") btn.style.top = "16px"; else btn.style.bottom = "16px";
          if (h === "left") btn.style.left = "16px"; else btn.style.right = "16px";
          document.body.appendChild(btn);
        }
      } else {
        // ensure visible text
        btn.textContent = ui.labelIdle || "Listen";
      }

      // Singleton audio element (mini will reuse it)
      let audioEl = $("#ai-listen-audio");
      if (!audioEl) {
        audioEl = document.createElement("audio");
        audioEl.id = "ai-listen-audio";
        audioEl.preload = "auto";
        document.body.appendChild(audioEl);
      }

      // Click: toggle mini; if opening, fetch & play from 0:00
      btn.addEventListener("click", async (ev) => {
        ev.preventDefault();

        // If mini is visible, close & pause (toggle behavior)
        if (window.AiMini?.isOpen?.()) {
          try { window.AiMini.close(); } catch {}
          try { audioEl.pause(); } catch {}
          return;
        }

        try {
          // 1) load mini code if needed
          const srcBase = (document.currentScript && document.currentScript.src) || location.href;
          await ensureMiniLoaded(srcBase);

          // 2) Build narration parts
          const { plain, title, subtitle, author } = buildNarration(selector);

          // 3) Open mini immediately with clean metadata
          const subline = subtitle || (author ? `By ${author}` : location.hostname);
          window.AiMini.open({ title: title || document.title || "AI Listen", subtitle: subline });

          // 4) Request TTS
          const url = await getAudioUrl(apiBase, tenant, voiceId, plain, preset);

          // 5) Clean start every time (no resume/no halfway)
          const a = (window.AiMini.audio?.() || audioEl);
          try {
            a.pause();
            a.removeAttribute("src");
            a.currentTime = 0;
          } catch {}

          a.src = url;
          a.preload = "auto";

          await new Promise((res) => {
            const onReady = () => { a.removeEventListener("canplay", onReady); res(); };
            a.addEventListener("canplay", onReady, { once: true });
            a.load();
          });

          try { await a.play(); } catch {}
        } catch (e) {
          console.error("[AIL] Listen click failed:", e);
          try { window.AiMini?.error?.("Playback error"); } catch {}
        }
      });
    }
  };

  // Auto-init
  try { window.AiListen.init(); } catch (e) { console.error("[AIL] init error", e); }
})();
