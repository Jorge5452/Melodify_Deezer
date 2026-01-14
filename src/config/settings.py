# -*- coding: utf-8 -*-
"""
Settings module: Environment variables and runtime configuration.

This module loads environment variables and defines runtime settings.
"""

import os
from typing import Dict, List
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# ----- API TOKENS AND KEYS -----
# Telegram Bot API Token
TELEGRAM_TOKEN: str = os.environ.get("TELEGRAM_TOKEN", "")
# Deezer ARL (Authentication Renewal Login) for Deezer authentication
DEEZER_ARL: str = os.environ.get("DEEZER_AR", "")
# Chat ID for storing files in the "vault"
VAULT_CHATID: str = os.environ.get("VAULT_CHATID", "")

# ----- PATHS AND DIRECTORIES -----
# Directory for downloads
DOWNLOAD_PATH: str = "./descargas"

# ----- RATE LIMITS -----
# Maximum requests per user within the time window
RATE_LIMIT_MAX_REQUESTS: int = 5
# Time window in seconds for rate limiting
RATE_LIMIT_TIME_WINDOW: int = 60
# Maximum concurrent downloads per user
MAX_CONCURRENT_DOWNLOADS_PER_USER: int = 2
# Global concurrent downloads limit
MAX_CONCURRENT_DOWNLOADS_GLOBAL: int = 10

# ----- TIMEOUTS AND EXPIRATION -----
# Session timeout in seconds (1 hour)
SESSION_TIMEOUT: int = 3600
# Session cleanup interval in seconds (10 minutes)
SESSION_CLEANUP_INTERVAL: int = 600

# ----- SESSION MANAGEMENT -----
# Maximum sessions kept in memory
SESSION_CACHE_SIZE: int = 100
# Expiration times per role (seconds)
SESSION_TIERS: Dict[str, int] = {
    "admin": 86400,     # 24 hours for admins
    "premium": 43200,   # 12 hours for premium users
    "normal": 3600      # 1 hour for regular users
}
# Byte threshold for data compression
COMPRESSION_THRESHOLD: int = 1024
# DB operations before flush
DB_BATCH_SIZE: int = 10
# Time between DB flushes (seconds)
DB_FLUSH_INTERVAL: int = 5
# Monthly download limit for regular users
MONTHLY_DOWNLOAD_LIMIT: int = 50
# Role hierarchy (lowest to highest)
ROLES_HIERARCHY: List[str] = ["normal", "premium", "admin"]

# ----- LOGGING -----
# Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
LOG_LEVEL: str = "WARNING"
# Log message format
LOG_FORMAT: str = "%(asctime)s - %(levelname)s - %(message)s"

# ----- HTTP TIMEOUTS -----
HTTP_CONNECT_TIMEOUT = float(os.getenv("HTTP_CONNECT_TIMEOUT", "20.0"))
HTTP_READ_TIMEOUT = float(os.getenv("HTTP_READ_TIMEOUT", "300.0"))
HTTP_WRITE_TIMEOUT = float(os.getenv("HTTP_WRITE_TIMEOUT", "300.0"))

# ----- RETRY CONFIGURATION -----
MAX_RETRIES = int(os.getenv("MAX_RETRIES", "3"))
INITIAL_RETRY_DELAY = float(os.getenv("INITIAL_RETRY_DELAY", "2.0"))
RETRY_BACKOFF_FACTOR = float(os.getenv("RETRY_BACKOFF_FACTOR", "2.0"))
