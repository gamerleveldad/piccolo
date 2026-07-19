@echo off
echo ==============================================
echo [1/3] Compiling React UI Locally...
echo ==============================================
cd frontend
call npm run build
cd ..

echo ==============================================
echo [2/3] Staging files on the server...
echo ==============================================
set SERVER_IP=192.168.4.50
set SERVER_USER=dashb

ssh %SERVER_USER%@%SERVER_IP% "mkdir -p /tmp/dashboard-ui"
scp -r frontend/dist/* %SERVER_USER%@%SERVER_IP%:/tmp/dashboard-ui/

echo ==============================================
echo [3/3] Hot-Swapping into active container...
echo ==============================================
:: This injects the new files into the running container and cleans up
ssh %SERVER_USER%@%SERVER_IP% "sudo docker cp /tmp/dashboard-ui/. howls-dashboard:/app/static/ && rm -rf /tmp/dashboard-ui"

echo ==============================================
echo UI Hot-Swap Complete! Refresh your browser.
echo ==============================================
pause