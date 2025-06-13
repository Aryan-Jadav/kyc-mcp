#!/usr/bin/env python3
"""
KYC Verification MCP Server

A Model Context Protocol server that provides KYC (Know Your Customer) verification tools
using the SurePass API. This server implements various document verification, OCR,
face verification, and other KYC-related services.
"""

import json
import logging
import sys
import signal
import os

# Load environment variables from .env file
try:
    from dotenv import load_dotenv
    load_dotenv()
    print("Environment variables loaded from .env file", file=sys.stderr)
    # Debug: Check if API token is loaded
    api_token = os.getenv("SUREPASS_API_TOKEN")
    if api_token:
        print(f"API token loaded successfully (length: {len(api_token)})", file=sys.stderr)
    else:
        print("WARNING: API token not found in environment", file=sys.stderr)
except ImportError:
    print("python-dotenv not installed, skipping .env file loading", file=sys.stderr)
except Exception as e:
    print(f"Could not load .env file: {e}", file=sys.stderr)

from mcp.server.fastmcp import FastMCP

from kyc_client import KYCClient
from config import ENDPOINTS
from database import db_manager
from config_db import DATABASE_ENABLED
from universal_database import universal_db_manager, store_universal_verification_data

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s [%(levelname)s] %(message)s',
    stream=sys.stderr
)
logger = logging.getLogger("kyc-mcp-server")

# Initialize global kyc_client
kyc_client = None

# Create the FastMCP server
mcp = FastMCP("kyc-verification-server")

# Initialize KYC client and database on server startup
async def ensure_client_initialized():
    global kyc_client
    if kyc_client is None:
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

        except Exception as e:
            logger.error(f"Failed to initialize services: {str(e)}")
            raise e

@mcp.tool()
async def verify_api_ready() -> str:
    """Check if the KYC API client is initialized and ready"""
    await ensure_client_initialized()
    try:
        # Try making a simple request to check API token validity
        from config import SUREPASS_API_TOKEN, BASE_URL
        if not SUREPASS_API_TOKEN:
            return "Error: API token not found. Please set the SUREPASS_API_TOKEN environment variable."

        logger.info(f"Testing API connectivity to {BASE_URL}")

        # Try a simple API call to verify token and connectivity
        data = {"id_number": "TEMP123"}  # Using a dummy PAN for test
        response = await kyc_client.post_json(ENDPOINTS["pan_comprehensive"], data)

        if response.status_code == 401:
            return "Error: Invalid API token. Please check your SUREPASS_API_TOKEN."
        elif response.status_code == 403:
            return "Error: API token lacks required permissions."
        elif response.status_code is None:
            # Network error occurred
            return f"Network Error: {response.error}\n\nTroubleshooting steps:\n1. Check if you can access https://kyc-api.surepass.io in your browser\n2. Verify firewall allows HTTPS connections\n3. If behind corporate network, check proxy settings"

        return f"API client ready and token validated (Status: {response.status_code})"
    except Exception as e:
        logger.error(f"API readiness check failed: {str(e)}")
        return f"Error verifying API readiness: {str(e)}\n\nThis appears to be a network connectivity issue. Please check your internet connection and firewall settings."

@mcp.tool()
async def debug_environment() -> str:
    """Debug environment variables and configuration"""
    import os
    import socket
    from config import SUREPASS_API_TOKEN, BASE_URL

    # Test network connectivity
    connectivity_test = {}
    try:
        # Test DNS resolution
        result = socket.getaddrinfo('kyc-api.surepass.io', 443, socket.AF_INET)
        ip = result[0][4][0]
        connectivity_test["dns_resolution"] = f"✓ kyc-api.surepass.io -> {ip}"

        # Test port connectivity
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5)
        port_result = sock.connect_ex((ip, 443))
        sock.close()

        if port_result == 0:
            connectivity_test["port_443"] = "✓ Port 443 is open"
        else:
            connectivity_test["port_443"] = f"✗ Port 443 blocked (error {port_result})"
            connectivity_test["diagnosis"] = "SurePass servers are blocking your IP address"
            connectivity_test["solution"] = "Contact SurePass support for IP whitelisting"

    except Exception as e:
        connectivity_test["error"] = f"Network test failed: {str(e)}"

    debug_info = {
        "environment_check": {
            "api_token_set": bool(SUREPASS_API_TOKEN),
            "api_token_length": len(SUREPASS_API_TOKEN) if SUREPASS_API_TOKEN else 0,
            "api_token_preview": SUREPASS_API_TOKEN[:20] + "..." if SUREPASS_API_TOKEN else "None",
            "base_url": BASE_URL
        },
        "connectivity_test": connectivity_test,
        "os_environment": {
            "surepass_vars": {k: v[:20] + "..." if len(v) > 20 else v
                            for k, v in os.environ.items()
                            if 'SUREPASS' in k.upper()},
            "kyc_vars": {k: v[:20] + "..." if len(v) > 20 else v
                        for k, v in os.environ.items()
                        if 'KYC' in k.upper()}
        },
        "client_status": {
            "client_initialized": kyc_client is not None,
            "client_type": str(type(kyc_client)) if kyc_client else "None"
        }
    }

    return json.dumps(debug_info, indent=2)

mcp.startup_handler = ensure_client_initialized

# Clean up client and database on exit
def cleanup_handler(signum, _frame):
    """Signal handler for cleanup"""
    logger.info("Received signal %s, cleaning up...", signum)
    import asyncio

    def run_cleanup():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        async def cleanup():
            # Close KYC client
            if kyc_client:
                try:
                    await kyc_client.__aexit__(None, None, None)
                    await kyc_client.close()
                    logger.info("KYC client closed successfully")
                except Exception as e:
                    logger.error("Error closing KYC client: %s", str(e))

            # Close database
            if DATABASE_ENABLED:
                try:
                    await db_manager.close()
                    await universal_db_manager.close()
                    logger.info("Database connections closed successfully")
                except Exception as e:
                    logger.error("Error closing database: %s", str(e))

        try:
            loop.run_until_complete(cleanup())
        except Exception as e:
            logger.error("Error during cleanup: %s", str(e))
        finally:
            loop.close()

    try:
        run_cleanup()
    except Exception as e:
        logger.error("Error during cleanup: %s", str(e))

    sys.exit(0)

# Register cleanup handler for signals
signal.signal(signal.SIGINT, cleanup_handler)
signal.signal(signal.SIGTERM, cleanup_handler)

logger.info("KYC MCP Server initialized and ready")

# Define individual tools using FastMCP decorators
@mcp.tool()
async def verify_pan_kra(id_number: str) -> str:
    """Verify PAN using KRA (KYC Registration Agency) database

    Args:
        id_number: PAN number to verify (e.g., "EKRPR1234F")
    """
    await ensure_client_initialized()
    try:
        # Validate PAN format
        import re
        if not re.match(r'^[A-Z]{5}[0-9]{4}[A-Z]$', id_number):
            return "Error: Invalid PAN format. PAN should be in format AAAAA9999A"
            
        data = {"id_number": id_number}
        logger.info(f"Making PAN-KRA verification request for {id_number}")
            
        response = await kyc_client.post_json(ENDPOINTS["pan_kra"], data)
        
        # Log the complete response for debugging
        logger.debug(f"Raw PAN-KRA response: {json.dumps(response.data, indent=2)}")
        logger.debug(f"Response status code: {response.status_code}")
        logger.debug(f"Response message: {response.message}")

        if not response.success:
            # Handle authentication errors
            if response.status_code == 401:
                return "Error: Authentication failed. Please check your API token."
            elif response.status_code == 403:
                return "Error: Access forbidden. Your API token lacks required permissions."
            
            # Extract error message
            error_msg = None
            if response.error:
                error_msg = response.error.replace("API Error: ", "")
            elif response.message:
                error_msg = response.message
            elif response.data and isinstance(response.data, dict):
                error_msg = (
                    response.data.get('message') or 
                    response.data.get('error') or 
                    response.data.get('detail')
                )
            
            if response.data:
                logger.debug(f"Full error response data: {json.dumps(response.data, indent=2)}")

            if error_msg:
                logger.error(f"PAN-KRA verification error: {error_msg}")
                if "Invalid" in error_msg or "not found" in error_msg.lower():
                    return f"Error: {error_msg}"
                return f"Error: PAN-KRA verification failed - {error_msg}"
            else:
                logger.error("Unknown error in PAN-KRA verification")
                return "Error: Unable to verify PAN using KRA. Please check the number and try again."

        # Store data in universal database if enabled
        if DATABASE_ENABLED and response.data:
            try:
                stored_record = await store_universal_verification_data(response.data, ENDPOINTS["pan_kra"])
                if stored_record:
                    logger.info(f"PAN-KRA data stored in universal database with ID: {stored_record.id}")
            except Exception as e:
                logger.error(f"Error storing PAN-KRA data in universal database: {str(e)}")

        response_json = {
            'success': True,
            'data': response.data,
            'status_code': response.status_code,
            'message': response.message or 'Success',
            'message_code': response.message_code or 'success'
        }

        logger.debug(f"Processed PAN-KRA verification response: {json.dumps(response_json, indent=2)}")
        return json.dumps(response_json, indent=2)
    except Exception as e:
        logger.error(f"Error in PAN-KRA verification: {str(e)}")
        return f"Error: {str(e)}"

