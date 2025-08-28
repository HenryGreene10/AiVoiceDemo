// static/tts-widget.v1.js
if (!window.__ttsWidgetLoaded) window.__ttsWidgetLoaded = true;

window.AiListen = {
  init(opts = {}) {
    const apiBase  = (opts.apiBase || document.currentScript?.dataset.base || "").replace(/\/$/, "");
    const voiceId  = opts.voiceId || document.currentScript?.dataset.voice || "";
    const selector = opts.selector || "article";

    // singleton audio
    let audioEl = document.getElementById("ai-listen-audio");
    if (!audioEl) { audioEl = document.createElement("audio"); audioEl.id="ai-listen-audio"; document.body.appendChild(audioEl); }

    // singleton button
    let btn = document.getElementById("ai-listen-btn");
    if (!btn) { btn = document.createElement("button"); btn.id="ai-listen-btn"; btn.textContent="Listen"; btn.style.cssText="position:fixed;right:16px;bottom:16px;z-index:999999;padding:10px 14px;border-radius:9999px;"; document.body.appendChild(btn); }

    function pageText() {
      const root = document.querySelector(selector) || document.body;
      const clone = root.cloneNode(true);
      clone.querySelectorAll('button, audio, video, script, style, noscript, svg, #ai-listen-btn, #ai-listen-audio').forEach(n=>n.remove());
      let t = (clone.innerText || "").replace(/\s+/g," ").trim();
      t = t.replace(/[^\x09\x0A\x0D\x20-\x7E\u00A0-\u024F]/g," ");
      return t.slice(0, 600);
    }

    async function getAudioUrl(text){
      const r = await fetch(`${apiBase}/api/tts?voice=${encodeURIComponent(voiceId)}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text })
      });
      const body = await r.text();
      if (!r.ok) throw new Error(`API ${r.status}: ${body}`);
      const j = JSON.parse(body);
      if (!j?.audioUrl) throw new Error("No audioUrl returned");
      return apiBase + j.audioUrl;
    }

    let busy = false;
    btn.onclick = async () => {
      if (busy) return;
      busy = true; btn.disabled = true; btn.textContent = "Loading…";
      try {
        const src = await getAudioUrl(pageText());
        audioEl.autoplay = true;
        audioEl.src = src;
        await audioEl.play();
        btn.textContent = "Pause";
      } catch (e) {
        console.error("[AiListen] error", e);
        btn.textContent = "Error";
      } finally {
        busy = false; btn.disabled = false;
      }
    };

    audioEl.addEventListener("play",  () => btn.textContent = "Pause");
    audioEl.addEventListener("pause", () => btn.textContent = "Play");
    audioEl.addEventListener("ended", () => btn.textContent = "Replay");
  }
};
  