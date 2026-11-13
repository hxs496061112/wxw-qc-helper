"""Explicit live smoke check. Downloads public program assets; no account or business data."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import urllib.request
import zipfile

ROOT=Path(__file__).resolve().parents[1]
PS=Path(os.environ['SystemRoot'])/'System32/WindowsPowerShell/v1.0/powershell.exe'
FEED='https://github.com/hxs496061112/wxw-qc-helper/releases/latest/download/'

def run(manager,profile,*args):
    env=os.environ.copy()
    env['LOCALAPPDATA']=str(profile)
    result=subprocess.run([str(PS),'-NoProfile','-ExecutionPolicy','Bypass','-File',str(manager),*args,'-NoUI'],env=env,capture_output=True,timeout=180)
    if result.returncode:
        raise RuntimeError((result.stdout+result.stderr).decode('gb18030',errors='replace'))
    return json.loads((profile/'WxwQcHelper/extension/manifest.json').read_text(encoding='utf-8'))['version']

def main():
    with tempfile.TemporaryDirectory(prefix='wxw-public-release-') as folder:
        work=Path(folder)
        installer=work/'installer.zip'
        with urllib.request.urlopen(FEED+'wxw-qc-installer.zip',timeout=45) as response:
            installer.write_bytes(response.read(8388609))
        assert installer.read_bytes()==(ROOT/'dist/wxw-qc-installer.zip').read_bytes()
        with zipfile.ZipFile(installer) as archive:
            archive.extractall(work/'unpacked')
        base=next((work/'unpacked').iterdir())
        profile=work/'profile'
        expected=json.loads((ROOT/'extension/manifest.json').read_text(encoding='utf-8'))['version']
        assert run(base/'manager/WxwQcUpdater.ps1',profile,'-Mode','Install','-PayloadDirectory',str(base/'payload'))==expected
        # Exercise the updater's real HTTPS path, with no GitHub credentials.
        assert run(profile/'WxwQcHelper/Launch.ps1',profile,'-Mode','Update')==expected
        fresh=work/'fresh'
        assert run(ROOT/'manager/WxwQcUpdater.ps1',fresh,'-Mode','Update')==expected
        print(json.dumps({'public_version':expected,'installer_sha256':hashlib.sha256(installer.read_bytes()).hexdigest(),'offline_installer':'passed','online_download_and_install':'passed','repeat_update':'passed'},ensure_ascii=False))

if __name__=='__main__':main()
