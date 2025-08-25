const $ = (s)=>document.querySelector(s);
const key = "listen_base";
const def = "http://127.0.0.1:3000";

async function load(){
  const d = await chrome.storage.sync.get(key);
  $("#base").value = d[key] || def;
}
async function save(){
  const v = $("#base").value.replace(/\/+$/,"");
  await chrome.storage.sync.set({ [key]: v });
  $("#status").textContent = "Saved.";
  setTimeout(()=>$("#status").textContent="", 1200);
}
async function test(){
  const v = $("#base").value.replace(/\/+$/,"");
  try{
    const r = await fetch(`${v}/health`, { cache:"no-store" });
    $("#status").textContent = r.ok ? "✅ /health OK" : `❌ ${r.status}`;
  }catch(e){ $("#status").textContent = "❌ not reachable"; }
}
async function reset(){ $("#base").value = def; await save(); }

$("#save").onclick = save;
$("#test").onclick = test;
$("#reset").onclick = reset;
load();
