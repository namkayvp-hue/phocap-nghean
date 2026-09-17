$ErrorActionPreference = "Stop"
$Host.UI.RawUI.WindowTitle = "TRUY VET PLAN THCS MAU DON"

Set-Location "C:\PhoCap"
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"

if (Test-Path "C:\PhoCap\.venv\Scripts\python.exe") {
    $Py = "C:\PhoCap\.venv\Scripts\python.exe"
} else {
    $Py = "python"
}

$OutFile = Join-Path $env:USERPROFILE "Desktop\TRUY_VET_PLAN_MAU_DON.txt"

Write-Host "==================================================================" -ForegroundColor Cyan
Write-Host "TRUY VET QD3805-OP-0108 / MAU DON / PLAN_ID" -ForegroundColor Cyan
Write-Host "CHI DOC - KHONG GHI DATABASE" -ForegroundColor Yellow
Write-Host "Ket qua: $OutFile" -ForegroundColor Cyan
Write-Host "==================================================================" -ForegroundColor Cyan
Write-Host ""

& $Py -X utf8 "C:\PhoCap\truy_vet_plan_mau_don.py" 2>&1 | Tee-Object -FilePath $OutFile

Write-Host ""
Write-Host "==================================================================" -ForegroundColor Cyan
Write-Host "DA CHAY XONG. GUI FILE TRUY_VET_PLAN_MAU_DON.txt CHO CHATGPT." -ForegroundColor Green
Write-Host "==================================================================" -ForegroundColor Cyan
Read-Host "Nhan Enter de dong"
