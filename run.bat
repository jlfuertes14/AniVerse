@echo off
title Anime Discovery Engine
echo.
echo  ========================================
echo   Anime Discovery Engine - Starting...
echo  ========================================
echo.

:: Start Backend
echo [1/2] Starting FastAPI backend on port 8000...
start "Backend - FastAPI" cmd /k "cd /d %~dp0 && python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload"

:: Wait a moment for backend to start
timeout /t 3 /nobreak >nul

:: Start Frontend
echo [2/2] Starting Next.js frontend on port 3000...
start "Frontend - Next.js" cmd /k "cd /d %~dp0frontend && npx next dev --port 3000"

:: Wait and open browser
timeout /t 5 /nobreak >nul
echo.
echo  ========================================
echo   Opening http://localhost:3000 ...
echo  ========================================
start http://localhost:3000

echo.
echo  Backend:  http://localhost:8000/docs
echo  Frontend: http://localhost:3000
echo.
echo  Close both terminal windows to stop.
pause
