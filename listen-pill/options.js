// listen-pill/options.js
(() => {
  const apiBaseEl = document.getElementById("apiBase");
  const voiceIdEl = document.getElementById("voiceId");
  const saveBtn = document.getElementById("saveBtn");

  // load
  chrome.storage.sync.get(["apiBase", "voiceId"], (cfg) => {
    apiBaseEl.value = cfg.apiBase || "http://localhost:8000";
    voiceIdEl.value = cfg.voiceId || "";
  });

  // save
  saveBtn?.addEventListener("click", (e) => {
    e.preventDefault();
    chrome.storage.sync.set(
      { apiBase: apiBaseEl.value.trim(), voiceId: voiceIdEl.value.trim() },
      () => {
        saveBtn.textContent = "Saved ✓";
        setTimeout(() => (saveBtn.textContent = "Save"), 1200);
      }
    );
  });
})();
