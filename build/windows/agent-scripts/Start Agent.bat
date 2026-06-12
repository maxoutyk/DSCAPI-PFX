@echo off
setlocal
cd /d "%~dp0"
title IG E-Sign Agent

if not exist "IG-E-Sign-Agent.exe" (
  echo ERROR: IG-E-Sign-Agent.exe was not found in:
  echo   %CD%
  pause
  exit /b 1
)

echo IG E-Sign Agent
echo Keep this window open while signing from the portal.
echo.
"IG-E-Sign-Agent.exe" run
echo.
echo Agent stopped ^(exit code %ERRORLEVEL%^).
pause
