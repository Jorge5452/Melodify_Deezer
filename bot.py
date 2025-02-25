import re
import logging
import os
import shutil
import asyncio
from typing import List, Union
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CallbackContext
from vault import load_vault, save_vault, add_to_vault, get_from_vault
from downloader import download_track
from deemix.settings import load, save
import requests
from io import BytesIO

# Definir formatos de audio
class TrackFormats:
    FLAC = 9
    MP3_320 = 3
    MP3_128 = 1
    MP4_RA3 = 15
    MP4_RA2 = 14
    MP4_RA1 = 13
    DEFAULT = 8
    LOCAL = 0

# Expresiones regulares para validar URLs de Deezer
DEEZER_TRACK_REGEX = r'(https?://)?(www\.)?deezer\.com/(?:\w{2}/)?track/(\d+)'
DEEZER_ALBUM_REGEX = r'(https?://)?(www\.)?deezer\.com/(?:\w{2}/)?album/(\d+)'
DEEZER_PLAYLIST_REGEX = r'(https?://)?(www\.)?deezer\.com/(?:\w{2}/)?playlist/(\d+)'

def validate_deezer_url(url: str) -> bool:
    """Valida si una URL es una URL válida de Deezer."""
    patterns = [DEEZER_TRACK_REGEX, DEEZER_ALBUM_REGEX, DEEZER_PLAYLIST_REGEX]
    return any(re.match(pattern, url) for pattern in patterns)

def get_content_type(url: str) -> str:
    """Determina el tipo de contenido de una URL de Deezer."""
    if re.match(DEEZER_TRACK_REGEX, url):
        return "track"
    elif re.match(DEEZER_ALBUM_REGEX, url):
        return "album"
    elif re.match(DEEZER_PLAYLIST_REGEX, url):
        return "playlist"
    return "unknown"

def extract_id_from_url(url: str) -> str:
    """Extrae el ID de una URL de Deezer."""
    for pattern in [DEEZER_TRACK_REGEX, DEEZER_ALBUM_REGEX, DEEZER_PLAYLIST_REGEX]:
        match = re.match(pattern, url)
        if match:
            return match.group(3)
    return ""

# Añadir al inicio del archivo, después de las importaciones
BATCH_SIZE = 5  # Número de pistas por lote

