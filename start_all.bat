@echo off
chcp 65001 > nul
title BTC 트레이딩 앱

echo ===============================
echo   BTC Trading App Starting...
echo ===============================

echo.
echo [1/2] 백엔드 서버 시작 (포트 8000)...
start "Backend (FastAPI)" powershell -NoExit -Command "& 'C:\Users\etri\anaconda3\python.exe' 'C:\Users\etri\Desktop\Coding\Trading\start_backend.py'"

timeout /t 5 /nobreak > nul

echo [2/2] 프론트엔드 서버 시작 (포트 5173)...
start "Frontend (Vite)" powershell -NoExit -Command "& 'C:\Users\etri\anaconda3\node.exe' 'C:\Users\etri\Desktop\Coding\Trading\frontend\node_modules\vite\bin\vite.js' 'C:\Users\etri\Desktop\Coding\Trading\frontend' --port 5173 --config 'C:\Users\etri\Desktop\Coding\Trading\frontend\vite.config.js'"

timeout /t 5 /nobreak > nul

echo.
echo 서버가 시작되었습니다!
echo    트레이딩 앱: http://localhost:5173
echo    API 문서:    http://localhost:8000/docs
echo.

start http://localhost:5173

exit
