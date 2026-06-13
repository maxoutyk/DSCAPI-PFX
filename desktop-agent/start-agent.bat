@echo off
setlocal
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
  echo Python 3 is required. Install from https://www.python.org/downloads/
  exit /b 1
)

set "API_BASE="
if exist portal.url (
  for /f "tokens=1,* delims==" %%A in ('findstr /b "api_base=" portal.url') do set "API_BASE=%%B"
)
if "%API_BASE%"=="" set /p API_BASE=Portal URL (e.g. https://sign.incitegravity.com): 

if not exist .paired (
  set /p CODE=Enter pairing code from USB Agent page: 
  python agent.py pair --api-base "%API_BASE%" --code "%CODE%"
  echo paired> .paired
)

echo Starting agent in the system tray (near the clock)...
python agent.py run --port 9765
