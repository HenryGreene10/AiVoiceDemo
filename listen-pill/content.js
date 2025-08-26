// content.js — inline Listen pill with preview + telemetry

async function getBase() {
  try {
    const d = await chrome.storage.sync.get('listen_base');
    const v = d.listen_base || localStorage.getItem('listen_base') || 'http://127.0.0.1:3000';
    return v.replace(/\/+$/, '');
  } catch {
    return 'http://127.0.0.1:3000';
  }
}

// ---------------- helpers ----------------
const rid = () => (crypto.randomUUID?.() || String(Date.now()));

async function sendMetric(event, extra = {}) {
  try {
    const payload = { event, ts: Date.now(), domain: location.hostname, url: location.href, ...extra };
    const blob = new Blob([JSON.stringify(payload)], { type: "application/json" });
    const BASE = await getBase();
    navigator.sendBeacon?.(`${BASE}/metric`, blob);
  } catch {}
}

function toast(msg) {
  const t = document.createElement("div");
  t.textContent = msg;
  t.style.cssText = `
    position:fixed; left:50%; bottom:90px; transform:translateX(-50%);
    background:#111; color:#fff; padding:10px 14px; border-radius:999px;
    font:600 13px/1 system-ui,-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;
    z-index:2147483647; box-shadow:0 8px 24px rgba(0,0,0,.18);
  `;
  document.documentElement.appendChild(t);
  setTimeout(() => t.remove(), 1600);
}

function ensureAudio() {
  let a = document.getElementById("listen-audio");
  if (!a) {
    a = document.createElement("audio");
    a.id = "listen-audio";
    a.controls = true;
    a.autoplay = true;
    a.style.position = "fixed";
    a.style.right = "20px";
    a.style.bottom = "70px";
    a.style.zIndex = "2147483647";
    document.documentElement.appendChild(a);
  }
  return a;
}

async function previewClipInline(BASE) {
  try {
    sendMetric("preview_click");
    const res = await fetch(`${BASE}/extract?url=${encodeURIComponent(location.href)}`);
    if (!res.ok) throw new Error("extract failed");
    const j = await res.json();
    const clip = (j?.text || "").slice(0, 320); // ~3–5s
    if (!clip) throw new Error("no text");
    const a = ensureAudio();
    a.src = `${BASE}/tts?model=eleven_flash_v2&text=${encodeURIComponent(clip)}`;
    await a.play();
  } catch (err) {
    console.warn("[listen] preview error:", err);
    toast("Preview unavailable on this page.");
  }
}

function makeDraggable(el) {
  let sx=0, sy=0, ox=0, oy=0, dragging=false;
  const start=(e)=>{ dragging=true;
    sx=("touches" in e ? e.touches[0].clientX : e.clientX);
    sy=("touches" in e ? e.touches[0].clientY : e.clientY);
    const r=el.getBoundingClientRect(); ox=r.left; oy=r.top; e.preventDefault(); };
  const move=(e)=>{ if(!dragging) return;
    const cx=("touches" in e ? e.touches[0].clientX : e.clientX);
    const cy=("touches" in e ? e.touches[0].clientY : e.clientY);
    el.style.left=Math.max(8, ox+(cx-sx))+"px"; el.style.top=Math.max(8, oy+(cy-sy))+"px";
    el.style.right="auto"; el.style.bottom="auto"; };
  const end=()=>{ dragging=false; };
  el.addEventListener("mousedown", start);
  el.addEventListener("touchstart", start, { passive:false });
  window.addEventListener("mousemove", move);
  window.addEventListener("touchmove", move, { passive:false });
  window.addEventListener("mouseup", end);
  window.addEventListener("touchend", end);
}

