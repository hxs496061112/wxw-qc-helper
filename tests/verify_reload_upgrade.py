"""Explicit network test: actual public v0.6.2 -> latest via browser Reload.
Uses a temporary Windows install/profile and dedicated native-host registry keys.
No business page is opened. The initial extension's host name alone is redirected
to the test registration, which is removed on exit. Downloaded code is verified
by the production updater's pinned signing key before installation.
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
import urllib.request
import uuid
import winreg
import zipfile
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[1]
PS=Path(os.environ['SystemRoot'])/'System32/WindowsPowerShell/v1.0/powershell.exe'
ID='hldbbmhhmgjcfmlbkglekcigjkbefobe'

def main():
    expected=json.loads((ROOT/'extension/manifest.json').read_text(encoding='utf-8'))['version']
    name='com.wxw.qc.upgrade_test_'+uuid.uuid4().hex
    keys=[]
    with tempfile.TemporaryDirectory(prefix='wxw-real-upgrade-') as folder:
        temp=Path(folder);archive=temp/'old.zip'
        url='https://github.com/hxs496061112/wxw-qc-helper/releases/download/v0.6.2/wxw-qc-installer.zip'
        with urllib.request.urlopen(url,timeout=45) as response:archive.write_bytes(response.read(8388609))
        with zipfile.ZipFile(archive) as z:z.extractall(temp/'unpacked')
        package=next((temp/'unpacked').iterdir())
        env=os.environ.copy();env['LOCALAPPDATA']=str(temp/'local')
        result=subprocess.run([str(PS),'-NoProfile','-ExecutionPolicy','Bypass','-File',str(ROOT/'manager/WxwQcUpdater.ps1'),'-Mode','Install','-NoUI','-PayloadDirectory',str(package/'payload')],env=env,capture_output=True,timeout=60)
        assert result.returncode==0,(result.stdout+result.stderr).decode('gb18030',errors='replace')
        install=temp/'local/WxwQcHelper';ext=install/'extension'
        assert json.loads((ext/'manifest.json').read_text(encoding='utf-8'))['version']=='0.6.2'
        for file in ('NativeHost.cmd','NativeHost.ps1'):shutil.copy2(install/'manager'/file,install/file)
        background=ext/'background.js'
        background.write_text(background.read_text(encoding='utf-8').replace('com.wxw.qc.updater',name),encoding='utf-8')
        host=temp/'host.json'
        host.write_text(json.dumps({'name':name,'description':'Isolated real upgrade verification','path':str(install/'NativeHost.cmd'),'type':'stdio','allowed_origins':[f'chrome-extension://{ID}/']}),encoding='utf-8')
        try:
            with sync_playwright() as p:
                context=p.chromium.launch_persistent_context(str(temp/'browser'),channel='chromium',headless=True,env=env,ignore_default_args=['--disable-extensions'],args=[f'--load-extension={ext}'])
                try:
                    page=context.new_page();page.set_default_timeout(5000)
                    page.goto('chrome://extensions/');page.locator('#devMode').click()
                    popup=context.new_page();popup.goto(f'chrome-extension://{ID}/popup.html')
                    popup.locator('#status').filter(has_text='未能连接').wait_for(timeout=15000)
                    assert '0.6.2' in popup.locator('#version').inner_text()
                    # Registration happens after initial load, so only the real Reload triggers the download.
                    for vendor in ('Google\\Chrome','Chromium'):
                        path=f'Software\\{vendor}\\NativeMessagingHosts\\{name}'
                        with winreg.CreateKey(winreg.HKEY_CURRENT_USER,path) as key:winreg.SetValueEx(key,'',0,winreg.REG_SZ,str(host))
                        keys.append(path)
                    print('Installed public v0.6.2; clicking the browser Reload button.',flush=True)
                    page.locator('extensions-item').locator('#dev-reload-button').click()
                    deadline=time.monotonic()+145
                    while time.monotonic()<deadline:
                        try:
                            if popup.is_closed():popup=context.new_page()
                            popup.goto(f'chrome-extension://{ID}/popup.html',timeout=3000)
                            version=popup.locator('#version').inner_text(timeout=1000)
                            status=popup.locator('#status').inner_text(timeout=1000)
                            if expected in version and '已更新至' in status:break
                            if '更新未完成' in status:raise AssertionError(status)
                        except AssertionError:raise
                        except Exception:pass
                        page.wait_for_timeout(500)
                    assert expected in popup.locator('#version').inner_text()
                    assert '已更新至' in popup.locator('#status').inner_text()
                    assert (ext/'layout.css').read_bytes()==(ROOT/'extension/layout.css').read_bytes()
                    print('PASS: one real browser Reload downloaded and applied public v0.6.2 -> '+expected+'; runtime and layout files match.',flush=True)
                finally:context.close()
        finally:
            for path in keys:winreg.DeleteKey(winreg.HKEY_CURRENT_USER,path)

if __name__=='__main__':main()
