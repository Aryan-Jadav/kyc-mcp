#!/usr/bin/env python3
"""
Simple SSE Test Script
Tests the SSE endpoint to ensure it's working properly
"""

import requests
import json
import time

BASE_URL = "http://139.59.70.153:8000"

def test_sse_connection():
    """Test SSE connection"""
    print("🌊 Testing SSE Connection...")
    
    try:
        url = f"{BASE_URL}/mcp/sse"
        print(f"Connecting to: {url}")
        
        response = requests.get(url, stream=True, timeout=10)
        print(f"Status Code: {response.status_code}")
        
        if response.status_code == 200:
            print("✅ SSE Connection Successful!")
            print("📡 Reading SSE events...")
            
            lines_read = 0
            for line in response.iter_lines(decode_unicode=True):
                if line:
                    print(f"SSE: {line}")
                    lines_read += 1
                    if lines_read >= 5:  # Read first 5 events
                        break
            
            return True
        else:
            print(f"❌ SSE Connection Failed: {response.status_code}")
            print(f"Response: {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ SSE Error: {str(e)}")
        return False

def test_sse_info():
    """Test SSE info endpoint"""
    print("\n📋 Testing SSE Info...")
    
    try:
        url = f"{BASE_URL}/mcp/sse/info"
        response = requests.get(url, timeout=10)
        
        if response.status_code == 200:
            print("✅ SSE Info Successful!")
            data = response.json()
            print(f"Info: {json.dumps(data, indent=2)}")
            return True
        else:
            print(f"❌ SSE Info Failed: {response.status_code}")
            return False
            
    except Exception as e:
        print(f"❌ SSE Info Error: {str(e)}")
        return False

def test_mcp_call():
    """Test MCP tool call"""
    print("\n🔧 Testing MCP Tool Call...")
    
    try:
        url = f"{BASE_URL}/mcp/call"
        data = {
            "tool": "verify_pan_comprehensive",
            "parameters": {
                "id_number": "ABCDE1234F"
            }
        }
        
        response = requests.post(url, json=data, timeout=30)
        
        if response.status_code == 200:
            print("✅ MCP Tool Call Successful!")
            result = response.json()
            print(f"Result: {json.dumps(result, indent=2)}")
            return True
        else:
            print(f"❌ MCP Tool Call Failed: {response.status_code}")
            print(f"Response: {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ MCP Tool Call Error: {str(e)}")
        return False

def test_health():
    """Test health endpoint"""
    print("\n❤️ Testing Health Endpoint...")
    
    try:
        url = f"{BASE_URL}/health"
        response = requests.get(url, timeout=10)
        
        if response.status_code == 200:
            print("✅ Health Check Successful!")
            data = response.json()
            print(f"Health: {json.dumps(data, indent=2)}")
            return True
        else:
            print(f"❌ Health Check Failed: {response.status_code}")
            return False
            
    except Exception as e:
        print(f"❌ Health Check Error: {str(e)}")
        return False

def main():
    """Run all SSE tests"""
    print("🚀 Starting SSE Tests")
    print(f"Base URL: {BASE_URL}")
    
    tests = [
        ("Health Check", test_health),
        ("SSE Info", test_sse_info),
        ("SSE Connection", test_sse_connection),
        ("MCP Tool Call", test_mcp_call),
    ]
    
    passed = 0
    total = len(tests)
    
    for test_name, test_func in tests:
        print(f"\n{'='*50}")
        print(f"Running: {test_name}")
        print('='*50)
        
        success = test_func()
        if success:
            passed += 1
        
        time.sleep(1)  # Small delay between tests
    
    print(f"\n{'='*50}")
    print(f"📊 Test Results: {passed}/{total} tests passed")
    print('='*50)
    
    if passed == total:
        print("🎉 All SSE tests passed!")
        return 0
    else:
        print("❌ Some SSE tests failed.")
        return 1

if __name__ == "__main__":
    exit(main())
