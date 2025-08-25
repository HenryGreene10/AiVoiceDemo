(() => {
    if (window.__aiListenLoaded) return; window.__aiListenLoaded = true;

    // inject button
    const btn = Object.assign(document.createElement('button'), { textContent: 'Listen (click = preview, Shift = full)' });
    Object.assign(btn.style, {position:'fixed',right:'16px',bottom:'16px',zIndex:999999,
      padding:'12px 16px',borderRadius:'12px',border:'0',fontWeight:'700',
      background:'#3b82f6',color:'#fff',boxShadow:'0 6px 20px rgba(0,0,0,.2)',cursor:'pointer'});
    document.body.appendChild(btn);
  
    // simple article text grabber (filters UI)
    function getText(){
      const root = document.querySelector('article, main, [role=main]') || document.body;
      const bad = new Set(['NAV','FOOTER','ASIDE','BUTTON','INPUT','TEXTAREA','SELECT','SCRIPT','STYLE']);
      const keep = root.querySelectorAll('h1,h2,h3,p,li');
      const parts=[];
      keep.forEach(el=>{
        if (bad.has(el.tagName)) return;
        if (el.closest('nav,footer,aside,header,[role="button"],.player,[aria-hidden="true"]')) return;
        const t=(el.innerText||'').trim();
        if (t.length>0) parts.push(t);
      });
      return parts.join('\n\n').slice(0,15000);
    }
  
    function ensureAudio(){
      let a = document.getElementById('listen-audio');
      if (!a){
        a = document.createElement('audio');
        a.id = 'listen-audio';
        a.controls = true; a.autoplay = true;
        a.style.position='fixed'; a.style.right='20px'; a.style.bottom='70px'; a.style.zIndex='2147483647';
        document.documentElement.appendChild(a);
      }
      return a;
    }

    async function previewClipInline(){
      const full = getText();
      if (!full || full.split(/\s+/).length < 30) { alert('No readable article text found'); return; }
      const clip = full.slice(0, 1100);
      const a = ensureAudio();
      const u = new URL('http://127.0.0.1:3000/tts');
      u.searchParams.set('model', 'eleven_flash_v2');
      u.searchParams.set('text', clip);
      a.src = u.toString();
      try{ await a.play(); }catch{}
    }

    let busy = false;
    btn.addEventListener('click', async (e) => {
      if (busy) return;
      busy = true; btn.style.opacity = '.7';
      try{
        if (!e.shiftKey){
          await previewClipInline();
        } else {
          const a = ensureAudio();
          a.src = 'http://127.0.0.1:3000/read?url=' + encodeURIComponent(location.href);
          await a.play();
        }
      } finally {
        btn.style.opacity = '1';
        setTimeout(()=>{ busy = false; }, 800);
      }
    });
  })();
  