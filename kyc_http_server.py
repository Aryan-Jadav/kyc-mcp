#!/usr/bin/env python3
"""
HTTP API Server for KYC MCP Integration with n8n

This server exposes the KYC MCP functionality as both:
1. REST API endpoints for traditional HTTP requests
2. Server-Sent Events (SSE) endpoints for MCP client integration

Both interfaces provide the same KYC verification capabilities.
"""

import os
import json
import logging
import asyncio
from typing import Dict, Any, Optional
from fastapi import FastAPI, HTTPException, BackgroundTasks, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
import uvicorn
import httpx

# Import KYC components

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
    title="KYC Verification API with MCP SSE Support",
    description="HTTP API for KYC verification services using SurePass. Supports both REST API and MCP Server-Sent Events.",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    root_path="/mcp"
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
        logger.info("🚀 Starting KYC HTTP server initialization...")

        # Check environment variables
        if not SUREPASS_API_TOKEN:
            logger.error("❌ SUREPASS_API_TOKEN environment variable is not set!")
            logger.error("Please set the API token before starting the server")
        else:
            logger.info("✅ API token is configured")

        # Initialize KYC client for REST API
        logger.info("Initializing KYC client for REST API...")
        kyc_client = KYCClient()
        await kyc_client.__aenter__()
        logger.info("✅ KYC client initialized successfully")



        # Initialize database only if enabled
        if DATABASE_ENABLED:
            try:
                logger.info("Initializing database managers...")
                await db_manager.initialize()
                await universal_db_manager.initialize()
                logger.info("✅ Database managers initialized successfully")
            except Exception as db_error:
                logger.warning(f"⚠️ Database initialization failed: {db_error}")
                logger.info("Continuing without database storage")
        else:
            logger.info("Database storage is disabled")

        logger.info("🎉 HTTP server startup completed successfully")
    except Exception as e:
        logger.error(f"❌ Failed to initialize services: {str(e)}")
        logger.error("Server will start but API endpoints may not work properly")
        # Don't raise the error, continue without database
        logger.info("Continuing with limited functionality")

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
            try:
                await db_manager.close()
                await universal_db_manager.close()
                logger.info("Database connections closed")
            except Exception as db_error:
                logger.warning(f"Error closing database: {db_error}")

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
        "client_initialized": kyc_client is not None,
        "endpoints": {
            "rest_api": "/api/",
            "universal_endpoint": "/mcp/universal-verify"
        }
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

# Universal endpoint for custom GPT integration
@app.post("/universal-verify")
async def universal_verify(request: Request):
    """
    Universal endpoint for custom GPT integration
    Accepts tool name and parameters, routes to appropriate KYC service
    """
    try:
        # Parse JSON body
        try:
            body = await request.json()
        except Exception as json_error:
            logger.error(f"JSON parsing error: {json_error}")
            return JSONResponse({
                "success": False,
                "error": "Invalid JSON in request body",
                "message": "Please provide valid JSON",
                "data": None
            }, status_code=400)

        tool = body.get("tool")
        params = body.get("params", {})

        logger.info(f"Universal verify request - Tool: {tool}, Params: {params}")

        # Validate tool parameter
        if not tool:
            return JSONResponse({
                "success": False,
                "error": "Tool parameter is required",
                "message": "Please specify a tool name (e.g., 'pan', 'pan_comprehensive', 'pan_kra')",
                "data": None
            }, status_code=400)

        # Check if tool exists
        if tool not in ENDPOINTS:
            available_tools = list(ENDPOINTS.keys())
            return JSONResponse({
                "success": False,
                "error": f"Tool '{tool}' not supported",
                "message": f"Available tools: {', '.join(available_tools)}",
                "data": None
            }, status_code=400)

        # Check if KYC client is initialized
        if not kyc_client:
            return JSONResponse({
                "success": False,
                "error": "KYC service not available",
                "message": "KYC client not initialized. Please try again later.",
                "data": None
            }, status_code=503)

        # Validate params for PAN tools
        if tool.startswith("pan") and not params.get("id_number"):
            return JSONResponse({
                "success": False,
                "error": "Missing required parameter",
                "message": "PAN verification requires 'id_number' parameter",
                "data": None
            }, status_code=400)

        # Make the verification request
        logger.info(f"Making KYC request to endpoint: {ENDPOINTS[tool]}")
        response = await kyc_client.post_json(ENDPOINTS[tool], params)

        # Determine HTTP status code
        http_status = 200
        if not response.success:
            if response.status_code:
                http_status = 400 if response.status_code == 422 else response.status_code
            else:
                http_status = 500

        # Return standardized response
        return JSONResponse({
            "success": response.success,
            "data": response.data,
            "error": response.error,
            "message": response.message or f"{tool} verification completed"
        }, status_code=http_status)

    except Exception as e:
        logger.error(f"Unexpected error in universal verify: {str(e)}", exc_info=True)
        return JSONResponse({
            "success": False,
            "error": f"Internal server error: {str(e)}",
            "message": "Verification request failed due to server error",
            "data": None
        }, status_code=500)

from fastapi import APIRouter, Request
from langchain_agent import ask_agent

@app.post("/langchain/ask")
async def langchain_ask(request: Request):
    data = await request.json()
    question = data.get("question")
    if not question:
        return JSONResponse({"success": False, "error": "Missing 'question' in request."}, status_code=400)
    try:
        # Run the agent (sync for now; can be made async if needed)
        result = ask_agent(question)
        return JSONResponse({"success": True, "result": result})
    except Exception as e:
        logger.error(f"LangChain agent error: {e}", exc_info=True)
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)

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
