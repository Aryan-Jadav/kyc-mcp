"""Database management for KYC MCP Server with Google Sheets Integration"""

import json
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List, Tuple, Union

from config_db import DATABASE_ENABLED
from google_config import GOOGLE_SHEETS_ENABLED, STORAGE_TYPE

# Import both database managers with error handling
try:
    from google_sheets_database import google_sheets_db_manager
except ImportError:
    google_sheets_db_manager = None

logger = logging.getLogger("kyc-database")

class HybridDatabaseManager:
    """Hybrid database manager that can use Google Sheets or SQL based on configuration"""
    
    def __init__(self):
        self.storage_type = STORAGE_TYPE
        self.google_sheets_enabled = GOOGLE_SHEETS_ENABLED and DATABASE_ENABLED
        self.initialized = False
        
        # Set primary storage backend with null check
        if (self.storage_type == "google_sheets" and 
            self.google_sheets_enabled and 
            google_sheets_db_manager is not None):
            self.primary_db = google_sheets_db_manager
            logger.info("Using Google Sheets as primary storage")
        else:
            # Fallback to mock manager
            self.primary_db = MockDatabaseManager()
            if google_sheets_db_manager is None:
                logger.warning("Google Sheets manager not available, using mock database")
            else:
                logger.info("Using mock database manager (Google Sheets disabled)")
    
    async def initialize(self):
        """Initialize the database manager"""
        if not DATABASE_ENABLED:
            logger.info("Database storage is disabled")
            return
            
        try:
            await self.primary_db.initialize()
            self.initialized = True
            logger.info("Hybrid database manager initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize database manager: {str(e)}")
            raise
    
    async def close(self):
        """Close database connections"""
        if hasattr(self.primary_db, 'close'):
            await self.primary_db.close()
        logger.info("Database connections closed")
    
    # Delegate all methods to the primary database manager
    async def store_pan_data(self, pan_data: Dict[str, Any], api_endpoint: str = None):
        """Store PAN data"""
        if not self.initialized:
            return None
        return await self.primary_db.store_pan_data(pan_data, api_endpoint)
    
    async def search_by_pan(self, pan_number: str):
        """Search by PAN number"""
        if not self.initialized:
            return None
        return await self.primary_db.search_by_pan(pan_number)
    
    async def search_by_name(self, name: str, exact_match: bool = False):
        """Search by name"""
        if not self.initialized:
            return []
        return await self.primary_db.search_by_name(name, exact_match)
    
    async def search_by_phone(self, phone_number: str):
        """Search by phone number"""
        if not self.initialized:
            return []
        return await self.primary_db.search_by_phone(phone_number)
    
    async def search_by_email(self, email: str):
        """Search by email"""
        if not self.initialized:
            return []
        return await self.primary_db.search_by_email(email)
    
    async def get_all_records(self, limit: int = None, offset: int = 0):
        """Get all records"""
        if not self.initialized:
            return []
        return await self.primary_db.get_all_records(limit, offset)
    
    async def get_statistics(self):
        """Get database statistics"""
        if not self.initialized:
            return {}
        return await self.primary_db.get_statistics()

class MockDatabaseManager:
    """Mock database manager for when Google Sheets is disabled"""
    
    def __init__(self):
        self.initialized = False
    
    async def initialize(self):
        self.initialized = True
        logger.info("Mock database manager initialized")
    
    async def close(self):
        logger.info("Mock database manager closed")
    
    async def store_pan_data(self, pan_data: Dict[str, Any], api_endpoint: str = None):
        logger.warning("Mock database: PAN data not stored (Google Sheets disabled)")
        return None
    
    async def search_by_pan(self, pan_number: str):
        logger.warning("Mock database: Search not available (Google Sheets disabled)")
        return None
    
    async def search_by_name(self, name: str, exact_match: bool = False):
        logger.warning("Mock database: Search not available (Google Sheets disabled)")
        return []
    
    async def search_by_phone(self, phone_number: str):
        logger.warning("Mock database: Search not available (Google Sheets disabled)")
        return []
    
    async def search_by_email(self, email: str):
        logger.warning("Mock database: Search not available (Google Sheets disabled)")
        return []
    
    async def get_all_records(self, limit: int = None, offset: int = 0):
        logger.warning("Mock database: No records available (Google Sheets disabled)")
        return []
    
    async def get_statistics(self):
        logger.warning("Mock database: No statistics available (Google Sheets disabled)")
        return {
            'total_records': 0,
            'records_today': 0,
            'most_recent_record': None,
            'database_enabled': False,
            'storage_type': 'disabled'
        }

# Global database manager instance
db_manager = HybridDatabaseManager()