$ErrorActionPreference = "Continue"
Set-Location "C:\PhoCap"

$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"

$ExportDir = "C:\PhoCap\exports"
New-Item -ItemType Directory -Force -Path $ExportDir | Out-Null
$OutFile = Join-Path $ExportDir "XAC_DINH_PLAN_MAU_DON.txt"
$Desktop = [Environment]::GetFolderPath("Desktop")
$DesktopFile = if ($Desktop) { Join-Path $Desktop "XAC_DINH_PLAN_MAU_DON.txt" } else { $null }

if (Test-Path "C:\PhoCap\.venv\Scripts\python.exe") {
    $Py = "C:\PhoCap\.venv\Scripts\python.exe"
} else {
    $Py = "python"
}

"==================================================================" | Set-Content -Path $OutFile -Encoding UTF8
"BAT DAU XAC DINH PLAN THCS MAU DON - V2" | Add-Content -Path $OutFile -Encoding UTF8
("Thoi gian: " + (Get-Date -Format "yyyy-MM-dd HH:mm:ss")) | Add-Content -Path $OutFile -Encoding UTF8
"==================================================================" | Add-Content -Path $OutFile -Encoding UTF8

Write-Host "==================================================================" -ForegroundColor Cyan
Write-Host "XAC DINH PLAN THCS MAU DON - V2" -ForegroundColor Cyan
Write-Host "File ket qua CHAC CHAN:" -ForegroundColor Yellow
Write-Host $OutFile -ForegroundColor Yellow
Write-Host "==================================================================" -ForegroundColor Cyan
Write-Host ""

try {
    & $Py -X utf8 "C:\PhoCap\xac_dinh_plan_mau_don_v2.py" 2>&1 | Tee-Object -FilePath $OutFile -Append
    $ExitCode = $LASTEXITCODE
} catch {
    ("POWERSHELL ERROR: " + $_.Exception.Message) | Tee-Object -FilePath $OutFile -Append
    $ExitCode = 99
}

if ($DesktopFile) {
    try {
        Copy-Item -Force $OutFile $DesktopFile
        Write-Host ""
        Write-Host "Da chep them ra Desktop:" -ForegroundColor Green
        Write-Host $DesktopFile -ForegroundColor Green
    } catch {
        Write-Host "Khong chep duoc ra Desktop, nhung file trong C:\PhoCap\exports van co." -ForegroundColor Yellow
    }
}

Write-Host ""
Write-Host "ExitCode = $ExitCode" -ForegroundColor Cyan
Write-Host "FILE KET QUA:" -ForegroundColor Cyan
Write-Host $OutFile -ForegroundColor Green
Write-Host ""
Read-Host "Nhan Enter de dong"
