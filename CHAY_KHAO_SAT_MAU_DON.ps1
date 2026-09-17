$ErrorActionPreference = "Stop"
$Host.UI.RawUI.WindowTitle = "CHAY KHAO SAT THCS MAU DON"

Set-Location "C:\PhoCap"

$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"

$Py = $null
if (Test-Path "C:\PhoCap\.venv\Scripts\python.exe") {
    $Py = "C:\PhoCap\.venv\Scripts\python.exe"
} else {
    $Py = "python"
}

$OutFile = Join-Path $env:USERPROFILE "Desktop\KHAO_SAT_MAU_DON_1578.txt"

Write-Host "==================================================================" -ForegroundColor Cyan
Write-Host "CHAY KHAO SAT THCS MAU DON - CHI DOC" -ForegroundColor Cyan
Write-Host "Ket qua se luu tai: $OutFile" -ForegroundColor Cyan
Write-Host "==================================================================" -ForegroundColor Cyan
Write-Host ""

& $Py -X utf8 "C:\PhoCap\khao_sat_mau_don_1578.py" 2>&1 | Tee-Object -FilePath $OutFile

Write-Host ""
Write-Host "==================================================================" -ForegroundColor Cyan
Write-Host "DA CHAY XONG. GUI FILE TREN DESKTOP CHO CHATGPT." -ForegroundColor Green
Write-Host "==================================================================" -ForegroundColor Cyan
Read-Host "Nhan Enter de dong"
