import re
import logging
import os
import shutil
import asyncio
import requests
from io import BytesIO
from typing import List, Union
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaAudio
from telegram.ext import ContextTypes, CallbackContext
from vault import load_vault, save_vault, add_to_vault, get_from_vault
from downloader import download_track, enqueue_download
from deemix.settings import load, save
from user_session import UserSession
from config import (
    BATCH_SIZE,
    TrackFormats,
    DEEZER_TRACK_REGEX,
    DEEZER_ALBUM_REGEX,
    DEEZER_PLAYLIST_REGEX
)
from modules.audio_sender import send_and_save_audio
from modules.track_processor import process_track
from modules.collection_processor import (
    process_collection, process_playlist_in_batches,
    process_small_collection, get_collection_info,
    extract_tracks_info, send_collection_preview
)
# Importar las funciones y clases refactorizadas
from modules.utils import (
    create_simulated_update, safe_edit_message
)
from modules.validation import (
    validate_deezer_url, get_content_type, extract_id_from_url
)
from modules.commands import (
    start, configuracion, config_callback, stats_command
)
# Importar módulos nuevos
from modules.message_handler import handle_message
from modules.search_handler import (
    search_content, show_search_menu, show_artist_results,
    show_album_results, show_track_results, show_artist_info,
    show_artist_albums, show_artist_top_tracks,
    start_album_download, start_track_download
)
from modules.callbacks import (
    process_search_callback, handle_search_callback,
    handle_artist_callback, handle_artist_menu_callback,
    handle_download_callback, handle_back_callback,
    handle_back_to_search
)