@mcp.tool()
async def verify_pan_basic(id_number: str) -> str:
    """Basic PAN (Permanent Account Number) verification

    Args:
        id_number: PAN number to verify (e.g., "EKRPR1234F")
    """
    await ensure_client_initialized()
    try:
        # Validate PAN format first
        import re
        if not re.match(r'^[A-Z]{5}[0-9]{4}[A-Z]$', id_number):
            return "Error: Invalid PAN format. PAN should be in format AAAAA9999A"
            
        data = {"id_number": id_number}
        logger.info(f"Making basic PAN verification request for {id_number}")
        
        # Check API token before making request
        from config import SUREPASS_API_TOKEN
        if not SUREPASS_API_TOKEN:
            return "Error: API token not configured. Please set SUREPASS_API_TOKEN in environment variables."
            
        response = await kyc_client.post_json(ENDPOINTS["pan"], data)
        
        # Log the complete response for debugging
        logger.debug(f"Raw PAN response: {json.dumps(response.data, indent=2)}")
        logger.debug(f"Response status code: {response.status_code}")
        logger.debug(f"Response message: {response.message}")

        # Handle error cases
        if not response.success:
            # First check for auth/permission errors
            if response.status_code == 401:
                return "Error: Authentication failed. Please check your API token."
            elif response.status_code == 403:
                return "Error: Access forbidden. Your API token does not have permission to access PAN verification."
            
            # For non-success responses, extract the error message
            error_msg = None
            if response.error:
                error_msg = response.error.replace("API Error: ", "")  # Remove prefix if present
            elif response.message:
                error_msg = response.message
            elif response.data and isinstance(response.data, dict):
                error_msg = (
                    response.data.get('message') or 
                    response.data.get('error') or 
                    response.data.get('detail')
                )
            
            # Log full response data for debugging
            if response.data:
                logger.debug(f"Full error response data: {json.dumps(response.data, indent=2)}")

            # Return error message if we found one
            if error_msg:
                logger.error(f"Basic PAN verification error: {error_msg}")
                if "Invalid" in error_msg or "not found" in error_msg.lower():
                    return f"Error: {error_msg}"
                return f"Error: PAN verification failed - {error_msg}"
            else:
                logger.error("Unknown error in PAN verification response")
                if response.status_code:
                    return f"Error: API returned status code {response.status_code} without details. Please check the PAN number and try again."
                return "Error: API returned an error without details. Please check the PAN number and try again."

        # Store data in universal database if enabled
        if DATABASE_ENABLED and response.data:
            try:
                stored_record = await store_universal_verification_data(response.data, ENDPOINTS["pan"])
                if stored_record:
                    logger.info(f"Basic PAN data stored in universal database with ID: {stored_record.id}")
            except Exception as e:
                logger.error(f"Error storing basic PAN data in universal database: {str(e)}")

        # Handle successful response
        response_json = {
            'success': True,
            'data': response.data,
            'status_code': response.status_code,
            'message': response.message or 'Success',
            'message_code': response.message_code or 'success'
        }

        logger.debug(f"Processed PAN verification response: {json.dumps(response_json, indent=2)}")
        return json.dumps(response_json, indent=2)
    except Exception as e:
        logger.error(f"Error in basic PAN verification: {str(e)}")
        return f"Error: {str(e)}"

@mcp.tool()
async def verify_pan_aadhaar_link(pan_number: str, aadhaar_number: str) -> str:
    """Verify if PAN is linked with Aadhaar

    Args:
        pan_number: PAN number to verify
        aadhaar_number: Aadhaar number to check linkage with
    """
    await ensure_client_initialized()
    try:
        # Validate PAN format
        import re
        if not re.match(r'^[A-Z]{5}[0-9]{4}[A-Z]$', pan_number):
            return "Error: Invalid PAN format. PAN should be in format AAAAA9999A"
        
        # Validate Aadhaar format (12 digits)
        if not re.match(r'^\d{12}$', aadhaar_number):
            return "Error: Invalid Aadhaar format. Aadhaar should be 12 digits"
            
        data = {
            "pan_number": pan_number,
            "aadhaar_number": aadhaar_number
        }
        logger.info(f"Making PAN-Aadhaar link verification request for PAN: {pan_number}")
            
        response = await kyc_client.post_json(ENDPOINTS["pan_aadhaar_link"], data)
        
        # Log the complete response for debugging
        logger.debug(f"Raw PAN-Aadhaar link response: {json.dumps(response.data, indent=2)}")
        logger.debug(f"Response status code: {response.status_code}")
        logger.debug(f"Response message: {response.message}")

        if not response.success:
            # Handle authentication errors
            if response.status_code == 401:
                return "Error: Authentication failed. Please check your API token."
            elif response.status_code == 403:
                return "Error: Access forbidden. Your API token lacks required permissions."
            
            # Extract error message
            error_msg = None
            if response.error:
                error_msg = response.error.replace("API Error: ", "")
            elif response.message:
                error_msg = response.message
            elif response.data and isinstance(response.data, dict):
                error_msg = (
                    response.data.get('message') or 
                    response.data.get('error') or 
                    response.data.get('detail')
                )
            
            if response.data:
                logger.debug(f"Full error response data: {json.dumps(response.data, indent=2)}")

            if error_msg:
                logger.error(f"PAN-Aadhaar link verification error: {error_msg}")
                if "Invalid" in error_msg or "not found" in error_msg.lower():
                    return f"Error: {error_msg}"
                return f"Error: PAN-Aadhaar link verification failed - {error_msg}"
            else:
                logger.error("Unknown error in PAN-Aadhaar link verification")
                return "Error: Unable to verify PAN-Aadhaar link. Please check the provided numbers and try again."

        response_json = {
            'success': True,
            'data': response.data,
            'status_code': response.status_code,
            'message': response.message or 'Success',
            'message_code': response.message_code or 'success'
        }
        
        logger.debug(f"Processed PAN-Aadhaar link verification response: {json.dumps(response_json, indent=2)}")
        return json.dumps(response_json, indent=2)
    except Exception as e:
        logger.error(f"Error in PAN-Aadhaar link verification: {str(e)}")
        return f"Error: {str(e)}"

@mcp.tool()
async def verify_pan_adv_v2(id_number: str) -> str:
    """Advanced PAN (Permanent Account Number) verification v2 with extended details

    Args:
        id_number: PAN number to verify (e.g., "EKRPR1234F")
    """
    await ensure_client_initialized()
    try:
        # Validate PAN format first
        import re
        if not re.match(r'^[A-Z]{5}[0-9]{4}[A-Z]$', id_number):
            return "Error: Invalid PAN format. PAN should be in format AAAAA9999A"
            
        data = {"id_number": id_number}
        logger.info(f"Making advanced PAN v2 verification request for {id_number}")
            
        response = await kyc_client.post_json(ENDPOINTS["pan_adv_v2"], data)
        
        # Log the complete response for debugging
        logger.debug(f"Raw PAN ADV V2 response: {json.dumps(response.data, indent=2)}")
        logger.debug(f"Response status code: {response.status_code}")
        logger.debug(f"Response message: {response.message}")

        if not response.success:
            # Handle authentication errors
            if response.status_code == 401:
                return "Error: Authentication failed. Please check your API token."
            elif response.status_code == 403:
                return "Error: Access forbidden. Your API token lacks required permissions."
            
            # Extract error message
            error_msg = None
            if response.error:
                error_msg = response.error.replace("API Error: ", "")
            elif response.message:
                error_msg = response.message
            elif response.data and isinstance(response.data, dict):
                error_msg = (
                    response.data.get('message') or 
                    response.data.get('error') or 
                    response.data.get('detail')
                )
            
            if response.data:
                logger.debug(f"Full error response data: {json.dumps(response.data, indent=2)}")

            if error_msg:
                logger.error(f"Advanced PAN v2 verification error: {error_msg}")
                if "Invalid" in error_msg or "not found" in error_msg.lower():
                    return f"Error: {error_msg}"
                return f"Error: PAN advanced v2 verification failed - {error_msg}"
            else:
                logger.error("Unknown error in PAN advanced v2 verification")
                return "Error: Unable to verify PAN. Please check the number and try again."

        # Store data in universal database if enabled
        if DATABASE_ENABLED and response.data:
            try:
                stored_record = await store_universal_verification_data(response.data, ENDPOINTS["pan_adv_v2"])
                if stored_record:
                    logger.info(f"PAN advanced v2 data stored in universal database with ID: {stored_record.id}")
            except Exception as e:
                logger.error(f"Error storing PAN advanced v2 data in universal database: {str(e)}")

        response_json = {
            'success': True,
            'data': response.data,
            'status_code': response.status_code,
            'message': response.message or 'Success',
            'message_code': response.message_code or 'success'
        }

        logger.debug(f"Processed PAN advanced v2 verification response: {json.dumps(response_json, indent=2)}")
        return json.dumps(response_json, indent=2)
    except Exception as e:
        logger.error(f"Error in advanced PAN v2 verification: {str(e)}")
        return f"Error: {str(e)}"

@mcp.tool()
async def verify_pan_adv(id_number: str) -> str:
    """Advanced PAN (Permanent Account Number) verification with extended details

    Args:
        id_number: PAN number to verify (e.g., "EKRPR1234F")
    """
    await ensure_client_initialized()
    try:
        # Validate PAN format first
        import re
        if not re.match(r'^[A-Z]{5}[0-9]{4}[A-Z]$', id_number):
            return "Error: Invalid PAN format. PAN should be in format AAAAA9999A"
            
        data = {"id_number": id_number}
        logger.info(f"Making advanced PAN verification request for {id_number}")
        
        # Check API token before making request
        from config import SUREPASS_API_TOKEN
        if not SUREPASS_API_TOKEN:
            return "Error: API token not configured. Please set SUREPASS_API_TOKEN in environment variables."
            
        response = await kyc_client.post_json(ENDPOINTS["pan_adv"], data)
        
        # Log the complete response for debugging
        logger.debug(f"Raw PAN ADV response: {json.dumps(response.data, indent=2)}")
        logger.debug(f"Response status code: {response.status_code}")
        logger.debug(f"Response message: {response.message}")

        if not response.success:
            # Handle authentication errors
            if response.status_code == 401:
                return "Error: Authentication failed. Please check your API token."
            elif response.status_code == 403:
                return "Error: Access forbidden. Your API token lacks required permissions."
            
            # Extract error message
            error_msg = None
            if response.error:
                error_msg = response.error.replace("API Error: ", "")
            elif response.message:
                error_msg = response.message
            elif response.data and isinstance(response.data, dict):
                error_msg = (
                    response.data.get('message') or 
                    response.data.get('error') or 
                    response.data.get('detail')
                )
            
            if response.data:
                logger.debug(f"Full error response data: {json.dumps(response.data, indent=2)}")

            if error_msg:
                logger.error(f"Advanced PAN verification error: {error_msg}")
                if "Invalid" in error_msg or "not found" in error_msg.lower():
                    return f"Error: {error_msg}"
                return f"Error: PAN advanced verification failed - {error_msg}"
            else:
                logger.error("Unknown error in PAN advanced verification")
                return "Error: Unable to verify PAN. Please check the number and try again."

        # Store data in universal database if enabled
        if DATABASE_ENABLED and response.data:
            try:
                stored_record = await store_universal_verification_data(response.data, ENDPOINTS["pan_adv"])
                if stored_record:
                    logger.info(f"PAN advanced data stored in universal database with ID: {stored_record.id}")
            except Exception as e:
                logger.error(f"Error storing PAN advanced data in universal database: {str(e)}")

        response_json = {
            'success': True,
            'data': response.data,
            'status_code': response.status_code,
            'message': response.message or 'Success',
            'message_code': response.message_code or 'success'
        }

        logger.debug(f"Processed PAN advanced verification response: {json.dumps(response_json, indent=2)}")
        return json.dumps(response_json, indent=2)
    except Exception as e:
        logger.error(f"Error in advanced PAN verification: {str(e)}")
        return f"Error: {str(e)}"

