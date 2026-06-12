@echo off
setlocal
cd /d "%~dp0"
title IG E-Sign Agent
echo IG E-Sign Agent - keep this window open while signing from the portal.
echo.
"IG-E-Sign-Agent.exe" run
if errorlevel 1 pause
