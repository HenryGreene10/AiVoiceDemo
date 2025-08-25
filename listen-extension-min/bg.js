// change port if your server isn't on 3000
const BASE = "http://127.0.0.1:3000";

chrome.action.onClicked.addListener((tab) => {
  if (!tab || !tab.url) return;
  const u = BASE + "/read?url=" + encodeURIComponent(tab.url);
  chrome.tabs.create({ url: u });
});
