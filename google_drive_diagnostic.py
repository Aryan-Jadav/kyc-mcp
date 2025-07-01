#!/usr/bin/env python3
"""
Complete diagnostic script for Google Drive and Sheets integration
"""

import json
import os
import sys
import traceback
from datetime import datetime

def test_google_apis():
    """Test Google APIs step by step"""
    print("🔍 Starting Google APIs Diagnostic Test")
    print("=" * 50)
    
    # Step 1: Check credentials file
    print("\n📋 Step 1: Checking credentials file...")
    creds_path = os.getenv("GOOGLE_CREDENTIALS_PATH", "credentials.json")
    print(f"Looking for credentials at: {creds_path}")
    
    if not os.path.exists(creds_path):
        print(f"❌ Credentials file not found at {creds_path}")
        return False
    
    print("✅ Credentials file found")
    
    try:
        with open(creds_path, 'r') as f:
            creds_data = json.load(f)
        
        # Check required fields
        required_fields = ['type', 'project_id', 'private_key', 'client_email']
        missing_fields = [field for field in required_fields if not creds_data.get(field)]
        
        if missing_fields:
            print(f"❌ Missing required fields: {missing_fields}")
            return False
        
        print(f"✅ Credentials structure valid")
        print(f"   📧 Service account: {creds_data['client_email']}")
        print(f"   🏷️  Project ID: {creds_data['project_id']}")
        
    except Exception as e:
        print(f"❌ Error reading credentials: {e}")
        return False
    
    # Step 2: Test Google imports
    print("\n📦 Step 2: Testing Google library imports...")
    try:
        from google.oauth2.service_account import Credentials
        from googleapiclient.discovery import build
        import gspread
        print("✅ All Google libraries imported successfully")
    except ImportError as e:
        print(f"❌ Import error: {e}")
        print("Install missing packages: pip install google-api-python-client gspread")
        return False
    
    # Step 3: Test credentials loading
    print("\n🔑 Step 3: Testing credentials loading...")
    try:
        scopes = [
            'https://www.googleapis.com/auth/spreadsheets',
            'https://www.googleapis.com/auth/drive'
        ]
        
        creds = Credentials.from_service_account_file(creds_path, scopes=scopes)
        print("✅ Credentials loaded successfully")
        
        # Test gspread auth
        gc = gspread.authorize(creds)
        print("✅ gspread authorization successful")
        
    except Exception as e:
        print(f"❌ Credentials loading failed: {e}")
        print(f"Full error: {traceback.format_exc()}")
        return False
    
    # Step 4: Test Drive API
    print("\n📁 Step 4: Testing Google Drive API...")
    try:
        drive_service = build('drive', 'v3', credentials=creds)
        
        # Test basic Drive access
        about = drive_service.about().get(fields='user,storageQuota').execute()
        user_email = about.get('user', {}).get('emailAddress', 'Unknown')
        print(f"✅ Drive API connected successfully")
        print(f"   📧 Connected as: {user_email}")
        
        # Test folder creation capability
        test_folder_metadata = {
            'name': 'KYC_Test_Folder_' + datetime.now().strftime('%Y%m%d_%H%M%S'),
            'mimeType': 'application/vnd.google-apps.folder'
        }
        
        test_folder = drive_service.files().create(body=test_folder_metadata).execute()
        folder_id = test_folder.get('id')
        print(f"✅ Test folder created: {folder_id}")
        
        # Clean up test folder
        drive_service.files().delete(fileId=folder_id).execute()
        print("✅ Test folder cleaned up")
        
    except Exception as e:
        print(f"❌ Drive API test failed: {e}")
        if "403" in str(e):
            print("   💡 This might be a permissions issue. Check:")
            print("   1. Google Drive API is enabled in Google Cloud Console")
            print("   2. Service account has proper IAM roles")
        return False
    
    # Step 5: Test Sheets API
    print("\n📊 Step 5: Testing Google Sheets API...")
    try:
        sheets_service = build('sheets', 'v4', credentials=creds)
        
        # Test with gspread
        test_sheet_name = 'KYC_Test_Sheet_' + datetime.now().strftime('%Y%m%d_%H%M%S')
        test_sheet = gc.create(test_sheet_name)
        print(f"✅ Test spreadsheet created: {test_sheet.id}")
        
        # Test writing data
        worksheet = test_sheet.sheet1
        worksheet.update('A1', [['Test', 'Data']])
        print("✅ Test data written to sheet")
        
        # Test reading data
        values = worksheet.get_all_values()
        print(f"✅ Test data read from sheet: {values}")
        
        # Clean up test sheet
        gc.del_spreadsheet(test_sheet.id)
        print("✅ Test spreadsheet cleaned up")
        
    except Exception as e:
        print(f"❌ Sheets API test failed: {e}")
        if "403" in str(e):
            print("   💡 This might be a permissions issue. Check:")
            print("   1. Google Sheets API is enabled in Google Cloud Console")
            print("   2. Service account has proper IAM roles")
        return False
    
    # Step 6: Test KYC application imports
    print("\n🔧 Step 6: Testing KYC application imports...")
    try:
        sys.path.insert(0, '/app')  # Add app directory to path
        
        from google_config import (
            GOOGLE_CREDENTIALS_PATH, GOOGLE_DRIVE_ENABLED, GOOGLE_SHEETS_ENABLED,
            KYC_DRIVE_FOLDER_NAME, STORAGE_TYPE
        )
        
        print("✅ Google config imported successfully")
        print(f"   📁 Drive enabled: {GOOGLE_DRIVE_ENABLED}")
        print(f"   📊 Sheets enabled: {GOOGLE_SHEETS_ENABLED}")
        print(f"   💾 Storage type: {STORAGE_TYPE}")
        print(f"   📂 Drive folder: {KYC_DRIVE_FOLDER_NAME}")
        
        from google_drive_storage import google_drive_storage
        print("✅ Google Drive storage imported")
        print(f"   🔧 Initialized: {getattr(google_drive_storage, 'initialized', False)}")
        
        from google_sheets_database import google_sheets_db_manager
        print("✅ Google Sheets database imported")
        print(f"   🔧 Initialized: {getattr(google_sheets_db_manager, 'initialized', False)}")
        
    except Exception as e:
        print(f"❌ KYC imports failed: {e}")
        print(f"Full error: {traceback.format_exc()}")
        return False
    
    print("\n🎉 All tests passed! Google Drive and Sheets should work properly.")
    return True