@mcp.tool()
async def verify_pan_comprehensive(id_number: str) -> str:
    """Verify PAN (Permanent Account Number) with comprehensive details

    Args:
        id_number: PAN number to verify
    """
    await ensure_client_initialized()
    try:
        # Validate PAN format first
        import re
        if not re.match(r'^[A-Z]{5}[0-9]{4}[A-Z]$', id_number):
            return "Error: Invalid PAN format. PAN should be in format AAAAA9999A"
            
        data = {"id_number": id_number}
        logger.info(f"Making PAN verification request for {id_number}")
        
        # Check API token before making request
        from config import SUREPASS_API_TOKEN
        if not SUREPASS_API_TOKEN:
            return "Error: API token not configured. Please set SUREPASS_API_TOKEN in environment variables."
            
        response = await kyc_client.post_json(ENDPOINTS["pan_comprehensive"], data)
        
        if not response.success:
            # First check for auth/permission errors
            if response.status_code == 401:
                logger.error("PAN comprehensive verification failed: Authentication error")
                return "Error: Authentication failed. Please check your API token and ensure it has permissions for PAN verification."
            elif response.status_code == 403:
                logger.error("PAN comprehensive verification failed: Access forbidden")
                return "Error: Access forbidden. Your API token does not have permission to access PAN verification."
            
            # Then check for other error messages
            error_msg = None
            if response.error:
                error_msg = response.error.replace("API Error: ", "")  # Remove prefix if present
            elif response.message:
                error_msg = response.message
            elif response.data and isinstance(response.data, dict):
                error_msg = (
                    response.data.get('message') or 
                    response.data.get('error') or 
                    response.data.get('detail')
                )

            # Log full response data for debugging
            if response.data:
                logger.debug(f"Full error response data: {json.dumps(response.data, indent=2)}")

            # Return formatted error message
            if error_msg:
                logger.error(f"PAN comprehensive verification failed: {error_msg}")
                if "Invalid" in error_msg or "not found" in error_msg.lower():
                    return f"Error: {error_msg}"
                return f"Error: PAN comprehensive verification failed - {error_msg}"
            else:
                logger.error("Unknown error in PAN comprehensive verification")
                return "Error: Unable to verify PAN. Please check the PAN number and try again."
        
        # Log raw response data for debugging
        logger.debug(f"Raw PAN response data: {json.dumps(response.data, indent=2)}")

        # Store data in universal database if enabled
        if DATABASE_ENABLED and response.data:
            try:
                stored_record = await store_universal_verification_data(response.data, ENDPOINTS["pan_comprehensive"])
                if stored_record:
                    logger.info(f"PAN comprehensive data stored in universal database with ID: {stored_record.id}")
            except Exception as e:
                logger.error(f"Error storing PAN comprehensive data in universal database: {str(e)}")

        # Convert the generic response data to PANData model
        if response.data:
            from models import PANData
            try:
                # Clean up any None values in address if present
                if 'address' in response.data and isinstance(response.data['address'], dict):
                    response.data['address'] = {k: v for k, v in response.data['address'].items() if v is not None}

                pan_data = PANData.model_validate(response.data)
                logger.debug(f"Processed PAN data: {pan_data.model_dump(exclude_none=True)}")
                response.data = pan_data
            except Exception as e:
                logger.error(f"Error processing PAN data: {str(e)}")
                logger.debug(f"Validation error details: {str(e)}")
                # Continue with raw data if validation fails

        response_json = response.model_dump()
        logger.debug(f"Final response: {response_json}")
        return json.dumps(response_json, indent=2)
    except Exception as e:
        logger.error(f"Error verifying PAN: {str(e)}")
        return f"Error: {str(e)} - Please check your API token and ensure it has permissions for PAN verification"

@mcp.tool()
async def verify_tan(id_number: str) -> str:
    """Verify TAN (Tax Deduction Account Number)

    Args:
        id_number: TAN number to verify
    """
    await ensure_client_initialized()
    try:
        data = {"id_number": id_number}
        response = await kyc_client.post_json(ENDPOINTS["tan"], data)

        # Store in universal database if successful
        if response.success and response.data:
            try:
                stored_person = await store_universal_verification_data(response.data, ENDPOINTS["tan"])
                if stored_person:
                    logger.info(f"TAN verification data stored for person ID: {stored_person.id}")
            except Exception as e:
                logger.error(f"Error storing TAN verification data: {str(e)}")

        return json.dumps(response.model_dump(), indent=2)
    except Exception as e:
        logger.error(f"Error verifying TAN: {str(e)}")
        return f"Error: {str(e)}"

@mcp.tool()
async def verify_voter_id(id_number: str, authorization_token: str = None) -> str:
    """Verify Voter ID

    Args:
        id_number: Voter ID number
        authorization_token: Authorization token (optional if set in environment)
    """
    if kyc_client is None:
        await ensure_client_initialized()
    try:
        data = {"id_number": id_number}
        response = await kyc_client.post_json(
            ENDPOINTS["voter_id"],
            data,
            authorization_token=authorization_token
        )

        # Store in universal database if successful
        if response.success and response.data:
            try:
                stored_person = await store_universal_verification_data(response.data, ENDPOINTS["voter_id"])
                if stored_person:
                    logger.info(f"Voter ID verification data stored for person ID: {stored_person.id}")
            except Exception as e:
                logger.error(f"Error storing Voter ID verification data: {str(e)}")

        return json.dumps(response.model_dump(), indent=2)
    except Exception as e:
        logger.error(f"Error verifying Voter ID: {str(e)}")
        return f"Error: {str(e)}"

@mcp.tool()
async def verify_driving_license(id_number: str, dob: str) -> str:
    """Verify Driving License

    Args:
        id_number: License number
        dob: Date of birth (YYYY-MM-DD)
    """
    await ensure_client_initialized()
    try:
        data = {"id_number": id_number, "dob": dob}
        response = await kyc_client.post_json(ENDPOINTS["driving_license"], data)
        return json.dumps(response.model_dump(), indent=2)
    except Exception as e:
        logger.error(f"Error verifying Driving License: {str(e)}")
        return f"Error: {str(e)}"

@mcp.tool()
async def verify_passport(id_number: str, dob: str) -> str:
    """Verify Passport details

    Args:
        id_number: Passport file number
        dob: Date of birth (YYYY-MM-DD)
    """
    await ensure_client_initialized()
    try:
        data = {"id_number": id_number, "dob": dob}
        response = await kyc_client.post_json(ENDPOINTS["passport"], data)
        return json.dumps(response.model_dump(), indent=2)
    except Exception as e:
        logger.error(f"Error verifying Passport: {str(e)}")
        return f"Error: {str(e)}"

@mcp.tool()
async def verify_bank_account(id_number: str, ifsc: str, authorization_token: str = None) -> str:
    """Verify bank account details

    Args:
        id_number: Account number
        ifsc: IFSC code
        authorization_token: Authorization token (optional if set in environment)
    """
    await ensure_client_initialized()
    try:
        data = {"id_number": id_number, "ifsc": ifsc, "ifsc_details": True}
        response = await kyc_client.post_json(
            ENDPOINTS["bank_verification"],
            data,
            authorization_token=authorization_token
        )

        # Store in universal database if successful
        if response.success and response.data:
            try:
                stored_person = await store_universal_verification_data(response.data, ENDPOINTS["bank_verification"])
                if stored_person:
                    logger.info(f"Bank verification data stored for person ID: {stored_person.id}")
            except Exception as e:
                logger.error(f"Error storing bank verification data: {str(e)}")

        return json.dumps(response.model_dump(), indent=2)
    except Exception as e:
        logger.error(f"Error verifying Bank Account: {str(e)}")
        return f"Error: {str(e)}"

@mcp.tool()
async def verify_gstin(id_number: str, authorization_token: str = None) -> str:
    """Verify GSTIN details

    Args:
        id_number: GSTIN number
        authorization_token: Authorization token (optional if set in environment)
    """
    await ensure_client_initialized()
    try:
        data = {"id_number": id_number}
        response = await kyc_client.post_json(
            ENDPOINTS["gstin"],
            data,
            authorization_token=authorization_token
        )

        # Store in universal database if successful
        if response.success and response.data:
            try:
                stored_person = await store_universal_verification_data(response.data, ENDPOINTS["gstin"])
                if stored_person:
                    logger.info(f"GSTIN verification data stored for person ID: {stored_person.id}")
            except Exception as e:
                logger.error(f"Error storing GSTIN verification data: {str(e)}")

        return json.dumps(response.model_dump(), indent=2)
    except Exception as e:
        logger.error(f"Error verifying GSTIN: {str(e)}")
        return f"Error: {str(e)}"

# Additional Document Verification Tools
@mcp.tool()
async def verify_itr_compliance(pan_number: str) -> str:
    """Check ITR compliance for a PAN number

    Args:
        pan_number: PAN number to check compliance for
    """
    await ensure_client_initialized()
    try:
        data = {"pan_number": pan_number}
        response = await kyc_client.post_json(ENDPOINTS["itr_compliance"], data)
        return json.dumps(response.model_dump(), indent=2)
    except Exception as e:
        logger.error(f"Error checking ITR compliance: {str(e)}")
        return f"Error: {str(e)}"

@mcp.tool()
async def verify_electricity_bill(id_number: str, operator_code: str) -> str:
    """Verify electricity bill details

    Args:
        id_number: Electricity bill ID number
        operator_code: Operator code (e.g., MH for Maharashtra)
    """
    await ensure_client_initialized()
    try:
        data = {"id_number": id_number, "operator_code": operator_code}
        response = await kyc_client.post_json(ENDPOINTS["electricity_bill"], data)
        return json.dumps(response.model_dump(), indent=2)
    except Exception as e:
        logger.error(f"Error verifying electricity bill: {str(e)}")
        return f"Error: {str(e)}"

@mcp.tool()
async def aadhaar_to_uan(aadhaar_number: str, authorization_token: str = None) -> str:
    """Get UAN from Aadhaar number

    Args:
        aadhaar_number: Aadhaar number
        authorization_token: Authorization token (optional if set in environment)
    """
    await ensure_client_initialized()
    try:
        data = {"aadhaar_number": aadhaar_number}
        response = await kyc_client.post_json(
            ENDPOINTS["aadhaar_to_uan"],
            data,
            authorization_token=authorization_token
        )
        return json.dumps(response.model_dump(), indent=2)
    except Exception as e:
        logger.error(f"Error getting UAN from Aadhaar: {str(e)}")
        return f"Error: {str(e)}"

@mcp.tool()
async def ckyc_search(id_number: str, document_type: str, authorization_token: str = None) -> str:
    """Search CKYC records

    Args:
        id_number: Document ID number (e.g., PAN)
        document_type: Type of document (e.g., PAN)
        authorization_token: Authorization token (optional if set in environment)
    """
    await ensure_client_initialized()
    try:
        data = {"id_number": id_number, "document_type": document_type}
        response = await kyc_client.post_json(
            ENDPOINTS["ckyc_search"],
            data,
            authorization_token=authorization_token
        )
        return json.dumps(response.model_dump(), indent=2)
    except Exception as e:
        logger.error(f"Error searching CKYC: {str(e)}")
        return f"Error: {str(e)}"