# Añadir esta nueva función para procesar playlists grandes por lotes
async def process_playlist_in_batches(update, context, track_urls, track_ids, track_titles, 
                                     dz, settings, listener, vault_chat_id, 
                                     status_message, cache_key, content_type):
    """
    Procesa una playlist grande en lotes.
    """
    total_tracks = len(track_urls)
    total_batches = (total_tracks + BATCH_SIZE - 1) // BATCH_SIZE  # Redondeo hacia arriba
    
    file_ids_all = []
    successful_tracks = 0
    
    for batch_num in range(total_batches):
        start_idx = batch_num * BATCH_SIZE
        end_idx = min(start_idx + BATCH_SIZE, total_tracks)
        
        # Obtener listas para este lote
        batch_urls = track_urls[start_idx:end_idx]
        batch_ids = track_ids[start_idx:end_idx]
        batch_titles = track_titles[start_idx:end_idx]
        
        # Actualizar mensaje de estado
        await status_message.edit_text(
            f"⏳ Lote {batch_num+1}/{total_batches}: Descargando pistas {start_idx+1}-{end_idx} de {total_tracks}..."
        )
        
        # Descargar y enviar pistas de este lote
        file_ids_batch = []
        for i, (track_url, track_id, track_title) in enumerate(zip(batch_urls, batch_ids, batch_titles)):
            try:
                # Índice global para mensajes
                global_idx = start_idx + i
                
                # Definir clave de caché para esta pista
                bitrate = settings.get("maxBitrate", 3)
                individual_cache_key = f"{track_id}_{bitrate}"
                
                # Verificar si esta pista específica está en caché
                cached_track = get_from_vault(individual_cache_key)
                if cached_track:
                    file_ids_batch.append(cached_track)
                    file_ids_all.append(cached_track)
                    await update.message.reply_audio(audio=cached_track)
                    successful_tracks += 1
                    continue
                
                # Actualizar mensaje para esta pista
                await status_message.edit_text(
                    f"⏳ Lote {batch_num+1}/{total_batches}: Descargando pista {global_idx+1}/{total_tracks}...\n"
                    f"🎵 {track_title}"
                )
                
                # Descargar pista individual
                file_path = await download_track(track_url, dz, settings, listener)
                
                # Enviar y guardar en vault
                file_id = await send_and_save_audio(
                    context, 
                    update.message.chat_id, 
                    file_path, 
                    f"{content_type.title()} pista {global_idx+1}/{total_tracks}", 
                    vault_chat_id, 
                    individual_cache_key,
                    dz=dz,
                    track_id=track_id
                )
                
                # Guardar ID en las listas y en vault individual
                file_ids_batch.append(file_id)
                file_ids_all.append(file_id)
                add_to_vault(individual_cache_key, file_id)
                successful_tracks += 1
                
                # Eliminar archivo temporal
                if os.path.exists(file_path):
                    os.remove(file_path)
                
                # Pequeña pausa entre descargas (solo dentro del lote)
                if i < len(batch_urls) - 1:
                    await asyncio.sleep(1)
                    
            except Exception as e:
                logging.error(f"Error descargando pista {start_idx+i+1}: {str(e)}", exc_info=True)
                await update.message.reply_text(f"⚠️ Error con pista {start_idx+i+1}: {track_title}")
        
        # Pequeña pausa entre lotes
        if batch_num < total_batches - 1:
            await asyncio.sleep(3)  # Pausa más larga entre lotes
        
    # Guardar todos los IDs en el vault como playlist/album completo
    if file_ids_all:
        add_to_vault(cache_key, file_ids_all)
        await status_message.edit_text(
            f"✅ {content_type.title()} enviado completamente ({successful_tracks}/{total_tracks} pistas)"
        )
    else:
        await status_message.edit_text(f"❌ No se pudo descargar ninguna pista del {content_type}.")
    
    return file_ids_all

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Maneja el comando /start."""
    help_text = (
        "👋 *¡Bienvenido a MelodifyDeluxe!*\n\n"
        "Puedo descargar música de alta calidad desde Deezer.\n\n"
        "*Comandos disponibles:*\n"
        "• Envía un enlace de Deezer para descargar una canción, álbum o playlist.\n"
        "• /config - Configura la calidad de audio.\n"
        "• /start - Muestra este mensaje de ayuda.\n\n"
        "🔗 *Ejemplo:* https://www.deezer.com/track/3135556"
    )
    await update.message.reply_text(help_text, parse_mode="Markdown")

async def configuracion(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Maneja el comando /config para configurar la calidad de audio."""
    settings = context.bot_data.get('settings', load())
    current_bitrate = settings.get("maxBitrate", 3)
    
    keyboard = [
        [InlineKeyboardButton(f"FLAC (Calidad máxima) {'✅' if current_bitrate == TrackFormats.FLAC else ''}", 
                            callback_data=str(TrackFormats.FLAC))],
        [InlineKeyboardButton(f"MP3 320kbps {'✅' if current_bitrate == TrackFormats.MP3_320 else ''}", 
                            callback_data=str(TrackFormats.MP3_320))],
        [InlineKeyboardButton(f"MP3 128kbps {'✅' if current_bitrate == TrackFormats.MP3_128 else ''}", 
                            callback_data=str(TrackFormats.MP3_128))]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "⚙️ *Configuración de Calidad*\nSelecciona el formato de descarga:",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )

