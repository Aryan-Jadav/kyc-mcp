"""MySQL configuration for KYC Database"""

import os

# MySQL Database Configuration
MYSQL_CONFIG = {
    'host': os.getenv('MYSQL_HOST', 'localhost'),
    'user': os.getenv('MYSQL_USER', 'root'),
    'password': os.getenv('MYSQL_PASSWORD', ''),
    'database': os.getenv('MYSQL_DATABASE', 'kyc_db'),
    'port': int(os.getenv('MYSQL_PORT', '3306')),
}

# SQLAlchemy URL
MYSQL_URL = f"mysql://{MYSQL_CONFIG['user']}:{MYSQL_CONFIG['password']}@{MYSQL_CONFIG['host']}:{MYSQL_CONFIG['port']}/{MYSQL_CONFIG['database']}"

# Connection Pool Settings
POOL_SIZE = int(os.getenv('MYSQL_POOL_SIZE', '5'))
MAX_OVERFLOW = int(os.getenv('MYSQL_MAX_OVERFLOW', '10'))
POOL_TIMEOUT = int(os.getenv('MYSQL_POOL_TIMEOUT', '30'))
