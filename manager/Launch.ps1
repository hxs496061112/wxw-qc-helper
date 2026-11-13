param([ValidateSet('Update','Rollback','Status')][string]$Mode='Update',[switch]$NoUI)
$ErrorActionPreference='Stop'
# This stable entry point remains outside the two directories replaced by an update.
$root=[IO.Path]::GetFullPath($PSScriptRoot)
$runner=Join-Path $root 'manager\WxwQcUpdater.ps1'
if(-not (Test-Path -LiteralPath $runner)) {
    $journalPath=Join-Path $root 'pending-update.json'
    if(Test-Path -LiteralPath $journalPath) {
        $journal=[IO.File]::ReadAllText($journalPath)|ConvertFrom-Json
        if($journal.backup -notmatch '^backups/[0-9]{8}-[0-9]{6}-[a-f0-9]{32}$'){throw 'Invalid recovery path.'}
        $runner=Join-Path $root ($journal.backup+'/manager/WxwQcUpdater.ps1')
    }
}
if(-not (Test-Path -LiteralPath $runner)){throw 'Updater missing. Please run the original installer again.'}
& $runner -Mode $Mode -NoUI:$NoUI
