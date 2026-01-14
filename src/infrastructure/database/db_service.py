# -*- coding: utf-8 -*-
"""
Database service for user session persistence.

This module implements an abstraction layer over SQLite
for handling persistent storage of sessions.
"""

import sqlite3
import json
import time
import logging
import os
import zlib
from typing import Dict, Any, Optional, List, Tuple
from contextlib import contextmanager

from src.config import (
    COMPRESSION_THRESHOLD,
    SESSION_TIMEOUT,
    SESSION_TIERS
)

# Database configuration
DB_DIR = "./data"
DB_PATH = f"{DB_DIR}/melodify_sessions.db"

# Valid system roles
VALID_ROLES = ["normal", "premium", "admin"]
DEFAULT_ROLE = "normal"

# Ensure directory exists
os.makedirs(DB_DIR, exist_ok=True)


def compress_data(data_dict: Dict[str, Any]) -> Tuple[bytes, bool]:
    """
    Compresses a dictionary if it exceeds the configured threshold.
    
    Args:
        data_dict: Dictionary to compress
        
    Returns:
        Tuple (compressed_data, is_compressed)
    """
    json_str = json.dumps(data_dict)
    
    # Compress only if exceeds threshold
    if len(json_str) > COMPRESSION_THRESHOLD:
        compressed = zlib.compress(json_str.encode())
        return compressed, True
    
    # Return uncompressed
    return json_str.encode(), False


def decompress_data(data: bytes, is_compressed: bool) -> Dict[str, Any]:
    """
    Decompresses data if necessary and converts to dictionary.
    
    Args:
        data: Data to decompress
        is_compressed: Indicator if data is compressed
        
    Returns:
        Dictionary with decompressed data
    """
    if is_compressed:
        json_str = zlib.decompress(data).decode()
    else:
        json_str = data.decode()
        
    return json.loads(json_str)


@contextmanager
def get_connection():
    """
    Manages the SQLite database connection.
    
    Establishes a connection with optimizations and closes it automatically
    when the context ends.
    """
    conn = None
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row  # Allows accessing columns by name
        conn.execute("PRAGMA journal_mode=WAL")  # Improves write performance
        conn.execute("PRAGMA synchronous=NORMAL")  # Balance between safety/performance
        yield conn
    except Exception as e:
        logging.error(f"Database connection error: {str(e)}", exc_info=True)
        raise
    finally:
        if conn:
            conn.close()


