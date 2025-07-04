"""Updated Universal Database Manager with Google Sheets Integration"""

import json
import logging
from datetime import datetime
from typing import Optional, Dict, Any, List

from config_db import DATABASE_ENABLED
from google_config import GOOGLE_SHEETS_ENABLED, STORAGE_TYPE

# Import Google Sheets managers with error handling
try:
    from universal_google_sheets import universal_google_sheets_manager
    from google_drive_storage import google_drive_storage
except ImportError:
    universal_google_sheets_manager = None
    google_drive_storage = None

logger = logging.getLogger("kyc-universal-database")

class HybridUniversalDatabaseManager:
    """Hybrid universal database manager with Google Sheets support"""
    
    def __init__(self):
        self.storage_type = STORAGE_TYPE
        self.google_sheets_enabled = GOOGLE_SHEETS_ENABLED and DATABASE_ENABLED
        self.initialized = False
        
        # Set primary storage backend with null check
        if (self.storage_type == "google_sheets" and 
            self.google_sheets_enabled and 
            universal_google_sheets_manager is not None):
            self.primary_db = universal_google_sheets_manager
            self.drive_storage = google_drive_storage
            logger.info("Using Google Sheets as primary universal storage")
        else:
            # Fallback to mock manager
            self.primary_db = MockUniversalDatabaseManager()
            self.drive_storage = None
            if universal_google_sheets_manager is None:
                logger.warning("Google Sheets universal manager not available, using mock database")
            else:
                logger.info("Using mock universal database manager (Google Sheets disabled)")
    
    async def initialize(self):
        """Initialize the universal database manager"""
        if not DATABASE_ENABLED:
            logger.info("Universal database storage is disabled")
            return
            
        try:
            await self.primary_db.initialize()
            
            # Initialize Google Drive if enabled and available
            if self.drive_storage and hasattr(self.drive_storage, 'initialize'):
                await self.drive_storage.initialize()
                logger.info("Google Drive storage initialized")
            
            self.initialized = True
            logger.info("Hybrid universal database manager initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize universal database manager: {str(e)}")
            raise
    
    async def close(self):
        """Close database connections"""
        if hasattr(self.primary_db, 'close'):
            await self.primary_db.close()
        
        if self.drive_storage and hasattr(self.drive_storage, 'close'):
            await self.drive_storage.close()
        
        logger.info("Universal database connections closed")
    
    async def store_verification_data(self, verification_data: Dict[str, Any], api_endpoint: str, verification_type: str) -> Optional[Dict[str, Any]]:
        """Store verification data with optional Drive backup"""
        if not self.initialized:
            return None
            
        try:
            # Store in primary database (Google Sheets)
            result = await self.primary_db.store_verification_data(verification_data, api_endpoint, verification_type)
            
            # Store backup in Google Drive if enabled and available
            if self.drive_storage and result and hasattr(self.drive_storage, 'store_verification_report'):
                record_id = str(result.get('id', 'unknown'))
                
                try:
                    # Store verification report
                    await self.drive_storage.store_verification_report(
                        verification_data, verification_type, record_id
                    )
                    
                    # Store raw API response
                    await self.drive_storage.store_raw_api_response(
                        verification_data, api_endpoint, record_id
                    )
                    logger.info(f"Stored backup files in Google Drive for record {record_id}")
                except Exception as drive_error:
                    logger.warning(f"Failed to store backup in Google Drive: {str(drive_error)}")
            
            return result
            
        except Exception as e:
            logger.error(f"Error storing verification data: {str(e)}")
            return None
    
    async def search_record(self, search_type: str, search_value: str) -> List[Dict[str, Any]]:
        """Search records"""
        if not self.initialized:
            return []
        return await self.primary_db.search_record(search_type, search_value)
    
    async def search_person_by_identifier(self, identifier_type: str, value: str) -> List[Dict[str, Any]]:
        """Search persons by identifier"""
        if not self.initialized:
            return []
        return await self.primary_db.search_person_by_identifier(identifier_type, value)
    
    async def get_person_complete_profile(self, person_id: int) -> Optional[Dict[str, Any]]:
        """Get complete person profile"""
        if not self.initialized:
            return None
        return await self.primary_db.get_person_complete_profile(person_id)

class MockUniversalDatabaseManager:
    """Mock universal database manager for when Google Sheets is disabled"""
    
    def __init__(self):
        self.initialized = False
    
    async def initialize(self):
        self.initialized = True
        logger.info("Mock universal database manager initialized")
    
    async def close(self):
        logger.info("Mock universal database manager closed")
    
    async def store_verification_data(self, verification_data: Dict[str, Any], api_endpoint: str, verification_type: str):
        logger.warning("Mock database: Verification data not stored (Google Sheets disabled)")
        return None
    
    async def search_record(self, search_type: str, search_value: str):
        logger.warning("Mock database: Search not available (Google Sheets disabled)")
        return []
    
    async def search_person_by_identifier(self, identifier_type: str, value: str):
        logger.warning("Mock database: Search not available (Google Sheets disabled)")
        return []
    
    async def get_person_complete_profile(self, person_id: int):
        logger.warning("Mock database: Profile not available (Google Sheets disabled)")
        return None

# Compatibility function for existing code
async def store_universal_verification_data(verification_data: Dict[str, Any], api_endpoint: str) -> Optional[Dict[str, Any]]:
    """Store verification data (compatibility function)"""
    verification_type = api_endpoint.strip("/").split("/")[-1]  # Extract type from endpoint
    return await universal_db_manager.store_verification_data(verification_data, api_endpoint, verification_type)

# Global instance
universal_db_manager = HybridUniversalDatabaseManager()