// ---------------- inject pill ----------------
// Integrated sticky panel version
(function mountListenUI(){
  if (document.getElementById('listen-ui')) return;

  const container = document.querySelector('article') ||
                    document.querySelector('main [role=main]') ||
                    document.querySelector('main') || document.body;

  const ui = document.createElement('div');
  ui.id = 'listen-ui';
  ui.innerHTML = `
    <span id="listen-cur">0:00</span>
    <input id="listen-bar" type="range" min="0" max="100" value="0" />
    <span id="listen-dur">0:00</span>

    <button id="listen-rew"  class="listen-btn" type="button" title="Back 10s" aria-label="Back 10 seconds">
      <svg viewBox="0 0 24 24" fill="none"><path d="M10 6v3L5 5l5-4v3a8 8 0 108 8" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>
    </button>

    <button id="listen-play" type="button" title="Play / Pause" aria-label="Play">
      <svg viewBox="0 0 24 24" fill="none"><path d="M8 5v14l11-7z" fill="currentColor"/></svg>
    </button>

    <button id="listen-fwd" class="listen-btn" type="button" title="Forward 30s" aria-label="Forward 30 seconds">
      <svg viewBox="0 0 24 24" fill="none"><path d="M14 6v3l5-4-5-4v3a8 8 0 11-8 8" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>
    </button>
  `;

  const anchor = container.querySelector('h1, h2') || container.firstElementChild;
  if (anchor && anchor.parentNode) anchor.parentNode.insertBefore(ui, anchor.nextSibling);
  else container.prepend(ui);
  if (container === document.body) ui.classList.add('fallback');

  // audio element
  const audio = document.getElementById('listen-audio') || (()=>{ const a=document.createElement('audio'); a.id='listen-audio'; a.preload='none'; a.style.display='none'; document.documentElement.appendChild(a); return a; })();

  // refs
  const play = ui.querySelector('#listen-play');
  const rew  = ui.querySelector('#listen-rew');
  const fwd  = ui.querySelector('#listen-fwd');
  const bar  = ui.querySelector('#listen-bar');
  const cur  = ui.querySelector('#listen-cur');
  const dur  = ui.querySelector('#listen-dur');

  // helpers
  const fmt = (s)=>{ s = Math.max(0, s|0); const m=(s/60|0), ss=String(s%60).padStart(2,'0'); return `${m}:${ss}`; };
  const setIcon = ()=> {
    play.innerHTML = audio.paused
      ? `<svg viewBox="0 0 24 24" fill="none"><path d="M8 5v14l11-7z" fill="currentColor"/></svg>`
      : `<svg viewBox="0 0 24 24" fill="none"><rect x="6" y="5" width="4" height="14" fill="black"/><rect x="14" y="5" width="4" height="14" fill="black"/></svg>`;
  };

  let busy = false;
  const withBusy = (fn) => async (e) => {
    if (busy) return;
    busy = true; play.disabled = true; ui.style.opacity = '.85';
    try { await fn(e); } finally { setTimeout(()=>{ busy=false; play.disabled=false; ui.style.opacity='1'; }, 350); }
  };

  // audio <-> UI
  audio.addEventListener('loadedmetadata', ()=>{ dur.textContent = fmt(audio.duration); cur.textContent = fmt(0); bar.value = 0; });
  audio.addEventListener('timeupdate', ()=>{
    if (!audio.duration) return;
    cur.textContent = fmt(audio.currentTime);
    dur.textContent = fmt(audio.duration);
    bar.value = (audio.currentTime / audio.duration) * 100;
  });
  audio.addEventListener('play', setIcon);
  audio.addEventListener('pause', setIcon);
  audio.addEventListener('ended', setIcon);

  bar.addEventListener('input', ()=>{ if (audio.duration) audio.currentTime = (bar.value/100)*audio.duration; });
  rew.addEventListener('click', ()=>{ audio.currentTime = Math.max(0, audio.currentTime - 10); });
  fwd.addEventListener('click', ()=>{ if(audio.duration) audio.currentTime = Math.min(audio.duration, audio.currentTime + 30); });

  // preview vs full
  async function startPlayback(e){
    e?.preventDefault();
    const BASE = (await getBase()).replace(/\/+$/,'');
    if (!e?.shiftKey){
      try{
        const r = await fetch(`${BASE}/extract?url=${encodeURIComponent(location.href)}`);
        if (!r.ok) throw new Error('extract failed');
        const j = await r.json();
        const clip = (j?.text || '').slice(0, 320);
        if (!clip) throw new Error('no text');
        audio.src = `${BASE}/tts?model=eleven_flash_v2&text=${encodeURIComponent(clip)}`;
      }catch(err){ console.warn('[listen] preview error', err); return; }
    } else {
      audio.src = `${BASE}/read?url=${encodeURIComponent(location.href)}`;
    }
    try { await audio.play(); } catch {}
  }

  play.addEventListener('click', withBusy(async (e)=>{
    if (audio.src && !audio.paused){ audio.pause(); return; }
    return startPlayback(e);
  }), { capture: true });
  play.addEventListener('keydown', (e)=>{ if (e.key===' '||e.key==='Enter') startPlayback(e); });

  console.log('[listen] mini-player mounted on', location.hostname);
})();
