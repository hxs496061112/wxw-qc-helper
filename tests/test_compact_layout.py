"""Layout regression using synthetic scan DOM only; all requests are intercepted."""
from html import escape
from pathlib import Path
import json
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'test-output'

def fixture(count,notes=False):
    orders=','.join('DEMO-ORDER-'+str(i) for i in range(count))
    cards=[]
    for i in range(count):
        size=39+i
        cards.append(f'''<div class="right-center"><div class="flex original-summary"><img class="thumb" src="https://example.test/{i}.svg"><div>合成测试商品 {i+1}<br>原商品标题、规格保留<br>规格1 : Demo-{size}</div></div>
          <div class="select-center"><div class="select-active"><div class="flex"><div class="select-image"><img src="https://example.test/{i}.svg"></div><div><div class="wrap">测试款 {i+1}（{size}）</div><div class="flex"><span class="sign">x1</span><div><div class="wrap">测试款 {i+1}（{size}）</div><div>规格1 : Demo-{size}</div></div></div></div></div></div></div></div>''')
    note='核对鞋码，加一副鞋带' if notes else '-'
    picking='合并包裹，请逐项核对' if notes else '-'
    headers=''.join(f'<th class="col_{i}">{label}</th>' for i,label in enumerate(['平台订单号','运单号','备注','拣货备注']))
    cells=''.join(f'<td class="col_{i}"><div class="vxe-cell">{escape(v)}</div></td>' for i,v in enumerate([orders,'TRACK-DEMO',note,picking]))
    return '''<!doctype html><meta charset="utf-8"><style>
      *{box-sizing:border-box}body{font:14px "Microsoft YaHei",sans-serif;margin:24px;background:#f5f6f8;color:#303b47}
      h2{font-size:18px;margin:0 0 18px}.el-card__body{background:white;padding:12px}
      #scanInput{width:85%;padding:12px;border:1px solid #99c6ff;margin:10px 0}button{padding:12px}
      .center-body{display:flex;align-items:stretch;min-height:760px}.body-left{width:20%;min-width:200px;padding:10px;position:relative}
      .body-left .shop{margin:0 0 12px;white-space:nowrap}.PRIMARY{color:#409eff}.status{position:absolute;right:8px;top:8px;color:#409eff}
      .body-right{width:80%;border:1px solid #eceff2;padding:10px}.right-title{display:flex;gap:10px;margin-bottom:14px}
      .right-title>div{width:25%;padding:8px;background:#f7f8fa;border:1px solid #ebeef2;border-radius:4px}
      .right-center{margin-bottom:12px}.flex{display:flex;gap:8px}.original-summary{margin-bottom:14px}
      .thumb{width:42px;height:42px}.select-center{border-left:2px solid #409eff;padding-left:8px}.select-image img{width:80px;height:80px}.wrap{line-height:1.5}
      table{width:100%;table-layout:fixed;border-collapse:collapse;margin-top:18px}td,th{border:1px solid #eee;padding:8px;overflow-wrap:anywhere;text-align:left;font-size:12px}
    </style><h2>质检布局预览 · 全部为合成测试数据</h2><div class="el-card__body"><div id="counter">累计扫描 1 次, 成功 1 次, 失败 0 次</div><input id="scanInput" placeholder="请扫描运单号"><button>扫描</button><div class="center-body"><div class="body-left">
    <div class="shop">DE 德国</div><div class="shop"><a href="#" class="PRIMARY">'''+orders+'''</a></div><div class="shop">TRACK-DEMO</div><div class="shop">合成物流商</div><div class="shop">测试物流渠道 · 标准服务</div><div class="shop">预估重量：1.5</div><span class="status">✓</span></div><div class="body-right"><div class="right-title"><div>合成测试店铺</div><div>EUR 64</div><div>已出库 已发货</div><div>合计数量 '''+str(count)+'''</div></div>'''+''.join(cards)+'''</div></div><div class="listview"><table class="vxe-table--header"><thead><tr>'''+headers+'''</tr></thead></table><table class="vxe-table--body"><tbody><tr>'''+cells+'''</tr></tbody></table><button id="verify">验货</button></div></div>'''

