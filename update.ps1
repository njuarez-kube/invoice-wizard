$ErrorActionPreference = 'Stop'
$appDir = Split-Path -Parent (Resolve-Path $PSCommandPath)

# ── Read GitHub repo from config.ini ─────────────────────────────────────────
$configPath = Join-Path $appDir 'config.ini'
$configContent = Get-Content $configPath -Raw -ErrorAction SilentlyContinue
if ($configContent -match 'github_repo\s*=\s*([^\r\n]+)') {
    $repo = $Matches[1].Trim()
} else {
    $repo = ''
}

if (-not $repo) {
    Write-Host ''
    Write-Host '  ERROR: github_repo not configured in config.ini'
    Write-Host '  Please contact support.'
    Write-Host ''
    Read-Host '  Press Enter to exit'
    exit 1
}

Write-Host ''
Write-Host '  ============================================'
Write-Host '   The Invoice Wizard - Update'
Write-Host '  ============================================'
Write-Host ''

# ── Read local version ────────────────────────────────────────────────────────
$localVerFile = Join-Path $appDir 'version.txt'
$localVer = if (Test-Path $localVerFile) { (Get-Content $localVerFile -Raw).Trim() } else { '0' }
Write-Host "  Current version : $localVer"
Write-Host '  Checking for updates...'

# ── Fetch latest release from GitHub ─────────────────────────────────────────
try {
    $rel = Invoke-RestMethod "https://api.github.com/repos/$repo/releases/latest" -TimeoutSec 10
} catch {
    Write-Host ''
    Write-Host "  ERROR: Could not connect to GitHub: $_"
    Write-Host '  Check your internet connection and try again.'
    Write-Host ''
    Read-Host '  Press Enter to exit'
    exit 1
}

$latestVer = $rel.tag_name.TrimStart('v')
Write-Host "  Latest version  : $latestVer"

if ($localVer -eq $latestVer) {
    Write-Host ''
    Write-Host '  You are already up to date!'
    Write-Host ''
    Read-Host '  Press Enter to exit'
    exit 0
}

# ── Find zip asset ────────────────────────────────────────────────────────────
$asset = $rel.assets | Where-Object { $_.name -like '*.zip' } | Select-Object -First 1
if (-not $asset) {
    Write-Host ''
    Write-Host '  ERROR: No update package found in this release.'
    Read-Host '  Press Enter to exit'
    exit 1
}

Write-Host ''
Write-Host "  Downloading v$latestVer..."
$zipPath = Join-Path $env:TEMP 'invoice_wizard_update.zip'
Invoke-WebRequest $asset.browser_download_url -OutFile $zipPath -UseBasicParsing

Write-Host '  Installing...'

# ── Extract to a temp folder ──────────────────────────────────────────────────
$tmpDir = Join-Path $env:TEMP 'invoice_wizard_extracted'
if (Test-Path $tmpDir) { Remove-Item $tmpDir -Recurse -Force }
Expand-Archive $zipPath $tmpDir -Force

# ── Copy new files, preserving user data ─────────────────────────────────────
# These are never overwritten (user-specific data)
$skipFiles = @('config.ini', 'token.json', 'gdrive_service_account.json')
$skipDirs  = @('output')

Get-ChildItem $tmpDir -Recurse -File | ForEach-Object {
    $relPath = $_.FullName.Substring($tmpDir.Length + 1)
    $dest    = Join-Path $appDir $relPath
    $skip    = $false

    foreach ($f in $skipFiles) {
        if ($relPath -eq $f) { $skip = $true; break }
    }
    foreach ($d in $skipDirs) {
        if ($relPath -like "$d\*" -or $relPath -like "$d/*") { $skip = $true; break }
    }
    # Vendor JSON files: only add new ones, never overwrite existing (user-customized)
    if (-not $skip -and ($relPath -like 'vendors\*' -or $relPath -like 'vendors/*') -and (Test-Path $dest)) {
        $skip = $true
    }

    if (-not $skip) {
        $destDir = Split-Path $dest
        if (-not (Test-Path $destDir)) { New-Item -ItemType Directory -Path $destDir -Force | Out-Null }
        Copy-Item $_.FullName $dest -Force
    }
}

# ── Cleanup ───────────────────────────────────────────────────────────────────
Remove-Item $zipPath -Force -ErrorAction SilentlyContinue
Remove-Item $tmpDir -Recurse -Force -ErrorAction SilentlyContinue

Write-Host ''
Write-Host "  OK  Updated to v$latestVer successfully!"
Write-Host ''
Write-Host '  Please restart the app (double-click start.bat).'
Write-Host ''
Read-Host '  Press Enter to exit'
