#!/usr/bin/env python3
"""
Test script for KYC API endpoints
This script tests the deployed KYC API to ensure all endpoints are working correctly.
"""

import requests
import json
import sys
import time

# Configuration
BASE_URL = "http://139.59.70.153:8000"
TEST_PAN = "ABCDE1234F"  # Test PAN number

def test_endpoint(url, method="GET", data=None, description=""):
    """Test a single endpoint"""
    print(f"\n🧪 Testing: {description}")
    print(f"   URL: {url}")
    
    try:
        if method == "GET":
            response = requests.get(url, timeout=30)
        elif method == "POST":
            response = requests.post(url, json=data, timeout=30)
        
        print(f"   Status: {response.status_code}")
        
        if response.status_code == 200:
            print("   ✅ SUCCESS")
            try:
                result = response.json()
                print(f"   Response: {json.dumps(result, indent=2)[:200]}...")
            except:
                print(f"   Response: {response.text[:200]}...")
        else:
            print("   ❌ FAILED")
            print(f"   Error: {response.text}")
            
        return response.status_code == 200
        
    except requests.exceptions.RequestException as e:
        print(f"   ❌ NETWORK ERROR: {str(e)}")
        return False

def main():
    """Run all API tests"""
    print("🚀 Starting KYC API Tests")
    print(f"Base URL: {BASE_URL}")
    
    tests = [
        {
            "url": f"{BASE_URL}/health",
            "method": "GET",
            "description": "Health Check"
        },
        {
            "url": f"{BASE_URL}/api/status",
            "method": "GET", 
            "description": "API Status Check"
        },
        {
            "url": f"{BASE_URL}/docs",
            "method": "GET",
            "description": "API Documentation"
        },
        {
            "url": f"{BASE_URL}/api/verify/pan/basic",
            "method": "POST",
            "data": {"id_number": TEST_PAN},
            "description": "Basic PAN Verification"
        },
        {
            "url": f"{BASE_URL}/api/verify/pan/comprehensive",
            "method": "POST",
            "data": {"id_number": TEST_PAN},
            "description": "Comprehensive PAN Verification"
        }
    ]
    
    passed = 0
    total = len(tests)
    
    for test in tests:
        success = test_endpoint(
            test["url"], 
            test.get("method", "GET"),
            test.get("data"),
            test["description"]
        )
        if success:
            passed += 1
        time.sleep(1)  # Small delay between tests
    
    print(f"\n📊 Test Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All tests passed! The API is working correctly.")
        return 0
    else:
        print("❌ Some tests failed. Please check the server logs.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
