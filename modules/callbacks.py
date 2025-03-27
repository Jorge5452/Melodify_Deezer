import logging
from typing import List, Dict, Any, Callable, Awaitable
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery
from telegram.ext import ContextTypes, CallbackContext
from modules.search_handler import (
    search_content, show_artist_results, show_album_results, 
    show_track_results, show_artist_info, show_artist_albums,
    show_artist_top_tracks, start_album_download, start_track_download
)

async def process_search_callback(update: Any, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Procesa los callbacks de los botones de búsqueda.
    
    Función principal que evalúa y dirige los callbacks a las funciones
    adecuadas según el tipo de acción solicitada.
    
    Args:
        update: Objeto Update con información del callback
        context: Contexto del manejador de callbacks
    
    Note:
        Los datos de callback siguen el formato "accion:parámetro1:parámetro2..."
    """
    query = update.callback_query
    await query.answer()
    
    # Dividir los datos en partes usando ":" como separador
    data = query.data.split(":")
    action = data[0]
    
    # Mapeo de acciones a funciones de manejo
    handlers: Dict[str, Callable[[CallbackQuery, ContextTypes.DEFAULT_TYPE, List[str]], Awaitable[None]]] = {
        "search": handle_search_callback,
        "artist": handle_artist_callback,
        "artist_menu": handle_artist_menu_callback,
        "download": handle_download_callback,
        "back": handle_back_callback
    }
    
    # Ejecutar el manejador correspondiente si existe
    if action in handlers:
        await handlers[action](query, context, data)
    else:
        logging.warning(f"Acción desconocida: {action}")

async def handle_search_callback(query: CallbackQuery, context: ContextTypes.DEFAULT_TYPE, data: List[str]) -> None:
    """
    Maneja la acción de búsqueda.
    
    Procesa solicitudes de búsqueda y muestra resultados según
    el tipo de contenido buscado (artista, álbum, canción).
    
    Args:
        query: Objeto CallbackQuery de Telegram
        context: Contexto del bot
        data: Lista con los datos del callback ["search", tipo_busqueda, término_búsqueda]
        
    Note:
        Formato de data esperado: ["search", "artist|album|track", "término_búsqueda"]
    """
    # Extraer tipo y término de búsqueda
    search_type = data[1]  # "artist", "album" o "track"
    search_query = data[2]  # Término de búsqueda
    
    # Mostrar mensaje de búsqueda en curso
    await query.edit_message_text(f"🔍 Buscando {search_type}: {search_query}...")
    
    # Obtener cliente Deezer del contexto
    dz = context.bot_data.get('dz')
    
    # Realizar búsqueda
    results = await search_content(dz, search_query, search_type)
    
    # Verificar resultados
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

async def handle_artist_callback(query: CallbackQuery, context: ContextTypes.DEFAULT_TYPE, data: List[str]) -> None:
    """
    Maneja la acción de selección de artista.
    
    Muestra información detallada de un artista específico cuando
    el usuario selecciona un artista de los resultados.
    
    Args:
        query: Objeto CallbackQuery de Telegram
        context: Contexto del bot
        data: Lista con los datos del callback ["artist", id_artista]
        
    Note:
        Formato de data esperado: ["artist", "id_artista"]
    """
    # Extraer ID del artista
    artist_id = data[1]
    
    # Mostrar información del artista
    await show_artist_info(query, context, artist_id)

async def handle_artist_menu_callback(query: CallbackQuery, context: ContextTypes.DEFAULT_TYPE, data: List[str]) -> None:
    """
    Maneja las opciones del menú de artista.
    
    Procesa las selecciones realizadas en el menú de un artista,
    como ver álbumes o canciones populares.
    
    Args:
        query: Objeto CallbackQuery de Telegram
        context: Contexto del bot
        data: Lista con los datos del callback ["artist_menu", id_artista, opción]
        
    Note:
        Formato de data esperado: ["artist_menu", "id_artista", "albums|top"]
    """
    # Extraer datos
    artist_id = data[1]
    option = data[2]  # "albums" o "top"
    
    # Procesar según la opción seleccionada
    if option == "albums":
        await show_artist_albums(query, context, artist_id)
    elif option == "top":
        await show_artist_top_tracks(query, context, artist_id)

async def handle_download_callback(query: CallbackQuery, context: ContextTypes.DEFAULT_TYPE, data: List[str]) -> None:
    """
    Maneja la acción de descarga desde los resultados de búsqueda.
    
    Inicia el proceso de descarga del contenido seleccionado por el usuario.
    
    Args:
        query: Objeto CallbackQuery de Telegram
        context: Contexto del bot
        data: Lista con los datos del callback ["download", tipo_contenido, id_contenido]
        
    Note:
        Formato de data esperado: ["download", "album|track", "id_contenido"]
    """
    # Extraer tipo e ID del contenido
    content_type = data[1]  # "album" o "track"
    content_id = data[2]
    
    # Iniciar descarga según el tipo de contenido
    if content_type == "album":
        await start_album_download(query, context, content_id)
    elif content_type == "track":
        await start_track_download(query, context, content_id)

async def handle_back_callback(query: CallbackQuery, context: ContextTypes.DEFAULT_TYPE, data: List[str]) -> None:
    """
    Maneja la acción de volver atrás en la navegación.
    
    Permite al usuario regresar a la pantalla anterior en la navegación
    de resultados de búsqueda o información de artista.
    
    Args:
        query: Objeto CallbackQuery de Telegram
        context: Contexto del bot
        data: Lista con los datos del callback ["back", tipo_retorno, id_opcional]
        
    Note:
        Formato de data esperado: ["back", "search|artist", "id_opcional"]
    """
    if len(data) > 1:
        back_type = data[1]
        
        if back_type == "search":
            await handle_back_to_search(query, data)
        elif back_type == "artist" and len(data) > 2:
            # Volver a la info del artista
            artist_id = data[2]
            await show_artist_info(query, context, artist_id)

async def handle_back_to_search(query: CallbackQuery, data: List[str]) -> None:
    """
    Maneja la acción de volver al menú de búsqueda.
    
    Permite al usuario regresar al menú principal de búsqueda
    para realizar una nueva búsqueda.
    
    Args:
        query: Objeto CallbackQuery de Telegram
        data: Lista con los datos del callback ["back", "search", término_búsqueda]
        
    Note:
        Formato de data esperado: ["back", "search", "término_búsqueda"]
    """
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
