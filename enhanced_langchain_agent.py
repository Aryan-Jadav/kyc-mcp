"""
Enhanced LangChain Agent for KYC MCP Server
Provides intelligent query understanding and KYC verification routing
"""

import os
import json
import logging
import re
from typing import Dict, Any, List, Optional, Union
import requests
from datetime import datetime

# LangChain imports
from langchain.agents import initialize_agent, Tool
from langchain.agents.agent_types import AgentType
from langchain.chat_models import ChatOpenAI
from langchain.memory import ConversationBufferMemory

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def parse_verification_request(query: str) -> Dict[str, Any]:
    """Parse natural language verification requests"""
    query_lower = query.lower()
    
    # Extract PAN number pattern
    pan_pattern = r'[A-Z]{5}[0-9]{4}[A-Z]'
    pan_match = re.search(pan_pattern, query.upper())
    
    # Extract GSTIN pattern  
    gstin_pattern = r'\b\d{2}[A-Z]{5}\d{4}[A-Z]\d[Z][A-Z\d]\b'
    gstin_match = re.search(gstin_pattern, query.upper())
    
    # Extract phone number pattern
    phone_pattern = r'\b\d{10}\b'
    phone_match = re.search(phone_pattern, query)
    
    # Extract bank account and IFSC
    bank_account_pattern = r'\b\d{9,18}\b'
    ifsc_pattern = r'\b[A-Z]{4}0[A-Z0-9]{6}\b'
    bank_match = re.search(bank_account_pattern, query)
    ifsc_match = re.search(ifsc_pattern, query.upper())
    
    # Determine verification type
    if pan_match:
        pan_number = pan_match.group()
        if any(word in query_lower for word in ["comprehensive", "detailed", "complete"]):
            tool = "pan_comprehensive"
        elif "kra" in query_lower:
            tool = "pan_kra"
        else:
            tool = "pan_comprehensive"  # Default to comprehensive
        
        return {
            "tool": tool,
            "params": {"id_number": pan_number}
        }
    
    elif gstin_match:
        gstin_number = gstin_match.group()
        tool = "gstin_advanced" if "advanced" in query_lower else "gstin"
        return {
            "tool": tool,
            "params": {"id_number": gstin_number}
        }
    
    elif bank_match and ifsc_match:
        account_number = bank_match.group()
        ifsc_code = ifsc_match.group()
        return {
            "tool": "bank_verification",
            "params": {"id_number": account_number, "ifsc": ifsc_code}
        }
    
    elif phone_match:
        phone_number = phone_match.group()
        if any(word in query_lower for word in ["upi", "payment"]):
            return {
                "tool": "upi_verification", 
                "params": {"id_number": phone_number}
            }
        else:
            return {
                "tool": "telecom_verification",
                "params": {"id_number": phone_number}
            }
    
    # If no specific pattern found
    return {
        "error": "Could not identify the document type or number to verify. Please specify what you want to verify (e.g., 'Verify PAN ABCDE1234F')"
    }

def make_verification_request(tool: str, params: Dict[str, Any], server_url: str) -> str:
    """Make direct verification request"""
    try:
        url = f"{server_url}/universal-verify"
        logger.info(f"Making verification request to {url} with tool: {tool}, params: {params}")
        
        response = requests.post(
            url,
            json={"tool": tool, "params": params},
            headers={"Content-Type": "application/json"},
            timeout=30
        )
        
        if response.status_code == 200:
            result = response.json()
            return format_verification_response(result, tool)
        else:
            logger.error(f"API call failed with status {response.status_code}: {response.text}")
            return f"❌ Verification failed with status {response.status_code}. Please try again or contact support."
            
    except requests.exceptions.Timeout:
        return "❌ Verification request timed out. The service may be busy. Please try again."
    except requests.exceptions.ConnectionError:
        return "❌ Cannot connect to verification service. Please check your connection."
    except Exception as e:
        logger.error(f"Verification error: {str(e)}")
        return f"❌ Verification error: {str(e)}"

def format_verification_response(result: Dict[str, Any], tool: str) -> str:
    """Format verification response for better readability"""
    if not result.get("success"):
        error_msg = result.get("error", "Unknown error")
        return f"❌ Verification failed: {error_msg}"
    
    data = result.get("data", {})
    
    if tool.startswith("pan"):
        response = f"✅ **PAN Verification Successful**\n\n"
        if data.get("pan_number"):
            response += f"📄 **PAN Number:** {data['pan_number']}\n"
        if data.get("full_name"):
            response += f"👤 **Name:** {data['full_name']}\n"
        if data.get("father_name"):
            response += f"👨 **Father's Name:** {data['father_name']}\n"
        if data.get("aadhaar_linked") is not None:
            status = "✅ Linked" if data['aadhaar_linked'] else "❌ Not Linked"
            response += f"🔗 **Aadhaar Status:** {status}\n"
        if data.get("address"):
            addr = data['address']
            if isinstance(addr, dict):
                if addr.get("full"):
                    response += f"🏠 **Address:** {addr['full']}\n"
                elif addr.get("city") or addr.get("state"):
                    city = addr.get("city", "")
                    state = addr.get("state", "")
                    if city and state:
                        response += f"🏠 **Location:** {city}, {state}\n"
        if data.get("category"):
            response += f"📊 **Category:** {data['category']}\n"
        
        return response.strip()
    
    elif tool.startswith("gstin"):
        response = f"✅ **GSTIN Verification Successful**\n\n"
        if data.get("gstin"):
            response += f"📄 **GSTIN:** {data['gstin']}\n"
        if data.get("business_name"):
            response += f"🏢 **Business Name:** {data['business_name']}\n"
        if data.get("status"):
            response += f"📊 **Status:** {data['status']}\n"
        if data.get("registration_date"):
            response += f"📅 **Registration Date:** {data['registration_date']}\n"
        
        return response.strip()
    
    elif tool == "bank_verification":
        response = f"✅ **Bank Verification Successful**\n\n"
        if data.get("account_number"):
            response += f"🏦 **Account Number:** {data['account_number']}\n"
        if data.get("name"):
            response += f"👤 **Account Holder:** {data['name']}\n"
        if data.get("bank_name"):
            response += f"🏛️ **Bank Name:** {data['bank_name']}\n"
        if data.get("ifsc"):
            response += f"🔢 **IFSC Code:** {data['ifsc']}\n"
        
        return response.strip()
    
    else:
        # Generic response for other verification types
        return f"✅ **{tool.replace('_', ' ').title()} verification completed successfully.**\n\n📋 **Details:**\n{json.dumps(data, indent=2)}"

class EnhancedKYCAgent:
    """Enhanced KYC agent with direct verification approach"""
    
    def __init__(self, server_url: str = None, openai_api_key: str = None):
        self.server_url = server_url or os.getenv("KYC_SERVER_URL", "http://localhost:8000")
        
        # Store OpenAI key but we'll primarily use direct processing
        if openai_api_key:
            os.environ["OPENAI_API_KEY"] = openai_api_key
        
        # Initialize memory for conversation context
        self.memory = ConversationBufferMemory(
            memory_key="chat_history",
            return_messages=True
        )
    
    def ask(self, question: str) -> str:
        """Process a user question and return response"""
        try:
            question_lower = question.lower().strip()
            
            # Handle simple greetings directly
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
            
            # Handle service inquiries directly
            if any(word in question_lower for word in ["what", "services", "offer", "help", "can", "do", "available"]):
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
            
            # Handle verification requests directly
            if any(word in question_lower for word in ["verify", "check", "validate", "confirm"]):
                verification_result = parse_verification_request(question)
                
                if verification_result.get("error"):
                    return verification_result["error"]
                
                # Make verification request
                tool = verification_result["tool"]
                params = verification_result["params"]
                
                return make_verification_request(tool, params, self.server_url)
            
            # For other questions, provide helpful guidance
            return """I'm here to help with document verification. I can verify:

🔍 **To verify a document, please use one of these formats:**
- "Verify PAN [PAN_NUMBER]"
- "Check GSTIN [GSTIN_NUMBER]"
- "Verify bank account [ACCOUNT] with IFSC [IFSC_CODE]"
- "Check phone number [PHONE_NUMBER]"

📋 **For information:**
- "What services do you offer?"
- "What documents can you verify?"

What would you like to verify today?"""
            
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
        return f"I encountered an error: {str(e)}. Please try again or contact support."

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