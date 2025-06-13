"""Database configuration for KYC MCP Server"""

import os
from typing import Optional

# Database Configuration
DATABASE_URL = os.getenv("KYC_DATABASE_URL", "sqlite+aiosqlite:///kyc_data.db")
DATABASE_ENABLED = os.getenv("KYC_DATABASE_ENABLED", "true").lower() in ("true", "1", "yes", "on")

# Database settings
DATABASE_SETTINGS = {
    "echo": os.getenv("KYC_DATABASE_ECHO", "false").lower() in ("true", "1", "yes", "on"),
    "pool_pre_ping": True,
    "pool_recycle": 3600,  # 1 hour
}

# Data retention settings (in days)
DATA_RETENTION_DAYS = int(os.getenv("KYC_DATA_RETENTION_DAYS", "365"))  # 1 year default

# Privacy settings
ENABLE_DATA_ANONYMIZATION = os.getenv("KYC_ENABLE_DATA_ANONYMIZATION", "false").lower() in ("true", "1", "yes", "on")
ANONYMIZE_AFTER_DAYS = int(os.getenv("KYC_ANONYMIZE_AFTER_DAYS", "90"))  # 3 months default

# Search settings
MAX_SEARCH_RESULTS = int(os.getenv("KYC_MAX_SEARCH_RESULTS", "100"))
ENABLE_FUZZY_SEARCH = os.getenv("KYC_ENABLE_FUZZY_SEARCH", "true").lower() in ("true", "1", "yes", "on")

# Backup settings
ENABLE_AUTO_BACKUP = os.getenv("KYC_ENABLE_AUTO_BACKUP", "false").lower() in ("true", "1", "yes", "on")
BACKUP_INTERVAL_HOURS = int(os.getenv("KYC_BACKUP_INTERVAL_HOURS", "24"))
BACKUP_RETENTION_DAYS = int(os.getenv("KYC_BACKUP_RETENTION_DAYS", "30"))

# Performance settings
BATCH_SIZE = int(os.getenv("KYC_BATCH_SIZE", "1000"))
CONNECTION_TIMEOUT = int(os.getenv("KYC_CONNECTION_TIMEOUT", "30"))
