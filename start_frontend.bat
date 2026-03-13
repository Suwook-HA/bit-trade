@echo off
set ROOT=%~dp0
set NODE=C:\Program Files\nodejs\node.exe
set VITE=%ROOT%frontend\node_modules\vite\bin\vite.js

"%NODE%" "%VITE%" "%ROOT%frontend" --port 5173
