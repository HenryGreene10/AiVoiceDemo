// listen-pill/tts-bridge.js
(() => {
    const log = (...a) => console.log("[listen-bridge]", ...a);
  
    // Get config from extension options (fallback to localhost)
    let API_BASE = "http://localhost:8000";
    let VOICE_ID = "";
    if (chrome?.storage?.sync) {
      chrome.storage.sync.get(["apiBase", "voiceId"], (cfg) => {
        API_BASE = cfg.apiBase || API_BASE;
        VOICE_ID = cfg.voiceId || VOICE_ID;
        log("cfg", { API_BASE, VOICE_ID });
      });
    }
  
    // Find your UI (generic selectors to avoid changing your HTML/CSS)
    function getUI(root = document) {
      const container =
        root.querySelector("[data-listen-root]") ||
        root.querySelector(".ai-listen") ||
        root.querySelector(".listen-pill") ||
        root.querySelector(".listen-card") ||
        root.body;
  
      if (!container) return null;
  
      return {
        root: container,
        playBtn:
          container.querySelector("[data-action='play']") ||
          container.querySelector(".listen-play") ||
          container.querySelector("button"),
        speedSel:
          container.querySelector("[data-speed]") ||
          container.querySelector(".listen-speed"),
        urlInput:
          container.querySelector("[data-url]") ||
          container.querySelector(".listen-url"),
        status:
          container.querySelector("[data-status]") ||
          container.querySelector(".listen-status"),
        cacheBadge:
          container.querySelector("[data-cache]") ||
          container.querySelector(".listen-cache"),
        audio:
          container.querySelector("audio") ||
          (() => {
            const a = document.createElement("audio");
            a.preload = "none";
            a.style.display = "none";
            container.appendChild(a);
            return a;
          })(),
      };
    }
  
    function setStatus(ui, msg) {
      if (ui.status) ui.status.textContent = msg || "";
    }
    function setBusy(ui, b) {
      if (ui.playBtn) {
        ui.playBtn.disabled = b;
        ui.playBtn.textContent = b ? "Generating…" : "Play";
      }
    }
  
    function selectedText() {
      const s = window.getSelection();
      return s && s.toString().trim() ? s.toString().trim() : "";
    }
    function extractArticle() {
      // non-destructive: read only
      const host =
        document.querySelector("article") ||
        document.querySelector("main") ||
        document.body;
      const clone = host.cloneNode(true);
      clone.querySelectorAll("nav,aside,script,style,noscript").forEach((n) =>
        n.remove()
      );
      return (clone.innerText || "").replace(/\s+\n/g, "\n").trim().slice(0, 8000);
    }
  
    async function generateAndPlay(ui, text) {
      if (!text) throw new Error("No text to read.");
      if (!VOICE_ID) throw new Error("Set a Voice ID in extension options.");
  
      setBusy(ui, true);
      setStatus(ui, "Generating…");
      if (ui.cacheBadge) ui.cacheBadge.hidden = true;
  
      const res = await fetch(`${API_BASE}/tts`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text, voiceId: VOICE_ID }),
      });
      if (!res.ok) throw new Error(`TTS failed (${res.status})`);
  
      const cached = (res.headers.get("x-cache-hit") || "").toLowerCase() === "true";
      if (ui.cacheBadge) {
        ui.cacheBadge.textContent = "⚡ cached";
        ui.cacheBadge.hidden = !cached;
      }
  
      const blob = await res.blob(); // audio/mpeg
      const url = URL.createObjectURL(blob);
      if (ui.audio.dataset.url) URL.revokeObjectURL(ui.audio.dataset.url);
      ui.audio.dataset.url = url;
      ui.audio.src = url;
  
      const rate = parseFloat(ui.speedSel?.value || "1") || 1;
      ui.audio.playbackRate = rate;
  
      await ui.audio.play();
      setStatus(ui, cached ? "Ready (cached)" : "Ready");
    }
  
    function attach(ui) {
      if (!ui?.playBtn) return;
      if (ui.playBtn.dataset.wired === "1") return; // avoid double-binding
      ui.playBtn.dataset.wired = "1";
  
      ui.playBtn.addEventListener("click", async () => {
        try {
          // Respect your existing UX: if audio loaded, toggle play/pause
          if (ui.audio?.src) {
            if (ui.audio.paused) {
              ui.audio.play();
              return;
            } else {
              ui.audio.pause();
              return;
            }
          }
  
          // Otherwise, generate
          let text = selectedText();
          if (!text) text = extractArticle();
  
          // If user typed a URL in your input, we can pass the URL to backend later;
          // for now, stick to text-only MVP.
          await generateAndPlay(ui, text);
        } catch (e) {
          console.error(e);
          setStatus(ui, e.message || "Error");
        } finally {
          setBusy(ui, false);
        }
      });
  
      // live speed updates
      ui.speedSel?.addEventListener("change", () => {
        const rate = parseFloat(ui.speedSel.value || "1") || 1;
        ui.audio.playbackRate = rate;
      });
  
      log("wired");
    }
  
    // Wait for your UI to exist (in case your content.js inserts it later)
    function whenReady() {
      const ui = getUI();
      if (ui?.playBtn) {
        attach(ui);
      } else {
        const mo = new MutationObserver(() => {
          const ui2 = getUI();
          if (ui2?.playBtn) {
            attach(ui2);
            mo.disconnect();
          }
        });
        mo.observe(document.documentElement, { childList: true, subtree: true });
      }
    }
  
    whenReady();
  })();
  