@mcp.tool()
async def gstin_by_pan(id_number: str, authorization_token: str = None) -> str:
    """Get GSTIN details by PAN number

    Args:
        id_number: PAN number
        authorization_token: Authorization token (optional if set in environment)
    """
    await ensure_client_initialized()
    try:
        data = {"id_number": id_number}
        response = await kyc_client.post_json(
            ENDPOINTS["gstin_by_pan"],
            data,
            authorization_token=authorization_token
        )
        return json.dumps(response.model_dump(), indent=2)
    except Exception as e:
        logger.error(f"Error getting GSTIN by PAN: {str(e)}")
        return f"Error: {str(e)}"

@mcp.tool()
async def email_check(email: str, authorization_token: str = None) -> str:
    """Check email employment details

    Args:
        email: Email address to check
        authorization_token: Authorization token (optional if set in environment)
    """
    await ensure_client_initialized()
    try:
        data = {"email": email}
        response = await kyc_client.post_json(
            ENDPOINTS["email_check"],
            data,
            authorization_token=authorization_token
        )
        return json.dumps(response.model_dump(), indent=2)
    except Exception as e:
        logger.error(f"Error checking email: {str(e)}")
        return f"Error: {str(e)}"

@mcp.tool()
async def name_to_cin(company_name_search: str, authorization_token: str = None) -> str:
    """Search company CIN by name

    Args:
        company_name_search: Company name to search
        authorization_token: Authorization token (optional if set in environment)
    """
    await ensure_client_initialized()
    try:
        data = {"company_name_search": company_name_search}
        response = await kyc_client.post_json(
            ENDPOINTS["name_to_cin"],
            data,
            authorization_token=authorization_token
        )
        return json.dumps(response.model_dump(), indent=2)
    except Exception as e:
        logger.error(f"Error searching CIN by name: {str(e)}")
        return f"Error: {str(e)}"

# Corporate Verification Tools
@mcp.tool()
async def pan_udyam_check(pan_number: str, full_name: str, dob: str) -> str:
    """Verify PAN and Udyam registration details

    Args:
        pan_number: PAN number to verify
        full_name: Full name of the company/business
        dob: Date of registration (YYYY-MM-DD)
    """
    await ensure_client_initialized()
    try:
        # Validate PAN format
        import re
        if not re.match(r'^[A-Z]{5}[0-9]{4}[A-Z]$', pan_number):
            return "Error: Invalid PAN format. PAN should be in format AAAAA9999A"

        # Validate company name
        if not full_name or not full_name.strip():
            return "Error: Company name cannot be empty"

        # Validate date format
        if not re.match(r'^\d{4}-\d{2}-\d{2}$', dob):
            return "Error: Invalid date format. Date should be in YYYY-MM-DD format"

        data = {
            "pan_number": pan_number,
            "full_name": full_name.strip(),
            "dob": dob
        }
        
        logger.info(f"Making PAN-Udyam verification request for PAN: {pan_number}, Company: {full_name}")
        response = await kyc_client.post_json(ENDPOINTS["pan_udyam"], data)
        
        # Log the complete response for debugging
        logger.debug(f"Raw PAN-Udyam response: {json.dumps(response.data, indent=2)}")
        logger.debug(f"Response status code: {response.status_code}")
        logger.debug(f"Response message: {response.message}")

        if not response.success:
            # Handle authentication errors
            if response.status_code == 401:
                return "Error: Authentication failed. Please check your API token."
            elif response.status_code == 403:
                return "Error: Access forbidden. Your API token lacks required permissions."
            
            # Extract error message
            error_msg = None
            if response.error:
                error_msg = response.error.replace("API Error: ", "")
            elif response.message:
                error_msg = response.message
            elif response.data and isinstance(response.data, dict):
                error_msg = (
                    response.data.get('message') or 
                    response.data.get('error') or 
                    response.data.get('detail')
                )
            
            if response.data:
                logger.debug(f"Full error response data: {json.dumps(response.data, indent=2)}")

            if error_msg:
                logger.error(f"PAN-Udyam verification error: {error_msg}")
                if "Invalid" in error_msg or "not found" in error_msg.lower():
                    return f"Error: {error_msg}"
                return f"Error: PAN-Udyam verification failed - {error_msg}"
            else:
                logger.error("Unknown error in PAN-Udyam verification")
                return "Error: Unable to verify PAN-Udyam details. Please check the provided information and try again."

        response_json = {
            'success': True,
            'data': response.data,
            'status_code': response.status_code,
            'message': response.message or 'Success',
            'message_code': response.message_code or 'success'
        }
        
        logger.debug(f"Processed PAN-Udyam verification response: {json.dumps(response_json, indent=2)}")
        return json.dumps(response_json, indent=2)
    except Exception as e:
        logger.error(f"Error in PAN-Udyam verification: {str(e)}")
        return f"Error: {str(e)}"

@mcp.tool()
async def gstin_advanced(id_number: str, authorization_token: str = None) -> str:
    """Get advanced GSTIN details

    Args:
        id_number: GSTIN number
        authorization_token: Authorization token (optional if set in environment)
    """
    await ensure_client_initialized()
    try:
        data = {"id_number": id_number}
        response = await kyc_client.post_json(
            ENDPOINTS["gstin_advanced"],
            data,
            authorization_token=authorization_token
        )
        return json.dumps(response.model_dump(), indent=2)
    except Exception as e:
        logger.error(f"Error getting advanced GSTIN details: {str(e)}")
        return f"Error: {str(e)}"

@mcp.tool()
async def telecom_generate_otp(id_number: str) -> str:
    """Generate OTP for telecom verification

    Args:
        id_number: Phone number
    """
    await ensure_client_initialized()
    try:
        data = {"id_number": id_number}
        response = await kyc_client.post_json(ENDPOINTS["telecom_generate_otp"], data)
        return json.dumps(response.model_dump(), indent=2)
    except Exception as e:
        logger.error(f"Error generating telecom OTP: {str(e)}")
        return f"Error: {str(e)}"

@mcp.tool()
async def court_case_search(name: str, father_name: str, address: str, case_type: str,
                           state_name: str, search_type: str, category: str,
                           authorization_token: str = None) -> str:
    """Search court case details

    Args:
        name: Person's name
        father_name: Father's name
        address: Address
        case_type: Type of case (e.g., respondent)
        state_name: State name (e.g., WESTBENGAL)
        search_type: Search type (e.g., individual)
        category: Category (e.g., civil)
        authorization_token: Authorization token (optional if set in environment)
    """
    await ensure_client_initialized()
    try:
        data = {
            "name": name,
            "father_name": father_name,
            "source": "ecourt",
            "address": address,
            "case_type": case_type,
            "state_name": state_name,
            "search_type": search_type,
            "category": category
        }
        response = await kyc_client.post_json(
            ENDPOINTS["ecourts_search"],
            data,
            authorization_token=authorization_token
        )
        return json.dumps(response.model_dump(), indent=2)
    except Exception as e:
        logger.error(f"Error searching court cases: {str(e)}")
        return f"Error: {str(e)}"

@mcp.tool()
async def telecom_verification(id_number: str, authorization_token: str = None) -> str:
    """Verify telecom details

    Args:
        id_number: Phone number
        authorization_token: Authorization token (optional if set in environment)
    """
    await ensure_client_initialized()
    try:
        data = {"id_number": id_number}
        response = await kyc_client.post_json(
            ENDPOINTS["telecom_verification"],
            data,
            authorization_token=authorization_token
        )
        return json.dumps(response.model_dump(), indent=2)
    except Exception as e:
        logger.error(f"Error verifying telecom: {str(e)}")
        return f"Error: {str(e)}"

@mcp.tool()
async def ecourts_cnr_search(cnr_number: str, authorization_token: str = None) -> str:
    """Search court cases by CNR number

    Args:
        cnr_number: CNR number
        authorization_token: Authorization token (optional if set in environment)
    """
    await ensure_client_initialized()
    try:
        data = {"cnr_number": cnr_number}
        response = await kyc_client.post_json(
            ENDPOINTS["ecourts_cnr"],
            data,
            authorization_token=authorization_token
        )
        return json.dumps(response.model_dump(), indent=2)
    except Exception as e:
        logger.error(f"Error searching by CNR: {str(e)}")
        return f"Error: {str(e)}"

@mcp.tool()
async def prefill_report_v2(name: str, mobile: str, authorization_token: str = None) -> str:
    """Generate prefill report v2

    Args:
        name: Person's name
        mobile: Mobile number
        authorization_token: Authorization token (optional if set in environment)
    """
    await ensure_client_initialized()
    try:
        data = {"name": name, "mobile": mobile}
        response = await kyc_client.post_json(
            ENDPOINTS["prefill_report"],
            data,
            authorization_token=authorization_token
        )
        return json.dumps(response.model_dump(), indent=2)
    except Exception as e:
        logger.error(f"Error generating prefill report: {str(e)}")
        return f"Error: {str(e)}"

# Vehicle Services
@mcp.tool()
async def rc_to_mobile_number(rc_number: str, authorization_token: str = None) -> str:
    """Get mobile number from RC number

    Args:
        rc_number: RC (Registration Certificate) number
        authorization_token: Authorization token (optional if set in environment)
    """
    await ensure_client_initialized()
    try:
        data = {"rc_number": rc_number}
        response = await kyc_client.post_json(
            ENDPOINTS["rc_to_mobile"],
            data,
            authorization_token=authorization_token
        )
        return json.dumps(response.model_dump(), indent=2)
    except Exception as e:
        logger.error(f"Error getting mobile from RC: {str(e)}")
        return f"Error: {str(e)}"

@mcp.tool()
async def aadhaar_generate_otp(id_number: str, authorization_token: str = None) -> str:
    """Generate OTP for Aadhaar verification

    Args:
        id_number: Aadhaar number
        authorization_token: Authorization token (optional if set in environment)
    """
    await ensure_client_initialized()
    try:
        data = {"id_number": id_number}
        response = await kyc_client.post_json(
            ENDPOINTS["aadhaar_generate_otp"],
            data,
            authorization_token=authorization_token
        )
        return json.dumps(response.model_dump(), indent=2)
    except Exception as e:
        logger.error(f"Error generating Aadhaar OTP: {str(e)}")
        return f"Error: {str(e)}"

@mcp.tool()
async def director_phone(id_number: str) -> str:
    """Get director phone details

    Args:
        id_number: Director ID number
    """
    await ensure_client_initialized()
    try:
        data = {"id_number": id_number}
        response = await kyc_client.post_json(ENDPOINTS["director_phone"], data)
        return json.dumps(response.model_dump(), indent=2)
    except Exception as e:
        logger.error(f"Error getting director phone: {str(e)}")
        return f"Error: {str(e)}"

