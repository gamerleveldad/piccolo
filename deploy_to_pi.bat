@echo off
echo ==============================================
echo Pushing Unified Stack to Raspberry Pi 5
echo ==============================================

set PI_IP=192.168.4.55
set PI_USER=pi
set DEST_DIR=/home/%PI_USER%/homelab

echo Step 1: Creating target directory on host...
ssh %PI_USER%@%PI_IP% "mkdir -p %DEST_DIR%"

echo Step 2: Transferring source files via SCP...
:: Excludes node_modules and python cache via your existing .dockerignore
scp -r . %PI_USER%@%PI_IP%:%DEST_DIR%

echo Step 3: Rebuilding Docker Compose Architecture...
ssh %PI_USER%@%PI_IP% "cd %DEST_DIR% && docker compose up -d --build --remove-orphans"

echo ==============================================
echo Deployment and Compilation Complete.
echo ==============================================
pause