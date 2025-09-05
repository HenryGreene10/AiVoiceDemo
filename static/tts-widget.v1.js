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
    const container = document.querySelector(selector) || document.querySelector("#demo-article") || document.body;

    const title = (document.querySelector("h1")?.innerText || "").trim();
    const subtitle = (document.querySelector(".dek, .subtitle, h2")?.innerText || "").trim();
    const author = (document.querySelector(".byline")?.textContent || "").replace(/^By\s*/i,"").trim();

    // collect story text only
    const clone = container.cloneNode(true);
    clone.querySelectorAll([
      "figure,figcaption,picture,video,iframe,svg,canvas",
      ".caption,.credit,.media,.gallery,.photo",
      "sup,sub,.citation,[role='doc-footnote'],.footnotes,.references",
      "aside,.related,.read-more,.recommended",
      "nav,header,footer,form,script,style"
    ].join(",")).forEach(n => n.remove());

    // paragraphs/lists/quotes as blocks
    const blocks = [];
    clone.querySelectorAll("p,li,blockquote").forEach(n => {
      const s = (n.innerText || "").replace(/\s+/g," ").trim();
      if (s) blocks.push(s);
    });

    let body = blocks.join(" ").trim();

    // de-dup title/byline if repeated at body start
    if (title && body.toLowerCase().startsWith(title.toLowerCase())) {
      body = body.slice(title.length).trim();
    }
    body = body.replace(/^\s*By\s+.+?(\.\s+|  +|\n+)/i, "");

    // paragraph breaks → natural pauses in most TTS
    const parts = [];
    if (title)   parts.push(title);
    if (subtitle)parts.push(subtitle);
    if (author)  parts.push(`By ${author}`);
    if (body)    parts.push(body);

    const plain = parts.join("\n\n").slice(0, 15000); // generous safety cap
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
  
  function numberToWordsUS(num){ // supports 0..999,999,999
    const ones=["zero","one","two","three","four","five","six","seven","eight","nine"];
    const teens=["ten","eleven","twelve","thirteen","fourteen","fifteen","sixteen","seventeen","eighteen","nineteen"];
    const tens=["","","twenty","thirty","forty","fifty","sixty","seventy","eighty","ninety"];
    function chunk(n){
      let s="";
      const h=Math.floor(n/100), t=n%100;
      if(h) s+=ones[h]+" hundred";
      if(t){ if(s) s+=" ";
        if(t<10) s+=ones[t];
        else if(t<20) s+=teens[t-10];
        else { s+=tens[Math.floor(t/10)]; if(t%10) s+="-"+ones[t%10]; }
      }
      return s || "zero";
    }
    if (num===0) return "zero";
    const parts=[], units=[""," thousand"," million"," billion"];
    let i=0;
    while(num>0 && i<units.length){
      const c=num%1000;
      if(c) parts.unshift(chunk(c)+units[i]);
      num=Math.floor(num/1000); i++;
    }
    return parts.join(" ");
  }
  function normalizeNumbers(text){
    // 13,000 → thirteen thousand ; 250000 → two hundred fifty thousand
    return text.replace(/\b\d{1,3}(?:,\d{3})+\b|\b\d{4,9}\b/g, m => {
      const n = Number(m.replace(/,/g,""));
      if (!Number.isFinite(n)) return m;
      return numberToWordsUS(n);
    });
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
          const spoken = normalizeNumbers(plain);           
          const url = await getAudioUrl(apiBase, tenant, voiceId, spoken, preset);

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
