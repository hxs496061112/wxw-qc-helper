[CmdletBinding()]
param(
    [ValidateSet('Install','Update','Rollback','Status')][string]$Mode='Update',
    [string]$PayloadDirectory='',
    [switch]$NoUI,
    [switch]$InstallIntegration,
    [switch]$LibraryOnly
)
$ErrorActionPreference='Stop'
Set-StrictMode -Version 2
$script:Root=[IO.Path]::GetFullPath((Join-Path $env:LOCALAPPDATA 'WxwQcHelper'))
$script:Feed='https://github.com/hxs496061112/wxw-qc-helper/releases/latest/download/'
$script:ReleaseBase='https://github.com/hxs496061112/wxw-qc-helper/releases/download/'
$script:TrustKey=[IO.File]::ReadAllText((Join-Path $PSScriptRoot 'trusted-key.xml'))
$script:Utf8=New-Object Text.UTF8Encoding($false)
$script:Metadata=@('current.json','current.sig','current.zip','install-state.json','last-good.json')
Add-Type -AssemblyName System.IO.Compression
Add-Type -AssemblyName System.IO.Compression.FileSystem

function Safe-Path([string]$Path) {
    $full=[IO.Path]::GetFullPath($Path)
    if(-not $full.StartsWith($script:Root+[IO.Path]::DirectorySeparatorChar,[StringComparison]::OrdinalIgnoreCase)) {throw '路径超出助手安装目录，操作已停止。'}
    $cursor=$full
    while($cursor.Length -ge $script:Root.Length) {
        if(Test-Path -LiteralPath $cursor) {
            if(((Get-Item -LiteralPath $cursor -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0){throw '安装目录包含链接或重定向，操作已停止。'}
        }
        if($cursor -eq $script:Root){break}
        $cursor=[IO.Path]::GetDirectoryName($cursor)
    }
    return $full
}
function Remove-Managed([string]$Path) {
    $safe=Safe-Path $Path
    if(Test-Path -LiteralPath $safe) {
        $links=Get-ChildItem -LiteralPath $safe -Recurse -Force -ErrorAction Stop | Where-Object {($_.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0}
        if($links){throw '待清理目录含链接，已停止清理。'}
        Remove-Item -LiteralPath $safe -Recurse -Force
    }
}
function Save-Json([string]$Path,$Value) {
    $safe=Safe-Path $Path
    $temp=$safe+'.tmp'
    [IO.File]::WriteAllText($temp,($Value|ConvertTo-Json -Depth 12),$script:Utf8)
    Move-Item -LiteralPath $temp -Destination $safe -Force
}
function Read-Json([string]$Path) {return ([IO.File]::ReadAllText($Path)|ConvertFrom-Json)}
function Initialize-Root {
    if([IO.Path]::GetFileName($script:Root) -ne 'WxwQcHelper'){throw '无效安装路径。'}
    [void](Safe-Path (Join-Path $script:Root 'extension'))
    $marker=Join-Path $script:Root '.wxw-qc-install'
    if(Test-Path -LiteralPath $marker) {
        if([IO.File]::ReadAllText($marker) -ne 'wxw-qc-helper-v1'){throw '安装标记不匹配。'}
    } else {
        if((Test-Path -LiteralPath $script:Root) -and @(Get-ChildItem -LiteralPath $script:Root -Force).Count){throw '目标文件夹已有其他文件，未覆盖。'}
        [void][IO.Directory]::CreateDirectory($script:Root)
        [IO.File]::WriteAllText($marker,'wxw-qc-helper-v1')
    }
}
function Download-Bytes([string]$Url,[int]$MaxBytes) {
    if(-not ($Url.StartsWith($script:Feed,[StringComparison]::Ordinal) -or $Url.StartsWith($script:ReleaseBase,[StringComparison]::Ordinal))){throw '更新地址不在已配置仓库内。'}
    [Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12
    $request=[Net.HttpWebRequest]::Create($Url)
    $request.UserAgent='WxwQcHelper-Updater/1.0'
    $request.Timeout=30000;$request.ReadWriteTimeout=30000
    $request.AllowAutoRedirect=$true;$request.MaximumAutomaticRedirections=5
    $request.Headers['Cache-Control']='no-cache'
    $response=$null;$stream=$null;$memory=$null
    try {
        $response=$request.GetResponse()
        if($response.ResponseUri.Scheme -ne 'https'){throw '更新下载没有使用HTTPS。'}
        if($response.ContentLength -gt $MaxBytes){throw '更新文件超出大小上限。'}
        $stream=$response.GetResponseStream();$memory=New-Object IO.MemoryStream
        $buffer=New-Object byte[] 8192
        while(($read=$stream.Read($buffer,0,$buffer.Length)) -gt 0) {
            if($memory.Length+$read -gt $MaxBytes){throw '更新文件超出大小上限。'}
            $memory.Write($buffer,0,$read)
        }
        return ,$memory.ToArray()
    } finally {if($stream){$stream.Dispose()};if($response){$response.Dispose()};if($memory){$memory.Dispose()}}
}
function Verify-Release([byte[]]$Json,[byte[]]$Signature) {
    $rsa=New-Object Security.Cryptography.RSACryptoServiceProvider
    $rsa.PersistKeyInCsp=$false
    try {
        $rsa.FromXmlString($script:TrustKey)
        $sig=[Convert]::FromBase64String([Text.Encoding]::ASCII.GetString($Signature).Trim())
        if(-not $rsa.VerifyData($Json,[Security.Cryptography.CryptoConfig]::MapNameToOID('SHA256'),$sig)){throw '发布签名不正确，旧版本未修改。'}
    } finally {$rsa.Dispose()}
    $info=([Text.Encoding]::UTF8.GetString($Json)|ConvertFrom-Json)
    if($info.schema -ne 1 -or $info.product -ne 'wxw-qc-helper' -or $info.version -notmatch '^\d+\.\d+\.\d+(\.\d+)?$'){throw '版本清单格式不正确。'}
    [void][version]$info.version
    $expected=$script:ReleaseBase+'v'+$info.version+'/wxw-qc-update.zip'
    if($info.url -cne $expected -or $info.sha256 -notmatch '^[a-f0-9]{64}$'){throw '版本清单下载地址或校验码异常。'}
    $names=@($info.files.PSObject.Properties.Name)
    if($names.Count -lt 6 -or $names.Count -gt 64 -or ($names|Sort-Object -Unique).Count -ne $names.Count){throw '更新文件列表异常。'}
    foreach($name in $names){
        if($name -cnotmatch '^(extension|manager)/[A-Za-z0-9][A-Za-z0-9._-]*$'){throw '更新包包含不允许的路径。'}
        if($info.files.$name -notmatch '^[a-f0-9]{64}$'){throw '文件校验码异常。'}
    }
    foreach($required in @('extension/manifest.json','extension/content.js','extension/layout.css','extension/popup.html','extension/popup.js','extension/popup.css','manager/WxwQcUpdater.ps1','manager/Launch.ps1','manager/trusted-key.xml')){
        if($names -cnotcontains $required){throw '更新包缺少必要文件。'}
    }
    return $info
}
function Hash-Bytes([byte[]]$Bytes) {
    $hash=[Security.Cryptography.SHA256]::Create()
    try{return ([BitConverter]::ToString($hash.ComputeHash($Bytes))).Replace('-','').ToLowerInvariant()}finally{$hash.Dispose()}
}
function Test-Files([string]$Directory,$Info) {
    foreach($property in $Info.files.PSObject.Properties) {
        $path=Join-Path $Directory $property.Name
        if(-not (Test-Path -LiteralPath $path -PathType Leaf)){return $false}
        if((Hash-Bytes ([IO.File]::ReadAllBytes($path))) -cne $property.Value){return $false}
    }
    return $true
}
function Expand-Verified([byte[]]$Archive,$Info,[string]$Stage) {
    if((Hash-Bytes $Archive) -cne $Info.sha256){throw '安装包校验失败，旧版本未修改。'}
    [void](Safe-Path $Stage)
    [void][IO.Directory]::CreateDirectory($Stage)
    $memory=[IO.MemoryStream]::new($Archive,$false)
    $zip=[IO.Compression.ZipArchive]::new($memory,[IO.Compression.ZipArchiveMode]::Read)
    try {
        $expected=@($Info.files.PSObject.Properties.Name);$seen=@{};$total=0L
        foreach($entry in $zip.Entries) {
            $name=$entry.FullName
            if($expected -cnotcontains $name -or $seen.ContainsKey($name)){throw '安装包文件列表不匹配。'}
            $seen[$name]=$true;$total+=$entry.Length
            if($entry.Length -gt 2097152 -or $total -gt 8388608){throw '解压文件超出大小上限。'}
            $target=Safe-Path (Join-Path $Stage $name)
            [void][IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($target))
            [IO.Compression.ZipFileExtensions]::ExtractToFile($entry,$target,$false)
        }
        if($seen.Count -ne $expected.Count){throw '安装包文件不完整。'}
    } finally {$zip.Dispose();$memory.Dispose()}
    if(-not (Test-Files $Stage $Info)){throw '解压后校验失败，旧版本未修改。'}
    if([IO.File]::ReadAllText((Join-Path $Stage 'manager/trusted-key.xml')) -cne $script:TrustKey){throw '更新包意外更换了验证公钥。'}
    $manifest=Read-Json (Join-Path $Stage 'extension/manifest.json')
    if($manifest.version -ne $Info.version -or $manifest.manifest_version -ne 3){throw '扩展版本与发布版本不一致。'}
    foreach($entry in $manifest.content_scripts){
        foreach($match in $entry.matches){if($match -cne 'https://v3.wxwerp.com/*'){throw '更新包的站点访问范围不符合预期。'}}
    }
}
function Recover-Pending {
    $journalPath=Join-Path $script:Root 'pending-update.json'
    if(-not (Test-Path -LiteralPath $journalPath)){return}
    $journal=Read-Json $journalPath
    $backup=Safe-Path (Join-Path $script:Root $journal.backup)
    foreach($name in @('extension','manager')) {
        $saved=Safe-Path (Join-Path $backup $name);$target=Safe-Path (Join-Path $script:Root $name)
        if(Test-Path -LiteralPath $saved){Remove-Managed $target;Move-Item -LiteralPath $saved -Destination $target}
        elseif(-not $journal.had.$name){Remove-Managed $target}
    }
    foreach($name in $script:Metadata) {
        $saved=Join-Path $backup $name;$target=Safe-Path (Join-Path $script:Root $name)
        if(Test-Path -LiteralPath $saved){Copy-Item -LiteralPath $saved -Destination $target -Force}
        elseif($journal.metadata -notcontains $name){if(Test-Path -LiteralPath $target){Remove-Item -LiteralPath $target -Force}}
    }
    Remove-Item -LiteralPath (Safe-Path $journalPath) -Force
    Write-Host '已恢复上次未完成更新前的版本。'
}
function Apply-Bundle([byte[]]$Archive,[byte[]]$Json,[byte[]]$Signature,$Info) {
    $stage=Safe-Path (Join-Path $script:Root ('.stage-'+[guid]::NewGuid().ToString('N')))
    try {
        Expand-Verified $Archive $Info $stage
        $backupRelative='backups/'+(Get-Date -Format 'yyyyMMdd-HHmmss')+'-'+[guid]::NewGuid().ToString('N')
        $backup=Safe-Path (Join-Path $script:Root $backupRelative)
        [void][IO.Directory]::CreateDirectory($backup)
        $had=@{};$existing=@()
        foreach($name in @('extension','manager')){$had[$name]=Test-Path -LiteralPath (Join-Path $script:Root $name)}
        foreach($name in $script:Metadata){
            $path=Join-Path $script:Root $name
            if(Test-Path -LiteralPath $path){$existing+=$name;Copy-Item -LiteralPath $path -Destination (Join-Path $backup $name)}
        }
        Save-Json (Join-Path $script:Root 'pending-update.json') @{backup=$backupRelative;had=$had;metadata=$existing}
        try {
            foreach($name in @('extension','manager')) {
                $target=Safe-Path (Join-Path $script:Root $name)
                if($had[$name]){Move-Item -LiteralPath $target -Destination (Safe-Path (Join-Path $backup $name))}
                Move-Item -LiteralPath (Safe-Path (Join-Path $stage $name)) -Destination $target
            }
            [IO.File]::WriteAllBytes((Safe-Path (Join-Path $script:Root 'current.zip')),$Archive)
            [IO.File]::WriteAllBytes((Safe-Path (Join-Path $script:Root 'current.json')),$Json)
            [IO.File]::WriteAllBytes((Safe-Path (Join-Path $script:Root 'current.sig')),$Signature)
            Save-Json (Join-Path $script:Root 'install-state.json') @{product='wxw-qc-helper';version=$Info.version;installedAt=(Get-Date).ToString('o')}
            $launcher=Safe-Path (Join-Path $script:Root 'Launch.ps1')
            if(-not (Test-Path -LiteralPath $launcher)){
                Copy-Item -LiteralPath (Join-Path $script:Root 'manager/Launch.ps1') -Destination $launcher
            }
            if($existing -contains 'current.zip'){Save-Json (Join-Path $script:Root 'last-good.json') @{backup=$backupRelative}}
            Remove-Item -LiteralPath (Safe-Path (Join-Path $script:Root 'pending-update.json')) -Force
        } catch {Recover-Pending;throw}
    } finally {Remove-Managed $stage}
}
function Remove-LegacyShortcuts([string]$DesktopDirectory=[Environment]::GetFolderPath('Desktop')) {
    $shell=New-Object -ComObject WScript.Shell
    try {
        foreach($item in @(@('旺销王助手在线更新','Update'),@('旺销王助手回退上一版','Rollback'))) {
            $path=Join-Path $DesktopDirectory ($item[0]+'.lnk')
            if(-not (Test-Path -LiteralPath $path -PathType Leaf)){continue}
            $shortcut=$shell.CreateShortcut($path)
            try {
                $target=Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
                $expected=@('Launch.ps1','manager\WxwQcUpdater.ps1') | ForEach-Object {
                    '-NoProfile -ExecutionPolicy Bypass -File "'+(Join-Path $script:Root $_)+'" -Mode '+$item[1]
                }
                if($shortcut.TargetPath -ieq $target -and $shortcut.WorkingDirectory -ieq $script:Root -and $expected -icontains $shortcut.Arguments) {
                    Remove-Item -LiteralPath $path -Force
                }
            } finally {[Runtime.InteropServices.Marshal]::ReleaseComObject($shortcut)|Out-Null}
        }
    } finally {[Runtime.InteropServices.Marshal]::ReleaseComObject($shell)|Out-Null}
}
function Finish-Integration {
    if($Mode -eq 'Install' -and ($InstallIntegration -or -not $NoUI)){Register-NativeHost}
    try{Remove-LegacyShortcuts}catch{Write-Host '旧桌面快捷方式未能清理，可手动删除；不影响 Edge 更新。'}
}
function Register-NativeHost {
    foreach($name in @('NativeHost.cmd','NativeHost.ps1')){
        Copy-Item -LiteralPath (Join-Path $script:Root ('manager/'+$name)) -Destination (Safe-Path (Join-Path $script:Root $name)) -Force
    }
    $manifestPath=Safe-Path (Join-Path $script:Root 'native-host.json')
    Save-Json $manifestPath @{name='com.wxw.qc.updater';description='Wxw QC signed updater';path=(Join-Path $script:Root 'NativeHost.cmd');type='stdio';allowed_origins=@('chrome-extension://hldbbmhhmgjcfmlbkglekcigjkbefobe/')}
    $key=[Microsoft.Win32.Registry]::CurrentUser.CreateSubKey('Software\Microsoft\Edge\NativeMessagingHosts\com.wxw.qc.updater')
    try{$key.SetValue('',$manifestPath,[Microsoft.Win32.RegistryValueKind]::String)}finally{$key.Dispose()}
}
function Notify-Result([string]$Text,[bool]$Failed=$false) {
    Write-Host $Text
    if(-not $NoUI){
        Add-Type -AssemblyName System.Windows.Forms
        $icon=if($Failed){[Windows.Forms.MessageBoxIcon]::Warning}else{[Windows.Forms.MessageBoxIcon]::Information}
        [Windows.Forms.MessageBox]::Show($Text,'旺销王质检放大助手',[Windows.Forms.MessageBoxButtons]::OK,$icon)|Out-Null
    }
}
if($LibraryOnly){return}
$lock=$null
try {
    Initialize-Root
    try{$lock=[IO.File]::Open((Safe-Path (Join-Path $script:Root 'update.lock')),[IO.FileMode]::OpenOrCreate,[IO.FileAccess]::ReadWrite,[IO.FileShare]::None)}catch{throw '已有一个安装或更新程序正在运行，请等它完成。'}
    Recover-Pending
    if($Mode -eq 'Status') {
        $state=Join-Path $script:Root 'install-state.json'
        if(Test-Path -LiteralPath $state){Write-Output ([IO.File]::ReadAllText($state))}else{Write-Output '尚未安装。'}
        return
    }
    if($Mode -eq 'Install'){
        if(-not $PayloadDirectory){throw '缺少离线安装文件，请先完整解压安装包。'}
        $json=[IO.File]::ReadAllBytes((Join-Path $PayloadDirectory 'latest.json'))
        $sig=[IO.File]::ReadAllBytes((Join-Path $PayloadDirectory 'latest.sig'))
    } elseif($Mode -eq 'Rollback') {
        $last=Join-Path $script:Root 'last-good.json'
        if(-not (Test-Path -LiteralPath $last)){throw '尚无可回退的上一版本。'}
        $saved=Safe-Path (Join-Path $script:Root (Read-Json $last).backup)
        $json=[IO.File]::ReadAllBytes((Join-Path $saved 'current.json'))
        $sig=[IO.File]::ReadAllBytes((Join-Path $saved 'current.sig'))
    } else {
        Write-Host '正在检查线上版本，请稍候……'
        $json=Download-Bytes ($script:Feed+'latest.json') 262144
        $sig=Download-Bytes ($script:Feed+'latest.sig') 8192
    }
    $info=Verify-Release $json $sig
    $currentVersion=[version]'0.0.0'
    $installed=Join-Path $script:Root 'extension\manifest.json'
    if(Test-Path -LiteralPath $installed){$currentVersion=[version](Read-Json $installed).version}
    if($Mode -ne 'Rollback' -and [version]$info.version -lt $currentVersion){throw '线上版本低于本机版本，未执行降级。'}
    if($Mode -ne 'Rollback' -and [version]$info.version -eq $currentVersion -and (Test-Files $script:Root $info)){
        Finish-Integration
        Notify-Result ('本机文件已是最新版本 '+$info.version+'。以后直接在 Edge 点「重新加载」检查更新，成功后刷新扫码页。')
        return
    }
    Write-Host ('正在校验并安装版本 '+$info.version+'……')
    if($Mode -eq 'Install'){$archive=[IO.File]::ReadAllBytes((Join-Path $PayloadDirectory 'wxw-qc-update.zip'))}
    elseif($Mode -eq 'Rollback'){$archive=[IO.File]::ReadAllBytes((Join-Path $saved 'current.zip'))}
    else {$archive=Download-Bytes $info.url 8388608}
    Apply-Bundle $archive $json $sig $info
    if($Mode -eq 'Rollback'){Save-Json (Join-Path $script:Root 'skip-online-once.json') @{version=$info.version}}
    Finish-Integration
    if($Mode -eq 'Install') {
        $text="安装文件已准备好，版本 $($info.version)。`r`n`r`n首次：在 Edge 扩展管理页开启开发人员模式，加载以下文件夹：`r`n$(Join-Path $script:Root 'extension')`r`n`r`n已加载这个目录的，无需重新添加。`r`n以后直接在 Edge 点「重新加载」，等待助手图标显示 OK，再刷新扫码页。"
    } else {
        $text="本机文件已更新至 $($info.version)。`r`n`r`n通过 Edge 发起的更新会自动加载新版。等待助手图标显示 OK，再刷新旺销王扫码页。`r`n无需删除扩展或重新添加。"
    }
    Notify-Result $text
} catch {
    Notify-Result ("操作未完成："+$_.Exception.Message+"`r`n请检查网络或联系维护人员，勿删除原扩展目录。") $true
    exit 1
} finally {if($lock){$lock.Dispose()}}
