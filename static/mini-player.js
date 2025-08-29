(function(){
    const $ = (s,r=document)=>r.querySelector(s);
  
    function fmt(t){
      t = Math.max(0, Math.floor(t||0));
      const m = Math.floor(t/60), s = t%60;
      return `${m}:${s.toString().padStart(2,'0')}`;
    }
  
    function ensureMini(){
      let bar = $('#ai-mini');
      if (bar) return bar;
  
      bar = document.createElement('div');
      bar.id = 'ai-mini';
      bar.innerHTML = `
        <button class="mp-btn" id="mp-back" title="Back 10s">«</button>
        <button class="mp-btn" id="mp-play" title="Play/Pause">►</button>
        <button class="mp-btn" id="mp-fwd"  title="Fwd 10s">»</button>
  
        <div class="mp-col">
          <div class="mp-title" id="mp-title">AI Listen</div>
          <div class="mp-sub" id="mp-sub"></div>
        </div>
  
        <div class="mp-progress">
          <div class="mp-time" id="mp-elapsed">0:00</div>
          <input type="range" min="0" max="100" value="0" class="mp-range" id="mp-seek">
          <div class="mp-time" id="mp-remaining">0:00</div>
        </div>
  
        <select class="mp-rate" id="mp-rate" title="Playback speed">
          <option>0.8x</option><option selected>1.0x</option>
          <option>1.2x</option><option>1.5x</option><option>2.0x</option>
        </select>
  
        <button class="mp-btn" id="mp-close" title="Close">✕</button>
      `;
      document.body.appendChild(bar);
      return bar;
    }
  
    function bindMiniControls(audio, meta){
      const bar = ensureMini();
      const q = id => bar.querySelector(id);
  
      // meta
      q('#mp-title').textContent = meta?.title || 'AI Listen';
      q('#mp-sub').textContent   = meta?.subtitle || '';
  
      const play = q('#mp-play'), back = q('#mp-back'), fwd = q('#mp-fwd');
      const rate = q('#mp-rate'), seek = q('#mp-seek');
      const el   = q('#mp-elapsed'), rem = q('#mp-remaining');
      const close= q('#mp-close');
  
      const sync = ()=>{
        try{
          const d = audio.duration || 0, c = audio.currentTime || 0;
          el.textContent = fmt(c);
          rem.textContent = d ? `-${fmt(Math.max(0, d - c))}` : '0:00';
          if (d) seek.value = Math.round((c/d)*100);
        }catch{}
      };
  
      // controls
      play.onclick = ()=> audio.paused ? audio.play().catch(()=>{}) : audio.pause();
      back.onclick = ()=> { try{ audio.currentTime = Math.max(0, audio.currentTime - 10); }catch{} };
      fwd.onclick  = ()=> { try{ audio.currentTime = Math.min((audio.duration||1e9), audio.currentTime + 10); }catch{} };
      rate.onchange= ()=> { audio.playbackRate = parseFloat(rate.value)||1; };
  
      seek.oninput = ()=>{
        try{
          const d = audio.duration||0;
          audio.currentTime = d * (parseInt(seek.value||'0',10)/100);
        }catch{}
      };
  
      audio.addEventListener('timeupdate', sync);
      audio.addEventListener('durationchange', sync);
      audio.addEventListener('play', ()=>{ play.textContent='❚❚'; bar.classList.add('show'); bar.classList.remove('hidden'); });
      audio.addEventListener('pause',()=>{ play.textContent='►'; });
      audio.addEventListener('ended',()=>{ play.textContent='►'; });
  
      close.onclick = ()=> { bar.classList.remove('show'); bar.classList.add('hidden'); };
  
      // show immediately for feedback
      bar.classList.add('show');
    }
  
    // public API
    window.AiMini = {
      open(meta){
        // reuse (or create) the shared audio element your widget already manages
        let audio = document.getElementById('ai-listen-audio');
        if (!audio){
          audio = document.createElement('audio');
          audio.id = 'ai-listen-audio';
          document.body.appendChild(audio);
        }
        bindMiniControls(audio, meta||{});
      },
      audio(){ return document.getElementById('ai-listen-audio'); }
    };
  })();
  