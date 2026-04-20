<#
HarnessAI installer (Windows PowerShell).

Usage:
  .\install.ps1               # interactive (shows diff if previously installed)
  .\install.ps1 -Force        # overwrite without confirmation
  .\install.ps1 -DryRun       # print the plan, do not copy
  $env:CLAUDE_HOME = "C:\custom\.claude"; .\install.ps1

What it does:
  1. harness\ → $CLAUDE_HOME\harness\
  2. skills\{ha-*,_ha_shared} → $CLAUDE_HOME\skills\
  3. writes SHA-256 manifest to $CLAUDE_HOME\harness\.install-manifest.json
  4. on re-run, detects changes via manifest diff
#>

[CmdletBinding()]
param(
    [switch]$Force,
    [switch]$DryRun
)

$ErrorActionPreference = 'Stop'
$RepoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path

if (-not $env:CLAUDE_HOME) {
    $ClaudeHome = Join-Path $env:USERPROFILE '.claude'
} else {
    $ClaudeHome = $env:CLAUDE_HOME
}

$ManifestPath = Join-Path $ClaudeHome 'harness\.install-manifest.json'

# Copy plan — list of (source_abs, target_rel)
$Plan = New-Object System.Collections.Generic.List[object]

function Add-Plan {
    param([string]$SrcDir, [string]$TargetPrefix)
    if (-not (Test-Path $SrcDir)) { return }
    Get-ChildItem -LiteralPath $SrcDir -Recurse -File | Where-Object {
        # Skip __pycache__/ directories and .pyc files (Python runtime cache)
        $_.FullName -notmatch '\\__pycache__\\' -and $_.Extension -ne '.pyc'
    } | ForEach-Object {
        $rel = $_.FullName.Substring($SrcDir.Length).TrimStart('\', '/')
        # Manifest targets always use forward slashes (cross-platform)
        $target = ($TargetPrefix + '/' + $rel) -replace '\\', '/'
        $Plan.Add([pscustomobject]@{ Src = $_.FullName; Target = $target }) | Out-Null
    }
}

Add-Plan (Join-Path $RepoRoot 'harness') 'harness'
$SkillsRoot = Join-Path $RepoRoot 'skills'
if (Test-Path $SkillsRoot) {
    Get-ChildItem -LiteralPath $SkillsRoot -Directory | Where-Object {
        $_.Name -like 'ha-*' -or $_.Name -eq '_ha_shared'
    } | ForEach-Object {
        Add-Plan $_.FullName ('skills/' + $_.Name)
    }
}

Write-Host "HarnessAI install plan"
Write-Host "  repo:   $RepoRoot"
Write-Host "  target: $ClaudeHome"
Write-Host "  files:  $($Plan.Count)"
Write-Host ""

# Build old-hash map from existing manifest
$OldHashes = @{}
if (Test-Path $ManifestPath) {
    try {
        $old = Get-Content -LiteralPath $ManifestPath -Raw | ConvertFrom-Json
        foreach ($f in $old.files) {
            $OldHashes[$f.target] = $f.sha256
        }
    } catch {
        Write-Warning "failed to parse existing manifest — treating as full reinstall: $_"
    }
}

# Classify changes
$Added = New-Object System.Collections.Generic.List[string]
$Modified = New-Object System.Collections.Generic.List[string]
$Unchanged = New-Object System.Collections.Generic.List[string]
$NewTargets = @{}

foreach ($item in $Plan) {
    $newHash = (Get-FileHash -LiteralPath $item.Src -Algorithm SHA256).Hash.ToLower()
    $oldHash = $OldHashes[$item.Target]
    $NewTargets[$item.Target] = $newHash
    if (-not $oldHash) {
        $Added.Add($item.Target) | Out-Null
    } elseif ($oldHash -ne $newHash) {
        $Modified.Add($item.Target) | Out-Null
    } else {
        $Unchanged.Add($item.Target) | Out-Null
    }
}

$Removed = $OldHashes.Keys | Where-Object { -not $NewTargets.ContainsKey($_) }

Write-Host "Change summary:"
Write-Host "  added:     $($Added.Count)"
Write-Host "  modified:  $($Modified.Count)"
Write-Host "  unchanged: $($Unchanged.Count)"
Write-Host "  removed:   $(@($Removed).Count)"
Write-Host ""

if ($Modified.Count -gt 0 -and -not $Force -and -not $DryRun) {
    Write-Host "Will modify:"
    foreach ($f in $Modified) { Write-Host "  M $f" }
    Write-Host ""
    if (@($Removed).Count -gt 0) {
        Write-Host "Will remove (absent from repo — clean up targets manually):"
        foreach ($f in $Removed) { Write-Host "  D $f" }
        Write-Host ""
    }
    # In non-interactive environments (CI, redirected stdin) Read-Host hangs — abort instead.
    if (-not [Environment]::UserInteractive -or [Console]::IsInputRedirected) {
        Write-Host "Non-interactive session detected — cannot prompt. Re-run with -Force if changes are expected." -ForegroundColor Yellow
        exit 1
    }
    $reply = Read-Host "Continue? [y/N]"
    if ($reply -notmatch '^[yY]') {
        Write-Host "Aborted."
        exit 0
    }
}

if ($DryRun) {
    Write-Host "[dry-run] no files copied."
    exit 0
}

# Copy files + write new manifest
New-Item -ItemType Directory -Force -Path (Join-Path $ClaudeHome 'harness') | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $ClaudeHome 'skills') | Out-Null

$manifestFiles = New-Object System.Collections.Generic.List[object]
foreach ($item in $Plan) {
    $targetAbs = Join-Path $ClaudeHome ($item.Target -replace '/', '\')
    $targetDir = Split-Path -Parent $targetAbs
    if (-not (Test-Path $targetDir)) {
        New-Item -ItemType Directory -Force -Path $targetDir | Out-Null
    }
    Copy-Item -LiteralPath $item.Src -Destination $targetAbs -Force
    $hash = (Get-FileHash -LiteralPath $targetAbs -Algorithm SHA256).Hash.ToLower()
    $manifestFiles.Add([pscustomobject]@{ target = $item.Target; sha256 = $hash }) | Out-Null
}

$manifest = [ordered]@{
    version      = '0.1.0'
    installed_at = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
    source       = $RepoRoot
    files        = $manifestFiles
}
$manifest | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $ManifestPath -Encoding UTF8

Write-Host "[OK] install complete"
Write-Host "  installed: $($Plan.Count) files"
Write-Host "  manifest:  $ManifestPath"
Write-Host ""
Write-Host "Set this env var (add to your PowerShell profile):"
Write-Host "  `$env:HARNESS_AI_HOME = '$RepoRoot'"
Write-Host ""
Write-Host "Next: open a fresh Claude Code session and run '/ha-init'."
