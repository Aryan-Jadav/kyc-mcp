@echo off
echo KYC MCP Server - Digital Ocean Deployment
echo ==========================================

REM Configuration - UPDATE THESE VALUES
set SERVER_IP=139.59.70.153
set SERVER_USER=root
set PROJECT_DIR=/root/kyc-mcp-server

echo.
echo Please update the SERVER_IP in this script before running!
echo Current SERVER_IP: %SERVER_IP%
echo.

if "%SERVER_IP%"=="YOUR_DROPLET_IP" (
    echo ERROR: Please update SERVER_IP in the script first!
    pause
    exit /b 1
)

echo Step 1: Creating project archive...
tar -czf kyc-mcp-server.tar.gz ^
    --exclude=venv ^
    --exclude=__pycache__ ^
    --exclude=*.db ^
    --exclude=*.log ^
    --exclude=.git ^
    *.py *.txt *.yml *.sh .env* .dockerignore Dockerfile README.md TROUBLESHOOTING.md

if %ERRORLEVEL% NEQ 0 (
    echo ERROR: Failed to create archive
    pause
    exit /b 1
)

echo ✓ Archive created successfully

echo.
echo Step 2: Uploading to Digital Ocean...
scp kyc-mcp-server.tar.gz %SERVER_USER%@%SERVER_IP%:/root/

if %ERRORLEVEL% NEQ 0 (
    echo ERROR: Failed to upload archive
    pause
    exit /b 1
)

echo ✓ Archive uploaded successfully

echo.
echo Step 3: Extracting and setting up on server...
ssh %SERVER_USER%@%SERVER_IP% "cd /root && rm -rf %PROJECT_DIR% && mkdir -p %PROJECT_DIR% && cd %PROJECT_DIR% && tar -xzf /root/kyc-mcp-server.tar.gz && rm /root/kyc-mcp-server.tar.gz"

if %ERRORLEVEL% NEQ 0 (
    echo ERROR: Failed to extract on server
    pause
    exit /b 1
)

echo ✓ Files extracted on server

echo.
echo Step 4: Setting up environment and deploying...
ssh %SERVER_USER%@%SERVER_IP% "cd %PROJECT_DIR% && cp .env.docker .env && chmod +x deploy.sh && ./deploy.sh"

if %ERRORLEVEL% NEQ 0 (
    echo ERROR: Deployment failed
    pause
    exit /b 1
)

echo.
echo ✓ Deployment completed successfully!
echo.
echo Your KYC MCP Server is now running on:
echo   Health Check: http://%SERVER_IP%:8000/health
echo   API Docs: http://%SERVER_IP%:8000/docs
echo   API Status: http://%SERVER_IP%:8000/api/status
echo.
echo To check logs: ssh %SERVER_USER%@%SERVER_IP% "cd %PROJECT_DIR% && docker-compose logs -f"
echo.

REM Clean up local archive
del kyc-mcp-server.tar.gz

pause
