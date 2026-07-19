@echo off
:: Force the script to start in the correct directory
cd /d "D:\_CodingProjects\Game_Scanner"

:: Explicitly activate the virtual environment
::call venv\Scripts\activate

:: Run the scanner and capture the output. 
:: The %1 captures the argument (daily, weekly, monthly) passed from Task Scheduler
venv\Scripts\python.exe scanner.py %1 >> scanner_log.txt 2>&1