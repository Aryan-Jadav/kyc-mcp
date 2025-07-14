#!/usr/bin/env python3
"""
Enhanced MCP Direct Client for KYC Verification with LangChain Support

This client provides Claude Desktop integration with:
1. Direct KYC verification tools (WORKING - unchanged)
2. LangChain-powered chat agent (WORKING - unchanged)  
3. NEW: Smart intelligent verification with auto-routing
4. Database search capabilities

Compatible with Claude Desktop MCP configuration.
"""

import json
import sys
import requests
import time
import logging
import re
from typing import Dict, Any, Optional, List
import os

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    stream=sys.stderr
)
logger = logging.getLogger("kyc-mcp-client")

class EnhancedKYCMCPServer:
    """Enhanced MCP Server with LangChain integration and smart verification"""
    
    def __init__(self):
        # Server endpoints - update these to match your server
        self.base_url = os.getenv("KYC_SERVER_URL", "http://139.59.70.153:8000")
        self.universal_endpoint = f"{self.base_url}/universal-verify"
        self.universal_file_endpoint = f"{self.base_url}/universal-verify-file"
        self.chat_endpoint = f"{self.base_url}/api/chat"
        self.verify_endpoint = f"{self.base_url}/api/chat/verify"
        self.capabilities_endpoint = f"{self.base_url}/api/chat/capabilities"
        self.health_endpoint = f"{self.base_url}/health"
        
        # OCR endpoints
        self.ocr_endpoints = {
            "ocr_pan": f"{self.base_url}/api/ocr/pan",
            "ocr_aadhaar": f"{self.base_url}/api/ocr/aadhaar",
            "ocr_passport": f"{self.base_url}/api/ocr/passport",
            "ocr_license": f"{self.base_url}/api/ocr/license",
            "ocr_voter": f"{self.base_url}/api/ocr/voter",
            "ocr_gst": f"{self.base_url}/api/ocr/gst",
            "ocr_itr": f"{self.base_url}/api/ocr/itr",
            "ocr_cheque": f"{self.base_url}/api/ocr/cheque",
            "ocr_document_detect": f"{self.base_url}/api/ocr/document-detect"
        }
        
        # Session management
        self.session_id = None
        
        # NEW: Add smart document patterns for the enhanced intelligent_verify
        self.document_patterns = {
            'pan': r'\b[A-Z]{5}[0-9]{4}[A-Z]\b',
            'aadhaar': r'\b\d{4}\s?\d{4}\s?\d{4}\b|\b\d{12}\b',
            'gstin': r'\b\d{2}[A-Z]{5}\d{4}[A-Z]\d[Z][A-Z\d]\b',
            'ifsc': r'\b[A-Z]{4}0[A-Z0-9]{6}\b',
            'mobile': r'\b[6-9]\d{9}\b',
            'email': r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
            'upi': r'\b[\w\.-]+@[\w\.-]+\b'
        }
        
        # NEW: Smart routing for common document types
        self.smart_routing = {
            'pan': {
                'comprehensive': 'pan_comprehensive',
                'detailed': 'pan_comprehensive', 
                'kra': 'pan_kra',
                'advanced': 'pan_adv',
                'basic': 'pan',
                'default': 'pan_comprehensive'
            },
            'aadhaar': {
                'otp': 'aadhaar_generate_otp',
                'generate': 'aadhaar_generate_otp',
                'validate': 'aadhaar_validation',
                'default': 'aadhaar_validation'
            },
            'gstin': {
                'advanced': 'gstin_advanced',
                'detailed': 'gstin_advanced',
                'default': 'gstin'
            },
            'mobile': {
                'upi': 'find_upi_id',
                'bank': 'mobile_to_bank',
                'telecom': 'telecom_verification',
                'default': 'telecom_verification'
            }
        }
        
        logger.info(f"Initialized KYC MCP Server client for: {self.base_url}")
        
        # Test connectivity on startup
        self._test_connectivity()
    
    def _test_connectivity(self):
        """Test server connectivity and features"""
        try:
            response = requests.get(self.health_endpoint, timeout=5)
            if response.status_code == 200:
                health_data = response.json()
                logger.info(f"✅ Server connectivity confirmed")
                logger.info(f"   LangChain available: {health_data.get('langchain_available', False)}")
                logger.info(f"   OpenAI configured: {health_data.get('openai_configured', False)}")
            else:
                logger.warning(f"⚠️ Server responded with status {response.status_code}")
        except Exception as e:
            logger.warning(f"⚠️ Server connectivity test failed: {str(e)}")
            logger.info("   Continuing anyway - server might be starting up")
    
    # NEW: Smart verification method
    def smart_verify(self, message: str) -> str:
        """Smart verification with document auto-detection and routing"""
        try:
            logger.info(f"🧠 Smart verify request: {message}")
            
            # Handle help
            if any(word in message.lower() for word in ['help', 'what can', 'services']):
                return """🧠 **Smart KYC Verification**

I can automatically detect document types and route to the best verification service:

📄 **Document Verification:**
• **PAN**: "Verify PAN ABCDE1234F" (auto-routes to comprehensive)
• **Aadhaar**: "Generate OTP for Aadhaar 123456789012" 
• **GSTIN**: "Check GSTIN 29ABCDE1234F1Z5"
• **Mobile**: "Find UPI for mobile 9876543210"

📄 **OCR Operations:**
✅ **File Path Support**: "OCR PAN card from /path/to/pan.jpg"
✅ **Direct File Upload**: Just attach/upload your document to Claude Desktop!
• **PAN OCR**: "OCR this PAN card" (with attached image)
• **Passport OCR**: "Extract data from passport" (with attached PDF)
• **License OCR**: "Process driving license" (with attached image)
• **Document Detection**: "Detect document type" (with attached file)

💡 **Examples:**
• "Verify PAN ABCDE1234F comprehensive"
• "OCR this PAN card /Users/john/documents/pan_card.jpg"
• "Extract passport data" (attach passport PDF/image)
• "Process Aadhaar card OCR" (attach Aadhaar image)

🚀 **New Feature**: You can now drag & drop files directly into Claude Desktop for instant OCR processing! No need to provide file paths anymore."""
            
            # Check for OCR operations
            message_lower = message.lower()
            
            # Handle OCR requests
            if any(ocr_word in message_lower for ocr_word in ['ocr', 'extract', 'process', 'scan']):
                return self._handle_ocr_request(message, message_lower)
            
            # Handle regular verification (existing logic)
            extracted = self._extract_documents(message)
            
            if not extracted:
                return """❌ **No documents detected**

Please include either:
📋 **Document number** like: PAN: ABCDE1234F, GSTIN: 29ABCDE1234F1Z5, Aadhaar: 123456789012
📁 **File path for OCR** like: "OCR PAN card /path/to/file.jpg"

💡 **Examples:**
• "Verify PAN ABCDE1234F"
• "OCR passport /Users/john/passport.pdf"
• "Extract data from /path/to/document.jpg"
"""
            
            # Route to appropriate tool
            routing = self._smart_route(extracted, message.lower())
            
            if 'error' in routing:
                return f"❌ **Error**: {routing['error']}"
            
            # Make the API call
            result = self.call_universal_verify(routing['tool'], routing['params'])
            
            # Format response
            return self._format_smart_response(result, routing['tool'])
            
        except Exception as e:
            logger.error(f"Smart verify error: {str(e)}")
            return f"❌ **Error**: {str(e)}"
    
    def _handle_ocr_request(self, message: str, message_lower: str) -> str:
        """Handle OCR-specific requests"""
        import re
        
        # Extract file path - look for common path patterns
        file_patterns = [
            r'["\']([^"\']+\.[a-zA-Z]{3,4})["\']',  # "path/file.ext" or 'path/file.ext'
            r'(/[^\s]+\.[a-zA-Z]{3,4})',            # /unix/path/file.ext
            r'([A-Z]:[^\s]+\.[a-zA-Z]{3,4})',       # C:\windows\path\file.ext
            r'([~/][^\s]+\.[a-zA-Z]{3,4})',         # ~/path/file.ext
        ]
        
        file_path = None
        for pattern in file_patterns:
            match = re.search(pattern, message)
            if match:
                file_path = match.group(1)
                break
        
        if not file_path:
            return """❌ **No file path found**

You can process documents in two ways:

🔗 **File Path (Traditional):**
• "OCR PAN card '/Users/john/documents/pan.jpg'"
• "Extract passport data from C:\\docs\\passport.pdf"
• "Process document ~/Downloads/license.png"

📎 **Direct Upload (New!):**
• Just attach/upload your document to Claude Desktop and say:
• "OCR this PAN card"
• "Extract passport data"
• "Process this document"

🔍 **Supported formats**: JPG, PNG, PDF, TIFF, BMP, GIF"""
        
        # Determine OCR tool based on document type mentioned
        ocr_tool = None
        if any(word in message_lower for word in ['pan', 'pan card']):
            ocr_tool = 'ocr_pan'
        elif any(word in message_lower for word in ['aadhaar', 'aadhar']):
            ocr_tool = 'ocr_aadhaar'
        elif any(word in message_lower for word in ['passport']):
            ocr_tool = 'ocr_passport'
        elif any(word in message_lower for word in ['license', 'licence', 'driving']):
            ocr_tool = 'ocr_license'
        elif any(word in message_lower for word in ['voter', 'voter id']):
            ocr_tool = 'ocr_voter'
        elif any(word in message_lower for word in ['gst', 'gstin']):
            ocr_tool = 'ocr_gst'
        elif any(word in message_lower for word in ['itr', 'income tax']):
            ocr_tool = 'ocr_itr'
        elif any(word in message_lower for word in ['cheque', 'check']):
            ocr_tool = 'ocr_cheque'
        elif any(word in message_lower for word in ['detect', 'identify', 'unknown']):
            ocr_tool = 'ocr_document_detect'
        else:
            # Default to document detection if type is unclear
            ocr_tool = 'ocr_document_detect'
        
        # Make OCR request
        result = self.call_ocr_tool(ocr_tool, file_path)
        
        # Format response
        try:
            result_data = json.loads(result)
            if result_data.get('success'):
                data = result_data.get('data', {})
                file_info = result_data.get('file_info', {})
                
                response = f"✅ **OCR Processing Successful**\n\n🎯 **Tool Used**: {ocr_tool}\n📁 **File**: {file_info.get('filename', file_path)}\n\n📋 **Extracted Data**:\n"
                
                # Show key extracted fields
                if data:
                    for key, value in data.items():
                        if value and key not in ['storage_info', 'raw_data']:
                            response += f"   • **{key.replace('_', ' ').title()}**: {value}\n"
                
                return response
            else:
                error = result_data.get('error', 'Unknown error')
                return f"❌ **OCR Processing Failed**\n\n🎯 **Tool Used**: {ocr_tool}\n📁 **File**: {file_path}\n📋 **Error**: {error}"
                
        except Exception as e:
            return f"❌ **OCR Response Error**: {str(e)}"
    
    def _extract_documents(self, text: str) -> Dict[str, str]:
        """Extract document numbers from text"""
        extracted = {}
        text_upper = text.upper()
        
        for doc_type, pattern in self.document_patterns.items():
            matches = re.findall(pattern, text_upper)
            if matches:
                extracted[doc_type] = matches[0]
        
        return extracted
    
    def _smart_route(self, documents: Dict[str, str], message_lower: str) -> Dict[str, Any]:
        """Smart routing logic"""
        # PAN routing
        if 'pan' in documents:
            pan_number = documents['pan']
            routing_options = self.smart_routing['pan']
            
            # Check for specific keywords
            for keyword, tool in routing_options.items():
                if keyword != 'default' and keyword in message_lower:
                    return {'tool': tool, 'params': {'id_number': pan_number}}
            
            # Default to comprehensive
            return {'tool': routing_options['default'], 'params': {'id_number': pan_number}}
        
        # Aadhaar routing
        elif 'aadhaar' in documents:
            aadhaar_number = documents['aadhaar']
            routing_options = self.smart_routing['aadhaar']
            
            for keyword, tool in routing_options.items():
                if keyword != 'default' and keyword in message_lower:
                    return {'tool': tool, 'params': {'id_number': aadhaar_number}}
            
            return {'tool': routing_options['default'], 'params': {'id_number': aadhaar_number}}
        
        # GSTIN routing
        elif 'gstin' in documents:
            gstin_number = documents['gstin']
            routing_options = self.smart_routing['gstin']
            
            for keyword, tool in routing_options.items():
                if keyword != 'default' and keyword in message_lower:
                    return {'tool': tool, 'params': {'id_number': gstin_number}}
            
            return {'tool': routing_options['default'], 'params': {'id_number': gstin_number}}
        
        # Mobile routing
        elif 'mobile' in documents:
            mobile_number = documents['mobile']
            routing_options = self.smart_routing['mobile']
            
            for keyword, tool in routing_options.items():
                if keyword != 'default' and keyword in message_lower:
                    if tool == 'find_upi_id':
                        return {'tool': tool, 'params': {'mobile_number': mobile_number}}
                    elif tool == 'mobile_to_bank':
                        return {'tool': tool, 'params': {'mobile_no': mobile_number}}
                    else:
                        return {'tool': tool, 'params': {'id_number': mobile_number}}
            
            return {'tool': routing_options['default'], 'params': {'id_number': mobile_number}}
        
        # Bank verification (needs both account and IFSC)
        elif 'ifsc' in documents:
            ifsc_code = documents['ifsc']
            # Look for account number
            account_match = re.search(r'\b\d{9,18}\b', message_lower)
            if account_match:
                account_number = account_match.group()
                return {'tool': 'bank_verification', 'params': {'id_number': account_number, 'ifsc': ifsc_code}}
            else:
                return {'error': 'Bank verification needs both account number and IFSC code'}
        
        else:
            return {'error': 'Document type not supported yet'}
    
    def _format_smart_response(self, result_json: str, tool_used: str) -> str:
        """Format the response nicely"""
        try:
            result = json.loads(result_json)
            
            if result.get('success'):
                data = result.get('data', {})
                response = f"✅ **Smart Verification Successful**\n\n🎯 **Tool Used**: {tool_used}\n\n📋 **Results**:\n"
                
                # Show key fields
                key_fields = ['pan_number', 'full_name', 'gstin', 'business_name', 'name', 'status']
                for field in key_fields:
                    if field in data and data[field]:
                        response += f"   • **{field.replace('_', ' ').title()}**: {data[field]}\n"
                
                return response
            else:
                error = result.get('error', 'Unknown error')
                return f"❌ **Verification Failed**\n\n🎯 **Tool Used**: {tool_used}\n📋 **Error**: {error}"
                
        except Exception as e:
            return f"❌ **Response Format Error**: {str(e)}"
    
    # EXISTING METHODS - UNCHANGED
    def call_universal_verify(self, tool: str, params: Dict[str, Any]) -> str:
        """Send request to universal verify endpoint"""
        payload = {"tool": tool, "params": params}
        
        try:
            logger.info(f"🔍 Universal verify: {tool} with params: {params}")
            response = requests.post(
                self.universal_endpoint,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                logger.info(f"✅ Universal verify successful for {tool}")
                return json.dumps(result, indent=2)
            else:
                error_msg = f"Universal verify failed with status {response.status_code}: {response.text}"
                logger.error(f"❌ {error_msg}")
                return json.dumps({
                    "success": False,
                    "error": error_msg,
                    "tool": tool,
                    "params": params
                })
                
        except requests.exceptions.Timeout:
            error_msg = f"Universal verify request timed out for tool: {tool}"
            logger.error(f"❌ {error_msg}")
            return json.dumps({"success": False, "error": error_msg})
        except Exception as e:
            error_msg = f"Universal verify error for {tool}: {str(e)}"
            logger.error(f"❌ {error_msg}")
            return json.dumps({"success": False, "error": error_msg})
    
    def call_chat_agent(self, message: str, session_id: Optional[str] = None, clear_history: bool = False) -> str:
        """Send request to chat agent endpoint"""
        payload = {
            "message": message,
            "session_id": session_id or self.session_id,
            "clear_history": clear_history
        }
        
        try:
            logger.info(f"💬 Chat agent request: {message[:50]}...")
            response = requests.post(
                self.chat_endpoint,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=45  # Longer timeout for LLM responses
            )
            
            if response.status_code == 200:
                result = response.json()
                if result.get("success"):
                    logger.info("✅ Chat agent responded successfully")
                    # Update session ID if provided
                    if result.get("session_id"):
                        self.session_id = result["session_id"]
                    return result.get("response", "No response received")
                else:
                    error_msg = result.get("error", "Chat agent returned unsuccessful response")
                    logger.error(f"❌ Chat agent error: {error_msg}")
                    return f"Chat Error: {error_msg}"
            else:
                error_msg = f"Chat request failed with status {response.status_code}: {response.text}"
                logger.error(f"❌ {error_msg}")
                return f"Chat Request Failed: {error_msg}"
                
        except requests.exceptions.Timeout:
            error_msg = "Chat request timed out - the AI might be processing a complex query"
            logger.error(f"❌ {error_msg}")
            return error_msg
        except Exception as e:
            error_msg = f"Chat error: {str(e)}"
            logger.error(f"❌ {error_msg}")
            return error_msg
    
    def call_intelligent_verify(self, message: str) -> str:
        """NEW: Enhanced intelligent verify using smart routing"""
        return self.smart_verify(message)
    
    def call_ocr_tool(self, tool_name: str, file_path: Optional[str] = None, file_content: Optional[str] = None, file_name: Optional[str] = None, use_pdf: str = "true", authorization_token: Optional[str] = None) -> str:
        """Call OCR tool with file upload - supports both file path and file content"""
        try:
            import os
            import tempfile
            import base64
            
            # Validate tool name
            if tool_name not in self.ocr_endpoints:
                available_tools = list(self.ocr_endpoints.keys())
                return json.dumps({
                    "success": False,
                    "error": f"OCR tool '{tool_name}' not supported",
                    "available_tools": available_tools
                })
            
            # Handle file content (from Claude Desktop attachment) - DIRECT BASE64 APPROACH
            try:
                if file_content:
                    logger.info(f"📄 OCR request: {tool_name} for attached file: {file_name or 'unknown'}")
                    logger.info(f"📄 Using direct base64 approach - no temporary files!")
                    
                    # Clean base64 content if it's a data URL
                    clean_base64 = file_content
                    if file_content.startswith('data:'):
                        logger.info("📄 Detected data URL format, extracting base64 part")
                        clean_base64 = file_content.split(',')[1]
                    
                    logger.info(f"📄 Base64 content length: {len(clean_base64)}")
                    
                    # Prepare form data with base64 content - NO FILE UPLOAD
                    files = None  # No file upload needed
                    data = {
                        'file_content_base64': clean_base64,
                        'file_name': file_name or 'unknown'
                    }
                    
                    # Add additional parameters for specific tools
                    if tool_name == "ocr_itr":
                        data['use_pdf'] = use_pdf
                    if authorization_token:
                        data['authorization_token'] = authorization_token
                    
                    logger.info(f"📄 Sending base64 directly to server (no file conversion!)")
                    
                    # Make request to OCR endpoint with base64 data
                    response = requests.post(
                        self.ocr_endpoints[tool_name],
                        data=data,  # Send as form data, not files
                        timeout=60
                    )
                    
                    if response.status_code == 200:
                        result = response.json()
                        logger.info(f"✅ OCR successful for {tool_name} (base64 direct)")
                        return json.dumps(result, indent=2)
                    else:
                        error_msg = f"OCR request failed with status {response.status_code}: {response.text}"
                        logger.error(f"❌ {error_msg}")
                        return json.dumps({
                            "success": False,
                            "error": error_msg,
                            "tool": tool_name,
                            "file_name": file_name or "unknown"
                        })
                    
                # Handle file path (original behavior with file upload)
                elif file_path:
                    if not os.path.exists(file_path):
                        return json.dumps({
                            "success": False,
                            "error": f"File not found: {file_path}"
                        })
                    
                    logger.info(f"📄 OCR request: {tool_name} for file: {file_path}")
                    
                    # Prepare file for upload
                    files = {'file': open(file_path, 'rb')}
                    data = {}
                    
                    # Add additional parameters for specific tools
                    if tool_name == "ocr_itr":
                        data['use_pdf'] = use_pdf
                    if authorization_token:
                        data['authorization_token'] = authorization_token
                    
                    # Make request to OCR endpoint
                    response = requests.post(
                        self.ocr_endpoints[tool_name],
                        files=files,
                        data=data,
                        timeout=60  # Longer timeout for file processing
                    )
                    
                    # Close file handle
                    files['file'].close()
                    
                    if response.status_code == 200:
                        result = response.json()
                        logger.info(f"✅ OCR successful for {tool_name} (file upload)")
                        return json.dumps(result, indent=2)
                    else:
                        error_msg = f"OCR request failed with status {response.status_code}: {response.text}"
                        logger.error(f"❌ {error_msg}")
                        return json.dumps({
                            "success": False,
                            "error": error_msg,
                            "tool": tool_name,
                            "file_path": file_path
                        })
                    
                else:
                    return json.dumps({
                        "success": False,
                        "error": "Either file_path or file_content must be provided"
                    })
                        
            except Exception as e:
                error_msg = f"OCR error for {tool_name}: {str(e)}"
                logger.error(f"❌ {error_msg}")
                return json.dumps({
                    "success": False,
                    "error": error_msg,
                    "tool": tool_name,
                    "file_path": file_path or file_name or "unknown"
                })
        except Exception as e:
            error_msg = f"OCR tool error: {str(e)}"
            logger.error(f"❌ {error_msg}")
            return json.dumps({
                "success": False,
                "error": error_msg,
                "tool": tool_name
            })
    
    def call_universal_file_verify(self, tool: str, file_path: Optional[str] = None, file_content: Optional[str] = None, file_name: Optional[str] = None, use_pdf: str = "true", authorization_token: Optional[str] = None) -> str:
        """Call universal file verify endpoint for OCR tools - supports both file path and file content"""
        try:
            import os
            import tempfile
            import base64
            
            temp_file_path = None
            
            try:
                # Handle file content (from Claude Desktop attachment) - DIRECT BASE64 APPROACH
                if file_content:
                    logger.info(f"📄 Universal file verify: {tool} for attached file: {file_name or 'unknown'}")
                    logger.info(f"📄 Using direct base64 approach - no temporary files!")
                    
                    # Clean base64 content if it's a data URL
                    clean_base64 = file_content
                    if file_content.startswith('data:'):
                        logger.info("📄 Detected data URL format, extracting base64 part")
                        clean_base64 = file_content.split(',')[1]
                    
                    logger.info(f"📄 Base64 content length: {len(clean_base64)}")
                    
                    # Prepare form data with base64 content - NO FILE UPLOAD
                    files = None  # No file upload needed
                    data = {
                        'tool': tool,
                        'file_content_base64': clean_base64,
                        'file_name': file_name or 'unknown',
                        'use_pdf': use_pdf
                    }
                    
                    if authorization_token:
                        data['authorization_token'] = authorization_token
                    
                    logger.info(f"📄 Sending base64 directly to universal endpoint (no file conversion!)")
                    
                    # Make request to universal endpoint with base64 data
                    response = requests.post(
                        self.universal_file_endpoint,
                        data=data,  # Send as form data, not files
                        timeout=60
                    )
                    
                    if response.status_code == 200:
                        result = response.json()
                        logger.info(f"✅ Universal file verify successful for {tool} (base64 direct)")
                        return json.dumps(result, indent=2)
                    else:
                        error_msg = f"Universal file verify failed with status {response.status_code}: {response.text}"
                        logger.error(f"❌ {error_msg}")
                        return json.dumps({
                            "success": False,
                            "error": error_msg,
                            "tool": tool,
                            "file_name": file_name or "unknown"
                        })
                    
                # Handle file path (original behavior with file upload)
                elif file_path:
                    if not os.path.exists(file_path):
                        return json.dumps({
                            "success": False,
                            "error": f"File not found: {file_path}"
                        })
                    
                    logger.info(f"📄 Universal file verify: {tool} for file: {file_path}")
                    
                    # Prepare file and data for upload
                    files = {'file': open(file_path, 'rb')}
                    data = {
                        'tool': tool,
                        'use_pdf': use_pdf
                    }
                    
                    if authorization_token:
                        data['authorization_token'] = authorization_token
                    
                    # Make request
                    response = requests.post(
                        self.universal_file_endpoint,
                        files=files,
                        data=data,
                        timeout=60
                    )
                    
                    # Close file handle
                    files['file'].close()
                    
                    if response.status_code == 200:
                        result = response.json()
                        logger.info(f"✅ Universal file verify successful for {tool} (file upload)")
                        return json.dumps(result, indent=2)
                    else:
                        error_msg = f"Universal file verify failed with status {response.status_code}: {response.text}"
                        logger.error(f"❌ {error_msg}")
                        return json.dumps({
                            "success": False,
                            "error": error_msg,
                            "tool": tool,
                            "file_path": file_path
                        })
                    
                else:
                    return json.dumps({
                        "success": False,
                        "error": "Either file_path or file_content must be provided"
                    })
                    
            finally:
                # Clean up temporary file if created
                if temp_file_path and os.path.exists(temp_file_path):
                    try:
                        os.unlink(temp_file_path)
                        logger.info(f"🗑️ Cleaned up temporary file: {temp_file_path}")
                    except Exception as e:
                        logger.warning(f"⚠️ Failed to clean up temporary file: {e}")
                        
        except Exception as e:
            error_msg = f"Universal file verify error for {tool}: {str(e)}"
            logger.error(f"❌ {error_msg}")
            return json.dumps({
                "success": False,
                "error": error_msg,
                "tool": tool,
                "file_path": file_path or file_name or "unknown"
            })
    
    def get_capabilities(self) -> str:
        """Get chat capabilities information"""
        try:
            logger.info("📋 Fetching capabilities...")
            response = requests.get(
                self.capabilities_endpoint,
                timeout=10
            )
            
            if response.status_code == 200:
                result = response.json()
                logger.info("✅ Capabilities retrieved successfully")
                return json.dumps(result, indent=2)
            else:
                error_msg = f"Capabilities request failed with status {response.status_code}"
                logger.error(f"❌ {error_msg}")
                return json.dumps({"error": error_msg})
                
        except Exception as e:
            error_msg = f"Capabilities error: {str(e)}"
            logger.error(f"❌ {error_msg}")
            return json.dumps({"error": error_msg})

    def handle_request(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Handle MCP request - FIXED to work properly with Claude Desktop"""
        method = request.get("method")
        req_id = request.get("id", 1)

        logger.info(f"🔄 Handling MCP request: {method}")

        if method == "initialize":
            logger.info("🚀 Initializing MCP server...")
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "serverInfo": {
                        "name": "enhanced-kyc-mcp", 
                        "version": "2.1.0",
                        "description": "Enhanced KYC MCP Server with LangChain integration and smart verification routing"
                    }
                }
            }

        elif method == "tools/list":
            logger.info("📝 Listing available tools...")
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "tools": [
                        {
                            "name": "universal_verify",
                            "description": "Direct KYC verification for specific document types (PAN, GSTIN, Bank, etc.)",
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "tool": {
                                        "type": "string", 
                                        "description": "Verification type",
                                        "enum": [
                                            "pan", "pan_comprehensive", "pan_kra", "pan_adv", "pan_adv_v2",
                                            "gstin", "gstin_advanced", "bank_verification", "upi_verification",
                                            "aadhaar_generate_otp", "aadhaar_validation", "voter_id",
                                            "driving_license", "passport", "tan", "itr_compliance",
                                            "find_upi_id", "upi_mobile_name", "mobile_to_bank", "telecom_verification"
                                        ]
                                    },
                                    "params": {
                                        "type": "object", 
                                        "description": "Parameters specific to the verification type",
                                        "properties": {
                                            "id_number": {"type": "string", "description": "Document number to verify"},
                                            "ifsc": {"type": "string", "description": "IFSC code for bank verification"},
                                            "dob": {"type": "string", "description": "Date of birth (YYYY-MM-DD)"},
                                            "mobile_number": {"type": "string", "description": "Mobile number"},
                                            "mobile_no": {"type": "string", "description": "Mobile number (alternate)"}
                                        }
                                    }
                                },
                                "required": ["tool", "params"]
                            }
                        },
                        {
                            "name": "chat_agent",
                            "description": "Natural language KYC assistant with conversation memory and intelligent responses",
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "message": {
                                        "type": "string", 
                                        "description": "Natural language message or question about KYC services"
                                    },
                                    "session_id": {
                                        "type": "string", 
                                        "description": "Optional session ID for conversation continuity"
                                    },
                                    "clear_history": {
                                        "type": "boolean",
                                        "description": "Clear conversation history before processing"
                                    }
                                },
                                "required": ["message"]
                            }
                        },
                        {
                            "name": "intelligent_verify",
                            "description": "🧠 SMART VERIFICATION - Auto-detects document types and intelligently routes to the best verification service. Just describe what you want to verify!",
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "message": {
                                        "type": "string", 
                                        "description": "Natural language verification request (e.g., 'Verify PAN ABCDE1234F', 'Check GSTIN 29ABCDE1234F1Z5 advanced', 'Generate OTP for Aadhaar 123456789012')"
                                    }
                                },
                                "required": ["message"]
                            }
                        },
                        {
                            "name": "get_capabilities",
                            "description": "Get information about available KYC services and chat capabilities",
                            "inputSchema": {
                                "type": "object",
                                "properties": {},
                                "additionalProperties": False
                            }
                        },
                        {
                            "name": "ocr_pan",
                            "description": "Extract data from PAN card image/document using OCR",
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "file_path": {
                                        "type": "string", 
                                        "description": "Full path to the PAN card image file (JPG, PNG, PDF)"
                                    },
                                    "file_content": {
                                        "type": "string",
                                        "description": "Base64 encoded file content (alternative to file_path)"
                                    },
                                    "file_name": {
                                        "type": "string",
                                        "description": "Original filename when using file_content"
                                    },
                                    "authorization_token": {
                                        "type": "string",
                                        "description": "Optional authorization token"
                                    }
                                },
                                "required": []
                            }
                        },
                        {
                            "name": "ocr_aadhaar",
                            "description": "Extract data from Aadhaar card image/document using OCR",
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "file_path": {
                                        "type": "string", 
                                        "description": "Full path to the Aadhaar card image file (JPG, PNG, PDF)"
                                    },
                                    "file_content": {
                                        "type": "string",
                                        "description": "Base64 encoded file content (alternative to file_path)"
                                    },
                                    "file_name": {
                                        "type": "string",
                                        "description": "Original filename when using file_content"
                                    },
                                    "authorization_token": {
                                        "type": "string",
                                        "description": "Optional authorization token"
                                    }
                                },
                                "required": []
                            }
                        },
                        {
                            "name": "ocr_passport",
                            "description": "Extract data from Passport document using OCR",
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "file_path": {
                                        "type": "string", 
                                        "description": "Full path to the passport image file (JPG, PNG, PDF)"
                                    },
                                    "file_content": {
                                        "type": "string",
                                        "description": "Base64 encoded file content (alternative to file_path)"
                                    },
                                    "file_name": {
                                        "type": "string",
                                        "description": "Original filename when using file_content"
                                    },
                                    "authorization_token": {
                                        "type": "string",
                                        "description": "Optional authorization token"
                                    }
                                },
                                "required": []
                            }
                        },
                        {
                            "name": "ocr_license",
                            "description": "Extract data from Driving License document using OCR",
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "file_path": {
                                        "type": "string", 
                                        "description": "Full path to the driving license image file (JPG, PNG, PDF)"
                                    },
                                    "file_content": {
                                        "type": "string",
                                        "description": "Base64 encoded file content (alternative to file_path)"
                                    },
                                    "file_name": {
                                        "type": "string",
                                        "description": "Original filename when using file_content"
                                    },
                                    "authorization_token": {
                                        "type": "string",
                                        "description": "Optional authorization token"
                                    }
                                },
                                "required": []
                            }
                        },
                        {
                            "name": "ocr_voter",
                            "description": "Extract data from Voter ID document using OCR",
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "file_path": {
                                        "type": "string", 
                                        "description": "Full path to the voter ID image file (JPG, PNG, PDF)"
                                    },
                                    "file_content": {
                                        "type": "string",
                                        "description": "Base64 encoded file content (alternative to file_path)"
                                    },
                                    "file_name": {
                                        "type": "string",
                                        "description": "Original filename when using file_content"
                                    },
                                    "authorization_token": {
                                        "type": "string",
                                        "description": "Optional authorization token"
                                    }
                                },
                                "required": []
                            }
                        },
                        {
                            "name": "ocr_gst",
                            "description": "Extract data from GST document using OCR",
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "file_path": {
                                        "type": "string", 
                                        "description": "Full path to the GST document image file (JPG, PNG, PDF)"
                                    },
                                    "file_content": {
                                        "type": "string",
                                        "description": "Base64 encoded file content (alternative to file_path)"
                                    },
                                    "file_name": {
                                        "type": "string",
                                        "description": "Original filename when using file_content"
                                    },
                                    "authorization_token": {
                                        "type": "string",
                                        "description": "Optional authorization token"
                                    }
                                },
                                "required": []
                            }
                        },
                        {
                            "name": "ocr_itr",
                            "description": "Extract data from ITR document using OCR",
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "file_path": {
                                        "type": "string", 
                                        "description": "Full path to the ITR document file (JPG, PNG, PDF)"
                                    },
                                    "file_content": {
                                        "type": "string",
                                        "description": "Base64 encoded file content (alternative to file_path)"
                                    },
                                    "file_name": {
                                        "type": "string",
                                        "description": "Original filename when using file_content"
                                    },
                                    "use_pdf": {
                                        "type": "string",
                                        "description": "Whether to use PDF processing (default: 'true')"
                                    },
                                    "authorization_token": {
                                        "type": "string",
                                        "description": "Optional authorization token"
                                    }
                                },
                                "required": []
                            }
                        },
                        {
                            "name": "ocr_cheque",
                            "description": "Extract data from Cheque document using OCR",
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "file_path": {
                                        "type": "string", 
                                        "description": "Full path to the cheque image file (JPG, PNG, PDF)"
                                    },
                                    "file_content": {
                                        "type": "string",
                                        "description": "Base64 encoded file content (alternative to file_path)"
                                    },
                                    "file_name": {
                                        "type": "string",
                                        "description": "Original filename when using file_content"
                                    },
                                    "authorization_token": {
                                        "type": "string",
                                        "description": "Optional authorization token"
                                    }
                                },
                                "required": []
                            }
                        },
                        {
                            "name": "ocr_document_detect",
                            "description": "Detect document type using OCR analysis",
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "file_path": {
                                        "type": "string", 
                                        "description": "Full path to the document image file (JPG, PNG, PDF)"
                                    },
                                    "file_content": {
                                        "type": "string",
                                        "description": "Base64 encoded file content (alternative to file_path)"
                                    },
                                    "file_name": {
                                        "type": "string",
                                        "description": "Original filename when using file_content"
                                    },
                                    "authorization_token": {
                                        "type": "string",
                                        "description": "Optional authorization token"
                                    }
                                },
                                "required": []
                            }
                        },
                        {
                            "name": "universal_file_verify",
                            "description": "Universal file verification endpoint for OCR and file-based tools",
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "tool": {
                                        "type": "string", 
                                        "description": "OCR tool name",
                                        "enum": [
                                            "ocr_pan", "ocr_aadhaar", "ocr_passport", "ocr_license",
                                            "ocr_voter", "ocr_gst", "ocr_itr", "ocr_cheque", "ocr_document_detect"
                                        ]
                                    },
                                    "file_path": {
                                        "type": "string", 
                                        "description": "Full path to the document file"
                                    },
                                    "file_content": {
                                        "type": "string",
                                        "description": "Base64 encoded file content (alternative to file_path)"
                                    },
                                    "file_name": {
                                        "type": "string",
                                        "description": "Original filename when using file_content"
                                    },
                                    "use_pdf": {
                                        "type": "string",
                                        "description": "Whether to use PDF processing (default: 'true')"
                                    },
                                    "authorization_token": {
                                        "type": "string",
                                        "description": "Optional authorization token"
                                    }
                                },
                                "required": ["tool"]
                            }
                        }
                    ]
                }
            }

        elif method == "tools/call":
            try:
                tool_name = request["params"]["name"]
                args = request["params"]["arguments"]
                
                logger.info(f"🛠️ Calling tool: {tool_name}")
                
                if tool_name == "universal_verify":
                    tool = args.get("tool")
                    params = args.get("params", {})
                    
                    if not tool:
                        raise ValueError("Tool parameter is required for universal_verify")
                    
                    result = self.call_universal_verify(tool, params)
                    
                elif tool_name == "chat_agent":
                    message = args.get("message")
                    session_id = args.get("session_id")
                    clear_history = args.get("clear_history", False)
                    
                    if not message:
                        raise ValueError("Message parameter is required for chat_agent")
                    
                    result = self.call_chat_agent(message, session_id, clear_history)
                    
                elif tool_name == "intelligent_verify":
                    message = args.get("message")
                    
                    if not message:
                        raise ValueError("Message parameter is required for intelligent_verify")
                    
                    result = self.call_intelligent_verify(message)
                    
                elif tool_name == "get_capabilities":
                    result = self.get_capabilities()
                    
                elif tool_name == "ocr_pan":
                    file_path = args.get("file_path")
                    file_content = args.get("file_content")
                    file_name = args.get("file_name")
                    authorization_token = args.get("authorization_token")
                    
                    if not file_path and not file_content:
                        raise ValueError("Either file_path or file_content parameter is required for ocr_pan")
                    
                    result = self.call_ocr_tool("ocr_pan", file_path=file_path, file_content=file_content, file_name=file_name, authorization_token=authorization_token)
                    
                elif tool_name == "ocr_aadhaar":
                    file_path = args.get("file_path")
                    file_content = args.get("file_content")
                    file_name = args.get("file_name")
                    authorization_token = args.get("authorization_token")
                    
                    if not file_path and not file_content:
                        raise ValueError("Either file_path or file_content parameter is required for ocr_aadhaar")
                    
                    result = self.call_ocr_tool("ocr_aadhaar", file_path=file_path, file_content=file_content, file_name=file_name, authorization_token=authorization_token)
                    
                elif tool_name == "ocr_passport":
                    file_path = args.get("file_path")
                    file_content = args.get("file_content")
                    file_name = args.get("file_name")
                    authorization_token = args.get("authorization_token")
                    
                    if not file_path and not file_content:
                        raise ValueError("Either file_path or file_content parameter is required for ocr_passport")
                    
                    result = self.call_ocr_tool("ocr_passport", file_path=file_path, file_content=file_content, file_name=file_name, authorization_token=authorization_token)
                    
                elif tool_name == "ocr_license":
                    file_path = args.get("file_path")
                    file_content = args.get("file_content")
                    file_name = args.get("file_name")
                    authorization_token = args.get("authorization_token")
                    
                    if not file_path and not file_content:
                        raise ValueError("Either file_path or file_content parameter is required for ocr_license")
                    
                    result = self.call_ocr_tool("ocr_license", file_path=file_path, file_content=file_content, file_name=file_name, authorization_token=authorization_token)
                    
                elif tool_name == "ocr_voter":
                    file_path = args.get("file_path")
                    file_content = args.get("file_content")
                    file_name = args.get("file_name")
                    authorization_token = args.get("authorization_token")
                    
                    if not file_path and not file_content:
                        raise ValueError("Either file_path or file_content parameter is required for ocr_voter")
                    
                    result = self.call_ocr_tool("ocr_voter", file_path=file_path, file_content=file_content, file_name=file_name, authorization_token=authorization_token)
                    
                elif tool_name == "ocr_gst":
                    file_path = args.get("file_path")
                    file_content = args.get("file_content")
                    file_name = args.get("file_name")
                    authorization_token = args.get("authorization_token")
                    
                    if not file_path and not file_content:
                        raise ValueError("Either file_path or file_content parameter is required for ocr_gst")
                    
                    result = self.call_ocr_tool("ocr_gst", file_path=file_path, file_content=file_content, file_name=file_name, authorization_token=authorization_token)
                    
                elif tool_name == "ocr_itr":
                    file_path = args.get("file_path")
                    file_content = args.get("file_content")
                    file_name = args.get("file_name")
                    use_pdf = args.get("use_pdf", "true")
                    authorization_token = args.get("authorization_token")
                    
                    if not file_path and not file_content:
                        raise ValueError("Either file_path or file_content parameter is required for ocr_itr")
                    
                    result = self.call_ocr_tool("ocr_itr", file_path=file_path, file_content=file_content, file_name=file_name, use_pdf=use_pdf, authorization_token=authorization_token)
                    
                elif tool_name == "ocr_cheque":
                    file_path = args.get("file_path")
                    file_content = args.get("file_content")
                    file_name = args.get("file_name")
                    authorization_token = args.get("authorization_token")
                    
                    if not file_path and not file_content:
                        raise ValueError("Either file_path or file_content parameter is required for ocr_cheque")
                    
                    result = self.call_ocr_tool("ocr_cheque", file_path=file_path, file_content=file_content, file_name=file_name, authorization_token=authorization_token)
                    
                elif tool_name == "ocr_document_detect":
                    file_path = args.get("file_path")
                    file_content = args.get("file_content")
                    file_name = args.get("file_name")
                    authorization_token = args.get("authorization_token")
                    
                    if not file_path and not file_content:
                        raise ValueError("Either file_path or file_content parameter is required for ocr_document_detect")
                    
                    result = self.call_ocr_tool("ocr_document_detect", file_path=file_path, file_content=file_content, file_name=file_name, authorization_token=authorization_token)
                    
                elif tool_name == "universal_file_verify":
                    tool = args.get("tool")
                    file_path = args.get("file_path")
                    file_content = args.get("file_content")
                    file_name = args.get("file_name")
                    use_pdf = args.get("use_pdf", "true")
                    authorization_token = args.get("authorization_token")
                    
                    if not tool:
                        raise ValueError("Tool parameter is required for universal_file_verify")
                    if not file_path and not file_content:
                        raise ValueError("Either file_path or file_content parameter is required for universal_file_verify")
                        
                    result = self.call_universal_file_verify(tool, file_path=file_path, file_content=file_content, file_name=file_name, use_pdf=use_pdf, authorization_token=authorization_token)
                    
                else:
                    error_msg = f"Unknown tool: {tool_name}"
                    logger.error(f"❌ {error_msg}")
                    return {
                        "jsonrpc": "2.0",
                        "id": req_id,
                        "error": {
                            "code": -32601,
                            "message": error_msg,
                            "data": {
                                "available_tools": [
                                    "universal_verify", "chat_agent", "intelligent_verify", "get_capabilities",
                                    "ocr_pan", "ocr_aadhaar", "ocr_passport", "ocr_license", "ocr_voter",
                                    "ocr_gst", "ocr_itr", "ocr_cheque", "ocr_document_detect", "universal_file_verify"
                                ]
                            }
                        }
                    }
                
                logger.info(f"✅ Tool {tool_name} executed successfully")
                
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "content": [{
                            "type": "text",
                            "text": result
                        }]
                    }
                }
                
            except KeyError as e:
                error_msg = f"Missing required parameter: {str(e)}"
                logger.error(f"❌ {error_msg}")
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {
                        "code": -32602,
                        "message": error_msg
                    }
                }
            except ValueError as e:
                error_msg = f"Invalid parameter: {str(e)}"
                logger.error(f"❌ {error_msg}")
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {
                        "code": -32602,
                        "message": error_msg
                    }
                }
            except Exception as e:
                error_msg = f"Tool execution error: {str(e)}"
                logger.error(f"❌ {error_msg}")
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {
                        "code": -1,
                        "message": error_msg
                    }
                }

        else:
            error_msg = f"Method not found: {method}"
            logger.error(f"❌ {error_msg}")
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {
                    "code": -32601,
                    "message": error_msg,
                    "data": {
                        "available_methods": ["initialize", "tools/list", "tools/call"]
                    }
                }
            }

    def run(self):
        """Run the MCP server"""
        logger.info("🚀 Enhanced KYC MCP Server starting...")
        logger.info(f"   Server URL: {self.base_url}")
        logger.info("   ✅ Original tools: universal_verify, chat_agent, get_capabilities")
        logger.info("   🆕 NEW: intelligent_verify with smart document detection and routing")
        logger.info("   📄 NEW: OCR tools for all document types (PAN, Aadhaar, Passport, etc.)")
        logger.info("   📁 NEW: universal_file_verify for file-based operations")
        logger.info("   🔧 FIXED: Proper Claude Desktop compatibility")
        logger.info("   Waiting for MCP requests from Claude Desktop...")
        
        for line in sys.stdin:
            try:
                # Parse the JSON-RPC request
                request_line = line.strip()
                if not request_line:
                    continue
                    
                request = json.loads(request_line)
                
                # Handle the request
                response = self.handle_request(request)
                
                # Send the response (always send for Claude Desktop compatibility)
                print(json.dumps(response), flush=True)
                
            except json.JSONDecodeError as e:
                logger.error(f"❌ JSON decode error: {e}")
                error_response = {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "error": {
                        "code": -32700,
                        "message": "Parse error",
                        "data": str(e)
                    }
                }
                print(json.dumps(error_response), flush=True)
                
            except KeyboardInterrupt:
                logger.info("🛑 MCP server stopped by user")
                break
                
            except Exception as e:
                logger.error(f"❌ Unexpected error: {e}")
                error_response = {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "error": {
                        "code": -1,
                        "message": f"Internal server error: {str(e)}"
                    }
                }
                print(json.dumps(error_response), flush=True)

def main():
    """Main entry point"""
    # Set up environment
    if len(sys.argv) > 1:
        # Allow server URL to be passed as command line argument
        os.environ["KYC_SERVER_URL"] = sys.argv[1]
    
    # Create and run the server
    server = EnhancedKYCMCPServer()
    try:
        server.run()
    except KeyboardInterrupt:
        logger.info("🛑 MCP server shutdown completed")
    except Exception as e:
        logger.error(f"❌ Fatal error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()