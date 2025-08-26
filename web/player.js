(function(){
  if (window.TTSPlayer) return;

  function fmt(s){ s = Math.max(0, s|0); const m=(s/60|0), ss=String(s%60).padStart(2,'0'); return `${m}:${ss}`; }

  function createShadow(){
    let host = document.getElementById('tts-player-host');
    if (!host){ host = document.createElement('div'); host.id = 'tts-player-host'; document.documentElement.appendChild(host); }
    const root = host.shadowRoot || host.attachShadow({mode:'open'});
    if (!root.querySelector('#root')){
      const wrap = document.createElement('div'); wrap.id = 'root';
      const style = document.createElement('style'); style.textContent = `
        #root{position:fixed;left:18px;bottom:18px;z-index:2147483647;pointer-events:auto}
        .card{display:flex;align-items:center;gap:12px;background:#111;color:#fff;border:1px solid #222;border-radius:12px;padding:10px 14px;box-shadow:0 10px 30px rgba(0,0,0,.25)}
        .pp{width:36px;height:36px;border-radius:999px;background:#ffd400;color:#000;border:0;font-weight:800;cursor:pointer}
        .title{font:600 14px/1.2 system-ui,-apple-system,Segoe UI,Roboto,Arial;max-width:280px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
        .time{width:80px;text-align:right;font:600 12px/1 system-ui;opacity:.85}
        .bar{appearance:none;-webkit-appearance:none;width:220px;height:6px;border-radius:999px;background:#2a2a2a;outline:none}
        .bar::-webkit-slider-thumb{-webkit-appearance:none;width:14px;height:14px;border-radius:999px;background:#ffd400;border:0}
      `;
      wrap.innerHTML = `<div class="card"><button class="pp" aria-label="Play/Pause">▶</button><div class="title"></div><input class="bar" type="range" min="0" max="100" value="0"/><div class="time"><span class="cur">0:00</span> / <span class="dur">0:00</span></div></div>`;
      root.appendChild(style); root.appendChild(wrap);
    }
    return root;
  }

  function audioEl(){
    let a = document.getElementById('listen-audio');
    if (!a){ a = document.createElement('audio'); a.id='listen-audio'; a.preload='none'; a.style.display='none'; document.documentElement.appendChild(a); }
    return a;
  }

  const api = {
    init(opts){
      this.opts = opts || {};
      this.root = createShadow();
      this.titleEl = this.root.querySelector('.title');
      this.pp = this.root.querySelector('.pp');
      this.bar = this.root.querySelector('.bar');
      this.cur = this.root.querySelector('.cur');
      this.dur = this.root.querySelector('.dur');
      this.audio = audioEl();
      this.titleEl.textContent = document.title || opts.title || '';
      const self = this;
      function setPP(){ self.pp.textContent = self.audio.paused ? '▶' : '⏸'; }
      this.audio.addEventListener('loadedmetadata', ()=>{ self.dur.textContent = fmt(self.audio.duration); self.cur.textContent = fmt(0); self.bar.value = 0; });
      this.audio.addEventListener('timeupdate', ()=>{ if(self.audio.duration){ self.cur.textContent = fmt(self.audio.currentTime); self.dur.textContent = fmt(self.audio.duration); self.bar.value = (self.audio.currentTime/self.audio.duration)*100; }});
      this.audio.addEventListener('play', setPP); this.audio.addEventListener('pause', setPP); this.audio.addEventListener('ended', setPP);
      this.bar.addEventListener('input', ()=>{ if(self.audio.duration) self.audio.currentTime = (self.bar.value/100)*self.audio.duration; });
      this.pp.addEventListener('click', async ()=>{
        if (self.audio.src && !self.audio.paused) { self.audio.pause(); return; }
        if (!self.audio.src && self.opts.audioUrl){ self.audio.src = self.opts.audioUrl; }
        try{ await self.audio.play(); }catch{}
      });
      return this;
    },
    setSource(audioUrl, title){
      this.opts = this.opts || {}; this.opts.audioUrl = audioUrl; if (title) this.titleEl.textContent = title; this.audio.src = audioUrl; this.audio.currentTime = 0;
    }
  };

  window.TTSPlayer = api;
})();


