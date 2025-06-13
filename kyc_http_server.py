#!/usr/bin/env python3
"""
HTTP API Server for KYC MCP Integration with n8n

This server exposes the KYC MCP functionality as REST API endpoints
that can be called from n8n workflows.
"""

import os
import json
import logging
import asyncio
from typing import Dict, Any, Optional
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import uvicorn

# Load environment variables
try:
    from dotenv import load_dotenv
    load_dotenv()
    print("Environment variables loaded from .env file")
except ImportError:
    print("python-dotenv not installed, skipping .env file loading")
except Exception as e:
    print(f"Could not load .env file: {e}")

# Import MCP components
from kyc_client import KYCClient
from config import ENDPOINTS, SUREPASS_API_TOKEN
from database import db_manager
from config_db import DATABASE_ENABLED
from universal_database import universal_db_manager

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)
logger = logging.getLogger("kyc-http-server")

# FastAPI app
app = FastAPI(
    title="KYC Verification API",
    description="HTTP API for KYC verification services using SurePass",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# Add CORS middleware for n8n integration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure this properly for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global KYC client
kyc_client: Optional[KYCClient] = None

# Pydantic models for request/response
class PANVerificationRequest(BaseModel):
    id_number: str = Field(..., description="PAN number to verify", example="ABCDE1234F")

class BasicVerificationRequest(BaseModel):
    id_number: str = Field(..., description="ID number to verify")

class PANAadhaarLinkRequest(BaseModel):
    pan_number: str = Field(..., description="PAN number")
    aadhaar_number: str = Field(..., description="Aadhaar number")

class BankVerificationRequest(BaseModel):
    id_number: str = Field(..., description="Account number")
    ifsc: str = Field(..., description="IFSC code")
    authorization_token: Optional[str] = Field(None, description="Optional authorization token")

class APIResponse(BaseModel):
    success: bool
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    message: Optional[str] = None

# Startup and shutdown events
@app.on_event("startup")
async def startup_event():
    """Initialize KYC client and database on startup"""
    global kyc_client
    try:
        # Initialize KYC client
        kyc_client = KYCClient()
        await kyc_client.__aenter__()
        logger.info("KYC client initialized")

        # Initialize database
        if DATABASE_ENABLED:
            await db_manager.initialize()
            await universal_db_manager.initialize()
            logger.info("Database managers initialized")
        else:
            logger.info("Database storage is disabled")

        logger.info("HTTP server startup completed")
    except Exception as e:
        logger.error(f"Failed to initialize services: {str(e)}")
        raise e

@app.on_event("shutdown")
async def shutdown_event():
    """Clean up resources on shutdown"""
    global kyc_client
    try:
        if kyc_client:
            await kyc_client.__aexit__(None, None, None)
            await kyc_client.close()
            logger.info("KYC client closed")

        if DATABASE_ENABLED:
            await db_manager.close()
            await universal_db_manager.close()
            logger.info("Database connections closed")

        logger.info("HTTP server shutdown completed")
    except Exception as e:
        logger.error(f"Error during shutdown: {str(e)}")

# Health check endpoint
@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "KYC Verification API",
        "api_token_configured": bool(SUREPASS_API_TOKEN),
        "client_initialized": kyc_client is not None
    }

# API Status endpoint
@app.get("/api/status")
async def api_status():
    """Check API connectivity and token validity"""
    if not kyc_client:
        raise HTTPException(status_code=503, detail="KYC client not initialized")
    
    if not SUREPASS_API_TOKEN:
        raise HTTPException(status_code=500, detail="API token not configured")
    
    try:
        # Test API connectivity with a dummy request
        data = {"id_number": "TEMP123"}
        response = await kyc_client.post_json(ENDPOINTS["pan_comprehensive"], data)
        
        if response.status_code == 401:
            raise HTTPException(status_code=401, detail="Invalid API token")
        elif response.status_code == 403:
            raise HTTPException(status_code=403, detail="API token lacks required permissions")
        elif response.status_code is None:
            raise HTTPException(status_code=503, detail=f"Network error: {response.error}")
        
        return {
            "status": "ready",
            "message": "API client ready and token validated",
            "status_code": response.status_code
        }
    except Exception as e:
        logger.error(f"API status check failed: {str(e)}")
        raise HTTPException(status_code=503, detail=f"API status check failed: {str(e)}")

# PAN Verification Endpoints
@app.post("/api/verify/pan/basic", response_model=APIResponse)
async def verify_pan_basic(request: PANVerificationRequest):
    """Basic PAN verification"""
    if not kyc_client:
        raise HTTPException(status_code=503, detail="KYC client not initialized")
    
    try:
        import re
        if not re.match(r'^[A-Z]{5}[0-9]{4}[A-Z]$', request.id_number):
            raise HTTPException(status_code=400, detail="Invalid PAN format. PAN should be in format AAAAA9999A")
        
        data = {"id_number": request.id_number}
        response = await kyc_client.post_json(ENDPOINTS["pan"], data)
        
        if not response.success:
            return APIResponse(
                success=False,
                error=response.error,
                message=response.message
            )
        
        return APIResponse(
            success=True,
            data=response.data,
            message=response.message or "PAN verification completed"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in basic PAN verification: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/verify/pan/comprehensive", response_model=APIResponse)
async def verify_pan_comprehensive(request: PANVerificationRequest):
    """Comprehensive PAN verification with detailed information"""
    if not kyc_client:
        raise HTTPException(status_code=503, detail="KYC client not initialized")
    
    try:
        import re
        if not re.match(r'^[A-Z]{5}[0-9]{4}[A-Z]$', request.id_number):
            raise HTTPException(status_code=400, detail="Invalid PAN format. PAN should be in format AAAAA9999A")
        
        data = {"id_number": request.id_number}
        response = await kyc_client.post_json(ENDPOINTS["pan_comprehensive"], data)
        
        if not response.success:
            return APIResponse(
                success=False,
                error=response.error,
                message=response.message
            )
        
        return APIResponse(
            success=True,
            data=response.data,
            message=response.message or "PAN comprehensive verification completed"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in comprehensive PAN verification: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/verify/pan/kra", response_model=APIResponse)
async def verify_pan_kra(request: PANVerificationRequest):
    """PAN verification using KRA database"""
    if not kyc_client:
        raise HTTPException(status_code=503, detail="KYC client not initialized")
    
    try:
        import re
        if not re.match(r'^[A-Z]{5}[0-9]{4}[A-Z]$', request.id_number):
            raise HTTPException(status_code=400, detail="Invalid PAN format. PAN should be in format AAAAA9999A")
        
        data = {"id_number": request.id_number}
        response = await kyc_client.post_json(ENDPOINTS["pan_kra"], data)
        
        if not response.success:
            return APIResponse(
                success=False,
                error=response.error,
                message=response.message
            )
        
        return APIResponse(
            success=True,
            data=response.data,
            message=response.message or "PAN KRA verification completed"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in PAN KRA verification: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# Additional verification endpoints can be added here...

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    host = os.getenv("HOST", "0.0.0.0")
    
    logger.info(f"Starting KYC HTTP server on {host}:{port}")
    uvicorn.run(
        "kyc_http_server:app",
        host=host,
        port=port,
        reload=False,
        log_level="info"
    )
