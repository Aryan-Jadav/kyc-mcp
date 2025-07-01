"""HTTP client for SurePass KYC API - Optimized for High Concurrency"""

import asyncio
import httpx
import logging
from typing import Dict, Any, Optional, Union
import json
from pathlib import Path
from contextlib import asynccontextmanager
import threading
from weakref import WeakSet

from config import BASE_URL, DEFAULT_HEADERS, MULTIPART_HEADERS, SUREPASS_API_TOKEN, ENDPOINTS
from models import KYCResponse, APIError

logger = logging.getLogger("kyc-mcp-server")

class ConnectionPool:
    """Manages HTTP client connection pool for high concurrency"""
    
    def __init__(self, max_clients: int = 50):
        self.max_clients = max_clients
        self.available_clients = None
        self.active_clients = WeakSet()
        self._lock = asyncio.Lock()
        self._initialized = False
        self.base_url = BASE_URL
    
    async def initialize(self):
        """Initialize the connection pool"""
        if self._initialized:
            return
            
        async with self._lock:
            if self._initialized:
                return
                
            self.available_clients = asyncio.Queue(maxsize=self.max_clients)
            
            # Pre-create HTTP clients with optimized settings
            for _ in range(self.max_clients):
                client = httpx.AsyncClient(
                    timeout=httpx.Timeout(
                        60.0,           # Total timeout
                        connect=15.0,   # Connection timeout
                        read=45.0,      # Read timeout
                        write=15.0,     # Write timeout
                        pool=15.0       # Pool timeout
                    ),
                    limits=httpx.Limits(
                        max_keepalive_connections=100,  # Increased for concurrency
                        max_connections=200,            # Much higher limit
                        keepalive_expiry=120.0          # Longer keepalive
                    ),
                    verify=True,
                    trust_env=True,
                    follow_redirects=True,
                    # Additional optimizations
                    http2=True  # Enable HTTP/2 for better performance
                )
                await self.available_clients.put(client)
            
            self._initialized = True
            logger.info(f"Connection pool initialized with {self.max_clients} clients")
    
    @asynccontextmanager
    async def get_client(self):
        """Get an HTTP client from the pool with fallback"""
        if not self._initialized:
            await self.initialize()
            
        client = None
        is_pool_client = False
        
        try:
            # Try to get client from pool with short timeout
            try:
                client = await asyncio.wait_for(
                    self.available_clients.get(), 
                    timeout=2.0
                )
                is_pool_client = True
                self.active_clients.add(client)
            except asyncio.TimeoutError:
                # Create temporary client if pool is exhausted
                logger.warning("Connection pool exhausted, creating temporary client")
                client = self._create_temp_client()
                is_pool_client = False
            
            yield client
            
        finally:
            # Return client to pool if it's a pool client and still valid
            if client and is_pool_client and not client.is_closed:
                try:
                    self.active_clients.discard(client)
                    await self.available_clients.put(client)
                except Exception as e:
                    logger.warning(f"Error returning client to pool: {e}")
                    await client.aclose()
            elif client and not is_pool_client:
                # Close temporary client
                await client.aclose()
    
    def _create_temp_client(self) -> httpx.AsyncClient:
        """Create a temporary client with reduced settings"""
        return httpx.AsyncClient(
            timeout=httpx.Timeout(30.0),
            limits=httpx.Limits(
                max_keepalive_connections=5,
                max_connections=10
            ),
            verify=True
        )
    
    async def close_all(self):
        """Close all clients in the pool"""
        if not self._initialized:
            return
            
        # Close clients in pool
        while not self.available_clients.empty():
            try:
                client = await self.available_clients.get()
                await client.aclose()
            except Exception as e:
                logger.warning(f"Error closing pool client: {e}")
        
        # Close any remaining active clients
        for client in list(self.active_clients):
            try:
                if not client.is_closed:
                    await client.aclose()
            except Exception as e:
                logger.warning(f"Error closing active client: {e}")
        
        logger.info("All HTTP clients closed")

# Global connection pool instance
_connection_pool = None
_pool_lock = threading.Lock()

def get_connection_pool() -> ConnectionPool:
    """Get the global connection pool instance"""
    global _connection_pool
    if _connection_pool is None:
        with _pool_lock:
            if _connection_pool is None:
                _connection_pool = ConnectionPool(max_clients=50)
    return _connection_pool

