@echo off
setlocal
cd /d "%~dp0"
title IG E-Sign Agent - Pairing
set "API_BASE="
if exist portal.url (
  for /f "usebackq tokens=1,* delims==" %%A in (`findstr /b "api_base=" portal.url`) do set "API_BASE=%%B"
)
if "%API_BASE%"=="" (
  echo Open your IG E-Sign portal - USB Agent page - and note the portal URL.
  set /p API_BASE=Portal URL (e.g. https://sign.incitegravity.com): 
)
set /p CODE=Pairing code from USB Agent page: 
"IG-E-Sign-Agent.exe" pair --api-base "%API_BASE%" --code "%CODE%"
echo.
if exist .paired del .paired
echo paired> .paired
pause
