"""Universal Database Manager for KYC Data Storage"""

import json
import logging
from datetime import datetime
from typing import Optional, Dict, Any, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_, and_, func
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from database_models import UniversalRecord, SearchHistory
from database import DatabaseManager
from config_db import DATABASE_ENABLED, MAX_SEARCH_RESULTS

logger = logging.getLogger("kyc-universal-database")

class UniversalKYCDatabase(DatabaseManager):
    """Universal database manager for all KYC verification types"""
    
    def __init__(self):
        super().__init__()
    
    async def store_verification_data(self, verification_data: Dict[str, Any], api_endpoint: str, verification_type: str) -> Optional[UniversalRecord]:
        """Store verification data from any KYC API endpoint"""
        if not self.initialized or not DATABASE_ENABLED:
            return None
            
        try:
            async with self.get_session() as session:
                if session is None:
                    return None

                # Extract document number based on verification type
                doc_number = verification_data.get('id_number') or verification_data.get('pan_number')
                
                # Find existing record or create new one
                existing_record = None
                if verification_type.startswith('pan') and doc_number:
                    stmt = select(UniversalRecord).where(UniversalRecord.pan_number == doc_number)
                    result = await session.execute(stmt)
                    existing_record = result.scalar_one_or_none()
                elif verification_type == 'aadhaar' and doc_number:
                    stmt = select(UniversalRecord).where(UniversalRecord.aadhaar_number == doc_number)
                    result = await session.execute(stmt)
                    existing_record = result.scalar_one_or_none()
                
                if existing_record:
                    # Update existing record
                    await self._update_record(session, existing_record, verification_data, verification_type)
                    record = existing_record
                else:
                    # Create new record
                    record = await self._create_record(session, verification_data, verification_type)

                await session.commit()
                return record

        except Exception as e:
            logger.error(f"Error storing verification data: {str(e)}")
            return None

    async def _create_record(self, session: AsyncSession, data: Dict[str, Any], verification_type: str) -> UniversalRecord:
        """Create new universal record"""
        record = UniversalRecord()
        await self._update_record(session, record, data, verification_type)
        session.add(record)
        return record

    async def _update_record(self, session: AsyncSession, record: UniversalRecord, data: Dict[str, Any], verification_type: str):
        """Update record with new verification data"""
        
        # Update document numbers based on verification type
        if verification_type.startswith('pan'):
            record.pan_number = data.get('id_number') or data.get('pan_number')
        elif verification_type == 'aadhaar':
            record.aadhaar_number = data.get('id_number') or data.get('aadhaar_number')
        elif verification_type == 'voter_id':
            record.voter_id = data.get('id_number')
        elif verification_type == 'driving_license':
            record.driving_license = data.get('id_number')
        elif verification_type == 'passport':
            record.passport_number = data.get('id_number')
        elif verification_type == 'gstin':
            record.gstin = data.get('id_number')
        elif verification_type == 'tan':
            record.tan_number = data.get('id_number')
        elif verification_type == 'bank_verification':
            record.bank_account = data.get('id_number')

        # Update personal information
        if data.get('full_name'):
            record.full_name = data['full_name']
        if data.get('first_name'):
            record.first_name = data['first_name']
        if data.get('middle_name'):
            record.middle_name = data['middle_name']
        if data.get('last_name'):
            record.last_name = data['last_name']
        if data.get('father_name'):
            record.father_name = data['father_name']
        if data.get('gender'):
            record.gender = data['gender']
        if data.get('dob'):
            record.dob = data['dob']
        if data.get('category'):
            record.category = data['category']
        if 'is_minor' in data:
            record.is_minor = data['is_minor']

        # Update contact information
        if data.get('phone_number') or data.get('mobile'):
            record.phone_number = data.get('phone_number') or data.get('mobile')
        if data.get('email'):
            record.email = data['email']

        # Update address information
        if data.get('address'):
            record.address_data = data['address']

        # Update business information
        if data.get('company_name'):
            record.company_name = data['company_name']
        if data.get('business_type'):
            record.business_type = data['business_type']
        if data.get('incorporation_date'):
            record.incorporation_date = data['incorporation_date']

        # Update bank information
        if data.get('ifsc_code'):
            record.ifsc_code = data['ifsc_code']
        if data.get('bank_name'):
            record.bank_name = data['bank_name']
        if data.get('branch_name'):
            record.branch_name = data['branch_name']
        if data.get('upi_id'):
            record.upi_id = data['upi_id']

        # Update verification status
        if 'aadhaar_linked' in data:
            record.aadhaar_linked = data['aadhaar_linked']
        if 'dob_verified' in data:
            record.dob_verified = data['dob_verified']
        
        record.verification_status = 'verified'
        record.last_verification_type = verification_type
        record.verification_source = verification_type
        record.verification_count = (record.verification_count or 0) + 1
        
        # Update verification history
        if record.verification_history is None:
            record.verification_history = []
        record.verification_history.append({
            'type': verification_type,
            'timestamp': datetime.utcnow().isoformat(),
            'status': 'success'
        })

        # Store raw response
        if record.raw_responses is None:
            record.raw_responses = {}
        record.raw_responses[verification_type] = data

        record.last_verified_at = datetime.utcnow()
        record.updated_at = datetime.utcnow()

    async def search_record(self, search_type: str, search_value: str) -> List[UniversalRecord]:
        """Search records by any field"""
        if not self.initialized or not DATABASE_ENABLED:
            return []

        try:
            async with self.get_session() as session:
                if session is None:
                    return []

                stmt = None
                if search_type == 'pan':
                    stmt = select(UniversalRecord).where(UniversalRecord.pan_number == search_value.upper())
                elif search_type == 'name':
                    search_pattern = f"%{search_value}%"
                    stmt = select(UniversalRecord).where(
                        or_(
                            UniversalRecord.full_name.ilike(search_pattern),
                            UniversalRecord.first_name.ilike(search_pattern),
                            UniversalRecord.last_name.ilike(search_pattern)
                        )
                    )
                elif search_type == 'phone':
                    stmt = select(UniversalRecord).where(UniversalRecord.phone_number == search_value)
                elif search_type == 'email':
                    stmt = select(UniversalRecord).where(UniversalRecord.email.ilike(f"%{search_value}%"))
                
                if stmt is not None:
                    stmt = stmt.limit(MAX_SEARCH_RESULTS)
                    result = await session.execute(stmt)
                    records = result.scalars().all()

                    # Log search in history
                    search_history = SearchHistory(
                        search_type=search_type,
                        search_query=search_value,
                        results_count=len(records)
                    )
                    session.add(search_history)
                    await session.commit()

                    return list(records)

                return []

        except Exception as e:
            logger.error(f"Error searching records: {str(e)}")
            return []

# Create an alias for the store_verification_data method
async def store_universal_verification_data(verification_data: Dict[str, Any], api_endpoint: str) -> Optional[UniversalRecord]:
    """Alias for store_verification_data method to maintain compatibility"""
    verification_type = api_endpoint.strip("/").split("/")[-1]  # Extract type from endpoint
    return await universal_db_manager.store_verification_data(verification_data, api_endpoint, verification_type)

# Global instance
universal_db_manager = UniversalKYCDatabase()
