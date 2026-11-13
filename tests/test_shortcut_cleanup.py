"""Verify cleanup with real Windows shortcuts in an isolated fake desktop."""
from pathlib import Path
import os
import subprocess
import tempfile

ROOT=Path(__file__).resolve().parents[1]
PS=Path(os.environ['SystemRoot'])/'System32/WindowsPowerShell/v1.0/powershell.exe'
with tempfile.TemporaryDirectory(prefix='wxw-shortcuts-') as folder:
    temp=Path(folder)
    script=temp/'test.ps1'
    script.write_text(r'''
param($Runner,$Desktop)
. $Runner -LibraryOnly -NoUI
[void][IO.Directory]::CreateDirectory($Desktop)
$shell=New-Object -ComObject WScript.Shell
$ours=Join-Path $Desktop '旺销王助手在线更新.lnk'
$other=Join-Path $Desktop '旺销王助手回退上一版.lnk'
$a=$shell.CreateShortcut($ours)
$a.TargetPath=Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
$a.Arguments='-NoProfile -ExecutionPolicy Bypass -File "'+(Join-Path $script:Root 'Launch.ps1')+'" -Mode Update'
$a.WorkingDirectory=$script:Root;$a.Save()
$b=$shell.CreateShortcut($other)
$b.TargetPath=Join-Path $env:SystemRoot 'System32\notepad.exe';$b.Save()
[IO.File]::WriteAllText((Join-Path $Desktop 'other.txt'),'keep')
Remove-LegacyShortcuts $Desktop
if(Test-Path -LiteralPath $ours){throw 'Owned shortcut not cleaned'}
if(-not(Test-Path -LiteralPath $other)){throw 'Unrelated shortcut removed'}
if([IO.File]::ReadAllText((Join-Path $Desktop 'other.txt')) -ne 'keep'){throw 'Unrelated file changed'}
Remove-LegacyShortcuts $Desktop
Write-Output 'PASS: owned shortcut removed, unrelated shortcut and file preserved, repeat safe.'
''',encoding='utf-8-sig')
    env=os.environ.copy();env['LOCALAPPDATA']=str(temp/'profile')
    result=subprocess.run([str(PS),'-NoProfile','-ExecutionPolicy','Bypass','-File',str(script),str(ROOT/'manager/WxwQcUpdater.ps1'),str(temp/'desktop')],env=env,capture_output=True,timeout=30)
    assert result.returncode==0,(result.stdout+result.stderr).decode('gb18030',errors='replace')
    print(result.stdout.decode('gb18030',errors='replace'))