@mcp.tool()
async def tds_check(tan_number: str, pan_number: str, year: str, quarter: str,
                   type_of_return: str, authorization_token: str = None) -> str:
    """Check TDS details

    Args:
        tan_number: TAN number
        pan_number: PAN number
        year: Year (e.g., 2020)
        quarter: Quarter (e.g., Q4)
        type_of_return: Type of return (e.g., salary)
        authorization_token: Authorization token (optional if set in environment)
    """
    await ensure_client_initialized()
    try:
        data = {
            "tan_number": tan_number,
            "pan_number": pan_number,
            "year": year,
            "quarter": quarter,
            "type_of_return": type_of_return
        }
        response = await kyc_client.post_json(
            ENDPOINTS["tds_check"],
            data,
            authorization_token=authorization_token
        )
        return json.dumps(response.model_dump(), indent=2)
    except Exception as e:
        logger.error(f"Error checking TDS: {str(e)}")
        return f"Error: {str(e)}"

@mcp.tool()
async def commercial_credit_report(business_name: str, mobile: str, pan: str, consent: str = "Y", authorization_token: str = None) -> str:
    """Fetch commercial credit report for a business

    Args:
        business_name: Name of the business
        mobile: Mobile number
        pan: PAN number of the business
        consent: Consent (Y/N, defaults to Y)
        authorization_token: Authorization token (optional if set in environment)
    """
    await ensure_client_initialized()
    try:
        # Validate inputs
        if not business_name or not business_name.strip():
            return "Error: Business name cannot be empty"
        
        # Validate mobile number format (10 digits)
        import re
        if not re.match(r'^\d{10}$', mobile):
            return "Error: Invalid mobile number format. Mobile number should be 10 digits"
            
        # Validate PAN format
        if not re.match(r'^[A-Z]{5}[0-9]{4}[A-Z]$', pan):
            return "Error: Invalid PAN format. PAN should be in format AAAAA9999A"
            
        # Validate consent
        if consent.upper() not in ["Y", "N"]:
            return "Error: Consent should be either 'Y' or 'N'"
            
        data = {
            "business_name": business_name.strip(),
            "mobile": mobile,
            "pan": pan,
            "consent": consent.upper()
        }
        
        logger.info(f"Making commercial credit report request for business: {business_name}, PAN: {pan}")
        response = await kyc_client.post_json(
            ENDPOINTS["credit_report_commercial"],
            data,
            authorization_token=authorization_token
        )
        
        # Log the complete response for debugging
        logger.debug(f"Raw commercial credit report response: {json.dumps(response.data, indent=2)}")
        logger.debug(f"Response status code: {response.status_code}")
        logger.debug(f"Response message: {response.message}")

        if not response.success:
            # Handle authentication errors
            if response.status_code == 401:
                return "Error: Authentication failed. Please check your API token."
            elif response.status_code == 403:
                return "Error: Access forbidden. Your API token lacks required permissions."
            
            # Extract error message
            error_msg = None
            if response.error:
                error_msg = response.error.replace("API Error: ", "")
            elif response.message:
                error_msg = response.message
            elif response.data and isinstance(response.data, dict):
                error_msg = (
                    response.data.get('message') or 
                    response.data.get('error') or 
                    response.data.get('detail')
                )
            
            if response.data:
                logger.debug(f"Full error response data: {json.dumps(response.data, indent=2)}")

            if error_msg:
                logger.error(f"Commercial credit report error: {error_msg}")
                if "Invalid" in error_msg or "not found" in error_msg.lower():
                    return f"Error: {error_msg}"
                return f"Error: Commercial credit report fetch failed - {error_msg}"
            else:
                logger.error("Unknown error in commercial credit report fetch")
                return "Error: Unable to fetch commercial credit report. Please check the provided details and try again."

        response_json = {
            'success': True,
            'data': response.data,
            'status_code': response.status_code,
            'message': response.message or 'Success',
            'message_code': response.message_code or 'success'
        }
        
        logger.debug(f"Processed commercial credit report response: {json.dumps(response_json, indent=2)}")
        return json.dumps(response_json, indent=2)
    except Exception as e:
        logger.error(f"Error fetching commercial credit report: {str(e)}")
        return f"Error: {str(e)}"

@mcp.tool()
async def credit_report_pdf(name: str, id_number: str, id_type: str, mobile: str,
                         consent: str = "Y", gender: str = None, authorization_token: str = None) -> str:
    """Fetch credit report in PDF format

    Args:
        name: Person's name
        id_number: ID number (PAN, Aadhaar, etc.)
        id_type: Type of ID (e.g., pan, aadhaar)
        mobile: Mobile number
        consent: Consent (Y/N, defaults to Y)
        gender: Gender (male/female, optional)
        authorization_token: Authorization token (optional if set in environment)
    """
    await ensure_client_initialized()
    try:
        # Validate inputs
        if not name or not name.strip():
            return "Error: Name cannot be empty"
            
        if not id_number or not id_number.strip():
            return "Error: ID number cannot be empty"
            
        if not id_type or not id_type.strip():
            return "Error: ID type cannot be empty"
            
        # Validate mobile number format (10 digits)
        import re
        if not re.match(r'^\d{10}$', mobile):
            return "Error: Invalid mobile number format. Mobile number should be 10 digits"
            
        # Validate consent
        if consent.upper() not in ["Y", "N"]:
            return "Error: Consent should be either 'Y' or 'N'"
            
        # Validate gender if provided
        if gender and gender.lower() not in ["male", "female"]:
            return "Error: Gender should be either 'male' or 'female'"
            
        data = {
            "name": name.strip(),
            "id_number": id_number.strip(),
            "id_type": id_type.lower().strip(),
            "mobile": mobile,
            "consent": consent.upper()
        }
        
        # Add gender if provided
        if gender:
            data["gender"] = gender.lower()
        
        logger.info(f"Making credit report PDF request for name: {name}, ID: {id_number}")
        response = await kyc_client.post_json(
            ENDPOINTS["credit_report_pdf"],
            data,
            authorization_token=authorization_token
        )
        
        # Log the complete response for debugging
        logger.debug(f"Raw credit report PDF response: {json.dumps(response.data, indent=2)}")
        logger.debug(f"Response status code: {response.status_code}")
        logger.debug(f"Response message: {response.message}")

        if not response.success:
            # Handle authentication errors
            if response.status_code == 401:
                return "Error: Authentication failed. Please check your API token."
            elif response.status_code == 403:
                return "Error: Access forbidden. Your API token lacks required permissions."
            
            # Extract error message
            error_msg = None
            if response.error:
                error_msg = response.error.replace("API Error: ", "")
            elif response.message:
                error_msg = response.message
            elif response.data and isinstance(response.data, dict):
                error_msg = (
                    response.data.get('message') or 
                    response.data.get('error') or 
                    response.data.get('detail')
                )
            
            if response.data:
                logger.debug(f"Full error response data: {json.dumps(response.data, indent=2)}")

            if error_msg:
                logger.error(f"Credit report PDF error: {error_msg}")
                if "Invalid" in error_msg or "not found" in error_msg.lower():
                    return f"Error: {error_msg}"
                return f"Error: Credit report PDF fetch failed - {error_msg}"
            else:
                logger.error("Unknown error in credit report PDF fetch")
                return "Error: Unable to fetch credit report PDF. Please check the provided details and try again."

        response_json = {
            'success': True,
            'data': response.data,
            'status_code': response.status_code,
            'message': response.message or 'Success',
            'message_code': response.message_code or 'success'
        }
        
        logger.debug(f"Processed credit report PDF response: {json.dumps(response_json, indent=2)}")
        return json.dumps(response_json, indent=2)
    except Exception as e:
        logger.error(f"Error fetching credit report PDF: {str(e)}")
        return f"Error: {str(e)}"

@mcp.tool()
async def credit_report_details(name: str, id_number: str, id_type: str, mobile: str,
                               consent: str, authorization_token: str = None) -> str:
    """Fetch credit report details

    Args:
        name: Person's name
        id_number: ID number (Aadhaar, etc.)
        id_type: Type of ID (e.g., aadhaar)
        mobile: Mobile number
        consent: Consent (Y/N)
        authorization_token: Authorization token (optional if set in environment)
    """
    await ensure_client_initialized()
    try:
        data = {
            "name": name,
            "id_number": id_number,
            "id_type": id_type,
            "mobile": mobile,
            "consent": consent
        }
        response = await kyc_client.post_json(
            ENDPOINTS["credit_report"],
            data,
            authorization_token=authorization_token
        )
        return json.dumps(response.model_dump(), indent=2)
    except Exception as e:
        logger.error(f"Error fetching credit report: {str(e)}")
        return f"Error: {str(e)}"

@mcp.tool()
async def pull_kra(id_number: str, dob: str) -> str:
    """Pull KRA details

    Args:
        id_number: PAN number
        dob: Date of birth (YYYY-MM-DD)
    """
    await ensure_client_initialized()
    try:
        data = {"id_number": id_number, "dob": dob}
        response = await kyc_client.post_json(ENDPOINTS["pull_kra"], data)
        return json.dumps(response.model_dump(), indent=2)
    except Exception as e:
        logger.error(f"Error pulling KRA: {str(e)}")
        return f"Error: {str(e)}"

@mcp.tool()
async def company_details(id_number: str, authorization_token: str = None) -> str:
    """Get company details by CIN

    Args:
        id_number: CIN number
        authorization_token: Authorization token (optional if set in environment)
    """
    await ensure_client_initialized()
    try:
        data = {"id_number": id_number}
        response = await kyc_client.post_json(
            ENDPOINTS["company_details"],
            data,
            authorization_token=authorization_token
        )
        return json.dumps(response.model_dump(), indent=2)
    except Exception as e:
        logger.error(f"Error getting company details: {str(e)}")
        return f"Error: {str(e)}"

# PEP and Legal Services
@mcp.tool()
async def pep_details(name: str, dob: str, nationality: str, address: str) -> str:
    """Check PEP (Politically Exposed Person) details

    Args:
        name: Person's name
        dob: Date of birth (YYYY-MM-DD)
        nationality: Nationality
        address: Address
    """
    await ensure_client_initialized()
    try:
        data = {
            "name": name,
            "dob": dob,
            "nationality": nationality,
            "address": address
        }
        response = await kyc_client.post_json(ENDPOINTS["pep_match"], data)
        return json.dumps(response.model_dump(), indent=2)
    except Exception as e:
        logger.error(f"Error checking PEP details: {str(e)}")
        return f"Error: {str(e)}"