def test_manual_initialization():
    """Test manual initialization of Google services"""
    print("\n🔧 Testing manual initialization...")
    
    try:
        sys.path.insert(0, '/app')
        
        # Test Google Drive initialization
        from google_drive_storage import google_drive_storage
        print("📁 Initializing Google Drive storage...")
        
        import asyncio
        
        async def init_drive():
            await google_drive_storage.initialize()
            print(f"✅ Google Drive initialized: {google_drive_storage.initialized}")
            
            if google_drive_storage.initialized:
                folder_ids = getattr(google_drive_storage, 'folder_ids', {})
                print(f"📂 Folders created: {list(folder_ids.keys())}")
                
                # Test statistics
                stats = await google_drive_storage.get_storage_statistics()
                print(f"📊 Storage stats: {stats}")
        
        asyncio.run(init_drive())
        
        # Test Google Sheets initialization
        from google_sheets_database import google_sheets_db_manager
        print("\n📊 Initializing Google Sheets database...")
        
        async def init_sheets():
            await google_sheets_db_manager.initialize()
            print(f"✅ Google Sheets initialized: {google_sheets_db_manager.initialized}")
            
            if google_sheets_db_manager.initialized:
                spreadsheet_name = getattr(google_sheets_db_manager, 'spreadsheet_name', 'Unknown')
                print(f"📋 Spreadsheet: {spreadsheet_name}")
                
                if hasattr(google_sheets_db_manager, 'spreadsheet') and google_sheets_db_manager.spreadsheet:
                    print(f"🆔 Spreadsheet ID: {google_sheets_db_manager.spreadsheet.id}")
        
        asyncio.run(init_sheets())
        
        return True
        
    except Exception as e:
        print(f"❌ Manual initialization failed: {e}")
        print(f"Full error: {traceback.format_exc()}")
        return False

if __name__ == "__main__":
    print("🚀 Google Drive & Sheets Diagnostic Tool")
    print("=" * 60)
    
    # Run basic API tests
    api_success = test_google_apis()
    
    if api_success:
        print("\n" + "=" * 60)
        # Run manual initialization tests
        init_success = test_manual_initialization()
        
        if init_success:
            print("\n✅ ALL TESTS PASSED!")
            print("Google Drive should be working properly in your KYC application.")
        else:
            print("\n⚠️ API tests passed but initialization failed.")
            print("Check the KYC application configuration.")
    else:
        print("\n❌ BASIC API TESTS FAILED!")
        print("Fix the Google API issues before proceeding.")
    
    print("\n" + "=" * 60)
    print("🔧 Troubleshooting Guide:")
    print("1. Ensure Google Drive API and Sheets API are enabled")
    print("2. Check service account permissions in Google Cloud Console")
    print("3. Verify credentials.json is valid and has all required fields")
    print("4. Make sure the service account has the right IAM roles:")
    print("   - Service Account Token Creator")
    print("   - Editor (or custom role with drive/sheets permissions)")
    print("5. If using shared drives, grant access to the service account")