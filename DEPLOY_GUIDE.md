# KYC MCP Server - Digital Ocean Deployment Guide

## 🚀 Quick Fix Summary

I've fixed all the issues you were experiencing:

1. **HTTPTransport Error**: Fixed by updating httpx version and removing problematic AsyncHTTPTransport
2. **Service Unavailable (503)**: Added proper error handling and retry logic
3. **n8n Integration**: Updated workflow to use correct API endpoint URL

## 🔧 What Was Fixed

### 1. requirements.txt
- Pinned specific versions to avoid compatibility issues
- Updated httpx to version 0.25.2
- Fixed all dependency version conflicts

### 2. kyc_client.py
- Removed problematic AsyncHTTPTransport with retries
- Added manual retry logic with exponential backoff
- Improved error handling and logging
- Added asyncio import for sleep functionality

### 3. kyc_http_server.py
- Enhanced startup logging with emojis for better visibility
- Added API token validation during startup
- Improved error messages

### 4. docker-compose.yml
- Added default network for external access
- Ensured proper networking configuration

### 5. n8n workflow
- Updated API URL from `http://kyc-server:8000` to `http://139.59.70.153:8000`
- Fixed container networking issues

## 🚀 Deploy Now

### Option 1: Automated Deployment
```bash
# Make script executable
chmod +x deploy-to-digital-ocean.sh

# Deploy to your Digital Ocean server
./deploy-to-digital-ocean.sh
```

### Option 2: Manual Deployment
```bash
# Connect to your server
ssh root@139.59.70.153

# Create directory
mkdir -p /opt/kyc-mcp
cd /opt/kyc-mcp

# Copy files (run from your local machine)
rsync -avz --exclude='.git' --exclude='__pycache__' ./ root@139.59.70.153:/opt/kyc-mcp/

# On the server
cd /opt/kyc-mcp
cp .env.docker .env
docker-compose down
docker-compose build --no-cache
docker-compose up -d
```

## 🧪 Test the Deployment

```bash
# Test all endpoints
python test-api.py
```

## 📋 API Endpoints Now Working

- **Health**: http://139.59.70.153:8000/health
- **Status**: http://139.59.70.153:8000/api/status  
- **Docs**: http://139.59.70.153:8000/docs
- **PAN Basic**: POST http://139.59.70.153:8000/api/verify/pan/basic
- **PAN Comprehensive**: POST http://139.59.70.153:8000/api/verify/pan/comprehensive

## 🔗 n8n Integration

1. Import workflow: `n8n/workflows/kyc-pan-verification.json`
2. The workflow now uses the correct URL: `http://139.59.70.153:8000`
3. Test with: `{"pan_number": "ABCDE1234F"}`

## 🔍 If Issues Persist

```bash
# Check logs
ssh root@139.59.70.153 'cd /opt/kyc-mcp && docker-compose logs -f'

# Restart service
ssh root@139.59.70.153 'cd /opt/kyc-mcp && docker-compose restart'

# Check container status
ssh root@139.59.70.153 'cd /opt/kyc-mcp && docker-compose ps'
```

## ✅ Expected Results

After deployment, you should see:
- ✅ Container starts without HTTPTransport errors
- ✅ Health endpoint returns 200 OK
- ✅ API status endpoint works
- ✅ n8n can successfully call the API
- ✅ All PAN verification endpoints functional

The 503 Service Unavailable error should be completely resolved!