# Bank and UPI Services
@mcp.tool()
async def upi_mobile_to_name(mobile_number: str) -> str:
    """Get account holder name from mobile number using UPI

    Args:
        mobile_number: Mobile number to lookup
    """
    await ensure_client_initialized()
    try:
        # Validate mobile number format (10 digits)
        import re
        if not re.match(r'^\d{10}$', mobile_number):
            return "Error: Invalid mobile number format. Mobile number should be 10 digits"
            
        data = {"mobile_number": mobile_number}
        logger.info(f"Making UPI mobile to name request for mobile: {mobile_number}")
            
        response = await kyc_client.post_json(ENDPOINTS["upi_mobile_name"], data)
        
        # Log the complete response for debugging
        logger.debug(f"Raw UPI mobile to name response: {json.dumps(response.data, indent=2)}")
        logger.debug(f"Response status code: {response.status_code}")
        logger.debug(f"Response message: {response.message}")

        if not response.success:
            # Handle authentication errors
            if response.status_code == 401:
                return "Error: Authentication failed. Please check your API token."
            elif response.status_code == 403:
                return "Error: Access forbidden. Your API token lacks required permissions."
            
            # Extract error message
            error_msg = None
            if response.error:
                error_msg = response.error.replace("API Error: ", "")
            elif response.message:
                error_msg = response.message
            elif response.data and isinstance(response.data, dict):
                error_msg = (
                    response.data.get('message') or 
                    response.data.get('error') or 
                    response.data.get('detail')
                )
            
            if response.data:
                logger.debug(f"Full error response data: {json.dumps(response.data, indent=2)}")

            if error_msg:
                logger.error(f"UPI mobile to name error: {error_msg}")
                if "Invalid" in error_msg or "not found" in error_msg.lower():
                    return f"Error: {error_msg}"
                return f"Error: UPI mobile to name lookup failed - {error_msg}"
            else:
                logger.error("Unknown error in UPI mobile to name lookup")
                return "Error: Unable to get name from mobile number. Please check the number and try again."

        response_json = {
            'success': True,
            'data': response.data,
            'status_code': response.status_code,
            'message': response.message or 'Success',
            'message_code': response.message_code or 'success'
        }
        
        logger.debug(f"Processed UPI mobile to name response: {json.dumps(response_json, indent=2)}")
        return json.dumps(response_json, indent=2)
    except Exception as e:
        logger.error(f"Error in UPI mobile to name lookup: {str(e)}")
        return f"Error: {str(e)}"

@mcp.tool()
async def bank_upi_verification(upi_id: str, authorization_token: str = None) -> str:
    """Verify UPI ID

    Args:
        upi_id: UPI ID to verify
        authorization_token: Authorization token (optional if set in environment)
    """
    await ensure_client_initialized()
    try:
        data = {"upi_id": upi_id}
        response = await kyc_client.post_json(
            ENDPOINTS["upi_verification"],
            data,
            authorization_token=authorization_token
        )
        return json.dumps(response.model_dump(), indent=2)
    except Exception as e:
        logger.error(f"Error verifying UPI: {str(e)}")
        return f"Error: {str(e)}"

@mcp.tool()
async def aadhaar_validation(id_number: str, authorization_token: str = None) -> str:
    """Validate Aadhaar number

    Args:
        id_number: Aadhaar number
        authorization_token: Authorization token (optional if set in environment)
    """
    await ensure_client_initialized()
    try:
        data = {"id_number": id_number}
        response = await kyc_client.post_json(
            ENDPOINTS["aadhaar_validation"],
            data,
            authorization_token=authorization_token
        )
        return json.dumps(response.model_dump(), indent=2)
    except Exception as e:
        logger.error(f"Error validating Aadhaar: {str(e)}")
        return f"Error: {str(e)}"

@mcp.tool()
async def udyog_aadhaar(id_number: str, authorization_token: str = None) -> str:
    """Verify Udyog Aadhaar

    Args:
        id_number: Udyog Aadhaar number
        authorization_token: Authorization token (optional if set in environment)
    """
    await ensure_client_initialized()
    try:
        data = {"id_number": id_number}
        response = await kyc_client.post_json(
            ENDPOINTS["udyog_aadhaar"],
            data,
            authorization_token=authorization_token
        )
        return json.dumps(response.model_dump(), indent=2)
    except Exception as e:
        logger.error(f"Error verifying Udyog Aadhaar: {str(e)}")
        return f"Error: {str(e)}"

@mcp.tool()
async def e_aadhaar_generate_otp(id_number: str, authorization_token: str = None) -> str:
    """Generate OTP for e-Aadhaar

    Args:
        id_number: Aadhaar number
        authorization_token: Authorization token (optional if set in environment)
    """
    await ensure_client_initialized()
    try:
        data = {"id_number": id_number}
        response = await kyc_client.post_json(
            ENDPOINTS["e_aadhaar"],
            data,
            authorization_token=authorization_token
        )
        return json.dumps(response.model_dump(), indent=2)
    except Exception as e:
        logger.error(f"Error generating e-Aadhaar OTP: {str(e)}")
        return f"Error: {str(e)}"

@mcp.tool()
async def pan_to_uan(pan_number: str, authorization_token: str = None) -> str:
    """Get UAN from PAN number

    Args:
        pan_number: PAN number
        authorization_token: Authorization token (optional if set in environment)
    """
    await ensure_client_initialized()
    try:
        data = {"pan_number": pan_number}
        response = await kyc_client.post_json(
            ENDPOINTS["pan_to_uan"],
            data,
            authorization_token=authorization_token
        )
        return json.dumps(response.model_dump(), indent=2)
    except Exception as e:
        logger.error(f"Error getting UAN from PAN: {str(e)}")
        return f"Error: {str(e)}"

@mcp.tool()
async def find_upi_id(mobile_number: str, authorization_token: str = None) -> str:
    """Find UPI ID by mobile number

    Args:
        mobile_number: Mobile number to search for UPI IDs
        authorization_token: Authorization token (optional if set in environment)
    """
    await ensure_client_initialized()
    try:
        # Validate mobile number format (10 digits)
        import re
        if not re.match(r'^\d{10}$', mobile_number):
            return "Error: Invalid mobile number format. Mobile number should be 10 digits"
            
        data = {"mobile_number": mobile_number}
        logger.info(f"Making find UPI ID request for mobile: {mobile_number}")
            
        response = await kyc_client.post_json(
            ENDPOINTS["find_upi_id"],
            data,
            authorization_token=authorization_token
        )
        
        # Log the complete response for debugging
        logger.debug(f"Raw find UPI ID response: {json.dumps(response.data, indent=2)}")
        logger.debug(f"Response status code: {response.status_code}")
        logger.debug(f"Response message: {response.message}")

        if not response.success:
            # Handle authentication errors
            if response.status_code == 401:
                return "Error: Authentication failed. Please check your API token."
            elif response.status_code == 403:
                return "Error: Access forbidden. Your API token lacks required permissions."
            
            # Extract error message
            error_msg = None
            if response.error:
                error_msg = response.error.replace("API Error: ", "")
            elif response.message:
                error_msg = response.message
            elif response.data and isinstance(response.data, dict):
                error_msg = (
                    response.data.get('message') or 
                    response.data.get('error') or 
                    response.data.get('detail')
                )
            
            if response.data:
                logger.debug(f"Full error response data: {json.dumps(response.data, indent=2)}")

            if error_msg:
                logger.error(f"Find UPI ID error: {error_msg}")
                if "Invalid" in error_msg or "not found" in error_msg.lower():
                    return f"Error: {error_msg}"
                return f"Error: Find UPI ID failed - {error_msg}"
            else:
                logger.error("Unknown error in find UPI ID request")
                return "Error: Unable to find UPI ID. Please check the mobile number and try again."

        response_json = {
            'success': True,
            'data': response.data,
            'status_code': response.status_code,
            'message': response.message or 'Success',
            'message_code': response.message_code or 'success'
        }
        
        logger.debug(f"Processed find UPI ID response: {json.dumps(response_json, indent=2)}")
        return json.dumps(response_json, indent=2)
    except Exception as e:
        logger.error(f"Error in find UPI ID: {str(e)}")
        return f"Error: {str(e)}"

# Additional Services
@mcp.tool()
async def name_matching(name_1: str, name_2: str, name_type: str, authorization_token: str = None) -> str:
    """Match two names for similarity

    Args:
        name_1: First name
        name_2: Second name
        name_type: Type of name (e.g., person)
        authorization_token: Authorization token (optional if set in environment)
    """
    try:
        data = {"name_1": name_1, "name_2": name_2, "name_type": name_type}
        response = await kyc_client.post_json(
            ENDPOINTS["name_matching"],
            data,
            authorization_token=authorization_token
        )
        return json.dumps(response.model_dump(), indent=2)
    except Exception as e:
        logger.error(f"Error matching names: {str(e)}")
        return f"Error: {str(e)}"

@mcp.tool()
async def corporate_din(id_number: str) -> str:
    """Get corporate DIN details

    Args:
        id_number: DIN number
    """
    try:
        data = {"id_number": id_number}
        response = await kyc_client.post_json(ENDPOINTS["din"], data)
        return json.dumps(response.model_dump(), indent=2)
    except Exception as e:
        logger.error(f"Error getting DIN details: {str(e)}")
        return f"Error: {str(e)}"

@mcp.tool()
async def mobile_to_bank_details(mobile_no: str, authorization_token: str = None) -> str:
    """Get bank details from mobile number

    Args:
        mobile_no: Mobile number
        authorization_token: Authorization token (optional if set in environment)
    """
    try:
        data = {"mobile_no": mobile_no}
        response = await kyc_client.post_json(
            ENDPOINTS["mobile_to_bank"],
            data,
            authorization_token=authorization_token
        )
        return json.dumps(response.model_dump(), indent=2)
    except Exception as e:
        logger.error(f"Error getting bank details from mobile: {str(e)}")
        return f"Error: {str(e)}"

@mcp.tool()
async def esic_details(id_number: str) -> str:
    """Get ESIC details

    Args:
        id_number: ESIC number
    """
    try:
        data = {"id_number": id_number}
        response = await kyc_client.post_json(ENDPOINTS["esic_details"], data)
        return json.dumps(response.model_dump(), indent=2)
    except Exception as e:
        logger.error(f"Error getting ESIC details: {str(e)}")
        return f"Error: {str(e)}"

@mcp.tool()
async def rc_full_details(id_number: str, authorization_token: str = None) -> str:
    """Get full RC details

    Args:
        id_number: RC number
        authorization_token: Authorization token (optional if set in environment)
    """
    try:
        data = {"id_number": id_number}
        response = await kyc_client.post_json(
            ENDPOINTS["rc_full"],
            data,
            authorization_token=authorization_token
        )
        return json.dumps(response.model_dump(), indent=2)
    except Exception as e:
        logger.error(f"Error getting RC details: {str(e)}")
        return f"Error: {str(e)}"

