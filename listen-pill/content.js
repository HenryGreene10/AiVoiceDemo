// content.js — Listen pill with preview + telemetry (MV3 content script)

// Change this if your backend is on a different port or HTTPS tunnel.
// You can also override at runtime via: localStorage.listen_base = "https://your-tunnel.example";
const BASE = (localStorage.getItem("listen_base") || "http://127.0.0.1:3000").replace(/\/+$/, "");

// ---- helpers ---------------------------------------------------------------

const rid = () => (crypto.randomUUID?.() || String(Date.now()));

function sendMetric(event, extra = {}) {
  try {
    const payload = {
      event,
      ts: Date.now(),
      domain: location.hostname,
      url: location.href,
      ...extra,
    };
    const blob = new Blob([JSON.stringify(payload)], { type: "application/json" });
    navigator.sendBeacon?.(`${BASE}/metric`, blob);
  } catch {
    /* no-op */
  }
}

async function preview10s() {
  try {
    sendMetric("preview_click");
    const res = await fetch(`${BASE}/extract?url=${encodeURIComponent(location.href)}`, { method: "GET" });
    if (!res.ok) throw new Error("extract failed");
    const j = await res.json();
    const text = (j?.text || "").slice(0, 500); // ~10–12s
    if (!text) throw new Error("no text");
    const u = `${BASE}/tts?text=${encodeURIComponent(text)}`;
    window.open(u, "_blank", "noopener");
  } catch (e) {
    console.warn("[listen] preview error:", e);
    toast("Preview unavailable on this page.");
  }
}

function toast(msg) {
  // tiny inline toast so you get feedback without extra CSS
  const t = document.createElement("div");
  t.textContent = msg;
  t.style.cssText = `
    position:fixed; left:50%; bottom:90px; transform:translateX(-50%);
    background:#111; color:#fff; padding:10px 14px; border-radius:999px;
    font:600 13px/1 system-ui,-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;
    z-index:2147483647; box-shadow:0 8px 24px rgba(0,0,0,.18);
  `;
  document.documentElement.appendChild(t);
  setTimeout(() => t.remove(), 1800);
}

// simple drag so you can reposition the pill during the demo
function makeDraggable(el) {
  let sx = 0, sy = 0, ox = 0, oy = 0, dragging = false;
  const start = (e) => {
    dragging = true;
    sx = ("touches" in e ? e.touches[0].clientX : e.clientX);
    sy = ("touches" in e ? e.touches[0].clientY : e.clientY);
    const r = el.getBoundingClientRect();
    ox = r.left; oy = r.top;
    e.preventDefault();
  };
  const move = (e) => {
    if (!dragging) return;
    const cx = ("touches" in e ? e.touches[0].clientX : e.clientX);
    const cy = ("touches" in e ? e.touches[0].clientY : e.clientY);
    el.style.left = Math.max(8, ox + (cx - sx)) + "px";
    el.style.top  = Math.max(8, oy + (cy - sy)) + "px";
    el.style.right = "auto";
    el.style.bottom = "auto";
  };
  const end = () => (dragging = false);
  el.addEventListener("mousedown", start);
  el.addEventListener("touchstart", start, { passive: false });
  window.addEventListener("mousemove", move);
  window.addEventListener("touchmove", move, { passive: false });
  window.addEventListener("mouseup", end);
  window.addEventListener("touchend", end);
}

// ---- inject the pill -------------------------------------------------------

(function inject() {
  // avoid double-inject
  if (document.getElementById("listen-pill")) return;

  // create pill
  const pill = document.createElement("button");
  pill.id = "listen-pill";
  pill.type = "button";
  pill.textContent = "Listen ▶ (preview=Shift)";
  pill.title = "Stream this article as audio";

  // inline safety styles in case overlay.css didn't load
  pill.style.cssText = `
    position:fixed; right:20px; bottom:20px; z-index:2147483647;
    padding:12px 16px; border:0; border-radius:999px; cursor:pointer;
    background:#111; color:#fff; font:600 14px/1 system-ui,-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;
    box-shadow:0 10px 30px rgba(0,0,0,.18);
  `;

  pill.addEventListener("click", (e) => {
    e.preventDefault();
    // Shift-click = quick preview
    if (e.shiftKey) return preview10s();

    const id = rid();
    sendMetric("listen_click", { rid: id });

    const u = `${BASE}/read?rid=${encodeURIComponent(id)}&url=${encodeURIComponent(location.href)}`;
    // new tab avoids mixed-content blocking on HTTPS pages while backend is HTTP
    window.open(u, "_blank", "noopener");
  });

  document.documentElement.appendChild(pill);
  makeDraggable(pill);

  console.log("[listen] pill injected on", location.href, "→ backend:", BASE);
})();
