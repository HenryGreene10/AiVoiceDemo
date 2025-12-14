// v108 — inline pill under H1, clean narration order, skip clutter, clean start
// NOTE: Auto-insertion uses MutationObserver to handle SPA/hydrated news sites.
// Cache behavior, hashing, and trial limits are owned by the backend and are not modified here.
console.log("[AIL] widget v108 LIVE", new Date().toISOString());

(() => {
  "use strict";
  if (window.__ttsWidgetLoaded) return;
  window.__ttsWidgetLoaded = true;

  let ailArticleRoot = null;
  let ailListenButton = null;
  let ailArticleDetectionDone = false;
  let ailArticleMutationObserver = null;
  let ailPlacementRetried = false;
  let ailFallbackPlaced = false;

  function logAIL(...args) {
    console.log("[AIL]", ...args);
  }

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

  function parseColor(str) {
    try {
      const c = document.createElement("canvas").getContext("2d");
      c.fillStyle = str || "#000";
      const rgb = c.fillStyle.replace(/[^\d,]/g, "").split(",").map((n) => +n.trim());
      return { r: rgb[0] || 0, g: rgb[1] || 0, b: rgb[2] || 0 };
    } catch {
      return { r: 0, g: 0, b: 0 };
    }
  }

  function luminance(color) {
    const c = parseColor(color);
    const L = (v) => {
      v /= 255;
      return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4);
    };
    return 0.2126 * L(c.r) + 0.7152 * L(c.g) + 0.0722 * L(c.b);
  }

  function isDarkColor(color) {
    try {
      return luminance(color) < 0.5;
    } catch {
      return false;
    }
  }

  function pickAccentColor() {
    const pill =
      document.querySelector(".listen-btn, #ai-listen-btn, .ail-listen") ||
      document.querySelector("#ai-fab, .ai-fab, [data-ai-fab]");
    if (pill) {
      const style = getComputedStyle(pill);
      return style.backgroundColor || style.color || "";
    }
    const anchor = document.querySelector("a");
    if (anchor) return getComputedStyle(anchor).color;
    return "";
  }

  function applyWidgetTheme(rootEl) {
    const target = rootEl || document.querySelector(".ai-mini-root") || document.body;
    const card = target?.querySelector?.(".ai-card");
    const cardStyle = card ? getComputedStyle(card) : getComputedStyle(target);
    const bodyStyle = getComputedStyle(document.body);
    const surface =
      (cardStyle && cardStyle.backgroundColor && cardStyle.backgroundColor !== "transparent"
        ? cardStyle.backgroundColor
        : null) ||
      (bodyStyle && bodyStyle.backgroundColor) ||
      "#ffffff";

    const darkSurface = isDarkColor(surface);
    const controlBg = darkSurface ? "#ffffff" : surface;
    const border = darkSurface ? "rgba(255,255,255,0.28)" : "rgba(0,0,0,0.12)";
    let accent = pickAccentColor();
    if (!accent || accent === "transparent") {
      accent = darkSurface ? "#8fd3ff" : "#1f4b99";
    }
    const iconColor = darkSurface ? "#000000" : "#1a1c1a";

    const applyTo = (el) => {
      if (!el || !el.style) return;
      el.style.setProperty("--ail-surface", surface);
      el.style.setProperty("--ail-control-bg", controlBg);
      el.style.setProperty("--ail-control-border", border);
      el.style.setProperty("--ail-accent", accent);
      el.style.setProperty("--ail-icon-color", iconColor);
      el.style.setProperty("--mp-bg", surface);
      el.style.setProperty("--mp-border", border);
      el.style.setProperty("--mp-progress-fill", accent);
      el.style.setProperty("--mp-progress-bg", border);
    };

    applyTo(document.documentElement);
    applyTo(target);
  }
  window.__AIL_applyWidgetTheme = applyWidgetTheme;

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

    if (!resp.ok) {
      let msg = "";
      try {
        msg = await resp.text();
      } catch {
        msg = "article-audio request failed";
      }
      throw new Error(`TTS ${resp.status}: ${msg || "article-audio failed"}`);
    }

    const blob = await resp.blob();
    if (window.__AIL_AUDIO_URL) {
      try {
        URL.revokeObjectURL(window.__AIL_AUDIO_URL);
      } catch {}
    }
    const objectUrl = URL.createObjectURL(blob);
    window.__AIL_AUDIO_URL = objectUrl;

    const headers = resp.headers || new Headers();
    const hash = headers.get("x-ail-hash") || null;
    const cachedHeader = (headers.get("x-cache") || "").toUpperCase();
    const cached = cachedHeader === "HIT";
    console.log("[AIL] article audio blob ready", { hash, cached });

    return {
      url: objectUrl,
      cached,
      hash,
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

  function isVisible(el) {
    if (!el) return false;
    const style = window.getComputedStyle ? getComputedStyle(el) : null;
    if (style && (style.display === "none" || style.visibility === "hidden" || style.opacity === "0")) {
      return false;
    }
    const rect = el.getBoundingClientRect ? el.getBoundingClientRect() : null;
    if (rect && (rect.width === 0 || rect.height === 0)) {
      return false;
    }
    return true;
  }

  function findLongestVisibleParagraph(root) {
    const scope = root || document;
    const paragraphs = scope.querySelectorAll("p");
    let winner = null;
    let longest = 0;
    paragraphs.forEach((p) => {
      if (!p) return;
      if (p.closest("nav, header, footer, aside")) return;
      if (!isVisible(p)) return;
      const text = (p.innerText || p.textContent || "").replace(/\s+/g, " ").trim();
      const len = text.length;
      if (len > longest) {
        longest = len;
        winner = p;
      }
    });
    return winner;
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

  function findArticleContext() {
    const root = findArticleRoot();
    if (!root) {
      return {
        root: null,
        heading: null,
        placementTarget: null,
        byline: null,
        firstBodyBlock: null,
      };
    }

    let heading = root.querySelector("h1") || root.querySelector("h2");

    if (!heading) {
      const docHeading =
        document.querySelector("article h1, main h1, [role='main'] h1") ||
        document.querySelector("article h2, main h2, [role='main'] h2");
      if (
        docHeading &&
        (docHeading.compareDocumentPosition(root) & Node.DOCUMENT_POSITION_FOLLOWING)
      ) {
        heading = docHeading;
      }
    }

    const byline =
      root.querySelector("[itemprop='author'], .byline, [data-type='byline'], [data-testid='author']") ||
      root.querySelector(".Article__subtitle, .metadata__byline");

    let placementTarget = null;
    if (heading) {
      const headerLike = heading.closest(
        "header, .metadata, .byline, .article-meta, .Article__header, .story-header"
      );
      placementTarget = headerLike || heading.parentElement || heading;
    }

    let firstBodyBlock = null;
    const searchScope = (byline && (byline.parentElement || root)) || root;
    if (searchScope) {
      firstBodyBlock = searchScope.querySelector(
        "p, .article__content p, .body-text p, section, div"
      );
      if (firstBodyBlock && !(firstBodyBlock.textContent || "").trim()) {
        firstBodyBlock = null;
      }
    }

    return { root, heading, placementTarget, byline, firstBodyBlock };
  }

  function findFirstBodyParagraph(root) {
    if (!root) return null;
    const MIN_CHARS = 80;
    const paragraphs = root.querySelectorAll("p");
    for (const p of paragraphs) {
      if (!p) continue;
      if (
        p.closest(
          "header, nav, footer, aside, [aria-label*='breadcrumb' i], [aria-label*='navigation' i]"
        )
      ) {
        continue;
      }
      if (!isVisible(p)) continue;
      const text = (p.textContent || "").replace(/\s+/g, " ").trim();
      if (text.length >= MIN_CHARS) {
        return p;
      }
    }
    return null;
  }

  function shortTextSnippet(text, max = 80) {
    const clean = (text || "").replace(/\s+/g, " ").trim();
    if (!clean) return "";
    return clean.length > max ? `${clean.slice(0, max)}…` : clean;
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
    let heading = null;

    if (!article && listenButton) {
      article = listenButton.closest("article,[itemtype*='Article'],[role='main'],main");
    }
    if (!article && ailArticleRoot) {
      article = ailArticleRoot;
    }

    const context = findArticleContext();
    if (!article && context.root) {
      article = context.root;
    }
    if (!heading && context.heading) {
      heading = context.heading;
    }

    if (!article) {
      console.warn("[EasyAudio] No article container found");
      return { title: "", author: "", bodyText: "", fullText: "" };
    }

    if (!heading) {
      heading = article.querySelector("[data-ail-title]") || article.querySelector("h1, h2");
    }

    const authorEl = article.querySelector("[data-ail-author]");
    const title = heading ? heading.textContent.replace(/\s+/g, " ").trim() : "";
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

      function sendMetric(eventName, extra = {}) {
        try {
          const base = (runtimeConfig.apiBase || window.location.origin).replace(/\/+$/, "");
          const payload = {
            event: eventName,
            tenant: runtimeConfig.tenant,
            page_url: extra.pageUrl || window.location.href,
            referrer: typeof extra.referrer === "string" ? extra.referrer : (document.referrer || ""),
            ts: Date.now()
          };
          const opts = {
            method: "POST",
            headers: {
              "content-type": "application/json",
              "x-tenant-key": runtimeConfig.tenant
            },
            body: JSON.stringify(payload)
          };
          try { opts.keepalive = true; } catch {}
          fetch(base + "/metric", opts).catch(() => {});
        } catch {
          // swallow
        }
      }

      window.__AIL_sendMetric = sendMetric;

      function attachListenHandler(btn) {
        if (btn.__ailBound) return;
        btn.__ailBound = true;

        btn.addEventListener("click", async (ev) => {
          ev.preventDefault();
          console.log("[AIL] Listen click");
          console.log("[AIL] Listen handler fired", { buttonId: btn.id || null });
          try { sendMetric("click_listen"); } catch {}

          try {
            const srcBase = (scriptEl && scriptEl.src) || location.href;
            await ensureMiniLoaded(srcBase);
            window.__AIL_applyWidgetTheme?.();

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

      function detachArticleObserver() {
        if (ailArticleMutationObserver) {
          ailArticleMutationObserver.disconnect();
          ailArticleMutationObserver = null;
          logAIL("MutationObserver detached after successful article detection.");
        }
      }

      function markArticleDetectionComplete() {
        if (!ailArticleDetectionDone) {
          ailArticleDetectionDone = true;
          detachArticleObserver();
        }
      }

      function setupArticleMutationObserver() {
        if (ailArticleMutationObserver || ailArticleDetectionDone) return;
        if (typeof MutationObserver === "undefined") return;

        ailArticleMutationObserver = new MutationObserver(() => {
          if (ailArticleDetectionDone) {
            detachArticleObserver();
            return;
          }
          if (ailPlacementRetried) return;

          if (!ailArticleMutationObserver) return;
          if (ailArticleMutationObserver.__pending) return;
          ailArticleMutationObserver.__pending = true;
          requestAnimationFrame(() => {
            if (!ailArticleMutationObserver) return;
            ailArticleMutationObserver.__pending = false;
            if (ailArticleDetectionDone) {
              detachArticleObserver();
              return;
            }
            ailPlacementRetried = true;
            initListenButton({ fromObserver: true });
          });
        });

        ailArticleMutationObserver.observe(document.body, {
          childList: true,
          subtree: true
        });
      }

      function initListenButton(opts = {}) {
        const fromObserver = !!(opts && opts.fromObserver);
        // 1) If a .ail-listen already exists, just wire it up.
        const manualBtn = document.querySelector(".ail-listen");
        if (manualBtn && !manualBtn.dataset.ailAuto) {
          manualBtn.id ||= "ai-listen-btn";
          manualBtn.classList.add("listen-btn", "ail-listen");
          if (className) manualBtn.classList.add(className);
          if (!manualBtn.textContent?.trim()) manualBtn.textContent = labelIdle;
          attachListenHandler(manualBtn);
          ailListenButton = manualBtn;
          markArticleDetectionComplete();
          return;
        }

        if (!autoInsertEnabled) {
          console.debug("[AIL] No .ail-listen trigger found; auto-insert disabled (no tenant).");
          return;
        }

        if (
          ailArticleDetectionDone &&
          ailListenButton &&
          document.body.contains(ailListenButton)
        ) {
          logAIL("Listen button already attached; skipping re-attach.");
          return;
        }

        const { root, placementTarget } = findArticleContext();
        const firstLongParagraph = root ? findFirstBodyParagraph(root) : null;

        const srcBase = (scriptEl && scriptEl.src) || location.href;
        ensureMiniStyles(srcBase);
        let btn = ailListenButton;
        if (!btn || !document.body.contains(btn)) {
          btn = document.createElement("button");
          btn.type = "button";
          btn.id = "ai-listen-btn";
          btn.classList.add("listen-btn", "ail-listen");
          btn.dataset.ailAuto = "1";
          if (className) btn.classList.add(className);
          btn.textContent = labelIdle;
          btn.style.display = "inline-block";
          btn.style.padding = "0.4rem 1.2rem";
          btn.style.borderRadius = "999px";
          btn.style.border = "none";
          btn.style.cursor = "pointer";
          btn.style.fontWeight = "600";
          attachListenHandler(btn);
          ailListenButton = btn;
        }

        const wrapper = document.createElement("div");
        wrapper.className = "ail-listen-button-wrapper";

        const previousWrapper = btn.closest && btn.closest(".ail-listen-button-wrapper");
        wrapper.appendChild(btn);
        if (previousWrapper && previousWrapper !== wrapper) {
          previousWrapper.remove();
        }

        if (firstLongParagraph && firstLongParagraph.parentElement) {
          firstLongParagraph.parentElement.insertBefore(wrapper, firstLongParagraph);
          ailArticleRoot = root;
          ailFallbackPlaced = false;
          markArticleDetectionComplete();
          logAIL("Listen button attached near long body paragraph", {
            snippet: shortTextSnippet(firstLongParagraph.textContent),
          });
          return;
        }

        const longestParagraph = findLongestVisibleParagraph(root || document);
        if (longestParagraph && longestParagraph.parentElement) {
          longestParagraph.parentElement.insertBefore(wrapper, longestParagraph);
          ailArticleRoot = root;
          ailFallbackPlaced = false;
          markArticleDetectionComplete();
          logAIL("Listen button attached near longest visible paragraph", {
            snippet: shortTextSnippet(longestParagraph.textContent),
          });
          return;
        }

        if (root) {
          logAIL("Listen button fallback placement (no long body paragraph found)", {
            reason: "no-long-para",
          });
        }

        if (placementTarget) {
          placementTarget.insertAdjacentElement("afterend", wrapper);
          ailArticleRoot = root;
          ailFallbackPlaced = false;
          markArticleDetectionComplete();
          logAIL("Listen button attached near article root:", describeNode(placementTarget));
          return;
        }

        if (root) {
          root.insertBefore(wrapper, root.firstChild);
          ailArticleRoot = root;
          ailFallbackPlaced = false;
          markArticleDetectionComplete();
          logAIL("Listen button attached at fallback article root:", describeNode(root));
          return;
        }

        document.body.insertAdjacentElement("afterbegin", wrapper);
        logAIL("No suitable article root; using generic placement only.");
        ailFallbackPlaced = true;
        if (fromObserver) {
          markArticleDetectionComplete();
        }
      }

      initListenButton();
      setupArticleMutationObserver();
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

  /*
   * Placement notes:
   * - Prefer the first long body paragraph (>80 chars) under the detected article root.
   * - Fall back to heading/byline/root placement if no qualifying paragraph is found.
   * - Duplicate guard and MutationObserver reattach logic remain unchanged.
   */

  /*
    Manual verification checklist:
    - Demo article: LISTEN button renders under the title/byline, first playback reads the headline, reload hits cache instantly.
    - CNN (hydrated DOM): MutationObserver repositions the button under the heading once content loads; first playback includes the headline and cache HITs on reload.
    - Host-provided button: no duplicate LISTEN buttons are injected.
  */
})();
