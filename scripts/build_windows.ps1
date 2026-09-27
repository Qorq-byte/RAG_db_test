param([string]$InnoCompiler = "$PSScriptRoot/../.data/tools/inno/ISCC.exe")
$ErrorActionPreference = 'Stop'
Set-Location (Join-Path $PSScriptRoot '..')
uv sync --frozen
if ($LASTEXITCODE -ne 0) { throw 'Dependency sync failed' }
# Do not let unrelated tools on PATH supply incompatible native libraries.
$env:PATH = (Join-Path (Get-Location) '.venv/Scripts') + ';' + (Join-Path $env:SystemRoot 'System32') + ';' + $env:SystemRoot
& ./.venv/Scripts/python.exe -m PyInstaller packaging/windows.spec --noconfirm
if ($LASTEXITCODE -ne 0) { throw 'PyInstaller build failed' }
& ./dist/RAGDB/RAGDB-CLI.exe --self-test
if ($LASTEXITCODE -ne 0) { throw 'Frozen package integration check failed' }
& $InnoCompiler packaging/installer.iss
if ($LASTEXITCODE -ne 0) { throw 'Installer build failed' }
Get-FileHash ./dist/RAGDB-0.1.0-windows-x64-setup.exe -Algorithm SHA256 |
    ForEach-Object { "$($_.Hash.ToLower())  RAGDB-0.1.0-windows-x64-setup.exe" } |
    Set-Content ./dist/SHA256SUMS.txt -Encoding ascii
