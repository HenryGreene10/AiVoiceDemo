// v108 — inline pill under H1, clean narration order, skip clutter, clean start
console.log("[AIL] widget v108 LIVE", new Date().toISOString());

(() => {
  "use strict";
  if (window.__ttsWidgetLoaded) return;
  window.__ttsWidgetLoaded = true;

  const $ = (s, r = document) => r.querySelector(s);

  // --- script data (kept minimal) ---
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
        // we ONLY use labelIdle + optional className; no floating, no inline styles
        labelIdle: d.labelIdle || "Listen",
        className: d.class || ""
      }
    };
  }
  function normalizeBase(raw) {
    let base = (raw || "").trim().replace(/\s+/g, "");
    if (!/^https?:\/\//i.test(base)) base = location.origin;
    base = base.replace(/^http:\/\//i, "https://").replace(/\/+$/g, "");
    return base;
  }

  // --- meta helpers ---
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
    const explicit = pickMeta([
      'meta[name="author"]',
      'meta[property="article:author"]'
    ]);
    const byline =
      document.querySelector(
        '[rel="author"], [itemprop="author"], .byline, .post-byline, .c-byline, .author'
      )?.textContent || "";
    return (explicit || byline || "").replace(/^By\s*/i, "").trim();
  }

  // --- body extraction (skip captions/embeds/refs/etc) ---
  function getBody(selector) {
    const roots = [
      selector,
      "article [itemprop='articleBody']",
      "article",
      "main",
      "[role='main']",
      ".article-body, .post-content, .story-body, .entry-content"
    ]
      .map((s) => document.querySelector(s))
      .filter(Boolean);

    const root = roots[0] || document.body;
    const clone = root.cloneNode(true);

    // remove non-story elements
    clone
      .querySelectorAll(
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
      )
      .forEach((n) => n.remove());

    const blocks = [];
    clone.querySelectorAll("h1,h2,h3,p,li,blockquote").forEach((n) => {
      const s = (n.innerText || "").replace(/\s+/g, " ").trim();
      if (s) blocks.push(s);
    });

    let text = blocks.join(" ");
    text = text.replace(/[^\x09\x0A\x0D\x20-\x7E\u00A0-\u024F]/g, " ");
    return text.trim();
  }

  // --- small cleaners ---
  function stripLeadingByLines(txt) {
    // remove leading “By …” line(s) the body might contain
    return (txt || "")
      .replace(/^\s*By\s+.+?\n+/i, "")
      .replace(/^\s*By\s+.+?\s{2,}/i, "");
  }

  // --- narration shaping (Title → Subtitle → By Author → Body) ---
  function buildNarration(selector) {
    const title = getTitle();
    const subtitle = getSubtitle();
    const author = getAuthor();
    let body = getBody(selector);

    // de-dup title and author lines if body starts with them
    if (title && body.toLowerCase().startsWith(title.toLowerCase())) {
      body = body.slice(title.length).trim();
    }
    body = stripLeadingByLines(body);

    const parts = [];
    if (title) parts.push(title);
    if (subtitle) parts.push(subtitle);
    if (author) parts.push(`By ${author}`);
    if (body) parts.push(body);

    // Paragraph gaps create natural pauses with most TTS engines
    const plain = parts.join("\n\n").slice(0, 12000); // generous cap
    return { plain, title, subtitle, author, body };
  }

  // --- ensure mini-player code ---
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

  // --- API call ---
  async function getAudioUrl(apiBase, tenant, voiceId, text, preset) {
    const headers = { "content-type": "application/json" };
    if (tenant) headers["x-tenant-key"] = tenant;

    const payload = {
      text,
      voice_id: voiceId || undefined,
      preset: preset || undefined
    };
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
    if (!/^https?:\/\//i.test(url)) url = apiBase + url;
    return url;
  }

  // --- public init ---
  window.AiListen = {
    init(opts = {}) {
      const script = getScriptTag();
      const ds = readDataset(script);

      const apiBase = normalizeBase(opts.apiBase || ds.apiBase || location.origin);
      const voiceId = opts.voiceId || ds.voiceId || "";
      const tenant = opts.tenant || ds.tenant || "";
      const preset = opts.preset || ds.preset || "news";
      const selector = opts.selector || ds.selector;
      const ui = Object.assign({}, ds.ui, opts.ui || {});

      window._AIL_DEBUG = { base: apiBase, tenant, voiceId, preset };

      // Use existing inline button if present; otherwise create one
      let btn = $("#ai-listen-btn");
      if (!btn) {
        btn = document.createElement("button");
        btn.id = "ai-listen-btn";
        btn.type = "button";
        btn.textContent = ui.labelIdle || "Listen";
      } else {
        btn.textContent = ui.labelIdle || "Listen";
      }

      // Always use your CSS pill, never inline styles; place under H1
      if (ui.className) btn.classList.add(ui.className);
      btn.classList.add("listen-btn");
      btn.removeAttribute("style");

      const h1 = document.querySelector("h1");
      if (h1 && (!btn.parentElement || btn.parentElement !== h1.parentElement)) {
        h1.insertAdjacentElement("afterend", btn);
      } else if (!btn.parentElement) {
        (document.querySelector(selector) || document.body).prepend(btn);
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

        // Toggle: if open → close & pause
        if (window.AiMini?.isOpen?.()) {
          try {
            window.AiMini.close();
          } catch {}
          try {
            audioEl.pause();
          } catch {}
          return;
        }

        try {
          const srcBase =
            (document.currentScript && document.currentScript.src) || location.href;
          await ensureMiniLoaded(srcBase);

          const { plain, title, subtitle, author } = buildNarration(selector);
          const subline = subtitle || (author ? `By ${author}` : location.hostname);
          window.AiMini.open({
            title: title || document.title || "AI Listen",
            subtitle: subline
          });

          const url = await getAudioUrl(apiBase, tenant, voiceId, plain, preset);

          const a = window.AiMini.audio?.() || audioEl;
          try {
            a.pause();
            a.removeAttribute("src");
            a.currentTime = 0;
          } catch {}

          a.src = url;
          a.preload = "auto";

          await new Promise((res) => {
            const onReady = () => {
              a.removeEventListener("canplay", onReady);
              res();
            };
            a.addEventListener("canplay", onReady, { once: true });
            a.load();
          });

          try {
            await a.play();
          } catch {}
        } catch (e) {
          console.error("[AIL] Listen click failed:", e);
          try {
            window.AiMini?.error?.("Playback error");
          } catch {}
        }
      });
    }
  };

  // Auto-init
  try {
    window.AiListen.init();
  } catch (e) {
    console.error("[AIL] init error", e);
  }
})();
