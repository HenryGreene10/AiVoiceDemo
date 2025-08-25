(() => {
    if (window.__aiListenLoaded) return; window.__aiListenLoaded = true;

    // inject button
    const btn = Object.assign(document.createElement('button'), { textContent: '▶ Listen' });
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
  
    let audio;
    async function play(){
      const text = getText();
      if (!text || text.split(/\s+/).length < 30) { alert('No readable article text found'); return; }
      btn.disabled = true; btn.textContent = '… loading';
      try{
        const u = new URL('http://127.0.0.1:3000/tts');
        u.searchParams.set('text', text);
        audio = new Audio(u.toString());
        audio.onended = () => { btn.textContent='▶ Listen'; };
        await audio.play();
        btn.textContent = '⏸ Pause';
      }catch(e){ alert(e.message); btn.textContent='▶ Listen'; }
      finally{ btn.disabled = false; }
    }
  
    btn.onclick = async () => {
      if (audio && !audio.paused){ audio.pause(); btn.textContent='▶ Listen'; }
      else await play();
    };
  })();
  