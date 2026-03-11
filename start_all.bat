@echo off
chcp 65001 > nul
title BTC 트레이딩 앱

echo ===============================
echo   BTC Trading App Starting...
echo ===============================

set ROOT=%~dp0
set PYTHON=C:\Users\etri\anaconda3\python.exe
set NODE=C:\Users\etri\anaconda3\node.exe
set VITE=%ROOT%frontend\node_modules\vite\bin\vite.js

echo.
echo [1/2] 백엔드 서버 시작 (포트 8000)...
start "Backend (FastAPI)" cmd /k "%PYTHON% "%ROOT%start_backend.py""

timeout /t 5 /nobreak > nul

echo [2/2] 프론트엔드 서버 시작 (포트 5173)...
start "Frontend (Vite)" cmd /k "%NODE% "%VITE%" "%ROOT%frontend" --port 5173 --config "%ROOT%frontend\vite.config.js""

timeout /t 5 /nobreak > nul

echo.
echo 서버가 시작되었습니다!
echo    트레이딩 앱: http://localhost:5173
echo    API 문서:    http://localhost:8000/docs
echo.

start http://localhost:5173

exit
