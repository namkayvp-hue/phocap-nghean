$ErrorActionPreference = "Stop"
Set-Location "C:\PhoCap"
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"

Write-Host "==================================================================" -ForegroundColor Yellow
Write-Host "SAP THUC HIEN COMMIT CHINH THUC:" -ForegroundColor Yellow
Write-Host "THCS Mau Don (1578) -> PTDT Ban tru THCS Thach Ngan (1577)" -ForegroundColor Yellow
Write-Host "PLAN: PA2026-C1BD6766C723" -ForegroundColor Yellow
Write-Host "==================================================================" -ForegroundColor Yellow
Write-Host ""
$Confirm = Read-Host "Nhap dung CHAP_NHAN de tiep tuc"

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

& $Py -X utf8 "C:\PhoCap\commit_mau_don_full_source_merge.py"
$ExitCode = $LASTEXITCODE

Write-Host ""
Write-Host "==================================================================" -ForegroundColor Cyan
Write-Host "KET QUA LUON DUOC LUU TAI:" -ForegroundColor Cyan
Write-Host "C:\PhoCap\exports\COMMIT_MAU_DON_FULL_SOURCE_MERGE.txt" -ForegroundColor Green
Write-Host "ExitCode = $ExitCode" -ForegroundColor Cyan
Write-Host "==================================================================" -ForegroundColor Cyan
Read-Host "Nhan Enter de dong"
exit $ExitCode
