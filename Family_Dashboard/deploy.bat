@echo off
echo ==============================================
echo Pushing Project to Debian Server...
echo ==============================================
set DEBIAN_IP=192.168.4.50
set DEBIAN_USER=dashb
set DEST_DIR=/home/%DEBIAN_USER%/howls-dashboard

ssh %DEBIAN_USER%@%DEBIAN_IP% "mkdir -p %DEST_DIR%"
scp -r * %DEBIAN_USER%@%DEBIAN_IP%:%DEST_DIR%

echo ==============================================
echo Rebuilding Docker Container...
echo ==============================================
:: Update the last line of your deploy.bat to this:
ssh %DEBIAN_USER%@%DEBIAN_IP% "cd %DEST_DIR% && sudo docker compose up -d --build --remove-orphans"

echo Deployment Complete.
pause