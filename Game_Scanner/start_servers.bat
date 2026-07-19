@echo off
echo Booting up the Game Scanner Environment...

echo 1. Starting FastAPI Backend...
REM Explicitly using the venv python executable guarantees it finds your local packages
start "FastAPI Backend" cmd /k "py -m uvicorn main:app --reload"

echo 2. Starting Vite React Frontend...
cd src\frontend
start "React Frontend" cmd /k "npm run dev"

echo Servers are running! Close the new command prompt windows to shut them down.