def initialize_database() -> bool:
    """
    Creates necessary tables if they don't exist.
    
    This function must be called before using any
    other function in this module.
    
    Returns:
        True if initialization was successful, False otherwise
    """
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            
            # User sessions table
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                settings TEXT NOT NULL,
                last_activity REAL NOT NULL,
                context_data BLOB,
                context_data_compressed INTEGER DEFAULT 0,
                total_downloads INTEGER DEFAULT 0,
                active_downloads INTEGER DEFAULT 0,
                role TEXT DEFAULT 'normal',
                monthly_downloads INTEGER DEFAULT 0,
                current_month INTEGER DEFAULT 0,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL
            )
            ''')
            
            # Index for activity searches
            cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_last_activity ON users(last_activity)
            ''')
            
            # Index for role searches
            cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_role ON users(role)
            ''')
            
            # Verify if necessary columns exist in the table
            cursor.execute("PRAGMA table_info(users)")
            columns = {col[1] for col in cursor.fetchall()}
            
            # Add columns if they don't exist
            if 'role' not in columns:
                logging.info("Adding 'role' column to users table")
                cursor.execute("ALTER TABLE users ADD COLUMN role TEXT DEFAULT 'normal'")
                
            if 'context_data_compressed' not in columns:
                logging.info("Adding 'context_data_compressed' column for compression support")
                cursor.execute("ALTER TABLE users ADD COLUMN context_data_compressed INTEGER DEFAULT 0")
                
            if 'monthly_downloads' not in columns:
                logging.info("Adding 'monthly_downloads' column to users table")
                cursor.execute("ALTER TABLE users ADD COLUMN monthly_downloads INTEGER DEFAULT 0")
                
            if 'current_month' not in columns:
                logging.info("Adding 'current_month' column to users table")
                cursor.execute("ALTER TABLE users ADD COLUMN current_month INTEGER DEFAULT 0")
                
            conn.commit()
            logging.info("Database initialized successfully")
            
            # Verify if table was created with expected structure
            cursor.execute("PRAGMA table_info(users)")
            columns = {col[1] for col in cursor.fetchall()}
            expected_columns = {
                "user_id", "settings", "last_activity", "context_data", 
                "context_data_compressed", "total_downloads", "active_downloads", 
                "role", "monthly_downloads", "current_month", 
                "created_at", "updated_at"
            }
            
            if not expected_columns.issubset(columns):
                missing = expected_columns - columns
                logging.warning(f"Missing columns in users table: {missing}")
                
        return True
    except Exception as e:
        logging.error(f"Error initializing database: {e}", exc_info=True)
        return False


def save_user_session(user_id: int, session_data: Dict[str, Any]) -> bool:
    """
    Saves a user session to the database.
    If the context is large, it compresses automatically.
    
    Args:
        user_id: User ID
        session_data: Dictionary with session data
        
    Returns:
        True if operation was successful, False otherwise
    """
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            now = time.time()
            
            # Convert dictionaries to JSON for storage
            settings_json = json.dumps(session_data.get("settings", {}))
            
            # Apply compression to context_data if necessary
            context_data = session_data.get("context_data", {})
            context_bytes, is_compressed = compress_data(context_data)
            
            # Ensure role is valid
            role = session_data.get("role", DEFAULT_ROLE)
            print(role)
            if role not in VALID_ROLES:
                role = DEFAULT_ROLE
            
            # Insert or update record (UPSERT)
            cursor.execute('''
            INSERT OR REPLACE INTO users 
            (user_id, settings, last_activity, context_data, context_data_compressed,
            total_downloads, active_downloads, role, monthly_downloads, current_month,
            created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                user_id,
                settings_json,
                session_data.get("last_activity", now),
                sqlite3.Binary(context_bytes),  # Possibly compressed data
                1 if is_compressed else 0,      # Compression indicator
                session_data.get("total_downloads", 0),
                session_data.get("active_downloads", 0),
                role,
                session_data.get("monthly_downloads", 0),
                session_data.get("current_month", 0),
                session_data.get("created_at", now),
                now  # updated_at is always current time
            ))
            conn.commit()
            return True
    except sqlite3.OperationalError as e:
        if "database is locked" in str(e):
            logging.warning(f"Database locked when saving session {user_id}, retrying...")
            time.sleep(0.5)  # Brief pause before retry
            return save_user_session(user_id, session_data)  # Retry once
        logging.error(f"Operational error saving session for user {user_id}: {e}", exc_info=True)
        return False
    except Exception as e:
        logging.error(f"Error saving session for user {user_id}: {e}", exc_info=True)
        return False


def load_user_session(user_id: int) -> Optional[Dict[str, Any]]:
    """
    Loads a user session from the database.
    Decompresses data if necessary.
    
    Args:
        user_id: User ID
        
    Returns:
        Dictionary with session data or None if not found
    """
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute('''
            SELECT * FROM users WHERE user_id = ?
            ''', (user_id,))
            
            row = cursor.fetchone()
            if not row:
                return None
                
            # Determine if data is compressed
            is_compressed = bool(row["context_data_compressed"]) if "context_data_compressed" in row.keys() else False
            
            # Decompress if necessary
            context_data = {}
            if row["context_data"]:
                try:
                    context_data = decompress_data(row["context_data"], is_compressed)
                except Exception as e:
                    logging.error(f"Error decompressing data for user {user_id}: {e}", exc_info=True)
            
            # Convert back to dictionary with JSON deserialization
            return {
                "user_id": row["user_id"],
                "settings": json.loads(row["settings"]),
                "last_activity": row["last_activity"],
                "context_data": context_data,
                "total_downloads": row["total_downloads"],
                "active_downloads": row["active_downloads"],
                "role": row["role"] if "role" in row.keys() else DEFAULT_ROLE,
                "monthly_downloads": row["monthly_downloads"] if "monthly_downloads" in row.keys() else 0,
                "current_month": row["current_month"] if "current_month" in row.keys() else 0,
                "created_at": row["created_at"],
                "updated_at": row["updated_at"]
            }
    except Exception as e:
        logging.error(f"Error loading session for user {user_id}: {e}", exc_info=True)
        return None


