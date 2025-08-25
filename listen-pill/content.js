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
    const clip = (j?.text || "").slice(0, 700); // ~8–10s
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
(function inject() {
  if (document.getElementById("listen-pill")) return;

  const pill = document.createElement("button");
  pill.id = "listen-pill";
  pill.type = "button";
  pill.textContent = "Listen (click = preview, Shift = full)";
  pill.title = "Stream this article as audio";
  pill.style.cssText = `
    position:fixed; right:20px; bottom:20px; z-index:2147483647;
    padding:12px 16px; border:0; border-radius:999px; cursor:pointer;
    background:#111; color:#fff; font:600 14px/1 system-ui,-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;
    box-shadow:0 10px 30px rgba(0,0,0,.18);
  `;

  let busy = false;
  async function withBusy(fn){
    if (busy) return;
    busy = true; pill.style.opacity = '.7'; pill.disabled = true;
    try { await fn(); } finally { setTimeout(()=>{ busy=false; pill.style.opacity='1'; pill.disabled=false; }, 700); }
  }

  pill.addEventListener("click", (e) => withBusy(async () => {
    e.preventDefault();
    const BASE = await getBase();
    if (!e.shiftKey) return previewClipInline(BASE);     // default = short preview
    const a = ensureAudio();                              // Shift = full article
    a.src = `${BASE}/read?url=${encodeURIComponent(location.href)}`;
    try { await a.play(); } catch {}
  }));

  chrome.storage?.onChanged?.addListener((c)=>{ if (c.listen_base) console.log('[listen] BASE updated:', c.listen_base.newValue); });
  

  document.documentElement.appendChild(pill);
  makeDraggable(pill);
  getBase().then(b => console.log("[listen] pill injected on", location.href, "→ backend:", b));

})();
