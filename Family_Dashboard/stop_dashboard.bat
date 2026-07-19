@echo off
title Weather Dashboard Killer
echo ==============================================
echo   STOPPING WEATHER DASHBOARD SERVERS 
echo ==============================================

echo Launcher: Terminating Python Uvicorn processes...
taskkill /FI "WINDOWTITLE eq Weather Backend*" /T /F >nul 2>&1
taskkill /IM python.exe /F >nul 2>&1

echo Launcher: Terminating Node/Vite processes...
taskkill /FI "WINDOWTITLE eq Weather Frontend*" /T /F >nul 2>&1
taskkill /IM node.exe /F >nul 2>&1

echo ==============================================
echo   All servers stopped successfully!
echo ==============================================
timeout /t 3