@mcp.tool()
async def aadhaar_pan_link_check(aadhaar_number: str, authorization_token: str = None) -> str:
    """Check if Aadhaar is linked to PAN

    Args:
        aadhaar_number: Aadhaar number
        authorization_token: Authorization token (optional if set in environment)
    """
    try:
        data = {"aadhaar_number": aadhaar_number}
        response = await kyc_client.post_json(
            ENDPOINTS["aadhaar_pan_link"],
            data,
            authorization_token=authorization_token
        )
        return json.dumps(response.model_dump(), indent=2)
    except Exception as e:
        logger.error(f"Error checking Aadhaar-PAN link: {str(e)}")
        return f"Error: {str(e)}"

@mcp.tool()
async def verify_mobile_to_pan(name: str, mobile_no: str, authorization_token: str = None) -> str:
    """Get PAN details from name and mobile number

    Args:
        name: Person's name
        mobile_no: Mobile number
        authorization_token: Authorization token (optional if set in environment)
    """
    await ensure_client_initialized()
    try:
        # Validate input parameters
        if not name or not name.strip():
            return "Error: Name cannot be empty"
        if not mobile_no or not mobile_no.strip():
            return "Error: Mobile number cannot be empty"
            
        # Clean and format the data
        data = {
            "name": name.strip(),
            "mobile_no": mobile_no.strip()
        }
        logger.info(f"Making mobile-to-PAN request for name: {name}, mobile: {mobile_no}")
        response = await kyc_client.post_json(
            ENDPOINTS["mobile_to_pan"],
            data,
            authorization_token=authorization_token
        )
        if not response.success:
            error_msg = None
            if response.error:
                error_msg = response.error.replace("API Error: ", "")  # Remove prefix if present
            elif response.message:
                error_msg = response.message
            elif response.data and isinstance(response.data, dict):
                error_msg = (
                    response.data.get('message') or 
                    response.data.get('error') or 
                    "Verification failed"
                )
            
            # Log full response data for debugging
            if response.data:
                logger.debug(f"Error response data: {json.dumps(response.data, indent=2)}")
            
            return f"Error: {error_msg}"
            
        return json.dumps(response.model_dump(), indent=2)
    except Exception as e:
        logger.error(f"Error getting PAN from mobile: {str(e)}")
        return f"Error: {str(e)}"

@mcp.tool()
async def lei_verification(lei_code: str) -> str:
    """Verify LEI code

    Args:
        lei_code: LEI code to verify
    """
    try:
        data = {"lei_code": lei_code}
        response = await kyc_client.post_json(ENDPOINTS["lei_validation"], data)
        return json.dumps(response.model_dump(), indent=2)
    except Exception as e:
        logger.error(f"Error verifying LEI: {str(e)}")
        return f"Error: {str(e)}"

# OCR and File-based Services
@mcp.tool()
async def ocr_gst_lut(file_path: str) -> str:
    """OCR GST LUT document

    Args:
        file_path: Path to the GST document file
    """
    try:
        files = {"file": file_path}
        response = await kyc_client.post_form(ENDPOINTS["ocr_gst"], files)
        return json.dumps(response.model_dump(), indent=2)
    except Exception as e:
        logger.error(f"Error processing GST OCR: {str(e)}")
        return f"Error: {str(e)}"

@mcp.tool()
async def ocr_passport(file_path: str) -> str:
    """OCR Passport document

    Args:
        file_path: Path to the passport file
    """
    try:
        files = {"file": file_path}
        response = await kyc_client.post_form(ENDPOINTS["ocr_passport"], files)
        return json.dumps(response.model_dump(), indent=2)
    except Exception as e:
        logger.error(f"Error processing Passport OCR: {str(e)}")
        return f"Error: {str(e)}"

@mcp.tool()
async def ocr_license(front_file_path: str) -> str:
    """OCR License document

    Args:
        front_file_path: Path to the front side of license file
    """
    try:
        files = {"front": front_file_path}
        response = await kyc_client.post_form(ENDPOINTS["ocr_license"], files)
        return json.dumps(response.model_dump(), indent=2)
    except Exception as e:
        logger.error(f"Error processing License OCR: {str(e)}")
        return f"Error: {str(e)}"

@mcp.tool()
async def ocr_itr(file_path: str, use_pdf: str = "true") -> str:
    """OCR ITR document

    Args:
        file_path: Path to the ITR file
        use_pdf: Whether to use PDF processing (default: true)
    """
    try:
        files = {"file": file_path}
        data = {"use_pdf": use_pdf}
        response = await kyc_client.post_form(ENDPOINTS["ocr_itr"], files, data)
        return json.dumps(response.model_dump(), indent=2)
    except Exception as e:
        logger.error(f"Error processing ITR OCR: {str(e)}")
        return f"Error: {str(e)}"

@mcp.tool()
async def ocr_voter(file_path: str) -> str:
    """OCR Voter ID document

    Args:
        file_path: Path to the voter ID file
    """
    try:
        files = {"file": file_path}
        response = await kyc_client.post_form(ENDPOINTS["ocr_voter"], files)
        return json.dumps(response.model_dump(), indent=2)
    except Exception as e:
        logger.error(f"Error processing Voter ID OCR: {str(e)}")
        return f"Error: {str(e)}"

@mcp.tool()
async def face_liveness(file_path: str) -> str:
    """Check face liveness

    Args:
        file_path: Path to the face image file
    """
    try:
        files = {"file": file_path}
        response = await kyc_client.post_form(ENDPOINTS["face_liveness"], files)
        return json.dumps(response.model_dump(), indent=2)
    except Exception as e:
        logger.error(f"Error checking face liveness: {str(e)}")
        return f"Error: {str(e)}"

@mcp.tool()
async def face_match(selfie_path: str, id_card_path: str) -> str:
    """Match face between selfie and ID card

    Args:
        selfie_path: Path to the selfie image
        id_card_path: Path to the ID card image
    """
    try:
        files = {"selfie": selfie_path, "id_card": id_card_path}
        response = await kyc_client.post_form(ENDPOINTS["face_match"], files)
        return json.dumps(response.model_dump(), indent=2)
    except Exception as e:
        logger.error(f"Error matching faces: {str(e)}")
        return f"Error: {str(e)}"

@mcp.tool()
async def face_background_remover(file_path: str, authorization_token: str = None) -> str:
    """Remove background from face image

    Args:
        file_path: Path to the face image file
        authorization_token: Authorization token (optional if set in environment)
    """
    try:
        files = {"file": file_path}
        response = await kyc_client.post_form(
            ENDPOINTS["face_background_remover"],
            files,
            authorization_token=authorization_token
        )
        return json.dumps(response.model_dump(), indent=2)
    except Exception as e:
        logger.error(f"Error removing background: {str(e)}")
        return f"Error: {str(e)}"

@mcp.tool()
async def ocr_document_detect(file_path: str) -> str:
    """Detect document type using OCR

    Args:
        file_path: Path to the document file
    """
    try:
        files = {"file": file_path}
        response = await kyc_client.post_form(ENDPOINTS["ocr_document_detect"], files)
        return json.dumps(response.model_dump(), indent=2)
    except Exception as e:
        logger.error(f"Error detecting document: {str(e)}")
        return f"Error: {str(e)}"

# Additional OCR Services
@mcp.tool()
async def face_extract(image_path: str, authorization_token: str = None) -> str:
    """Extract face from image

    Args:
        image_path: Path to the image file
        authorization_token: Authorization token (optional if set in environment)
    """
    try:
        files = {"image": image_path}
        response = await kyc_client.post_form(
            ENDPOINTS["face_extract"],
            files,
            authorization_token=authorization_token
        )
        return json.dumps(response.model_dump(), indent=2)
    except Exception as e:
        logger.error(f"Error extracting face: {str(e)}")
        return f"Error: {str(e)}"

@mcp.tool()
@mcp.tool()
async def ocr_cheque(file_path: str, authorization_token: str = None) -> str:
    """OCR Cheque document

    Args:
        file_path: Path to the cheque file
        authorization_token: Authorization token (optional if set in environment)
    """
    try:
        files = {"file": file_path}
        response = await kyc_client.post_form(
            ENDPOINTS["ocr_cheque"],
            files,
            authorization_token=authorization_token
        )
        return json.dumps(response.model_dump(), indent=2)
    except Exception as e:
        logger.error(f"Error processing Cheque OCR: {str(e)}")
        return f"Error: {str(e)}"

@mcp.tool()
async def ocr_pan(file_path: str) -> str:
    """OCR PAN card document

    Args:
        file_path: Path to the PAN card file
    """
    try:
        files = {"file": file_path}
        response = await kyc_client.post_form(ENDPOINTS["ocr_pan"], files)
        return json.dumps(response.model_dump(), indent=2)
    except Exception as e:
        logger.error(f"Error processing PAN OCR: {str(e)}")
        return f"Error: {str(e)}"

@mcp.tool()
async def aadhaar_qr_upload(qr_text: str) -> str:
    """Upload Aadhaar QR text

    Args:
        qr_text: QR text content
    """
    try:
        files = {"qr_text": qr_text}
        response = await kyc_client.post_form(ENDPOINTS["aadhaar_qr"], files)
        return json.dumps(response.model_dump(), indent=2)
    except Exception as e:
        logger.error(f"Error uploading Aadhaar QR: {str(e)}")
        return f"Error: {str(e)}"

# Special form-based services that use different parameter names
@mcp.tool()
async def ocr_gst(file_path: str) -> str:
    """OCR GST document

    Args:
        file_path: Path to the GST document file
    """
    try:
        files = {"file": file_path}
        response = await kyc_client.post_form(ENDPOINTS["ocr_gst"], files)
        return json.dumps(response.model_dump(), indent=2)
    except Exception as e:
        logger.error(f"Error processing GST OCR: {str(e)}")
        return f"Error: {str(e)}"

# Add resources
@mcp.resource("kyc://api/documentation")
def get_documentation() -> str:
    """Get KYC API documentation"""
    return """
KYC Verification MCP Server Documentation

This server provides comprehensive access to KYC (Know Your Customer) verification services
through the SurePass API. Available services include:

DOCUMENT VERIFICATION:
- TAN verification and TDS check
- Voter ID verification
- Driving License verification
- Passport verification
- Aadhaar verification, OTP generation, and validation
- PAN card verification and PAN to UAN conversion
- ITR compliance check
- Pull KRA details
- E-Aadhaar OTP generation
- Aadhaar-PAN link check
- Aadhaar QR upload

BANK & FINANCIAL VERIFICATION:
- Bank account verification
- UPI ID verification and discovery
- IFSC code validation
- Mobile to bank details mapping
- Credit report generation
- ESIC details verification

CORPORATE VERIFICATION:
- GSTIN verification (basic and advanced)
- GSTIN by PAN lookup
- Company CIN verification and details
- Director phone details
- Corporate DIN verification
- Udyog Aadhaar verification
- Company name to CIN search

OCR SERVICES:
- PAN card OCR
- Passport OCR
- Driving License OCR
- Voter ID OCR
- GST document OCR
- ITR document OCR
- Cheque OCR
- Document type detection

FACE & BIOMETRIC SERVICES:
- Face liveness detection
- Face matching between selfie and ID
- Face extraction from images
- Background removal from face images

LEGAL & COMPLIANCE:
- CKYC search
- Court case search (eCourts)
- CNR-based court search
- PEP (Politically Exposed Person) matching
- LEI code verification

VEHICLE SERVICES:
- RC (Registration Certificate) full details
- RC to mobile number mapping

UTILITY SERVICES:
- Electricity bill verification
- Telecom OTP generation and verification
- Email employment check
- Name matching utility
- Prefill report generation v2

Usage Notes:
- Each tool requires specific parameters as documented in the tool schemas
- Most tools require authorization tokens for API access (can be set via environment variables)
- File-based tools (OCR, face verification) require valid file paths
- Some tools support both required and optional authorization tokens
- All responses are returned in JSON format for easy parsing
"""