async def config_callback(update: Update, context: CallbackContext):
    """Maneja las respuestas a los botones de configuración."""
    query = update.callback_query
    await query.answer()
    
    new_bitrate = int(query.data)
    settings = context.bot_data.get('settings', load())
    settings["maxBitrate"] = new_bitrate
    context.bot_data['settings'] = settings
    save(settings)  # Guardar configuración en disco
    
    format_name = {
        TrackFormats.FLAC: "FLAC (Calidad máxima)",
        TrackFormats.MP3_320: "MP3 320kbps",
        TrackFormats.MP3_128: "MP3 128kbps"
    }.get(new_bitrate, "Desconocido")
    
    await query.edit_message_text(f"✅ Calidad actualizada a: {format_name}")

async def send_and_save_audio(context, chat_id, file_path, caption, vault_chat_id, key, dz=None, track_id=None):
    """
    Envía un archivo de audio y lo guarda en el vault.
    
    Args:
        context: Contexto del bot
        chat_id: ID del chat donde enviar el audio
        file_path: Ruta al archivo local
        caption: Descripción
        vault_chat_id: ID del chat para almacenar el audio
        key: Clave para el vault
        dz: Objeto Deezer (opcional)
        track_id: ID de la pista de Deezer (opcional)
    
    Returns:
        El file_id del audio enviado
    """
    try:
        # Extraer metadatos si es posible
        title = None
        performer = None
        duration = None
        thumbnail = None  # Cambiado de thumb a thumbnail (nombre correcto)
        
        # Intentar obtener metadatos de Deezer si se proporcionan dz y track_id
        if dz and track_id and str(track_id).isdigit():
            try:
                track_info = dz.api.get_track(track_id)
                if track_info:
                    title = track_info.get('title')
                    performer = track_info.get('artist', {}).get('name')
                    duration = track_info.get('duration')
                    
                    # Obtener URL de la miniatura
                    album_info = track_info.get('album', {})
                    cover_url = album_info.get('cover_medium') or album_info.get('cover_small')
                    
                    if cover_url:
                        # Descargar imagen de carátula
                        response = requests.get(cover_url)
                        if response.status_code == 200:
                            thumbnail = BytesIO(response.content)
                            thumbnail.name = "cover.jpg"
            except Exception as e:
                logging.warning(f"No se pudieron obtener metadatos de Deezer: {str(e)}")
        
        # Si no se pudieron obtener metadatos, extraer del nombre del archivo
        if not title or not performer:
            # Extraer información del nombre del archivo
            filename = os.path.basename(file_path)
            # Quitar extensión
            filename_no_ext = os.path.splitext(filename)[0]
            
            # Intentar hacer parsing si tiene formato "Artista - Título"
            if " - " in filename_no_ext:
                parts = filename_no_ext.split(" - ", 1)
                if not performer:
                    performer = parts[0].strip()
                if not title:
                    title = parts[1].strip()
            else:
                # Si no tiene el formato esperado, usar el nombre como título
                if not title:
                    title = filename_no_ext
        
        # Enviar al canal de vault con metadatos
        with open(file_path, "rb") as f:
            # Preparar argumentos para send_audio
            send_kwargs = {
                "chat_id": vault_chat_id,
                "audio": f,
                "caption": caption,
                "title": title,
                "performer": performer
            }
            
            # Añadir duración si está disponible
            if duration:
                send_kwargs["duration"] = duration
                
            # Añadir miniatura si está disponible (usando el nombre correcto del parámetro)
            if thumbnail:
                send_kwargs["thumbnail"] = thumbnail
                
            sent_message = await context.bot.send_audio(**send_kwargs)
            
        file_id = sent_message.audio.file_id
        
        # Enviar al usuario con el mismo file_id para mantener los metadatos
        await context.bot.send_audio(
            chat_id=chat_id,
            audio=file_id
        )
        
        return file_id
    except Exception as e:
        logging.error(f"Error al enviar audio: {str(e)}", exc_info=True)
        raise