def load_all_sessions() -> Dict[int, Dict[str, Any]]:
    """
    Loads all user sessions from the database.
    
    For large databases, consider using pagination.
    
    Returns:
        Dictionary with all sessions (user_id: session_data)
    """
    sessions = {}
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            
            # Limit to 1000 results to avoid memory issues
            cursor.execute('''
            SELECT * FROM users 
            ORDER BY last_activity DESC 
            LIMIT 1000
            ''')
            
            for row in cursor.fetchall():
                user_id = row["user_id"]
                try:
                    sessions[user_id] = {
                        "user_id": user_id,
                        "settings": json.loads(row["settings"]),
                        "last_activity": row["last_activity"],
                        "context_data": json.loads(row["context_data"]) if row["context_data"] else {},
                        "total_downloads": row["total_downloads"],
                        "active_downloads": row["active_downloads"],
                        "role": row["role"] if "role" in row.keys() else DEFAULT_ROLE,
                        "created_at": row["created_at"],
                        "updated_at": row["updated_at"]
                    }
                except json.JSONDecodeError:
                    logging.error(f"Error decoding JSON for user {user_id}")
                    # Skip this session and continue with others
                    continue
                
        logging.info(f"Loaded {len(sessions)} sessions from database")
        return sessions
    except Exception as e:
        logging.error(f"Error loading all sessions: {e}", exc_info=True)
        return {}


def delete_session(user_id: int) -> bool:
    """
    Deletes a user session from the database.
    
    Args:
        user_id: User ID
        
    Returns:
        True if deleted successfully, False otherwise
    """
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM users WHERE user_id = ?", (user_id,))
            conn.commit()
            return cursor.rowcount > 0
    except Exception as e:
        logging.error(f"Error deleting session for user {user_id}: {e}", exc_info=True)
        return False


def delete_expired_sessions(timeout_seconds: int) -> int:
    """
    Deletes expired sessions from the database.
    
    Args:
        timeout_seconds: Maximum inactivity time in seconds
        
    Returns:
        Number of sessions deleted
    """
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cutoff = time.time() - timeout_seconds
            cursor.execute("DELETE FROM users WHERE last_activity < ?", (cutoff,))
            deleted_count = cursor.rowcount
            conn.commit()
            if deleted_count > 0:
                logging.info(f"Deleted {deleted_count} expired sessions from database")
            return deleted_count
    except Exception as e:
        logging.error(f"Error deleting expired sessions: {e}", exc_info=True)
        return 0


def get_session_stats() -> Dict[str, Any]:
    """
    Gets statistics of stored sessions.
    
    Returns:
        Dictionary with general statistics
    """
    stats = {
        'total_sessions': 0,
        'active_last_hour': 0,
        'active_last_day': 0,
        'total_downloads': 0,
        'oldest_session': None,
        'newest_session': None
    }
    
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            
            # Total sessions
            cursor.execute('SELECT COUNT(*) FROM users')
            stats['total_sessions'] = cursor.fetchone()[0]
            
            # Active in last hour
            hour_ago = time.time() - 3600
            cursor.execute('SELECT COUNT(*) FROM users WHERE last_activity > ?', (hour_ago,))
            stats['active_last_hour'] = cursor.fetchone()[0]
            
            # Active in last day
            day_ago = time.time() - 86400
            cursor.execute('SELECT COUNT(*) FROM users WHERE last_activity > ?', (day_ago,))
            stats['active_last_day'] = cursor.fetchone()[0]
            
            # Total downloads
            cursor.execute('SELECT SUM(total_downloads) FROM users')
            result = cursor.fetchone()[0]
            stats['total_downloads'] = result if result is not None else 0
            
            # Oldest session
            cursor.execute('SELECT MIN(created_at) FROM users')
            stats['oldest_session'] = cursor.fetchone()[0]
            
            # Newest session
            cursor.execute('SELECT MAX(created_at) FROM users')
            stats['newest_session'] = cursor.fetchone()[0]
            
        return stats
    except Exception as e:
        logging.error(f"Error getting session statistics: {e}", exc_info=True)
        return stats


def optimize_database() -> bool:
    """
    Optimizes the database by removing unused space.
    
    This operation may take time on large databases.
    
    Returns:
        True if operation was successful, False otherwise
    """
    try:
        with get_connection() as conn:
            conn.execute("VACUUM")
            conn.execute("ANALYZE")
            logging.info("Database optimized successfully")
            return True
    except Exception as e:
        logging.error(f"Error optimizing database: {e}", exc_info=True)
        return False


def backup_database(backup_path: Optional[str] = None) -> bool:
    """
    Creates a backup of the database.
    
    Args:
        backup_path: Path for backup file. If None,
                    generates a path with timestamp.
        
    Returns:
        True if operation was successful, False otherwise
    """
    if not backup_path:
        backup_path = f"{DB_PATH}.backup-{int(time.time())}"
        
    try:
        # Verify destination directory exists
        backup_dir = os.path.dirname(backup_path)
        if backup_dir:
            os.makedirs(backup_dir, exist_ok=True)
            
        with get_connection() as conn:
            backup = sqlite3.connect(backup_path)
            conn.backup(backup)
            backup.close()
            
        logging.info(f"Database backup created at {backup_path}")
        return True
    except Exception as e:
        logging.error(f"Error creating database backup: {e}", exc_info=True)
        return False