# Universal Database Search Tools
@mcp.tool()
async def search_person_by_pan(pan_number: str) -> str:
    """Search for person by PAN number across all verification types

    Args:
        pan_number: PAN number to search for (e.g., "EKRPR1234F")
    """
    if not DATABASE_ENABLED:
        return "Error: Database storage is disabled. Enable it by setting KYC_DATABASE_ENABLED=true"

    try:
        # Validate PAN format
        import re
        if not re.match(r'^[A-Z]{5}[0-9]{4}[A-Z]$', pan_number):
            return "Error: Invalid PAN format. PAN should be in format AAAAA9999A"

        persons = await universal_db_manager.search_record('pan', pan_number.upper())

        if persons:
            # Get complete profiles for all found persons
            complete_profiles = []
            for person in persons:
                profile = await universal_db_manager.get_person_complete_profile(person.id)
                if profile:
                    complete_profiles.append(profile)

            result = {
                'success': True,
                'found': True,
                'count': len(complete_profiles),
                'persons': complete_profiles,
                'message': f'Found {len(complete_profiles)} person(s) with PAN {pan_number}'
            }
        else:
            result = {
                'success': True,
                'found': False,
                'count': 0,
                'persons': [],
                'message': f'No person found with PAN {pan_number}'
            }

        return json.dumps(result, indent=2)

    except Exception as e:
        logger.error(f"Error searching person by PAN: {str(e)}")
        return f"Error: {str(e)}"

@mcp.tool()
async def search_person_by_name(name: str, exact_match: bool = False) -> str:
    """Search for persons by name across all verification types

    Args:
        name: Name to search for
        exact_match: Whether to perform exact match (default: False for partial match)
    """
    if not DATABASE_ENABLED:
        return "Error: Database storage is disabled. Enable it by setting KYC_DATABASE_ENABLED=true"

    try:
        if not name or not name.strip():
            return "Error: Name cannot be empty"

        persons = await universal_db_manager.search_person_by_identifier('name', name.strip())

        if persons:
            # Get complete profiles for all found persons
            complete_profiles = []
            for person in persons:
                profile = await universal_db_manager.get_person_complete_profile(person.id)
                if profile:
                    complete_profiles.append(profile)

            result = {
                'success': True,
                'found': True,
                'count': len(complete_profiles),
                'persons': complete_profiles,
                'message': f'Found {len(complete_profiles)} person(s) matching name "{name}"'
            }
        else:
            result = {
                'success': True,
                'found': False,
                'count': 0,
                'persons': [],
                'message': f'No persons found matching name "{name}"'
            }

        return json.dumps(result, indent=2)

    except Exception as e:
        logger.error(f"Error searching person by name: {str(e)}")
        return f"Error: {str(e)}"

@mcp.tool()
async def search_person_by_phone(phone_number: str) -> str:
    """Search for persons by phone number across all verification types

    Args:
        phone_number: Phone number to search for
    """
    if not DATABASE_ENABLED:
        return "Error: Database storage is disabled. Enable it by setting KYC_DATABASE_ENABLED=true"

    try:
        if not phone_number or not phone_number.strip():
            return "Error: Phone number cannot be empty"

        persons = await universal_db_manager.search_person_by_identifier('phone', phone_number.strip())

        if persons:
            # Get complete profiles for all found persons
            complete_profiles = []
            for person in persons:
                profile = await universal_db_manager.get_person_complete_profile(person.id)
                if profile:
                    complete_profiles.append(profile)

            result = {
                'success': True,
                'found': True,
                'count': len(complete_profiles),
                'persons': complete_profiles,
                'message': f'Found {len(complete_profiles)} person(s) with phone number "{phone_number}"'
            }
        else:
            result = {
                'success': True,
                'found': False,
                'count': 0,
                'persons': [],
                'message': f'No persons found with phone number "{phone_number}"'
            }

        return json.dumps(result, indent=2)

    except Exception as e:
        logger.error(f"Error searching person by phone: {str(e)}")
        return f"Error: {str(e)}"

@mcp.tool()
async def get_person_complete_profile_tool(person_id: int) -> str:
    """Get complete profile of a person including all verifications, documents, and contacts

    Args:
        person_id: Person ID to get profile for
    """
    if not DATABASE_ENABLED:
        return "Error: Database storage is disabled. Enable it by setting KYC_DATABASE_ENABLED=true"

    try:
        profile = await universal_db_manager.get_person_complete_profile(person_id)

        if profile:
            result = {
                'success': True,
                'found': True,
                'profile': profile,
                'message': f'Retrieved complete profile for person ID {person_id}'
            }
        else:
            result = {
                'success': True,
                'found': False,
                'profile': None,
                'message': f'No person found with ID {person_id}'
            }

        return json.dumps(result, indent=2)

    except Exception as e:
        logger.error(f"Error getting person profile: {str(e)}")
        return f"Error: {str(e)}"

# Legacy Database Search Tools (PAN-specific)
@mcp.tool()
async def search_pan_database(pan_number: str) -> str:
    """Search for PAN record in local database

    Args:
        pan_number: PAN number to search for (e.g., "EKRPR1234F")
    """
    if not DATABASE_ENABLED:
        return "Error: Database storage is disabled. Enable it by setting KYC_DATABASE_ENABLED=true"

    try:
        # Validate PAN format
        import re
        if not re.match(r'^[A-Z]{5}[0-9]{4}[A-Z]$', pan_number):
            return "Error: Invalid PAN format. PAN should be in format AAAAA9999A"

        record = await db_manager.search_by_pan(pan_number.upper())

        if record:
            result = {
                'success': True,
                'found': True,
                'record': record.to_dict(),
                'message': f'Found PAN record for {pan_number}'
            }
        else:
            result = {
                'success': True,
                'found': False,
                'record': None,
                'message': f'No record found for PAN {pan_number}'
            }

        return json.dumps(result, indent=2)

    except Exception as e:
        logger.error(f"Error searching PAN database: {str(e)}")
        return f"Error: {str(e)}"

@mcp.tool()
async def search_name_database(name: str, exact_match: bool = False) -> str:
    """Search for records by name in local database

    Args:
        name: Name to search for
        exact_match: Whether to perform exact match (default: False for partial match)
    """
    if not DATABASE_ENABLED:
        return "Error: Database storage is disabled. Enable it by setting KYC_DATABASE_ENABLED=true"

    try:
        if not name or not name.strip():
            return "Error: Name cannot be empty"

        records = await db_manager.search_by_name(name.strip(), exact_match)

        result = {
            'success': True,
            'found': len(records) > 0,
            'count': len(records),
            'records': [record.to_dict() for record in records],
            'message': f'Found {len(records)} record(s) for name "{name}"'
        }

        return json.dumps(result, indent=2)

    except Exception as e:
        logger.error(f"Error searching name database: {str(e)}")
        return f"Error: {str(e)}"

@mcp.tool()
async def search_phone_database(phone_number: str) -> str:
    """Search for records by phone number in local database

    Args:
        phone_number: Phone number to search for
    """
    if not DATABASE_ENABLED:
        return "Error: Database storage is disabled. Enable it by setting KYC_DATABASE_ENABLED=true"

    try:
        if not phone_number or not phone_number.strip():
            return "Error: Phone number cannot be empty"

        records = await db_manager.search_by_phone(phone_number.strip())

        result = {
            'success': True,
            'found': len(records) > 0,
            'count': len(records),
            'records': [record.to_dict() for record in records],
            'message': f'Found {len(records)} record(s) for phone number "{phone_number}"'
        }

        return json.dumps(result, indent=2)

    except Exception as e:
        logger.error(f"Error searching phone database: {str(e)}")
        return f"Error: {str(e)}"

@mcp.tool()
async def search_email_database(email: str) -> str:
    """Search for records by email in local database

    Args:
        email: Email address to search for
    """
    if not DATABASE_ENABLED:
        return "Error: Database storage is disabled. Enable it by setting KYC_DATABASE_ENABLED=true"

    try:
        if not email or not email.strip():
            return "Error: Email cannot be empty"

        records = await db_manager.search_by_email(email.strip())

        result = {
            'success': True,
            'found': len(records) > 0,
            'count': len(records),
            'records': [record.to_dict() for record in records],
            'message': f'Found {len(records)} record(s) for email "{email}"'
        }

        return json.dumps(result, indent=2)

    except Exception as e:
        logger.error(f"Error searching email database: {str(e)}")
        return f"Error: {str(e)}"

@mcp.tool()
async def get_database_statistics() -> str:
    """Get database statistics and information"""
    if not DATABASE_ENABLED:
        return "Error: Database storage is disabled. Enable it by setting KYC_DATABASE_ENABLED=true"

    try:
        stats = await db_manager.get_statistics()

        result = {
            'success': True,
            'statistics': stats,
            'message': 'Database statistics retrieved successfully'
        }

        return json.dumps(result, indent=2)

    except Exception as e:
        logger.error(f"Error getting database statistics: {str(e)}")
        return f"Error: {str(e)}"

@mcp.tool()
async def list_recent_records(limit: int = 10) -> str:
    """List recent PAN records from database

    Args:
        limit: Maximum number of records to return (default: 10, max: 100)
    """
    if not DATABASE_ENABLED:
        return "Error: Database storage is disabled. Enable it by setting KYC_DATABASE_ENABLED=true"

    try:
        # Validate limit
        if limit < 1:
            limit = 10
        elif limit > 100:
            limit = 100

        records = await db_manager.get_all_records(limit=limit)

        result = {
            'success': True,
            'count': len(records),
            'records': [record.to_dict() for record in records],
            'message': f'Retrieved {len(records)} recent record(s)'
        }

        return json.dumps(result, indent=2)

    except Exception as e:
        logger.error(f"Error listing recent records: {str(e)}")
        return f"Error: {str(e)}"

@mcp.resource("kyc://api/endpoints")
def get_endpoints() -> str:
    """Get API endpoints list"""
    return json.dumps(ENDPOINTS, indent=2)


if __name__ == "__main__":
    mcp.run()