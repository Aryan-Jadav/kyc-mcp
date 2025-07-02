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
    
    async def store_verification_data(self, verification_data: Dict[str, Any], api_endpoint: str, verification_type: str) -> Optional[Dict[str, Any]]:
        """Store verification data from any KYC API endpoint"""
        if not self.initialized or not DATABASE_ENABLED:
            return None
            
        try:
            # Extract document number based on verification type
            doc_number = verification_data.get('id_number') or verification_data.get('pan_number')
            
            worksheet = await self._run_sync(
                self.spreadsheet.worksheet, 
                self.worksheets['api_output_data']
            )
            
            # Find existing record
            existing_record = await self._find_universal_record(worksheet, verification_type, doc_number)
            
            # Prepare record data
            record_data = await self._prepare_universal_record_data(
                verification_data, verification_type, existing_record
            )
            
            if existing_record:
                # Update existing record
                await self._run_sync(
                    worksheet.update,
                    f"A{existing_record['row_num']}",
                    [record_data]
                )
                logger.info(f"Updated existing {verification_type} record for {doc_number}")
                record_id = existing_record['id']
            else:
                # Add new record
                await self._run_sync(worksheet.append_row, record_data)
                logger.info(f"Created new {verification_type} record for {doc_number}")
                record_id = record_data[0]  # ID is first column
            
            return {'id': record_id, 'verification_type': verification_type}
            
        except Exception as e:
            logger.error(f"Error storing verification data: {str(e)}")
            return None
    
    async def _find_universal_record(self, worksheet, verification_type: str, doc_number: str) -> Optional[Dict[str, Any]]:
        """Find existing universal record"""
        if not doc_number:
            return None
            
        try:
            records = await self._run_sync(worksheet.get_all_records)
            
            for i, record in enumerate(records, start=2):  # Start from row 2
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