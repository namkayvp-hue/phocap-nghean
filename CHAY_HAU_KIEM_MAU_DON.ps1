$ErrorActionPreference = "Continue"
Set-Location "C:\PhoCap"
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"

$ExportDir = "C:\PhoCap\exports"
New-Item -ItemType Directory -Force -Path $ExportDir | Out-Null
$OutFile = Join-Path $ExportDir "HAU_KIEM_MAU_DON.txt"

if (Test-Path "C:\PhoCap\.venv\Scripts\python.exe") {
    $Py = "C:\PhoCap\.venv\Scripts\python.exe"
} else {
    $Py = "python"
}

Write-Host "==================================================================" -ForegroundColor Cyan
Write-Host "HAU KIEM THCS MAU DON - CHI DOC" -ForegroundColor Cyan
Write-Host "Ket qua: $OutFile" -ForegroundColor Yellow
Write-Host "==================================================================" -ForegroundColor Cyan

& $Py -X utf8 "C:\PhoCap\hau_kiem_mau_don.py" 2>&1 | Tee-Object -FilePath $OutFile

Write-Host ""
Write-Host "GUI FILE SAU CHO CHATGPT:" -ForegroundColor Green
Write-Host $OutFile -ForegroundColor Green
Read-Host "Nhan Enter de dong"
