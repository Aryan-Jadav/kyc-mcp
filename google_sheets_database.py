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
    """Google Sheets database manager for KYC data storage"""
    
    def __init__(self):
        self.gc = None
        self.drive_service = None
        self.sheets_service = None
        self.spreadsheet = None
        self.initialized = False
        self.executor = ThreadPoolExecutor(max_workers=5)
        
        # Configuration
        self.spreadsheet_name = os.getenv("KYC_SPREADSHEET_NAME", "KYC_Verification_Database")
        self.folder_id = os.getenv("GOOGLE_DRIVE_FOLDER_ID")  # Optional: specific folder
        
        # Worksheet names
        self.worksheets = {
            'universal_records': 'Universal_Records',
            'pan_records': 'PAN_Records', 
            'search_history': 'Search_History',
            'audit_log': 'Audit_Log',
            'api_usage': 'API_Usage',
            'api_responses': 'API_Responses',
            'queries': 'Queries'
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
        """Move spreadsheet to specific Drive folder"""
        try:
            file_id = self.spreadsheet.id
            # Remove from root and add to folder
            def move_file():
                return self.drive_service.files().update(
                    fileId=file_id,
                    addParents=self.folder_id,
                    removeParents='root',
                    fields='id, parents'
                ).execute()
            
            await self._run_sync(move_file)
            logger.info(f"Moved spreadsheet to folder: {self.folder_id}")
        except Exception as e:
            logger.warning(f"Could not move spreadsheet to folder: {str(e)}")
    
    async def _initialize_worksheets(self):
        """Initialize all required worksheets with headers"""
        try:
            # Universal Records worksheet
            await self._ensure_worksheet_exists('universal_records', [
                'ID', 'PAN_Number', 'Aadhaar_Number', 'Voter_ID', 'Driving_License', 
                'Passport_Number', 'GSTIN', 'TAN_Number', 'Bank_Account',
                'Full_Name', 'First_Name', 'Middle_Name', 'Last_Name', 'Father_Name',
                'Gender', 'DOB', 'Category', 'Is_Minor',
                'Phone_Number', 'Email', 'Address_Data',
                'Company_Name', 'Business_Type', 'Incorporation_Date',
                'IFSC_Code', 'Bank_Name', 'Branch_Name', 'UPI_ID',
                'Aadhaar_Linked', 'DOB_Verified', 'Verification_Status',
                'Last_Verification_Type', 'Verification_Source', 'Verification_Count',
                'Confidence_Score', 'Verification_History', 'Raw_Responses',
                'Extra_Data', 'Created_At', 'Updated_At', 'Last_Verified_At'
            ])
            
            # PAN Records worksheet (legacy compatibility)
            await self._ensure_worksheet_exists('pan_records', [
                'ID', 'PAN_Number', 'Full_Name', 'First_Name', 'Middle_Name', 'Last_Name',
                'Father_Name', 'Email', 'Phone_Number', 'Gender', 'DOB', 'Category',
                'Is_Minor', 'Address_Data', 'Masked_Aadhaar', 'Aadhaar_Linked',
                'DOB_Verified', 'Less_Info', 'Raw_API_Data', 'API_Endpoint',
                'Verification_Count', 'Created_At', 'Updated_At', 'Last_Verified_At'
            ])
            
            # Search History worksheet
            await self._ensure_worksheet_exists('search_history', [
                'ID', 'Search_Type', 'Search_Query', 'Results_Count', 'Search_Timestamp'
            ])
            
            # Audit Log worksheet
            await self._ensure_worksheet_exists('audit_log', [
                'ID', 'Record_ID', 'Action', 'Changed_Fields', 'Old_Values', 
                'New_Values', 'Timestamp'
            ])
            
            # API Usage worksheet
            await self._ensure_worksheet_exists('api_usage', [
                'ID', 'API_Endpoint', 'Request_Type', 'Status_Code', 'Success', 
                'Response_Time_MS', 'Request_Size_Bytes', 'Response_Size_Bytes',
                'User_Agent', 'IP_Address', 'Timestamp'
            ])
            
            # API Responses worksheet
            await self._ensure_worksheet_exists('api_responses', [
                'ID', 'Record_ID', 'API_Endpoint', 'Request_Data', 'Response_Data',
                'Status_Code', 'Success', 'Error_Message', 'Processing_Time_MS',
                'Timestamp'
            ])
            
            # Queries worksheet
            await self._ensure_worksheet_exists('queries', [
                'ID', 'Query_Type', 'Query_Data', 'API_Endpoint', 'Response_ID',
                'Success', 'Timestamp'
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
        """Store API response in Google Sheets"""
        if not self.initialized or not DATABASE_ENABLED:
            return None
            
        try:
            def get_worksheet():
                return self.spreadsheet.worksheet(self.worksheets['api_responses'])
            
            worksheet = await self._run_sync(get_worksheet)
            
            response_id = await self._get_next_id('api_responses')
            timestamp = datetime.utcnow().isoformat()
            
            # Convert data to JSON strings
            request_json = json.dumps(request_data)
            response_json = json.dumps(response_data)
            
            row_data = [
                response_id,
                record_id,
                api_endpoint,
                request_json,
                response_json,
                status_code,
                'true' if success else 'false',
                error_message or '',
                processing_time_ms,
                timestamp
            ]
            
            def append_row():
                return worksheet.append_row(row_data)
            
            await self._run_sync(append_row)
            logger.info(f"Stored API response with ID: {response_id}")
            
            return {'id': response_id, 'timestamp': timestamp}
            
        except Exception as e:
            logger.error(f"Error storing API response: {str(e)}")
            return None
    
    async def log_api_usage(self, api_endpoint: str, request_type: str, status_code: int, 
                          success: bool, response_time_ms: int = 0, request_size_bytes: int = 0, 
                          response_size_bytes: int = 0, user_agent: str = None, 
                          ip_address: str = None) -> Optional[Dict[str, Any]]:
        """Log API usage in Google Sheets"""
        if not self.initialized or not DATABASE_ENABLED:
            return None
            
        try:
            def get_worksheet():
                return self.spreadsheet.worksheet(self.worksheets['api_usage'])
            
            worksheet = await self._run_sync(get_worksheet)
            
            usage_id = await self._get_next_id('api_usage')
            timestamp = datetime.utcnow().isoformat()
            
            row_data = [
                usage_id,
                api_endpoint,
                request_type,
                status_code,
                'true' if success else 'false',
                response_time_ms,
                request_size_bytes,
                response_size_bytes,
                user_agent or '',
                ip_address or '',
                timestamp
            ]
            
            def append_row():
                return worksheet.append_row(row_data)
            
            await self._run_sync(append_row)
            logger.info(f"Logged API usage with ID: {usage_id}")
            
            return {'id': usage_id, 'timestamp': timestamp}
            
        except Exception as e:
            logger.error(f"Error logging API usage: {str(e)}")
            return None
    
    async def store_query(self, query_type: str, query_data: Dict[str, Any], api_endpoint: str, 
                        response_id: str = None, success: bool = True) -> Optional[Dict[str, Any]]:
        """Store query in Google Sheets"""
        if not self.initialized or not DATABASE_ENABLED:
            return None
            
        try:
            def get_worksheet():
                return self.spreadsheet.worksheet(self.worksheets['queries'])
            
            worksheet = await self._run_sync(get_worksheet)
            
            query_id = await self._get_next_id('queries')
            timestamp = datetime.utcnow().isoformat()
            
            # Convert query data to JSON string
            query_json = json.dumps(query_data)
            
            row_data = [
                query_id,
                query_type,
                query_json,
                api_endpoint,
                response_id or '',
                'true' if success else 'false',
                timestamp
            ]
            
            def append_row():
                return worksheet.append_row(row_data)
            
            await self._run_sync(append_row)
            logger.info(f"Stored query with ID: {query_id}")
            
            return {'id': query_id, 'timestamp': timestamp}
            
        except Exception as e:
            logger.error(f"Error storing query: {str(e)}")
            return None
    
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

# Global instance
google_sheets_db_manager = GoogleSheetsKYCDatabase()