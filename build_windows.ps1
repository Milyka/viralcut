# Сборка KrlzCut для Windows 10/11 (x64) в один exe-каталог + ZIP.
# Запуск:  powershell -ExecutionPolicy Bypass -File build_windows.ps1
param(
    # Пусто — версия берётся из viralcut/_version.py (единый источник истины).
    [string]$Version = "",
    [switch]$SkipModel
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

Write-Host "[KrlzCut] Python..." -ForegroundColor Cyan
$py = $null
foreach ($candidate in @("py -3.12", "python")) {
    try {
        & cmd /c "$candidate -c `"import sys; assert sys.version_info >= (3, 11)`"" *> $null
        if ($LASTEXITCODE -eq 0) {
            $py = $candidate
            break
        }
    } catch { }
}
if (-not $py) { throw "Не найден Python 3.12. Установите с https://www.python.org/downloads/windows/" }

if (-not (Test-Path ".venv-win\Scripts\python.exe")) {
    Write-Host "[KrlzCut] создаю .venv-win..." -ForegroundColor Cyan
    & cmd /c "$py -m venv .venv-win"
}
$venvPy = Join-Path $PSScriptRoot ".venv-win\Scripts\python.exe"
$venvPip = Join-Path $PSScriptRoot ".venv-win\Scripts\pip.exe"

if (-not $Version) {
    $Version = (& $venvPy "tools\version.py").Trim()
    if (-not $Version) { throw "Не удалось прочитать версию из tools/version.py" }
}
Write-Host "[KrlzCut] версия: $Version" -ForegroundColor Cyan

& $venvPy -m pip install --upgrade pip
& $venvPip install -r requirements-desktop.txt pyinstaller

if (-not $SkipModel -and -not (Test-Path "build\whisper-small\model.bin")) {
    Write-Host "[KrlzCut] скачиваю Whisper Small (один раз)..." -ForegroundColor Cyan
    try {
        & $venvPy -c "from huggingface_hub import snapshot_download; snapshot_download('Systran/faster-whisper-small', local_dir='build/whisper-small', allow_patterns=['model.bin','config.json','tokenizer.json','vocabulary.txt'])"
    } catch {
        Write-Warning "Модель не скачалась — приложение докачает её при первом запуске."
    }
}

Write-Host "[KrlzCut] PyInstaller..." -ForegroundColor Cyan
& (Join-Path $PSScriptRoot ".venv-win\Scripts\pyinstaller.exe") ViralCut.spec --noconfirm --clean
if ($LASTEXITCODE -ne 0) { throw "PyInstaller завершился с ошибкой" }

$outDir = Join-Path $PSScriptRoot "release"
New-Item -ItemType Directory -Force $outDir | Out-Null
$zip = Join-Path $outDir "KrlzCut-$Version-windows-x64.zip"
if (Test-Path $zip) { Remove-Item $zip -Force }
Write-Host "[KrlzCut] упаковываю $zip..." -ForegroundColor Cyan
Compress-Archive -Path "dist\KrlzCut" -DestinationPath $zip -CompressionLevel Optimal

$hash = (Get-FileHash $zip -Algorithm SHA256).Hash.ToLower()
"$hash  $(Split-Path $zip -Leaf)" | Out-File -Encoding ascii (Join-Path $outDir "SHA256SUMS-windows.txt")

Write-Host ""
Write-Host "SHA256: $hash"
Write-Host "Готово: $zip" -ForegroundColor Green
Write-Host "Запуск: dist\KrlzCut\KrlzCut.exe"
