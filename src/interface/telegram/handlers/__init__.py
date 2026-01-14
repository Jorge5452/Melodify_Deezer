# -*- coding: utf-8 -*-
"""
Telegram handlers package.

Exports all command and message handlers for the bot.
"""

# Commands
from src.interface.telegram.handlers.commands import (
    start,
    configuracion,
    config_callback,
    stats_command,
)

# Admin commands
from src.interface.telegram.handlers.admin import (
    admin_help,
    cmd_set_role,
    set_role_user_id,
    set_role_confirm,
    set_user_role,
    cancel_conversation,
    cmd_user_info,
    admin_stats,
    handle_admin_callback,
    cmd_maintenance,
    cmd_broadcast,
    cmd_system,
    broadcast_confirm,
    cmd_session_stats,
    WAITING_FOR_USER_ID,
    WAITING_FOR_ROLE,
)

# Premium commands
from src.interface.telegram.handlers.premium import (
    premium_help,
    premium_stats,
    premium_audio_options,
    handle_premium_callback,
    process_download_queue,
)

# Message handling
from src.interface.telegram.handlers.message_handler import handle_message
from src.interface.telegram.handlers.messages import (
    message_manager,
    ProgressMessage,
    MessageManager,
    safe_edit_message,
    delete_message_safe,
)

# Track and collection processors
from src.interface.telegram.handlers.track import process_track
from src.interface.telegram.handlers.collection import (
    process_collection,
    get_collection_info,
    extract_tracks_info,
    send_collection_preview,
    CollectionProcessingError,
    EmptyCollectionError,
    TrackNotAvailableError,
)

# Search
from src.interface.telegram.handlers.search import (
    search_content,
    show_search_menu,
    show_artist_results,
    show_album_results,
    show_track_results,
    show_artist_info,
    show_artist_albums,
    show_artist_top_tracks,
    start_album_download,
    start_track_download,
)

# Audio
from src.interface.telegram.handlers.audio import send_and_save_audio

__all__ = [
    # Commands
    "start",
    "configuracion",
    "config_callback",
    "stats_command",
    # Admin
    "admin_help",
    "cmd_set_role",
    "set_role_user_id",
    "set_role_confirm",
    "set_user_role",
    "cancel_conversation",
    "cmd_user_info",
    "admin_stats",
    "handle_admin_callback",
    "cmd_maintenance",
    "cmd_broadcast",
    "cmd_system",
    "broadcast_confirm",
    "cmd_session_stats",
    "WAITING_FOR_USER_ID",
    "WAITING_FOR_ROLE",
    # Premium
    "premium_help",
    "premium_stats",
    "premium_audio_options",
    "handle_premium_callback",
    "process_download_queue",
    # Messages
    "handle_message",
    "message_manager",
    "ProgressMessage",
    "MessageManager",
    "safe_edit_message",
    "delete_message_safe",
    # Processors
    "process_track",
    "process_collection",
    "get_collection_info",
    "extract_tracks_info",
    "send_collection_preview",
    # Search
    "search_content",
    "show_search_menu",
    "show_artist_results",
    "show_album_results",
    "show_track_results",
    "show_artist_info",
    "show_artist_albums",
    "show_artist_top_tracks",
    "start_album_download",
    "start_track_download",
    # Audio
    "send_and_save_audio",
    # Exceptions
    "CollectionProcessingError",
    "EmptyCollectionError",
    "TrackNotAvailableError",
]
