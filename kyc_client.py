"""HTTP client for SurePass KYC API"""

import httpx
import logging
from typing import Dict, Any, Optional, Union
import json
from pathlib import Path

from config import BASE_URL, DEFAULT_HEADERS, MULTIPART_HEADERS, SUREPASS_API_TOKEN, ENDPOINTS
from models import KYCResponse, APIError

logger = logging.getLogger("kyc-mcp-server")


class KYCClient:
    """HTTP client for KYC API operations"""
    
    def __init__(self, timeout: int = 60):  # Increased default timeout
        self.base_url = BASE_URL
        self.timeout = timeout

        # Configure client with aggressive retry and timeout settings for network issues
        transport = httpx.HTTPTransport(
            retries=5,  # More retries
            verify=True
        )

        self.client = httpx.AsyncClient(
            timeout=httpx.Timeout(
                timeout,
                connect=30.0,  # Longer connect timeout
                read=30.0,     # Longer read timeout
                write=30.0,    # Longer write timeout
                pool=30.0      # Longer pool timeout
            ),
            limits=httpx.Limits(
                max_keepalive_connections=10,
                max_connections=20,
                keepalive_expiry=30.0
            ),
            verify=True,
            trust_env=True,
            follow_redirects=True,
            transport=transport
        )
    
    async def __aenter__(self):
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.client.aclose()
    
    def _prepare_headers(self, authorization_token: Optional[str] = None,
                        is_multipart: bool = False) -> Dict[str, str]:
        """Prepare headers for API request"""
        if is_multipart:
            headers = {}  # Let httpx set Content-Type for multipart
        else:
            headers = DEFAULT_HEADERS.copy()

        if authorization_token:
            if authorization_token.startswith('Bearer '):
                headers["Authorization"] = authorization_token
            else:
                headers["Authorization"] = f"Bearer {authorization_token}"

        return headers
    
    async def post_json(self, endpoint: str, data: Dict[str, Any],
                       authorization_token: Optional[str] = None) -> KYCResponse:
        """Make a POST request with JSON data"""
        url = f"{self.base_url}{endpoint}"
        # Use environment token if none provided
        if authorization_token is None:
            authorization_token = SUREPASS_API_TOKEN
            
        # Validate API token
        if not authorization_token:
            error_msg = ("No API token provided. Please set the SUREPASS_API_TOKEN environment variable "
                      "or pass an authorization_token parameter.")
            logger.error(error_msg)
            return KYCResponse(success=False, error=error_msg, status_code=401)
            
        headers = self._prepare_headers(authorization_token)
        
        try:
            logger.info(f"Making request to {url}")
            logger.debug(f"Request headers: {headers}")
            logger.debug(f"Request data: {data}")
            request_data = {}
            if endpoint == ENDPOINTS["pan_comprehensive"]:
                # Format specifically for PAN comprehensive v2 endpoint
                request_data = {
                    "id_number": data["id_number"],
                    "get_father_name": True,   # Get father's name if available
                    "get_address": True,       # Get complete address details
                    "get_gender": True,        # Get gender information
                    "get_minor_flag": True,    # Get minor status
                    "consent": "Y",            # Required for full data access
                    "get_pdf": True,           # Get PDF document if available
                    "get_extra_payload_text": True  # Get any additional information
                }
            elif endpoint == ENDPOINTS["pan"]:
                # Basic PAN verification format
                request_data = {
                    "id_number": data["id_number"]
                }
                logger.debug("Using basic PAN verification format")
            else:
                request_data = data
                logger.debug(f"Using default request format for endpoint: {endpoint}")

            response = await self.client.post(url, json=request_data, headers=headers)
            if response.status_code != 200:
                error_msg = f"API error: Status {response.status_code}, Response: {response.text}"
                logger.error(error_msg)
                if response.status_code == 401:
                    error_msg = ("Authentication failed. Please check your API token and ensure it has "
                               "the required permissions for this operation.")
                elif response.status_code == 403:
                    error_msg = ("Access forbidden. Your API token may not have permission to access "
                               "this endpoint.")
                return KYCResponse(success=False, error=error_msg, status_code=response.status_code)
            return self._handle_response(response, endpoint)
        except httpx.RequestError as e:
            error_msg = str(e)
            logger.error(f"HTTP request failed: {error_msg}")

            # Provide more descriptive error messages for common network issues
            if "All connection attempts failed" in error_msg:
                error_msg = (
                    "Network connection failed. This could be due to:\n"
                    "1. Firewall blocking HTTPS connections to kyc-api.surepass.io\n"
                    "2. Corporate network restrictions\n"
                    "3. ISP blocking the connection\n"
                    "4. The API server may be temporarily unavailable\n"
                    f"Original error: {error_msg}"
                )
            elif "ConnectionError" in error_msg:
                error_msg = (
                    "Connection failed. Please check:\n"
                    "1. Your internet connection\n"
                    "2. Firewall settings (allow HTTPS to kyc-api.surepass.io)\n"
                    "3. Proxy settings if behind corporate network\n"
                    f"Original error: {error_msg}"
                )
            elif "TimeoutError" in error_msg or "ConnectTimeout" in error_msg:
                error_msg = (
                    "Connection timed out. The server took too long to respond.\n"
                    "This might indicate network connectivity issues or server overload.\n"
                    f"Original error: {error_msg}"
                )

            return KYCResponse(success=False, error=error_msg, status_code=None)
    
    async def post_form(self, endpoint: str, files: Dict[str, Any],
                       data: Optional[Dict[str, str]] = None,
                       authorization_token: Optional[str] = None) -> KYCResponse:
        """Make a POST request with form data (file upload)"""
        url = f"{self.base_url}{endpoint}"
        # Use environment token if none provided
        if authorization_token is None:
            authorization_token = SUREPASS_API_TOKEN
            
        # Validate API token
        if not authorization_token:
            error_msg = ("No API token provided. Please set the SUREPASS_API_TOKEN environment variable "
                      "or pass an authorization_token parameter.")
            logger.error(error_msg)
            return KYCResponse(success=False, error=error_msg, status_code=401)
            
        headers = self._prepare_headers(authorization_token, is_multipart=True)
        
        try:
            # Prepare files for upload
            prepared_files = {}
            for key, file_path in files.items():
                if isinstance(file_path, str):
                    file_path = Path(file_path)
                if file_path.exists():
                    prepared_files[key] = open(file_path, 'rb')
                else:
                    raise APIError(f"File not found: {file_path}")
            
            logger.info(f"Making form request to {url}")
            logger.debug(f"Request headers: {headers}")
            logger.debug(f"Request data: {data}")
            response = await self.client.post(url, files=prepared_files, 
                                            data=data or {}, headers=headers)
            
            # Close file handles
            for file_handle in prepared_files.values():
                file_handle.close()
            
            if response.status_code != 200:
                error_msg = f"API error: Status {response.status_code}, Response: {response.text}"
                logger.error(error_msg)
                if response.status_code == 401:
                    error_msg = ("Authentication failed. Please check your API token and ensure it has "
                               "the required permissions for this operation.")
                elif response.status_code == 403:
                    error_msg = ("Access forbidden. Your API token may not have permission to access "
                               "this endpoint.")
                return KYCResponse(success=False, error=error_msg, status_code=response.status_code)
            return self._handle_response(response, endpoint)  # Pass endpoint to handler
        except httpx.RequestError as e:
            error_msg = str(e)
            logger.error(f"HTTP form request failed: {error_msg}")
            # Provide more descriptive error messages for common issues
            if "ConnectionError" in error_msg:
                error_msg = ("Connection failed. Please check your internet connection and verify "
                           "the API base URL is correct.")
            elif "TimeoutError" in error_msg:
                error_msg = "Request timed out. The server took too long to respond."
            elif "ConnectTimeout" in error_msg:
                error_msg = "Connection timed out. Could not establish connection to the server."
            return KYCResponse(success=False, error=error_msg, status_code=None)
    
    def _handle_response(self, response: httpx.Response, endpoint: str) -> KYCResponse:
        """Handle HTTP response"""
        try:
            if response.status_code == 200:
                raw_data = response.json()
                # Handle both success and error responses from the API
                success = raw_data.get('success', True)  # Default to True for backward compatibility
                status_code = raw_data.get('status_code', response.status_code)
                message = raw_data.get('message')
                message_code = raw_data.get('message_code')
                
                # Check response format and extract data
                if 'data' in raw_data:
                    data = raw_data['data']
                    logger.debug(f"Response contains data field for endpoint {endpoint}: {json.dumps(data, indent=2)}")
                else:
                    # Some endpoints (like basic PAN) return data at root level
                    logger.info(f"No 'data' field found in response for endpoint {endpoint}, using root level")
                    data = raw_data
                    # For basic PAN endpoint, make sure we have standard fields
                    if endpoint == ENDPOINTS["pan"]:
                        data.setdefault('success', success)
                        data.setdefault('status_code', status_code)
                        data.setdefault('message', message or 'Verification completed')
                    logger.debug(f"Using root level as data for endpoint {endpoint}: {json.dumps(data, indent=2)}")

                logger.info(f"Processing response for endpoint: {endpoint}")

                # For PAN comprehensive endpoint, ensure proper structure with address
                if isinstance(data, dict) and endpoint == ENDPOINTS["pan_comprehensive"]:
                    logger.debug(f"Processing PAN comprehensive data")
                    
                    # Handle address data for PAN comprehensive
                    # Extract address components from response if available
                    # Initialize address data with None values
                    address_data = {
                        'line_1': None,
                        'line_2': None,
                        'street_name': None,
                        'zip': None,
                        'city': None,
                        'state': None,
                        'country': None,
                        'full': None
                    }

                    # Use the exact field names from the API response
                    address_fields = ['line_1', 'line_2', 'street_name', 'zip', 'city', 'state', 'country', 'full']

                    # If address is present in the response, copy it directly
                    if 'address' in data and isinstance(data['address'], dict):
                        address_response = data['address']
                        logger.debug(f"Found address in response: {json.dumps(address_response, indent=2)}")
                        # Copy each field, ensuring we maintain the exact structure
                        for field in address_fields:
                            if field in address_response:
                                value = address_response[field]
                                if value is not None:  # Allow empty strings and 0 values
                                    if isinstance(value, (str, int)):
                                        address_data[field] = str(value).strip()
                                    else:
                                        logger.warning(f"Unexpected type for address field {field}: {type(value)}")
                    else:
                        logger.warning("No address object found in response, checking root level fields")
                        # If no address in response, check if fields are at root level
                        for field in address_fields:
                            if field in data:
                                value = data.pop(field, None)
                                if value is not None:  # Allow empty strings and 0 values
                                    if isinstance(value, (str, int)):
                                        address_data[field] = str(value).strip()
                                    else:
                                        logger.warning(f"Unexpected type for address field {field}: {type(value)}")
                        
                    # Always set address data in response
                    data['address'] = address_data
                    logger.info(f"Extracted address: {json.dumps(address_data, indent=2)}")
                    
                    # Ensure all required fields are present
                    data.setdefault('client_id', None)
                    data.setdefault('pan_number', None)
                    data.setdefault('full_name', None)
                    data.setdefault('full_name_split', [])
                    data.setdefault('masked_aadhaar', None)
                    data.setdefault('email', None)
                    data.setdefault('phone_number', None)
                    data.setdefault('gender', None)
                    data.setdefault('dob', None)
                    data.setdefault('input_dob', None)
                    data.setdefault('aadhaar_linked', False)
                    data.setdefault('dob_verified', False)
                    data.setdefault('dob_check', False)
                    data.setdefault('category', None)
                    data.setdefault('less_info', False)
                elif endpoint == ENDPOINTS["pan"]:
                    # For basic PAN verification, keep the data as is
                    logger.debug(f"Using processed basic PAN data: {json.dumps(data, indent=2)}")
                else:
                    # For other endpoints, ensure we have valid response structure
                    if not isinstance(data, dict):
                        data = {
                            'success': success,
                            'status_code': status_code,
                            'message': message or 'Request completed',
                            'raw_response': data
                        }
                    logger.debug(f"Processed response structure: {json.dumps(data, indent=2)}")
                
                logger.info(f"Final response data for endpoint {endpoint}: {json.dumps(data, indent=2)}")
                
                return KYCResponse(
                    success=success,
                    data=data,
                    status_code=status_code,
                    message=message,
                    message_code=message_code
                )
            else:
                error_data = response.text
                try:
                    error_json = response.json()
                    # Try multiple possible error message locations
                    error_message = (
                        error_json.get('message') or 
                        error_json.get('error') or 
                        (error_json.get('data', {}) or {}).get('message') or
                        (error_json.get('data', {}) or {}).get('error') or
                        error_data
                    )
                    # Include more details in debug log
                    logger.debug(f"Raw error response for endpoint {endpoint}: {json.dumps(error_json, indent=2)}")
                    
                    # Return full error response in data field for debugging
                    return KYCResponse(
                        success=False,
                        error=f"API Error: {error_message}",
                        status_code=response.status_code,
                        data=error_json  # Include full error response for debugging
                    )
                except:
                    error_message = error_data
                    logger.warning(f"Could not parse error response as JSON for endpoint {endpoint}: {error_data}")
                    return KYCResponse(
                        success=False,
                        error=f"API Error: {error_message}",
                        status_code=response.status_code
                    )
        except json.JSONDecodeError:
            return KYCResponse(
                success=False,
                error=f"Invalid JSON response: {response.text}",
                status_code=response.status_code
            )
    
    async def close(self):
        """Close the HTTP client"""
        await self.client.aclose()
