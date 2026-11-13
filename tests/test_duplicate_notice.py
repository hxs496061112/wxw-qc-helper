"""Duplicate result recognition uses fresh system notices and failure counters."""
from pathlib import Path
from playwright.sync_api import sync_playwright
from test_viewport_layout import workspace_fixture as fixture

ROOT=Path(__file__).resolve().parents[1]
MESSAGE='这单重复了，重复扫描了。'

with sync_playwright() as p:
    browser=p.chromium.launch(headless=True)
    page=browser.new_page(viewport={'width':1536,'height':1000})
    page.set_default_timeout(5000)
    page.route('**/*',lambda r:r.fulfill(content_type='image/svg+xml',body='<svg xmlns="http://www.w3.org/2000/svg" width="200" height="200"><rect width="200" height="200" fill="#dde6df"/></svg>') if r.request.url.endswith('.svg') else r.fulfill(content_type='text/html',body=fixture(2)))
    page.goto('https://v3.wxwerp.com/order/startjob?taskId=synthetic')
    page.add_style_tag(content=(ROOT/'extension/layout.css').read_text(encoding='utf-8'))
    page.add_script_tag(content=(ROOT/'extension/content.js').read_text(encoding='utf-8'))
    panel=page.locator('#wxw-qc-live')
    panel.locator('.photo').first.wait_for()
    def scan(code):
        page.locator('#scanInput').fill(code);page.locator('#scanInput').press('Enter')
    def counter(total,success,fail):
        page.locator('#counter').evaluate('(e,t)=>e.textContent=t',f'累计扫描 {total} 次, 成功 {success} 次, 失败 {fail} 次')
    def toast(text):
        page.evaluate('(t)=>{const e=document.createElement("div");e.className="el-message el-message--error";e.setAttribute("role","alert");e.textContent=t;document.body.append(e);}',text)

    scan('TRACK-DEMO')
    # A normal order remark containing the same sentence must not classify a failure.
    page.evaluate('()=>{const e=document.createElement("p");e.textContent="已存在被扫描过的订单 DEMO";document.querySelector(".body-left").append(e);}')
    counter(2,1,1)
    panel.locator('.empty').filter(has_text='本次扫码失败').wait_for()
    assert panel.locator('.photo').count()==0
    # The error banner may arrive after the failed counter. Upgrade the reason when it arrives.
    toast('已存在被扫描过的订单DEMO-ORDER-0')
    panel.locator('.duplicate').wait_for()
    assert panel.locator('.duplicate').inner_text()==MESSAGE
    assert panel.locator('.duplicate').evaluate('(e)=>getComputedStyle(e).color')=='rgb(189, 32, 32)'
    assert int(panel.locator('.duplicate').evaluate('(e)=>getComputedStyle(e).fontWeight'))>=800
    assert float(panel.locator('.duplicate').evaluate('(e)=>parseFloat(getComputedStyle(e).fontSize)'))>=32
    assert page.locator('#scanInput').evaluate('(e)=>e===document.activeElement')
    # Existing duplicate notice must not leak into a different failure.
    scan('TRACK-OTHER');counter(3,1,2);toast('订单不存在')
    panel.locator('.empty').filter(has_text='本次扫码失败').wait_for()
    assert panel.locator('.duplicate').count()==0
    # Identical text in a new toast is still a fresh duplicate result.
    scan('TRACK-DEMO');toast('已存在被扫描过的订单DEMO-ORDER-0')
    page.wait_for_timeout(200);counter(4,1,3)
    panel.locator('.duplicate').wait_for()
    page.locator('.el-message').evaluate_all('(nodes)=>nodes.forEach(e=>e.remove())')
    page.wait_for_timeout(650)
    assert panel.locator('.duplicate').inner_text()==MESSAGE
    assert panel.locator('.photo,.remark-box').count()==0
    (ROOT/'test-output').mkdir(exist_ok=True)
    page.screenshot(path=str(ROOT/'test-output/duplicate-notice.png'),full_page=True)
    # Next successful scan must clear duplicate state and render SKU information again.
    scan('TRACK-DEMO');counter(5,2,3)
    panel.locator('.photo').first.wait_for()
    assert panel.locator('.duplicate').count()==0 and panel.locator('.photo').count()==2
    print('PASS: fresh duplicate toast, both event orders, persistent large red text, stale notice isolation, unrelated failures and next success.')
    browser.close()
