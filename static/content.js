// base URL of your backend (change port if needed)
const BASE = "http://127.0.0.1:3000";

(function inject() {
  if (document.getElementById("listen-pill")) return;

  const pill = document.createElement("button");
  pill.id = "listen-pill";
  pill.textContent = "Listen ▶";
  pill.title = "Stream this article as audio";
  pill.addEventListener("click", (e) => {
    e.preventDefault();
    const u = BASE + "/read?url=" + encodeURIComponent(location.href);
    window.open(u, "_blank", "noopener");
    // optional: tiny telemetry
    try {
      navigator.sendBeacon?.(
        BASE + "/metric",
        new Blob([JSON.stringify({ domain: location.hostname, action: "listen_click", ts: Date.now() })], { type: "application/json" })
      );
    } catch {}
  });

  document.documentElement.appendChild(pill);
})();
