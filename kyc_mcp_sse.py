"""
KYC MCP Server with SSE Support
This module defines the MCP tools and resources for KYC verification
that can be accessed via Server-Sent Events.
"""

import json
import logging
import re
from typing import Dict, Any, Optional
from mcp.server.fastmcp import FastMCP

# Import KYC components
from kyc_client import KYCClient
from config import ENDPOINTS, SUREPASS_API_TOKEN
from models import KYCResponse

logger = logging.getLogger("kyc-mcp-sse")

# Global KYC client for MCP tools
kyc_client: Optional[KYCClient] = None

async def initialize_kyc_client():
    """Initialize the global KYC client"""
    global kyc_client
    if kyc_client is None:
        kyc_client = KYCClient()
        await kyc_client.__aenter__()
        logger.info("KYC client initialized for MCP SSE")

def create_kyc_mcp_server() -> FastMCP:
    """
    Create and configure the FastMCP server with KYC tools and resources.
    
    Returns:
        FastMCP instance configured with KYC verification tools
    """
    mcp = FastMCP("KYC-Verification-Server")
    
    @mcp.tool()
    async def verify_pan_basic(id_number: str) -> str:
        """
        Perform basic PAN verification
        
        Args:
            id_number: PAN number to verify (format: AAAAA9999A)
            
        Returns:
            JSON string with verification results
        """
        try:
            # Validate PAN format
            if not re.match(r'^[A-Z]{5}[0-9]{4}[A-Z]$', id_number):
                return json.dumps({
                    "success": False,
                    "error": "Invalid PAN format. PAN should be in format AAAAA9999A",
                    "data": None
                })
            
            # Ensure client is initialized
            if kyc_client is None:
                await initialize_kyc_client()
            
            # Perform verification
            data = {"id_number": id_number}
            response = await kyc_client.post_json(ENDPOINTS["pan"], data)
            
            result = {
                "success": response.success,
                "data": response.data,
                "message": response.message or "PAN basic verification completed",
                "error": response.error
            }
            
            logger.info(f"Basic PAN verification completed for {id_number}")
            return json.dumps(result, indent=2)
            
        except Exception as e:
            logger.error(f"Error in basic PAN verification: {str(e)}")
            return json.dumps({
                "success": False,
                "error": f"Verification failed: {str(e)}",
                "data": None
            })
    
    @mcp.tool()
    async def verify_pan_comprehensive(id_number: str) -> str:
        """
        Perform comprehensive PAN verification with detailed information
        
        Args:
            id_number: PAN number to verify (format: AAAAA9999A)
            
        Returns:
            JSON string with comprehensive verification results including address
        """
        try:
            # Validate PAN format
            if not re.match(r'^[A-Z]{5}[0-9]{4}[A-Z]$', id_number):
                return json.dumps({
                    "success": False,
                    "error": "Invalid PAN format. PAN should be in format AAAAA9999A",
                    "data": None
                })
            
            # Ensure client is initialized
            if kyc_client is None:
                await initialize_kyc_client()
            
            # Perform comprehensive verification
            data = {"id_number": id_number}
            response = await kyc_client.post_json(ENDPOINTS["pan_comprehensive"], data)
            
            result = {
                "success": response.success,
                "data": response.data,
                "message": response.message or "PAN comprehensive verification completed",
                "error": response.error
            }
            
            logger.info(f"Comprehensive PAN verification completed for {id_number}")
            return json.dumps(result, indent=2)
            
        except Exception as e:
            logger.error(f"Error in comprehensive PAN verification: {str(e)}")
            return json.dumps({
                "success": False,
                "error": f"Verification failed: {str(e)}",
                "data": None
            })
    
    @mcp.tool()
    async def verify_pan_kra(id_number: str) -> str:
        """
        Perform PAN verification using KRA database
        
        Args:
            id_number: PAN number to verify (format: AAAAA9999A)
            
        Returns:
            JSON string with KRA verification results
        """
        try:
            # Validate PAN format
            if not re.match(r'^[A-Z]{5}[0-9]{4}[A-Z]$', id_number):
                return json.dumps({
                    "success": False,
                    "error": "Invalid PAN format. PAN should be in format AAAAA9999A",
                    "data": None
                })
            
            # Ensure client is initialized
            if kyc_client is None:
                await initialize_kyc_client()
            
            # Perform KRA verification
            data = {"id_number": id_number}
            response = await kyc_client.post_json(ENDPOINTS["pan_kra"], data)
            
            result = {
                "success": response.success,
                "data": response.data,
                "message": response.message or "PAN KRA verification completed",
                "error": response.error
            }
            
            logger.info(f"KRA PAN verification completed for {id_number}")
            return json.dumps(result, indent=2)
            
        except Exception as e:
            logger.error(f"Error in KRA PAN verification: {str(e)}")
            return json.dumps({
                "success": False,
                "error": f"Verification failed: {str(e)}",
                "data": None
            })
    
    @mcp.resource("kyc://api/status")
    async def api_status() -> str:
        """Get KYC API status and connectivity information"""
        try:
            if kyc_client is None:
                await initialize_kyc_client()
            
            # Test API connectivity
            data = {"id_number": "TEMP123"}
            response = await kyc_client.post_json(ENDPOINTS["pan_comprehensive"], data)
            
            status = {
                "service": "KYC Verification API",
                "api_token_configured": bool(SUREPASS_API_TOKEN),
                "client_initialized": kyc_client is not None,
                "connectivity_test": {
                    "status_code": response.status_code,
                    "success": response.success if response.status_code != 401 else True,
                    "message": "API connectivity verified"
                }
            }
            
            return json.dumps(status, indent=2)
            
        except Exception as e:
            logger.error(f"Error checking API status: {str(e)}")
            return json.dumps({
                "service": "KYC Verification API",
                "error": f"Status check failed: {str(e)}",
                "client_initialized": kyc_client is not None
            })
    
    @mcp.resource("kyc://api/endpoints")
    def available_endpoints() -> str:
        """Get list of available KYC API endpoints"""
        return json.dumps({
            "available_endpoints": ENDPOINTS,
            "description": "Available KYC verification endpoints",
            "supported_services": [
                "PAN Basic Verification",
                "PAN Comprehensive Verification", 
                "PAN KRA Verification"
            ]
        }, indent=2)
    
    @mcp.prompt()
    def kyc_verification_prompt(verification_type: str, id_number: str) -> str:
        """
        Generate a prompt for KYC verification
        
        Args:
            verification_type: Type of verification (basic, comprehensive, kra)
            id_number: ID number to verify
        """
        return f"""Please perform {verification_type} KYC verification for the following details:
        
ID Number: {id_number}
Verification Type: {verification_type.upper()}

Use the appropriate KYC verification tool to process this request and provide detailed results."""
    
    logger.info("KYC MCP server configured with tools and resources")
    return mcp
