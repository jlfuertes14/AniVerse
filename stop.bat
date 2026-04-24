@echo off
echo Stopping Anime Discovery Engine...
taskkill /f /fi "WINDOWTITLE eq Backend - FastAPI" >nul 2>&1
taskkill /f /fi "WINDOWTITLE eq Frontend - Next.js" >nul 2>&1
echo Done!
pause
