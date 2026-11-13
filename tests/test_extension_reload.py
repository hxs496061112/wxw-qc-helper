"""Runs only against an isolated Chromium profile; no business website requests."""
import base64
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[1]

def main():
    with tempfile.TemporaryDirectory(prefix='wxw-browser-test-') as folder:
        temp=Path(folder)
        ext=temp/'extension'
        shutil.copytree(ROOT/'extension',ext)
        manifest=json.loads((ext/'manifest.json').read_text(encoding='utf-8'))
        digest=hashlib.sha256(base64.b64decode(manifest['key'])).hexdigest()[:32]
        extension_id=''.join(chr(ord('a')+int(c,16)) for c in digest)
        with sync_playwright() as p:
            context=p.chromium.launch_persistent_context(str(temp/'profile'),channel='chromium',headless=True,ignore_default_args=['--disable-extensions'],args=[f'--disable-extensions-except={ext}',f'--load-extension={ext}'])
            try:
                page=context.new_page()
                page.set_default_timeout(3000)
                page.set_default_navigation_timeout(3000)
                # Match the developer-mode install required in INSTALL.txt.
                page.goto('chrome://extensions/')
                page.locator('#devMode').click()
                url=f'chrome-extension://{extension_id}/popup.html'
                page.goto(url)
                print('Loaded installed popup.',flush=True)
                assert '0.6.1' in page.locator('#version').inner_text()
                manifest['version']='0.6.2'
                (ext/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False),encoding='utf-8')
                page.locator('#apply').click()
                print('Clicked runtime reload.',flush=True)
                # Reload unloads the popup. Opening it again must use the changed files.
                check=context.new_page()
                check.set_default_navigation_timeout(3000)
                check.set_default_timeout(3000)
                for _ in range(20):
                    try:
                        check.goto(url)
                        if '0.6.2' in check.locator('#version').inner_text(timeout=1000):break
                    except Exception as error:print(type(error).__name__,str(error)[:160],flush=True)
                    check.wait_for_timeout(250)
                assert '0.6.2' in check.locator('#version').inner_text()
                print('PASS: isolated Chromium popup reload reads the new on-disk extension version.')
            finally:context.close()

if __name__=='__main__':main()
