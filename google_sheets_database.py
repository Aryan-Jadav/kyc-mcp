"""Fixed Google Sheets Database Manager for KYC Data Storage"""

import json
import logging
from datetime import datetime
from typing import Optional, Dict, Any, List, Tuple
import gspread
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
import io
import os
import asyncio
from concurrent.futures import ThreadPoolExecutor
from functools import partial

from config_db import DATABASE_ENABLED

logger = logging.getLogger("kyc-google-sheets")

class GoogleSheetsKYCDatabase:
    """Google Sheets database manager for KYC data storage (refactored for 2 main sheets)"""
    
    def __init__(self):
        self.gc = None
        self.drive_service = None
        self.sheets_service = None
        self.spreadsheet = None
        self.initialized = False
        self.executor = ThreadPoolExecutor(max_workers=5)
        
        # Configuration
        self.spreadsheet_name = os.getenv("KYC_SPREADSHEET_NAME", "KYC_Verification_Database")
        self.folder_id = os.getenv("GOOGLE_DRIVE_FOLDER_ID")
        
        # Two optimized worksheets for efficient data storage
        self.worksheets = {
            'api_usage_logs': 'API_Usage_Logs',
            'api_data': 'API_Data',
        }
    
    async def initialize(self):
        """Initialize Google Sheets and Drive connections"""
        if not DATABASE_ENABLED:
            logger.info("Database storage is disabled")
            return
            
        try:
            # Load credentials
            creds_path = os.getenv("GOOGLE_CREDENTIALS_PATH", "credentials.json")
            if not os.path.exists(creds_path):
                logger.error(f"Google credentials file not found: {creds_path}")
                raise FileNotFoundError(f"Google credentials file not found: {creds_path}")
            
            # Set up scopes
            scopes = [
                'https://www.googleapis.com/auth/spreadsheets',
                'https://www.googleapis.com/auth/drive'
            ]
            
            # Initialize credentials
            creds = Credentials.from_service_account_file(creds_path, scopes=scopes)
            
            # Initialize gspread client
            self.gc = gspread.authorize(creds)
            
            # Initialize Google Drive and Sheets services
            self.drive_service = build('drive', 'v3', credentials=creds)
            self.sheets_service = build('sheets', 'v4', credentials=creds)
            
            # Initialize or find spreadsheet
            await self._initialize_spreadsheet()
            
            self.initialized = True
            logger.info("Google Sheets database initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize Google Sheets database: {str(e)}")
            raise
    
    async def _run_sync(self, func, *args, **kwargs):
        """Run synchronous function in thread pool - FIXED VERSION"""
        loop = asyncio.get_event_loop()
        # Use partial to properly handle args and kwargs
        if kwargs:
            func_with_args = partial(func, *args, **kwargs)
            return await loop.run_in_executor(self.executor, func_with_args)
        else:
            return await loop.run_in_executor(self.executor, func, *args)
    
    async def _initialize_spreadsheet(self):
        """Initialize or find the KYC spreadsheet"""
        try:
            # Try to find existing spreadsheet
            try:
                self.spreadsheet = await self._run_sync(self.gc.open, self.spreadsheet_name)
                logger.info(f"Found existing spreadsheet: {self.spreadsheet_name}")
                
                # Always ensure spreadsheet is in the correct folder
                if self.folder_id:
                    await self._ensure_spreadsheet_in_folder()
                    
            except gspread.SpreadsheetNotFound:
                # Create new spreadsheet
                self.spreadsheet = await self._run_sync(self.gc.create, self.spreadsheet_name)
                logger.info(f"Created new spreadsheet: {self.spreadsheet_name}")
                
                # Move to specific folder if specified
                if self.folder_id:
                    await self._move_to_folder()
            
            # Initialize worksheets
            await self._initialize_worksheets()
            
        except Exception as e:
            logger.error(f"Error initializing spreadsheet: {str(e)}")
            raise
    
    async def _move_to_folder(self):
        """Move spreadsheet to Reports folder inside the target Drive folder"""
        try:
            file_id = self.spreadsheet.id
            
            # Get or create Reports folder
            reports_folder_id = await self._get_or_create_reports_folder()
            
            # Remove from root and add to Reports folder
            def move_file():
                return self.drive_service.files().update(
                    fileId=file_id,
                    addParents=reports_folder_id,
                    removeParents='root',
                    fields='id, parents'
                ).execute()
            
            await self._run_sync(move_file)
            logger.info(f"Moved spreadsheet to Reports folder: {reports_folder_id}")
        except Exception as e:
            logger.warning(f"Could not move spreadsheet to Reports folder: {str(e)}")
    
    async def _ensure_spreadsheet_in_folder(self):
        """Ensure spreadsheet is in the correct folder (Reports subfolder)"""
        try:
            file_id = self.spreadsheet.id
            
            # First, ensure the Reports folder exists in the target folder
            reports_folder_id = await self._get_or_create_reports_folder()
            
            # Check current folder location
            def get_file_info():
                return self.drive_service.files().get(
                    fileId=file_id,
                    fields='id,parents'
                ).execute()
            
            file_info = await self._run_sync(get_file_info)
            current_parents = file_info.get('parents', [])
            
            # If spreadsheet is not in the Reports folder, move it
            if reports_folder_id not in current_parents:
                logger.info(f"Moving spreadsheet to Reports folder: {reports_folder_id}")
                
                # Remove from current location and add to Reports folder
                def move_file():
                    return self.drive_service.files().update(
                        fileId=file_id,
                        addParents=reports_folder_id,
                        removeParents=','.join(current_parents),
                        fields='id, parents'
                    ).execute()
                
                await self._run_sync(move_file)
                logger.info(f"✅ Spreadsheet moved to Reports folder: {reports_folder_id}")
            else:
                logger.info(f"✅ Spreadsheet already in Reports folder: {reports_folder_id}")
                
        except Exception as e:
            logger.warning(f"Could not ensure spreadsheet is in Reports folder: {str(e)}")
    
    async def _get_or_create_reports_folder(self):
        """Get or create Reports folder inside the target folder"""
        try:
            # Search for existing Reports folder in the target folder
            def search_reports_folder():
                query = f"name='Reports' and mimeType='application/vnd.google-apps.folder' and '{self.folder_id}' in parents and trashed=false"
                results = self.drive_service.files().list(q=query, fields='files(id,name)').execute()
                return results.get('files', [])
            
            existing_folders = await self._run_sync(search_reports_folder)
            
            if existing_folders:
                return existing_folders[0]['id']
            
            # Create Reports folder if it doesn't exist
            def create_reports_folder():
                folder_metadata = {
                    'name': 'Reports',
                    'mimeType': 'application/vnd.google-apps.folder',
                    'parents': [self.folder_id],
                    'description': 'KYC Reports and Data Storage'
                }
                folder = self.drive_service.files().create(body=folder_metadata, fields='id,name').execute()
                return folder
            
            folder = await self._run_sync(create_reports_folder)
            logger.info(f"✅ Created Reports folder: {folder['id']}")
            return folder['id']
            
        except Exception as e:
            logger.error(f"Error creating Reports folder: {str(e)}")
            # Fallback to main folder
            return self.folder_id
    
    async def _initialize_worksheets(self):
        """Initialize optimized worksheets with comprehensive headers"""
        try:
            # API Usage Logs worksheet - for tracking all API requests
            await self._ensure_worksheet_exists('api_usage_logs', [
                'ID', 'Request_Type', 'API_Endpoint', 'Request_Data', 'Status_Code', 'Success',
                'Error_Message', 'Processing_Time_MS', 'Request_Size_Bytes', 'Response_Size_Bytes',
                'User_Agent', 'IP_Address', 'Timestamp', 'Response_ID'
            ])
            
            # API Data worksheet - combined structured and raw data for efficiency
            await self._ensure_worksheet_exists('api_data', [
                'ID', 'Record_ID', 'API_Endpoint', 'Request_Data_JSON', 'Response_Data_JSON',
                'Status_Code', 'Success', 'Error_Message', 'Processing_Time_MS', 'Timestamp',
                'Verification_Type', 'Document_Number', 'Person_Name', 'Verification_Status',
                'Confidence_Score', 'Processing_Time', 'Key_Field_1', 'Key_Field_2', 'Key_Field_3'
            ])
            
        except Exception as e:
            logger.error(f"Error initializing worksheets: {str(e)}")
            raise
    
    async def _ensure_worksheet_exists(self, worksheet_key: str, headers: List[str]):
        """Ensure worksheet exists with proper headers - FIXED VERSION"""
        worksheet_name = self.worksheets[worksheet_key]
        
        try:
            # Try to get existing worksheet
            def get_worksheet():
                return self.spreadsheet.worksheet(worksheet_name)
            
            try:
                worksheet = await self._run_sync(get_worksheet)
                
                # Check if headers are set
                def get_headers():
                    return worksheet.row_values(1)
                
                existing_headers = await self._run_sync(get_headers)
                if not existing_headers or existing_headers != headers:
                    # Update headers
                    def update_headers():
                        return worksheet.update('A1', [headers])
                    
                    await self._run_sync(update_headers)
                    logger.info(f"Updated headers for worksheet: {worksheet_name}")
                    
            except gspread.WorksheetNotFound:
                # Create new worksheet
                def add_worksheet():
                    return self.spreadsheet.add_worksheet(
                        title=worksheet_name,
                        rows=1000,
                        cols=len(headers)
                    )
                
                worksheet = await self._run_sync(add_worksheet)
                
                # Add headers
                def add_headers():
                    return worksheet.update('A1', [headers])
                
                await self._run_sync(add_headers)
                logger.info(f"Created new worksheet: {worksheet_name}")
                
        except Exception as e:
            logger.error(f"Error ensuring worksheet exists: {str(e)}")
            raise
    
    async def close(self):
        """Close connections and cleanup"""
        if self.executor:
            self.executor.shutdown(wait=True)
        logger.info("Google Sheets database connections closed")
    
    async def store_pan_data(self, pan_data: Dict[str, Any], api_endpoint: str = None) -> Optional[Dict[str, Any]]:
        """Store PAN data in Google Sheets"""
        if not self.initialized or not DATABASE_ENABLED:
            return None
            
        try:
            pan_number = pan_data.get('pan_number')
            if not pan_number:
                logger.warning("No PAN number found in data, skipping storage")
                return None
            
            def get_worksheet():
                return self.spreadsheet.worksheet(self.worksheets['pan_records'])
            
            worksheet = await self._run_sync(get_worksheet)
            
            # Check if record exists
            existing_row = await self._find_pan_record(worksheet, pan_number)
            
            # Prepare row data
            timestamp = datetime.utcnow().isoformat()
            address_json = json.dumps(pan_data.get('address')) if pan_data.get('address') else ""
            raw_data_json = json.dumps(pan_data)
            
            row_data = [
                existing_row['row_num'] if existing_row else await self._get_next_id('pan_records'),
                pan_data.get('pan_number', ''),
                pan_data.get('full_name', ''),
                pan_data.get('first_name', ''),
                pan_data.get('middle_name', ''),
                pan_data.get('last_name', ''),
                pan_data.get('father_name', ''),
                pan_data.get('email', ''),
                pan_data.get('phone_number', ''),
                pan_data.get('gender', ''),
                pan_data.get('dob', ''),
                pan_data.get('category', ''),
                pan_data.get('is_minor', ''),
                address_json,
                pan_data.get('masked_aadhaar', ''),
                pan_data.get('aadhaar_linked', ''),
                pan_data.get('dob_verified', ''),
                pan_data.get('less_info', ''),
                raw_data_json,
                api_endpoint or '',
                existing_row['verification_count'] + 1 if existing_row else 1,
                existing_row['created_at'] if existing_row else timestamp,
                timestamp,
                timestamp
            ]
            
            if existing_row:
                # Update existing row
                def update_row():
                    return worksheet.update(f"A{existing_row['row_num']}", [row_data])
                
                await self._run_sync(update_row)
                logger.info(f"Updated existing PAN record for {pan_number}")
            else:
                # Add new row
                def append_row():
                    return worksheet.append_row(row_data)
                
                await self._run_sync(append_row)
                logger.info(f"Created new PAN record for {pan_number}")
            
            return {'id': row_data[0], 'pan_number': pan_number}
            
        except Exception as e:
            logger.error(f"Error storing PAN data: {str(e)}")
            return None
    
    async def _find_pan_record(self, worksheet, pan_number: str) -> Optional[Dict[str, Any]]:
        """Find existing PAN record"""
        try:
            def get_all_records():
                return worksheet.get_all_records()
            
            records = await self._run_sync(get_all_records)
            
            for i, record in enumerate(records, start=2):  # Start from row 2 (after headers)
                if record.get('PAN_Number') == pan_number:
                    return {
                        'row_num': i,
                        'verification_count': int(record.get('Verification_Count', 0)),
                        'created_at': record.get('Created_At', '')
                    }
            
            return None
            
        except Exception as e:
            logger.error(f"Error finding PAN record: {str(e)}")
            return None
    
    async def _get_next_id(self, worksheet_key: str) -> int:
        """Get next available ID for a worksheet"""
        try:
            def get_worksheet():
                return self.spreadsheet.worksheet(self.worksheets[worksheet_key])
            
            worksheet = await self._run_sync(get_worksheet)
            
            # Get all values in first column
            def get_col_values():
                return worksheet.col_values(1)
            
            values = await self._run_sync(get_col_values)
            
            # Find highest numeric ID
            max_id = 0
            for value in values[1:]:  # Skip header
                try:
                    if value and int(value) > max_id:
                        max_id = int(value)
                except ValueError:
                    continue
            
            return max_id + 1
            
        except Exception as e:
            logger.error(f"Error getting next ID: {str(e)}")
            return 1
    
    async def search_by_pan(self, pan_number: str) -> Optional[Dict[str, Any]]:
        """Search for record by PAN number"""
        if not self.initialized or not DATABASE_ENABLED:
            return None
            
        try:
            def get_worksheet():
                return self.spreadsheet.worksheet(self.worksheets['pan_records'])
            
            worksheet = await self._run_sync(get_worksheet)
            
            def get_all_records():
                return worksheet.get_all_records()
            
            records = await self._run_sync(get_all_records)
            
            for record in records:
                if record.get('PAN_Number') == pan_number.upper():
                    # Log search
                    await self._log_search('pan_number', pan_number, 1)
                    return self._convert_sheet_record_to_dict(record)
            
            await self._log_search('pan_number', pan_number, 0)
            return None
            
        except Exception as e:
            logger.error(f"Error searching by PAN: {str(e)}")
            return None
    
    async def search_by_name(self, name: str, exact_match: bool = False) -> List[Dict[str, Any]]:
        """Search for records by name"""
        if not self.initialized or not DATABASE_ENABLED:
            return []
            
        try:
            def get_worksheet():
                return self.spreadsheet.worksheet(self.worksheets['pan_records'])
            
            worksheet = await self._run_sync(get_worksheet)
            
            def get_all_records():
                return worksheet.get_all_records()
            
            records = await self._run_sync(get_all_records)
            matches = []
            
            for record in records:
                full_name = record.get('Full_Name', '').lower()
                first_name = record.get('First_Name', '').lower()
                last_name = record.get('Last_Name', '').lower()
                search_name = name.lower()
                
                if exact_match:
                    if search_name in [full_name, first_name, last_name]:
                        matches.append(self._convert_sheet_record_to_dict(record))
                else:
                    if (search_name in full_name or 
                        search_name in first_name or 
                        search_name in last_name):
                        matches.append(self._convert_sheet_record_to_dict(record))
            
            await self._log_search('name', name, len(matches))
            return matches
            
        except Exception as e:
            logger.error(f"Error searching by name: {str(e)}")
            return []
    
    async def search_by_phone(self, phone_number: str) -> List[Dict[str, Any]]:
        """Search for records by phone number"""
        if not self.initialized or not DATABASE_ENABLED:
            return []
            
        try:
            def get_worksheet():
                return self.spreadsheet.worksheet(self.worksheets['pan_records'])
            
            worksheet = await self._run_sync(get_worksheet)
            
            def get_all_records():
                return worksheet.get_all_records()
            
            records = await self._run_sync(get_all_records)
            matches = []
            
            for record in records:
                if record.get('Phone_Number') == phone_number:
                    matches.append(self._convert_sheet_record_to_dict(record))
            
            await self._log_search('phone_number', phone_number, len(matches))
            return matches
            
        except Exception as e:
            logger.error(f"Error searching by phone: {str(e)}")
            return []
    
    async def search_by_email(self, email: str) -> List[Dict[str, Any]]:
        """Search for records by email"""
        if not self.initialized or not DATABASE_ENABLED:
            return []
            
        try:
            def get_worksheet():
                return self.spreadsheet.worksheet(self.worksheets['pan_records'])
            
            worksheet = await self._run_sync(get_worksheet)
            
            def get_all_records():
                return worksheet.get_all_records()
            
            records = await self._run_sync(get_all_records)
            matches = []
            
            for record in records:
                record_email = record.get('Email', '').lower()
                if email.lower() in record_email:
                    matches.append(self._convert_sheet_record_to_dict(record))
            
            await self._log_search('email', email, len(matches))
            return matches
            
        except Exception as e:
            logger.error(f"Error searching by email: {str(e)}")
            return []
    
    async def get_all_records(self, limit: int = None, offset: int = 0) -> List[Dict[str, Any]]:
        """Get all records with pagination"""
        if not self.initialized or not DATABASE_ENABLED:
            return []
            
        try:
            def get_worksheet():
                return self.spreadsheet.worksheet(self.worksheets['pan_records'])
            
            worksheet = await self._run_sync(get_worksheet)
            
            def get_all_records():
                return worksheet.get_all_records()
            
            records = await self._run_sync(get_all_records)
            
            # Sort by Created_At descending (most recent first)
            sorted_records = sorted(
                records, 
                key=lambda x: x.get('Created_At', ''), 
                reverse=True
            )
            
            # Apply pagination
            end_index = offset + limit if limit else len(sorted_records)
            paginated_records = sorted_records[offset:end_index]
            
            return [self._convert_sheet_record_to_dict(record) for record in paginated_records]
            
        except Exception as e:
            logger.error(f"Error getting all records: {str(e)}")
            return []
    
    async def get_statistics(self) -> Dict[str, Any]:
        """Get database statistics"""
        if not self.initialized or not DATABASE_ENABLED:
            return {}
            
        try:
            def get_worksheet():
                return self.spreadsheet.worksheet(self.worksheets['pan_records'])
            
            worksheet = await self._run_sync(get_worksheet)
            
            def get_all_records():
                return worksheet.get_all_records()
            
            records = await self._run_sync(get_all_records)
            total_records = len(records)
            
            # Count records created today
            today = datetime.utcnow().date().isoformat()
            today_records = sum(
                1 for record in records 
                if record.get('Created_At', '').startswith(today)
            )
            
            # Get most recent record
            most_recent = None
            if records:
                sorted_records = sorted(
                    records, 
                    key=lambda x: x.get('Created_At', ''), 
                    reverse=True
                )
                most_recent = sorted_records[0].get('Created_At')
            
            return {
                'total_records': total_records,
                'records_today': today_records,
                'most_recent_record': most_recent,
                'database_enabled': DATABASE_ENABLED,
                'storage_type': 'Google Sheets',
                'spreadsheet_name': self.spreadsheet_name,
                'spreadsheet_id': self.spreadsheet.id if self.spreadsheet else None
            }
            
        except Exception as e:
            logger.error(f"Error getting statistics: {str(e)}")
            return {}
    
    async def _log_search(self, search_type: str, query: str, results_count: int):
        """Log search operation"""
        try:
            def get_worksheet():
                return self.spreadsheet.worksheet(self.worksheets['search_history'])
            
            worksheet = await self._run_sync(get_worksheet)
            
            search_id = await self._get_next_id('search_history')
            timestamp = datetime.utcnow().isoformat()
            
            row_data = [
                search_id,
                search_type,
                query,
                results_count,
                timestamp
            ]
            
            def append_row():
                return worksheet.append_row(row_data)
            
            await self._run_sync(append_row)
            
        except Exception as e:
            logger.warning(f"Failed to log search: {str(e)}")
    
    async def store_api_response(self, record_id: str, api_endpoint: str, request_data: Dict[str, Any], 
                               response_data: Dict[str, Any], status_code: int, success: bool, 
                               error_message: str = None, processing_time_ms: int = 0) -> Optional[Dict[str, Any]]:
        """Store API response in Google Sheets with structured data"""
        if not self.initialized or not DATABASE_ENABLED:
            return None
            
        try:
            def get_worksheet():
                return self.spreadsheet.worksheet(self.worksheets['api_data'])
            
            worksheet = await self._run_sync(get_worksheet)
            
            response_id = await self._get_next_id('api_data')
            timestamp = datetime.utcnow().isoformat()
            
            # Extract key fields from response data for structured storage
            extracted_data = self._extract_key_response_fields(response_data)
            
            # Store only essential data as structured fields, keep full data as JSON
            row_data = [
                response_id,
                record_id,
                api_endpoint,
                json.dumps(request_data),  # Keep request as JSON
                json.dumps(response_data),  # Keep full response as JSON
                status_code,
                'true' if success else 'false',
                error_message or '',
                processing_time_ms,
                timestamp,
                # Add structured fields for better querying
                extracted_data.get('verification_type', ''),
                extracted_data.get('document_number', ''),
                extracted_data.get('person_name', ''),
                extracted_data.get('verification_status', ''),
                extracted_data.get('confidence_score', ''),
                extracted_data.get('processing_time', '')
            ]
            
            def append_row():
                return worksheet.append_row(row_data)
            
            await self._run_sync(append_row)
            logger.info(f"✅ Complete API response stored in Google Sheets: {response_id}")
            
            return {'id': response_id, 'timestamp': timestamp}
            
        except Exception as e:
            logger.error(f"Error storing API response: {str(e)}")
            return None
    
    def _extract_key_response_fields(self, response_data: Dict[str, Any]) -> Dict[str, Any]:
        """Extract key fields from response data for structured storage - Enhanced for 60+ endpoints"""
        try:
            extracted = {}
            
            # Extract common KYC fields
            if isinstance(response_data, dict):
                # Document numbers (PAN, Aadhaar, etc.) - Enhanced for all endpoints
                if 'pan_number' in response_data:
                    extracted['key1'] = response_data.get('pan_number', '')
                    extracted['verification_type'] = 'pan_verification'
                elif 'aadhaar_number' in response_data:
                    extracted['key1'] = response_data.get('aadhaar_number', '')
                    extracted['verification_type'] = 'aadhaar_verification'
                elif 'id_number' in response_data:
                    extracted['key1'] = response_data.get('id_number', '')
                    extracted['verification_type'] = 'document_verification'
                elif 'gstin' in response_data:
                    extracted['key1'] = response_data.get('gstin', '')
                    extracted['verification_type'] = 'gstin_verification'
                elif 'voter_id' in response_data:
                    extracted['key1'] = response_data.get('voter_id', '')
                    extracted['verification_type'] = 'voter_verification'
                elif 'driving_license' in response_data:
                    extracted['key1'] = response_data.get('driving_license', '')
                    extracted['verification_type'] = 'license_verification'
                elif 'passport_number' in response_data:
                    extracted['key1'] = response_data.get('passport_number', '')
                    extracted['verification_type'] = 'passport_verification'
                elif 'bank_account' in response_data:
                    extracted['key1'] = response_data.get('bank_account', '')
                    extracted['verification_type'] = 'bank_verification'
                elif 'tan_number' in response_data:
                    extracted['key1'] = response_data.get('tan_number', '')
                    extracted['verification_type'] = 'tan_verification'
                elif 'upi_id' in response_data:
                    extracted['key1'] = response_data.get('upi_id', '')
                    extracted['verification_type'] = 'upi_verification'
                elif 'mobile_number' in response_data:
                    extracted['key1'] = response_data.get('mobile_number', '')
                    extracted['verification_type'] = 'mobile_verification'
                elif 'email' in response_data:
                    extracted['key1'] = response_data.get('email', '')
                    extracted['verification_type'] = 'email_verification'
                elif 'company_name' in response_data:
                    extracted['key1'] = response_data.get('company_name', '')
                    extracted['verification_type'] = 'company_verification'
                elif 'cin' in response_data:
                    extracted['key1'] = response_data.get('cin', '')
                    extracted['verification_type'] = 'cin_verification'
                elif 'din' in response_data:
                    extracted['key1'] = response_data.get('din', '')
                    extracted['verification_type'] = 'din_verification'
                elif 'rc_number' in response_data:
                    extracted['key1'] = response_data.get('rc_number', '')
                    extracted['verification_type'] = 'rc_verification'
                elif 'uan' in response_data:
                    extracted['key1'] = response_data.get('uan', '')
                    extracted['verification_type'] = 'uan_verification'
                elif 'lei_code' in response_data:
                    extracted['key1'] = response_data.get('lei_code', '')
                    extracted['verification_type'] = 'lei_verification'
                elif 'esic_number' in response_data:
                    extracted['key1'] = response_data.get('esic_number', '')
                    extracted['verification_type'] = 'esic_verification'
                elif 'electricity_bill_number' in response_data:
                    extracted['key1'] = response_data.get('electricity_bill_number', '')
                    extracted['verification_type'] = 'electricity_verification'
                elif 'cnr_number' in response_data:
                    extracted['key1'] = response_data.get('cnr_number', '')
                    extracted['verification_type'] = 'court_verification'
                elif 'case_number' in response_data:
                    extracted['key1'] = response_data.get('case_number', '')
                    extracted['verification_type'] = 'court_verification'
                elif 'qr_text' in response_data:
                    extracted['key1'] = response_data.get('qr_text', '')
                    extracted['verification_type'] = 'qr_verification'
                elif 'file_path' in response_data:
                    extracted['key1'] = response_data.get('file_path', '')
                    extracted['verification_type'] = 'ocr_verification'
                elif 'image_path' in response_data:
                    extracted['key1'] = response_data.get('image_path', '')
                    extracted['verification_type'] = 'face_verification'
                else:
                    # Try to find any ID-like field
                    id_fields = ['id', 'number', 'code', 'reference', 'tracking_id', 'request_id']
                    for field in id_fields:
                        if field in response_data:
                            extracted['key1'] = str(response_data.get(field, ''))
                            extracted['verification_type'] = 'general_verification'
                            break
                    else:
                        extracted['key1'] = ''
                        extracted['verification_type'] = 'general_verification'
                
                # Person details - Enhanced for all endpoints
                if 'full_name' in response_data:
                    extracted['key2'] = response_data.get('full_name', '')
                elif 'name' in response_data:
                    extracted['key2'] = response_data.get('name', '')
                elif 'person_name' in response_data:
                    extracted['key2'] = response_data.get('person_name', '')
                elif 'applicant_name' in response_data:
                    extracted['key2'] = response_data.get('applicant_name', '')
                elif 'customer_name' in response_data:
                    extracted['key2'] = response_data.get('customer_name', '')
                elif 'director_name' in response_data:
                    extracted['key2'] = response_data.get('director_name', '')
                elif 'owner_name' in response_data:
                    extracted['key2'] = response_data.get('owner_name', '')
                elif 'father_name' in response_data:
                    extracted['key2'] = response_data.get('father_name', '')
                elif 'mother_name' in response_data:
                    extracted['key2'] = response_data.get('mother_name', '')
                elif 'spouse_name' in response_data:
                    extracted['key2'] = response_data.get('spouse_name', '')
                elif 'guardian_name' in response_data:
                    extracted['key2'] = response_data.get('guardian_name', '')
                else:
                    extracted['key2'] = ''
                
                # Additional details (DOB, phone, etc.) - Enhanced for all endpoints
                if 'dob' in response_data:
                    extracted['key3'] = response_data.get('dob', '')
                elif 'date_of_birth' in response_data:
                    extracted['key3'] = response_data.get('date_of_birth', '')
                elif 'phone_number' in response_data:
                    extracted['key3'] = response_data.get('phone_number', '')
                elif 'mobile' in response_data:
                    extracted['key3'] = response_data.get('mobile', '')
                elif 'mobile_number' in response_data:
                    extracted['key3'] = response_data.get('mobile_number', '')
                elif 'email' in response_data:
                    extracted['key3'] = response_data.get('email', '')
                elif 'email_id' in response_data:
                    extracted['key3'] = response_data.get('email_id', '')
                elif 'address' in response_data:
                    extracted['key3'] = response_data.get('address', '')
                elif 'location' in response_data:
                    extracted['key3'] = response_data.get('location', '')
                elif 'city' in response_data:
                    extracted['key3'] = response_data.get('city', '')
                elif 'state' in response_data:
                    extracted['key3'] = response_data.get('state', '')
                elif 'pincode' in response_data:
                    extracted['key3'] = response_data.get('pincode', '')
                elif 'gender' in response_data:
                    extracted['key3'] = response_data.get('gender', '')
                elif 'age' in response_data:
                    extracted['key3'] = response_data.get('age', '')
                elif 'category' in response_data:
                    extracted['key3'] = response_data.get('category', '')
                elif 'type' in response_data:
                    extracted['key3'] = response_data.get('type', '')
                elif 'status' in response_data:
                    extracted['key3'] = response_data.get('status', '')
                else:
                    extracted['key3'] = ''
                
                # Verification status - Enhanced for all endpoints
                if 'verification_status' in response_data:
                    extracted['verification_status'] = response_data.get('verification_status', '')
                elif 'status' in response_data:
                    extracted['verification_status'] = response_data.get('status', '')
                elif 'success' in response_data:
                    extracted['verification_status'] = 'success' if response_data.get('success') else 'failed'
                elif 'result' in response_data:
                    extracted['verification_status'] = response_data.get('result', '')
                elif 'match' in response_data:
                    extracted['verification_status'] = 'matched' if response_data.get('match') else 'not_matched'
                elif 'valid' in response_data:
                    extracted['verification_status'] = 'valid' if response_data.get('valid') else 'invalid'
                elif 'verified' in response_data:
                    extracted['verification_status'] = 'verified' if response_data.get('verified') else 'not_verified'
                elif 'liveness_score' in response_data:
                    extracted['verification_status'] = 'live' if response_data.get('liveness_score', 0) > 0.5 else 'not_live'
                elif 'face_match_score' in response_data:
                    extracted['verification_status'] = 'matched' if response_data.get('face_match_score', 0) > 0.8 else 'not_matched'
                elif 'ocr_confidence' in response_data:
                    extracted['verification_status'] = 'success' if response_data.get('ocr_confidence', 0) > 0.7 else 'low_confidence'
                else:
                    extracted['verification_status'] = 'unknown'
                
                # Confidence and timing - Enhanced for all endpoints
                if 'confidence_score' in response_data:
                    extracted['confidence_score'] = str(response_data.get('confidence_score', ''))
                elif 'confidence' in response_data:
                    extracted['confidence_score'] = str(response_data.get('confidence', ''))
                elif 'ocr_confidence' in response_data:
                    extracted['confidence_score'] = str(response_data.get('ocr_confidence', ''))
                elif 'liveness_score' in response_data:
                    extracted['confidence_score'] = str(response_data.get('liveness_score', ''))
                elif 'face_match_score' in response_data:
                    extracted['confidence_score'] = str(response_data.get('face_match_score', ''))
                elif 'match_score' in response_data:
                    extracted['confidence_score'] = str(response_data.get('match_score', ''))
                elif 'accuracy' in response_data:
                    extracted['confidence_score'] = str(response_data.get('accuracy', ''))
                else:
                    extracted['confidence_score'] = ''
                    
                if 'processing_time' in response_data:
                    extracted['processing_time'] = str(response_data.get('processing_time', ''))
                elif 'response_time' in response_data:
                    extracted['processing_time'] = str(response_data.get('response_time', ''))
                elif 'execution_time' in response_data:
                    extracted['processing_time'] = str(response_data.get('execution_time', ''))
                elif 'duration' in response_data:
                    extracted['processing_time'] = str(response_data.get('duration', ''))
                else:
                    extracted['processing_time'] = ''
            
            return extracted
            
        except Exception as e:
            logger.warning(f"Error extracting response fields: {e}")
            return {
                'key1': '', 'key2': '', 'key3': '', 
                'verification_status': 'error', 'confidence_score': '', 'processing_time': ''
            }
    
    async def update_query_response_id(self, log_id: str, response_id: str, success: bool) -> bool:
        """Update existing query with response ID instead of creating duplicate"""
        if not self.initialized or not DATABASE_ENABLED:
            return False
            
        try:
            def get_worksheet():
                return self.spreadsheet.worksheet(self.worksheets['api_usage_logs'])
            
            worksheet = await self._run_sync(get_worksheet)
            
            # Find the query row by ID and update it
            def update_query():
                # Get all records to find the query
                all_records = worksheet.get_all_records()
                for i, record in enumerate(all_records, start=2):  # Start from row 2 (after headers)
                    if record.get('ID') == str(log_id):
                        # Update the response_id and success columns
                        worksheet.update(f'N{i}', response_id)  # Response_ID column
                        worksheet.update(f'F{i}', 'true' if success else 'false')  # Success column
                        return True
                return False
            
            success = await self._run_sync(update_query)
            if success:
                logger.info(f"Updated query {log_id} with response ID {response_id}")
            else:
                logger.warning(f"Could not find query {log_id} to update")
            
            return success
            
        except Exception as e:
            logger.error(f"Error updating query response ID: {str(e)}")
            return False
    
    async def log_api_usage(self, request_type: str, api_endpoint: str, request_data: dict, status_code: int, success: bool, error_message: str, processing_time_ms: int, request_size_bytes: int, response_size_bytes: int, user_agent: str = '', ip_address: str = '', response_id: str = None) -> dict:
        if not self.initialized:
            return None
        worksheet = await self._run_sync(self.spreadsheet.worksheet, self.worksheets['api_usage_logs'])
        log_id = await self._get_next_id('api_usage_logs')
        timestamp = datetime.utcnow().isoformat()
        row_data = [
            log_id, request_type, api_endpoint, json.dumps(request_data), status_code, 'true' if success else 'false',
            error_message or '', processing_time_ms, request_size_bytes, response_size_bytes, user_agent, ip_address, timestamp, response_id or ''
        ]
        await self._run_sync(worksheet.append_row, row_data)
        await self._expand_headers('api_usage_logs', [k for k in request_data.keys() if k not in self.worksheets['api_usage_logs']])
        return {'id': log_id, 'timestamp': timestamp}

    async def store_api_output(self, record_id: str, api_endpoint: str, response_data: dict) -> dict:
        """Store API output in combined API Data worksheet (legacy method for compatibility)"""
        if not self.initialized:
            return None
        
        # Use the combined API Data worksheet instead of separate output worksheet
        worksheet = await self._run_sync(self.spreadsheet.worksheet, self.worksheets['api_data'])
        output_id = await self._get_next_id('api_data')
        timestamp = datetime.utcnow().isoformat()
        
        # Extract key fields for analytics
        key_fields = self._extract_key_response_fields(response_data)
        
        # Store in combined format with all fields
        row_data = [
            output_id, record_id, api_endpoint,
            '',  # Request_Data_JSON (empty for output method)
            json.dumps(response_data, ensure_ascii=False),  # Response_Data_JSON
            200,  # Status_Code (assume success)
            'true',  # Success
            '',  # Error_Message
            0,  # Processing_Time_MS
            timestamp,
            key_fields.get('verification_type', ''),
            key_fields.get('document_number', ''),
            key_fields.get('person_name', ''),
            key_fields.get('verification_status', ''),
            key_fields.get('confidence_score', ''),
            key_fields.get('processing_time', ''),
            key_fields.get('key1', ''),
            key_fields.get('key2', ''),
            key_fields.get('key3', '')
        ]
        
        await self._run_sync(worksheet.append_row, row_data)
        await self._expand_headers('api_data', [k for k in response_data.keys() if k not in self.worksheets['api_data']])
        logger.info(f"✅ API output stored in combined worksheet: {output_id}")
        return {'id': output_id, 'timestamp': timestamp}

    def _convert_sheet_record_to_dict(self, record: Dict[str, Any]) -> Dict[str, Any]:
        """Convert Google Sheets record to standardized dictionary"""
        try:
            # Parse JSON fields
            address_data = None
            if record.get('Address_Data'):
                try:
                    address_data = json.loads(record['Address_Data'])
                except json.JSONDecodeError:
                    address_data = record['Address_Data']
            
            raw_api_data = None
            if record.get('Raw_API_Data'):
                try:
                    raw_api_data = json.loads(record['Raw_API_Data'])
                except json.JSONDecodeError:
                    raw_api_data = record['Raw_API_Data']
            
            return {
                'id': record.get('ID'),
                'pan_number': record.get('PAN_Number'),
                'full_name': record.get('Full_Name'),
                'first_name': record.get('First_Name'),
                'middle_name': record.get('Middle_Name'),
                'last_name': record.get('Last_Name'),
                'father_name': record.get('Father_Name'),
                'email': record.get('Email'),
                'phone_number': record.get('Phone_Number'),
                'gender': record.get('Gender'),
                'dob': record.get('DOB'),
                'category': record.get('Category'),
                'is_minor': record.get('Is_Minor'),
                'address_data': address_data,
                'masked_aadhaar': record.get('Masked_Aadhaar'),
                'aadhaar_linked': record.get('Aadhaar_Linked'),
                'dob_verified': record.get('DOB_Verified'),
                'less_info': record.get('Less_Info'),
                'raw_api_data': raw_api_data,
                'api_endpoint': record.get('API_Endpoint'),
                'verification_count': record.get('Verification_Count'),
                'created_at': record.get('Created_At'),
                'updated_at': record.get('Updated_At'),
                'last_verified_at': record.get('Last_Verified_At')
            }
            
        except Exception as e:
            logger.error(f"Error converting sheet record: {str(e)}")
            return record

    async def _expand_headers(self, worksheet_key: str, new_fields):
        worksheet_name = self.worksheets[worksheet_key]
        def get_worksheet():
            return self.spreadsheet.worksheet(worksheet_name)
        worksheet = await self._run_sync(get_worksheet)
        def get_headers():
            return worksheet.row_values(1)
        headers = await self._run_sync(get_headers)
        updated = False
        for field in new_fields:
            if field not in headers:
                headers.append(field)
                updated = True
        if updated:
            def update_headers():
                return worksheet.update('A1', [headers])
            await self._run_sync(update_headers)
        return headers

# Global instance
google_sheets_db_manager = GoogleSheetsKYCDatabase()