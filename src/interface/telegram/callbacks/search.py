# -*- coding: utf-8 -*-
"""
Callback handlers for search-related interactions.

Processes callbacks from inline keyboard buttons in search results
and navigation.
"""

import logging
from typing import List, Dict, Callable, Awaitable

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery, Update
from telegram.ext import ContextTypes

from src.interface.telegram.utils.decorators import (
    with_error_handling,
    with_callback_error_handling,
    with_callback_user_session,
)


@with_error_handling
async def process_search_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Processes search button callbacks.
    
    Main function that evaluates and directs callbacks to appropriate
    functions based on the requested action type.
    
    Args:
        update: Update object with callback information
        context: Callback handler context
    
    Note:
        Callback data follows the format "action:param1:param2..."
    """
    # Import here to avoid circular imports
    from src.interface.telegram.handlers.search import (
        search_content, show_artist_results, show_album_results,
        show_track_results, show_artist_info, show_artist_albums,
        show_artist_top_tracks, start_album_download, start_track_download
    )
    
    query = update.callback_query
    await query.answer()
    
    # Split data using ":" as separator
    data = query.data.split(":")
    action = data[0]
    
    # Action to handler mapping
    if action == "search":
        await _handle_search_callback(query, context, data)
    elif action == "artist":
        await _handle_artist_callback(query, context, data)
    elif action == "artist_menu":
        await _handle_artist_menu_callback(query, context, data)
    elif action == "download":
        await _handle_download_callback(query, context, data)
    elif action == "back":
        await _handle_back_callback(query, context, data)
    else:
        logging.warning(f"Unknown action: {action}")


@with_callback_error_handling
async def _handle_search_callback(query: CallbackQuery, context: ContextTypes.DEFAULT_TYPE, data: List[str]) -> None:
    """Handles search action."""
    from src.interface.telegram.handlers.search import (
        search_content, show_artist_results, show_album_results, show_track_results
    )
    
    search_type = data[1]
    search_query = data[2]
    
    await query.edit_message_text(f"🔍 Buscando {search_type}...")
    
    dz = context.bot_data.get('dz')
    results = await search_content(dz, search_query, search_type)
    
    if not results:
        await query.edit_message_text(f"❌ No encontré resultados para '{search_query}'")
        return
    
    if search_type == "artist":
        await show_artist_results(query, results)
    elif search_type == "album":
        await show_album_results(query, results)
    elif search_type == "track":
        await show_track_results(query, results)


@with_callback_error_handling
async def _handle_artist_callback(query: CallbackQuery, context: ContextTypes.DEFAULT_TYPE, data: List[str]) -> None:
    """Handles artist selection action."""
    from src.interface.telegram.handlers.search import show_artist_info
    
    artist_id = data[1]
    await show_artist_info(query, context, artist_id)


@with_callback_error_handling
async def _handle_artist_menu_callback(query: CallbackQuery, context: ContextTypes.DEFAULT_TYPE, data: List[str]) -> None:
    """Handles artist menu options."""
    from src.interface.telegram.handlers.search import show_artist_albums, show_artist_top_tracks
    
    artist_id = data[1]
    option = data[2]
    
    if option == "albums":
        await show_artist_albums(query, context, artist_id)
    elif option == "top":
        await show_artist_top_tracks(query, context, artist_id)


@with_callback_error_handling
@with_callback_user_session
async def _handle_download_callback(query: CallbackQuery, context: ContextTypes.DEFAULT_TYPE, data: List[str]) -> None:
    """Handles download action from search results."""
    from src.interface.telegram.handlers.search import start_album_download, start_track_download
    
    content_type = data[1]
    content_id = data[2]
    
    if content_type == "album":
        await start_album_download(query, context, content_id)
    elif content_type == "track":
        await start_track_download(query, context, content_id)


@with_callback_error_handling
async def _handle_back_callback(query: CallbackQuery, context: ContextTypes.DEFAULT_TYPE, data: List[str]) -> None:
    """Handles back navigation action."""
    from src.interface.telegram.handlers.search import show_artist_info
    
    if len(data) > 1:
        back_type = data[1]
        
        if back_type == "search":
            await _handle_back_to_search(query, data)
        elif back_type == "artist" and len(data) > 2:
            artist_id = data[2]
            await show_artist_info(query, context, artist_id)


@with_callback_error_handling
async def _handle_back_to_search(query: CallbackQuery, data: List[str]) -> None:
    """Handles back to search menu action."""
    search_query = data[2] if len(data) > 2 else "Búsqueda"
    keyboard = [
        [InlineKeyboardButton("🎤 Buscar por Artista", callback_data=f"search:artist:{search_query}")],
        [InlineKeyboardButton("💿 Buscar por Álbum", callback_data=f"search:album:{search_query}")],
        [InlineKeyboardButton("🎵 Buscar por Canción", callback_data=f"search:track:{search_query}")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        f"🔍 *Búsqueda de música*\n\n"
        f"Término de búsqueda: *{search_query}*\n\n"
        f"Selecciona el tipo de búsqueda:",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )
