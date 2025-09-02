(function(){
  if (document.querySelector('script[src*="tts-widget"]')) {
    console.log('[AI Listen] Widget already present.'); return;
  }
  const s = document.createElement('script');
  s.src = (window.AIL_WIDGET_SRC || '/static/tts-widget.v1.js') + `?v=${Date.now()}`;
  s.dataset.base = window.AIL_API_BASE || 'https://YOUR-API-HOST';
  s.dataset.voice = window.AIL_VOICE || '21m00Tcm4TlvDq8ikWAM';
  s.dataset.selector = window.AIL_SELECTOR || 'article, main, .post';
  s.dataset.position = 'bottom-right';
  s.dataset.variant = 'inline';
  s.dataset.docId = (location.host + location.pathname).slice(0,128);
  document.head.appendChild(s);
  console.log('[AI Listen] Injected widget.');
})();
