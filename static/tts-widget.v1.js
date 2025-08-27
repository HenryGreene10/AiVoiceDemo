// static/tts-widget.v1.js
(() => {
    if (window.__ttsWidgetLoaded) return; window.__ttsWidgetLoaded = true;
  
    // --- Config from <script data-*> ---
    const script   = document.currentScript;
    const ds       = (script && script.dataset) || {};
    const apiBase  = ((ds.base || 'http://127.0.0.1:3000') + '').replace(/\/+$/,'');
    const model    = (ds.model || 'eleven_turbo_v2') + '';
    const voiceId  = (ds.voice || '') + '';
    const stability = (ds.stability || '0.35') + '';
    const similarity = (ds.similarity || '0.75') + '';
    const style     = (ds.style || '0.40') + '';
    const opt       = (ds.opt || '2') + '';
    const startPadMs = parseInt(ds.startpad || '180', 10); // wait before play (0–500ms)
    const position = (ds.position || 'br').toLowerCase(); // br | bl | tr | tl
    const theme    = (ds.theme || 'light').toLowerCase(); // light | dark
  
    // --- Root overlay (click-through) ---
    const root = document.createElement('div');
    Object.assign(root.style, { position:'fixed', inset:'0', pointerEvents:'none', zIndex:'2147483647' });
    document.documentElement.appendChild(root);
  
    const host = document.createElement('div');
    root.appendChild(host);
    const shadow = host.attachShadow({ mode:'open' });
  
    const posClass =
      position === 'bl' ? 'pos-bl' :
      position === 'tr' ? 'pos-tr' :
      position === 'tl' ? 'pos-tl' : 'pos-br';
    const themeClass = theme === 'dark' ? 'theme-dark' : 'theme-light';
  
    shadow.innerHTML = `
      <style>
        :host { all: initial; }
        *, *::before, *::after { box-sizing: border-box; }
  
        /* THEME TOKENS */
        .theme-light { --bg:#ffffff; --fg:#111; --muted:#6b7280; --shadow:0 20px 50px rgba(0,0,0,.25); --btn:#111; --btnFg:#fff; --border:rgba(0,0,0,.06); }
        .theme-dark  { --bg:#151515; --fg:#eaeaea; --muted:#9ca3af; --shadow:0 20px 50px rgba(0,0,0,.45); --btn:#111; --btnFg:#fff; --border:rgba(255,255,255,.08); }
  
        .wrap { position: fixed; pointer-events: auto; }
        .pos-br .wrap { right:16px; bottom:16px; }
        .pos-bl .wrap { left:16px;  bottom:16px; }
        .pos-tr .wrap { right:16px; top:16px; }
        .pos-tl .wrap { left:16px;  top:16px;  }
  
        .btn {
          all: unset; cursor: pointer; display:inline-flex; align-items:center; gap:8px;
          padding:10px 14px; border-radius:14px; background:var(--btn); color:var(--btnFg);
          font:600 14px/1 system-ui; letter-spacing:.1px; box-shadow: var(--shadow);
          transition: transform .1s ease, opacity .2s ease;
          user-select: none; -webkit-tap-highlight-color: transparent;
        }
        .btn[disabled] { opacity:.6; cursor: default; }
        .btn:active { transform: translateY(1px); }
  
        .player {
          position: fixed; width: 340px; max-width: 92vw;
          border-radius:16px; background:var(--bg); color:var(--fg); border:1px solid var(--border);
          box-shadow: var(--shadow); padding:12px; display:none; pointer-events:auto;
          opacity:0; transform: translateY(10px); will-change: transform, opacity;
          transition: opacity .22s ease, transform .22s ease;
        }
        .pos-br .player { right:16px; bottom:64px; }
        .pos-bl .player { left:16px;  bottom:64px; }
        .pos-tr .player { right:16px; top:64px; }
        .pos-tl .player { left:16px;  top:64px;  }
  
        .player.open { display:block; opacity:1; transform: translateY(0); }
  
        @media (prefers-reduced-motion: reduce) {
          .player { transition: none; transform:none; }
          .btn { transition: none; }
        }
  
        .toprow { display:flex; align-items:center; justify-content:space-between; gap:8px; margin-bottom:6px; }
        .status { font:500 12px/1.3 system-ui; color:var(--muted); }
        .title  { font:600 12px/1.3 system-ui; color:var(--fg); white-space:nowrap; text-overflow:ellipsis; overflow:hidden; max-width: 70%; }
        .close  {
          all: unset; cursor: pointer; width:28px; height:28px; border-radius:999px;
          display:grid; place-items:center; color:var(--fg); background:transparent;
        }
        .close:hover { background:rgba(127,127,127,.12); }
  
        audio { width:100%; height:36px; }
  
        .hint { margin-top:6px; font:500 11px/1.2 system-ui; color:var(--muted); }
  
        .spinner {
          width:14px; height:14px; border-radius:999px; border:2px solid var(--muted); border-top-color:transparent;
          display:inline-block; vertical-align:middle; margin-left:6px; animation: sp .9s linear infinite;
        }
        @keyframes sp { to { transform: rotate(360deg); } }
  
        .toast {
          position: fixed; left:50%; transform: translateX(-50%);
          bottom: 16px; background:var(--bg); color:var(--fg);
          border:1px solid var(--border); box-shadow: var(--shadow);
          border-radius:12px; padding:8px 12px; font:600 12px/1.2 system-ui; display:none;
          pointer-events:auto;
        }
        .toast.show { display:block; animation: fade .22s ease both; }
        @keyframes fade { from { opacity:0; transform: translate(-50%, 6px); } to { opacity:1; transform: translate(-50%, 0); } }
      </style>
  
      <div class="${themeClass} ${posClass}">
        <div class="player" id="player" role="dialog" aria-modal="true" aria-label="AI voice player" aria-hidden="true">
          <div class="toprow">
            <div class="title" id="title"></div>
            <button class="close" id="closeBtn" aria-label="Close player" title="Close">✕</button>
          </div>
          <div class="status" id="status">Ready</div>
          <audio id="audio" controls preload="none"></audio>
          <div class="hint">Tip: hold <strong>Shift</strong> and click “Listen” for full article.</div>
        </div>
  
        <div class="wrap">
          <button class="btn" id="listenBtn" aria-label="Listen to this article">
            Listen
            <span class="spinner" id="btnSpin" style="display:none;"></span>
          </button>
        </div>
  
        <div class="toast" id="toast" role="status" aria-live="polite"></div>
      </div>
    `;
  
    // --- Elements ---
    const $ = (id) => shadow.getElementById(id);
    const player   = $('player');
    const listen   = $('listenBtn');
    const btnSpin  = $('btnSpin');
    const audioEl  = $('audio');
    const statusEl = $('status');
    const titleEl  = $('title');
    const closeBtn = $('closeBtn');
    const toastEl  = $('toast');
  
    // --- Utilities ---
    const emit = (type, extra={}) => {
      try {
        if (window.TTSWidget && typeof window.TTSWidget.onEvent === 'function') {
          window.TTSWidget.onEvent({ type, ts: Date.now(), ...extra });
        }
      } catch {}
    };
  
    const showToast = (msg, ms=2500) => {
      toastEl.textContent = msg;
      toastEl.classList.add('show');
      setTimeout(() => toastEl.classList.remove('show'), ms);
    };
  
    const setStatus = (t) => { statusEl.textContent = t; };
    const showBtnSpinner = (b) => { btnSpin.style.display = b ? 'inline-block' : 'none'; listen.disabled = !!b; };
    const sleep = (ms) => new Promise(r => setTimeout(r, ms));
    function waitCanPlay(el, timeout=5000) {
      return new Promise((resolve) => {
        let done = false;
        const on = () => { if (done) return; done = true; el.removeEventListener('canplay', on); resolve(); };
        el.addEventListener('canplay', on, { once: true });
        setTimeout(() => { if (done) return; done = true; el.removeEventListener('canplay', on); resolve(); }, timeout);
      });
    }
    function cleanStoryText(s) {
      if (!s) return s;
      s = s.replace(/\[\d+\]/g, "");
      s = s.replace(/\[(?:citation|clarification|verification)\s+needed\]/gi, "");
      s = s.replace(/\s*\((?:IPA[:\s]|pronunciation[:\s]|listen\b|\/)[^)]*\)\s*/gi, " ");
      s = s.replace(/\s+([,.;:!?])/g, "$1");
      s = s.replace(/([,.;:!?])(?=\S)/g, "$1 ");
      s = s.replace(/\s{2,}/g, " ").trim();
      return s;
    }
  
    function articleTitle() {
      return document.querySelector('h1')?.textContent?.trim() || document.title || 'Untitled';
    }
    function pagePreviewText(limit = 1200) {
      const paras = Array.from(document.querySelectorAll('article p, main p, p')).slice(0, 12);
      const raw = paras.map(p => p.innerText.trim()).filter(Boolean).join(' ');
      return cleanStoryText(raw).slice(0, limit);
    }
  
    async function previewClip() {
      const title = articleTitle(); titleEl.textContent = title;
      const body  = pagePreviewText(1200);
      const text  = `${title ? title + '. ' : ''}${body || 'This is a preview.'}`;
      const u = new URL(`${apiBase}/tts`);
      u.searchParams.set('model', model);
      u.searchParams.set('text', text);
      u.searchParams.set('stability', stability);
      u.searchParams.set('similarity', similarity);
      u.searchParams.set('style', style);
      u.searchParams.set('opt_latency', opt);
      if (voiceId) u.searchParams.set('voice', voiceId);
      return u.toString(); // server streams audio
    }
  
    async function fullArticle() {
      const isLocal = /^localhost$|^127\.0\.0\.1$/.test(location.hostname);
      const title = articleTitle(); titleEl.textContent = title;
      if (isLocal) {
        const body = cleanStoryText(pagePreviewText(20000));
        const text = `${title ? title + '. ' : ''}${body}`;
        const u = new URL(`${apiBase}/tts`);
        u.searchParams.set('model', model);
        u.searchParams.set('text', text);
        u.searchParams.set('stability', stability);
        u.searchParams.set('similarity', similarity);
        u.searchParams.set('style', style);
        u.searchParams.set('opt_latency', opt);
        if (voiceId) u.searchParams.set('voice', voiceId);
        return u.toString();
      }
      const url = `${apiBase}/read?url=${encodeURIComponent(location.href)}&model=${encodeURIComponent(model)}${voiceId ? `&voice=${encodeURIComponent(voiceId)}` : ''}`;
      return url;
    }
  
    async function ensureAudioAndPlay(src) {
      if (!src) return;
      setStatus('Loading…');
      showBtnSpinner(true);

      // Set source, force preload, and wait until the browser says it can play.
      audioEl.preload = 'auto';
      audioEl.autoplay = false;
      audioEl.src = src;

      await waitCanPlay(audioEl, 5000);
      audioEl.currentTime = 0; // make sure we start from the absolute beginning
      if (startPadMs > 0) await sleep(startPadMs); // tiny pause so first word isn’t clipped

      try {
        await audioEl.play();
        setStatus('Playing');
        emit('play_start', { src });
      } catch (err) {
        setStatus('Press play ▶');
        showToast('Autoplay blocked — press ▶');
        emit('play_autoplay_blocked');
      } finally {
        showBtnSpinner(false);
      }
    }
  
    // --- Player open/close + focus management ---
    let lastFocused = null;
    function openPlayer() {
      if (player.classList.contains('open')) return;
      player.style.display = 'block';
      player.classList.add('open');
      player.setAttribute('aria-hidden', 'false');
      lastFocused = document.activeElement;
      closeBtn.focus();
      window.addEventListener('keydown', onKeydown, true);
    }
    function closePlayer() {
      if (!player.classList.contains('open')) return;
      player.classList.remove('open');
      player.setAttribute('aria-hidden', 'true');
      // allow transition to finish then hide
      setTimeout(() => { if (!player.classList.contains('open')) player.style.display = 'none'; }, 220);
      window.removeEventListener('keydown', onKeydown, true);
      if (lastFocused && typeof lastFocused.focus === 'function') lastFocused.focus();
      emit('player_close');
    }
    function onKeydown(e) {
      if (e.key === 'Escape') { e.stopPropagation(); closePlayer(); }
    }
    closeBtn.addEventListener('click', (e)=>{ e.stopPropagation(); closePlayer(); });
  
    // --- Audio events for status ---
    audioEl.addEventListener('pause', () => setStatus('Paused'));
    audioEl.addEventListener('ended', () => setStatus('Ended'));
  
    // --- Listen button behavior ---
    listen.addEventListener('click', async (e) => {
      e.stopPropagation();
      if (!player.classList.contains('open')) openPlayer();
  
      try {
        const src = e.shiftKey ? await fullArticle() : await previewClip();
        await ensureAudioAndPlay(src);
      } catch (err) {
        console.error(err);
        setStatus('Error loading audio');
        showBtnSpinner(false);
        showToast('Error loading audio. Retry.');
        emit('play_error', { message: String(err?.message || err) });
      }
    });
  
    // --- Public API (optional) ---
    window.TTSWidget = {
      open:  () => openPlayer(),
      close: () => closePlayer(),
      isOpen: () => player.classList.contains('open'),
      async playPreview(){ openPlayer(); await ensureAudioAndPlay(await previewClip()); },
      async playFull(){ openPlayer(); await ensureAudioAndPlay(await fullArticle()); },
      onEvent: null, // set a handler: (evt) => { ... }
      setTheme(t){ /* convenience for future */ },
      setVoice(v){ /* use if your backend reads &voice= */ }
    };
  })();
  