$ErrorActionPreference = "Stop"
Set-Location "C:\PhoCap"
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"

Write-Host "==================================================================" -ForegroundColor Yellow
Write-Host "COMMIT CHINH THUC QD3805-OP-0644" -ForegroundColor Yellow
Write-Host "SOURCE: 1748 | THCS Yen Hoa" -ForegroundColor Yellow
Write-Host "TARGET: 1747 | PTDTBT THCS Yen Thang" -ForegroundColor Yellow
Write-Host "PLAN: PA2026-52415E680B77" -ForegroundColor Yellow
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

& $Py -X utf8 "C:\PhoCap\commit_thcs_op0644.py"
$ExitCode = $LASTEXITCODE

Write-Host ""
Write-Host "KET QUA:" -ForegroundColor Cyan
Write-Host "C:\PhoCap\exports\COMMIT_THCS_OP0644.txt" -ForegroundColor Green
Write-Host "ExitCode = $ExitCode" -ForegroundColor Cyan
Read-Host "Nhan Enter de dong"
exit $ExitCode
