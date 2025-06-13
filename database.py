"""Database management for KYC MCP Server"""

import json
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List, Tuple, Union
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy import select, update, delete, or_, and_, func, text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from contextlib import asynccontextmanager

from database_models import Base, PANRecord, SearchHistory, DataAuditLog
from config_db import (
    DATABASE_URL, DATABASE_ENABLED, DATABASE_SETTINGS,
    DATA_RETENTION_DAYS, MAX_SEARCH_RESULTS, ENABLE_FUZZY_SEARCH
)

logger = logging.getLogger("kyc-database")

class DatabaseManager:
    """Database manager for KYC data storage and retrieval"""
    
    def __init__(self):
        self.engine = None
        self.async_session_maker = None
        self.initialized = False
        
    async def initialize(self):
        """Initialize database connection and create tables"""
        if not DATABASE_ENABLED:
            logger.info("Database storage is disabled")
            return
            
        try:
            # Create async engine
            self.engine = create_async_engine(
                DATABASE_URL,
                echo=DATABASE_SETTINGS.get("echo", False),
                pool_pre_ping=DATABASE_SETTINGS.get("pool_pre_ping", True),
                pool_recycle=DATABASE_SETTINGS.get("pool_recycle", 3600),
            )
            
            # Create session maker
            self.async_session_maker = async_sessionmaker(
                self.engine,
                class_=AsyncSession,
                expire_on_commit=False
            )
            
            # Create tables
            async with self.engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
                
            self.initialized = True
            logger.info("Database initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize database: {str(e)}")
            raise
    
    async def close(self):
        """Close database connections"""
        if self.engine:
            await self.engine.dispose()
            logger.info("Database connections closed")
    
    @asynccontextmanager
    async def get_session(self):
        """Get database session context manager"""
        if not self.initialized or not DATABASE_ENABLED:
            yield None
            return
            
        async with self.async_session_maker() as session:
            try:
                yield session
            except Exception as e:
                await session.rollback()
                logger.error(f"Database session error: {str(e)}")
                raise
            finally:
                await session.close()
    
    async def store_pan_data(self, pan_data: Dict[str, Any], api_endpoint: str = None) -> Optional[PANRecord]:
        """Store or update PAN data in database"""
        if not self.initialized or not DATABASE_ENABLED:
            return None
            
        try:
            async with self.get_session() as session:
                if session is None:
                    return None
                    
                pan_number = pan_data.get('pan_number')
                if not pan_number:
                    logger.warning("No PAN number found in data, skipping database storage")
                    return None
                
                # Check if record already exists
                existing_record = await self._find_existing_record(session, pan_data)
                
                if existing_record:
                    # Update existing record
                    updated_record = await self._update_pan_record(session, existing_record, pan_data, api_endpoint)
                    await session.commit()
                    logger.info(f"Updated existing PAN record for {pan_number}")
                    return updated_record
                else:
                    # Create new record
                    new_record = await self._create_pan_record(session, pan_data, api_endpoint)
                    await session.commit()
                    logger.info(f"Created new PAN record for {pan_number}")
                    return new_record
                    
        except Exception as e:
            logger.error(f"Error storing PAN data: {str(e)}")
            return None
    
    async def _find_existing_record(self, session: AsyncSession, pan_data: Dict[str, Any]) -> Optional[PANRecord]:
        """Find existing record by PAN number or name combination"""
        pan_number = pan_data.get('pan_number')
        full_name = pan_data.get('full_name')
        
        if pan_number:
            # First try to find by PAN number (most reliable)
            stmt = select(PANRecord).where(PANRecord.pan_number == pan_number)
            result = await session.execute(stmt)
            record = result.scalar_one_or_none()
            if record:
                return record
        
        if full_name:
            # If no PAN match, try to find by full name (for cases where same person has multiple PANs)
            stmt = select(PANRecord).where(PANRecord.full_name == full_name)
            result = await session.execute(stmt)
            record = result.scalar_one_or_none()
            if record:
                return record
        
        return None
    
    async def _create_pan_record(self, session: AsyncSession, pan_data: Dict[str, Any], api_endpoint: str = None) -> PANRecord:
        """Create new PAN record"""
        # Extract address data
        address_data = None
        if 'address' in pan_data and pan_data['address']:
            if isinstance(pan_data['address'], dict):
                address_data = pan_data['address']
            else:
                address_data = {'full': str(pan_data['address'])}
        
        # Create new record
        record = PANRecord(
            pan_number=pan_data.get('pan_number'),
            full_name=pan_data.get('full_name'),
            first_name=pan_data.get('first_name'),
            middle_name=pan_data.get('middle_name'),
            last_name=pan_data.get('last_name'),
            father_name=pan_data.get('father_name'),
            email=pan_data.get('email'),
            phone_number=pan_data.get('phone_number'),
            gender=pan_data.get('gender'),
            dob=pan_data.get('dob'),
            category=pan_data.get('category'),
            is_minor=pan_data.get('is_minor'),
            address_data=address_data,
            masked_aadhaar=pan_data.get('masked_aadhaar'),
            aadhaar_linked=pan_data.get('aadhaar_linked'),
            dob_verified=pan_data.get('dob_verified'),
            less_info=pan_data.get('less_info'),
            raw_api_data=pan_data,
            api_endpoint=api_endpoint,
            verification_count=1,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            last_verified_at=datetime.utcnow()
        )
        
        session.add(record)
        await session.flush()  # Get the ID
        
        # Log the creation
        await self._log_audit_action(session, record.id, 'INSERT', {}, pan_data)
        
        return record

    async def _update_pan_record(self, session: AsyncSession, record: PANRecord, pan_data: Dict[str, Any], api_endpoint: str = None) -> PANRecord:
        """Update existing PAN record with new data"""
        old_values = record.to_dict()
        changed_fields = []

        # Update fields if new data is available
        fields_to_update = {
            'full_name': pan_data.get('full_name'),
            'first_name': pan_data.get('first_name'),
            'middle_name': pan_data.get('middle_name'),
            'last_name': pan_data.get('last_name'),
            'father_name': pan_data.get('father_name'),
            'email': pan_data.get('email'),
            'phone_number': pan_data.get('phone_number'),
            'gender': pan_data.get('gender'),
            'dob': pan_data.get('dob'),
            'category': pan_data.get('category'),
            'is_minor': pan_data.get('is_minor'),
            'masked_aadhaar': pan_data.get('masked_aadhaar'),
            'aadhaar_linked': pan_data.get('aadhaar_linked'),
            'dob_verified': pan_data.get('dob_verified'),
            'less_info': pan_data.get('less_info'),
        }

        # Update address data
        if 'address' in pan_data and pan_data['address']:
            if isinstance(pan_data['address'], dict):
                new_address = pan_data['address']
            else:
                new_address = {'full': str(pan_data['address'])}

            if record.address_data != new_address:
                changed_fields.append('address_data')
                record.address_data = new_address

        # Update other fields
        for field, new_value in fields_to_update.items():
            if new_value is not None:
                current_value = getattr(record, field)
                if current_value != new_value:
                    changed_fields.append(field)
                    setattr(record, field, new_value)

        # Always update these fields
        record.raw_api_data = pan_data
        record.verification_count += 1
        record.updated_at = datetime.utcnow()
        record.last_verified_at = datetime.utcnow()

        if api_endpoint:
            record.api_endpoint = api_endpoint

        # Log the update if there were changes
        if changed_fields:
            new_values = {field: getattr(record, field) for field in changed_fields}
            old_field_values = {field: old_values.get(field) for field in changed_fields}
            await self._log_audit_action(session, record.id, 'UPDATE', old_field_values, new_values)

        return record

    async def _log_audit_action(self, session: AsyncSession, record_id: int, action: str, old_values: Dict[str, Any], new_values: Dict[str, Any]):
        """Log audit action"""
        try:
            audit_log = DataAuditLog(
                pan_record_id=record_id,
                action=action,
                changed_fields=list(new_values.keys()) if isinstance(new_values, dict) else None,
                old_values=old_values,
                new_values=new_values,
                timestamp=datetime.utcnow()
            )
            session.add(audit_log)
        except Exception as e:
            logger.warning(f"Failed to log audit action: {str(e)}")

    async def search_by_pan(self, pan_number: str) -> Optional[PANRecord]:
        """Search for record by PAN number"""
        if not self.initialized or not DATABASE_ENABLED:
            return None

        try:
            async with self.get_session() as session:
                if session is None:
                    return None

                stmt = select(PANRecord).where(PANRecord.pan_number == pan_number.upper())
                result = await session.execute(stmt)
                record = result.scalar_one_or_none()

                # Log search
                await self._log_search(session, 'pan_number', pan_number, 1 if record else 0)

                return record

        except Exception as e:
            logger.error(f"Error searching by PAN: {str(e)}")
            return None

    async def search_by_name(self, name: str, exact_match: bool = False) -> List[PANRecord]:
        """Search for records by name"""
        if not self.initialized or not DATABASE_ENABLED:
            return []

        try:
            async with self.get_session() as session:
                if session is None:
                    return []

                if exact_match:
                    # Exact match search
                    stmt = select(PANRecord).where(
                        or_(
                            PANRecord.full_name == name,
                            PANRecord.first_name == name,
                            PANRecord.last_name == name
                        )
                    ).limit(MAX_SEARCH_RESULTS)
                else:
                    # Partial match search
                    search_pattern = f"%{name}%"
                    stmt = select(PANRecord).where(
                        or_(
                            PANRecord.full_name.ilike(search_pattern),
                            PANRecord.first_name.ilike(search_pattern),
                            PANRecord.last_name.ilike(search_pattern),
                            PANRecord.father_name.ilike(search_pattern)
                        )
                    ).limit(MAX_SEARCH_RESULTS)

                result = await session.execute(stmt)
                records = result.scalars().all()

                # Log search
                await self._log_search(session, 'name', name, len(records))

                return list(records)

        except Exception as e:
            logger.error(f"Error searching by name: {str(e)}")
            return []

    async def search_by_phone(self, phone_number: str) -> List[PANRecord]:
        """Search for records by phone number"""
        if not self.initialized or not DATABASE_ENABLED:
            return []

        try:
            async with self.get_session() as session:
                if session is None:
                    return []

                stmt = select(PANRecord).where(PANRecord.phone_number == phone_number).limit(MAX_SEARCH_RESULTS)
                result = await session.execute(stmt)
                records = result.scalars().all()

                # Log search
                await self._log_search(session, 'phone_number', phone_number, len(records))

                return list(records)

        except Exception as e:
            logger.error(f"Error searching by phone: {str(e)}")
            return []

    async def search_by_email(self, email: str) -> List[PANRecord]:
        """Search for records by email"""
        if not self.initialized or not DATABASE_ENABLED:
            return []

        try:
            async with self.get_session() as session:
                if session is None:
                    return []

                stmt = select(PANRecord).where(PANRecord.email.ilike(f"%{email}%")).limit(MAX_SEARCH_RESULTS)
                result = await session.execute(stmt)
                records = result.scalars().all()

                # Log search
                await self._log_search(session, 'email', email, len(records))

                return list(records)

        except Exception as e:
            logger.error(f"Error searching by email: {str(e)}")
            return []

    async def get_all_records(self, limit: int = None, offset: int = 0) -> List[PANRecord]:
        """Get all records with pagination"""
        if not self.initialized or not DATABASE_ENABLED:
            return []

        try:
            async with self.get_session() as session:
                if session is None:
                    return []

                stmt = select(PANRecord).order_by(PANRecord.created_at.desc()).offset(offset)
                if limit:
                    stmt = stmt.limit(limit)
                else:
                    stmt = stmt.limit(MAX_SEARCH_RESULTS)

                result = await session.execute(stmt)
                records = result.scalars().all()

                return list(records)

        except Exception as e:
            logger.error(f"Error getting all records: {str(e)}")
            return []

    async def get_statistics(self) -> Dict[str, Any]:
        """Get database statistics"""
        if not self.initialized or not DATABASE_ENABLED:
            return {}

        try:
            async with self.get_session() as session:
                if session is None:
                    return {}

                # Total records
                total_stmt = select(func.count(PANRecord.id))
                total_result = await session.execute(total_stmt)
                total_records = total_result.scalar()

                # Records created today
                today = datetime.utcnow().date()
                today_stmt = select(func.count(PANRecord.id)).where(
                    func.date(PANRecord.created_at) == today
                )
                today_result = await session.execute(today_stmt)
                today_records = today_result.scalar()

                # Most recent record
                recent_stmt = select(PANRecord.created_at).order_by(PANRecord.created_at.desc()).limit(1)
                recent_result = await session.execute(recent_stmt)
                most_recent = recent_result.scalar_one_or_none()

                return {
                    'total_records': total_records,
                    'records_today': today_records,
                    'most_recent_record': most_recent.isoformat() if most_recent else None,
                    'database_enabled': DATABASE_ENABLED,
                    'database_url': DATABASE_URL
                }

        except Exception as e:
            logger.error(f"Error getting statistics: {str(e)}")
            return {}

    async def _log_search(self, session: AsyncSession, search_type: str, query: str, results_count: int):
        """Log search operation"""
        try:
            search_log = SearchHistory(
                search_type=search_type,
                search_query=query,
                results_count=results_count,
                search_timestamp=datetime.utcnow()
            )
            session.add(search_log)
        except Exception as e:
            logger.warning(f"Failed to log search: {str(e)}")

# Global database manager instance
db_manager = DatabaseManager()