class KYCClient:
    """HTTP client for KYC API operations with high concurrency support"""
    
    def __init__(self, timeout: int = 60):
        self.base_url = BASE_URL
        self.timeout = timeout
        self.connection_pool = get_connection_pool()
        self._closed = False
    
    async def __aenter__(self):
        await self.connection_pool.initialize()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        self._closed = True
    
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
        """Make a POST request with JSON data using connection pool"""
        if self._closed:
            return KYCResponse(
                success=False, 
                error="Client is closed", 
                status_code=None
            )
            
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
        
        # Prepare request data based on endpoint
        request_data = self._prepare_request_data(endpoint, data)
        
        # Use connection pool for the request
        async with self.connection_pool.get_client() as client:
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    logger.debug(f"Making request to {url} (attempt {attempt + 1}/{max_retries})")
                    
                    response = await client.post(url, json=request_data, headers=headers)
                    
                    if response.status_code == 200:
                        return self._handle_response(response, endpoint)
                    elif response.status_code == 401:
                        error_msg = ("Authentication failed. Please check your API token and ensure it has "
                                   "the required permissions for this operation.")
                        return KYCResponse(success=False, error=error_msg, status_code=response.status_code)
                    elif response.status_code == 403:
                        error_msg = ("Access forbidden. Your API token may not have permission to access "
                                   "this endpoint.")
                        return KYCResponse(success=False, error=error_msg, status_code=response.status_code)
                    elif response.status_code >= 500 and attempt < max_retries - 1:
                        # Retry on server errors
                        logger.warning(f"Server error {response.status_code}, retrying in {attempt + 1} seconds...")
                        await asyncio.sleep(attempt + 1)
                        continue
                    else:
                        error_msg = f"API error: Status {response.status_code}, Response: {response.text}"
                        logger.error(error_msg)
                        return KYCResponse(success=False, error=error_msg, status_code=response.status_code)

                except httpx.RequestError as e:
                    error_msg = str(e)
                    logger.error(f"HTTP request failed: {error_msg}")

                    # Retry on network errors with exponential backoff
                    if attempt < max_retries - 1:
                        wait_time = min(2 ** attempt, 10)  # Exponential backoff, max 10 seconds
                        logger.warning(f"Network error, retrying in {wait_time} seconds... ({attempt + 1}/{max_retries})")
                        await asyncio.sleep(wait_time)
                        continue

                    # Provide descriptive error messages
                    if "All connection attempts failed" in error_msg:
                        error_msg = (
                            "Network connection failed. This could be due to:\n"
                            "1. Firewall blocking HTTPS connections to kyc-api.surepass.io\n"
                            "2. Corporate network restrictions\n"
                            "3. ISP blocking the connection\n"
                            "4. The API server may be temporarily unavailable\n"
                            f"Original error: {error_msg}"
                        )
                    elif "TimeoutError" in error_msg or "ConnectTimeout" in error_msg:
                        error_msg = (
                            "Connection timed out. The server took too long to respond.\n"
                            "This might indicate network connectivity issues or server overload.\n"
                            f"Original error: {error_msg}"
                        )

                    return KYCResponse(success=False, error=f"Network error after {max_retries} attempts: {error_msg}", status_code=None)
    
    def _prepare_request_data(self, endpoint: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Prepare request data based on endpoint"""
        if endpoint == ENDPOINTS["pan_comprehensive"]:
            # Format specifically for PAN comprehensive v2 endpoint
            return {
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
            return {"id_number": data["id_number"]}
        else:
            return data
    
    async def post_form(self, endpoint: str, files: Dict[str, Any],
                       data: Optional[Dict[str, str]] = None,
                       authorization_token: Optional[str] = None) -> KYCResponse:
        """Make a POST request with form data (file upload) using connection pool"""
        if self._closed:
            return KYCResponse(
                success=False, 
                error="Client is closed", 
                status_code=None
            )
            
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
            
            async with self.connection_pool.get_client() as client:
                logger.info(f"Making form request to {url}")
                response = await client.post(url, files=prepared_files, 
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
                
                return self._handle_response(response, endpoint)
                
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
        """Handle HTTP response - optimized for performance"""
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
                else:
                    # Some endpoints return data at root level
                    data = raw_data
                    # For basic PAN endpoint, make sure we have standard fields
                    if endpoint == ENDPOINTS["pan"]:
                        data.setdefault('success', success)
                        data.setdefault('status_code', status_code)
                        data.setdefault('message', message or 'Verification completed')

                # Handle PAN comprehensive endpoint address structure
                if isinstance(data, dict) and endpoint == ENDPOINTS["pan_comprehensive"]:
                    # Initialize address data with None values
                    address_data = {
                        'line_1': None, 'line_2': None, 'street_name': None,
                        'zip': None, 'city': None, 'state': None, 
                        'country': None, 'full': None
                    }

                    # Extract address from response if available
                    if 'address' in data and isinstance(data['address'], dict):
                        address_response = data['address']
                        for field in address_data.keys():
                            if field in address_response and address_response[field] is not None:
                                if isinstance(address_response[field], (str, int)):
                                    address_data[field] = str(address_response[field]).strip()
                    
                    # Always set address data in response
                    data['address'] = address_data
                    
                    # Ensure all required fields are present with defaults
                    defaults = {
                        'client_id': None, 'pan_number': None, 'full_name': None,
                        'full_name_split': [], 'masked_aadhaar': None, 'email': None,
                        'phone_number': None, 'gender': None, 'dob': None,
                        'input_dob': None, 'aadhaar_linked': False, 'dob_verified': False,
                        'dob_check': False, 'category': None, 'less_info': False
                    }
                    for key, default_value in defaults.items():
                        data.setdefault(key, default_value)
                
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
                    
                    # Return full error response in data field for debugging
                    return KYCResponse(
                        success=False,
                        error=f"API Error: {error_message}",
                        status_code=response.status_code,
                        data=error_json  # Include full error response for debugging
                    )
                except:
                    error_message = error_data
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
        self._closed = True

# Client factory for managing client lifecycle
class KYCClientFactory:
    """Factory for creating and managing KYC client instances"""
    
    def __init__(self):
        self.connection_pool = get_connection_pool()
    
    async def create_client(self) -> KYCClient:
        """Create a new KYC client instance"""
        client = KYCClient()
        await client.__aenter__()
        return client
    
    async def cleanup(self):
        """Cleanup all factory resources"""
        await self.connection_pool.close_all()

# Global factory instance
client_factory = KYCClientFactory()