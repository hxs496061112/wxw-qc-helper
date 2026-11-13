# Interactive installer: console output and a persistent result replace modal dialogs.
$ErrorActionPreference='Stop'
$utf8=[Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding=$utf8
$package=Split-Path -Parent $PSScriptRoot
$root=Join-Path $env:LOCALAPPDATA 'WxwQcHelper'
$logDirectory=Join-Path $env:LOCALAPPDATA 'WxwQcHelper-Setup'
$transcribing=$false;$child=$null;$code=1
try {
    [void][IO.Directory]::CreateDirectory($logDirectory)
    $logPath=Join-Path $logDirectory ('install-'+(Get-Date -Format 'yyyyMMdd-HHmmss')+'-'+[guid]::NewGuid().ToString('N')+'.txt')
    Start-Transcript -LiteralPath $logPath -Force | Out-Null
    $transcribing=$true
    Write-Host '旺销王质检放大助手 — 正在安装，请稍候…'
    foreach($file in @('manager/WxwQcUpdater.ps1','manager/trusted-key.xml','payload/latest.json','payload/latest.sig','payload/wxw-qc-update.zip')) {
        if(-not(Test-Path -LiteralPath (Join-Path $package $file) -PathType Leaf)){throw ('安装材料缺失：'+$file+'。请先将 ZIP 全部解压缩。')}
    }
    $start=[Diagnostics.ProcessStartInfo]::new()
    $start.FileName=Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
    $start.Arguments='-NoProfile -ExecutionPolicy Bypass -File "'+(Join-Path $PSScriptRoot 'WxwQcUpdater.ps1')+'" -Mode Install -PayloadDirectory "'+(Join-Path $package 'payload')+'" -NoUI -InstallIntegration'
    $start.UseShellExecute=$false;$start.CreateNoWindow=$true
    $start.RedirectStandardOutput=$true;$start.RedirectStandardError=$true
    $child=[Diagnostics.Process]::Start($start)
    $stdout=$child.StandardOutput.ReadToEndAsync();$stderr=$child.StandardError.ReadToEndAsync()
    if(-not $child.WaitForExit(120000)){$child.Kill();$child.WaitForExit();throw '安装超过两分钟，已停止。请保留当前窗口中的错误信息。'}
    Write-Host $stdout.Result
    if($stderr.Result){Write-Host $stderr.Result}
    if($child.ExitCode -ne 0){throw ('安装程序返回错误码 '+$child.ExitCode+'，详细信息见上方。')}
    # Verify the actual installed files and Edge registration before reporting success.
    $expected=[IO.File]::ReadAllText((Join-Path $package 'payload/latest.json'))|ConvertFrom-Json
    $manifest=[IO.File]::ReadAllText((Join-Path $root 'extension/manifest.json'))|ConvertFrom-Json
    if($manifest.version -ne $expected.version){throw '安装后的版本核对失败。'}
    foreach($file in @('Launch.ps1','NativeHost.cmd','NativeHost.ps1','native-host.json')){
        if(-not(Test-Path -LiteralPath (Join-Path $root $file) -PathType Leaf)){throw ('更新组件缺失：'+$file)}
    }
    $key=[Microsoft.Win32.Registry]::CurrentUser.OpenSubKey('Software\Microsoft\Edge\NativeMessagingHosts\com.wxw.qc.updater')
    if(-not $key){throw 'Edge 更新组件没有注册成功。'}
    try{if($key.GetValue('') -ine (Join-Path $root 'native-host.json')){throw 'Edge 更新组件登记路径不正确。'}}finally{$key.Dispose()}
    Write-Host ''
    Write-Host ('安装成功！版本 '+$manifest.version) -ForegroundColor Green
    Write-Host '下一步：Edge 地址栏打开 edge://extensions/，开启开发人员模式。'
    Write-Host '点击「加载解压缩的扩展」，选择以下文件夹：'
    Write-Host (Join-Path $root 'extension') -ForegroundColor Cyan
    Write-Host '以后在 Edge 点「重新加载」即可检查更新；显示 OK 后刷新扫码页。'
    $code=0
} catch {
    Write-Host ''
    Write-Host '安装未完成。请不要把窗口一闪而过当作成功。' -ForegroundColor Red
    Write-Host $_.Exception.Message -ForegroundColor Red
} finally {
    if($child){$child.Dispose()}
    if($transcribing){
        Write-Host ('安装记录：'+$logPath)
        Stop-Transcript|Out-Null
    }
}
exit $code
