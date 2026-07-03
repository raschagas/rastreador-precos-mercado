<#
Builds the portable Windows ZIP:
  1. downloads the embeddable CPython (amd64),
  2. enables pip (uncomment `import site` in the ._pth, run get-pip.py),
  3. drops in app/ + Iniciar.bat,
  4. zips the whole folder.

The resulting ZIP is fully self-contained: the user unzips it and runs
Iniciar.bat; pip requirements are fetched on first launch (with a prompt).

Usage:  pwsh -File build/build_portable.ps1 [-PyVersion 3.12.8]
#>
param(
    [string]$PyVersion = "3.12.8",
    [string]$OutName   = "RastreadorPrecos-portable"
)

$ErrorActionPreference = "Stop"
$root    = Split-Path -Parent $PSScriptRoot
$staging = Join-Path $PSScriptRoot "staging\$OutName"
$pydir   = Join-Path $staging "python"

Write-Host "==> Limpando staging"
if (Test-Path (Join-Path $PSScriptRoot "staging")) {
    Remove-Item (Join-Path $PSScriptRoot "staging") -Recurse -Force
}
New-Item -ItemType Directory -Force -Path $pydir | Out-Null

# 1. Embeddable Python -------------------------------------------------------
$embedUrl = "https://www.python.org/ftp/python/$PyVersion/python-$PyVersion-embed-amd64.zip"
$embedZip = Join-Path $PSScriptRoot "python-embed.zip"
Write-Host "==> Baixando Python embutido $PyVersion"
Invoke-WebRequest -Uri $embedUrl -OutFile $embedZip
Expand-Archive -Path $embedZip -DestinationPath $pydir -Force
Remove-Item $embedZip

# 2. Enable site + pip -------------------------------------------------------
$pth = Get-ChildItem $pydir -Filter "python*._pth" | Select-Object -First 1
Write-Host "==> Habilitando site em $($pth.Name)"
(Get-Content $pth.FullName) -replace '^#\s*import site', 'import site' |
    Set-Content $pth.FullName
Add-Content $pth.FullName "app"   # make engine/gui importable via ._pth too

$getpip = Join-Path $PSScriptRoot "get-pip.py"
if (-not (Test-Path $getpip)) {
    Write-Host "==> Baixando get-pip.py"
    Invoke-WebRequest -Uri "https://bootstrap.pypa.io/get-pip.py" -OutFile $getpip
}
Write-Host "==> Instalando pip no Python embutido"
& (Join-Path $pydir "python.exe") $getpip --no-warn-script-location

# 3. App payload -------------------------------------------------------------
Write-Host "==> Copiando app + lancador"
Copy-Item (Join-Path $root "app")        (Join-Path $staging "app") -Recurse
Copy-Item (Join-Path $root "Iniciar.bat") $staging
Copy-Item (Join-Path $root "README.md")   $staging -ErrorAction SilentlyContinue
# strip caches
Get-ChildItem $staging -Recurse -Directory -Filter "__pycache__" |
    Remove-Item -Recurse -Force -ErrorAction SilentlyContinue

# 4. Zip ---------------------------------------------------------------------
$outZip = Join-Path $PSScriptRoot "$OutName.zip"
if (Test-Path $outZip) { Remove-Item $outZip -Force }
Write-Host "==> Compactando $outZip"
Compress-Archive -Path $staging -DestinationPath $outZip
Write-Host "==> Pronto: $outZip"
