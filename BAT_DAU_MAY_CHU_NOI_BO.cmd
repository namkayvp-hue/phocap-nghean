@echo off
chcp 65001 >nul
cd /d C:\PhoCap
if not exist "C:\PhoCap\.venv\Scripts\python.exe" (
  echo Khong tim thay moi truong Python tai C:\PhoCap\.venv
  pause
  exit /b 1
)
title PHOCAP - MAY CHU NOI BO
"C:\PhoCap\.venv\Scripts\python.exe" -m uvicorn app.main:app --host 0.0.0.0 --port 8000
pause
