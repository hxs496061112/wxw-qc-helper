"""Viewport fit on the observed scan-page structure. Only synthetic data/requests."""
from pathlib import Path
import json
from playwright.sync_api import sync_playwright
from test_compact_layout import fixture

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'test-output'


def workspace_fixture(count, notes=False):
    html = fixture(count, notes)
    start = html.index('<div class="el-card__body">')
    result = html.index('<div class="center-body">')
    html = html[:start] + '''<div class="page"><div class="section">
      <div id="counter" class="ta-left mb-10px">累计扫描 5 次, 成功 5 次, 失败 0 次</div>
      <div class="navbar mb-10px"><div class="flex mb-10px">
        <div class="el-input"><input id="scanInput" placeholder="请扫描运单号"></div><button id="scanButton">扫描</button>
      </div></div><div class="el-card"><div class="el-card__body">''' + html[result:]
    html = html.replace('<div class="listview">', '<div class="task">任务 DEMO · 导入装袋 · 导出</div><div class="listview">')
    # Model a long scan history; all rows remain in the DOM for remark matching.
    row_start = html.index('<tbody><tr>') + len('<tbody>')
    row_end = html.index('</tr></tbody>', row_start) + len('</tr>')
    row = html[row_start:row_end]
    html = html[:row_end] + row * 9 + html[row_end:]
    html += '''</div></div></div><style>
      body{margin:0;padding:0}h2{height:78px;padding:16px;margin:0;font-size:16px}
      .section{padding:10px}.mb-10px{margin-bottom:10px}.el-card{border:1px solid #eee;overflow:hidden}
      .navbar .el-input{width:100%}#scanInput{width:100%;height:46px;margin:0}.navbar .flex{gap:10px}
      .center-body{margin-bottom:15px}.body-right{padding:10px}.right-center{font-size:12px}
      .right-title{margin-bottom:14px}.right-title>div{line-height:1.4}
      .task{height:20px;margin-bottom:10px}.listview table{margin:0}.listview th{height:32px}.listview td{height:52px}
      .listview table.vxe-table--header{position:sticky;top:0;background:#f5f7fa}
    </style>'''
    return html


