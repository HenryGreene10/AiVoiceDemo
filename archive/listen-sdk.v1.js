(() => {
  if (window.__listenSDKLoaded) return; window.__listenSDKLoaded = true;

  const script = document.currentScript;
  const ds = (script && script.dataset) || {};
  const cfg = {
    base: (ds.base || 'http://127.0.0.1:3000').replace(/\/+$/, ''),
    voice: ds.voice || '',
    model: ds.model || 'eleven_turbo_v2',
    position: (ds.position || 'right-bottom').toLowerCase(),
    theme: (ds.theme || 'dark').toLowerCase(),
  };

  function sendMetric(event, extra) {
    try {
      const payload = { event, ts: Date.now(), url: location.href, domain: location.hostname, ...extra };
      const blob = new Blob([JSON.stringify(payload)], { type: 'application/json' });
      navigator.sendBeacon?.(`${cfg.base}/metric`, blob);
    } catch {}
  }

  function ensureAudio() {
    let a = document.getElementById('listen-audio');
    if (!a) {
      a = document.createElement('audio');
      a.id = 'listen-audio';
      a.controls = true; a.autoplay = true;
      a.style.position = 'fixed';
      a.style.zIndex = '2147483647';
      positionElement(a, true);
      document.documentElement.appendChild(a);
    }
    return a;
  }

  function positionElement(el, isAudio){
    el.style.left = el.style.right = el.style.top = el.style.bottom = 'auto';
    const offset = isAudio ? 70 : 20;
    switch (cfg.position) {
      case 'right-top': el.style.right = '20px'; el.style.top = `${offset}px`; break;
      case 'left-bottom': el.style.left = '20px'; el.style.bottom = `${offset}px`; break;
      case 'left-top': el.style.left = '20px'; el.style.top = `${offset}px`; break;
      default: el.style.right = '20px'; el.style.bottom = `${offset}px`; break; // right-bottom
    }
  }

  function applyTheme(el){
    if (cfg.theme === 'light') {
      el.style.background = '#fff';
      el.style.color = '#111';
      el.style.boxShadow = '0 10px 30px rgba(0,0,0,.18)';
    } else {
      el.style.background = '#111';
      el.style.color = '#fff';
      el.style.boxShadow = '0 10px 30px rgba(0,0,0,.25)';
    }
  }

  function getTextSimple(){
    const root = document.querySelector('article, main, [role=main]') || document.body;
    const keep = root.querySelectorAll('h1,h2,h3,p,li');
    const bad = new Set(['NAV','FOOTER','ASIDE','BUTTON','INPUT','TEXTAREA','SELECT','SCRIPT','STYLE']);
    const parts = [];
    keep.forEach(el => {
      if (bad.has(el.tagName)) return;
      if (el.closest('nav,footer,aside,header,[role="button"],[aria-hidden="true"]')) return;
      const t = (el.innerText || '').trim();
      if (t) parts.push(t);
    });
    return parts.join('\n\n').slice(0, 15000);
  }

  async function previewClipInline(){
    sendMetric('preview_click');
    try{
      const r = await fetch(`${cfg.base}/extract?url=${encodeURIComponent(location.href)}`);
      const j = await r.json();
      const clip = (j?.text || getTextSimple()).slice(0, 700);
      if (!clip) throw new Error('no text');
      const a = ensureAudio();
      a.src = `${cfg.base}/tts?model=eleven_flash_v2&text=${encodeURIComponent(clip)}`;
      await a.play();
    }catch(e){ console.warn('[listen-sdk] preview error', e); }
  }

  // inject pill
  const pill = document.createElement('button');
  pill.textContent = 'Listen (click = preview, Shift = full)';
  pill.type = 'button';
  pill.style.position = 'fixed';
  pill.style.padding = '12px 16px';
  pill.style.border = '0'; pill.style.borderRadius = '999px'; pill.style.cursor = 'pointer';
  pill.style.zIndex = '2147483647';
  positionElement(pill, false);
  applyTheme(pill);
  document.documentElement.appendChild(pill);

  let busy = false;
  function withBusy(fn){
    if (busy) return;
    busy = true; pill.style.opacity = '.7'; pill.disabled = true;
    Promise.resolve(fn()).finally(()=> setTimeout(()=>{ busy=false; pill.style.opacity='1'; pill.disabled=false; }, 700));
  }

  pill.addEventListener('click', (e)=> withBusy(async ()=>{
    e.preventDefault();
    if (!e.shiftKey) return previewClipInline();
    sendMetric('listen_click');
    const a = ensureAudio();
    a.src = `${cfg.base}/read?url=${encodeURIComponent(location.href)}`;
    try{ await a.play(); }catch{}
  }));
})();


