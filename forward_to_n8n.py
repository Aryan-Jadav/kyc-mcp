# forward_to_n8n.py
import sys
import json
import requests

def main():
    input_data = json.loads(sys.stdin.read())
    pan = input_data.get("input")

    response = requests.post(
        "https://628a-139-59-70-153.ngrok-free.app/webhook/pan-basic",
        headers={"Content-Type": "application/json"},
        json={"pan": pan}
    )

    try:
        result = response.json()
    except Exception:
        result = {"output": "Invalid response from n8n"}

    print(json.dumps({"output": result.get("output", str(result))}))

if __name__ == "__main__":
    main()