async def handle_message(
    update: Update, 
    context: ContextTypes.DEFAULT_TYPE, 
    dz, 
    settings, 
    vault_chat_id, 
    listener
):
    """Maneja los mensajes entrantes, procesando URLs de Deezer."""
    try:
        url = update.message.text.strip()
        
        # Validar URL
        if not validate_deezer_url(url):
            await update.message.reply_text("🔗 Envía un enlace válido de Deezer (track, album o playlist)")
            return
        
        # Verificar cache en vault
        content_type = get_content_type(url)
        content_id = extract_id_from_url(url)
        
        if content_type == "track":
            bitrate = settings.get("maxBitrate", 3)
            cache_key = f"{content_id}_{bitrate}"
            cached_data = get_from_vault(cache_key)
            
            if cached_data:
                await update.message.reply_text("🎵 Encontrado en caché")
                await update.message.reply_audio(audio=cached_data)
                return
            
            # Notificar inicio de descarga
            status_message = await update.message.reply_text("⏳ Descargando pista...")
            
            # Descargar track
            try:
                file_path = await download_track(url, dz, settings, listener)
                
                # Actualizar estado
                await status_message.edit_text("✅ Descarga completada. Enviando...")
                
                # Enviar y guardar en vault
                file_id = await send_and_save_audio(
                    context, 
                    update.message.chat_id, 
                    file_path, 
                    f"Track: {content_id}", 
                    vault_chat_id, 
                    cache_key,
                    dz=dz,
                    track_id=content_id
                )
                
                # Guardar en vault
                add_to_vault(cache_key, file_id)
                
                # Eliminar archivo temporal
                if os.path.exists(file_path):
                    os.remove(file_path)
                
                # Actualizar mensaje de estado
                await status_message.edit_text("✅ Listo")
                
            except Exception as e:
                logging.error(f"Error al descargar: {str(e)}")
                await status_message.edit_text(f"❌ Error: {str(e)}")
        
        elif content_type in ["album", "playlist"]:
            cache_key = f"{content_type}_{content_id}"
            cached_data = get_from_vault(cache_key)
            
            if cached_data and isinstance(cached_data, list):
                await update.message.reply_text(f"📂 {content_type.title()} encontrado en caché")
                for file_id in cached_data:
                    await update.message.reply_audio(audio=file_id)
                return
            
            # Notificar inicio de descarga
            status_message = await update.message.reply_text(f"⏳ Obteniendo información de {content_type}...")
            
            try:
                # Obtener información del álbum/playlist
                collection_info = None
                if content_type == "album":
                    collection_info = dz.api.get_album(content_id)
                else:  # playlist
                    collection_info = dz.api.get_playlist(content_id)
                
                # Extraer metadatos y URLs de pistas
                track_urls = []
                track_ids = []
                track_titles = []
                
                try:
                    tracks = collection_info.get('tracks', {}).get('data', [])
                    for track in tracks:
                        track_id = track.get('id')
                        if track_id:
                            track_urls.append(f"https://www.deezer.com/track/{track_id}")
                            track_ids.append(str(track_id))
                            artist_name = track.get('artist', {}).get('name', 'Desconocido')
                            track_title = track.get('title', 'Sin título')
                            track_titles.append(f"{artist_name} - {track_title}")
                except Exception as e:
                    logging.warning(f"No se pudo obtener lista de tracks: {str(e)}")
                    # Si falló la obtención de metadatos, intentar descargar la playlist/álbum completo
                    return await download_complete_collection(update, context, url, content_type, content_id, 
                                                            dz, settings, listener, vault_chat_id, cache_key, status_message)
                
                if not track_urls:
                    await status_message.edit_text(f"❌ No se encontraron pistas en el {content_type}.")
                    return
                
                total_tracks = len(track_urls)
                logging.info(f"Pistas encontradas en {content_type}: {total_tracks}")
                
                # Enviar vista previa de la colección
                await send_collection_preview(update, context, collection_info, content_type, total_tracks)
                
                # Actualizar mensaje de estado
                await status_message.edit_text(f"⏳ Procesando {total_tracks} pistas de {content_type}...")
                
                # Determinar si procesar por lotes o individualmente
                if total_tracks > BATCH_SIZE:
                    # Procesar en lotes para playlists grandes
                    await process_playlist_in_batches(update, context, track_urls, track_ids, track_titles, 
                                                     dz, settings, listener, vault_chat_id, 
                                                     status_message, cache_key, content_type)
                else:
                    # Para pocas pistas, procesar individualmente
                    file_ids = []
                    for i, (track_url, track_id, track_title) in enumerate(zip(track_urls, track_ids, track_titles)):
                        try:
                            # Definir clave de caché para esta pista
                            bitrate = settings.get("maxBitrate", 3)
                            individual_cache_key = f"{track_id}_{bitrate}"
                            
                            # Verificar si esta pista específica está en caché
                            cached_track = get_from_vault(individual_cache_key)
                            if cached_track:
                                file_ids.append(cached_track)
                                await update.message.reply_audio(audio=cached_track)
                                continue
                            
                            # Actualizar mensaje de estado
                            await status_message.edit_text(f"⏳ Descargando pista {i+1}/{total_tracks}: {track_title}")
                            
                            # Descargar pista individual
                            file_path = await download_track(track_url, dz, settings, listener)
                            
                            # Enviar y guardar en vault
                            file_id = await send_and_save_audio(
                                context, 
                                update.message.chat_id, 
                                file_path, 
                                f"{content_type.title()} pista {i+1}/{total_tracks}", 
                                vault_chat_id, 
                                individual_cache_key,
                                dz=dz,
                                track_id=track_id
                            )
                            
                            # Guardar ID en la lista y en vault individual
                            file_ids.append(file_id)
                            add_to_vault(individual_cache_key, file_id)
                            
                            # Eliminar archivo temporal
                            if os.path.exists(file_path):
                                os.remove(file_path)
                            
                            # Pequeña pausa entre descargas
                            if i < total_tracks - 1:
                                await asyncio.sleep(1)
                            
                        except Exception as e:
                            logging.error(f"Error descargando pista {i+1}: {str(e)}", exc_info=True)
                            await update.message.reply_text(f"⚠️ Error con pista {i+1}: {track_title}")
                    
                    # Guardar todos los IDs en el vault como playlist/album
                    if file_ids:
                        add_to_vault(cache_key, file_ids)
                        await status_message.edit_text(f"✅ {content_type.title()} enviado completamente ({len(file_ids)}/{total_tracks} pistas)")
                    else:
                        await status_message.edit_text(f"❌ No se pudo descargar ninguna pista del {content_type}.")
            
            except Exception as e:
                logging.error(f"Error al procesar {content_type}: {str(e)}", exc_info=True)
                await status_message.edit_text(f"❌ Error: {str(e)}")
        
        else:
            await update.message.reply_text("🔗 Tipo de contenido no soportado")
            
    except Exception as e:
        logging.error(f"Error crítico: {str(e)}", exc_info=True)
        await update.message.reply_text("⚠️ Error procesando tu solicitud")

