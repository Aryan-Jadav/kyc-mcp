#!/usr/bin/env python3
"""
Test script for Ultra Robust Google Sheets Fix
Tests the enhanced error handling and header/data validation
"""

import asyncio
import logging
import os
import sys
from datetime import datetime

# Add current directory to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from universal_google_sheets import UniversalGoogleSheetsDatabase

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger("test-ultra-robust")

async def test_ultra_robust_storage():
    """Test the ultra-robust storage system"""
    
    logger.info("🧪 Starting Ultra Robust Google Sheets Test")
    
    try:
        # Initialize database
        db = UniversalGoogleSheetsDatabase()
        await db.initialize()
        
        logger.info("✅ Database initialized successfully")
        
        # Test data that previously caused the error
        test_verification_data = {
            'id_number': 'CTIPJ7546R',
            'pan_number': 'CTIPJ7546R',
            'full_name': 'Test User',
            'first_name': 'Test',
            'last_name': 'User',
            'father_name': 'Test Father',
            'gender': 'Male',
            'dob': '1990-01-01',
            'category': 'General',
            'is_minor': 'No',
            'phone_number': '9876543210',
            'email': 'test@example.com',
            'address_data': 'Test Address',
            'verification_status': 'Success',
            'confidence_score': '95.5',
            'extra_data': 'Additional test data',
            'new_field_1': 'This is a new field that should trigger header expansion',
            'new_field_2': 'Another new field for testing'
        }
        
        # Test API usage data
        api_usage = {
            'request_type': 'pan_verification',
            'api_endpoint': '/pan/pan',
            'request_data': {'id_number': 'CTIPJ7546R'},
            'status_code': 200,
            'success': True,
            'error_message': '',
            'processing_time_ms': 1500,
            'request_size_bytes': 100,
            'response_size_bytes': 500,
            'user_agent': 'Test Agent',
            'ip_address': '127.0.0.1'
        }
        
        # Test API response data
        api_response = {
            'success': True,
            'status_code': 200,
            'data': test_verification_data,
            'timestamp': datetime.utcnow().isoformat(),
            'processing_time_ms': 1500
        }
        
        logger.info("📝 Testing storage with comprehensive data...")
        
        # Test the storage function
        result = await db.store_verification_data(
            verification_data=test_verification_data,
            api_endpoint='/pan/pan',
            verification_type='pan_verification',
            api_usage=api_usage,
            api_response=api_response
        )
        
        if result:
            logger.info(f"✅ Storage successful! Record ID: {result.get('id')}")
            logger.info(f"✅ Verification type: {result.get('verification_type')}")
            
            # Test searching for the record
            logger.info("🔍 Testing record search...")
            search_results = await db.search_record('pan', 'CTIPJ7546R')
            
            if search_results:
                logger.info(f"✅ Found {len(search_results)} records in search")
                for record in search_results:
                    logger.info(f"   Record ID: {record.get('ID')}")
                    logger.info(f"   Name: {record.get('Full_Name')}")
                    logger.info(f"   Status: {record.get('Verification_Status')}")
            else:
                logger.warning("⚠️ No records found in search")
            
        else:
            logger.error("❌ Storage failed!")
            return False
        
        # Test with minimal data to ensure robustness
        logger.info("📝 Testing storage with minimal data...")
        
        minimal_data = {
            'id_number': 'TEST123456',
            'pan_number': 'TEST123456',
            'full_name': 'Minimal Test'
        }
        
        minimal_result = await db.store_verification_data(
            verification_data=minimal_data,
            api_endpoint='/pan/pan',
            verification_type='pan_verification'
        )
        
        if minimal_result:
            logger.info(f"✅ Minimal storage successful! Record ID: {minimal_result.get('id')}")
        else:
            logger.error("❌ Minimal storage failed!")
            return False
        
        # Test statistics
        logger.info("📊 Testing statistics...")
        stats = await db.get_statistics()
        if stats:
            logger.info(f"✅ Statistics retrieved: {stats.get('total_records', 0)} total records")
        
        logger.info("🎉 All tests completed successfully!")
        return True
        
    except Exception as e:
        logger.error(f"❌ Test failed with error: {str(e)}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        return False
    
    finally:
        # Cleanup
        if 'db' in locals():
            await db.close()

async def test_header_expansion():
    """Test header expansion functionality"""
    
    logger.info("🧪 Testing header expansion...")
    
    try:
        db = UniversalGoogleSheetsDatabase()
        await db.initialize()
        
        # Test with fields that should trigger header expansion
        test_data = {
            'id_number': 'EXPAND123',
            'pan_number': 'EXPAND123',
            'full_name': 'Header Expansion Test',
            'completely_new_field_1': 'This should trigger expansion',
            'another_new_field_2': 'This should also trigger expansion',
            'third_new_field_3': 'And this one too'
        }
        
        result = await db.store_verification_data(
            verification_data=test_data,
            api_endpoint='/pan/pan',
            verification_type='pan_verification'
        )
        
        if result:
            logger.info("✅ Header expansion test successful!")
            return True
        else:
            logger.error("❌ Header expansion test failed!")
            return False
            
    except Exception as e:
        logger.error(f"❌ Header expansion test failed: {str(e)}")
        return False
    
    finally:
        if 'db' in locals():
            await db.close()

async def test_error_recovery():
    """Test error recovery mechanisms"""
    
    logger.info("🧪 Testing error recovery...")
    
    try:
        db = UniversalGoogleSheetsDatabase()
        await db.initialize()
        
        # Test with malformed data
        malformed_data = {
            'id_number': 'ERROR123',
            'pan_number': 'ERROR123',
            'full_name': 'Error Recovery Test',
            # Add some problematic data
            'problematic_field': None,
            'empty_field': '',
            'very_long_field': 'x' * 10000  # Very long field
        }
        
        result = await db.store_verification_data(
            verification_data=malformed_data,
            api_endpoint='/pan/pan',
            verification_type='pan_verification'
        )
        
        if result:
            logger.info("✅ Error recovery test successful!")
            return True
        else:
            logger.error("❌ Error recovery test failed!")
            return False
            
    except Exception as e:
        logger.error(f"❌ Error recovery test failed: {str(e)}")
        return False
    
    finally:
        if 'db' in locals():
            await db.close()

async def main():
    """Run all tests"""
    
    logger.info("🚀 Starting Ultra Robust Google Sheets Test Suite")
    
    tests = [
        ("Ultra Robust Storage", test_ultra_robust_storage),
        ("Header Expansion", test_header_expansion),
        ("Error Recovery", test_error_recovery)
    ]
    
    results = {}
    
    for test_name, test_func in tests:
        logger.info(f"\n{'='*50}")
        logger.info(f"Running: {test_name}")
        logger.info(f"{'='*50}")
        
        try:
            result = await test_func()
            results[test_name] = result
            logger.info(f"✅ {test_name}: {'PASSED' if result else 'FAILED'}")
        except Exception as e:
            logger.error(f"❌ {test_name}: ERROR - {str(e)}")
            results[test_name] = False
    
    # Summary
    logger.info(f"\n{'='*50}")
    logger.info("TEST SUMMARY")
    logger.info(f"{'='*50}")
    
    passed = sum(1 for result in results.values() if result)
    total = len(results)
    
    for test_name, result in results.items():
        status = "✅ PASSED" if result else "❌ FAILED"
        logger.info(f"{test_name}: {status}")
    
    logger.info(f"\nOverall: {passed}/{total} tests passed")
    
    if passed == total:
        logger.info("🎉 ALL TESTS PASSED! The ultra-robust fix is working correctly.")
    else:
        logger.error(f"⚠️ {total - passed} tests failed. Please review the errors above.")
    
    return passed == total

if __name__ == "__main__":
    # Check if credentials are available
    if not os.path.exists("credentials.json"):
        logger.error("❌ credentials.json not found. Please ensure Google credentials are available.")
        sys.exit(1)
    
    # Run tests
    success = asyncio.run(main())
    
    if success:
        logger.info("🎉 Test suite completed successfully!")
        sys.exit(0)
    else:
        logger.error("❌ Test suite failed!")
        sys.exit(1) 