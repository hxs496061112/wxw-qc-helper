"""Real native-messaging protocol with synthetic updater and isolated browser."""
import json
from pathlib import Path
import shutil
import tempfile
import time
import winreg
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[1]
ID='hldbbmhhmgjcfmlbkglekcigjkbefobe'
NAME='com.wxw.qc.test'

def main():
    keys=[]
    with tempfile.TemporaryDirectory(prefix='wxw-native-test-') as folder:
        work=Path(folder)
        ext=work/'extension';shutil.copytree(ROOT/'extension',ext)
        background=ext/'background.js'
        background.write_text(background.read_text(encoding='utf-8').replace('com.wxw.qc.updater',NAME),encoding='utf-8')
        for name in ('NativeHost.cmd','NativeHost.ps1'):shutil.copy2(ROOT/'manager'/name,work/name)
        (work/'Launch.ps1').write_text("$p=Join-Path $PSScriptRoot 'extension/manifest.json';$m=[IO.File]::ReadAllText($p)|ConvertFrom-Json;$m.version='0.7.1';[IO.File]::WriteAllText($p,($m|ConvertTo-Json -Depth 8));[IO.File]::AppendAllText((Join-Path $PSScriptRoot 'calls.txt'),'x');exit 0",encoding='utf-8-sig')
        host=work/'host.json'
        host.write_text(json.dumps({'name':NAME,'description':'Isolated update test','path':str(work/'NativeHost.cmd'),'type':'stdio','allowed_origins':[f'chrome-extension://{ID}/']}),encoding='utf-8')
        try:
            for vendor in ('Google\\Chrome','Chromium'):
                path=f'Software\\{vendor}\\NativeMessagingHosts\\{NAME}'
                try:
                    key=winreg.OpenKey(winreg.HKEY_CURRENT_USER,path);key.Close()
                    raise RuntimeError('Test registry key already exists; refusing to overwrite')
                except FileNotFoundError:pass
                with winreg.CreateKey(winreg.HKEY_CURRENT_USER,path) as key:winreg.SetValueEx(key,'',0,winreg.REG_SZ,str(host))
                keys.append(path)
            with sync_playwright() as p:
                context=p.chromium.launch_persistent_context(str(work/'profile'),channel='chromium',headless=True,ignore_default_args=['--disable-extensions'],args=[f'--load-extension={ext}'])
                try:
                    page=context.new_page();page.set_default_timeout(5000)
                    page.goto('chrome://extensions/');page.locator('#devMode').click()
                    popup=context.new_page()
                    deadline=time.monotonic()+30
                    while time.monotonic()<deadline:
                        try:
                            if popup.is_closed():popup=context.new_page()
                            popup.goto(f'chrome-extension://{ID}/popup.html',timeout=3000)
                            if '0.7.1' in popup.locator('#version').inner_text(timeout=1000) and '已更新至' in popup.locator('#status').inner_text(timeout=1000):break
                        except Exception as error:print(type(error).__name__,flush=True)
                        page.wait_for_timeout(300)
                    assert '0.7.1' in popup.locator('#version').inner_text()
                    assert '已更新至' in popup.locator('#status').inner_text(),popup.locator('#status').inner_text()
                    assert (work/'calls.txt').read_text()=='x','Reload loop detected'
                    # Use the browser's actual extension-management reload button.
                    page.locator('extensions-item').locator('#dev-reload-button').click()
                    deadline=time.monotonic()+15
                    while time.monotonic()<deadline and (work/'calls.txt').read_text()!='xx':page.wait_for_timeout(250)
                    assert (work/'calls.txt').read_text()=='xx','Browser Reload did not invoke updater'
                    (work/'Launch.ps1').write_text('exit 1',encoding='utf-8-sig')
                    page.wait_for_timeout(500)
                    page.locator('extensions-item').locator('#dev-reload-button').click()
                    if popup.is_closed():popup=context.new_page()
                    popup.goto(f'chrome-extension://{ID}/popup.html')
                    popup.locator('#status').filter(has_text='更新未完成').wait_for(timeout=15000)
                    assert '0.7.1' in popup.locator('#version').inner_text()
                    (work/'skip-online-once.json').write_text('{}')
                    page.locator('extensions-item').locator('#dev-reload-button').click()
                    if popup.is_closed():popup=context.new_page()
                    popup.goto(f'chrome-extension://{ID}/popup.html')
                    popup.locator('#status').filter(has_text='回退版本已加载').wait_for(timeout=15000)
                    assert not (work/'skip-online-once.json').exists()
                    print('PASS: native host, automatic apply, browser Reload, no loop, failure preserves version.')
                finally:context.close()
        finally:
            for path in keys:winreg.DeleteKey(winreg.HKEY_CURRENT_USER,path)

if __name__=='__main__':main()