async def download_complete_collection(update, context, url, content_type, content_id, 
                                     dz, settings, listener, vault_chat_id, cache_key, status_message):
    """Función de respaldo para intentar descargar una colección completa de una vez."""
    try:
        # Actualizar mensaje
        await status_message.edit_text(f"⏳ Descargando {content_type} completo. Esto puede tardar...")
        
        # Intentar descargar como colección
        file_paths = await download_track(url, dz, settings, listener)
        
        if not isinstance(file_paths, list):
            file_paths = [file_paths]
        
        # Log para depuración
        logging.info(f"Archivos descargados: {len(file_paths)}")
        for fp in file_paths:
            logging.info(f"Archivo: {fp}")
        
        if len(file_paths) == 0:
            await status_message.edit_text(f"❌ No se pudo descargar el {content_type}.")
            return
        
        # Actualizar estado
        await status_message.edit_text(f"✅ Descarga completada. Enviando {len(file_paths)} pistas...")
        
        # Enviar cada pista y guardar IDs
        file_ids = []
        for i, file_path in enumerate(file_paths):
            try:
                if not os.path.exists(file_path):
                    logging.error(f"Archivo no encontrado: {file_path}")
                    continue
                
                # Añadir delay entre envíos
                if i > 0:
                    await asyncio.sleep(1)
                
                file_id = await send_and_save_audio(
                    context, 
                    update.message.chat_id, 
                    file_path, 
                    f"{content_type.title()} track {i+1}/{len(file_paths)}", 
                    vault_chat_id, 
                    f"{cache_key}_{i}",
                    dz=dz,
                    track_id=None  # Aquí no tenemos track_id disponible
                )
                file_ids.append(file_id)
                
                # Eliminar archivo temporal
                if os.path.exists(file_path):
                    os.remove(file_path)
                
            except Exception as e:
                logging.error(f"Error enviando pista {i+1}: {str(e)}", exc_info=True)
                await update.message.reply_text(f"⚠️ Error enviando pista {i+1}")
        
        # Guardar todos los IDs en el vault
        if file_ids:
            add_to_vault(cache_key, file_ids)
            await status_message.edit_text(f"✅ {content_type.title()} enviado completamente")
        else:
            await status_message.edit_text(f"❌ No se pudo enviar ninguna pista del {content_type}.")
            
    except Exception as e:
        logging.error(f"Error en download_complete_collection: {str(e)}", exc_info=True)
        await status_message.edit_text(f"❌ Error: {str(e)}")

