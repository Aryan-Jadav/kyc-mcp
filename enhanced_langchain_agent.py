"""
Enhanced LangChain Agent for KYC MCP Server
Provides intelligent query understanding and KYC verification routing
"""

import os
import json
import logging
import asyncio
from typing import Dict, Any, List, Optional, Union
import requests
from datetime import datetime

# LangChain imports
from langchain.agents import initialize_agent, Tool, AgentExecutor
from langchain.agents.agent_types import AgentType
from langchain.chat_models import ChatOpenAI
from langchain.tools.base import BaseTool, ToolException
from langchain.schema import AgentAction, AgentFinish
from langchain.memory import ConversationBufferMemory
from langchain.prompts import PromptTemplate
from langchain.callbacks.manager import CallbackManagerForToolRun

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class UniversalKYCTool(BaseTool):
    """Enhanced KYC tool with better error handling and validation"""
    
    name = "universal_kyc_verification"
    description = """
    Use this tool to perform KYC (Know Your Customer) verifications. 
    
    Available verification types:
    - PAN verification: pan, pan_comprehensive, pan_kra, pan_adv, pan_adv_v2
    - Aadhaar verification: aadhaar_generate_otp, aadhaar_validation
    - Bank verification: bank_verification, upi_verification
    - Corporate verification: gstin, gstin_advanced, company_details
    - Document verification: passport, driving_license, voter_id
    - And many more...
    
    Input should be a JSON string with:
    {
        "tool": "verification_type",
        "params": {
            "id_number": "document_number",
            "other_params": "as_needed"
        }
    }
    
    Examples:
    - PAN verification: {"tool": "pan_comprehensive", "params": {"id_number": "ABCDE1234F"}}
    - Bank verification: {"tool": "bank_verification", "params": {"id_number": "123456789", "ifsc": "SBIN0000123"}}
    - GSTIN verification: {"tool": "gstin", "params": {"id_number": "29ABCDE1234F1Z5"}}
    """
    
    # Fix: Add field declaration for LangChain compatibility
    server_url: str = ""
    
    def __init__(self, server_url: str = None):
        super().__init__()
        self.server_url = server_url or os.getenv("KYC_SERVER_URL", "http://localhost:8000")
        
    def _run(self, query: str, run_manager: Optional[CallbackManagerForToolRun] = None) -> str:
        """Execute the KYC verification tool"""
        try:
            logger.info(f"UniversalKYCTool received query: {query}")
            
            # Handle different input formats more robustly
            tool_input = None
            
            # Try to parse as JSON first
            if isinstance(query, str):
                # Clean up the query string
                query = query.strip()
                if query.startswith('{') and query.endswith('}'):
                    try:
                        tool_input = json.loads(query)
                        logger.info(f"Parsed JSON input: {tool_input}")
                    except json.JSONDecodeError as e:
                        logger.warning(f"JSON decode error: {e}, trying natural language parsing")
                        tool_input = self._parse_natural_language(query)
                else:
                    # Try natural language parsing
                    tool_input = self._parse_natural_language(query)
            else:
                tool_input = query
            
            # Validate input structure
            if not isinstance(tool_input, dict):
                logger.warning(f"Invalid tool input format: {tool_input}")
                return json.dumps({
                    "success": False,
                    "error": "Invalid input format. Expected JSON with 'tool' and 'params' fields.",
                    "received": str(tool_input),
                    "example": '{"tool": "pan_comprehensive", "params": {"id_number": "ABCDE1234F"}}'
                })
            
            if "tool" not in tool_input:
                # If no tool specified, try to extract from the query
                logger.info("No tool specified, attempting natural language parsing")
                tool_input = self._parse_natural_language(query if isinstance(query, str) else str(query))
            
            tool = tool_input.get("tool")
            params = tool_input.get("params", {})
            
            if not tool:
                return json.dumps({
                    "success": False,
                    "error": "No verification tool specified.",
                    "suggestion": "Please specify what type of document you want to verify (e.g., PAN, GSTIN, etc.)"
                })
            
            # Validate tool name
            valid_tools = [
                "pan", "pan_comprehensive", "pan_kra", "pan_adv", "pan_adv_v2", "pan_aadhaar_link",
                "aadhaar_generate_otp", "aadhaar_validation", "bank_verification", "upi_verification",
                "gstin", "gstin_advanced", "gstin_by_pan", "company_details", "passport", 
                "driving_license", "voter_id", "tan", "itr_compliance", "electricity_bill",
                "telecom_verification", "credit_report", "face_match", "face_liveness"
            ]
            
            if tool not in valid_tools:
                return json.dumps({
                    "success": False,
                    "error": f"Unknown verification tool: {tool}",
                    "available_tools": valid_tools[:10],  # Show first 10 for brevity
                    "message": "Use a valid verification tool name"
                })
            
            # Make the API call
            url = f"{self.server_url}/universal-verify"
            logger.info(f"Making API call to {url} with tool: {tool}, params: {params}")
            
            response = requests.post(
                url,
                json={"tool": tool, "params": params},
                headers={"Content-Type": "application/json"},
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                # Format the response for better readability
                return self._format_response(result, tool)
            else:
                return json.dumps({
                    "success": False,
                    "error": f"API call failed with status {response.status_code}",
                    "details": response.text
                })
                
        except requests.exceptions.Timeout:
            return json.dumps({
                "success": False,
                "error": "Request timed out. The verification service may be busy.",
                "suggestion": "Please try again in a moment."
            })
        except requests.exceptions.ConnectionError:
            return json.dumps({
                "success": False,
                "error": "Cannot connect to KYC verification service.",
                "check": "Ensure the KYC server is running and accessible."
            })
        except Exception as e:
            logger.error(f"KYC tool error: {str(e)}")
            return json.dumps({
                "success": False,
                "error": f"Unexpected error: {str(e)}",
                "type": type(e).__name__
            })
    
    def _parse_natural_language(self, query: str) -> Dict[str, Any]:
        """Parse natural language queries into structured tool calls"""
        logger.info(f"Parsing natural language query: {query}")
        query_lower = query.lower()
        
        # Extract PAN number pattern
        import re
        pan_pattern = r'[A-Z]{5}[0-9]{4}[A-Z]'
        pan_match = re.search(pan_pattern, query.upper())
        
        # Extract phone number pattern
        phone_pattern = r'\b\d{10}\b'
        phone_match = re.search(phone_pattern, query)
        
        # Extract GSTIN pattern
        gstin_pattern = r'\b\d{2}[A-Z]{5}\d{4}[A-Z]\d[Z][A-Z\d]\b'
        gstin_match = re.search(gstin_pattern, query.upper())
        
        # Determine verification type based on keywords and patterns
        if pan_match:
            pan_number = pan_match.group()
            if any(word in query_lower for word in ["comprehensive", "detailed", "complete"]):
                return {"tool": "pan_comprehensive", "params": {"id_number": pan_number}}
            elif "kra" in query_lower:
                return {"tool": "pan_kra", "params": {"id_number": pan_number}}
            else:
                return {"tool": "pan_comprehensive", "params": {"id_number": pan_number}}
                
        elif gstin_match:
            gstin_number = gstin_match.group()
            if "advanced" in query_lower:
                return {"tool": "gstin_advanced", "params": {"id_number": gstin_number}}
            else:
                return {"tool": "gstin", "params": {"id_number": gstin_number}}
                
        elif phone_match:
            phone_number = phone_match.group()
            if any(word in query_lower for word in ["upi", "payment"]):
                return {"tool": "upi_mobile_name", "params": {"mobile_number": phone_number}}
            elif "bank" in query_lower:
                return {"tool": "mobile_to_bank", "params": {"mobile_no": phone_number}}
            else:
                return {"tool": "telecom_verification", "params": {"id_number": phone_number}}
        
        # Check for general service inquiries
        elif any(word in query_lower for word in ["what", "services", "offer", "help", "can", "do"]):
            return {
                "tool": "info_request",
                "params": {},
                "response": "I can help you verify various documents including PAN cards, Aadhaar, GSTIN, bank accounts, passports, driving licenses, and more. Please let me know what document you'd like to verify."
            }
                
        # Default fallback
        return {
            "tool": "unknown",
            "params": {},
            "error": "Could not identify the document type. Please specify what you want to verify (e.g., 'Verify PAN ABCDE1234F')."
        }
    
    def _format_response(self, result: Dict[str, Any], tool: str) -> str:
        """Format the API response for better readability"""
        if not result.get("success"):
            return json.dumps({
                "verification_status": "FAILED",
                "tool_used": tool,
                "error": result.get("error", "Unknown error"),
                "message": result.get("message", "Verification failed")
            }, indent=2)
        
        # Extract key information based on verification type
        data = result.get("data", {})
        formatted_result = {
            "verification_status": "SUCCESS",
            "tool_used": tool,
            "timestamp": datetime.now().isoformat()
        }
        
        # Format based on verification type
        if tool.startswith("pan"):
            formatted_result.update({
                "pan_number": data.get("pan_number"),
                "full_name": data.get("full_name"),
                "father_name": data.get("father_name"),
                "aadhaar_linked": data.get("aadhaar_linked"),
                "address": data.get("address"),
                "category": data.get("category")
            })
        elif tool == "gstin":
            formatted_result.update({
                "gstin": data.get("gstin"),
                "business_name": data.get("business_name"),
                "status": data.get("status"),
                "registration_date": data.get("registration_date")
            })
        elif tool == "bank_verification":
            formatted_result.update({
                "account_number": data.get("account_number"),
                "account_holder_name": data.get("name"),
                "bank_name": data.get("bank_name"),
                "ifsc": data.get("ifsc"),
                "account_status": data.get("account_status")
            })
        else:
            # Include all data for other verification types
            formatted_result["verification_data"] = data
        
        # Remove None values
        formatted_result = {k: v for k, v in formatted_result.items() if v is not None}
        
        return json.dumps(formatted_result, indent=2, ensure_ascii=False)

class KYCInfoTool(BaseTool):
    """Tool for providing information about KYC services"""
    
    name = "kyc_info"
    description = """
    Use this tool to provide information about available KYC verification services.
    This tool answers general questions about what services are available.
    """
    
    def _run(self, query: str, run_manager: Optional[CallbackManagerForToolRun] = None) -> str:
        """Provide information about KYC services"""
        return """I can help you verify various types of documents and identities:

📄 **Document Verification:**
- PAN (Permanent Account Number) - Basic, Comprehensive, KRA verification
- Aadhaar - Validation, OTP generation
- Passport verification
- Driving License verification
- Voter ID verification

🏢 **Corporate Verification:**
- GSTIN (GST Identification) - Basic and Advanced
- Company CIN verification
- Director details verification
- Udyog Aadhaar verification

🏦 **Financial Verification:**
- Bank account verification
- UPI ID verification
- ITR compliance check
- Credit report generation

📱 **Additional Services:**
- Telecom verification
- Electricity bill verification
- Face matching and liveness detection
- OCR services for various documents

To verify a document, please provide the document type and number. For example:
- "Verify PAN ABCDE1234F"
- "Check GSTIN 29ABCDE1234F1Z5"
- "Verify bank account 123456789 with IFSC SBIN0000123"

What would you like to verify today?"""

class EnhancedKYCAgent:
    """Enhanced KYC agent with conversation memory and better prompting"""
    
    def __init__(self, server_url: str = None, openai_api_key: str = None):
        self.server_url = server_url or os.getenv("KYC_SERVER_URL", "http://localhost:8000")
        
        # Initialize OpenAI
        if openai_api_key:
            os.environ["OPENAI_API_KEY"] = openai_api_key
        elif not os.getenv("OPENAI_API_KEY"):
            raise ValueError("OpenAI API key is required. Set OPENAI_API_KEY environment variable.")
        
        # Initialize LLM
        self.llm = ChatOpenAI(
            temperature=0,
            model="gpt-3.5-turbo",
            max_tokens=1000
        )
        
        # Initialize memory
        self.memory = ConversationBufferMemory(
            memory_key="chat_history",
            return_messages=True
        )
        
        # Initialize tools
        self.tools = [
            UniversalKYCTool(server_url=self.server_url),
            KYCInfoTool()
        ]
        
        # Initialize agent
        self.agent = initialize_agent(
            tools=self.tools,
            llm=self.llm,
            agent=AgentType.CONVERSATIONAL_REACT_DESCRIPTION,
            memory=self.memory,
            verbose=True,
            handle_parsing_errors=True,
            max_iterations=3
        )
    
    def ask(self, question: str) -> str:
        """Process a user question and return response"""
        try:
            # Handle simple greetings directly
            question_lower = question.lower().strip()
            if question_lower in ["hello", "hi", "hey", "help"]:
                return """Hello! I'm your KYC verification assistant. I can help you verify various documents including:

📄 PAN cards, Aadhaar, Passport, Driving License, Voter ID
🏢 GSTIN, Company details, Director information
🏦 Bank accounts, UPI IDs, Credit reports
📱 And many more verification services

To get started, please tell me what document you'd like to verify. For example:
- "Verify PAN ABCDE1234F"
- "Check GSTIN 29ABCDE1234F1Z5"
- "What verification services do you offer?"

What can I help you verify today?"""
            
            response = self.agent.run(input=question)
            return response
        except Exception as e:
            logger.error(f"Agent error: {str(e)}")
            return f"I encountered an error while processing your request: {str(e)}. Please try rephrasing your question or contact support."
    
    def clear_memory(self):
        """Clear conversation memory"""
        self.memory.clear()
    
    def get_conversation_history(self) -> List[Dict[str, str]]:
        """Get conversation history"""
        return self.memory.chat_memory.messages

# Singleton instance for the agent
_agent_instance = None

def get_agent(server_url: str = None, openai_api_key: str = None) -> EnhancedKYCAgent:
    """Get or create the KYC agent instance"""
    global _agent_instance
    if _agent_instance is None:
        _agent_instance = EnhancedKYCAgent(server_url=server_url, openai_api_key=openai_api_key)
    return _agent_instance

def ask_agent(question: str, server_url: str = None, openai_api_key: str = None) -> str:
    """Simplified interface for asking the agent"""
    try:
        agent = get_agent(server_url=server_url, openai_api_key=openai_api_key)
        return agent.ask(question)
    except Exception as e:
        logger.error(f"Error in ask_agent: {str(e)}")
        return json.dumps({
            "success": False,
            "error": f"Agent initialization or execution failed: {str(e)}",
            "suggestion": "Check your OpenAI API key and server configuration"
        })

# Example usage and testing
if __name__ == "__main__":
    # Test the agent
    test_questions = [
        "Hello",
        "What verification services do you offer?",
        "Verify PAN ABCDE1234F",
        "Check GSTIN 29ABCDE1234F1Z5"
    ]
    
    agent = get_agent()
    
    for question in test_questions:
        print(f"\nQ: {question}")
        print(f"A: {agent.ask(question)}")
        print("-" * 50)