"""Build a private, self-contained offline preview from an explicitly saved HTML.

No network requests. Website scripts/links/forms are not carried into the preview.
The public repo contains only this builder and synthetic tests, never saved orders.
"""
import argparse
import base64
from datetime import datetime, timezone
import hashlib
from html import escape
from html.parser import HTMLParser
import json
import mimetypes
from pathlib import Path
import re
import secrets
from urllib.parse import unquote, urlsplit
import zipfile

ROOT = Path(__file__).resolve().parents[1]
VOID = set('area base br col embed hr img input link meta param source track wbr'.split())
MARKER = 'wxw-qc-private-offline-preview-v1'
PLACEHOLDER = 'data:image/svg+xml;base64,' + base64.b64encode(b'<svg xmlns="http://www.w3.org/2000/svg" width="300" height="300"><rect width="300" height="300" fill="#eef3ef"/></svg>').decode()


class Node:
    def __init__(self, tag='', attrs=(), parent=None):
        self.tag, self.attrs, self.children, self.parent = tag, dict(attrs), [], parent

    def walk(self):
        yield self
        for child in self.children:
            if isinstance(child, Node):
                yield from child.walk()

    def has(self, cls):
        return cls in self.attrs.get('class', '').split()

    def text(self):
        return ''.join(c.text() if isinstance(c, Node) else c for c in self.children)


class Document(HTMLParser):
    def __init__(self, source):
        super().__init__(convert_charrefs=True)
        self.root = Node()
        self.current = self.root
        self.feed(source)

    def handle_starttag(self, tag, attrs):
        child = Node(tag, attrs, self.current)
        self.current.children.append(child)
        if tag not in VOID:
            self.current = child

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        node = self.current
        while node.parent:
            if node.tag == tag:
                self.current = node.parent
                return
            node = node.parent

    def handle_data(self, data):
        self.current.children.append(data)


