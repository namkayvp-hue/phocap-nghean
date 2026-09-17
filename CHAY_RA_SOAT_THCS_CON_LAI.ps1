$ErrorActionPreference = "Continue"
Set-Location "C:\PhoCap"
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"

$ExportDir = "C:\PhoCap\exports"
New-Item -ItemType Directory -Force -Path $ExportDir | Out-Null
$OutFile = Join-Path $ExportDir "RA_SOAT_THCS_CON_LAI_GIU_NGUYEN.txt"

if (Test-Path "C:\PhoCap\.venv\Scripts\python.exe") {
    $Py = "C:\PhoCap\.venv\Scripts\python.exe"
} else {
    $Py = "python"
}

Write-Host "==================================================================" -ForegroundColor Cyan
Write-Host "RA SOAT THCS CON LAI - GIU NGUYEN CAC CASE CHI NHAN THEM LOP/DIEM" -ForegroundColor Cyan
Write-Host "Ket qua: $OutFile" -ForegroundColor Yellow
Write-Host "==================================================================" -ForegroundColor Cyan

& $Py -X utf8 "C:\PhoCap\ra_soat_thcs_con_lai_giu_nguyen.py" 2>&1 | Tee-Object -FilePath $OutFile

Write-Host ""
Write-Host "GUI FILE SAU CHO CHATGPT:" -ForegroundColor Green
Write-Host $OutFile -ForegroundColor Green
Read-Host "Nhan Enter de dong"
