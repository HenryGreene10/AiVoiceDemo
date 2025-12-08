// v108 — inline pill under H1, clean narration order, skip clutter, clean start
console.log("[AIL] widget v108 LIVE", new Date().toISOString());

(() => {
  "use strict";
  if (window.__ttsWidgetLoaded) return;
  window.__ttsWidgetLoaded = true;

  const $ = (s, r = document) => r.querySelector(s);

  function findScriptEl() {
    return (
      document.currentScript ||
      document.querySelector('script[data-ail-tenant]') ||
      document.querySelector('script[src*="tts-widget"]')
    );
  }

  const scriptEl = findScriptEl();
  const scriptData = (scriptEl && scriptEl.dataset) || {};
  const apiBase = scriptData.ailApiBase || window.location.origin;
  const tenant = scriptData.ailTenant || "default";
  const AIL_CONFIG = { apiBase, tenant };

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
  function ensureMiniStyles(scriptSrc) {
    if (document.querySelector('link[data-ail-mini-css]')) return;
    const link = document.createElement("link");
    link.rel = "stylesheet";
    link.href = new URL("mini-player.css", scriptSrc).toString() + "?v=26";
    link.dataset.ailMiniCss = "1";
    document.head.appendChild(link);
  }

  async function ensureMiniLoaded(scriptSrc) {
    if (window.AiMini) return;
    ensureMiniStyles(scriptSrc);
    await new Promise((resolve, reject) => {
      const s = document.createElement("script");
      s.src = new URL("mini-player.js", scriptSrc).toString() + "?v=24";
      s.onload = resolve;
      s.onerror = reject;
      document.head.appendChild(s);
    });
  }

  // --- API call ---
  async function articleAudioUrl(payload) {
    // Base URL for the backend, from config or fallback to window location
    const apiBase = (AIL_CONFIG && AIL_CONFIG.apiBase) || window.location.origin;
    const baseNoSlash = apiBase.replace(/\/+$/, "");

    const resp = await fetch(baseNoSlash + "/api/article-audio", {
      method: "POST",
      headers: {
        "content-type": "application/json",
        "x-tenant-key": AIL_CONFIG && AIL_CONFIG.tenant ? AIL_CONFIG.tenant : "default",
      },
      body: JSON.stringify(payload || {}),
    });

    const data = await resp.json();
    if (!resp.ok) {
      const msg =
        data && (data.detail || data.error || data.message) ||
        `The page could not be found`;
      throw new Error(`TTS ${resp.status}: ${msg}`);
    }

    // Prefer audio_url/audioUrl/url from the JSON
    let url = data.audio_url || data.audioUrl || data.url;
    if (!url) {
      throw new Error("TTS: no audio URL in response");
    }

    // If URL is relative ("/cache/…"), resolve it against apiBase
    if (!/^https?:\/\//i.test(url)) {
      url = new URL(url, baseNoSlash + "/").href;
    }

    return {
      url,
      cached: !!data.cached,
      hash: data.hash || null,
    };
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

  function getExplicitArticles() {
    return Array.from(document.querySelectorAll("[data-ail-article]"));
  }

  const ARTICLE_HINT_SELECTORS = [
    "[data-ail-article]",
    "article",
    '[itemtype*="Article"]',
    '[itemtype*="article"]',
    "main"
  ];
  const NOISE_CLASS_RE = /(nav|menu|footer|header|sidebar|aside|promo|banner|share|social|related|newsletter)/i;
  const NOISE_TAGS = new Set(["NAV", "HEADER", "FOOTER", "ASIDE", "FORM"]);
  const FALLBACK_TAGS = new Set(["section", "div", "article", "main"]);
  const SKIP_CONTAINER_SELECTOR = "nav,header,footer,aside,form,button,input,textarea,select";
  const BODY_TAG_SELECTOR = "p,li,blockquote";
  const MIN_ARTICLE_TEXT = 300;

  function cleanNodeText(node) {
    return (node?.innerText || node?.textContent || "").replace(/\s+/g, " ").trim();
  }

  function textLength(node) {
    return cleanNodeText(node).length;
  }

  function isNoiseContainer(node) {
    if (!node || !node.tagName) return false;
    if (NOISE_TAGS.has(node.tagName.toUpperCase())) return true;
    const haystack = `${node.className || ""} ${node.id || ""}`.toLowerCase();
    return NOISE_CLASS_RE.test(haystack);
  }

  function findExplicitArticle(listenButton) {
    const articles = getExplicitArticles();
    if (!listenButton && articles.length === 1) {
      return articles[0];
    }

    if (listenButton) {
      const fromButton = listenButton.closest("[data-ail-article]");
      if (fromButton) return fromButton;
    }

    if (articles.length === 1) {
      return articles[0];
    }

    return null;
  }

  function findArticleContainer(listenButton) {
    const explicit = findExplicitArticle(listenButton);
    if (explicit) return explicit;

    const explicitList = getExplicitArticles();
    if (explicitList.length > 0) {
      return null;
    }

    if (listenButton) {
      const local = listenButton.closest("article,[itemtype*='Article'],[role='main'],main");
      if (local) return local;
    }

    const global = document.querySelector("article,[itemtype*='Article'],[role='main'],main");
    if (global) return global;

    return null;
  }

  function shouldSkipNode(node) {
    if (!node) return true;
    if (node.closest(SKIP_CONTAINER_SELECTOR)) return true;
    return isNoiseContainer(node);
  }

  function pickTitleFromArticle(articleEl) {
    if (!articleEl) return "";
    const titleNode =
      articleEl.querySelector("[data-ail-title]") ||
      articleEl.querySelector("h1") ||
      articleEl.querySelector("h2");
    return cleanNodeText(titleNode);
  }

  function pickAuthorFromArticle(articleEl) {
    if (!articleEl) return "";
    const explicit =
      articleEl.querySelector("[data-ail-author]") ||
      articleEl.querySelector("[itemprop='author']") ||
      articleEl.querySelector("[rel='author']");
    if (explicit) {
      return cleanNodeText(explicit).replace(/^by\s*/i, "");
    }
    const fallback = Array.from(articleEl.querySelectorAll("*")).find((node) => {
      const haystack = `${node.className || ""} ${node.id || ""}`.toLowerCase();
      if (!haystack) return false;
      return haystack.includes("author") || haystack.includes("byline");
    });
    return cleanNodeText(fallback).replace(/^by\s*/i, "");
  }

  function collectBodyText(articleEl) {
    if (!articleEl) return "";
    const scoped = articleEl.querySelector("[data-ail-body]") || articleEl;
    const blocks = [];
    scoped.querySelectorAll(BODY_TAG_SELECTOR).forEach((node) => {
      if (shouldSkipNode(node)) return;
      const text = cleanNodeText(node);
      if (text) blocks.push(text);
    });
    if (blocks.length) {
      return stripLeadingByLines(blocks.join("\n\n")).trim();
    }
    const fallback = cleanNodeText(scoped);
    return stripLeadingByLines(fallback);
  }

  function extractArticleParts(listenButton) {
    const container = findArticleContainer(listenButton);
    if (!container) {
      console.warn("[EasyAudio] No article container found for Listen button");
      return { title: "", author: "", bodyText: "", fullText: "" };
    }

    const title = pickTitleFromArticle(container);
    const author = pickAuthorFromArticle(container);
    const bodyText = collectBodyText(container).trim();
    const parts = [];
    if (title) parts.push(title);
    if (author) parts.push(`By ${author}`);
    if (bodyText) parts.push(bodyText);
    const fullText = parts.join("\n\n").trim();

    if (!fullText || fullText.length < 20) {
      console.warn("[EasyAudio] Extracted article text is very short or empty", {
        hasExplicit: getExplicitArticles().length > 0,
        container
      });
    } else {
      console.log("[EasyAudio] Using article container", {
        hasExplicit: getExplicitArticles().length > 0,
        snippet: fullText.slice(0, 120)
      });
    }

    return {
      title,
      author,
      bodyText,
      fullText
    };
  }




  // --- public init ---
  window.AiListen = {
    init(opts = {}) {
      const ds = scriptData;
      const effectiveApiBase = (opts.apiBase || ds.ailApiBase || AIL_CONFIG.apiBase || window.location.origin).toString().trim();
      const effectiveTenant = opts.tenant || ds.ailTenant || AIL_CONFIG.tenant || "default";
      const selector = opts.selector || ds.selector || "article";
      const labelIdle = opts.labelIdle || ds.labelIdle || "Listen";
      const className = opts.className || ds.class || "";

      const runtimeConfig = {
        apiBase: effectiveApiBase.replace(/\/+$/, ""),
        tenant: effectiveTenant
      };

      window._AIL_DEBUG = { base: runtimeConfig.apiBase, tenant: runtimeConfig.tenant };

      function attachListenHandler(btn) {
        if (btn.__ailBound) return;
        btn.__ailBound = true;

        btn.addEventListener("click", async (ev) => {
          ev.preventDefault();
          console.log("[AIL] Listen click");

          try {
            const srcBase = (scriptEl && scriptEl.src) || location.href;
            await ensureMiniLoaded(srcBase);

            const pageUrl = window.location.href;
            const extracted = extractArticleParts(btn);
            let finalText = normalizeNumbers(extracted.fullText || "").trim();
            let pageTitle =
              extracted.title ||
              getTitle() ||
              document.querySelector("h1")?.innerText?.trim() ||
              document.title ||
              "EasyAudio";
            let subtitleText = getSubtitle() || document.querySelector(".dek, .subtitle")?.innerText?.trim() || "";

            const hasExplicit = getExplicitArticles().length > 0;
            if (!finalText || finalText.length < 20) {
              console.warn("[EasyAudio] finalText empty/short; not falling back to legacy scraping", {
                hasExplicit
              });
              return;
            }

            const spoken = finalText;

            const payload = {
              url: pageUrl,
              title: pageTitle,
              text: spoken
            };

          const { url } = await articleAudioUrl(payload, runtimeConfig);

            console.log("[AIL] Listen mini-player play");
            if (!window.AiMini?.open) {
              throw new Error("Mini-player unavailable");
            }
            window.AiMini.open({
              url,
              title: pageTitle,
              subtitle: subtitleText,
              href: pageUrl
            });

            // ensure timebar labels bind after mini is open
            try { window.AIL_bindTimebar && window.AIL_bindTimebar(); } catch {}
          } catch (e) {
            console.error("[AIL] Listen click failed:", e);
            try {
              window.AiMini?.error?.("Playback error");
            } catch {}
          }
        });
      }

      function initListenButton() {
        // 1) If a .ail-listen already exists, just wire it up.
        let btn = document.querySelector(".ail-listen");
        if (btn) {
          btn.id ||= "ai-listen-btn";
          btn.classList.add("listen-btn", "ail-listen");
          if (className) btn.classList.add(className);
          if (!btn.textContent?.trim()) btn.textContent = labelIdle;
          attachListenHandler(btn);
          return;
        }

        // NOTE: This block previously auto-injected a Listen button directly after the first <h1>.
        // To avoid surprise duplicates, the widget now leaves the DOM untouched when no trigger exists.
        console.debug("[AIL] No .ail-listen trigger found; skipping auto-insert");
      }

      initListenButton();
    }
  };

  // Auto-init once DOM is ready
  const runInit = () => {
    try {
      window.AiListen.init();
    } catch (e) {
      console.error("[AIL] init error", e);
    }
  };
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", runInit, { once: true });
  } else {
    runInit();
  }
})();
