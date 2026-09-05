# Сборка NIT-360 HMI под Windows: один портативный exe.
# Запускать на Windows из корня репозитория:
#     powershell -ExecutionPolicy Bypass -File pyside\packaging\build_windows.ps1
# Результат: dist\NIT-360-HMI.exe

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
Set-Location $root

$python = Join-Path $root ".venv-build\Scripts\python.exe"
if (-not (Test-Path $python)) {
    Write-Host "Создаю окружение сборки .venv-build..."
    py -3 -m venv .venv-build
}

& $python -m pip install --upgrade pip
& $python -m pip install -r pyside\requirements.txt -r pyside\requirements-build.txt

$env:NIT360_BUILD_MODE = "onefile"
& $python -m PyInstaller pyside\nit360.spec --noconfirm --clean

$exe = Join-Path $root "dist\NIT-360-HMI.exe"
if (-not (Test-Path $exe)) { throw "Сборка не создала $exe" }
$size = [math]::Round((Get-Item $exe).Length / 1MB, 1)
Write-Host "Готово: $exe ($size МБ)"
