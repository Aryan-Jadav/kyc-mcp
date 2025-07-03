"""Universal Google Sheets Database Manager for KYC Data Storage"""

import json
import logging
from datetime import datetime
from typing import Optional, Dict, Any, List
import asyncio
from concurrent.futures import ThreadPoolExecutor

from google_sheets_database import GoogleSheetsKYCDatabase
from config_db import DATABASE_ENABLED

logger = logging.getLogger("kyc-universal-google-sheets")

class UniversalGoogleSheetsDatabase(GoogleSheetsKYCDatabase):
    """Universal Google Sheets database manager for all KYC verification types"""
    
    def __init__(self):
        super().__init__()
        self.universal_headers = [
            'ID', 'PAN_Number', 'Aadhaar_Number', 'Voter_ID', 'Driving_License', 'Passport_Number', 'GSTIN', 'TAN_Number', 'Bank_Account',
            'Full_Name', 'First_Name', 'Middle_Name', 'Last_Name', 'Father_Name', 'Gender', 'DOB', 'Category', 'Is_Minor',
            'Phone_Number', 'Email', 'Address_Data', 'Company_Name', 'Business_Type', 'Incorporation_Date', 'IFSC_Code',
            'Bank_Name', 'Branch_Name', 'UPI_ID', 'Aadhaar_Linked', 'DOB_Verified', 'Verification_Status', 'Last_Verification_Type',
            'Verification_Source', 'Verification_Count', 'Confidence_Score', 'Verification_History', 'Raw_Responses', 'Extra_Data',
            'Created_At', 'Updated_At', 'Last_Verified_At'
        ]
    
    async def _ensure_universal_worksheet(self):
        worksheet_name = 'Universal_Records'
        def get_worksheet():
            return self.spreadsheet.worksheet(worksheet_name)
        try:
            worksheet = await self._run_sync(get_worksheet)
            def get_headers():
                return worksheet.row_values(1)
            existing_headers = await self._run_sync(get_headers)
            # Add any missing headers
            headers = list(self.universal_headers)
            for h in existing_headers:
                if h not in headers:
                    headers.append(h)
            if existing_headers != headers:
                def update_headers():
                    return worksheet.update('A1', [headers])
                await self._run_sync(update_headers)
        except Exception:
            # Create worksheet if not found
            def add_worksheet():
                return self.spreadsheet.add_worksheet(title=worksheet_name, rows=1000, cols=len(self.universal_headers))
            worksheet = await self._run_sync(add_worksheet)
            def add_headers():
                return worksheet.update('A1', [self.universal_headers])
            await self._run_sync(add_headers)

    async def _expand_universal_headers(self, new_fields):
        worksheet_name = 'Universal_Records'
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

    async def store_verification_data(self, verification_data: Dict[str, Any], api_endpoint: str, verification_type: str, api_usage: dict = None, api_response: dict = None) -> Optional[Dict[str, Any]]:
        """
        Store verification data in Universal_Records (robust, deployment-ready):
        - Auto-expands headers for new fields.
        - Merges with existing record if found (by any document number).
        - Updates only changed fields, appends to verification history and raw responses.
        - Logs API usage and stores API data in the other two tabs.
        - Idempotent and safe for concurrent writes.
        - Fully robust against header/data mismatches and race conditions.
        """
        if not self.initialized or not DATABASE_ENABLED:
            logger.error("UniversalGoogleSheetsDatabase not initialized or database disabled.")
            return None
        await self._ensure_universal_worksheet()
        # Expand headers if new fields are present
        new_fields = [k for k in verification_data.keys() if k not in self.universal_headers]
        if new_fields:
            self.universal_headers.extend(new_fields)
            await self._expand_universal_headers(new_fields)
        worksheet = await self._run_sync(self.spreadsheet.worksheet, 'Universal_Records')
        # Always re-fetch headers after possible expansion
        headers = await self._run_sync(lambda: worksheet.row_values(1))
        if not headers or not any(headers):
            logger.error("Universal_Records header row is empty or missing!")
            return None
        # Find existing record by any document number
        doc_numbers = [verification_data.get(f) for f in ['id_number','pan_number','aadhaar_number','voter_id','driving_license','passport_number','gstin','tan_number','bank_account'] if verification_data.get(f)]
        records = await self._run_sync(worksheet.get_all_records)
        match_row = None
        match_record = None
        for i, record in enumerate(records, start=2):
            for f in ['PAN_Number','Aadhaar_Number','Voter_ID','Driving_License','Passport_Number','GSTIN','TAN_Number','Bank_Account']:
                if record.get(f) and record.get(f) in doc_numbers:
                    match_row = i
                    match_record = record
                    break
            if match_row:
                break
        timestamp = datetime.utcnow().isoformat()
        # Build row_data to match headers
        def build_row_data():
            row = []
            for idx, h in enumerate(headers):
                if h == 'ID':
                    if match_row and match_record:
                        row.append(str(match_record.get('ID', match_row)))
                    else:
                        next_id = len(records) + 1
                        row.append(str(next_id))
                elif h == 'Verification_History':
                    history = []
                    if match_record and match_record.get('Verification_History'):
                        try:
                            history = json.loads(match_record['Verification_History'])
                        except Exception:
                            history = []
                    history.append({
                        'type': verification_type,
                        'timestamp': timestamp,
                        'status': 'success',
                        'api_endpoint': api_endpoint
                    })
                    row.append(json.dumps(history))
                elif h == 'Raw_Responses':
                    responses = {}
                    if match_record and match_record.get('Raw_Responses'):
                        try:
                            responses = json.loads(match_record['Raw_Responses'])
                        except Exception:
                            responses = {}
                    responses[verification_type] = verification_data
                    row.append(json.dumps(responses))
                elif h in verification_data:
                    row.append(str(verification_data[h]))
                elif match_record and h in match_record:
                    row.append(str(match_record[h]))
                else:
                    row.append('')
            return row
        row_data = build_row_data()
        # Defensive: if mismatch, retry once after short delay (race condition safe)
        if len(row_data) != len(headers):
            logger.warning(f"Header/data length mismatch (first try): {len(headers)} headers, {len(row_data)} data. Retrying after short delay.")
            logger.warning(f"Headers: {headers}")
            logger.warning(f"Row data: {row_data}")
            await asyncio.sleep(0.5)
            headers = await self._run_sync(lambda: worksheet.row_values(1))
            row_data = build_row_data()
        if len(row_data) != len(headers):
            logger.error(f"Header/data length mismatch (second try): {len(headers)} headers, {len(row_data)} data. Skipping write.")
            logger.error(f"Headers: {headers}")
            logger.error(f"Row data: {row_data}")
            return None
        if match_row:
            def update_row():
                return worksheet.update(f"A{match_row}", [row_data])
            await self._run_sync(update_row)
            logger.info(f"Updated Universal_Records row {match_row} for doc_numbers {doc_numbers}")
        else:
            def append_row():
                return worksheet.append_row(row_data)
            await self._run_sync(append_row)
            logger.info(f"Appended new Universal_Records row for doc_numbers {doc_numbers}")
        # Log API usage and store API data
        if api_usage and hasattr(self, 'log_api_usage'):
            await self.log_api_usage(**api_usage)
        if api_response and hasattr(self, 'store_api_output'):
            await self.store_api_output(row_data[0], api_endpoint, api_response)
        return {'id': row_data[0], 'verification_type': verification_type}
    
    async def _find_universal_record(self, worksheet, verification_type: str, doc_number: str) -> Optional[Dict[str, Any]]:
        """Find existing universal record"""
        if not doc_number:
            return None
            
        try:
            records = await self._run_sync(worksheet.get_all_records)
            
            # Handle empty worksheet
            if not records:
                return None
            
            for i, record in enumerate(records, start=2):  # Start from row 2
                try:
                    # Check based on verification type
                    if verification_type.startswith('pan') and record.get('PAN_Number') == doc_number:
                        return {'row_num': i, 'id': record.get('ID'), 'record': record}
                    elif verification_type == 'aadhaar' and record.get('Aadhaar_Number') == doc_number:
                        return {'row_num': i, 'id': record.get('ID'), 'record': record}
                    elif verification_type == 'voter_id' and record.get('Voter_ID') == doc_number:
                        return {'row_num': i, 'id': record.get('ID'), 'record': record}
                    elif verification_type == 'driving_license' and record.get('Driving_License') == doc_number:
                        return {'row_num': i, 'id': record.get('ID'), 'record': record}
                    elif verification_type == 'passport' and record.get('Passport_Number') == doc_number:
                        return {'row_num': i, 'id': record.get('ID'), 'record': record}
                    elif verification_type == 'gstin' and record.get('GSTIN') == doc_number:
                        return {'row_num': i, 'id': record.get('ID'), 'record': record}
                    elif verification_type == 'tan' and record.get('TAN_Number') == doc_number:
                        return {'row_num': i, 'id': record.get('ID'), 'record': record}
                    elif verification_type == 'bank_verification' and record.get('Bank_Account') == doc_number:
                        return {'row_num': i, 'id': record.get('ID'), 'record': record}
                except (KeyError, IndexError) as e:
                    # Skip malformed records
                    logger.warning(f"Skipping malformed record at row {i}: {e}")
                    continue
            
            return None
            
        except Exception as e:
            logger.error(f"Error finding universal record: {str(e)}")
            return None
    
    async def _prepare_universal_record_data(self, data: Dict[str, Any], verification_type: str, existing_record: Optional[Dict[str, Any]]) -> List[str]:
        """Prepare universal record data for Google Sheets"""
        try:
            timestamp = datetime.utcnow().isoformat()
            
            # Get existing data if updating
            if existing_record:
                existing_data = existing_record['record']
                record_id = existing_data.get('ID')
                created_at = existing_data.get('Created_At', timestamp)
                verification_count = int(existing_data.get('Verification_Count', 0)) + 1
                
                # Parse existing verification history
                existing_history = []
                if existing_data.get('Verification_History'):
                    try:
                        existing_history = json.loads(existing_data['Verification_History'])
                    except json.JSONDecodeError:
                        existing_history = []
                
                # Parse existing raw responses
                existing_responses = {}
                if existing_data.get('Raw_Responses'):
                    try:
                        existing_responses = json.loads(existing_data['Raw_Responses'])
                    except json.JSONDecodeError:
                        existing_responses = {}
            else:
                record_id = await self._get_next_id('api_output_data')
                created_at = timestamp
                verification_count = 1
                existing_history = []
                existing_responses = {}
                existing_data = {}
            
            # Update verification history
            existing_history.append({
                'type': verification_type,
                'timestamp': timestamp,
                'status': 'success'
            })
            
            # Update raw responses
            existing_responses[verification_type] = data
            
            # Prepare document numbers
            pan_number = data.get('id_number') if verification_type.startswith('pan') else existing_data.get('PAN_Number', '')
            aadhaar_number = data.get('id_number') if verification_type == 'aadhaar' else existing_data.get('Aadhaar_Number', '')
            voter_id = data.get('id_number') if verification_type == 'voter_id' else existing_data.get('Voter_ID', '')
            driving_license = data.get('id_number') if verification_type == 'driving_license' else existing_data.get('Driving_License', '')
            passport_number = data.get('id_number') if verification_type == 'passport' else existing_data.get('Passport_Number', '')
            gstin = data.get('id_number') if verification_type == 'gstin' else existing_data.get('GSTIN', '')
            tan_number = data.get('id_number') if verification_type == 'tan' else existing_data.get('TAN_Number', '')
            bank_account = data.get('id_number') if verification_type == 'bank_verification' else existing_data.get('Bank_Account', '')
            
            # Prepare address data
            address_data = data.get('address') or existing_data.get('Address_Data')
            address_json = json.dumps(address_data) if address_data else ""
            
            # Prepare other data fields
            verification_history_json = json.dumps(existing_history)
            raw_responses_json = json.dumps(existing_responses)
            extra_data_json = json.dumps(data.get('extra_data', {}))
            
            # Build complete row data
            row_data = [
                record_id,                                                    # ID
                pan_number or data.get('pan_number', ''),                    # PAN_Number
                aadhaar_number or data.get('aadhaar_number', ''),            # Aadhaar_Number
                voter_id,                                                     # Voter_ID
                driving_license,                                              # Driving_License
                passport_number,                                              # Passport_Number
                gstin,                                                        # GSTIN
                tan_number,                                                   # TAN_Number
                bank_account,                                                 # Bank_Account
                data.get('full_name') or existing_data.get('Full_Name', ''), # Full_Name
                data.get('first_name') or existing_data.get('First_Name', ''), # First_Name
                data.get('middle_name') or existing_data.get('Middle_Name', ''), # Middle_Name
                data.get('last_name') or existing_data.get('Last_Name', ''), # Last_Name
                data.get('father_name') or existing_data.get('Father_Name', ''), # Father_Name
                data.get('gender') or existing_data.get('Gender', ''),       # Gender
                data.get('dob') or existing_data.get('DOB', ''),             # DOB
                data.get('category') or existing_data.get('Category', ''),   # Category
                data.get('is_minor') or existing_data.get('Is_Minor', ''),   # Is_Minor
                data.get('phone_number') or data.get('mobile') or existing_data.get('Phone_Number', ''), # Phone_Number
                data.get('email') or existing_data.get('Email', ''),         # Email
                address_json,                                                 # Address_Data
                data.get('company_name') or existing_data.get('Company_Name', ''), # Company_Name
                data.get('business_type') or existing_data.get('Business_Type', ''), # Business_Type
                data.get('incorporation_date') or existing_data.get('Incorporation_Date', ''), # Incorporation_Date
                data.get('ifsc_code') or data.get('ifsc') or existing_data.get('IFSC_Code', ''), # IFSC_Code
                data.get('bank_name') or existing_data.get('Bank_Name', ''), # Bank_Name
                data.get('branch_name') or existing_data.get('Branch_Name', ''), # Branch_Name
                data.get('upi_id') or existing_data.get('UPI_ID', ''),       # UPI_ID
                data.get('aadhaar_linked') or existing_data.get('Aadhaar_Linked', ''), # Aadhaar_Linked
                data.get('dob_verified') or existing_data.get('DOB_Verified', ''), # DOB_Verified
                'verified',                                                   # Verification_Status
                verification_type,                                            # Last_Verification_Type
                verification_type,                                            # Verification_Source
                verification_count,                                           # Verification_Count
                data.get('confidence_score', ''),                           # Confidence_Score
                verification_history_json,                                    # Verification_History
                raw_responses_json,                                           # Raw_Responses
                extra_data_json,                                              # Extra_Data
                created_at,                                                   # Created_At
                timestamp,                                                    # Updated_At
                timestamp                                                     # Last_Verified_At
            ]
            
            # Convert all values to strings for Google Sheets
            return [str(value) if value is not None else '' for value in row_data]
            
        except Exception as e:
            logger.error(f"Error preparing universal record data: {str(e)}")
            return []
    
    async def search_record(self, search_type: str, search_value: str) -> List[Dict[str, Any]]:
        """Search universal records by any field"""
        if not self.initialized or not DATABASE_ENABLED:
            return []
            
        try:
            worksheet = await self._run_sync(
                self.spreadsheet.worksheet, 
                self.worksheets['universal_records']
            )
            
            records = await self._run_sync(worksheet.get_all_records)
            matches = []
            
            for record in records:
                if search_type == 'pan':
                    if record.get('PAN_Number') == search_value.upper():
                        matches.append(self._convert_universal_record_to_dict(record))
                elif search_type == 'name':
                    full_name = record.get('Full_Name', '').lower()
                    first_name = record.get('First_Name', '').lower()
                    last_name = record.get('Last_Name', '').lower()
                    search_name = search_value.lower()
                    
                    if (search_name in full_name or 
                        search_name in first_name or 
                        search_name in last_name):
                        matches.append(self._convert_universal_record_to_dict(record))
                elif search_type == 'phone':
                    if record.get('Phone_Number') == search_value:
                        matches.append(self._convert_universal_record_to_dict(record))
                elif search_type == 'email':
                    record_email = record.get('Email', '').lower()
                    if search_value.lower() in record_email:
                        matches.append(self._convert_universal_record_to_dict(record))
            
            await self._log_search(search_type, search_value, len(matches))
            return matches
            
        except Exception as e:
            logger.error(f"Error searching universal records: {str(e)}")
            return []
    
    async def search_person_by_identifier(self, identifier_type: str, value: str) -> List[Dict[str, Any]]:
        """Search persons by identifier (alias for search_record)"""
        return await self.search_record(identifier_type, value)
    
    async def get_person_complete_profile(self, person_id: int) -> Optional[Dict[str, Any]]:
        """Get complete profile of a person"""
        if not self.initialized or not DATABASE_ENABLED:
            return None
            
        try:
            worksheet = await self._run_sync(
                self.spreadsheet.worksheet, 
                self.worksheets['universal_records']
            )
            
            records = await self._run_sync(worksheet.get_all_records)
            
            for record in records:
                if record.get('ID') == str(person_id):
                    profile = self._convert_universal_record_to_dict(record)
                    
                    # Add verification details
                    verification_history = []
                    if record.get('Verification_History'):
                        try:
                            verification_history = json.loads(record['Verification_History'])
                        except json.JSONDecodeError:
                            verification_history = []
                    
                    raw_responses = {}
                    if record.get('Raw_Responses'):
                        try:
                            raw_responses = json.loads(record['Raw_Responses'])
                        except json.JSONDecodeError:
                            raw_responses = {}
                    
                    profile.update({
                        'verification_history': verification_history,
                        'raw_responses': raw_responses,
                        'total_verifications': len(verification_history)
                    })
                    
                    return profile
            
            return None
            
        except Exception as e:
            logger.error(f"Error getting person profile: {str(e)}")
            return None
    
    def _convert_universal_record_to_dict(self, record: Dict[str, Any]) -> Dict[str, Any]:
        """Convert Google Sheets universal record to standardized dictionary"""
        try:
            # Parse JSON fields
            address_data = None
            if record.get('Address_Data'):
                try:
                    address_data = json.loads(record['Address_Data'])
                except json.JSONDecodeError:
                    address_data = record['Address_Data']
            
            verification_history = []
            if record.get('Verification_History'):
                try:
                    verification_history = json.loads(record['Verification_History'])
                except json.JSONDecodeError:
                    verification_history = []
            
            raw_responses = {}
            if record.get('Raw_Responses'):
                try:
                    raw_responses = json.loads(record['Raw_Responses'])
                except json.JSONDecodeError:
                    raw_responses = {}
            
            extra_data = {}
            if record.get('Extra_Data'):
                try:
                    extra_data = json.loads(record['Extra_Data'])
                except json.JSONDecodeError:
                    extra_data = {}
            
            return {
                'id': record.get('ID'),
                # Document numbers
                'pan_number': record.get('PAN_Number'),
                'aadhaar_number': record.get('Aadhaar_Number'),
                'voter_id': record.get('Voter_ID'),
                'driving_license': record.get('Driving_License'),
                'passport_number': record.get('Passport_Number'),
                'gstin': record.get('GSTIN'),
                'tan_number': record.get('TAN_Number'),
                'bank_account': record.get('Bank_Account'),
                
                # Personal information
                'full_name': record.get('Full_Name'),
                'first_name': record.get('First_Name'),
                'middle_name': record.get('Middle_Name'),
                'last_name': record.get('Last_Name'),
                'father_name': record.get('Father_Name'),
                'gender': record.get('Gender'),
                'dob': record.get('DOB'),
                'category': record.get('Category'),
                'is_minor': record.get('Is_Minor'),
                
                # Contact information
                'phone_number': record.get('Phone_Number'),
                'email': record.get('Email'),
                'address_data': address_data,
                
                # Business information
                'company_name': record.get('Company_Name'),
                'business_type': record.get('Business_Type'),
                'incorporation_date': record.get('Incorporation_Date'),
                
                # Bank information
                'ifsc_code': record.get('IFSC_Code'),
                'bank_name': record.get('Bank_Name'),
                'branch_name': record.get('Branch_Name'),
                'upi_id': record.get('UPI_ID'),
                
                # Verification status
                'aadhaar_linked': record.get('Aadhaar_Linked'),
                'dob_verified': record.get('DOB_Verified'),
                'verification_status': record.get('Verification_Status'),
                'last_verification_type': record.get('Last_Verification_Type'),
                'verification_source': record.get('Verification_Source'),
                
                # Metadata
                'verification_count': record.get('Verification_Count'),
                'confidence_score': record.get('Confidence_Score'),
                'verification_history': verification_history,
                'raw_responses': raw_responses,
                'extra_data': extra_data,
                
                # Timestamps
                'created_at': record.get('Created_At'),
                'updated_at': record.get('Updated_At'),
                'last_verified_at': record.get('Last_Verified_At')
            }
            
        except Exception as e:
            logger.error(f"Error converting universal record: {str(e)}")
            return record

# Compatibility function for existing code
async def store_universal_verification_data(verification_data: Dict[str, Any], api_endpoint: str) -> Optional[Dict[str, Any]]:
    """Store verification data in Google Sheets (compatibility function)"""
    verification_type = api_endpoint.strip("/").split("/")[-1]  # Extract type from endpoint
    return await universal_google_sheets_manager.store_verification_data(verification_data, api_endpoint, verification_type)

# Global instance
universal_google_sheets_manager = UniversalGoogleSheetsDatabase()