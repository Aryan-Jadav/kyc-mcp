#!/usr/bin/env python3
"""
Universal Endpoint Test Script
Tests the /mcp/universal-verify endpoint for custom GPT integration
"""

import requests
import json
import time

BASE_URL = "http://139.59.70.153:8000"
TEST_PAN = "ABCDE1234F"

def test_universal_endpoint(tool, params, description):
    """Test the universal endpoint with specific tool and params"""
    print(f"\n🧪 Testing: {description}")
    
    try:
        url = f"{BASE_URL}/mcp/universal-verify"
        data = {
            "tool": tool,
            "params": params
        }
        
        print(f"   URL: {url}")
        print(f"   Tool: {tool}")
        print(f"   Params: {params}")
        
        response = requests.post(url, json=data, timeout=30)
        print(f"   Status: {response.status_code}")
        
        if response.status_code == 200:
            print("   ✅ SUCCESS")
            result = response.json()
            print(f"   Response: {json.dumps(result, indent=2)[:300]}...")
            return True
        else:
            print("   ❌ FAILED")
            print(f"   Error: {response.text}")
            return False
            
    except Exception as e:
        print(f"   ❌ NETWORK ERROR: {str(e)}")
        return False

def test_universal_error_cases():
    """Test error cases for the universal endpoint"""
    print(f"\n🔍 Testing Error Cases")
    
    error_tests = [
        {
            "data": {},
            "description": "Missing tool parameter",
            "expected_status": 400
        },
        {
            "data": {"tool": "invalid_tool", "params": {}},
            "description": "Invalid tool name",
            "expected_status": 400
        },
        {
            "data": {"tool": "pan"},
            "description": "Missing params",
            "expected_status": 200  # Should work with empty params
        }
    ]
    
    passed = 0
    for test in error_tests:
        try:
            url = f"{BASE_URL}/mcp/universal-verify"
            response = requests.post(url, json=test["data"], timeout=10)
            
            print(f"   Test: {test['description']}")
            print(f"   Expected: {test['expected_status']}, Got: {response.status_code}")
            
            if response.status_code == test["expected_status"]:
                print("   ✅ PASS")
                passed += 1
            else:
                print("   ❌ FAIL")
                print(f"   Response: {response.text[:200]}")
                
        except Exception as e:
            print(f"   ❌ ERROR: {str(e)}")
    
    return passed, len(error_tests)

def test_available_tools():
    """Test to see what tools are available"""
    print(f"\n📋 Testing Available Tools")
    
    # Test with invalid tool to get list of available tools
    try:
        url = f"{BASE_URL}/mcp/universal-verify"
        data = {"tool": "invalid_tool_to_get_list", "params": {}}
        
        response = requests.post(url, json=data, timeout=10)
        
        if response.status_code == 400:
            result = response.json()
            if "Available tools:" in result.get("message", ""):
                print("   ✅ Available tools listed in error message")
                print(f"   Message: {result['message']}")
                return True
            else:
                print("   ⚠️ Error message doesn't list available tools")
                print(f"   Response: {json.dumps(result, indent=2)}")
                return False
        else:
            print(f"   ❌ Unexpected status code: {response.status_code}")
            return False
            
    except Exception as e:
        print(f"   ❌ ERROR: {str(e)}")
        return False

def main():
    """Run all universal endpoint tests"""
    print("🚀 Starting Universal Endpoint Tests")
    print(f"Base URL: {BASE_URL}")
    
    # Test valid tools
    valid_tests = [
        ("pan", {"id_number": TEST_PAN}, "Basic PAN Verification"),
        ("pan_comprehensive", {"id_number": TEST_PAN}, "Comprehensive PAN Verification"),
        ("pan_kra", {"id_number": TEST_PAN}, "KRA PAN Verification"),
    ]
    
    passed = 0
    total = len(valid_tests)
    
    # Test valid cases
    for tool, params, description in valid_tests:
        success = test_universal_endpoint(tool, params, description)
        if success:
            passed += 1
        time.sleep(1)
    
    # Test error cases
    error_passed, error_total = test_universal_error_cases()
    passed += error_passed
    total += error_total
    
    # Test available tools
    if test_available_tools():
        passed += 1
    total += 1
    
    print(f"\n{'='*60}")
    print(f"📊 Universal Endpoint Test Results: {passed}/{total} tests passed")
    print('='*60)
    
    if passed == total:
        print("🎉 All universal endpoint tests passed!")
        print("✅ Ready for custom GPT integration!")
        return 0
    else:
        print("❌ Some tests failed. Check the implementation.")
        return 1

if __name__ == "__main__":
    exit(main())
