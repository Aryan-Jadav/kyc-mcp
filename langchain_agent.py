import os
import re
import requests
from langchain.agents import initialize_agent, Tool
from langchain.chat_models import ChatOpenAI, ChatAnthropic
from config import ENDPOINTS  # Make sure this points to your actual config.py

# Choose the appropriate LLM
def get_llm():
    provider = os.getenv("LLM_PROVIDER", "openai").lower()
    if provider == "anthropic":
        return ChatAnthropic(temperature=0)
    return ChatOpenAI(temperature=0)

# Automatically determine tool name from input text
def detect_tool_from_text(text: str) -> str:
    tool_match = None
    for tool in ENDPOINTS:
        if re.search(rf"\b{re.escape(tool)}\b", text, re.IGNORECASE):
            tool_match = tool
            break
    return tool_match

# Universal function for hitting /universal-verify
def universal_tool(input_text: str) -> str:
    tool = detect_tool_from_text(input_text)
    if not tool:
        return "Could not identify any supported KYC tool from your request."

    # Extract possible id_number, pan, aadhaar, ifsc, etc.
    params = {}

    if "pan" in tool:
        match = re.search(r"[A-Z]{5}[0-9]{4}[A-Z]", input_text)
        if match:
            params["id_number"] = match.group(0)

    elif "aadhaar" in tool:
        match = re.search(r"\b\d{12}\b", input_text)
        if match:
            params["id_number"] = match.group(0)

    elif "bank" in tool:
        acc = re.search(r"account(?: number)?[ :]*([0-9]{9,18})", input_text, re.I)
        ifsc = re.search(r"ifsc[ :]*([A-Z]{4}0[A-Z0-9]{6})", input_text, re.I)
        if acc:
            params["id_number"] = acc.group(1)
        if ifsc:
            params["ifsc"] = ifsc.group(1)

    elif "voter" in tool or "passport" in tool or "gst" in tool or "cin" in tool:
        match = re.search(r"[A-Z0-9]{6,20}", input_text, re.I)
        if match:
            params["id_number"] = match.group(0)

    # Fallback: extract generic ID number
    if not params.get("id_number"):
        match = re.search(r"\b([A-Z0-9]{6,20})\b", input_text, re.I)
        if match:
            params["id_number"] = match.group(1)

    if not params:
        return "Could not extract required ID details from your input."

    # Send the request
    url = os.getenv("KYC_SERVER_URL", "http://localhost:8000/universal-verify")
    payload = {"tool": tool, "params": params}
    try:
        response = requests.post(url, json=payload, timeout=30)
        result = response.json()

        if result.get("success"):
            data = result.get("data", {})
            if not data:
                return f"{tool} verification succeeded, but no data was returned."

            formatted = "\n".join(f"{k}: {v}" for k, v in data.items())
            return f"{tool} verification result:\n{formatted}"
        else:
            return f"{tool} verification failed: {result.get('error', 'Unknown error')}"
    except Exception as e:
        return f"Error calling KYC server: {str(e)}"

# LangChain Agent setup
tools = [
    Tool(
        name="kyc_universal_tool",
        func=universal_tool,
        description="Use this tool to verify KYC documents (PAN, Aadhaar, Voter ID, GST, Passport, CIN, etc)."
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
