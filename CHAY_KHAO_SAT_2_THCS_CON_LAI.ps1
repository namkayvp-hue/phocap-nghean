$ErrorActionPreference = "Continue"
Set-Location "C:\PhoCap"
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"

$ExportDir = "C:\PhoCap\exports"
New-Item -ItemType Directory -Force -Path $ExportDir | Out-Null
$OutFile = Join-Path $ExportDir "KHAO_SAT_2_THCS_CON_LAI.txt"

if (Test-Path "C:\PhoCap\.venv\Scripts\python.exe") {
    $Py = "C:\PhoCap\.venv\Scripts\python.exe"
} else {
    $Py = "python"
}

Write-Host "==================================================================" -ForegroundColor Cyan
Write-Host "KHAO SAT QD3805-OP-0210 VA QD3805-OP-0644 - CHI DOC" -ForegroundColor Cyan
Write-Host "Ket qua: $OutFile" -ForegroundColor Yellow
Write-Host "==================================================================" -ForegroundColor Cyan

& $Py -X utf8 "C:\PhoCap\khao_sat_2_thcs_con_lai.py" 2>&1 | Tee-Object -FilePath $OutFile

Write-Host ""
Write-Host "GUI FILE SAU CHO CHATGPT:" -ForegroundColor Green
Write-Host $OutFile -ForegroundColor Green
Read-Host "Nhan Enter de dong"
