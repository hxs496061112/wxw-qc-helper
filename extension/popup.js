'use strict';
document.getElementById('version').textContent='当前运行版本：'+chrome.runtime.getManifest().version;
document.getElementById('apply').addEventListener('click',()=>{
  try{chrome.runtime.reload();}catch{document.getElementById('error').textContent='请在 Edge 扩展管理页点击重新加载。';}
});
