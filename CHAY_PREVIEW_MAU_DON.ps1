$ErrorActionPreference = "Stop"
$Host.UI.RawUI.WindowTitle = "PREVIEW THCS MAU DON"

Set-Location "C:\PhoCap"
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"

if (Test-Path "C:\PhoCap\.venv\Scripts\python.exe") {
    $Py = "C:\PhoCap\.venv\Scripts\python.exe"
} else {
    $Py = "python"
}

$OutFile = Join-Path $env:USERPROFILE "Desktop\PREVIEW_MAU_DON_FULL_SOURCE_MERGE.txt"

Write-Host "==================================================================" -ForegroundColor Cyan
Write-Host "PREVIEW: THCS MAU DON -> PTDT BAN TRU THCS THACH NGAN" -ForegroundColor Cyan
Write-Host "CHI DOC - KHONG GHI DB" -ForegroundColor Yellow
Write-Host "Ket qua: $OutFile" -ForegroundColor Cyan
Write-Host "==================================================================" -ForegroundColor Cyan
Write-Host ""

& $Py -X utf8 "C:\PhoCap\preview_mau_don_full_source_merge.py" 2>&1 | Tee-Object -FilePath $OutFile

Write-Host ""
Write-Host "==================================================================" -ForegroundColor Cyan
Write-Host "DA CHAY XONG. GUI FILE PREVIEW TREN DESKTOP CHO CHATGPT." -ForegroundColor Green
Write-Host "==================================================================" -ForegroundColor Cyan
Read-Host "Nhan Enter de dong"
