<#
.SYNOPSIS
    Builds the Windows desktop app: a standalone folder, a portable .zip and
    (if Inno Setup is installed) a double-clickable Setup.exe.

.DESCRIPTION
    Everything is built inside an isolated .venv-build so the bundle only
    contains what AuditPack actually needs.

.PARAMETER SkipInstaller
    Build the executable and portable zip only, skipping Inno Setup.

.PARAMETER Clean
    Delete the build venv first and reinstall dependencies from scratch.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File desktop\build_windows.ps1
#>
[CmdletBinding()]
param(
    [switch]$SkipInstaller,
    [switch]$Clean
)

$ErrorActionPreference = 'Stop'

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$DesktopDir  = Join-Path $ProjectRoot 'desktop'
$VenvDir     = Join-Path $ProjectRoot '.venv-build'
$VenvPython  = Join-Path $VenvDir 'Scripts\python.exe'
$DistDir     = Join-Path $ProjectRoot 'dist'
$AppDir      = Join-Path $DistDir 'AuditPack'

Write-Host "==> Project root: $ProjectRoot"

if ($Clean -and (Test-Path $VenvDir)) {
    Write-Host '==> Removing existing build venv'
    Remove-Item -Recurse -Force $VenvDir
}

if (-not (Test-Path $VenvPython)) {
    Write-Host '==> Creating build virtual environment'
    python -m venv $VenvDir
    if (-not $?) { throw 'Could not create the virtual environment. Is Python 3.10+ on PATH?' }
}

Write-Host '==> Installing dependencies'
& $VenvPython -m pip install --upgrade pip --quiet
& $VenvPython -m pip install --quiet `
    -r (Join-Path $ProjectRoot 'requirements.txt') `
    -r (Join-Path $DesktopDir 'requirements-build.txt')
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }

if (-not (Test-Path (Join-Path $DesktopDir 'icon.ico'))) {
    Write-Host '==> Generating icon'
    & $VenvPython (Join-Path $DesktopDir 'make_icons.py')
}

Write-Host '==> Cleaning previous build output'
foreach ($path in @((Join-Path $ProjectRoot 'build'), $AppDir)) {
    if (Test-Path $path) { Remove-Item -Recurse -Force $path }
}

Write-Host '==> Running PyInstaller (this takes a few minutes)'
Push-Location $ProjectRoot
try {
    & $VenvPython -m PyInstaller (Join-Path $DesktopDir 'AuditPack.spec') --noconfirm --clean
    if ($LASTEXITCODE -ne 0) { throw 'PyInstaller failed.' }
} finally {
    Pop-Location
}

if (-not (Test-Path (Join-Path $AppDir 'AuditPack.exe'))) {
    throw "Expected executable was not produced in $AppDir"
}

$sizeMb = [math]::Round(((Get-ChildItem $AppDir -Recurse | Measure-Object Length -Sum).Sum / 1MB), 1)
Write-Host "==> Application folder built ($sizeMb MB): $AppDir"

Write-Host '==> Creating portable zip'
$zipPath = Join-Path $DistDir 'AuditPack-windows-portable.zip'
if (Test-Path $zipPath) { Remove-Item -Force $zipPath }
Compress-Archive -Path $AppDir -DestinationPath $zipPath
Write-Host "==> Portable zip: $zipPath"

if ($SkipInstaller) {
    Write-Host '==> Skipping installer (-SkipInstaller)'
    exit 0
}

$isccCandidates = @(
    "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
    "$env:ProgramFiles\Inno Setup 6\ISCC.exe",
    "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe"
)
$iscc = $isccCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $iscc) {
    $onPath = Get-Command iscc.exe -ErrorAction SilentlyContinue
    if ($onPath) { $iscc = $onPath.Source }
}

if (-not $iscc) {
    Write-Warning 'Inno Setup 6 was not found, so no Setup.exe was produced.'
    Write-Host    'Install it from https://jrsoftware.org/isdl.php (or: winget install JRSoftware.InnoSetup) and re-run this script.'
    exit 0
}

Write-Host "==> Building installer with $iscc"
& $iscc (Join-Path $DesktopDir 'installer.iss')
if ($LASTEXITCODE -ne 0) { throw 'Inno Setup compilation failed.' }

Get-ChildItem (Join-Path $DistDir 'installer') -Filter *.exe | ForEach-Object {
    Write-Host "==> Installer: $($_.FullName)"
}