# Función para descargar y enviar la vista previa de playlist/álbum
async def send_collection_preview(update, context, collection_info, content_type, total_tracks):
    """
    Envía una vista previa de la playlist o álbum con su carátula e información.
    
    Args:
        update: Objeto Update de Telegram
        context: Contexto del bot
        collection_info: Información de la colección (playlist/álbum)
        content_type: Tipo de contenido ('playlist' o 'album')
        total_tracks: Número total de pistas
    """
    try:
        # Determinar URL de la imagen según el tipo de contenido
        image_url = None
        title = collection_info.get('title', 'Sin título')
        
        if content_type == 'album':
            image_url = collection_info.get('cover_big') or collection_info.get('cover_medium')
            artist_name = collection_info.get('artist', {}).get('name', 'Artista desconocido')
            caption = f"🎵 Álbum: {title}\n👤 Artista: {artist_name}\n🔢 Pistas: {total_tracks}"
        else:  # playlist
            image_url = collection_info.get('picture_big') or collection_info.get('picture_medium')
            creator = collection_info.get('creator', {}).get('name', 'Creador desconocido')
            caption = f"🎵 Playlist: {title}\n👤 Creador: {creator}\n🔢 Pistas: {total_tracks}"
        
        # Si no hay URL de imagen, enviar solo mensaje de texto
        if not image_url:
            await update.message.reply_text(caption)
            return
        
        # Descargar imagen
        response = requests.get(image_url)
        if response.status_code != 200:
            # Si falla la descarga de imagen, enviar solo texto
            await update.message.reply_text(caption)
            return
        
        # Crear objeto de bytes para la imagen
        image_data = BytesIO(response.content)
        image_data.name = f"{content_type}_cover.jpg"
        
        # Enviar imagen con caption
        await context.bot.send_photo(
            chat_id=update.message.chat_id,
            photo=image_data,
            caption=caption
        )
        
    except Exception as e:
        logging.error(f"Error enviando vista previa: {str(e)}", exc_info=True)
        # Si falla, intentar enviar al menos el texto
        try:
            await update.message.reply_text(f"🎵 {content_type.title()}: {collection_info.get('title', 'Sin título')}\n🔢 Pistas: {total_tracks}")
        except:
            pass