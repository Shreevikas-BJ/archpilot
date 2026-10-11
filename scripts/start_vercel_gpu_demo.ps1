param(
    [string]$CloudflaredPath = ".demo\tools\cloudflared.exe",
    [switch]$Build
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$DemoDir = Join-Path $Root ".demo"
$TokenPath = Join-Path $DemoDir "vercel-proxy-token"
$FrontendEnv = Join-Path $Root "frontend\.env.local"
$Cloudflared = [System.IO.Path]::GetFullPath((Join-Path $Root $CloudflaredPath))

if (!(Test-Path -LiteralPath $Cloudflared)) {
    throw "cloudflared was not found at $Cloudflared. Download the official Windows binary there or pass -CloudflaredPath."
}

New-Item -ItemType Directory -Force -Path $DemoDir | Out-Null
if (Test-Path -LiteralPath $TokenPath) {
    $ProxyToken = (Get-Content -LiteralPath $TokenPath -Raw).Trim()
} else {
    $Bytes = New-Object byte[] 48
    $Generator = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try { $Generator.GetBytes($Bytes) } finally { $Generator.Dispose() }
    $ProxyToken = [Convert]::ToBase64String($Bytes).TrimEnd('=').Replace('+', '-').Replace('/', '_')
    Set-Content -LiteralPath $TokenPath -Value $ProxyToken -NoNewline
}
if (!$ProxyToken) { throw "The proxy token is empty." }

function Set-LocalEnvValue([string]$Path, [string]$Key, [string]$Value) {
    $Lines = if (Test-Path -LiteralPath $Path) { @(Get-Content -LiteralPath $Path) } else { @() }
    $Replacement = "$Key=$Value"
    $Found = $false
    $Updated = foreach ($Line in $Lines) {
        if ($Line -match "^$([regex]::Escape($Key))=") {
            $Found = $true
            $Replacement
        } else {
            $Line
        }
    }
    if (!$Found) { $Updated += $Replacement }
    Set-Content -LiteralPath $Path -Value $Updated
}

Set-LocalEnvValue $FrontendEnv "BACKEND_API_URL" "http://127.0.0.1:8000"
Set-LocalEnvValue $FrontendEnv "BACKEND_TIMEOUT_SECONDS" "3600"
Set-LocalEnvValue $FrontendEnv "ARCHPILOT_PROXY_TOKEN" $ProxyToken
$env:ARCHPILOT_PROXY_TOKEN = $ProxyToken

$Python = Join-Path $Root "backend\.venv\Scripts\python.exe"
if (!(Test-Path -LiteralPath $Python)) { throw "Backend virtual environment is missing. See README.md." }
$StartArgs = @((Join-Path $PSScriptRoot "start_demo.py"))
if ($Build) { $StartArgs += "--build" }
& $Python @StartArgs
if ($LASTEXITCODE -ne 0) { throw "The local ArchPilot stack did not start." }

$Stdout = Join-Path $DemoDir "cloudflared.stdout.log"
$Stderr = Join-Path $DemoDir "cloudflared.stderr.log"
Remove-Item -LiteralPath $Stdout, $Stderr -Force -ErrorAction SilentlyContinue
$Tunnel = Start-Process -FilePath $Cloudflared `
    -ArgumentList @("tunnel", "--url", "http://127.0.0.1:8000", "--no-autoupdate") `
    -WorkingDirectory $Root -WindowStyle Hidden -PassThru `
    -RedirectStandardOutput $Stdout -RedirectStandardError $Stderr

$Deadline = (Get-Date).AddSeconds(45)
$TunnelUrl = $null
while ((Get-Date) -lt $Deadline -and !$Tunnel.HasExited) {
    Start-Sleep -Milliseconds 500
    $Log = ((Get-Content -LiteralPath $Stdout, $Stderr -Raw -ErrorAction SilentlyContinue) -join "`n")
    $Match = [regex]::Match($Log, 'https://[a-z0-9-]+\.trycloudflare\.com')
    if ($Match.Success) { $TunnelUrl = $Match.Value; break }
}
if (!$TunnelUrl) {
    if (!$Tunnel.HasExited) { Stop-Process -Id $Tunnel.Id }
    throw "The Cloudflare quick tunnel did not publish a URL. Check $Stderr."
}

$Headers = @{ "X-ArchPilot-Proxy-Token" = $ProxyToken }
$Health = $null
$HealthDeadline = (Get-Date).AddSeconds(60)
while ((Get-Date) -lt $HealthDeadline -and !$Tunnel.HasExited) {
    try {
        $Health = Invoke-RestMethod -Uri "$TunnelUrl/v1/health" -Headers $Headers -TimeoutSec 10
        if ($Health.status -eq "ok" -and $Health.database -eq "ok") { break }
    } catch {
        Start-Sleep -Seconds 2
    }
}
if (!$Health -or $Health.status -ne "ok" -or $Health.database -ne "ok") {
    if (!$Tunnel.HasExited) { Stop-Process -Id $Tunnel.Id }
    throw "The tunneled backend health check failed after waiting for DNS and tunnel readiness."
}

@{
    tunnelUrl = $TunnelUrl
    tunnelPid = $Tunnel.Id
    tokenFile = $TokenPath
    startedAt = (Get-Date).ToString("o")
} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $DemoDir "vercel-bridge.json")

Write-Output "Vercel GPU bridge ready: $TunnelUrl"
Write-Output "Tunnel PID: $($Tunnel.Id)"
Write-Output "Use the tunnel URL for BACKEND_API_URL and the token file for ARCHPILOT_PROXY_TOKEN."
