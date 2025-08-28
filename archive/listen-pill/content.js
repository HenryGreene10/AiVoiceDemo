// content.js — launcher + modal bottom-sheet player (any site)
// BASE: use https tunnel in testing (see notes below)
async function getBase(){
  try{
    const d = await chrome?.storage?.sync?.get?.('listen_base');
    const v = d?.listen_base || localStorage.getItem('listen_base') || 'http://127.0.0.1:3000';
    return v.replace(/\/+$/, '');
  }catch{ return 'http://127.0.0.1:3000'; }
}
const fmt = s => { s=Math.max(0,s|0); const m=(s/60|0), ss=String(s%60).padStart(2,'0'); return `${m}:${ss}`; };

function getOrCreateAudio(){
  let a = document.getElementById('listen-audio');
  if(!a){
    a = document.createElement('audio');
    a.id = 'listen-audio';
    a.preload = 'none';
    a.style.display = 'none';
    document.documentElement.appendChild(a);
  }
  return a;
}

(function mount(){
  if(document.getElementById('listen-launcher')) return;

  // robust container (shell-safe)
  const container =
    document.querySelector('article') ||
    document.querySelector('main [role=main]') ||
    document.querySelector('main') ||
    document.body;
  const fixedMode = container === document.body;

  // launcher
  const launcher = document.createElement('div');
  launcher.id = 'listen-launcher';
  launcher.title = 'Listen';
  launcher.textContent = '🎧';
  document.documentElement.appendChild(launcher);

  // overlay + sheet
  const overlay = document.createElement('div');
  overlay.id = 'listen-overlay';
  if (fixedMode) overlay.classList.add('fixed-mode');
  overlay.setAttribute('aria-hidden','true');
  overlay.innerHTML = `
    <div class="listen-sheet" role="dialog" aria-modal="true" aria-label="Audiobook player" tabindex="-1">
      <button class="listen-close" aria-label="Close">✕</button>
      <img class="listen-cover" alt="" />
      <div class="listen-meta">
        <h1 class="listen-title"></h1>
        <h2 class="listen-subtitle"></h2>
        <div class="listen-author"></div>
      </div>
      <div class="listen-controls">
        <button class="listen-btn listen-rew" aria-label="Back 10 seconds">⟲10</button>
        <button class="listen-play" aria-label="Play/Pause">▶</button>
        <button class="listen-btn listen-fwd" aria-label="Forward 30 seconds">⟳30</button>
      </div>
      <div class="listen-progress">
        <span class="listen-cur">0:00</span>
        <input class="listen-bar" type="range" min="0" max="100" value="0" />
        <span class="listen-dur">0:00</span>
      </div>
    </div>
  `;
  document.documentElement.appendChild(overlay);

  const sheet = overlay.querySelector('.listen-sheet');
  const close = overlay.querySelector('.listen-close');
  const cover = overlay.querySelector('.listen-cover');
  const ttl   = overlay.querySelector('.listen-title');
  const sub   = overlay.querySelector('.listen-subtitle');
  const auth  = overlay.querySelector('.listen-author');
  const play  = overlay.querySelector('.listen-play');
  const rew   = overlay.querySelector('.listen-rew');
  const fwd   = overlay.querySelector('.listen-fwd');
  const cur   = overlay.querySelector('.listen-cur');
  const dur   = overlay.querySelector('.listen-dur');
  const bar   = overlay.querySelector('.listen-bar');
  const audio = getOrCreateAudio();

  function open(){ overlay.classList.add('open'); overlay.setAttribute('aria-hidden','false'); sheet.focus?.(); }
  function closeOverlay(){ overlay.classList.remove('open'); overlay.setAttribute('aria-hidden','true'); launcher.focus?.(); }
  overlay.addEventListener('click', e => { if(e.target === overlay) closeOverlay(); });
  close.addEventListener('click', closeOverlay);
  document.addEventListener('keydown', e => { if(overlay.classList.contains('open') && e.key === 'Escape') closeOverlay(); });

  async function loadMeta(){
    try{
      const BASE = await getBase();
      const r = await fetch(`${BASE}/meta?url=${encodeURIComponent(location.href)}`);
      if(r.ok){
        const j = await r.json();
        ttl.textContent  = j.title   || (document.querySelector('h1')?.textContent?.trim() || document.title);
        sub.textContent  = j.subtitle|| '';
        auth.textContent = j.author  ? `By ${j.author}` : '';
        if(j.image){ cover.src = j.image; cover.style.display='block'; } else { cover.remove(); }
      }else{
        ttl.textContent = document.querySelector('h1')?.textContent?.trim() || document.title;
      }
    }catch{}
  }

  function setPP(){ play.textContent = audio.paused ? '▶' : '⏸'; }
  audio.addEventListener('loadedmetadata', ()=>{ dur.textContent = fmt(audio.duration); cur.textContent = fmt(0); bar.value = 0; });
  audio.addEventListener('timeupdate', ()=>{ if(audio.duration){ cur.textContent = fmt(audio.currentTime); dur.textContent = fmt(audio.duration); bar.value = (audio.currentTime/audio.duration)*100; }});
  audio.addEventListener('play', setPP);
  audio.addEventListener('pause', setPP);
  audio.addEventListener('ended', setPP);

  bar.addEventListener('input', ()=>{ if(audio.duration) audio.currentTime = (bar.value/100)*audio.duration; });
  rew.addEventListener('click', ()=>{ audio.currentTime = Math.max(0, audio.currentTime - 10); });
  fwd.addEventListener('click', ()=>{ if(audio.duration) audio.currentTime = Math.min(audio.duration, audio.currentTime + 30); });

  async function startPlayback(full=false){
    const BASE = await getBase();
    if(!full){
      // preview ~3–5s (≈320 chars)
      try{
        const r = await fetch(`${BASE}/extract?url=${encodeURIComponent(location.href)}`);
        if(!r.ok) throw new Error('extract failed');
        const j = await r.json();
        const clip = (j?.text || '').slice(0, 320);
        if(!clip) throw new Error('no text');
        audio.src = `${BASE}/tts?model=eleven_flash_v2&text=${encodeURIComponent(clip)}`;
      }catch(err){ console.warn('[listen] preview error', err); return; }
    }else{
      audio.src = `${BASE}/read?url=${encodeURIComponent(location.href)}`;
    }
    try{ await audio.play(); }catch{}
  }

  launcher.addEventListener('click', async ()=>{ await loadMeta(); open(); });

  play.addEventListener('click', async (e)=>{
    if(audio.src && !audio.paused){ audio.pause(); return; }
    await startPlayback(e?.shiftKey === true);
  });
  play.addEventListener('keydown', (e)=>{ if(e.key===' ' || e.key==='Enter'){ e.preventDefault(); startPlayback(e.shiftKey===true); }});

  getBase().then(b => console.log('[listen] modal ready on', location.hostname, '→', b));
})();


