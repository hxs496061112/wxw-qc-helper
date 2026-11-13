$ErrorActionPreference='Stop'
$inputStream=[Console]::OpenStandardInput()
$outputStream=[Console]::OpenStandardOutput()
function Read-Exact([int]$Count){
    $bytes=New-Object byte[] $Count;$offset=0
    while($offset -lt $Count){$n=$inputStream.Read($bytes,$offset,$Count-$offset);if($n -le 0){throw 'Incomplete input'};$offset+=$n}
    return ,$bytes
}
$child=$null
try{
    $length=[BitConverter]::ToInt32((Read-Exact 4),0)
    if($length -lt 1 -or $length -gt 4096){throw 'Invalid message length'}
    $message=[Text.Encoding]::UTF8.GetString((Read-Exact $length))|ConvertFrom-Json
    if($message.action -cne 'update'){throw 'Unsupported action'}
    $skipPath=Join-Path $PSScriptRoot 'skip-online-once.json'
    $skip=Test-Path -LiteralPath $skipPath
    if($skip){Remove-Item -LiteralPath $skipPath -Force}
    else {
    $start=New-Object Diagnostics.ProcessStartInfo
    $start.FileName=Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
    $start.Arguments='-NoProfile -ExecutionPolicy Bypass -File "'+(Join-Path $PSScriptRoot 'Launch.ps1')+'" -Mode Update -NoUI'
    $start.UseShellExecute=$false;$start.CreateNoWindow=$true
    $start.RedirectStandardOutput=$true;$start.RedirectStandardError=$true
    $child=[Diagnostics.Process]::Start($start)
    $stdout=$child.StandardOutput.ReadToEndAsync();$stderr=$child.StandardError.ReadToEndAsync()
    if(-not $child.WaitForExit(120000)){$child.Kill();$child.WaitForExit();throw 'Update timed out'}
    if($child.ExitCode -ne 0){throw 'Update failed'}
    }
    $manifest=[IO.File]::ReadAllText((Join-Path $PSScriptRoot 'extension\manifest.json'))|ConvertFrom-Json
    $result=@{ok=$true;version=$manifest.version;skipped=$skip}
}catch{$result=@{ok=$false;error='Update unavailable; current extension preserved.'}}
finally{if($child){$child.Dispose()}}
$bytes=[Text.Encoding]::UTF8.GetBytes(($result|ConvertTo-Json -Compress))
$header=[BitConverter]::GetBytes([int]$bytes.Length)
$outputStream.Write($header,0,4);$outputStream.Write($bytes,0,$bytes.Length);$outputStream.Flush()
