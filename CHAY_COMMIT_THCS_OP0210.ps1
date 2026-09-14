$ErrorActionPreference = "Stop"
Set-Location "C:\PhoCap"
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"

Write-Host "==================================================================" -ForegroundColor Yellow
Write-Host "COMMIT CHINH THUC QD3805-OP-0210" -ForegroundColor Yellow
Write-Host "SOURCE: 1733 | THCS Thuong Son" -ForegroundColor Yellow
Write-Host "TARGET: 1734 | THCS Tran Phu" -ForegroundColor Yellow
Write-Host "PLAN: PA2026-0104708B7153" -ForegroundColor Yellow
Write-Host "THCS VAN HIEN: KHONG CHAM" -ForegroundColor Yellow
Write-Host "==================================================================" -ForegroundColor Yellow

$Confirm = Read-Host "Nhap dung CHAP_NHAN de thuc hien"
if ($Confirm -ne "CHAP_NHAN") {
    Write-Host "DA HUY. KHONG GHI DATABASE." -ForegroundColor Green
    Read-Host "Nhan Enter de dong"
    exit 0
}

if (Test-Path "C:\PhoCap\.venv\Scripts\python.exe") {
    $Py = "C:\PhoCap\.venv\Scripts\python.exe"
} else {
    $Py = "python"
}

& $Py -X utf8 "C:\PhoCap\commit_thcs_op0210.py"
$ExitCode = $LASTEXITCODE

Write-Host ""
Write-Host "KET QUA:" -ForegroundColor Cyan
Write-Host "C:\PhoCap\exports\COMMIT_THCS_OP0210.txt" -ForegroundColor Green
Write-Host "ExitCode = $ExitCode" -ForegroundColor Cyan
Read-Host "Nhan Enter de dong"
exit $ExitCode
