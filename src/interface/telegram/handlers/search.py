# -*- coding: utf-8 -*-
"""
Search handler for Deezer content.

Provides functions to search and display artists, albums, tracks,
and manage download initiation from search results.
"""

import logging
import requests
from io import BytesIO
from typing import Dict, List, Any

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery
from telegram.ext import ContextTypes
from deemix.settings import load

from src.interface.telegram.utils.helpers import create_simulated_update


async def search_content(dz, query: str, search_type: str = 'artist', limit: int = 5) -> List[Dict[str, Any]]:
    """
    Searches content in Deezer by type.
    
    Args:
        dz: Deezer client instance
        query: Search term
        search_type: Search type ('artist', 'album', 'track')
        limit: Maximum results to return
        
    Returns:
        List of search results
    """
    try:
        if search_type == 'artist':
            results = dz.api.search_artist(query, limit=limit)
        elif search_type == 'album':
            results = dz.api.search_album(query, limit=limit)
        elif search_type == 'track':
            results = dz.api.search_track(query, limit=limit)
        else:
            return []
        
        return results.get('data', [])
    except Exception as e:
        logging.error(f"Error in {search_type} search: {str(e)}", exc_info=True)
        return []


async def show_search_menu(update, context) -> None:
    """Shows the search options menu."""
    query = update.message.text.strip()
    
    keyboard = [
        [InlineKeyboardButton("🎤 Artistas", callback_data=f"search:artist:{query}")],
        [InlineKeyboardButton("💿 Álbumes", callback_data=f"search:album:{query}")],
        [InlineKeyboardButton("🎵 Canciones", callback_data=f"search:track:{query}")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        f"🔍 *Buscando: {query}*\n\n¿Qué estás buscando?",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )


async def show_artist_results(query: CallbackQuery, results: List[Dict[str, Any]]) -> None:
    """Shows artist search results."""
    keyboard = []
    
    for artist in results[:5]:
        artist_id = artist.get('id')
        artist_name = artist.get('name', 'Desconocido')
        keyboard.append([InlineKeyboardButton(f"🎤 {artist_name}", callback_data=f"artist:{artist_id}")])
    
    original_query = query.message.text.split(": ", 1)[1].split("\n")[0] if ": " in query.message.text else ""
    keyboard.append([InlineKeyboardButton("🔙 Volver", callback_data=f"back:search:{original_query}")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(
        "🎤 *Artistas encontrados:*\n\nSelecciona un artista:",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )


async def show_album_results(query: CallbackQuery, results: List[Dict[str, Any]]) -> None:
    """Shows album search results."""
    keyboard = []
    
    for album in results[:5]:
        album_id = album.get('id')
        album_title = album.get('title', 'Desconocido')
        artist_name = album.get('artist', {}).get('name', 'Desconocido')
        keyboard.append([InlineKeyboardButton(f"💿 {album_title} - {artist_name}", callback_data=f"download:album:{album_id}")])
    
    original_query = query.message.text.split(": ", 1)[1].split("\n")[0] if ": " in query.message.text else ""
    keyboard.append([InlineKeyboardButton("🔙 Volver", callback_data=f"back:search:{original_query}")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(
        "💿 *Álbumes encontrados:*\n\nSelecciona un álbum:",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )


async def show_track_results(query: CallbackQuery, results: List[Dict[str, Any]]) -> None:
    """Shows track search results."""
    keyboard = []
    
    for track in results[:5]:
        track_id = track.get('id')
        track_title = track.get('title', 'Desconocido')
        artist_name = track.get('artist', {}).get('name', 'Desconocido')
        keyboard.append([InlineKeyboardButton(f"🎵 {track_title} - {artist_name}", callback_data=f"download:track:{track_id}")])
    
    original_query = query.message.text.split(": ", 1)[1].split("\n")[0] if ": " in query.message.text else ""
    keyboard.append([InlineKeyboardButton("🔙 Volver", callback_data=f"back:search:{original_query}")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(
        "🎵 *Canciones encontradas:*\n\nSelecciona una canción:",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )


async def show_artist_info(query: CallbackQuery, context: ContextTypes.DEFAULT_TYPE, artist_id: str) -> None:
    """Shows artist information."""
    dz = context.bot_data.get('dz')
    
    try:
        artist_info = dz.api.get_artist(artist_id)
        
        if not artist_info:
            await query.message.reply_text("❌ No se pudo obtener información del artista.")
            return
        
        artist_name = artist_info.get('name', 'Desconocido')
        followers = artist_info.get('nb_fan', 0)
        
        text = f"🎤 *{artist_name}*\n👥 Seguidores: {followers:,}"
        
        keyboard = [
            [InlineKeyboardButton("💿 Álbumes", callback_data=f"artist_menu:{artist_id}:albums")],
            [InlineKeyboardButton("🔝 Top Canciones", callback_data=f"artist_menu:{artist_id}:top")],
            [InlineKeyboardButton("🔙 Volver", callback_data=f"back:search")]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # Try to send with image
        image_sent = False
        if 'picture_big' in artist_info and artist_info['picture_big']:
            try:
                response = requests.get(artist_info['picture_big'])
                if response.status_code == 200:
                    photo = BytesIO(response.content)
                    photo.name = f"artist_{artist_id}.jpg"
                    
                    await query.message.reply_photo(
                        photo=photo,
                        caption=text,
                        reply_markup=reply_markup,
                        parse_mode="Markdown"
                    )
                    image_sent = True
            except Exception as img_error:
                logging.warning(f"Error loading artist image: {img_error}")
        
        if not image_sent:
            try:
                await query.edit_message_text(
                    text=text,
                    reply_markup=reply_markup,
                    parse_mode="Markdown"
                )
            except Exception as edit_error:
                logging.warning(f"Could not edit message: {edit_error}")
                await query.message.reply_text(
                    text=text,
                    reply_markup=reply_markup,
                    parse_mode="Markdown"
                )
        
    except Exception as e:
        logging.error(f"Error getting artist info: {str(e)}", exc_info=True)
        await query.message.reply_text(f"❌ Error: {str(e)}")


async def show_artist_albums(query: CallbackQuery, context: ContextTypes.DEFAULT_TYPE, artist_id: str) -> None:
    """Shows artist albums."""
    dz = context.bot_data.get('dz')
    
    try:
        albums = dz.api.get_artist_albums(artist_id, limit=10)
        
        if not albums or not albums.get('data'):
            await query.message.reply_text("❌ No se encontraron álbumes para este artista.")
            return
        
        keyboard = []
        for album in albums.get('data', []):
            album_id = album.get('id')
            album_title = album.get('title', 'Desconocido')
            keyboard.append([InlineKeyboardButton(f"💿 {album_title}", callback_data=f"download:album:{album_id}")])
        
        keyboard.append([InlineKeyboardButton("🔙 Volver al artista", callback_data=f"back:artist:{artist_id}")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        if hasattr(query.message, 'caption') and query.message.caption:
            await query.message.reply_text(
                "💿 *Álbumes del artista:*\n\nSelecciona un álbum para descargar:",
                reply_markup=reply_markup,
                parse_mode="Markdown"
            )
        else:
            try:
                await query.edit_message_text(
                    "💿 *Álbumes del artista:*\n\nSelecciona un álbum para descargar:",
                    reply_markup=reply_markup,
                    parse_mode="Markdown"
                )
            except Exception as edit_error:
                logging.warning(f"Could not edit message: {edit_error}")
                await query.message.reply_text(
                    "💿 *Álbumes del artista:*\n\nSelecciona un álbum para descargar:",
                    reply_markup=reply_markup,
                    parse_mode="Markdown"
                )
        
    except Exception as e:
        logging.error(f"Error getting albums: {str(e)}", exc_info=True)
        await query.message.reply_text(f"❌ Error: {str(e)}")


async def show_artist_top_tracks(query: CallbackQuery, context: ContextTypes.DEFAULT_TYPE, artist_id: str) -> None:
    """Shows artist top tracks."""
    dz = context.bot_data.get('dz')
    
    try:
        top_tracks = dz.api.get_artist_top_tracks(artist_id, limit=10)
        
        if not top_tracks or not top_tracks.get('data'):
            await query.message.reply_text("❌ No se encontraron canciones para este artista.")
            return
        
        keyboard = []
        for track in top_tracks.get('data', []):
            track_id = track.get('id')
            track_title = track.get('title', 'Desconocido')
            keyboard.append([InlineKeyboardButton(f"🎵 {track_title}", callback_data=f"download:track:{track_id}")])
        
        keyboard.append([InlineKeyboardButton("🔙 Volver al artista", callback_data=f"back:artist:{artist_id}")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        if hasattr(query.message, 'caption') and query.message.caption:
            await query.message.reply_text(
                "🔝 *Top canciones del artista:*\n\nSelecciona una canción para descargar:",
                reply_markup=reply_markup,
                parse_mode="Markdown"
            )
        else:
            try:
                await query.edit_message_text(
                    "🔝 *Top canciones del artista:*\n\nSelecciona una canción para descargar:",
                    reply_markup=reply_markup,
                    parse_mode="Markdown"
                )
            except Exception as edit_error:
                logging.warning(f"Could not edit message: {edit_error}")
                await query.message.reply_text(
                    "🔝 *Top canciones del artista:*\n\nSelecciona una canción para descargar:",
                    reply_markup=reply_markup,
                    parse_mode="Markdown"
                )
        
    except Exception as e:
        logging.error(f"Error getting top tracks: {str(e)}", exc_info=True)
        await query.message.reply_text(f"❌ Error: {str(e)}")


async def start_album_download(query: CallbackQuery, context: ContextTypes.DEFAULT_TYPE, album_id: str) -> None:
    """Starts album download."""
    from src.interface.telegram.handlers.messages import message_manager
    
    dz = context.bot_data.get('dz')
    content_type = "álbum"
    album_info_text = content_type
    track_count = "varias"
    
    try:
        album_info = dz.api.get_album(album_id)
        if album_info:
            album_title = album_info.get('title', 'Álbum sin título')
            artist_name = album_info.get('artist', {}).get('name', 'Artista desconocido')
            album_info_text = f"{album_title} - {artist_name}"
            track_count = album_info.get('nb_tracks', 0)
    except Exception as e:
        logging.warning(f"Could not get album info: {e}")
    
    progress_msg = await message_manager.send_progress(
        None,
        process_type="collection",
        initial_status="processing",
        content_type=content_type,
        query=query,
        track_count=track_count
    )
    
    album_url = f"https://www.deezer.com/album/{album_id}"
    user_id = query.from_user.id
    
    sim_update = create_simulated_update(
        query, 
        context, 
        album_url,
        progress_message=progress_msg,
        from_search=True
    )
    
    sim_update.effective_user.id = user_id
        
    settings = context.bot_data.get('settings', load())
    vault_chat_id = context.bot_data.get('vault_chat_id')
    listener = context.bot_data.get('listener')
    
    from src.interface.telegram.handlers.message_handler import handle_message
    await handle_message(sim_update, context, dz, settings, vault_chat_id, listener)


async def start_track_download(query: CallbackQuery, context: ContextTypes.DEFAULT_TYPE, track_id: str) -> None:
    """Starts track download."""
    from src.interface.telegram.handlers.messages import message_manager
    
    dz = context.bot_data.get('dz')
    track_info_text = "canción"
    
    try:
        track_info = dz.api.get_track(track_id)
        if track_info:
            track_name = track_info.get('title', 'Canción sin título')
            artist_name = track_info.get('artist', {}).get('name', 'Artista desconocido')
            track_info_text = f"{track_name} - {artist_name}"
    except Exception as e:
        logging.warning(f"Could not get track info: {e}")
    
    progress_msg = await message_manager.send_progress(
        None,
        process_type="download",
        initial_status="downloading",
        content_type="canción",
        query=query,
        track_info=track_info_text
    )
    
    track_url = f"https://www.deezer.com/track/{track_id}"
    user_id = query.from_user.id
    
    sim_update = create_simulated_update(
        query, 
        context, 
        track_url,
        progress_message=progress_msg,
        from_search=True
    )
    
    sim_update.effective_user.id = user_id
    
    settings = context.bot_data.get('settings', load())
    vault_chat_id = context.bot_data.get('vault_chat_id')
    listener = context.bot_data.get('listener')
    
    from src.interface.telegram.handlers.message_handler import handle_message
    await handle_message(sim_update, context, dz, settings, vault_chat_id, listener)