def main():
    OUT.mkdir(exist_ok=True)
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True)
        page=browser.new_page(viewport={'width':1920,'height':1080})
        page.set_default_timeout(5000)
        current={'html':''}
        def route(r):
            if r.request.url.endswith('.svg'):
                i=int(r.request.url.rsplit('/',1)[1].split('.')[0]);color=['#bed7eb','#ddd5c6','#c8dece'][i]
                svg=f'<svg xmlns="http://www.w3.org/2000/svg" width="420" height="420"><rect width="420" height="420" fill="{color}"/><path d="M50 235 L130 125 L220 225 L350 240 Q390 250 380 285 L60 285 Z" fill="#fff" stroke="#344c5d" stroke-width="8"/><text x="140" y="350" font-size="28" fill="#344c5d">SKU {i+1}</text></svg>'
                r.fulfill(content_type='image/svg+xml',body=svg)
            else:r.fulfill(content_type='text/html',body=current['html'])
        page.route('**/*',route)
        summaries=[]
        for count in (1,2,3):
            for notes in (False,True):
                current['html']=fixture(count,notes)
                page.goto('https://v3.wxwerp.com/order/startjob?taskId=synthetic')
                page.add_style_tag(content=(ROOT/'extension/layout.css').read_text(encoding='utf-8'))
                page.add_script_tag(content=(ROOT/'extension/content.js').read_text(encoding='utf-8'))
                panel=page.locator('#wxw-qc-live')
                panel.locator('.photo').first.wait_for()
                assert panel.locator('.item').count()==count
                assert panel.locator('.remark-box').count()==(2 if notes else 0)
                page.locator('#scanInput').focus()
                for width in (1920,1536,1366,1280,1024,768):
                    page.set_viewport_size({'width':width,'height':1080})
                    page.wait_for_timeout(180)
                    left=page.locator('.body-left').bounding_box();right=page.locator('.body-right').bounding_box();box=panel.bounding_box()
                    assert left['y']+left['height']<=right['y']+1
                    assert left['height']<160,(width,left)
                    assert abs(left['width']-right['width'])<2
                    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1'),(count,notes,width)
                    assert page.locator('#scanInput').evaluate('(e)=>e===document.activeElement')
                    assert page.locator('.body-left .shop').count()==6
                    for shop in page.locator('.body-left .shop').all():
                        assert shop.is_visible() and shop.evaluate('(e)=>e.scrollWidth<=e.clientWidth+1')
                    for original in page.locator('.right-center').all():
                        a=original.bounding_box()
                        assert a['x']+a['width']<=box['x']+1 or a['y']+a['height']<=box['y']+1,(width,a,box)
                    assert page.locator('.listview').bounding_box()['y']>=box['y']+box['height']-1
                    if count==3 and width>=1280:
                        cards=[card.bounding_box() for card in panel.locator('.item').all()]
                        assert max(c['y'] for c in cards)-min(c['y'] for c in cards)<2,(width,notes,cards)
                    if count==2 and not notes and width>=1366:
                        assert abs(box['x']+box['width']/2-width/2)<180
                    if width==1920 and not notes:
                        page.screenshot(path=str(OUT/f'layout-{count}-items.png'),full_page=True)
                        summaries.append({'items':count,'info_bar_height':left['height'],'panel_x':box['x'],'panel_width':box['width']})
                if notes:
                    page.set_viewport_size({'width':1920,'height':1080})
                    page.screenshot(path=str(OUT/f'layout-{count}-items-notes.png'),full_page=True)
        # The stylesheet must not apply to other routes after the extension detaches.
        page.evaluate("history.pushState({},'', '/order/list')")
        page.wait_for_function("!document.querySelector('.wxw-qc-layout')")
        assert page.locator('.center-body').evaluate('(e)=>getComputedStyle(e).display')=='flex'
        print('PASS: single/two/three SKU, remarks, 6 viewport widths, original controls/focus, route cleanup.')
        print(json.dumps(summaries))
        browser.close()

if __name__=='__main__':main()
