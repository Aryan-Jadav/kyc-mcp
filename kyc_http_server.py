#!/usr/bin/env python3
"""
COMPLETE FIXED: HTTP API Server for KYC MCP Integration with Google Drive Storage
This server exposes KYC functionality with proper data storage in both database and Google Drive.
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

# Import Google Drive storage
try:
    from google_drive_storage import google_drive_storage
    GOOGLE_DRIVE_AVAILABLE = True
    print("Google Drive storage available")
except ImportError as e:
    google_drive_storage = None
    GOOGLE_DRIVE_AVAILABLE = False
    print(f"Google Drive not available: {e}")

# Import LangChain components
try:
    from enhanced_langchain_agent import ask_agent, get_agent, EnhancedKYCAgent
    LANGCHAIN_AVAILABLE = True
    print("LangChain integration available")
except ImportError as e:
    LANGCHAIN_AVAILABLE = False
    print(f"LangChain not available: {e}")

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)
logger = logging.getLogger("kyc-http-server")

# FastAPI app
app = FastAPI(
    title="KYC Verification API with Enhanced Storage",
    description="HTTP API for KYC verification services with database and Google Drive storage.",
    version="2.1.0",
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

class DatabaseSearchRequest(BaseModel):
    search_value: str = Field(..., description="Value to search for")
    search_type: str = Field(default="pan", description="Type of search (pan, name, phone, email)")

class APIResponse(BaseModel):
    success: bool
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    message: Optional[str] = None

# LangChain-specific models
class ChatRequest(BaseModel):
    message: str = Field(..., description="User message or question")
    session_id: Optional[str] = Field(None, description="Optional session ID for conversation continuity")
    clear_history: Optional[bool] = Field(False, description="Clear conversation history")

class ChatResponse(BaseModel):
    response: str = Field(..., description="Agent response")
    session_id: Optional[str] = Field(None, description="Session ID")
    success: bool = Field(True, description="Success status")
    error: Optional[str] = Field(None, description="Error message if failed")

# Enhanced storage function
async def store_verification_data_sheets_only(response_data: Dict[str, Any], api_endpoint: str) -> Dict[str, Any]:
    """Store verification data only in Google Sheets with single folder structure"""
    storage_result = {
        'sheets_stored': False,
        'record_id': None,
        'errors': []
    }
    
    try:
        # Store only in Google Sheets
        logger.info(f"📊 Storing in Google Sheets for endpoint: {api_endpoint}")
        
        # Initialize universal database manager if not already done
        if not universal_db_manager.initialized:
            await universal_db_manager.initialize()
        
        if universal_db_manager.initialized:
            verification_type = api_endpoint.split('/')[-1].replace('-', '_')
            
            # Store verification data in Google Sheets
            stored_record = await universal_db_manager.store_verification_data(
                response_data, api_endpoint, verification_type
            )
            
            if stored_record:
                storage_result['sheets_stored'] = True
                storage_result['record_id'] = stored_record.get('id', 'unknown')
                logger.info(f"✅ Google Sheets storage successful: {storage_result['record_id']}")
            else:
                storage_result['errors'].append("Google Sheets storage returned None")
                logger.warning("⚠️ Google Sheets storage returned None")
        else:
            storage_result['errors'].append("Google Sheets not initialized")
            logger.warning("⚠️ Google Sheets not initialized")
                    
    except Exception as e:
        error_msg = f"Google Sheets storage failed: {str(e)}"
        storage_result['errors'].append(error_msg)
        logger.error(f"❌ {error_msg}")
    
    return storage_result

# Startup and shutdown events
@app.on_event("startup")
async def startup_event():
    """Initialize KYC client and database on startup"""
    global kyc_client
    try:
        logger.info("🚀 Starting Enhanced KYC HTTP server initialization...")

        # Check environment variables
        if not SUREPASS_API_TOKEN:
            logger.error("❌ SUREPASS_API_TOKEN environment variable is not set!")
            logger.error("Please set the API token before starting the server")
        else:
            logger.info("✅ API token is configured")

        # Check OpenAI API key for LangChain
        if LANGCHAIN_AVAILABLE:
            openai_key = os.getenv("OPENAI_API_KEY")
            if openai_key:
                logger.info("✅ OpenAI API key configured for LangChain")
            else:
                logger.warning("⚠️ OpenAI API key not found - LangChain features may not work")

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

        # Initialize Google Drive storage
        if GOOGLE_DRIVE_AVAILABLE and google_drive_storage:
            try:
                logger.info("Initializing Google Drive storage...")
                await google_drive_storage.initialize()
                logger.info("✅ Google Drive storage initialized successfully")
                
                # Get storage statistics
                stats = await google_drive_storage.get_storage_statistics()
                logger.info(f"📊 Google Drive folders: {len(stats.get('folders', {}))}")
                
            except Exception as drive_error:
                logger.warning(f"⚠️ Google Drive initialization failed: {drive_error}")
                logger.info("Continuing without Google Drive storage")
        else:
            logger.info("Google Drive storage not available")

        logger.info("🎉 Enhanced HTTP server startup completed successfully")
    except Exception as e:
        logger.error(f"❌ Failed to initialize services: {str(e)}")
        logger.error("Server will start but API endpoints may not work properly")

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

        if GOOGLE_DRIVE_AVAILABLE and google_drive_storage:
            try:
                await google_drive_storage.close()
                logger.info("Google Drive storage closed")
            except Exception as drive_error:
                logger.warning(f"Error closing Google Drive: {drive_error}")

        logger.info("Enhanced HTTP server shutdown completed")
    except Exception as e:
        logger.error(f"Error during shutdown: {str(e)}")

# Health check endpoint
@app.get("/health")
async def health_check():
    """Enhanced health check endpoint"""
    return {
        "status": "healthy",
        "service": "Enhanced KYC Verification API",
        "version": "2.1.0",
        "api_token_configured": bool(SUREPASS_API_TOKEN),
        "client_initialized": kyc_client is not None,
        "database_enabled": DATABASE_ENABLED,
        "google_drive_available": GOOGLE_DRIVE_AVAILABLE,
        "google_drive_initialized": google_drive_storage.initialized if google_drive_storage else False,
        "langchain_available": LANGCHAIN_AVAILABLE,
        "openai_configured": bool(os.getenv("OPENAI_API_KEY")) if LANGCHAIN_AVAILABLE else False,
        "endpoints": {
            "rest_api": "/api/",
            "universal_endpoint": "/universal-verify",
            "chat_agent": "/api/chat",
            "intelligent_verify": "/api/chat/verify",
            "database_search": "/api/database/"
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
        
        # Get storage status
        storage_status = {
            "database_enabled": DATABASE_ENABLED,
            "google_drive_available": GOOGLE_DRIVE_AVAILABLE,
            "google_drive_initialized": google_drive_storage.initialized if google_drive_storage else False
        }
        
        return {
            "status": "ready",
            "message": "API client ready and token validated",
            "status_code": response.status_code,
            "storage_status": storage_status,
            "langchain_status": "available" if LANGCHAIN_AVAILABLE else "not available"
        }
    except Exception as e:
        logger.error(f"API status check failed: {str(e)}")
        raise HTTPException(status_code=503, detail=f"API status check failed: {str(e)}")

# =============================================================================
# ENHANCED PAN VERIFICATION ENDPOINTS WITH STORAGE
# =============================================================================

@app.post("/api/verify/pan/basic", response_model=APIResponse)
async def verify_pan_basic(request: PANVerificationRequest):
    """Basic PAN verification with enhanced storage"""
    if not kyc_client:
        raise HTTPException(status_code=503, detail="KYC client not initialized")
    
    try:
        import re
        if not re.match(r'^[A-Z]{5}[0-9]{4}[A-Z]$', request.id_number):
            raise HTTPException(status_code=400, detail="Invalid PAN format. PAN should be in format AAAAA9999A")
        
        logger.info(f"🔍 Processing basic PAN verification for: {request.id_number}")
        
        data = {"id_number": request.id_number}
        response = await kyc_client.post_json(ENDPOINTS["pan"], data)
        
        # Enhanced storage logic
        storage_result = None
        if response.status_code == 200 and response.data:
            logger.info("💾 Starting enhanced storage process...")
            storage_result = await store_verification_data_sheets_only(
                response.data, 
                ENDPOINTS["pan"]
            )
            logger.info(f"📊 Storage result: {storage_result}")
        
        # Prepare response with storage info
        response_data = response.data.copy() if response.data else {}
        if storage_result:
            response_data['storage_info'] = storage_result
        
        return APIResponse(
            success=response.success,
            data=response_data,
            error=response.error,
            message=response.message or "PAN verification completed"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in basic PAN verification: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/verify/pan/comprehensive", response_model=APIResponse)
async def verify_pan_comprehensive(request: PANVerificationRequest):
    """Comprehensive PAN verification with enhanced storage"""
    if not kyc_client:
        raise HTTPException(status_code=503, detail="KYC client not initialized")
    
    try:
        import re
        if not re.match(r'^[A-Z]{5}[0-9]{4}[A-Z]$', request.id_number):
            raise HTTPException(status_code=400, detail="Invalid PAN format. PAN should be in format AAAAA9999A")
        
        logger.info(f"🔍 Processing comprehensive PAN verification for: {request.id_number}")
        
        data = {"id_number": request.id_number}
        response = await kyc_client.post_json(ENDPOINTS["pan_comprehensive"], data)
        
        # Enhanced storage logic
        storage_result = None
        if response.status_code == 200 and response.data:
            logger.info("💾 Starting enhanced storage process...")
            storage_result = await store_verification_data_sheets_only(
                response.data, 
                ENDPOINTS["pan_comprehensive"]
            )
            logger.info(f"📊 Storage result: {storage_result}")
        
        # Prepare response with storage info
        response_data = response.data.copy() if response.data else {}
        if storage_result:
            response_data['storage_info'] = storage_result
        
        return APIResponse(
            success=response.success,
            data=response_data,
            error=response.error,
            message=response.message or "PAN comprehensive verification completed"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in comprehensive PAN verification: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/verify/pan/kra", response_model=APIResponse)
async def verify_pan_kra(request: PANVerificationRequest):
    """PAN verification using KRA database with enhanced storage"""
    if not kyc_client:
        raise HTTPException(status_code=503, detail="KYC client not initialized")
    
    try:
        import re
        if not re.match(r'^[A-Z]{5}[0-9]{4}[A-Z]$', request.id_number):
            raise HTTPException(status_code=400, detail="Invalid PAN format. PAN should be in format AAAAA9999A")
        
        logger.info(f"🔍 Processing PAN KRA verification for: {request.id_number}")
        
        data = {"id_number": request.id_number}
        response = await kyc_client.post_json(ENDPOINTS["pan_kra"], data)
        
        # Enhanced storage logic
        storage_result = None
        if response.status_code == 200 and response.data:
            logger.info("💾 Starting enhanced storage process...")
            storage_result = await store_verification_data_sheets_only(
                response.data, 
                ENDPOINTS["pan_kra"]
            )
            logger.info(f"📊 Storage result: {storage_result}")
        
        # Prepare response with storage info
        response_data = response.data.copy() if response.data else {}
        if storage_result:
            response_data['storage_info'] = storage_result
        
        return APIResponse(
            success=response.success,
            data=response_data,
            error=response.error,
            message=response.message or "PAN KRA verification completed"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in PAN KRA verification: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# =============================================================================
# ENHANCED UNIVERSAL ENDPOINT WITH STORAGE
# =============================================================================

@app.post("/universal-verify")
async def universal_verify(request: Request):
    """Enhanced universal endpoint with comprehensive storage"""
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

        logger.info(f"🔧 Enhanced universal verify request - Tool: {tool}, Params: {params}")

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
        logger.info(f"🚀 Making enhanced API request to endpoint: {ENDPOINTS[tool]}")
        response = await kyc_client.post_json(ENDPOINTS[tool], params)

        # Enhanced storage logic
        storage_result = None
        if response.status_code == 200 and response.data:
            logger.info("💾 Starting enhanced storage process...")
            storage_result = await store_verification_data_sheets_only(
                response.data, 
                ENDPOINTS[tool]
            )
            logger.info(f"📊 Storage result: {storage_result}")

        # Determine HTTP status code
        http_status = 200
        if not response.success:
            if response.status_code:
                http_status = 400 if response.status_code == 422 else response.status_code
            else:
                http_status = 500

        # Prepare enhanced response
        response_data = response.data.copy() if response.data else {}
        if storage_result:
            response_data['storage_info'] = storage_result

        # Return standardized response
        return JSONResponse({
            "success": response.success,
            "data": response_data,
            "error": response.error,
            "message": response.message or f"{tool} verification completed"
        }, status_code=http_status)

    except Exception as e:
        logger.error(f"Unexpected error in enhanced universal verify: {str(e)}", exc_info=True)
        return JSONResponse({
            "success": False,
            "error": f"Internal server error: {str(e)}",
            "message": "Verification request failed due to server error",
            "data": None
        }, status_code=500)

# =============================================================================
# DATABASE SEARCH ENDPOINTS
# =============================================================================

@app.post("/api/database/search", response_model=APIResponse)
async def search_database(request: DatabaseSearchRequest):
    """Search database for stored verification data"""
    if not DATABASE_ENABLED:
        raise HTTPException(status_code=503, detail="Database storage is disabled")
    
    try:
        logger.info(f"🔍 Database search request: {request.search_type} = {request.search_value}")
        
        results = []
        
        if request.search_type == "pan":
            # Search by PAN
            record = await db_manager.search_by_pan(request.search_value.upper())
            if record:
                results = [record]
        elif request.search_type == "name":
            # Search by name
            records = await db_manager.search_by_name(request.search_value)
            results = records
        elif request.search_type == "phone":
            # Search by phone
            records = await db_manager.search_by_phone(request.search_value)
            results = records
        elif request.search_type == "email":
            # Search by email
            records = await db_manager.search_by_email(request.search_value)
            results = records
        else:
            raise HTTPException(status_code=400, detail="Invalid search type. Use: pan, name, phone, email")
        
        # Convert results to dict format
        formatted_results = []
        for result in results:
            if hasattr(result, 'to_dict'):
                formatted_results.append(result.to_dict())
            else:
                formatted_results.append(result)
        
        return APIResponse(
            success=True,
            data={
                'search_type': request.search_type,
                'search_value': request.search_value,
                'results_count': len(formatted_results),
                'results': formatted_results
            },
            message=f"Found {len(formatted_results)} results for {request.search_type}: {request.search_value}"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Database search error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/database/stats")
async def get_database_stats():
    """Get database statistics"""
    if not DATABASE_ENABLED:
        raise HTTPException(status_code=503, detail="Database storage is disabled")
    
    try:
        stats = await db_manager.get_statistics()
        return APIResponse(
            success=True,
            data=stats,
            message="Database statistics retrieved successfully"
        )
    except Exception as e:
        logger.error(f"Error getting database stats: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/database/recent/{limit}")
async def get_recent_records(limit: int = 10):
    """Get recent verification records"""
    if not DATABASE_ENABLED:
        raise HTTPException(status_code=503, detail="Database storage is disabled")
    
    try:
        if limit > 100:
            limit = 100  # Cap at 100 records
        
        records = await db_manager.get_all_records(limit=limit)
        
        # Convert to dict format
        formatted_records = []
        for record in records:
            if hasattr(record, 'to_dict'):
                formatted_records.append(record.to_dict())
            else:
                formatted_records.append(record)
        
        return APIResponse(
            success=True,
            data={
                'limit': limit,
                'count': len(formatted_records),
                'records': formatted_records
            },
            message=f"Retrieved {len(formatted_records)} recent records"
        )
    except Exception as e:
        logger.error(f"Error getting recent records: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# =============================================================================
# GOOGLE DRIVE ENDPOINTS
# =============================================================================

@app.get("/api/drive/stats")
async def get_drive_stats():
    """Get Google Drive storage statistics"""
    if not GOOGLE_DRIVE_AVAILABLE or not google_drive_storage:
        raise HTTPException(status_code=503, detail="Google Drive storage not available")
    
    if not google_drive_storage.initialized:
        raise HTTPException(status_code=503, detail="Google Drive storage not initialized")
    
    try:
        stats = await google_drive_storage.get_storage_statistics()
        return APIResponse(
            success=True,
            data=stats,
            message="Google Drive statistics retrieved successfully"
        )
    except Exception as e:
        logger.error(f"Error getting Google Drive stats: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/drive/files/{record_id}")
async def get_drive_files_by_record(record_id: str):
    """Get Google Drive files associated with a record ID"""
    if not GOOGLE_DRIVE_AVAILABLE or not google_drive_storage:
        raise HTTPException(status_code=503, detail="Google Drive storage not available")
    
    if not google_drive_storage.initialized:
        raise HTTPException(status_code=503, detail="Google Drive storage not initialized")
    
    try:
        files = await google_drive_storage.list_files_by_record(record_id)
        return APIResponse(
            success=True,
            data={
                'record_id': record_id,
                'file_count': len(files),
                'files': files
            },
            message=f"Found {len(files)} files for record {record_id}"
        )
    except Exception as e:
        logger.error(f"Error getting Drive files: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# =============================================================================
# UNIVERSAL FILE VERIFY AND OCR ENDPOINTS  
# =============================================================================

@app.post("/universal-verify-file")
async def universal_verify_file(request: Request):
    """Universal file verification endpoint for OCR and file-based tools"""
    try:
        # Parse form data
        form = await request.form()
        
        tool = form.get("tool")
        file_content_base64 = form.get("file_content_base64")
        file_name = form.get("file_name", "unknown")
        use_pdf = form.get("use_pdf", "true")
        authorization_token = form.get("authorization_token")
        
        # Handle file upload if base64 not provided
        file_upload = None
        if not file_content_base64:
            file_upload = form.get("file")
        
        logger.info(f"🔧 Universal file verify request - Tool: {tool}, File: {file_name}")

        # Validate tool parameter
        if not tool:
            return JSONResponse({
                "success": False,
                "error": "Tool parameter is required",
                "message": "Please specify an OCR tool name (e.g., 'ocr_pan', 'ocr_aadhaar')",
                "data": None
            }, status_code=400)

        # Check if tool exists in OCR endpoints
        ocr_tools = ["ocr_pan", "ocr_aadhaar", "ocr_passport", "ocr_license", 
                     "ocr_voter", "ocr_gst", "ocr_itr", "ocr_cheque", "ocr_document_detect"]
        if tool not in ocr_tools:
            return JSONResponse({
                "success": False,
                "error": f"Tool '{tool}' not supported",
                "message": f"Available OCR tools: {', '.join(ocr_tools)}",
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

        # Validate that either file content or file upload is provided
        if not file_content_base64 and not file_upload:
            return JSONResponse({
                "success": False,
                "error": "File required",
                "message": "Either file_content_base64 or file upload is required",
                "data": None
            }, status_code=400)

        # Make the OCR request using appropriate endpoint
        endpoint = ENDPOINTS.get(tool)
        if not endpoint:
            return JSONResponse({
                "success": False,
                "error": f"Endpoint not found for tool '{tool}'",
                "data": None
            }, status_code=400)

        # Prepare data for API call
        files = None
        data = {}
        
        if file_content_base64:
            # Use base64 content directly
            data = {
                'file_content_base64': file_content_base64,
                'file_name': file_name
            }
        elif file_upload:
            # Use file upload
            files = {'file': (file_upload.filename, file_upload.file, file_upload.content_type)}
        
        # Add additional parameters
        if tool == "ocr_itr":
            data['use_pdf'] = use_pdf
        if authorization_token:
            data['authorization_token'] = authorization_token

        logger.info(f"🚀 Making OCR API request to endpoint: {endpoint}")
        
        # Make the request
        if files:
            response = await kyc_client.post_form(endpoint, files, data, authorization_token=authorization_token)
        else:
            response = await kyc_client.post_json(endpoint, data, authorization_token=authorization_token)

        # Enhanced storage logic - only Google Sheets
        storage_result = None
        if response.status_code == 200 and response.data:
            logger.info("💾 Starting Google Sheets storage...")
            try:
                # Store only in Google Sheets
                stored_record = await universal_db_manager.store_verification_data(
                    response.data, endpoint, tool
                )
                if stored_record:
                    storage_result = {
                        'sheets_stored': True,
                        'record_id': stored_record.get('id', 'unknown')
                    }
                    logger.info(f"✅ Google Sheets storage successful: {storage_result['record_id']}")
                else:
                    storage_result = {'sheets_stored': False, 'error': 'Storage returned None'}
            except Exception as storage_error:
                logger.error(f"❌ Google Sheets storage error: {storage_error}")
                storage_result = {'sheets_stored': False, 'error': str(storage_error)}

        # Determine HTTP status code
        http_status = 200
        if not response.success:
            if response.status_code:
                http_status = 400 if response.status_code == 422 else response.status_code
            else:
                http_status = 500

        # Prepare response
        response_data = response.data.copy() if response.data else {}
        response_data['file_info'] = {'filename': file_name, 'tool_used': tool}
        if storage_result:
            response_data['storage_info'] = storage_result

        return JSONResponse({
            "success": response.success,
            "data": response_data,
            "error": response.error,
            "message": response.message or f"OCR processing completed for {tool}",
            "tool": tool,
            "status_code": response.status_code
        }, status_code=http_status)

    except Exception as e:
        error_msg = f"Universal file verify error: {str(e)}"
        logger.error(f"❌ {error_msg}")
        return JSONResponse({
            "success": False,
            "error": error_msg,
            "data": None
        }, status_code=500)

# OCR Endpoints - Individual endpoints for each OCR tool
@app.post("/api/ocr/pan")
async def ocr_pan_endpoint(request: Request):
    """PAN card OCR processing"""
    return await handle_ocr_request(request, "ocr_pan")

@app.post("/api/ocr/aadhaar")
async def ocr_aadhaar_endpoint(request: Request):
    """Aadhaar card OCR processing"""
    return await handle_ocr_request(request, "ocr_aadhaar")

@app.post("/api/ocr/passport")
async def ocr_passport_endpoint(request: Request):
    """Passport OCR processing"""
    return await handle_ocr_request(request, "ocr_passport")

@app.post("/api/ocr/license")
async def ocr_license_endpoint(request: Request):
    """Driving License OCR processing"""
    return await handle_ocr_request(request, "ocr_license")

@app.post("/api/ocr/voter")
async def ocr_voter_endpoint(request: Request):
    """Voter ID OCR processing"""
    return await handle_ocr_request(request, "ocr_voter")

@app.post("/api/ocr/gst")
async def ocr_gst_endpoint(request: Request):
    """GST document OCR processing"""
    return await handle_ocr_request(request, "ocr_gst")

@app.post("/api/ocr/itr")
async def ocr_itr_endpoint(request: Request):
    """ITR document OCR processing"""
    return await handle_ocr_request(request, "ocr_itr")

@app.post("/api/ocr/cheque")
async def ocr_cheque_endpoint(request: Request):
    """Cheque OCR processing"""
    return await handle_ocr_request(request, "ocr_cheque")

@app.post("/api/ocr/document-detect")
async def ocr_document_detect_endpoint(request: Request):
    """Document type detection using OCR"""
    return await handle_ocr_request(request, "ocr_document_detect")

async def handle_ocr_request(request: Request, tool_name: str):
    """Common handler for all OCR requests"""
    try:
        # Parse form data
        form = await request.form()
        
        file_content_base64 = form.get("file_content_base64")
        file_name = form.get("file_name", "unknown")
        use_pdf = form.get("use_pdf", "true")
        authorization_token = form.get("authorization_token")
        
        # Handle file upload if base64 not provided
        file_upload = None
        if not file_content_base64:
            file_upload = form.get("file")

        logger.info(f"📄 OCR request: {tool_name} for file: {file_name}")

        # Check if KYC client is initialized
        if not kyc_client:
            return JSONResponse({
                "success": False,
                "error": "KYC service not available",
                "message": "KYC client not initialized. Please try again later.",
                "data": None
            }, status_code=503)

        # Validate that either file content or file upload is provided
        if not file_content_base64 and not file_upload:
            return JSONResponse({
                "success": False,
                "error": "File required",
                "message": "Either file_content_base64 or file upload is required",
                "data": None
            }, status_code=400)

        # Get endpoint
        endpoint = ENDPOINTS.get(tool_name)
        if not endpoint:
            return JSONResponse({
                "success": False,
                "error": f"Endpoint not found for tool '{tool_name}'",
                "data": None
            }, status_code=400)

        # Prepare data for API call
        files = None
        data = {}
        
        if file_content_base64:
            # Use base64 content directly
            data = {
                'file_content_base64': file_content_base64,
                'file_name': file_name
            }
        elif file_upload:
            # Use file upload
            files = {'file': (file_upload.filename, file_upload.file, file_upload.content_type)}
        
        # Add additional parameters
        if tool_name == "ocr_itr":
            data['use_pdf'] = use_pdf
        if authorization_token:
            data['authorization_token'] = authorization_token

        # Make the request
        if files:
            response = await kyc_client.post_form(endpoint, files, data, authorization_token=authorization_token)
        else:
            response = await kyc_client.post_json(endpoint, data, authorization_token=authorization_token)

        # Enhanced storage logic - only Google Sheets
        storage_result = None
        if response.status_code == 200 and response.data:
            logger.info("💾 Starting Google Sheets storage...")
            try:
                # Store only in Google Sheets
                stored_record = await universal_db_manager.store_verification_data(
                    response.data, endpoint, tool_name
                )
                if stored_record:
                    storage_result = {
                        'sheets_stored': True,
                        'record_id': stored_record.get('id', 'unknown')
                    }
                    logger.info(f"✅ Google Sheets storage successful: {storage_result['record_id']}")
                else:
                    storage_result = {'sheets_stored': False, 'error': 'Storage returned None'}
            except Exception as storage_error:
                logger.error(f"❌ Google Sheets storage error: {storage_error}")
                storage_result = {'sheets_stored': False, 'error': str(storage_error)}

        # Prepare response
        response_data = response.data.copy() if response.data else {}
        response_data['file_info'] = {'filename': file_name, 'tool_used': tool_name}
        if storage_result:
            response_data['storage_info'] = storage_result

        return JSONResponse({
            "success": response.success,
            "data": response_data,
            "error": response.error,
            "message": response.message or f"OCR processing completed for {tool_name}",
            "tool": tool_name,
            "status_code": response.status_code
        }, status_code=200 if response.success else 400)

    except Exception as e:
        error_msg = f"OCR error for {tool_name}: {str(e)}"
        logger.error(f"❌ {error_msg}")
        return JSONResponse({
            "success": False,
            "error": error_msg,
            "tool": tool_name,
            "data": None
        }, status_code=500)

# =============================================================================
# LANGCHAIN CHAT ENDPOINTS (UNCHANGED)
# =============================================================================

@app.post("/api/chat", response_model=ChatResponse)
async def chat_with_agent(request: ChatRequest):
    """Chat with the KYC LangChain agent"""
    if not LANGCHAIN_AVAILABLE:
        raise HTTPException(
            status_code=503, 
            detail="LangChain integration not available. Please install required dependencies and set OPENAI_API_KEY."
        )
    
    try:
        server_url = f"http://localhost:{os.getenv('PORT', 8000)}"
        
        # Clear history if requested
        if request.clear_history:
            try:
                agent = get_agent(server_url=server_url)
                agent.clear_memory()
                return ChatResponse(
                    response="Conversation history cleared. How can I help you with KYC verification?",
                    session_id=request.session_id,
                    success=True
                )
            except Exception as clear_error:
                logger.warning(f"Error clearing history: {clear_error}")
                return ChatResponse(
                    response="History clear requested, but encountered an issue. How can I help you?",
                    session_id=request.session_id,
                    success=True
                )
        
        # Create an async task with longer timeout
        async def run_chat():
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(
                None,
                ask_agent,
                request.message,
                server_url
            )
        
        # Wait for chat response with extended timeout (2 minutes)
        try:
            response = await asyncio.wait_for(run_chat(), timeout=120.0)
        except asyncio.TimeoutError:
            logger.error("LangChain chat agent timed out after 2 minutes")
            return ChatResponse(
                response="❌ **Request timed out**\n\nThe chat request took longer than expected. Please try again with a simpler query.",
                session_id=request.session_id,
                success=True
            )
        
        return ChatResponse(
            response=response,
            session_id=request.session_id,
            success=True
        )
        
    except Exception as e:
        logger.error(f"Chat agent error: {str(e)}")
        return ChatResponse(
            response="I encountered an error processing your request. Please try again or contact support.",
            session_id=request.session_id,
            success=False,
            error=str(e)
        )

@app.post("/api/chat/verify", response_model=ChatResponse)
async def intelligent_verification(request: ChatRequest):
    """Intelligent verification endpoint that understands natural language"""
    if not LANGCHAIN_AVAILABLE:
        raise HTTPException(
            status_code=503,
            detail="LangChain integration not available. Please install required dependencies and set OPENAI_API_KEY."
        )
    
    try:
        server_url = f"http://localhost:{os.getenv('PORT', 8000)}"
        
        # Create an async task with longer timeout
        async def run_verification():
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(
                None,
                ask_agent,
                f"Please verify: {request.message}",
                server_url
            )
        
        # Wait for verification with extended timeout (3 minutes)
        try:
            response = await asyncio.wait_for(run_verification(), timeout=180.0)
        except asyncio.TimeoutError:
            logger.error("LangChain agent timed out after 3 minutes")
            return ChatResponse(
                response="❌ **Verification timed out**\n\nThe verification process took longer than expected. This might be due to:\n• External API delays\n• Network connectivity issues\n• Server overload\n\nPlease try again in a few moments.",
                session_id=request.session_id,
                success=True
            )
        
        return ChatResponse(
            response=response,
            session_id=request.session_id,
            success=True
        )
        
    except Exception as e:
        logger.error(f"Intelligent verification error: {str(e)}")
        return ChatResponse(
            response=f"❌ **Verification Error**\n\nAn error occurred: {str(e)}\n\nPlease try again or contact support.",
            session_id=request.session_id,
            success=False,
            error=str(e)
        )

@app.get("/api/chat/capabilities")
async def get_chat_capabilities():
    """Get information about chat agent capabilities"""
    if not LANGCHAIN_AVAILABLE:
        return {
            "available": False,
            "error": "LangChain integration not available",
            "requirements": [
                "Install: pip install langchain==0.0.350 openai==0.28.1",
                "Set environment variable: OPENAI_API_KEY"
            ]
        }
    
    openai_configured = bool(os.getenv("OPENAI_API_KEY"))
    
    return {
        "available": True,
        "openai_configured": openai_configured,
        "capabilities": [
            "Natural language KYC verification requests",
            "PAN, Aadhaar, Bank, GSTIN verification",
            "Document verification (Passport, License, Voter ID)",
            "Corporate verification",
            "Database search and history",
            "Conversation memory",
            "Intelligent query parsing"
        ],
        "example_queries": [
            "Verify PAN ABCDE1234F",
            "Check GSTIN 29ABCDE1234F1Z5",
            "Verify bank account 123456789 with IFSC SBIN0000123",
            "What verification services do you offer?",
            "How do I verify a passport?",
            "Search for records with PAN ABCDE1234F"
        ],
        "endpoints": {
            "chat": "/api/chat",
            "verify": "/api/chat/verify",
            "capabilities": "/api/chat/capabilities"
        }
    }

# =============================================================================
# LEGACY LANGCHAIN ENDPOINT (Backward Compatibility)
# =============================================================================

@app.post("/langchain/ask")
async def langchain_ask_legacy(request: Request):
    """Legacy LangChain endpoint for backward compatibility"""
    data = await request.json()
    question = data.get("question")
    
    if not question:
        return JSONResponse({
            "success": False, 
            "error": "Missing 'question' in request."
        }, status_code=400)
    
    if not LANGCHAIN_AVAILABLE:
        return JSONResponse({
            "success": False,
            "error": "LangChain integration not available. Please install dependencies and set OPENAI_API_KEY."
        }, status_code=503)
    
    try:
        server_url = f"http://localhost:{os.getenv('PORT', 8000)}"
        
        # Create async task with timeout
        async def run_legacy_chat():
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(
                None,
                ask_agent,
                question,
                server_url
            )
        
        try:
            result = await asyncio.wait_for(run_legacy_chat(), timeout=120.0)
            return JSONResponse({"success": True, "result": result})
        except asyncio.TimeoutError:
            return JSONResponse({
                "success": False,
                "error": "Request timed out after 2 minutes"
            }, status_code=408)
            
    except Exception as e:
        logger.error(f"LangChain agent error: {e}", exc_info=True)
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)

# =============================================================================
# SYSTEM MANAGEMENT ENDPOINTS
# =============================================================================

@app.get("/api/system/storage-status")
async def get_storage_status():
    """Get comprehensive storage system status"""
    try:
        status = {
            "database": {
                "enabled": DATABASE_ENABLED,
                "initialized": False,
                "type": "unknown"
            },
            "google_drive": {
                "available": GOOGLE_DRIVE_AVAILABLE,
                "initialized": False,
                "folder_count": 0
            },
            "timestamp": asyncio.get_event_loop().time()
        }
        
        # Check database status
        if DATABASE_ENABLED:
            try:
                db_stats = await db_manager.get_statistics()
                status["database"]["initialized"] = True
                status["database"]["type"] = db_stats.get("storage_type", "unknown")
                status["database"]["stats"] = db_stats
            except Exception as e:
                status["database"]["error"] = str(e)
        
        # Check Google Drive status
        if GOOGLE_DRIVE_AVAILABLE and google_drive_storage:
            status["google_drive"]["initialized"] = google_drive_storage.initialized
            if google_drive_storage.initialized:
                try:
                    drive_stats = await google_drive_storage.get_storage_statistics()
                    status["google_drive"]["folder_count"] = len(drive_stats.get("folders", {}))
                    status["google_drive"]["stats"] = drive_stats
                except Exception as e:
                    status["google_drive"]["error"] = str(e)
        
        return APIResponse(
            success=True,
            data=status,
            message="Storage status retrieved successfully"
        )
        
    except Exception as e:
        logger.error(f"Error getting storage status: {str(e)}")
        return APIResponse(
            success=False,
            error=str(e),
            message="Failed to retrieve storage status"
        )

@app.post("/api/system/test-storage")
async def test_storage_system():
    """Test storage system with a dummy record"""
    try:
        test_data = {
            "pan_number": "TEST123456",
            "full_name": "Test User",
            "test_record": True,
            "timestamp": asyncio.get_event_loop().time()
        }
        
        # Test storage
        storage_result = await store_verification_data_sheets_only(
            test_data, 
            "/test/storage"
        )
        
        return APIResponse(
            success=True,
            data={
                "test_data": test_data,
                "storage_result": storage_result
            },
            message="Storage system test completed"
        )
        
    except Exception as e:
        logger.error(f"Storage test failed: {str(e)}")
        return APIResponse(
            success=False,
            error=str(e),
            message="Storage system test failed"
        )

# =============================================================================
# MAIN APPLICATION ENTRY POINT
# =============================================================================

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    host = os.getenv("HOST", "0.0.0.0")
    
    logger.info(f"🚀 Starting Enhanced KYC HTTP server on {host}:{port}")
    logger.info(f"🔧 Configuration:")
    logger.info(f"   API Token: {'✅ Configured' if SUREPASS_API_TOKEN else '❌ Missing'}")
    logger.info(f"   Database: {'✅ Enabled' if DATABASE_ENABLED else '❌ Disabled'}")
    logger.info(f"   Google Drive: {'✅ Available' if GOOGLE_DRIVE_AVAILABLE else '❌ Not Available'}")
    logger.info(f"   LangChain: {'✅ Available' if LANGCHAIN_AVAILABLE else '❌ Not Available'}")
    logger.info(f"   OpenAI API: {'✅ Configured' if os.getenv('OPENAI_API_KEY') else '❌ Not Configured'}")
    
    uvicorn.run(
        "kyc_http_server:app",
        host=host,
        port=port,
        reload=False,
        log_level="info"
    )