def main():
    OUT.mkdir(exist_ok=True)
    summaries=[]
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True)
        page=browser.new_page(viewport={'width':1920,'height':920})
        page.set_default_timeout(5000)
        current={'html':''}
        def route(r):
            if r.request.url.endswith('.svg'):
                r.fulfill(content_type='image/svg+xml',body='<svg xmlns="http://www.w3.org/2000/svg" width="420" height="420"><rect width="420" height="420" fill="#dae7e0"/><path d="M40 240 L130 110 L220 220 L350 240 Q390 250 380 290 L50 290 Z" fill="#fff" stroke="#344c5d" stroke-width="8"/><text x="110" y="350" font-size="28">TEST SKU</text></svg>')
            else:r.fulfill(content_type='text/html',body=current['html'])
        page.route('**/*',route)
        for count in (1,2,3):
            for notes in (False,True):
                current['html']=workspace_fixture(count,notes)
                page.goto('https://v3.wxwerp.com/order/startjob?taskId=synthetic')
                page.add_style_tag(content=(ROOT/'extension/layout.css').read_text(encoding='utf-8'))
                page.add_script_tag(content=(ROOT/'extension/content.js').read_text(encoding='utf-8'))
                panel=page.locator('#wxw-qc-live')
                panel.locator('.photo').first.wait_for()
                page.locator('#scanInput').focus()
                # Stable node identity matters: never replace the input or product photos on resize.
                page.evaluate('window.originalInput=document.querySelector("#scanInput");window.originalPhoto=document.querySelector("#wxw-qc-live").shadowRoot.querySelector(".photo")')
                for width,height in ((2187,1030),(1920,920),(1536,730),(1366,640),(1280,720)):
                    page.set_viewport_size({'width':width,'height':height})
                    page.wait_for_timeout(500)
                    data=page.evaluate('''()=>{
                      const h=document.querySelector('#wxw-qc-live'),s=h.shadowRoot;
                      const box=e=>{const r=e.getBoundingClientRect();return {x:r.x,y:r.y,w:r.width,h:r.height,bottom:r.bottom,right:r.right}};
                      return {panel:box(h),input:box(document.querySelector('#scanInput')),history:box(document.querySelector('.listview')),photos:[...s.querySelectorAll('.photo')].map(box),names:[...s.querySelectorAll('.name')].map(box),notes:[...s.querySelectorAll('.remark-box')].map(box),scroll:scrollY,overflow:document.documentElement.scrollWidth>innerWidth+1,
                        focus:document.activeElement===originalInput,sameInput:document.querySelector('#scanInput')===originalInput,samePhoto:s.querySelector('.photo')===originalPhoto,
                        total:s.querySelector('.order-total').innerText,styles:h.getAttribute('style')};}''')
                    assert data['panel']['bottom']<=height-95,(count,notes,width,height,data)
                    assert data['history']['bottom']<=height+2,(count,notes,width,height,data)
                    assert 96<=data['history']['h']<=165
                    assert data['input']['w']<width*.31 and data['input']['x']<30,data
                    assert data['input']['w']>=210,data
                    assert not data['overflow'] and data['scroll']==0,data
                    assert data['focus'] and data['sameInput'] and data['samePhoto'],data
                    assert len(data['photos'])==count and len(data['notes'])==(2 if notes else 0)
                    assert min(x['h'] for x in data['photos'])>=(80 if height<680 else 100)
                    assert page.locator('.listview tbody tr').count()==10
                    for box in data['names']+data['notes']:
                        assert box['bottom']<=data['panel']['bottom']+1
                    if (width,height)==(1536,730):
                        page.screenshot(path=str(OUT/f'viewport-{count}-notes-{notes}.png'))
                        summaries.append({'items':count,'notes':notes,'photo_h':data['photos'][0]['h'],'panel_bottom':data['panel']['bottom'],'history_bottom':data['history']['bottom']})
                # Scrolling history must not resize the main panel or lose any rows.
                before=panel.bounding_box()
                page.locator('.listview').evaluate('(e)=>e.scrollTop=180')
                page.wait_for_timeout(650)
                assert abs(panel.bounding_box()['height']-before['height'])<1
                assert page.locator('.listview').evaluate('(e)=>e.scrollTop')>0
        # Idle sizing must settle, not create a MutationObserver/layout loop.
        page.wait_for_timeout(600)
        page.evaluate('''()=>{window.layoutMutations=0;window.layoutWatcher=new MutationObserver(r=>layoutMutations+=r.length);layoutWatcher.observe(document.querySelector('.section'),{subtree:true,attributes:true,attributeFilter:['class','style']})}''')
        page.wait_for_timeout(1100)
        assert page.evaluate('layoutMutations')<5,page.evaluate('layoutMutations')
        page.evaluate('layoutWatcher.disconnect()')
        # Mixed quantities stay per SKU rather than counting the number of cards.
        page.locator('.sign').nth(1).evaluate('(e)=>e.textContent="x2"')
        page.locator('.right-title>div').last.evaluate('(e)=>e.textContent="合计数量 4"')
        page.wait_for_timeout(700)
        assert panel.locator('.order-total').inner_text().replace('\n','')=='本单合计× 4'
        assert panel.locator('.item .quantity.alert').count()==1
        # Native remark banners consume space too; accommodate them without hiding notes.
        page.set_viewport_size({'width':1920,'height':920})
        page.evaluate('''()=>{const result=document.querySelector('.center-body');for(let i=0;i<2;i++){const e=document.createElement('div');e.className='tips';e.textContent=i?'合并包裹，请逐项核对':'核对鞋码，加一副鞋带';e.style.cssText='padding:10px;margin-bottom:6px;background:#fcc';result.before(e)}}''')
        page.wait_for_timeout(700)
        assert panel.locator('.remark-box').count()==2
        assert page.locator('.listview').bounding_box()['y']+page.locator('.listview').bounding_box()['height']<=922
        # A long note must remain fully readable; allow overflow instead of hiding safety text.
        page.locator('.col_2 .vxe-cell').evaluate_all('(nodes)=>nodes.forEach(e=>e.textContent="请核对备注与鞋码。".repeat(80))')
        page.locator('.tips').first.evaluate('(e)=>e.textContent="请核对备注与鞋码。"')
        page.wait_for_timeout(700)
        assert panel.locator('.remark-text').first.inner_text()=="请核对备注与鞋码。"*80
        assert panel.locator('.remark-text').first.evaluate('(e)=>e.scrollHeight<=e.clientHeight+1')
        # Input keeps website handlers; the helper never clicks scan or verification.
        page.evaluate('window.scans=0;window.verifications=0;originalInput.addEventListener("keydown",e=>{if(e.key==="Enter")scans++});document.querySelector("#verify").addEventListener("click",()=>verifications++)')
        page.locator('#scanInput').fill('SYNTHETIC-TRACK');page.locator('#scanInput').press('Enter')
        page.wait_for_timeout(400)
        assert page.evaluate('scans===1&&verifications===0')
        assert panel.locator('.photo').count()==0
        # Route leave restores the native input width and the complete unbounded table.
        page.evaluate("history.pushState({},'', '/order/list')")
        page.wait_for_function("!document.querySelector('.wxw-qc-workspace')")
        assert page.locator('.listview').evaluate('(e)=>getComputedStyle(e).maxHeight')=='none'
        assert page.locator('#scanInput').bounding_box()['width']>1000
        # Opening a fresh task without a scanned order must already shorten the input.
        current['html']=workspace_fixture(1).replace('<div class="center-body">','<div class="empty-result">')
        page.goto('https://v3.wxwerp.com/order/startjob?taskId=empty')
        page.add_style_tag(content=(ROOT/'extension/layout.css').read_text(encoding='utf-8'))
        page.add_script_tag(content=(ROOT/'extension/content.js').read_text(encoding='utf-8'))
        page.locator('.wxw-qc-workspace').wait_for()
        assert page.locator('#scanInput').bounding_box()['width']<550
        assert page.locator('#wxw-qc-live').count()==0
        print('PASS: viewport fit, short native scan input, history scrolling, focus/node stability, quantity and route cleanup.')
        print(json.dumps(summaries))
        browser.close()


if __name__=='__main__':main()
