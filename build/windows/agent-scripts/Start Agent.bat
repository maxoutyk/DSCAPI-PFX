@echo off
setlocal
cd /d "%~dp0"

if not exist "IG-E-Sign-Agent.exe" (
  echo ERROR: IG-E-Sign-Agent.exe was not found in:
  echo   %CD%
  pause
  exit /b 1
)

start "" "IG-E-Sign-Agent.exe" run
