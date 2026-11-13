param([Parameter(Mandatory=$true)][string]$ManifestPath,[Parameter(Mandatory=$true)][string]$SignaturePath,[string]$KeyPath=(Join-Path $env:USERPROFILE '.codex\secrets\wxw-qc-helper\release-signing-key.xml'))
$ErrorActionPreference='Stop'
$rsa=New-Object Security.Cryptography.RSACryptoServiceProvider
$rsa.PersistKeyInCsp=$false
try {
    $rsa.FromXmlString([IO.File]::ReadAllText($KeyPath))
    $signature=$rsa.SignData([IO.File]::ReadAllBytes($ManifestPath),[Security.Cryptography.CryptoConfig]::MapNameToOID('SHA256'))
    [IO.File]::WriteAllText($SignaturePath,[Convert]::ToBase64String($signature),[Text.Encoding]::ASCII)
} finally {$rsa.Dispose()}