class Capture:
    def __init__(self, source):
        self.source = source.resolve()
        self.assets_dir = source.with_name(source.stem + '_files').resolve()
        self.assets = {}
        self.missing_assets = 0

    def local(self, url, base=None):
        parsed = urlsplit(url)
        if parsed.scheme or parsed.netloc:
            return None
        path = ((base or self.source.parent) / unquote(parsed.path)).resolve()
        if not path.is_relative_to(self.assets_dir) or not path.is_file():
            return None
        return path

    def data_url(self, url, base=None):
        if re.match(r'^data:(image/(?:png|jpeg|gif|webp|x-icon)|font/[a-z0-9.+-]+|application/(?:font-[a-z0-9.+-]+|x-font-[a-z0-9.+-]+));base64,', url, re.I):
            return url
        path = self.local(url, base)
        if path and path.suffix.lower() in ('.png', '.jpg', '.jpeg', '.gif', '.webp', '.ico', '.woff', '.woff2', '.ttf', '.otf'):
            if path.stat().st_size > 15_000_000:
                raise ValueError('Saved asset exceeds 15 MB')
            mime = mimetypes.guess_type(path.name)[0] or 'application/octet-stream'
            return 'data:' + mime + ';base64,' + base64.b64encode(path.read_bytes()).decode()
        self.missing_assets += 1
        return ''

    def css(self, text, base=None):
        # CSS may contain remote imports/fonts. Preserve local/data assets only.
        text = re.sub(r'@import\b[^;]*;', '', text, flags=re.I)
        def replace(match):
            url = match.group(1).strip().strip('\'"')
            if url.startswith('#'):
                return 'url(' + url + ')'
            data = self.data_url(url, base)
            return 'url("' + data + '")' if data else 'none'
        return re.sub(r'url\(\s*(.*?)\s*\)', replace, text, flags=re.I | re.S)

    def render(self, node):
        if isinstance(node, str):
            return escape(node, quote=False)
        attrs = node.attrs
        if node.tag in ('script', 'iframe', 'object', 'embed', 'audio', 'video', 'source', 'link', 'base', 'meta', 'template', 'style'):
            return ''
        if node.tag.startswith(('deepl-', 'codex-')) or attrs.get('id', '').startswith(('wxw-qc-', '_aihecong', 'codex-')):
            return ''
        values = {}
        for key, value in attrs.items():
            if value is None:
                value = ''
            if key.lower().startswith('on') or key in ('src', 'srcset', 'href', 'xlink:href', 'action', 'formaction', 'target', 'ping', 'nonce', 'integrity', 'download', 'autofocus', 'value'):
                if key in ('href', 'xlink:href') and value.startswith('#') and node.tag == 'use':
                    values[key] = value
                continue
            if key == 'class':
                value = ' '.join(c for c in value.split() if not c.startswith('wxw-qc-'))
            if key == 'style':
                value = re.sub(r'--wxw-qc-[^:;]+:[^;]*;?', '', value)
                value = self.css(value)
            # Keep Vue scope attributes and ordinary presentation/accessibility attributes.
            if key.startswith('data-v-') or key.startswith('aria-') or key in ('id', 'class', 'style', 'name', 'type', 'placeholder', 'role', 'tabindex', 'width', 'height', 'colspan', 'rowspan', 'title', 'alt', 'viewbox', 'd', 'fill', 'stroke', 'stroke-width', 'xmlns', 'cx', 'cy', 'r', 'x', 'y', 'x1', 'x2', 'y1', 'y2', 'points', 'transform', 'preserveaspectratio', 'clip-path', 'fill-rule', 'opacity', 'disabled', 'checked'):
                values[key] = value
        if node.tag == 'img':
            data = self.data_url(attrs.get('src', ''))
            key = hashlib.sha256(data.encode()).hexdigest()[:20] if data else 'missing'
            self.assets[key] = data or PLACEHOLDER
            values['data-preview-asset'] = key
            values['src'] = PLACEHOLDER
        if node.tag in ('button', 'input') and values.get('type') == 'submit':
            values['type'] = 'button'
        tag = 'div' if node.tag == 'form' else node.tag
        opening = '<' + tag + ''.join(' ' + k + '="' + escape(v, quote=True) + '"' for k, v in values.items()) + '>'
        return opening + ('' if tag in VOID else ''.join(self.render(c) for c in node.children) + '</' + tag + '>')

    def snapshot(self):
        document = Document(self.source.read_text(encoding='utf-8-sig'))
        nodes = list(document.root.walk())
        app = next((n for n in nodes if n.attrs.get('id') == 'app'), None)
        if not app:
            app = next((n for n in nodes if n.tag == 'body'), None)
        if not app or not any(n.attrs.get('id') == 'scanInput' for n in app.walk()):
            raise ValueError('Saved HTML must contain the order scan input')
        if not any(n.has('right-center') for n in app.walk()):
            raise ValueError('Saved HTML does not contain a scanned SKU result')
        css = []
        for node in nodes:
            if node.tag == 'link' and node.attrs.get('rel') == 'stylesheet':
                path = self.local(node.attrs.get('href', ''))
                if path and path.suffix == '.css' and path.name != 'hecong.css':
                    css.append(self.css(path.read_text(encoding='utf-8-sig'), path.parent))
            if node.tag == 'style' and node.parent and node.parent.tag == 'head':
                text = node.text()
                if not any(x in text for x in ('wxw-qc', ':host', 'codex-', 'aihecong', 'feedback-iconfont')):
                    css.append(self.css(text))
        # Preserve the site's SVG icon symbols, which can be siblings of #app.
        symbols = [n for n in nodes if n.tag == 'svg' and any(c.tag == 'symbol' for c in n.children if isinstance(c, Node))]
        extras = ''
        app_nodes = set(app.walk())
        for node in symbols:
            if node in app_nodes:
                continue
            node.attrs['style'] = 'position:absolute;width:0;height:0;overflow:hidden'
            node.attrs['aria-hidden'] = 'true'
            extras += self.render(node)
        body = extras + self.render(app)
        versions = [n.attrs.get('data-version') for n in nodes if n.attrs.get('id') == 'wxw-qc-live']
        body_node = next((n for n in nodes if n.tag == 'body'), None)
        body_style = self.css(body_node.attrs.get('style', '')) if body_node else ''
        return {'schema': 1, 'captured_at': datetime.now(timezone.utc).isoformat(), 'saved_extension_versions': versions, 'body_style': body_style,
                'html': body, 'css': '\n'.join(css), 'assets': self.assets, 'missing_asset_references': self.missing_assets,
                'source_sha256': hashlib.sha256(self.source.read_bytes()).hexdigest()}


