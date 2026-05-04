@echo off
echo Stopping Anime Discovery Engine...
taskkill /f /fi "WINDOWTITLE eq Backend - FastAPI" >nul 2>&1
taskkill /f /fi "WINDOWTITLE eq Frontend - Next.js" >nul 2>&1
taskkill /f /fi "IMAGENAME eq python.exe" /fi "WINDOWTITLE eq Backend - FastAPI" >nul 2>&1
for /f "tokens=2" %%i in ('wmic process where "name='python.exe' and executablepath like '%%Anime Discovery Engine%%.venv%%python.exe'" get processid ^| findstr /r "[0-9]"') do taskkill /f /pid %%i >nul 2>&1
for /f "tokens=2" %%i in ('wmic process where "name='node.exe' and executablepath like '%%ms-playwright-go%%'" get processid ^| findstr /r "[0-9]"') do taskkill /f /pid %%i >nul 2>&1
echo Done!
pause
 
