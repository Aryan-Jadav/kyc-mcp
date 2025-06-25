import os
import re
import requests
from langchain.agents import Tool, initialize_agent
from langchain.chat_models import ChatOpenAI
from config import ENDPOINTS

# Choose LLM provider (currently using OpenAI only)
def get_llm():
    return ChatOpenAI(temperature=0)

# Extract tool from natural language prompt using config keys
def detect_tool_from_text(text: str) -> str:
    for tool in ENDPOINTS:
        if re.search(rf"\b{re.escape(tool)}\b", text, re.IGNORECASE):
            return tool
    return None

# Extract basic parameters from text (customize as needed)
def extract_params(tool: str, text: str) -> dict:
    params = {}

    if "pan" in tool:
        match = re.search(r"[A-Z]{5}[0-9]{4}[A-Z]", text)
        if match:
            params["id_number"] = match.group(0)

    elif "aadhaar" in tool:
        match = re.search(r"\b\d{12}\b", text)
        if match:
            params["id_number"] = match.group(0)

    elif "bank" in tool:
        acc = re.search(r"account(?: number)?[ :]*([0-9]{9,18})", text, re.I)
        ifsc = re.search(r"ifsc[ :]*([A-Z]{4}0[A-Z0-9]{6})", text, re.I)
        if acc:
            params["id_number"] = acc.group(1)
        if ifsc:
            params["ifsc"] = ifsc.group(1)

    elif "voter" in tool or "passport" in tool or "gst" in tool or "cin" in tool:
        match = re.search(r"\b[A-Z0-9]{6,20}\b", text)
        if match:
            params["id_number"] = match.group(0)

    if not params:
        match = re.search(r"\b([A-Z0-9]{6,20})\b", text, re.I)
        if match:
            params["id_number"] = match.group(0)

    return params

# Call your /universal-verify API
def universal_tool(input_text: str) -> str:
    tool = detect_tool_from_text(input_text)
    if not tool:
        return "❌ Could not determine tool type from your input."

    params = extract_params(tool, input_text)
    if not params:
        return f"❌ Could not extract parameters for {tool.upper()} verification."

    url = os.getenv("KYC_SERVER_URL", "http://localhost:8000/universal-verify")
    payload = {"tool": tool, "params": params}

    try:
        resp = requests.post(url, json=payload, timeout=30)
        result = resp.json()

        if result.get("success"):
            data = result.get("data", {})
            if not data:
                return f"✅ {tool.upper()} verified successfully (no details returned)."
            
            id_val = (
                data.get("pan_number") or
                data.get("aadhaar_number") or
                data.get("id_number") or
                "<unknown>"
            )
            name = data.get("full_name") or data.get("name") or "<name not found>"

            details = "\n".join(f"{k}: {v}" for k, v in data.items())
            return f"✅ {tool.upper()} verification successful:\n• ID: {id_val}\n• Name: {name}\n\nDetails:\n{details}"
        else:
            return f"❌ Verification failed for {tool.upper()}:\n{result.get('message') or result.get('error') or 'Unknown error'}"
    
    except Exception as e:
        return f"❌ Error contacting KYC server: {str(e)}"

# LangChain agent setup
tools = [
    Tool(
        name="kyc_universal_tool",
        func=universal_tool,
        description="Use this tool to verify KYC documents (PAN, Aadhaar, Bank, GST, Passport, Voter ID, etc)."
    )
]

def ask_agent(question: str) -> str:
    llm = get_llm()
    agent = initialize_agent(
        tools=tools,
        llm=llm,
        agent="zero-shot-react-description",
        verbose=False,
    )
    return agent.run(question)
