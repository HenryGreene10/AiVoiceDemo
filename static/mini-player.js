console.log('[AIL] mini v27 LIVE', new Date().toISOString());

(function(){
  const $ = (s,r=document)=>r.querySelector(s);

  // --- FAB control ------------------------------------------------------------
  let FAB = null;           // we remember the element we hid
  let fabObserver = null;   // keeps it hidden if the widget tries to swap it

  // Find the floating Listen pill in any of the ways the widget might inject it
  function getFab(){
    // common ids/classes + aria-labels that flip to "Pause"/"Play"
    return document.querySelector(
      '#ai-fab, .ai-fab, [data-ai-fab], button[aria-label="Listen"], button[aria-label="Play"], button[aria-label="Pause"]'
    );
  }

  // Hide *hard* so the widget can't keep using it
  function hideFab(hard = true){
    const el = getFab();
    if(!el) return;
    FAB = el;
    el.classList.add('hide');
    el.setAttribute('aria-hidden','true');
    el.style.pointerEvents = 'none';
    el.style.opacity = '0';
    if (hard) el.style.display = 'none';
  }

  // Restore when we close our mini-player
  function showFab(){
    const el = FAB || getFab();
    if(!el) return;
    el.classList.remove('hide');
    el.removeAttribute('aria-hidden');
    el.style.display = '';
    el.style.pointerEvents = '';
    el.style.opacity = '';
  }

  // When mini is open, keep hiding the pill if the widget re-renders it
  function startFabObserver(){
    if (fabObserver) return;
    fabObserver = new MutationObserver(() => {
      // if it reappears (or flips to Pause), hide again
      const el = getFab();
      if (el && (el.style.display !== 'none' || !el.classList.contains('hide'))){
        hideFab(true);
      }
    });
    fabObserver.observe(document.body, { childList:true, subtree:true });
  }
  function stopFabObserver(){
    fabObserver?.disconnect();
    fabObserver = null;
  }

  // Default icons (inline SVG)
  const DEFAULT_ICONS = {
    play:  '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M8 5v14l11-7z"/></svg>',
    pause: '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M6 5h4v14H6zM14 5h4v14h-4z"/></svg>',
    back:  '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M11 7v10l-6-5 6-5zm1 10V7l6 5-6 5z"/></svg>',
    fwd:   '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M13 7v10l6-5-6-5zm-1 10V7l-6 5 6 5z"/></svg>',
  };

  // Live icon map (can be overridden)
  const ICONS = {...DEFAULT_ICONS};

  // Helper: render icon (inline <svg> string OR image URL)
  function renderIcon(btn, icon){
    if (!btn) return;
    const s = String(icon||"");
    if (s.trim().startsWith("<svg")) {
      btn.innerHTML = s;
    } else if (s) {
      btn.innerHTML = `<img src="${s}" alt="" />`;
    } else {
      btn.innerHTML = "";
    }
  }

  // ---- Auto-theme (unchanged; keep your version if you already have it) ----
  window.__AiListenAutoTheme ??= (function(){
    function parse(str){ const c=document.createElement("canvas").getContext("2d"); c.fillStyle=str||"#000"; const rgb=c.fillStyle.replace(/[^\d,]/g,"").split(",").map(n=>+n.trim()); return {r:rgb[0]||0,g:rgb[1]||0,b:rgb[2]||0};}
    const lum = c=>{ const L=v=>{v/=255;return v<=.03928?v/12.92:Math.pow((v+.055)/1.055,2.4)}; return .2126*L(c.r)+.7152*L(c.g)+.0722*L(c.b); };
    const dark = bg => { try { return lum(parse(bg)) < .5; } catch { return true; } };
    return function apply(){
      const root=document.documentElement, bcs=getComputedStyle(document.body);
      let bg=bcs.backgroundColor||'#fff'; if(bg==='transparent') bg='#fff';
      root.style.setProperty('--mp-font', bcs.fontFamily || 'system-ui, -apple-system, Segoe UI, Roboto, sans-serif');
      root.style.setProperty('--mp-bg', bg);
      root.style.setProperty('--mp-fg', bcs.color || (dark(bg)?'#eaf2ff':'#111'));
      root.style.setProperty('--mp-muted', dark(bg)?'rgba(255,255,255,.68)':'#506070');
      root.style.setProperty('--mp-border', dark(bg)?'rgba(255,255,255,.12)':'rgba(0,0,0,.12)');
      const a=document.querySelector('a'); if(a) root.style.setProperty('--mp-accent', getComputedStyle(a).color);
    };
  })();

  // Create overlay once on widget bootstrap
  if(!document.getElementById('ai-overlay')){
    document.body.insertAdjacentHTML('beforeend', '<div id="ai-overlay"></div>');
  }

  // --- Playback persistence: remember time & rate per document ---------------
  function makePosStore(audio, meta){
    // Prefer a stable document key over transient audio src
    const docKey = (() => {
      const tag = document.querySelector('script[src*="tts-widget"]');
      const fromTag   = tag?.dataset?.docId || tag?.dataset?.articleId || null;
      const fromMeta  = meta?.id || meta?.key || meta?.url || null;
      const fromGlobal= (typeof window !== 'undefined' && (window.AIL_DOC_ID || window.AIL_ARTICLE_ID)) || null;
      const urlKey    = location.origin + location.pathname + location.search;
      return String(fromMeta || fromTag || fromGlobal || urlKey);
    })();

    const keyFor = () => `aiListen:v2:pos:${docKey}`;

    let lastSaved = 0;
    const save = () => {
      try{
        const now = Date.now();
        if (now - lastSaved < 500) return; // throttle
        lastSaved = now;
        const data = { t: Math.max(0, audio.currentTime || 0),
                       r: audio.playbackRate || 1, ts: now };
        const k = keyFor();
        localStorage.setItem(k, JSON.stringify(data));
        sessionStorage.setItem(k, JSON.stringify(data));
      }catch{}
    };

    const load = () => {
      try{
        const k = keyFor();
        const raw = sessionStorage.getItem(k) || localStorage.getItem(k);
        if (!raw) return null;
        const obj = JSON.parse(raw);
        return (obj && Number.isFinite(obj.t)) ? obj : null;
      }catch{ return null; }
    };

    const clearIfEnded = () => {
      try{
        const k = keyFor();
        localStorage.removeItem(k);
        sessionStorage.removeItem(k);
      }catch{}
    };

    return { save, load, clearIfEnded };
  }

  // VISUAL pre-hide on press, but keep pointer-events so the click still fires.
  document.addEventListener('pointerdown', (e) => {
    const el = getFab?.();
    if (!el) return;
    if (e.target === el || el.contains(e.target)) {
      el.classList.add('prehide');           // just fade it; do NOT disable pointer-events
    }
  }, true);

  // After the click is dispatched, fully hide the FAB so it won't flash back.
  document.addEventListener('click', (e) => {
    const el = getFab?.();
    if (!el) return;
    if (el.classList.contains('prehide')) {
      el.classList.remove('prehide');
      hideFab?.(true);                        // now do the real hide (pointer-events: none)
    }
  }, true);



  // Give the Listen pill stable selectors and the right color on first paint
  (function tagFabOnce(){
    function tag(el){
      if (!el) return;
      // stable selectors so CSS/JS work
      el.id ||= 'ai-fab';
      el.classList.add('ai-fab');
      el.setAttribute('data-ai-fab','');

      // ensure right color before first click (avoid initial black)
      const bodyBg = getComputedStyle(document.body).backgroundColor || 'inherit';
      el.style.background = bodyBg;   // matches page / mini-player
      el.style.color = '#000';
    }

    // try existing
    let el = getFab(); if (el) { tag(el); return; }

    // watch DOM until widget injects it
    const mo = new MutationObserver(() => {
      const el = getFab();
      if (el){ tag(el); mo.disconnect(); }
    });
    mo.observe(document.body, { childList:true, subtree:true });

    // set theme vars at startup so CSS using --mp-* has values immediately
    document.addEventListener('DOMContentLoaded', () => {
      window.__AiListenAutoTheme?.();
    });
  })();

  // Build the mini-player DOM
  function ensureMini(){
    let wrap = $('#ai-mini');
    if (wrap) return wrap;

    wrap = document.createElement('div');
    wrap.id = 'ai-mini';

    const card = document.createElement('div');
    card.className = 'ai-card';
    card.innerHTML = `
      <button class="ai-close" id="mp-close" aria-label="Close player"></button>

      <div class="ai-title" id="mp-title">AI Listen</div>
      <div class="ai-meter">
        <div class="ai-progress">
          <input type="range" min="0" max="100" value="0" class="ai-range" id="mp-seek" aria-label="Seek">
        </div>
        <div class="ai-timebar">
          <div id="mp-elapsed">0:00</div>
          <div id="mp-total">--:--</div>
        </div>
      </div>

      <div class="ai-controls">
        <button class="ai-btn side"    id="mp-back" aria-label="Back 10 seconds"></button>
        <button class="ai-btn primary" id="mp-play" aria-label="Play"></button>
        <button class="ai-btn side"    id="mp-fwd"  aria-label="Forward 10 seconds"></button>
      </div>

      <div class="ai-footer">
        <select class="ai-rate" id="mp-rate" title="Playback speed" aria-label="Playback speed">
          <option>0.8x</option><option selected>1.0x</option>
          <option>1.2x</option><option>1.5x</option><option>2.0x</option>
        </select>
      </div>
    `;
    wrap.appendChild(card);
    document.body.appendChild(wrap);
    return wrap;
  }

  const fmt = t => { t=Math.max(0,Math.floor(t||0)); const m=Math.floor(t/60), s=t%60; return `${m}:${String(s).padStart(2,'0')}`; };

  // put near your other helpers
  function setPlayVisual(play, isPlaying){
    play.setAttribute('data-icon', isPlaying ? 'pause' : 'play');
    // update inline SVG if you're using defaults
    play.innerHTML = isPlaying
      ? '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M6 5h4v14H6zM14 5h4v14h-4z"/></svg>'
      : '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M8 5v14l11-7z"/></svg>';
  }

  function bindMini(audio, meta){
    const wrap = ensureMini();
    const q = id => wrap.querySelector(id);

    // --- Remember/restore position
    const pos = makePosStore(audio, meta);

    function restorePosition(saved){
      if(!saved) return;
      const apply = () => {
        try{
          if (Number.isFinite(saved.t)) {
            if (isFinite(audio.duration) && audio.duration > 0) {
              const clamp = Math.min(Math.max(saved.t, 0), Math.max(0, audio.duration - 0.25));
              audio.currentTime = clamp;
            } else {
              audio.currentTime = Math.max(0, saved.t);
            }
          }
          if (Number.isFinite(saved.r) && saved.r > 0) {
            audio.playbackRate = saved.r;
            const rateSel = q('#mp-rate'); if (rateSel) rateSel.value = `${saved.r.toFixed(1)}x`;
          }
        }catch{}
      };

      if (!isFinite(audio.duration) || !(audio.duration > 0)){
        const once = () => { audio.removeEventListener('loadedmetadata', once);
                             audio.removeEventListener('durationchange', once);
                             apply(); };
        audio.addEventListener('loadedmetadata', once);
        audio.addEventListener('durationchange', once);
      }
      apply();
    }

    // Early restore attempt
    restorePosition(pos.load());

    // meta
    q('#mp-title').textContent = meta?.title || 'AI Listen';

    const play = q('#mp-play'), back = q('#mp-back'), fwd = q('#mp-fwd');
    back.classList.add('side'); fwd.classList.add('side');

    back.setAttribute('data-icon','back');
    fwd.setAttribute('data-icon','fwd');
    play.setAttribute('data-icon','play');

    const rate  = q('#mp-rate');
    const seek  = q('#mp-seek');
    const el    = q('#mp-elapsed');
    const total = q('#mp-total');

    const fmt = t => {
      t = Math.max(0, Math.floor(t||0));
      const m = Math.floor(t/60), s = t%60;
      return `${m}:${String(s).padStart(2,'0')}`;
    };

    function setPlayVisual(isPlaying){
      play.setAttribute('data-icon', isPlaying ? 'pause' : 'play');
      // swap inline svg if you're not using custom masks
      play.innerHTML = isPlaying
        ? '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M6 5h4v14H6zM14 5h4v14h-4z"/></svg>'
        : '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M8 5v14l11-7z"/></svg>';
    }

    function setProgress(){
      const d = (isFinite(audio.duration) && audio.duration > 0) ? audio.duration : 0;
      const c = Math.max(0, audio.currentTime || 0);
      const pct = d ? Math.min(100, Math.max(0, (c/d)*100)) : 0;

      seek.value = String(Math.round(pct));
      seek.style.background =
        `linear-gradient(90deg, var(--mp-progress-fill) ${pct}%,
                               var(--mp-progress-bg) ${pct}%)`;
      el.textContent = fmt(c);
    }

    function tryUpdateTotal(){
      const d = audio.duration;
      if (isFinite(d) && d > 0){
        total.textContent = fmt(d);
        clearInterval(totalTimer);
      }
    }

    /* wire controls */
    play.onclick = ()=> audio.paused ? audio.play().catch(()=>{}) : audio.pause();
    back.onclick = ()=> { audio.currentTime = Math.max(0, (audio.currentTime||0) - 10); setProgress(); };
    fwd.onclick  = ()=> { const d = audio.duration||1e9; audio.currentTime = Math.min(d, (audio.currentTime||0) + 10); setProgress(); };
    rate.onchange= ()=> { audio.playbackRate = parseFloat(rate.value)||1; };
    seek.oninput = ()=> {
      const d = audio.duration||0;
      if (d) audio.currentTime = d * (parseInt(seek.value||'0',10)/100);
      setProgress();
    };

    // ensure the browser loads timing info
    audio.preload = 'metadata';

    // fire a few different hooks + a short polling fallback
    ['loadedmetadata','loadeddata','canplay','canplaythrough','durationchange']
      .forEach(ev => audio.addEventListener(ev, tryUpdateTotal));

    const totalTimer = setInterval(tryUpdateTotal, 500);

    // Save frequently
    audio.addEventListener('timeupdate', ()=>{ setProgress(); pos.save(); });
    audio.addEventListener('pause',      ()=>{ pos.save(); setPlayVisual(false); });
    audio.addEventListener('ratechange', ()=>{ pos.save(); });

    // Kick an immediate render so numbers show instantly
    tryUpdateTotal();
    setProgress();


    // Play state
    audio.addEventListener('play',  ()=> setPlayVisual(true));

    // Clear when finished
    audio.addEventListener('ended', ()=>{ setPlayVisual(false); pos.clearIfEnded(); });

    // Also try to restore once metadata lands (in addition to early attempt)
    audio.addEventListener('loadedmetadata', ()=> restorePosition(pos.load()));

    // If the tab hides (navigate/refresh), save once more
    document.addEventListener('visibilitychange', ()=>{ if(document.hidden) pos.save(); });

    // initial state
    total.textContent = '--:--';
    el.textContent    = '0:00';
    setPlayVisual(!audio.paused);
    setProgress();
    wrap.classList.add('show');

    // Hide pill on open, show on close
    hideFab(true);           // make the Listen pill go away immediately
    startFabObserver();      // keep it hidden if the widget flips it to "Pause"
    document.getElementById('ai-overlay')?.classList.add('show');

    // Wire up close functionality
    const overlay = document.getElementById('ai-overlay');
    const closeBtn = q('#mp-close');

    function closePlayer(){
      try{ pos.save(); }catch{}
      try{ audio.pause(); }catch{}
      wrap.classList.remove('show');
      document.getElementById('ai-overlay')?.classList.remove('show');
      stopFabObserver();       // stop watching
      showFab();               // bring the Listen pill back
    }

    // × button
    closeBtn.addEventListener('click', closePlayer);

    // click outside
    overlay?.addEventListener('click', closePlayer);

    // Esc key
    document.addEventListener('keydown', (e)=>{
      if(e.key === 'Escape' && wrap.classList.contains('show')) closePlayer();
    });
  }

  // Public API
  window.AiMini = {
    open(meta){
      // auto-theme unless disabled on the widget script tag
      const tag = document.querySelector('script[src*="tts-widget"]');
      const allow = (tag?.dataset?.autotheme ?? 'true') !== 'false';
      if (allow) window.__AiListenAutoTheme?.();

      let audio = document.getElementById('ai-listen-audio');
      if (!audio){
        audio = document.createElement('audio');
        audio.id = 'ai-listen-audio';
        document.body.appendChild(audio);
      }
      bindMini(audio, meta||{});
    },
    audio(){ return document.getElementById('ai-listen-audio'); },
    /** Override icons at runtime. Accepts inline <svg> strings OR image URLs. */
    useIcons(map){
      for (const k of ['play','pause','back','fwd']){
        if (map?.[k]) ICONS[k] = map[k];
      }
      // Refresh current buttons if mounted:
      const wrap = $('#ai-mini'); if (!wrap) return;
      renderIcon(wrap.querySelector('#mp-back'),  ICONS.back);
      renderIcon(wrap.querySelector('#mp-fwd'),   ICONS.fwd);
      // center button depends on state; just set to current:
      const play = wrap.querySelector('#mp-play');
      if (play){
        const audio = document.getElementById('ai-listen-audio');
        const icon = audio && !audio.paused ? ICONS.pause : ICONS.play;
        renderIcon(play, icon);
      }
    }
  };

  /* ---------- FAB helpers ---------- */
  function getFab(){
    return document.querySelector('#ai-fab, .ai-fab, [data-ai-fab]');
  }
  function hideFab(on = true){
    const el = getFab(); if (!el) return;
    el.classList.toggle('hide', !!on);
    el.classList.remove('prehide');  // clear any prehide residue
  }

  /* Prehide on press (visual only) so there's no flash, but still let click fire. */
  document.addEventListener('pointerdown', (e) => {
    const el = getFab(); if (!el) return;
    if (e.target === el || el.contains(e.target)) {
      el.classList.add('prehide');     // fade immediately
      // DO NOT disable pointer-events here – we want the click to go through
    }
  }, true);

  /* After click dispatches, do the real hide so the pill doesn't come back. */
  document.addEventListener('click', (e) => {
    const el = getFab(); if (!el) return;
    if (el.classList.contains('prehide')) {
      el.classList.remove('prehide');
      hideFab(true);                   // full hide (opacity + pointer-events)
    }
  }, true);

  /* Always wire the FAB to open the mini if it isn't open already. */
  function wireFabOpen(){
    const el = getFab();
    if (!el || el.dataset.aiWired) return;
    el.dataset.aiWired = '1';

    el.addEventListener('click', (ev) => {
      // If mini is visible, let the close/X handle it later
      const mini = document.getElementById('ai-mini');
      if (mini && mini.classList.contains('show')) return;

      // Call our mini explicitly (safe to call even if your widget also calls it)
      AiMini.open({
        title: document.querySelector('h1, [data-title]')?.textContent || document.title
      });
    });
  }

  /* Watch DOM additions in case the widget re-renders the FAB */
  wireFabOpen();
  new MutationObserver(wireFabOpen).observe(document.body, { childList:true, subtree:true });

  /* When the mini closes, make sure FAB is back and fully reset */
  (function(){
    const overlay = document.getElementById('ai-overlay');
    function onClosed(){
      hideFab(false);                  // show FAB again
    }
    // If your code already calls hideFab(false) in closePlayer, that's fine;
    // this is just a safety net if close happens by overlay/Esc etc.
    overlay?.addEventListener('transitionend', (e)=>{
      if (!overlay.classList.contains('show')) onClosed();
    });
  })();
})();
  