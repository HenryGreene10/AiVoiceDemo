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
(function injectPanel(){
  if (document.getElementById('listen-panel')) return;

  const container =
    document.querySelector('article, main [role=main], main, [data-test="ArticlePage"]') ||
    document.body;

  const panel = document.createElement('div');
  panel.id = 'listen-panel';
  panel.innerHTML = `
    <button id="listen-pp" aria-label="Play preview">▶</button>
    <div id="listen-title">Listen preview — Shift for full</div>
    <div class="listen-progress">
      <input id="listen-bar" type="range" min="0" max="100" value="0" />
    </div>
    <div id="listen-time">0:00 / 0:00</div>
    <div id="listen-close" title="Close">✕</div>
  `;

  if (container === document.body) panel.classList.add('fallback');
  if (container.firstElementChild) container.insertBefore(panel, container.firstElementChild);
  else container.appendChild(panel);

  let busy = false;

  function ensureDockedAudio(){
    let a = document.getElementById('listen-audio');
    if (!a){
      a = document.createElement('audio');
      a.id = 'listen-audio'; a.autoplay = true;
      panel.appendChild(a);
      wireAudio(a);
    }
    return a;
  }

  function fmt(t){ t=Math.max(0, t|0); const m=(t/60)|0, s=(t%60)|0; return m+":"+String(s).padStart(2,'0'); }

  function wireAudio(a){
    const pp = panel.querySelector('#listen-pp');
    const bar = panel.querySelector('#listen-bar');
    const time = panel.querySelector('#listen-time');
    const title = panel.querySelector('#listen-title');
    const close = panel.querySelector('#listen-close');
    title.textContent = (document.title || '').slice(0,60);
    close.onclick = ()=>{ a.pause(); panel.remove(); };

    a.addEventListener('play', ()=>{ pp.textContent='⏸'; });
    a.addEventListener('pause', ()=>{ pp.textContent='▶'; });
    a.addEventListener('timeupdate', ()=>{
      if (a.duration){ bar.value = ((a.currentTime/a.duration)*100)|0; time.textContent = fmt(a.currentTime) + ' / ' + fmt(a.duration); }
    });
    a.addEventListener('durationchange', ()=>{ if (a.duration){ time.textContent = fmt(a.currentTime) + ' / ' + fmt(a.duration); }});
    a.addEventListener('ended', ()=>{ pp.textContent='▶'; });
    bar.oninput = ()=>{ if (a.duration){ a.currentTime = (bar.value/100)*a.duration; }};
  }

  // After building panel and audio, bind controls
  const pp = panel.querySelector('#listen-pp');
  const bar = panel.querySelector('#listen-bar');
  const time = panel.querySelector('#listen-time');
  const title = panel.querySelector('#listen-title');
  const close = panel.querySelector('#listen-close');

  // make sure it's a real button, not a submit
  pp.setAttribute('type', 'button');
  // ensure clicks are allowed even if parents disable them
  panel.style.pointerEvents = 'auto';
  pp.style.pointerEvents = 'auto';

  // busy wrapper that forwards the event
  function withBusy(fn) {
    return async function (e) {
      console.log('[listen] handler entered');
      if (busy) return;
      busy = true; pp.disabled = true; panel.style.opacity = '.85';
      try { await fn(e); } finally {
        setTimeout(() => { busy = false; pp.disabled = false; panel.style.opacity = '1'; }, 500);
      }
    };
  }

  async function handleClick(e) {
    console.log('[listen] click', { shift: e?.shiftKey });
    if (e) { e.preventDefault(); e.stopPropagation(); }
    const BASE = await getBase();
    if (!e?.shiftKey) {
      title.textContent = 'Previewing…';
      await previewClipInline(BASE);
      return;
    }
    title.textContent = 'Reading full article…';
    const a = ensureDockedAudio();
    a.src = `${BASE}/read?url=${encodeURIComponent(location.href)}`;
    try { await a.play(); } catch {}
  }

  const onClick = withBusy(handleClick);
  // bind multiple routes so page overlays can't eat the event
  pp.addEventListener('click', onClick, { capture: true });
  pp.addEventListener('pointerdown', (e) => { if (e.button === 0) onClick(e); }, { capture: true });
  // keyboard accessibility
  pp.addEventListener('keydown', (e) => { if (e.key === 'Enter' || e.key === ' ') onClick(e); });
  // delegation fallback if node swapped
  panel.addEventListener('click', (e) => { if (e.target.closest && e.target.closest('#listen-pp')) onClick(e); }, { capture: true });

  console.log('[listen] panel bound on', location.hostname);
})();
