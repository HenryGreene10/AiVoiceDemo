// pro-player.js: binds your <audio> to a nice Media Chrome popout
(function(){
    const $ = (s,r=document)=>r.querySelector(s);
  
    function autoDetectThemeVars() {
      const body = getComputedStyle(document.body);
      const font = body.fontFamily || 'system-ui, -apple-system, Segoe UI, Roboto, sans-serif';
      // try to use link color as accent
      const a = $('a'); const linkColor = a ? getComputedStyle(a).color : '#0b5';
      return { font, accent: linkColor };
    }
  
    function ensurePopup() {
      let wrap = $('#ai-listen-popup');
      if (wrap) return wrap;
  
      wrap = document.createElement('div');
      wrap.id = 'ai-listen-popup';
      const card = document.createElement('div');
      card.className = 'ai-card';
      card.innerHTML = `
        <button class="ai-close" aria-label="Close">Close</button>
        <div class="ai-head">
          <div class="ai-dot"></div>
          <div>
            <div class="ai-title" id="ai-title">AI Listen</div>
            <div class="ai-sub" id="ai-sub"></div>
          </div>
        </div>
        <div class="ai-player-wrap">
          <media-controller audio>
            <audio id="ai-listen-audio" slot="media"></audio>
            <media-control-bar>
              <media-play-button></media-play-button>
              <media-time-range></media-time-range>
              <media-time-display show-duration></media-time-display>
              <media-playback-rate-button rates="0.8,1,1.2,1.5,2"></media-playback-rate-button>
              <media-mute-button></media-mute-button>
              <media-volume-range></media-volume-range>
            </media-control-bar>
          </media-controller>
        </div>
      `;
      wrap.appendChild(card);
      document.body.appendChild(wrap);
  
      // Close
      card.querySelector('.ai-close').onclick = () => (wrap.style.display = 'none');
  
      // Apply auto theme tokens once
      const t = autoDetectThemeVars();
      card.style.setProperty('--ai-font', t.font);
      card.style.setProperty('--ai-accent', t.accent);
  
      return wrap;
    }
  
    // Public API for your widget to call
    window.AiPlayer = {
      open({ title, subtitle }) {
        const wrap = ensurePopup();
        wrap.style.display = 'flex';
        const tEl = document.getElementById('ai-title');
        const sEl = document.getElementById('ai-sub');
        if (tEl) tEl.textContent = title || 'AI Listen';
        if (sEl) sEl.textContent = subtitle || '';
        // Focus play for accessibility
        setTimeout(()=> {
          const playBtn = wrap.querySelector('media-play-button');
          playBtn?.shadowRoot?.querySelector('button')?.focus?.();
        }, 50);
      },
      audioEl() {
        return document.getElementById('ai-listen-audio');
      }
    };
  })();
  