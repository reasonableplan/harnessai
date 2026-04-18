<#
HarnessAI 설치 스크립트 (Windows PowerShell)

사용법:
  .\install.ps1               # 상호작용 (기존 설치 있으면 diff 확인)
  .\install.ps1 -Force        # 확인 없이 덮어쓰기
  .\install.ps1 -DryRun       # 실제 복사 없이 계획만 출력
  $env:CLAUDE_HOME = "C:\custom\.claude"; .\install.ps1

동작:
  1. harness/ → $CLAUDE_HOME\harness\
  2. skills/{ha-*,_ha_shared} → $CLAUDE_HOME\skills\
  3. $CLAUDE_HOME\harness\.install-manifest.json 에 SHA256 기록
  4. 재실행 시 manifest diff 로 변경 감지
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

# 복사 계획 — (source_abs, target_rel) 목록
$Plan = New-Object System.Collections.Generic.List[object]

function Add-Plan {
    param([string]$SrcDir, [string]$TargetPrefix)
    if (-not (Test-Path $SrcDir)) { return }
    Get-ChildItem -LiteralPath $SrcDir -Recurse -File | Where-Object {
        # __pycache__ 디렉토리 + .pyc 파일 제외 (파이썬 런타임 캐시)
        $_.FullName -notmatch '\\__pycache__\\' -and $_.Extension -ne '.pyc'
    } | ForEach-Object {
        $rel = $_.FullName.Substring($SrcDir.Length).TrimStart('\', '/')
        # target 경로는 항상 forward slash (manifest 호환성)
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

Write-Host "HarnessAI 설치 준비"
Write-Host "  repo:   $RepoRoot"
Write-Host "  target: $ClaudeHome"
Write-Host "  files:  $($Plan.Count)"
Write-Host ""

# 기존 manifest 읽어 old hash 맵 구성
$OldHashes = @{}
if (Test-Path $ManifestPath) {
    try {
        $old = Get-Content -LiteralPath $ManifestPath -Raw | ConvertFrom-Json
        foreach ($f in $old.files) {
            $OldHashes[$f.target] = $f.sha256
        }
    } catch {
        Write-Warning "기존 manifest 파싱 실패 — 전체 재설치로 처리: $_"
    }
}

# 변경 분류
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

Write-Host "변경 요약:"
Write-Host "  added:     $($Added.Count)"
Write-Host "  modified:  $($Modified.Count)"
Write-Host "  unchanged: $($Unchanged.Count)"
Write-Host "  removed:   $(@($Removed).Count)"
Write-Host ""

if ($Modified.Count -gt 0 -and -not $Force -and -not $DryRun) {
    Write-Host "수정될 파일:"
    foreach ($f in $Modified) { Write-Host "  M $f" }
    Write-Host ""
    if (@($Removed).Count -gt 0) {
        Write-Host "삭제될 파일 (repo 에서 제거됨 — target 은 수동 처리):"
        foreach ($f in $Removed) { Write-Host "  D $f" }
        Write-Host ""
    }
    # non-interactive (CI, stdin redirect) 에서는 Read-Host 가 hang 함 → abort.
    if (-not [Environment]::UserInteractive -or [Console]::IsInputRedirected) {
        Write-Host "non-interactive 환경 감지 — 확인 불가. 변경 사항 있으면 -Force 로 재실행." -ForegroundColor Yellow
        exit 1
    }
    $reply = Read-Host "계속하시겠습니까? [y/N]"
    if ($reply -notmatch '^[yY]') {
        Write-Host "중단."
        exit 0
    }
}

if ($DryRun) {
    Write-Host "[dry-run] 실제 복사 생략."
    exit 0
}

# 실제 복사 + 새 manifest 작성
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

Write-Host "[OK] 설치 완료"
Write-Host "  installed: $($Plan.Count) files"
Write-Host "  manifest:  $ManifestPath"
Write-Host ""
Write-Host "환경 변수 설정 (PowerShell 프로파일에 추가 권장):"
Write-Host "  `$env:HARNESS_AI_HOME = '$RepoRoot'"
Write-Host ""
Write-Host "다음: 새 Claude Code 세션에서 '/ha-init' 사용 가능"