def preview_script():
    source = (ROOT / 'extension/content.js').read_text(encoding='utf-8')
    replacements = {
        "location.hostname!=='v3.wxwerp.com'": "!document.documentElement.hasAttribute('data-wxw-offline-preview')",
        "const onScanPage=()=>/^\\/order\\/startjob\\/?$/.test(location.pathname);": "const onScanPage=()=>document.documentElement.hasAttribute('data-wxw-offline-preview');",
        "if(url.protocol!=='https:')return null;": "if(!['data:','https:'].includes(url.protocol))return null;",
    }
    for old, new in replacements.items():
        if source.count(old) != 1:
            raise ValueError('Preview adapter needs review after extension source changed: ' + old)
        source = source.replace(old, new)
    return source


def build(snapshot, output, source=None):
    output = output.resolve()
    if output.is_relative_to(ROOT):
        raise ValueError('Private preview output must be outside the public repository')
    marker = output / '.wxw-preview'
    if output.exists() and any(output.iterdir()) and (not marker.exists() or marker.read_text() != MARKER):
        raise ValueError('Refusing to overwrite an unrelated nonempty output directory')
    output.mkdir(parents=True, exist_ok=True)
    marker.write_text(MARKER)
    if snapshot.get('schema') != 1:
        raise ValueError('Unsupported private snapshot format')
    manifest = json.loads((ROOT / 'extension/manifest.json').read_text(encoding='utf-8'))
    nonce = secrets.token_hex(16)
    payload = {'snapshot': snapshot, 'version': manifest['version'], 'nonce': nonce,
               'extensionJS': preview_script(), 'extensionCSS': (ROOT / 'extension/layout.css').read_text(encoding='utf-8')}
    template = (ROOT / 'preview/index.html').read_text(encoding='utf-8')
    encoded = json.dumps(payload, ensure_ascii=False).replace('<', '\\u003c').replace('\u2028', '\\u2028').replace('\u2029', '\\u2029')
    page = template.replace('__NONCE__', nonce).replace('__PAYLOAD__', encoded)
    (output / '打开预览.html').write_text(page, encoding='utf-8')
    (output / 'page-snapshot.json').write_text(json.dumps(snapshot, ensure_ascii=False), encoding='utf-8')
    (output / '使用说明.txt').write_text(
        '旺销王质检离线预览\n\n双击“打开预览.html”即可，不需要扫码枪、登录或联网。\n'
        '默认显示已保存的现场页面，并应用构建时的最新插件。顶部可选择单款、合并单、备注、重复扫码等演练场景。\n'
        '“现场原页面”用于对照原结构；“最新插件布局”用于修改和检查插件效果。\n'
        '这里的扫描和验货都是离线演练，不会提交订单。它不能代替质检电脑实际扫码验收。\n\n'
        '请保留整个文件夹。page-snapshot.json 是可复用的私有场景数据；如有原始网页存档.zip，它是保存网页的备份。\n'
        '文件含现场商品和订单信息，仅存放本机，不要上传到公开仓库。以后修改请告诉 Codex 使用这个文件夹重建预览。\n'
        f'本次插件版本：{manifest["version"]}\n', encoding='utf-8-sig')
    if source:
        assets = source.with_name(source.stem + '_files')
        archive = output / '原始网页存档.zip'
        if not archive.exists():
            with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as z:
                z.write(source, source.name)
                if assets.is_dir():
                    for path in sorted(assets.rglob('*')):
                        if path.is_file() and not path.is_symlink():
                            z.write(path, str(path.relative_to(source.parent)))
    result = {'version': manifest['version'], 'preview': str(output / '打开预览.html'),
              'image_assets': len(snapshot['assets']), 'preview_bytes': (output / '打开预览.html').stat().st_size,
              'extension_sha256': hashlib.sha256((ROOT / 'extension/content.js').read_bytes()).hexdigest()}
    (output / 'build-info.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    return result


def main():
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--source', type=Path, help='Saved webpage HTML, with its sibling _files directory')
    group.add_argument('--snapshot', type=Path, help='Previously generated private page-snapshot.json')
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    snapshot = Capture(args.source).snapshot() if args.source else json.loads(args.snapshot.read_text(encoding='utf-8'))
    print(json.dumps(build(snapshot, args.output_dir, args.source), ensure_ascii=False))


if __name__ == '__main__':
    main()