def migrate_memory_sessions_to_db(sessions_dict: Dict[int, Any]) -> int:
    """
    Migrates in-memory sessions to the database.
    
    Args:
        sessions_dict: Dictionary with sessions (user_id: UserSession)
        
    Returns:
        Number of sessions migrated successfully
    """
    migrated = 0
    current_time = time.time()
    
    for user_id, session in sessions_dict.items():
        try:
            # Create dictionary with relevant session data
            session_data = {
                "settings": session.settings,
                "last_activity": session.last_activity,
                "context_data": session.context_data,
                "total_downloads": session.total_downloads,
                "active_downloads": getattr(session, "active_downloads", 0),
                "created_at": getattr(session, "created_at", current_time),
                "updated_at": current_time
            }
            
            if save_user_session(user_id, session_data):
                migrated += 1
        except Exception as e:
            logging.error(f"Error migrating session {user_id}: {e}", exc_info=True)
    
    if migrated > 0:        
        logging.info(f"Migrated {migrated} of {len(sessions_dict)} sessions to database")
    return migrated 


def set_user_role(user_id: int, role: str) -> bool:
    """
    Updates a user's role in the database.
    
    Args:
        user_id: User ID
        role: New role (must be one of VALID_ROLES)
        
    Returns:
        True if updated successfully, False otherwise
    """
    if role not in VALID_ROLES:
        logging.error(f"Invalid role: {role}. Must be one of: {VALID_ROLES}")
        return False
        
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            # Check if user exists
            cursor.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
            if not cursor.fetchone():
                logging.warning(f"User {user_id} does not exist in database")
                return False
                
            # Update role
            cursor.execute(
                "UPDATE users SET role = ?, updated_at = ? WHERE user_id = ?",
                (role, time.time(), user_id)
            )
            conn.commit()
            logging.info(f"User {user_id} role updated to {role}")
            return True
    except Exception as e:
        logging.error(f"Error updating role for user {user_id}: {e}", exc_info=True)
        return False
        

def get_user_role(user_id: int) -> Optional[str]:
    """
    Gets a user's role from the database.
    
    Args:
        user_id: User ID
        
    Returns:
        User's role or None if not found
    """
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT role FROM users WHERE user_id = ?", 
                (user_id,)
            )
            row = cursor.fetchone()
            if row and "role" in row.keys():
                return row["role"]
            return DEFAULT_ROLE
    except Exception as e:
        logging.error(f"Error getting role for user {user_id}: {e}", exc_info=True)
        return DEFAULT_ROLE


def get_users_by_role(role: str) -> List[int]:
    """
    Gets a list of users with a specific role.
    
    Args:
        role: Role to search for
        
    Returns:
        List of user IDs with that role
    """
    users = []
    if role not in VALID_ROLES:
        logging.error(f"Invalid role: {role}. Must be one of: {VALID_ROLES}")
        return users
        
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT user_id FROM users WHERE role = ?", (role,))
            for row in cursor.fetchall():
                users.append(row["user_id"])
            return users
    except Exception as e:
        logging.error(f"Error getting users with role {role}: {e}", exc_info=True)
        return users 


def delete_tiered_sessions(tier_timeouts: Dict[str, int]) -> int:
    """
    Deletes expired sessions from DB respecting different times per role.
    
    Args:
        tier_timeouts: Dictionary with expiration times per role
        
    Returns:
        Number of sessions deleted
    """
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            now = time.time()
            deleted = 0
            
            # Delete sessions for each role type with its specific time
            for role, timeout in tier_timeouts.items():
                expire_time = now - timeout
                cursor.execute('''
                DELETE FROM users 
                WHERE role = ? AND last_activity < ?
                ''', (role, expire_time))
                deleted += cursor.rowcount
            
            # Delete any session with unknown role using default time
            expire_time = now - SESSION_TIMEOUT
            cursor.execute('''
            DELETE FROM users 
            WHERE role NOT IN ({}) AND last_activity < ?
            '''.format(','.join(['?'] * len(tier_timeouts))), 
            (*tier_timeouts.keys(), expire_time))
            
            deleted += cursor.rowcount
            conn.commit()
            
            return deleted
    except Exception as e:
        logging.error(f"Error deleting expired sessions: {e}", exc_info=True)
        return 0
