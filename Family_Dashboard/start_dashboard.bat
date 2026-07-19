@echo off
title Weather Dashboard Runner
echo ==============================================
echo   STARTING COMMAND CENTER WEATHER STACK
echo ==============================================

:: 1. Launch the Python Backend in a minimized window
echo Launcher: Starting FastAPI backend server...
start /min "Weather Backend" cmd /c "python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload"

:: 2. Launch the React Frontend in a minimized window
echo Launcher: Starting Vite frontend server...
start /min "Weather Frontend" cmd /c "cd frontend && npm run dev"

echo ----------------------------------------------
echo   Both servers are running in the background!
echo   Frontend: http://localhost:5173
echo   Backend:  http://localhost:8000
echo ----------------------------------------------
echo   Keep this window open, or close it when ready.
echo   To stop the servers completely, run 'stop_dashboard.bat'.
echo ==============================================
pause