(function(){
  if (window.__ttsLoaderLoaded) return; window.__ttsLoaderLoaded = true;

  function shouldInject(){
    if (window.top !== window) {
      try{
        const f = window.frameElement; if (!f) return false;
        const vw = window.top.innerWidth, vh = window.top.innerHeight; // may throw cross-origin
        const r = f.getBoundingClientRect();
        if (r.width >= vw*0.7 && r.height >= vh*0.7) return true;
        return false;
      }catch{return false;}
    }
    return true;
  }

  async function fetchToken(base){
    const origin = location.origin;
    const r = await fetch(`${base}/sdk/token`, { method:'POST', headers:{'content-type':'application/json'}, body: JSON.stringify({ origin, path:'/synthesize' })});
    if (!r.ok) throw new Error('token failed');
    return r.json();
  }

  async function synth(base){
    const { token } = await fetchToken(base);
    const r = await fetch(`${base}/synthesize`, { method:'POST', headers:{'content-type':'application/json','authorization':`Bearer ${token}`}, body: JSON.stringify({ url: location.href })});
    if (!r.ok) throw new Error('synth failed');
    return r.json();
  }

  async function init(){
    if (!shouldInject()) return;
    const base = (window.TTS_BASE || '').replace(/\/$/, '') || 'https://example.execute-api.region.amazonaws.com/Prod';
    try{
      const j = await synth(base);
      if (!window.TTSPlayer) return;
      window.TTSPlayer.init({ audioUrl: j.audioUrl, title: document.title });
    }catch(e){ console.warn('[tts-loader] failed', e); }
  }

  // SPA navigation watcher
  (function patchHistory(){
    const push = history.pushState;
    history.pushState = function(){ const r = push.apply(this, arguments); setTimeout(init, 50); return r; };
    window.addEventListener('popstate', ()=> setTimeout(init, 50));
  })();

  init();
})();


