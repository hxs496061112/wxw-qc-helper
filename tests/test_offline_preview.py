"""Offline preview checks. Defaults to synthetic data; private files are opt-in."""
import argparse
import base64
import json
from pathlib import Path
import re
import sys
import tempfile

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from build_preview import Capture, build
from test_viewport_layout import workspace_fixture


def synthetic_build(folder):
    source = folder / 'saved.html'
    assets = folder / 'saved_files'
    assets.mkdir()
    png = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII=')
    (assets / 'test.png').write_bytes(png)
    (assets / 'saved.css').write_text('.sample{background:url(test.png)}@import url(https://blocked.invalid/remote.css);', encoding='utf-8')
    content = workspace_fixture(2, history_rows=8)
    styles = re.findall(r'<style>(.*?)</style>', content, re.S)
    content = re.sub(r'<style>.*?</style>', '', content, flags=re.S)
    content = re.sub(r'<!doctype[^>]*>|<meta[^>]*>', '', content, flags=re.I)
    content = re.sub(r'https://example.test/\d+\.svg', './saved_files/test.png', content)
    # Includes site scripts, an old extension host, and active form/anchor handlers.
    source.write_text('<!doctype html><html><head><link rel="stylesheet" href="./saved_files/saved.css">'+
                      ''.join('<style>'+s+'</style>' for s in styles)+'</head><body><div id="app">'+content+
                      '<section id="wxw-qc-live" data-version="0.4.3"><template shadowrootmode="open">OLD</template></section>'+
                      '<a id="unsafe-link" href="https://blocked.invalid/" onclick="window.leaked=true">测试链接</a>'+
                      '<form action="https://blocked.invalid/"><input value="do-not-copy"><button type="submit">测试提交</button></form>'+
                      '<script>window.leaked=true;fetch("https://blocked.invalid/")</script></div></body></html>', encoding='utf-8')
    snapshot = Capture(source).snapshot()
    assert '<script' not in snapshot['html'] and 'onclick' not in snapshot['html']
    assert 'https://blocked.invalid' not in snapshot['html'] and 'do-not-copy' not in snapshot['html']
    assert '<form' not in snapshot['html'] and 'wxw-qc-live' not in snapshot['html']
    assert 'background:url("data:image/png;base64,' in snapshot['css']
    assert '@import' not in snapshot['css']
    assert snapshot['saved_extension_versions'] == ['0.4.3']
    try:
        build(snapshot, ROOT / 'preview-private-test')
    except ValueError:
        pass
    else:
        raise AssertionError('Private output was allowed inside the public repository')
    unrelated = folder / 'unrelated'
    unrelated.mkdir()
    (unrelated / 'keep.txt').write_text('keep', encoding='utf-8')
    try:
        build(snapshot, unrelated)
    except ValueError:
        pass
    else:
        raise AssertionError('Unrelated output folder was overwritten')
    output = folder / 'preview'
    result = build(snapshot, output, source)
    assert (output / '原始网页存档.zip').exists()
    result2 = build(json.loads((output / 'page-snapshot.json').read_text(encoding='utf-8')), output)
    assert result2['extension_sha256'] == result['extension_sha256']
    return Path(result['preview'])


