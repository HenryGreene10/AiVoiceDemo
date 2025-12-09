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
  const scriptHasTenant = !!scriptData.ailTenant;
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

  function getExplicitArticle() {
    const list = document.querySelectorAll("[data-ail-article]");
    if (list.length === 0) return null;
    if (list.length === 1) return list[0];
    return list[0];
  }

  function nodeTextLength(el) {
    return (el?.innerText || el?.textContent || "").replace(/\s+/g, " ").trim().length;
  }

  function findArticleRoot() {
    const explicit = getExplicitArticle();
    if (explicit) return explicit;

    const selectors = [
      "main article",
      "main .post",
      "main .post-content",
      "main .entry-content",
      "article",
      "main",
      '[role="main"]',
      ".post-content, .entry-content, .article-body, .blog-post, .post-body"
    ];
    const firstHeading = document.querySelector("h1");

    for (const selector of selectors) {
      const matches = Array.from(document.querySelectorAll(selector)).filter(
        (node) => node && node.nodeType === 1
      );
      if (!matches.length) continue;

      const scored = matches
        .map((node) => ({
          node,
          hasHeading: !!(firstHeading && node.contains(firstHeading)),
          length: nodeTextLength(node)
        }))
        .filter((entry) => entry.length > 20);

      if (!scored.length) continue;

      const preferred = scored.filter((entry) => entry.hasHeading);
      const pool = preferred.length ? preferred : scored;
      pool.sort((a, b) => b.length - a.length);
      return pool[0].node;
    }

    return null;
  }

  function describeNode(node) {
    if (!node || !node.tagName) return "unknown";
    let desc = node.tagName.toLowerCase();
    if (node.id) desc += `#${node.id}`;
    const classes = Array.from(node.classList || []).slice(0, 2);
    if (classes.length) desc += `.${classes.join(".")}`;
    const role = node.getAttribute?.("role");
    if (role) desc += `[role=${role}]`;
    return desc;
  }

  function findMainHeading(root) {
    if (!root) return null;
    const primary = root.querySelector("h1");
    if (primary) return primary;
    return root.querySelector("h2, h3");
  }

  function extractArticleParts(listenButton) {
    let article = getExplicitArticle();

    if (!article) {
      if (listenButton) {
        article = listenButton.closest("article,[itemtype*='Article'],[role='main'],main");
      }
      if (!article) {
        article = findArticleRoot();
      }
    }

    if (!article) {
      console.warn("[EasyAudio] No article container found");
      return { title: "", author: "", bodyText: "", fullText: "" };
    }

    const titleEl =
      article.querySelector("[data-ail-title]") ||
      article.querySelector("h1, h2");
    const authorEl = article.querySelector("[data-ail-author]");
    const title = titleEl ? titleEl.textContent.replace(/\s+/g, " ").trim() : "";
    const author = authorEl ? authorEl.textContent.replace(/\s+/g, " ").trim() : "";

    const bodyRoot = article.querySelector("[data-ail-body]") || article;
    const blockedTags = new Set(["NAV", "ASIDE", "FOOTER", "HEADER"]);
    const bodyParts = [];
    const walker = document.createTreeWalker(
      bodyRoot,
      NodeFilter.SHOW_ELEMENT,
      {
        acceptNode(node) {
          if (blockedTags.has(node.tagName)) return NodeFilter.FILTER_REJECT;
          if (node.matches("p, li, blockquote")) return NodeFilter.FILTER_ACCEPT;
          return NodeFilter.FILTER_SKIP;
        }
      }
    );

    let current;
    while ((current = walker.nextNode())) {
      const text = (current.textContent || "").replace(/\s+/g, " ").trim();
      if (text) bodyParts.push(text);
    }

    const bodyText = bodyParts.join("\n\n").trim();
    const sections = [];
    if (title) sections.push(title);
    if (author) sections.push(author);
    if (bodyText) sections.push(bodyText);
    const fullText = sections.join("\n\n").trim();
    const snippet = fullText.slice(0, 160).replace(/\s+/g, " ");
    console.log("[EasyAudio] TTS text snippet:", snippet);

    return { title, author, bodyText, fullText };
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
      const autoInsertEnabled = Boolean(
        (opts.tenant && String(opts.tenant).trim()) || scriptHasTenant
      );

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

            const hasExplicit = !!getExplicitArticle();
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

        if (!autoInsertEnabled) {
          console.debug("[AIL] No .ail-listen trigger found; auto-insert disabled (no tenant).");
          return;
        }

        const articleRoot = findArticleRoot();
        if (!articleRoot) {
          console.warn("[AIL] No suitable article root found; Listen button not injected.");
          return;
        }

        const srcBase = (scriptEl && scriptEl.src) || location.href;
        ensureMiniStyles(srcBase);

        btn = document.createElement("button");
        btn.type = "button";
        btn.id = "ai-listen-btn";
        btn.classList.add("listen-btn", "ail-listen");
        if (className) btn.classList.add(className);
        btn.textContent = labelIdle;
        btn.style.display = "inline-block";
        btn.style.padding = "0.4rem 1.2rem";
        btn.style.borderRadius = "999px";
        btn.style.border = "none";
        btn.style.cursor = "pointer";
        btn.style.fontWeight = "600";

        const wrapper = document.createElement("div");
        wrapper.className = "ail-listen-auto";
        wrapper.appendChild(btn);

        const directHeading = findMainHeading(articleRoot);
        let insertionTarget = directHeading;
        if (!insertionTarget) {
          const parentHeading = findMainHeading(document);
          if (parentHeading && parentHeading.parentNode && articleRoot.contains(parentHeading)) {
            insertionTarget = parentHeading;
          }
        }

        if (insertionTarget && insertionTarget.parentNode) {
          insertionTarget.parentNode.insertBefore(wrapper, insertionTarget);
        } else {
          articleRoot.insertBefore(wrapper, articleRoot.firstChild);
        }

        attachListenHandler(btn);
        console.log("[AIL] Listen button attached near article root:", describeNode(articleRoot));
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
