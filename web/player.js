// web/player.js
const $ = (id) => document.getElementById(id);
const API = "http://localhost:8000";

const textEl = $("tts-text");
const voiceEl = $("voice-id");
const btn = $("generate-btn");
const audio = $("audio");
const status = $("status");
const cacheBadge = $("cache-badge");

function setStatus(msg) { status.textContent = msg || ""; }
function setBusy(b) { btn.disabled = b; btn.textContent = b ? "Generating…" : "Generate"; }

btn.addEventListener("click", generate);
window.addEventListener("keydown", (e) => {
  if (e.code === "Space" && audio.src) { e.preventDefault(); audio.paused ? audio.play() : audio.pause(); }
  if (e.code === "Escape" && audio.src) { audio.pause(); audio.currentTime = 0; }
});

async function generate() {
  const text = (textEl.value || "").trim();
  const voiceId = (voiceEl.value || "").trim();
  if (!text) return setStatus("Enter some text.");
  if (!voiceId) return setStatus("Enter a voice ID.");

  try {
    setBusy(true);
    setStatus("Generating…");
    cacheBadge.hidden = true;

    const res = await fetch(`${API}/tts`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text, voiceId }),
    });

    if (!res.ok) throw new Error(`TTS failed (${res.status})`);

    const cached = (res.headers.get("x-cache-hit") || "").toLowerCase() === "true";
    cacheBadge.hidden = !cached;

    const blob = await res.blob(); // audio/mpeg
    const url = URL.createObjectURL(blob);
    // revoke previous object URL to avoid leaks
    if (audio.dataset.url) URL.revokeObjectURL(audio.dataset.url);
    audio.dataset.url = url;
    audio.src = url;
    await audio.play();
    setStatus(cached ? "Ready (cached)" : "Ready");
  } catch (err) {
    console.error(err);
    setStatus(err.message || "Error generating audio");
  } finally {
    setBusy(false);
  }
}
