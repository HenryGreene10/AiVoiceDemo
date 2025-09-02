(function(){
  const form = document.getElementById('demo-form');
  const urlInput = document.getElementById('url');
  const btn = document.getElementById('preview');
  const shell = document.getElementById('playerShell');
  const frame = document.getElementById('previewFrame');

  const isValid = (u)=>{
    try{
      const p = new URL(u);
      return p.protocol === 'http:' || p.protocol === 'https:';
    }catch{ return false; }
  };

  const enableBtn = (ok)=>{
    btn.disabled = !ok;
    btn.classList.toggle('enabled', !!ok);
    shell.classList.toggle('disabled', !ok);
    shell.setAttribute('aria-disabled', String(!ok));
  };

  urlInput.addEventListener('input', ()=>{
    enableBtn(isValid(urlInput.value.trim()));
  });

  form.addEventListener('submit', (e)=>{
    e.preventDefault();
    const u = urlInput.value.trim();
    if (!isValid(u)) return;
    const target = `/wrap?url=${encodeURIComponent(u)}`;
    // Load wrapped page into iframe
    frame.src = target;
  });

  // initial
  enableBtn(false);
})();
