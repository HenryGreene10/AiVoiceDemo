(function(){
    // Params: base, voice, model, url(optional)
    const qp = new URLSearchParams(location.search);
    const apiBase = (qp.get('base') || 'http://127.0.0.1:3000').replace(/\/+$/,'');
    const model   = qp.get('model') || 'eleven_turbo_v2';
    const voiceId = qp.get('voice') || '';
    const pageUrl = qp.get('url')   || ''; // for server-side /read
    const audio  = document.getElementById('audio');
    const status = document.getElementById('status');
  
    function getPreviewText(limit=1200){
      // in iframe we don’t have host DOM; accept optional title/preview via postMessage
      return window.__previewText || 'This is a preview.';
    }
  
    async function ensureAndPlay(src){
      status.textContent = 'Loading…';
      audio.src = src;
      try { await audio.play(); status.textContent = 'Playing'; }
      catch { status.textContent = 'Press play ▶'; }
    }
  
    async function previewSrc(){
      const text = getPreviewText();
      const u = new URL(`${apiBase}/tts`);
      u.searchParams.set('model', model);
      u.searchParams.set('text', text);
      return u.toString();
    }
  
    async function fullSrc(){
      if (pageUrl) return `${apiBase}/read?url=${encodeURIComponent(pageUrl)}&model=${encodeURIComponent(model)}`;
      // fallback to preview if no url passed
      return previewSrc();
    }
  
    // parent → child control
    window.addEventListener('message', async (e) => {
      const { type, payload } = e.data || {};
      try {
        if (type === 'tts:setPreviewText') { window.__previewText = String(payload || ''); }
        if (type === 'tts:playPreview')     { ensureAndPlay(await previewSrc()); }
        if (type === 'tts:playFull')        { ensureAndPlay(await fullSrc()); }
      } catch (err) { console.error(err); status.textContent = 'Error loading audio'; }
    }, false);
  
    // autoplay cue
    status.textContent = 'Ready';
  })();
  