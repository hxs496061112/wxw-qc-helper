from pathlib import Path
import base64
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import unittest
import zipfile

ROOT=Path(__file__).resolve().parents[1]
PS=Path(os.environ['SystemRoot'])/'System32/WindowsPowerShell/v1.0/powershell.exe'

class UpdaterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory(prefix='wxw-update-tests-')
        cls.work=Path(cls.temp.name)
        cls.manager=cls.work/'runner';cls.manager.mkdir()
        shutil.copy2(ROOT/'manager/WxwQcUpdater.ps1',cls.manager/'WxwQcUpdater.ps1')
        cls.key=cls.work/'test-private.xml'
        generator=cls.work/'make-key.ps1'
        generator.write_text("$r=New-Object Security.Cryptography.RSACryptoServiceProvider(2048);$r.PersistKeyInCsp=$false;[IO.File]::WriteAllText($args[0],$r.ToXmlString($true));[IO.File]::WriteAllText($args[1],$r.ToXmlString($false));$r.Dispose()",encoding='utf-8-sig')
        subprocess.run([str(PS),'-NoProfile','-ExecutionPolicy','Bypass','-File',str(generator),str(cls.key),str(cls.manager/'trusted-key.xml')],check=True,capture_output=True)
        cls.v50=cls.make_bundle('0.5.0')
        cls.v51=cls.make_bundle('0.5.1')

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    @classmethod
    def make_bundle(cls,version,extra_path=None):
        payload=cls.work/('payload-'+version+('-unsafe' if extra_path else ''));payload.mkdir()
        files={p.relative_to(ROOT).as_posix():p.read_bytes() for folder in ('extension','manager') for p in (ROOT/folder).iterdir() if p.is_file()}
        files['manager/trusted-key.xml']=(cls.manager/'trusted-key.xml').read_bytes()
        manifest=json.loads(files['extension/manifest.json'])
        manifest['version']=version
        files['extension/manifest.json']=json.dumps(manifest,ensure_ascii=False).encode()
        if extra_path:files[extra_path]=b'unsafe'
        archive=payload/'wxw-qc-update.zip'
        with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
            for name,data in files.items():z.writestr(name,data)
        info={'schema':1,'product':'wxw-qc-helper','version':version,
              'url':f'https://github.com/hxs496061112/wxw-qc-helper/releases/download/v{version}/wxw-qc-update.zip',
              'sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),
              'files':{name:hashlib.sha256(data).hexdigest() for name,data in files.items()}}
        (payload/'latest.json').write_text(json.dumps(info),encoding='utf-8')
        subprocess.run([str(PS),'-NoProfile','-ExecutionPolicy','Bypass','-File',str(ROOT/'scripts/Sign-Release.ps1'),'-ManifestPath',str(payload/'latest.json'),'-SignaturePath',str(payload/'latest.sig'),'-KeyPath',str(cls.key)],check=True,capture_output=True)
        return payload

    def setUp(self):
        self.profile=self.work/self._testMethodName;self.profile.mkdir()
        self.env=os.environ.copy();self.env['LOCALAPPDATA']=str(self.profile)
        self.installed=self.profile/'WxwQcHelper'

    def run_updater(self,mode='Install',payload=None,success=True,production=False):
        manager=(ROOT/'manager') if production else self.manager
        args=[str(PS),'-NoProfile','-ExecutionPolicy','Bypass','-File',str(manager/'WxwQcUpdater.ps1'),'-Mode',mode,'-NoUI']
        if payload:args+=['-PayloadDirectory',str(payload)]
        r=subprocess.run(args,env=self.env,capture_output=True,timeout=60)
        if success:self.assertEqual(r.returncode,0,r.stdout.decode(errors='replace')+r.stderr.decode(errors='replace'))
        else:self.assertNotEqual(r.returncode,0)
        return r

    def installed_version(self):
        return json.loads((self.installed/'extension/manifest.json').read_text(encoding='utf-8-sig'))['version']

    def test_production_offline_installer(self):
        self.run_updater(payload=ROOT/'dist',production=True)
        self.assertEqual(self.installed_version(),json.loads((ROOT/'extension/manifest.json').read_text(encoding='utf-8'))['version'])
        self.assertEqual((self.installed/'extension/content.js').read_bytes(),(ROOT/'extension/content.js').read_bytes())
        before=len(list((self.installed/'backups').iterdir()))
        self.run_updater(payload=ROOT/'dist',production=True)
        self.assertEqual(len(list((self.installed/'backups').iterdir())),before)

    def test_upgrade_and_explicit_rollback(self):
        self.run_updater(payload=self.v50)
        self.run_updater(payload=self.v51)
        self.assertEqual(self.installed_version(),'0.5.1')
        self.run_updater(payload=self.v50,success=False)
        self.assertEqual(self.installed_version(),'0.5.1')
        self.run_updater(mode='Rollback')
        self.assertEqual(self.installed_version(),'0.5.0')

    def test_corrupt_signature_and_archive_keep_old(self):
        self.run_updater(payload=self.v50)
        payload=self.profile/'bad';shutil.copytree(self.v51,payload)
        original=(payload/'latest.json').read_bytes()
        (payload/'latest.json').write_bytes(original+b' ')
        self.run_updater(payload=payload,success=False)
        self.assertEqual(self.installed_version(),'0.5.0')
        (payload/'latest.json').write_bytes(original)
        with (payload/'wxw-qc-update.zip').open('ab') as f:f.write(b'corrupt')
        self.run_updater(payload=payload,success=False)
        self.assertEqual(self.installed_version(),'0.5.0')

    def test_signed_unsafe_path_rejected(self):
        payload=self.make_bundle('0.5.2','extension/../../outside.txt')
        self.run_updater(payload=payload,success=False)
        self.assertFalse((self.profile/'outside.txt').exists())
        self.assertFalse((self.installed/'extension').exists())

    def test_unknown_existing_directory_untouched(self):
        self.installed.mkdir();sentinel=self.installed/'user-file.txt';sentinel.write_text('keep')
        self.run_updater(payload=self.v50,success=False)
        self.assertEqual(sentinel.read_text(),'keep')

    def failure_script(self,crash=False):
        script=self.profile/'simulate.ps1'
        failure='[Environment]::Exit(99)' if crash else "throw 'synthetic move failure'"
        code=r'''
param($Runner,$Payload)
. $Runner -LibraryOnly -NoUI
Initialize-Root
$j=[IO.File]::ReadAllBytes((Join-Path $Payload 'latest.json'))
$s=[IO.File]::ReadAllBytes((Join-Path $Payload 'latest.sig'))
$a=[IO.File]::ReadAllBytes((Join-Path $Payload 'wxw-qc-update.zip'))
$info=Verify-Release $j $s
$script:FailOnce=$true
function Move-Item {
 param([string]$LiteralPath,[string]$Destination,[switch]$Force)
 if($script:FailOnce -and $LiteralPath -like '*\.stage-*\manager'){$script:FailOnce=$false;FAILURE}
 Microsoft.PowerShell.Management\Move-Item -LiteralPath $LiteralPath -Destination $Destination -Force:$Force
}
try {Apply-Bundle $a $j $s $info;throw 'expected failure did not occur'}catch{Write-Output $_.Exception.Message}
'''.replace('FAILURE',failure)
        script.write_text(code,encoding='utf-8-sig')
        return script

    def test_replace_failure_restores_old(self):
        self.run_updater(payload=self.v50)
        r=subprocess.run([str(PS),'-NoProfile','-ExecutionPolicy','Bypass','-File',str(self.failure_script()),str(self.manager/'WxwQcUpdater.ps1'),str(self.v51)],env=self.env,capture_output=True,timeout=60)
        self.assertEqual(r.returncode,0,r.stderr.decode(errors='replace'))
        self.assertEqual(self.installed_version(),'0.5.0')
        self.assertFalse((self.installed/'pending-update.json').exists())

    def test_process_interruption_recovers_on_next_run(self):
        self.run_updater(payload=self.v50)
        r=subprocess.run([str(PS),'-NoProfile','-ExecutionPolicy','Bypass','-File',str(self.failure_script(crash=True)),str(self.manager/'WxwQcUpdater.ps1'),str(self.v51)],env=self.env,capture_output=True,timeout=60)
        self.assertEqual(r.returncode,99,r.stdout.decode(errors='replace')+r.stderr.decode(errors='replace'))
        self.assertTrue((self.installed/'pending-update.json').exists())
        # Exercise the actual desktop entry point while manager/ is absent.
        self.assertFalse((self.installed/'manager').exists())
        r=subprocess.run([str(PS),'-NoProfile','-ExecutionPolicy','Bypass','-File',str(self.installed/'Launch.ps1'),'-Mode','Status','-NoUI'],env=self.env,capture_output=True,timeout=60)
        self.assertEqual(r.returncode,0,r.stderr.decode(errors='replace'))
        self.assertEqual(self.installed_version(),'0.5.0')
        self.assertFalse((self.installed/'pending-update.json').exists())

if __name__=='__main__':unittest.main(verbosity=2)
