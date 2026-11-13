'use strict';
const report=async(status,text)=>{
  await chrome.storage.local.set({updateStatus:{status,text}});
  await chrome.action.setBadgeText({text:status==='checking'?'…':status==='error'?'!':status==='done'?'OK':''});
  await chrome.action.setBadgeBackgroundColor({color:status==='error'?'#b92929':'#28674d'});
};
chrome.runtime.onInstalled.addListener(async()=>{
  const version=chrome.runtime.getManifest().version;
  const state=await chrome.storage.local.get('appliedVersion');
  if(state.appliedVersion===version){
    await chrome.storage.local.remove('appliedVersion');
    await report('done','已更新至 '+version+'，请刷新旺销王扫码页。');return;
  }
  await report('checking','正在检查并下载更新，请稍候…');
  let port,received=false;
  try{
    port=chrome.runtime.connectNative('com.wxw.qc.updater');
    port.onMessage.addListener(async result=>{
      received=true;port.disconnect();
      if(!result.ok||!/^\d+\.\d+\.\d+(\.\d+)?$/.test(result.version||'')){
        await report('error','更新未完成，继续使用当前版本。请检查网络或运行安装程序。');return;
      }
      if(result.version!==version){
        await chrome.storage.local.set({appliedVersion:result.version});
        chrome.runtime.reload();
      }else await report('done',(result.skipped?'回退版本已加载 ':'当前已是最新版 ')+version+'，请刷新旺销王扫码页。');
    });
    port.onDisconnect.addListener(()=>{
      const error=chrome.runtime.lastError;
      if(!received)void report('error','未能连接更新程序，请先运行安装程序；也可使用桌面在线更新。');
    });
    port.postMessage({action:'update'});
  }catch{await report('error','无法启动更新程序，当前版本可继续使用。');}
});
