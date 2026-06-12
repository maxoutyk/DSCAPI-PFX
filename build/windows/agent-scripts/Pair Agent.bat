@echo off
setlocal
cd /d "%~dp0"
title IG E-Sign Agent - Pairing

if not exist "IG-E-Sign-Agent.exe" (
  echo ERROR: IG-E-Sign-Agent.exe was not found in:
  echo   %CD%
  pause
  exit /b 1
)

set "API_BASE="
if exist portal.url (
  for /f "usebackq tokens=1,* delims==" %%A in (`findstr /b "api_base=" portal.url`) do set "API_BASE=%%B"
)
if "%API_BASE%"=="" (
  echo Open your IG E-Sign portal - USB Agent page - and note the portal URL.
  set /p API_BASE=Portal URL ^(e.g. http://192.168.1.53:8000^): 
)
set /p CODE=Pairing code from USB Agent page: 
echo.
"IG-E-Sign-Agent.exe" pair --api-base "%API_BASE%" --code "%CODE%"
if errorlevel 1 (
  echo.
  echo Pairing failed. Check the portal URL and pairing code, then try again.
  pause
  exit /b 1
)
if exist .paired del .paired
echo paired> .paired
echo.
echo Paired successfully. You can now run "Start Agent.bat".
pause
