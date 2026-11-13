'use strict';
document.getElementById('version').textContent='当前运行版本：'+chrome.runtime.getManifest().version;
document.getElementById('apply').addEventListener('click',()=>{
  try{chrome.runtime.reload();}catch{document.getElementById('error').textContent='请在 Edge 扩展管理页点击重新加载。';}
});

const show=()=>chrome.storage.local.get('updateStatus').then(s=>{document.getElementById('status').textContent=s.updateStatus?.text||'点击重新加载可检查更新。';});show();chrome.storage.onChanged.addListener(show);
