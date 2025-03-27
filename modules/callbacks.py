import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from modules.search_handler import (
    search_content, show_artist_results, show_album_results, 
    show_track_results, show_artist_info, show_artist_albums,
    show_artist_top_tracks, start_album_download, start_track_download
)

async def process_search_callback(update, context):
    """Procesa los callbacks de los botones de búsqueda."""
    query = update.callback_query
    await query.answer()
    
    data = query.data.split(":")
    action = data[0]
    
    handlers = {
        "search": handle_search_callback,
        "artist": handle_artist_callback,
        "artist_menu": handle_artist_menu_callback,
        "download": handle_download_callback,
        "back": handle_back_callback
    }
    
    if action in handlers:
        await handlers[action](query, context, data)
    else:
        logging.warning(f"Acción desconocida: {action}")

async def handle_search_callback(query, context, data):
    """Maneja la acción de búsqueda."""
    search_type = data[1]
    search_query = data[2]
    
    await query.edit_message_text(f"🔍 Buscando {search_type}: {search_query}...")
    
    dz = context.bot_data.get('dz')
    results = await search_content(dz, search_query, search_type)
    
    if not results:
        await query.edit_message_text(f"❌ No se encontraron resultados para: {search_query}")
        return
    
    # Mostrar resultados según el tipo de búsqueda
    if search_type == "artist":
        await show_artist_results(query, results)
    elif search_type == "album":
        await show_album_results(query, results)
    elif search_type == "track":
        await show_track_results(query, results)

async def handle_artist_callback(query, context, data):
    """Maneja la acción de selección de artista."""
    artist_id = data[1]
    await show_artist_info(query, context, artist_id)

async def handle_artist_menu_callback(query, context, data):
    """Maneja las opciones del menú de artista."""
    artist_id = data[1]
    option = data[2]
    
    if option == "albums":
        await show_artist_albums(query, context, artist_id)
    elif option == "top":
        await show_artist_top_tracks(query, context, artist_id)

async def handle_download_callback(query, context, data):
    """Maneja la acción de descarga desde los resultados de búsqueda."""
    content_type = data[1]
    content_id = data[2]
    
    if content_type == "album":
        await start_album_download(query, context, content_id)
    elif content_type == "track":
        await start_track_download(query, context, content_id)

async def handle_back_callback(query, context, data):
    """Maneja la acción de volver atrás en la navegación."""
    if len(data) > 1:
        back_type = data[1]
        
        if back_type == "search":
            await handle_back_to_search(query, data)
        elif back_type == "artist" and len(data) > 2:
            # Volver a la info del artista
            artist_id = data[2]
            await show_artist_info(query, context, artist_id)

async def handle_back_to_search(query, data):
    """Maneja la acción de volver al menú de búsqueda."""
    search_query = data[2] if len(data) > 2 else "Búsqueda"
    keyboard = [
        [InlineKeyboardButton("🎤 Buscar por Artista", callback_data=f"search:artist:{search_query}")],
        [InlineKeyboardButton("💿 Buscar por Álbum", callback_data=f"search:album:{search_query}")],
        [InlineKeyboardButton("🎵 Buscar por Canción", callback_data=f"search:track:{search_query}")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Intentar editar, si falla, enviar nuevo mensaje
    try:
        await query.edit_message_text(
            f"🔍 *Búsqueda: {search_query}*\n\nSelecciona una opción:",
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )
    except Exception as e:
        logging.warning(f"No se pudo editar el mensaje al volver: {e}")
        await query.message.reply_text(
            f"🔍 *Búsqueda: {search_query}*\n\nSelecciona una opción:",
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )
