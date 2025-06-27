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
    
    def __init__(self, server_url: str = None):
        super().__init__()
        self.server_url = server_url or os.getenv("KYC_SERVER_URL", "http://localhost:8000")
        
    def _run(self, query: str, run_manager: Optional[CallbackManagerForToolRun] = None) -> str:
        """Execute the KYC verification tool"""
        try:
            # Parse the input
            if isinstance(query, str):
                try:
                    tool_input = json.loads(query)
                except json.JSONDecodeError:
                    # Try to intelligently parse natural language
                    tool_input = self._parse_natural_language(query)
            else:
                tool_input = query
                
            # Validate input structure
            if not isinstance(tool_input, dict) or "tool" not in tool_input:
                return json.dumps({
                    "success": False,
                    "error": "Invalid input format. Expected JSON with 'tool' and 'params' fields.",
                    "example": '{"tool": "pan_comprehensive", "params": {"id_number": "ABCDE1234F"}}'
                })
            
            tool = tool_input.get("tool")
            params = tool_input.get("params", {})
            
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
                return {"tool": "pan", "params": {"id_number": pan_number}}
                
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
                
        # Default fallback
        return {
            "tool": "unknown",
            "params": {},
            "error": "Could not parse the query. Please provide specific verification details."
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

class DatabaseSearchTool(BaseTool):
    """Tool for searching the KYC database"""
    
    name = "kyc_database_search"
    description = """
    Search the KYC database for previously verified records.
    
    Search types:
    - search_by_pan: Search by PAN number
    - search_by_name: Search by person name
    - search_by_phone: Search by phone number
    - get_statistics: Get database statistics
    
    Input format: {"search_type": "search_by_pan", "query": "ABCDE1234F"}
    """
    
    def __init__(self, server_url: str = None):
        super().__init__()
        self.server_url = server_url or os.getenv("KYC_SERVER_URL", "http://localhost:8000")
    
    def _run(self, query: str, run_manager: Optional[CallbackManagerForToolRun] = None) -> str:
        """Execute database search"""
        try:
            # Parse input
            if isinstance(query, str):
                try:
                    search_input = json.loads(query)
                except json.JSONDecodeError:
                    return json.dumps({
                        "success": False,
                        "error": "Invalid input format. Expected JSON with 'search_type' and 'query' fields."
                    })
            else:
                search_input = query
            
            search_type = search_input.get("search_type")
            search_query = search_input.get("query")
            
            # Map search types to MCP tools (this would need to be implemented)
            # For now, return a placeholder response
            return json.dumps({
                "success": True,
                "message": f"Database search functionality for {search_type} with query '{search_query}' would be implemented here",
                "note": "This requires the database search MCP tools to be exposed via HTTP endpoints"
            })
            
        except Exception as e:
            return json.dumps({
                "success": False,
                "error": f"Database search error: {str(e)}"
            })

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
            model="gpt-3.5-turbo",  # or gpt-4 for better performance
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
            DatabaseSearchTool(server_url=self.server_url)
        ]
        
        # Custom prompt template
        self.prompt_template = PromptTemplate(
            input_variables=["input", "chat_history", "agent_scratchpad"],
            template="""
You are a KYC (Know Your Customer) verification assistant. You help users verify documents and identities using various verification services.

Available verification types:
- PAN (Permanent Account Number) verification
- Aadhaar verification  
- Bank account verification
- GSTIN (GST Identification Number) verification
- Passport, Driving License, Voter ID verification
- Corporate document verification
- And many more...

When a user asks for verification:
1. Identify what type of document/number they want to verify
2. Extract the relevant information (document numbers, etc.)
3. Use the appropriate verification tool
4. Provide a clear, formatted response

For example:
- "Verify PAN ABCDE1234F" → Use pan_comprehensive tool
- "Check GSTIN 29ABCDE1234F1Z5" → Use gstin tool  
- "Verify bank account 123456789 with IFSC SBIN0000123" → Use bank_verification tool

Previous conversation:
{chat_history}

Current question: {input}

{agent_scratchpad}

Remember to:
- Ask for clarification if the request is unclear
- Provide helpful error messages if verification fails
- Format responses in a user-friendly way
- Suggest alternative verification methods when appropriate
"""
        )
        
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
        "Verify PAN ABCDE1234F",
        "Check GSTIN 29ABCDE1234F1Z5", 
        "What verification services do you offer?",
        "Search database for records with name John Doe"
    ]
    
    agent = get_agent()
    
    for question in test_questions:
        print(f"\nQ: {question}")
        print(f"A: {agent.ask(question)}")
        print("-" * 50)