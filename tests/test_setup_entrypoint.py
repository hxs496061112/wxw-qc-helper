"""Exercise the shipped CMD entry, signed installation, and real registry writes.
Only the registry subkey is redirected in the extracted test copy; the signed
payload remains unchanged. No production registration or desktop is modified.
"""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import threading
import time
import uuid
import winreg
import zipfile

ROOT=Path(__file__).resolve().parents[1]
PRODUCTION_KEY=r'Software\Microsoft\Edge\NativeMessagingHosts\com.wxw.qc.updater'

def launch(cmd,env):
    # The known CMD is a test entry, never a filesystem delete/move command.
    process=subprocess.Popen([os.environ['COMSPEC'],'/d','/c',str(cmd)],env=env,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
    output=bytearray();ready=threading.Event()
    def read():
        for line in iter(process.stdout.readline,b''):
            output.extend(line)
            if b'Press any key to close' in line:ready.set()
    reader=threading.Thread(target=read,daemon=True);reader.start()
    try:
        assert ready.wait(45),output.decode('utf-8',errors='replace')
        assert process.poll() is None,'Installer closed before the user acknowledged the result'
        process.stdin.write(b'\r\n');process.stdin.flush();process.stdin.close()
        code=process.wait(timeout=10);reader.join(timeout=5)
        return code,output.decode('utf-8',errors='replace')
    finally:
        if process.poll() is None:process.kill();process.wait()

def main():
    key=PRODUCTION_KEY+'.setup-test-'+uuid.uuid4().hex
    with tempfile.TemporaryDirectory(prefix='wxw-setup-test-') as folder:
        work=Path(folder)
        with zipfile.ZipFile(ROOT/'dist/wxw-qc-installer.zip') as z:z.extractall(work/'中文 安装目录')
        package=next((work/'中文 安装目录').iterdir())
        for name in ('Setup.ps1','WxwQcUpdater.ps1'):
            path=package/'manager'/name
            path.write_text(path.read_text(encoding='utf-8-sig').replace(PRODUCTION_KEY,key),encoding='utf-8-sig')
        env=os.environ.copy();env['LOCALAPPDATA']=str(work/'profile')
        cmd=package/'安装或升级.cmd'
        try:
            code,output=launch(cmd,env)
            assert code==0 and '安装成功' in output,output
            root=work/'profile/WxwQcHelper'
            manifest=json.loads((root/'extension/manifest.json').read_text(encoding='utf-8'))
            expected=json.loads((ROOT/'extension/manifest.json').read_text(encoding='utf-8'))['version']
            assert manifest['version']==expected
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER,key) as opened:
                assert winreg.QueryValueEx(opened,'')[0]==str(root/'native-host.json')
            assert (root/'NativeHost.cmd').exists()
            assert list((work/'profile/WxwQcHelper-Setup').glob('*.txt'))
            # A malformed extraction must report failure, leave window open, and preserve the install.
            (package/'payload/latest.sig').unlink()
            code,output=launch(cmd,env)
            assert code!=0 and '安装未完成' in output and '安装材料缺失' in output,output
            assert json.loads((root/'extension/manifest.json').read_text(encoding='utf-8'))['version']==expected
            print('PASS: shipped CMD stays open on success and failure; signed files, native registration, logs verified; Chinese/spaced path works.')
        finally:
            try:winreg.DeleteKey(winreg.HKEY_CURRENT_USER,key)
            except FileNotFoundError:pass

if __name__=='__main__':main()
