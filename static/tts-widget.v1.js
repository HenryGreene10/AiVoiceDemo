/* v18 — minimal auto-theme + options (no external CSS) */
if (!window.__ttsWidgetLoaded) window.__ttsWidgetLoaded = true;

(function () {
  const $ = (s, r=document) => r.querySelector(s);

  function sendMetric(apiBase, payload){
    try{
      const url = apiBase + "/metric";
      const body = JSON.stringify(payload);
      if (navigator.sendBeacon) {
        const blob = new Blob([body], {type:"application/json"});
        navigator.sendBeacon(url, blob);
      } else {
        fetch(url, {method:"POST", headers:{"Content-Type":"application/json"}, body}).catch(()=>{});
      }
    }catch{}
  }

  function fromDataset(script) {
    const d = script?.dataset || {};
    return {
      apiBase: (d.base || "").replace(/\/$/,""),
      voiceId: d.voice || "",
      tenantKey: d.tenant || "",
      selector: d.selector || "article",
      ui: {
        variant: d.variant || "floating",          // "floating" | "inline"
        position: d.position || "bottom-right",    // "top-left"|"top-right"|"bottom-left"|"bottom-right"
        labelIdle: d.labelIdle || "Listen",
        labelLoading: d.labelLoading || "Loading…",
        labelPause: d.labelPause || "Pause",
        labelError: d.labelError || "Error",
        className: d.class || "",                  // optional custom class for site CSS
        style: d.style || "",                      // optional inline style string
        autoTheme: (d.autotheme || "true") !== "false" // default true
      }
    };
  }

  function metaPick(selectors) {
    for (const s of selectors) {
      const el = document.querySelector(s);
      if (!el) continue;
      if (el.content) return el.content;
      const c = el.getAttribute?.('content'); if (c) return c;
      const t = el.textContent?.trim(); if (t) return t;
    }
    return "";
  }

  function getTitleAuthor() {
    const title  = metaPick(['meta[property="og:title"]','meta[name="twitter:title"]','meta[name="title"]']) || document.querySelector('h1')?.innerText || document.title || "";
    const author = metaPick(['meta[name="author"]','meta[property="article:author"]','.byline','.author']);
    return { title: (title||"").trim(), author: (author||"").trim() };
  }

  function pickMeta(selArr) {
    for (const s of selArr) {
      const el = document.querySelector(s);
      if (el) {
        if (el.content) return el.content;
        if (el.getAttribute) {
          const c = el.getAttribute("content");
          if (c) return c;
        }
        if (el.textContent) {
          const t = el.textContent.trim();
          if (t) return t;
        }
      }
    }
    return "";
  }

  function getTitle() {
    return pickMeta([
      'meta[property="og:title"]',
      'meta[name="twitter:title"]',
      'meta[name="title"]'
    ]) || (document.querySelector("h1")?.innerText ?? document.title ?? "");
  }

  function getAuthor() {
    return pickMeta([
      'meta[name="author"]',
      'meta[property="article:author"]',
      'meta[name="byl"]',
      '[rel="author"]',
      '[itemprop="author"]',
      '.byline, .author, .c-byline, .post-author'
    ]);
  }

  function getBody(selector) {
    // prefer common article containers
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

    // strip non-article elements
    clone.querySelectorAll([
      "nav","header","footer","aside","form",
      ".share",".ads,.advert,.sponsor",
      "button","audio","video","script","style","noscript","svg",
      "#ai-listen-btn","#ai-listen-audio"
    ].join(",")).forEach(n => n.remove());

    // headings/paras only
    let t = "";
    clone.querySelectorAll("h1,h2,h3,p,li,blockquote").forEach(n=>{
      const s = (n.innerText || "").replace(/\s+/g," ").trim();
      if (s) t += s + " ";
    });

    // clean + cap
    t = t.replace(/[^\x09\x0A\x0D\x20-\x7E\u00A0-\u024F]/g, " ");
    return t.slice(0, 2000).trim();
  }

  function cleanText(selector) {
    const title  = (getTitle()  || "").trim();
    const author = (getAuthor() || "").trim();
    const body   = (getBody(selector) || "").trim();

    let parts = [];
    if (title)  parts.push(title);
    if (author) parts.push(`By ${author}.`);
    if (body)   parts.push(body);

    let full = parts.join(" ");
    // final compact + cap to be safe
    full = full.replace(/\s+/g," ").trim().slice(0, 1200);
    return full || "This article has no readable text.";
  }

  // --- simple auto-theme based on host page ---
  function parseRGB(c){ const m = /rgba?\((\d+),\s*(\d+),\s*(\d+)/.exec(c||""); return m? [m[1],m[2],m[3]].map(Number):null; }
  function luminance([r,g,b]){ const a=[r,g,b].map(v=>{v/=255; return v<=.03928?v/12.92:Math.pow((v+.055)/1.055,2.4)}); return .2126*a[0]+.7152*a[1]+.0722*a[2]; }
  function chooseTextColor(bgCss){
    const rgb = parseRGB(bgCss); if(!rgb) return "#000";
    const L = luminance(rgb); return L < 0.5 ? "#fff" : "#000"; // dark bg -> white text
  }
  function detectHostTheme(){
    const bodyStyles = getComputedStyle(document.body);
    const font = bodyStyles.fontFamily || 'system-ui, -apple-system, Segoe UI, Roboto, sans-serif';
    // try to use the site's link color as "brand"
    const link = $('a'); 
    const linkColor = link ? getComputedStyle(link).color : bodyStyles.color || "rgb(17,17,17)";
    const textColor = chooseTextColor(linkColor);
    return { font, brandBg: linkColor, brandFg: textColor };
  }
  function applyAutoTheme(btn, ui){
    if (ui.className || ui.style || ui.variant === "inline") return; // respect explicit styling or inline placement
    const t = detectHostTheme();
    btn.style.background = t.brandBg;
    btn.style.color = t.brandFg;
    btn.style.border = "1px solid rgba(0,0,0,.15)";
    btn.style.borderRadius = "9999px";
    btn.style.padding = "10px 14px";
    btn.style.fontFamily = t.font;
    btn.style.boxShadow = "0 8px 24px rgba(0,0,0,.15)";
  }
  // --- end theme helpers ---

  async function getAudioUrl(apiBase, tenantKey, voiceId, text) {
    const headers = { "Content-Type": "application/json" };
    if (tenantKey) headers["x-tenant-key"] = tenantKey;

    console.log('[AIL] base=', apiBase, 'tenant=', tenantKey, 'voice=', voiceId);

    const r = await fetch(`${apiBase}/api/tts?voice=${encodeURIComponent(voiceId||"")}`, {
      method: "POST", headers, body: JSON.stringify({ text })
    });
    const body = await r.text();
    if (!r.ok) {
      if (body.includes("voice_not_found")) {
        const r2 = await fetch(`${apiBase}/api/tts`, { method:"POST", headers, body: JSON.stringify({ text }) });
        const b2 = await r2.text(); if (!r2.ok) throw new Error(`API ${r2.status}: ${b2}`);
        const j2 = JSON.parse(b2); return apiBase + j2.audioUrl;
      }
      throw new Error(`API ${r.status}: ${body}`);
    }
    const j = JSON.parse(body);
    if (!j?.audioUrl) throw new Error("No audioUrl returned");
    return apiBase + j.audioUrl;
  }

  function placeFloating(btn, position){
    btn.style.position = "fixed";
    btn.style.zIndex = "999999";
    btn.style.right = btn.style.left = btn.style.top = btn.style.bottom = "";
    const [v,h] = position.split("-");
    if (v==="top") btn.style.top="16px"; else btn.style.bottom="16px";
    if (h==="left") btn.style.left="16px"; else btn.style.right="16px";
  }

  function ensurePlayerUI() {
    let wrap = document.getElementById("ai-listen-popup");
    if (wrap) return wrap;

    wrap = document.createElement("div");
    wrap.id = "ai-listen-popup";
    Object.assign(wrap.style, {
      position: "fixed", inset: "0", background: "rgba(0,0,0,.45)",
      display: "flex", alignItems: "center", justifyContent: "center",
      zIndex: 999999
    });

    const card = document.createElement("div");
    Object.assign(card.style, {
      background: "#fff", color:"#111", minWidth:"320px", maxWidth:"560px",
      width:"92%", borderRadius:"12px", boxShadow:"0 20px 50px rgba(0,0,0,.3)",
      padding:"16px"
    });

    const head = document.createElement("div");
    head.textContent = "AI Listen";
    Object.assign(head.style, { font:"600 16px/1.2 system-ui, -apple-system, Segoe UI, Roboto, sans-serif", marginBottom:"8px" });

    const controls = document.createElement("div");
    controls.style.display = "flex";
    controls.style.alignItems = "center";
    controls.style.gap = "8px";

    const btnBack = document.createElement("button");
    btnBack.textContent = "« 10s";
    const btnPlay = document.createElement("button");
    btnPlay.textContent = "Play/Pause";
    const btnFwd = document.createElement("button");
    btnFwd.textContent = "10s »";
    const rate = document.createElement("select");
    ["0.8","1.0","1.2","1.5","2.0"].forEach(v=>{ const o=document.createElement("option"); o.value=v; o.text=v+"×"; if(v==="1.0") o.selected=true; rate.appendChild(o); });
    const close = document.createElement("button");
    close.textContent = "Close";

    [btnBack, btnPlay, btnFwd, rate, close].forEach(b=>{
      Object.assign(b.style, { padding:"8px 10px", borderRadius:"8px", border:"1px solid #ddd", background:"#f6f6f6", cursor:"pointer" });
    });

    controls.append(btnBack, btnPlay, btnFwd, rate, close);

    const audio = document.getElementById("ai-listen-audio") || (()=>{ const a=document.createElement("audio"); a.id="ai-listen-audio"; document.body.appendChild(a); return a; })();
    audio.controls = true; // native controls visible
    audio.style.width = "100%";
    audio.style.marginTop = "8px";

    // wire up
    btnBack.onclick = () => { try { audio.currentTime = Math.max(0, audio.currentTime - 10); } catch{} };
    btnFwd.onclick  = () => { try { audio.currentTime = Math.min((audio.duration||1e9), audio.currentTime + 10); } catch{} };
    btnPlay.onclick = () => { if (audio.paused) audio.play().catch(()=>{}); else audio.pause(); };
    rate.onchange   = () => { audio.playbackRate = parseFloat(rate.value || "1.0"); };

    close.onclick = () => { wrap.remove(); };

    card.append(head, controls, audio);
    wrap.appendChild(card);
    document.body.appendChild(wrap);
    return wrap;
  }

  window.AiListen = {
    init(opts={}) {
      const script = document.currentScript || $('script[src*="tts-widget.v1.js"]');
      const ds = fromDataset(script);
      const apiBase   = (opts.apiBase   ?? ds.apiBase).replace(/\/$/,"");
      const voiceId   = (opts.voiceId   ?? ds.voiceId)   || "";
      const tenantKey = (opts.tenantKey ?? ds.tenantKey) || "";
      const selector  =  opts.selector  ?? ds.selector;
      const ui        = Object.assign({}, ds.ui, opts.ui || {});

      // Helper to ensure mini-player is loaded
      async function ensureMiniLoaded(){
        if (window.AiMini) return;
        await new Promise((resolve, reject)=>{
          const s = document.createElement('script');
          // load mini-player from the same host as the widget
          s.src = new URL('mini-player.js', script.src).toString() + '?v=18';
          s.onload = resolve; s.onerror = reject;
          document.head.appendChild(s);
        });
      }

      // audio (singleton)
      let audioEl = document.getElementById("ai-listen-audio");
      if (!audioEl) { audioEl = document.createElement("audio"); audioEl.id="ai-listen-audio"; audioEl.preload="none"; document.body.appendChild(audioEl); }

      // button (singleton)
      let btn = document.getElementById("ai-listen-btn");
      if (!btn) {
        btn = document.createElement("button");
        btn.id = "ai-listen-btn";
        btn.type = "button";
        btn.textContent = ui.labelIdle;

        // ---- base look: transparent by default ----
        btn.style.background = "transparent";
        btn.style.color = "inherit";
        btn.style.border = "1px solid rgba(0,0,0,.2)";
        btn.style.borderRadius = "9999px";
        btn.style.padding = "10px 14px";
        btn.style.font = "500 14px/1 system-ui, -apple-system, Segoe UI, Roboto, sans-serif";
        btn.style.boxShadow = "none";
        btn.style.backdropFilter = "saturate(120%) blur(2px)"; // subtle on tinted sites
        btn.style.cursor = "pointer";
        btn.style.opacity = "0.95";
        // ------------------------------------------------
        if (ui.className) btn.className = ui.className;
        if (ui.style) btn.setAttribute("style", ui.style);
        if (ui.variant === "inline") { ( $(selector) || document.body).appendChild(btn); }
        else { document.body.appendChild(btn); placeFloating(btn, ui.position); }
        
        // count that the player was rendered (for CTR)
        sendMetric(apiBase, { event: "impression", url: location.href, voice: voiceId });
      } else {
        btn.textContent = ui.labelIdle;
        if (ui.className) btn.className = ui.className;
        if (ui.variant !== "inline") placeFloating(btn, ui.position);
      }

      if (ui.autoTheme !== false) applyAutoTheme(btn, ui);

      // interactions
      let busy = false;
      const setLabel = (t)=> (btn.textContent = t);
      btn.onclick = async ()=>{
        if (busy) return;
        busy = true; btn.disabled = true; setLabel(ui.labelLoading);
        
        // Track click event
        sendMetric(apiBase, { event:"click", url: location.href, voice: voiceId });
        
        try{
          const src = await getAudioUrl(apiBase, tenantKey, voiceId, cleanText(selector));
          audioEl.autoplay = true; audioEl.src = src; await audioEl.play();
          setLabel(ui.labelPause);

          // derive proper metadata
          const titleEl = document.querySelector('meta[property="og:title"]')?.content
                       || document.querySelector('h1')?.innerText
                       || document.title
                       || 'AI Listen';
          const authorEl = document.querySelector('meta[name="author"]')?.content
                        || document.querySelector('.byline,.author,[rel="author"]')?.textContent
                        || '';
          const subtitle = authorEl ? `By ${authorEl.trim()}` : location.hostname;

                     // open bottom mini-player (non-modal)
           try {
             await ensureMiniLoaded();
             
             // Apply auto-theme if allowed
             const scriptTag = document.querySelector('script[src*="tts-widget"]');
             const autoThemeAllowed = (scriptTag?.dataset?.autotheme ?? 'true') !== 'false';
             if (autoThemeAllowed && window.__AiListenAutoTheme) {
               window.__AiListenAutoTheme();
             }
             
             // make sure the mini bar uses the same audio element
             const miniAudio = window.AiMini.audio();
             if (miniAudio && miniAudio !== audioEl) {
               miniAudio.src = audioEl.src;
               try { await miniAudio.play(); } catch {}
             }
             window.AiMini.open({ title: titleEl, subtitle });
           } catch(e) {
             console.warn("[AiListen] Failed to load mini-player, falling back to popup:", e);
             // fallback to basic popup
             ensurePlayerUI();
           }
        } catch(e){ console.error("[AiListen]", e); setLabel(ui.labelError); }
        finally { busy = false; btn.disabled = false; }
      };

      // Track listening time
      let listened = 0, _t0 = 0;
      audioEl.addEventListener("play", ()=>{ 
        _t0 = performance.now(); 
        sendMetric(apiBase,{event:"start",url:location.href,voice:voiceId}); 
        setLabel(ui.labelPause);
      });
      audioEl.addEventListener("pause",()=>{ 
        if(_t0){ 
          listened += (performance.now()-_t0)/1000; 
          _t0=0; 
        }
        setLabel(ui.labelIdle);
      });
      audioEl.addEventListener("ended",()=>{ 
        if(_t0){ 
          listened += (performance.now()-_t0)/1000; 
          _t0=0; 
        }
        sendMetric(apiBase,{event:"ended", seconds: listened, url: location.href, voice: voiceId});
        listened = 0;
        setLabel(ui.labelIdle);
      });
      window.addEventListener("beforeunload",()=>{ 
        if(listened>0) sendMetric(apiBase,{event:"stop", seconds: listened, url:location.href, voice: voiceId}); 
      });
    }
  };
})();
  