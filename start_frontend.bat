@echo off
set ROOT=%~dp0
set NODE=C:\Users\etri\anaconda3\node.exe
set VITE=%ROOT%frontend\node_modules\vite\bin\vite.js

"%NODE%" "%VITE%" "%ROOT%frontend" --port 5173 --config "%ROOT%frontend\vite.config.js"
