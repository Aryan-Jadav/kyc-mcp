"""Google Services Configuration for KYC System"""

import os
from typing import Optional

# Google Services Configuration
GOOGLE_CREDENTIALS_PATH = os.getenv("GOOGLE_CREDENTIALS_PATH", "credentials.json")
GOOGLE_DRIVE_FOLDER_ID = os.getenv("GOOGLE_DRIVE_FOLDER_ID")  # Optional: specific folder

# Google Sheets Configuration
KYC_SPREADSHEET_NAME = os.getenv("KYC_SPREADSHEET_NAME", "KYC_Verification_Database")
GOOGLE_SHEETS_ENABLED = os.getenv("GOOGLE_SHEETS_ENABLED", "true").lower() in ("true", "1", "yes", "on")

# Google Drive Configuration
KYC_DRIVE_FOLDER_NAME = os.getenv("KYC_DRIVE_FOLDER_NAME", "KYC_Documents")
GOOGLE_DRIVE_ENABLED = os.getenv("GOOGLE_DRIVE_ENABLED", "true").lower() in ("true", "1", "yes", "on")

# Storage preferences
STORAGE_TYPE = os.getenv("KYC_STORAGE_TYPE", "google_sheets")  # "google_sheets", "sqlite", "both"
ENABLE_DRIVE_BACKUP = os.getenv("ENABLE_DRIVE_BACKUP", "true").lower() in ("true", "1", "yes", "on")

# Google API Settings
GOOGLE_API_TIMEOUT = int(os.getenv("GOOGLE_API_TIMEOUT", "30"))
GOOGLE_API_RETRIES = int(os.getenv("GOOGLE_API_RETRIES", "3"))

# Data retention settings for Google Drive
DRIVE_DATA_RETENTION_DAYS = int(os.getenv("DRIVE_DATA_RETENTION_DAYS", "365"))  # 1 year default
SHEETS_DATA_RETENTION_DAYS = int(os.getenv("SHEETS_DATA_RETENTION_DAYS", "730"))  # 2 years default

# Performance settings
GOOGLE_BATCH_SIZE = int(os.getenv("GOOGLE_BATCH_SIZE", "100"))
CONCURRENT_GOOGLE_OPERATIONS = int(os.getenv("CONCURRENT_GOOGLE_OPERATIONS", "5"))

# Backup settings
AUTO_BACKUP_ENABLED = os.getenv("AUTO_BACKUP_ENABLED", "true").lower() in ("true", "1", "yes", "on")
BACKUP_FREQUENCY_HOURS = int(os.getenv("BACKUP_FREQUENCY_HOURS", "24"))

# Validation settings
VALIDATE_GOOGLE_CREDENTIALS = os.getenv("VALIDATE_GOOGLE_CREDENTIALS", "true").lower() in ("true", "1", "yes", "on")

# Error handling
MAX_GOOGLE_API_ERRORS = int(os.getenv("MAX_GOOGLE_API_ERRORS", "5"))
GOOGLE_ERROR_COOLDOWN_SECONDS = int(os.getenv("GOOGLE_ERROR_COOLDOWN_SECONDS", "60"))