def check_preview(preview, screenshots=None):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={'width': 1920, 'height': 1000})
        page.set_default_timeout(6000)
        errors, requests = [], []
        page.on('pageerror', lambda e: errors.append(str(e)))
        page.route('http*://**/*', lambda r: (requests.append(r.request.method), r.abort()))
        page.goto(preview.resolve().as_uri())
        expected = {'single': [1], 'double': [2], 'two': [1, 1], 'mixed': [1, 2],
                    'three': [1, 1, 1], 'notes': [1, 1], 'no-notes': [1, 1]}
        results = []
        for scene in ['saved', *expected, 'duplicate', 'failure', 'waiting']:
            page.locator('#scene').select_option(scene)
            page.wait_for_timeout(1600)
            frame = page.frames[-1]
            host = frame.locator('#wxw-qc-live')
            assert host.count() == 1, scene
            assert host.get_attribute('data-version') == json.loads((ROOT / 'extension/manifest.json').read_text(encoding='utf-8'))['version']
            if scene in ('duplicate', 'failure', 'waiting'):
                wanted = {'duplicate': '这单重复了，重复扫描了。', 'failure': '本次扫码失败，请核对原页面',
                          'waiting': '等待本次扫码结果，上一单已清除'}[scene]
                expect(host.locator('.empty')).to_have_text(wanted)
                assert host.locator('.photo').count() == 0, scene
            else:
                assert host.locator('.item').count() > 0, scene
                if scene in expected:
                    quantities = expected[scene]
                    assert host.locator('.item').count() == len(quantities), scene
                    assert host.locator('.item .quantity b').all_text_contents() == ['× '+str(n) for n in quantities], scene
                    assert host.locator('.order-total b').inner_text() == '× '+str(sum(quantities)), scene
                    assert host.locator('.item .quantity.alert').count() == sum(n >= 2 for n in quantities), scene
                    assert host.locator('.size').all_text_contents() == [str(n)+'码' for n in [43,39,41][:len(quantities)]], scene
                    assert host.locator('.remark-box').count() == (2 if scene == 'notes' else 0), scene
                assert host.locator('.photo').evaluate_all('(es)=>es.every(e=>e.complete&&e.naturalWidth>0)'), scene
                assert host.locator('.size').first.evaluate('(e)=>getComputedStyle(e).color') == 'rgb(0, 0, 0)'
            assert frame.evaluate('!window.leaked')
            assert frame.locator('script[src],form,a[href^="http"]').count() == 0
            if screenshots and scene in ('saved', 'three', 'notes', 'duplicate'):
                screenshots.mkdir(parents=True, exist_ok=True)
                page.screenshot(path=str(screenshots / (scene+'.png')))
            results.append(scene)
        # Return to saved data; browser scroll must reveal the entire history.
        page.locator('#scene').select_option('saved')
        page.wait_for_timeout(900)
        frame = page.frames[-1]
        for width, height in ((1920,1000), (1536,864), (1280,800)):
            page.set_viewport_size({'width': width, 'height': height})
            page.wait_for_timeout(550)
            assert frame.evaluate('document.documentElement.scrollWidth<=innerWidth+1'), (width, height)
            last = frame.locator('.listview table.vxe-table--body tbody tr').last
            last.scroll_into_view_if_needed()
            assert last.is_visible()
            box = last.bounding_box()
            assert box['y'] >= 0 and box['y']+box['height'] <= height+1, (width, height, box)
            assert frame.locator('.listview').evaluate('(e)=>getComputedStyle(e).maxHeight') == 'none'
        verify = frame.get_by_role('button', name='验货', exact=True)
        if verify.count():
            verify.first.click()
            expect(page.locator('#status')).to_have_text('这是离线预览，此按钮不会执行真实业务操作')
        page.locator('#mode').select_option('native')
        page.wait_for_timeout(700)
        frame = page.frames[-1]
        assert frame.locator('#wxw-qc-live').count() == 0
        assert frame.locator('.right-center').count() > 0
        assert not errors, errors
        assert not requests, requests
        browser.close()
        return {'scenarios': results, 'browser_errors': len(errors), 'network_requests': len(requests), 'scroll_and_native_mode': 'passed'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--preview', type=Path, help='Optional private HTML; never committed')
    parser.add_argument('--screenshots', type=Path, help='Private output folder for screenshots')
    args = parser.parse_args()
    if args.preview:
        result = check_preview(args.preview, args.screenshots)
    else:
        with tempfile.TemporaryDirectory(prefix='wxw-offline-preview-') as tmp:
            result = check_preview(synthetic_build(Path(tmp)), args.screenshots)
    print(json.dumps(result, ensure_ascii=False))
