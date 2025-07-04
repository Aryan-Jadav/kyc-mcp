import os
from langchain.agents import initialize_agent, Tool
from langchain.llms import OpenAI, Anthropic
from langchain.prompts import PromptTemplate
from langchain.chains import LLMChain
import kyc_client
import requests

# Choose LLM provider based on environment variable or default to OpenAI
def get_llm():
    provider = os.getenv("LLM_PROVIDER", "openai").lower()
    if provider == "anthropic":
        return Anthropic(temperature=0)
    else:
        return OpenAI(temperature=0)

# Universal tool for all KYC endpoints
def universal_tool(input_text: str):
    # Simple extraction logic (regex/keywords)
    import re
    tool = None
    params = {}
    # Detect tool type
    if re.search(r"\bpan\b", input_text, re.I):
        tool = "pan"
        match = re.search(r"[A-Z]{5}[0-9]{4}[A-Z]", input_text)
        if match:
            params["id_number"] = match.group(0)
    elif re.search(r"aadhaar", input_text, re.I):
        tool = "aadhaar"
        match = re.search(r"\b\d{12}\b", input_text)
        if match:
            params["id_number"] = match.group(0)
    elif re.search(r"bank|account", input_text, re.I):
        tool = "bank"
        # Example: extract account number and IFSC
        acc = re.search(r"account(?: number)?[ :]*([0-9]{9,18})", input_text, re.I)
        ifsc = re.search(r"ifsc[ :]*([A-Z]{4}0[A-Z0-9]{6})", input_text, re.I)
        if acc:
            params["id_number"] = acc.group(1)
        if ifsc:
            params["ifsc"] = ifsc.group(1)
    else:
        return {"error": "Could not determine KYC tool from input."}
    if not tool or not params:
        return {"error": "Could not extract required parameters from input."}
    # Call /universal-verify endpoint
    url = os.getenv("KYC_SERVER_URL", "http://localhost:8000/universal-verify")
    payload = {"tool": tool, "params": params}
    try:
        resp = requests.post(url, json=payload, timeout=30)
        return resp.json()
    except Exception as e:
        return {"error": str(e)}

# Single LangChain tool for all KYC tasks
tools = [
    Tool(
        name="universal_kyc",
        func=universal_tool,
        description="Handle any KYC verification (PAN, Aadhaar, Bank, etc) from a natural language prompt."
    )
]

def ask_agent(question: str):
    llm = get_llm()
    agent = initialize_agent(
        tools,
        llm,
        agent="zero-shot-react-description",
        verbose=False
    )
    return agent.run(question)
