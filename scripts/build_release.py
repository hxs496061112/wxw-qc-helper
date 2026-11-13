from pathlib import Path
import base64
import hashlib
import json
import os
import subprocess
import zipfile
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]
DIST=ROOT/'dist'
POWERSHELL=Path(os.environ['SystemRoot'])/'System32/WindowsPowerShell/v1.0/powershell.exe'

def der(tag,data):
    n=len(data)
    length=bytes([n]) if n<128 else (bytes([0x80+(n.bit_length()+7)//8])+n.to_bytes((n.bit_length()+7)//8,'big'))
    return bytes([tag])+length+data

def public_key():
    root=ET.fromstring((ROOT/'manager/trusted-key.xml').read_text())
    def integer(name):
        value=base64.b64decode(root.findtext(name)).lstrip(b'\0') or b'\0'
        return der(2,(b'\0' if value[0]&128 else b'')+value)
    rsa=der(0x30,integer('Modulus')+integer('Exponent'))
    spki=der(0x30,bytes.fromhex('300d06092a864886f70d0101010500')+der(3,b'\0'+rsa))
    return base64.b64encode(spki).decode()

def main():
    DIST.mkdir(exist_ok=True)
    manifest_path=ROOT/'extension/manifest.json'
    manifest=json.loads(manifest_path.read_text(encoding='utf-8-sig'))
    manifest['key']=public_key()
    manifest_path.write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    version=manifest['version']
    for path in ROOT.rglob('*.ps1'):
        if 'dist' not in path.parts and 'test-output' not in path.parts:
            path.write_text(path.read_text(encoding='utf-8-sig'),encoding='utf-8-sig')
    files={}
    for folder in ('extension','manager'):
        for path in sorted((ROOT/folder).iterdir()):
            if path.is_file():files[path.relative_to(ROOT).as_posix()]=path.read_bytes()
    archive=DIST/'wxw-qc-update.zip'
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
        for name,content in files.items():z.writestr(name,content)
    release={'schema':1,'product':'wxw-qc-helper','version':version,
             'url':f'https://github.com/hxs496061112/wxw-qc-helper/releases/download/v{version}/wxw-qc-update.zip',
             'sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),
             'files':{name:hashlib.sha256(data).hexdigest() for name,data in files.items()}}
    (DIST/'latest.json').write_text(json.dumps(release,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    subprocess.run([str(POWERSHELL),'-NoProfile','-ExecutionPolicy','Bypass','-File',str(ROOT/'scripts/Sign-Release.ps1'),'-ManifestPath',str(DIST/'latest.json'),'-SignaturePath',str(DIST/'latest.sig')],check=True)
    launcher='@echo off\r\n"%SystemRoot%\\System32\\WindowsPowerShell\\v1.0\\powershell.exe" -NoProfile -ExecutionPolicy Bypass -File "%~dp0manager\\WxwQcUpdater.ps1" -Mode Install -PayloadDirectory "%~dp0payload"\r\nif errorlevel 1 pause\r\n'
    outer=DIST/'wxw-qc-installer.zip'
    with zipfile.ZipFile(outer,'w',zipfile.ZIP_DEFLATED) as z:
        prefix=f'旺销王助手在线更新版_v{version}/'
        z.writestr(prefix+'安装或升级.cmd',launcher.encode('ascii'))
        z.writestr(prefix+'使用说明.txt',(ROOT/'INSTALL.txt').read_text(encoding='utf-8-sig').encode('utf-8-sig'))
        for path in sorted((ROOT/'manager').iterdir()):
            if path.is_file():z.writestr(prefix+'manager/'+path.name,path.read_bytes())
        for name in ('latest.json','latest.sig','wxw-qc-update.zip'):
            z.writestr(prefix+'payload/'+name,(DIST/name).read_bytes())
    for path in (archive,outer):
        with zipfile.ZipFile(path) as z:assert z.testzip() is None
    print(json.dumps({'version':version,'runtime_files':len(files),'update_bytes':archive.stat().st_size,'installer_bytes':outer.stat().st_size},ensure_ascii=False))

if __name__=='__main__':main()
