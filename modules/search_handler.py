import logging
import requests
from io import BytesIO
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from modules.utils import create_simulated_update
from deemix.settings import load

async def search_content(dz, query, search_type='artist', limit=5):
    """
    Realiza una búsqueda en Deezer por artista, álbum o canción.
    
    Args:
        dz: Instancia de Deezer
        query: Término de búsqueda
        search_type: Tipo de búsqueda ('artist', 'album', 'track')
        limit: Número máximo de resultados
        
    Returns:
        Lista de resultados
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
        logging.error(f"Error en búsqueda de {search_type}: {str(e)}", exc_info=True)
        return []

async def show_search_menu(update, context):
    """Muestra el menú de opciones de búsqueda."""
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

async def show_artist_results(query, results):
    """Muestra los resultados de búsqueda de artistas."""
    keyboard = []
    
    for artist in results[:5]:  # Limitamos a 5 resultados
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

async def show_album_results(query, results):
    """Muestra los resultados de búsqueda de álbumes."""
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

async def show_track_results(query, results):
    """Muestra los resultados de búsqueda de canciones."""
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

async def show_artist_info(query, context, artist_id):
    """Muestra la información del artista."""
    dz = context.bot_data.get('dz')
    
    try:
        artist_info = dz.api.get_artist(artist_id)
        
        if not artist_info:
            # En lugar de editar, enviamos un nuevo mensaje
            await query.message.reply_text("❌ No se pudo obtener información del artista.")
            return
        
        artist_name = artist_info.get('name', 'Desconocido')
        followers = artist_info.get('nb_fan', 0)
        
        # Crear texto con la información
        text = f"🎤 *{artist_name}*\n👥 Seguidores: {followers:,}"
        
        # Crear el teclado con opciones
        keyboard = [
            [InlineKeyboardButton("💿 Álbumes", callback_data=f"artist_menu:{artist_id}:albums")],
            [InlineKeyboardButton("🔝 Top Canciones", callback_data=f"artist_menu:{artist_id}:top")],
            [InlineKeyboardButton("🔙 Volver", callback_data=f"back:search")]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # Si hay imagen, enviamos una foto
        image_sent = False
        if 'picture_big' in artist_info and artist_info['picture_big']:
            try:
                response = requests.get(artist_info['picture_big'])
                if response.status_code == 200:
                    photo = BytesIO(response.content)
                    photo.name = f"artist_{artist_id}.jpg"
                    
                    # Enviamos la foto como un nuevo mensaje
                    await query.message.reply_photo(
                        photo=photo,
                        caption=text,
                        reply_markup=reply_markup,
                        parse_mode="Markdown"
                    )
                    image_sent = True
            except Exception as img_error:
                logging.warning(f"Error al cargar la imagen del artista: {img_error}")
        
        # Si no enviamos imagen, actualizamos el mensaje de texto o enviamos uno nuevo
        if not image_sent:
            try:
                await query.edit_message_text(
                    text=text,
                    reply_markup=reply_markup,
                    parse_mode="Markdown"
                )
            except Exception as edit_error:
                logging.warning(f"No se pudo editar el mensaje: {edit_error}")
                await query.message.reply_text(
                    text=text,
                    reply_markup=reply_markup,
                    parse_mode="Markdown"
                )
        
    except Exception as e:
        logging.error(f"Error obteniendo info del artista: {str(e)}", exc_info=True)
        await query.message.reply_text(f"❌ Error: {str(e)}")

async def show_artist_albums(query, context, artist_id):
    """Muestra los álbumes del artista."""
    dz = context.bot_data.get('dz')
    
    try:
        albums = dz.api.get_artist_albums(artist_id, limit=10)
        
        if not albums or not albums.get('data'):
            # En lugar de editar el mensaje, enviamos uno nuevo
            await query.message.reply_text("❌ No se encontraron álbumes para este artista.")
            return
        
        keyboard = []
        for album in albums.get('data', []):
            album_id = album.get('id')
            album_title = album.get('title', 'Desconocido')
            keyboard.append([InlineKeyboardButton(f"💿 {album_title}", callback_data=f"download:album:{album_id}")])
        
        keyboard.append([InlineKeyboardButton("🔙 Volver al artista", callback_data=f"back:artist:{artist_id}")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # Verificamos si el mensaje contiene una foto (tiene caption) o es texto
        if hasattr(query.message, 'caption') and query.message.caption:
            # Si es un mensaje con foto, enviamos un nuevo mensaje en lugar de editar
            await query.message.reply_text(
                "💿 *Álbumes del artista:*\n\nSelecciona un álbum para descargar:",
                reply_markup=reply_markup,
                parse_mode="Markdown"
            )
        else:
            # Si es un mensaje normal, lo editamos
            try:
                await query.edit_message_text(
                    "💿 *Álbumes del artista:*\n\nSelecciona un álbum para descargar:",
                    reply_markup=reply_markup,
                    parse_mode="Markdown"
                )
            except Exception as edit_error:
                # Si falla la edición, enviamos un nuevo mensaje
                logging.warning(f"No se pudo editar el mensaje: {edit_error}")
                await query.message.reply_text(
                    "💿 *Álbumes del artista:*\n\nSelecciona un álbum para descargar:",
                    reply_markup=reply_markup,
                    parse_mode="Markdown"
                )
        
    except Exception as e:
        logging.error(f"Error obteniendo álbumes: {str(e)}", exc_info=True)
        # Enviamos un nuevo mensaje en lugar de editar
        await query.message.reply_text(f"❌ Error: {str(e)}")

async def show_artist_top_tracks(query, context, artist_id):
    """Muestra las canciones más populares del artista."""
    dz = context.bot_data.get('dz')
    
    try:
        top_tracks = dz.api.get_artist_top_tracks(artist_id, limit=10)
        
        if not top_tracks or not top_tracks.get('data'):
            # En lugar de editar el mensaje, enviamos uno nuevo
            await query.message.reply_text("❌ No se encontraron canciones para este artista.")
            return
        
        keyboard = []
        for track in top_tracks.get('data', []):
            track_id = track.get('id')
            track_title = track.get('title', 'Desconocido')
            keyboard.append([InlineKeyboardButton(f"🎵 {track_title}", callback_data=f"download:track:{track_id}")])
        
        keyboard.append([InlineKeyboardButton("🔙 Volver al artista", callback_data=f"back:artist:{artist_id}")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # Verificamos si el mensaje contiene una foto (tiene caption) o es texto
        if hasattr(query.message, 'caption') and query.message.caption:
            # Si es un mensaje con foto, enviamos un nuevo mensaje en lugar de editar
            await query.message.reply_text(
                "🔝 *Top canciones del artista:*\n\nSelecciona una canción para descargar:",
                reply_markup=reply_markup,
                parse_mode="Markdown"
            )
        else:
            # Si es un mensaje normal, lo editamos
            try:
                await query.edit_message_text(
                    "🔝 *Top canciones del artista:*\n\nSelecciona una canción para descargar:",
                    reply_markup=reply_markup,
                    parse_mode="Markdown"
                )
            except Exception as edit_error:
                # Si falla la edición, enviamos un nuevo mensaje
                logging.warning(f"No se pudo editar el mensaje: {edit_error}")
                await query.message.reply_text(
                    "🔝 *Top canciones del artista:*\n\nSelecciona una canción para descargar:",
                    reply_markup=reply_markup,
                    parse_mode="Markdown"
                )
        
    except Exception as e:
        logging.error(f"Error obteniendo top tracks: {str(e)}", exc_info=True)
        # Enviamos un nuevo mensaje en lugar de editar
        await query.message.reply_text(f"❌ Error: {str(e)}")

async def start_album_download(query, context, album_id):
    """Inicia la descarga de un álbum."""
    # Importar message_manager aquí para evitar importaciones circulares
    from modules.message_manager import message_manager
    
    # Obtener información del álbum para mostrar más detalles
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
        logging.warning(f"No se pudo obtener información del álbum: {e}")
    
    # Crear mensaje de progreso para la descarga
    progress_msg = await message_manager.send_progress(
        None,  # No tenemos un update real
        process_type="collection",
        initial_status="processing",  # Usar processing que es más apropiado para colecciones
        content_type=content_type,
        query=query,  # Pasar el query para editar el mensaje existente
        track_count=track_count
    )
    
    # Generar URL de Deezer para el álbum
    album_url = f"https://www.deezer.com/album/{album_id}"
  
    # Obtener user_id para las estadísticas
    user_id = query.from_user.id
    
    # Crear objeto Update simulado con el mensaje de progreso
    sim_update = create_simulated_update(
        query, 
        context, 
        album_url,
        progress_message=progress_msg,
        from_search=True  # Indicar que este update viene de una búsqueda
    )
    
    # Configurar user_id en effective_user que ya existe en el SimulatedUpdate
    sim_update.effective_user.id = user_id
        
    # Obtener componentes para handle_message
    dz = context.bot_data.get('dz')
    settings = context.bot_data.get('settings', load())
    vault_chat_id = context.bot_data.get('vault_chat_id')
    listener = context.bot_data.get('listener')
    
    # Importar handle_message aquí para evitar importaciones circulares
    from modules.message_handler import handle_message
    
    # Ejecutar handle_message con la URL del álbum
    await handle_message(sim_update, context, dz, settings, vault_chat_id, listener)

async def start_track_download(query, context, track_id):
    """Inicia la descarga de una canción."""
    # Importar message_manager aquí para evitar importaciones circulares
    from modules.message_manager import message_manager
    
    # Obtener información de la pista para mostrar más detalles
    dz = context.bot_data.get('dz')
    track_info_text = "canción"
    try:
        track_info = dz.api.get_track(track_id)
        if track_info:
            track_name = track_info.get('title', 'Canción sin título')
            artist_name = track_info.get('artist', {}).get('name', 'Artista desconocido')
            track_info_text = f"{track_name} - {artist_name}"
    except Exception as e:
        logging.warning(f"No se pudo obtener información de la pista: {e}")
        
    # Crear mensaje de progreso para la descarga en lugar de editar directamente
    # Usamos directamente el estado "downloading" para evitar la transición innecesaria
    progress_msg = await message_manager.send_progress(
        None,  # No tenemos un update real
        process_type="download",
        initial_status="downloading",  # Usar "downloading" en lugar de "starting"
        content_type="canción",
        query=query,  # Pasar el query para editar el mensaje existente
        track_info=track_info_text
    )
    
    # Generar URL de Deezer para la canción
    track_url = f"https://www.deezer.com/track/{track_id}"
    
    # Obtener user_id para las estadísticas
    user_id = query.from_user.id
    
    # Crear objeto Update simulado con el mensaje de progreso
    sim_update = create_simulated_update(
        query, 
        context, 
        track_url,
        progress_message=progress_msg,
        from_search=True  # Indicar que este update viene de una búsqueda
    )
    
    # Configurar user_id en effective_user que ya existe en el SimulatedUpdate
    sim_update.effective_user.id = user_id
    
    # Obtener componentes para handle_message
    dz = context.bot_data.get('dz')
    settings = context.bot_data.get('settings', load())
    vault_chat_id = context.bot_data.get('vault_chat_id')
    listener = context.bot_data.get('listener')
    
    # Importar handle_message aquí para evitar importaciones circulares
    from modules.message_handler import handle_message
    
    # Ejecutar handle_message con la URL de la canción
    await handle_message(sim_update, context, dz, settings, vault_chat_id, listener)
