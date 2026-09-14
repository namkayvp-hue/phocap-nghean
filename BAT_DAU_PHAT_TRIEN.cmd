@echo off
chcp 65001 >nul
cd /d C:\PhoCap
if not exist "C:\PhoCap\.venv\Scripts\python.exe" (
  echo Khong tim thay moi truong Python tai C:\PhoCap\.venv
  echo Hay chay lai bo cai tren may moi.
  pause
  exit /b 1
)
title PHOCAP - CHE DO PHAT TRIEN
"C:\PhoCap\.venv\Scripts\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
pause
