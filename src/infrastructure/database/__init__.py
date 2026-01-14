# -*- coding: utf-8 -*-
"""Database infrastructure: SQLite persistence layer."""

from .db_service import (
    initialize_database,
    save_user_session,
    load_user_session,
    load_all_sessions,
    delete_session,
    delete_expired_sessions,
    get_session_stats,
    optimize_database,
    backup_database,
    migrate_memory_sessions_to_db,
    set_user_role,
    get_user_role,
    get_users_by_role,
    delete_tiered_sessions,
    get_connection,
    compress_data,
    decompress_data,
    VALID_ROLES,
    DEFAULT_ROLE,
    DB_DIR,
    DB_PATH,
)
