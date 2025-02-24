import re
import logging
import os
import shutil
from typing import List, Union
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CallbackContext
from vault import load_vault, save_vault, add_to_vault, get_from_vault
from downloader import download_track
from deemix.settings import load, save

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
        
        # Intentar obtener metadatos de Deezer si se proporcionan dz y track_id
        if dz and track_id and str(track_id).isdigit():
            try:
                track_info = dz.api.get_track(track_id)
                if track_info:
                    title = track_info.get('title')
                    performer = track_info.get('artist', {}).get('name')
                    duration = track_info.get('duration')
                    logging.info(f"Obtenidos metadatos de Deezer: {title} - {performer}")
            except Exception as e:
                logging.warning(f"No se pudieron obtener metadatos de Deezer: {str(e)}")
        
        # Si no se pudieron obtener metadatos, extraer del nombre del archivo
        if not title or not performer:
            # Extraer información del nombre del archivo
            import os
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
            
            logging.info(f"Extraídos metadatos del nombre: {title} - {performer}")
        
        # Enviar al canal de vault con metadatos
        with open(file_path, "rb") as f:
            sent_message = await context.bot.send_audio(
                chat_id=vault_chat_id,
                audio=f,
                caption=caption,
                title=title,
                performer=performer,
                duration=duration
            )
        file_id = sent_message.audio.file_id
        
        # Enviar al usuario con el mismo file_id para mantener los metadatos
        await context.bot.send_audio(
            chat_id=chat_id,
            audio=file_id
        )
        
        return file_id
    except Exception as e:
        logging.error(f"Error al enviar audio: {str(e)}")
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
            status_message = await update.message.reply_text(f"⏳ Descargando {content_type}. Esto puede tardar...")
            
            try:
                # Obtener información del álbum/playlist para tener los IDs de las pistas
                track_ids = []
                try:
                    if content_type == "album":
                        album_info = dz.api.get_album(content_id)
                        tracks = album_info.get('tracks', {}).get('data', [])
                        track_ids = [str(track.get('id')) for track in tracks]
                    elif content_type == "playlist":
                        playlist_info = dz.api.get_playlist(content_id)
                        tracks = playlist_info.get('tracks', {}).get('data', [])
                        track_ids = [str(track.get('id')) for track in tracks]
                except Exception as e:
                    logging.warning(f"No se pudo obtener lista de tracks: {str(e)}")
                
                # Descargar album/playlist
                file_paths = await download_track(url, dz, settings, listener)
                
                if not isinstance(file_paths, list):
                    file_paths = [file_paths]
                
                # Actualizar estado
                await status_message.edit_text(f"✅ Descarga completada. Enviando {len(file_paths)} pistas...")
                
                # Enviar cada pista y guardar IDs
                file_ids = []
                for i, file_path in enumerate(file_paths):
                    try:
                        # Determinar el track_id correcto si está disponible
                        track_id = None
                        if i < len(track_ids):
                            track_id = track_ids[i]
                        
                        file_id = await send_and_save_audio(
                            context, 
                            update.message.chat_id, 
                            file_path, 
                            f"{content_type.title()} track {i+1}/{len(file_paths)}", 
                            vault_chat_id, 
                            f"{cache_key}_{i}",
                            dz=dz,
                            track_id=track_id
                        )
                        file_ids.append(file_id)
                        
                        # Eliminar archivo temporal después de enviarlo
                        if os.path.exists(file_path):
                            os.remove(file_path)
                    except Exception as e:
                        logging.error(f"Error enviando pista {i+1}: {str(e)}")
                
                # Guardar todos los IDs en el vault
                add_to_vault(cache_key, file_ids)
                
                # Actualizar mensaje de estado
                await status_message.edit_text(f"✅ {content_type.title()} enviado completamente")
                
            except Exception as e:
                logging.error(f"Error al descargar {content_type}: {str(e)}")
                await status_message.edit_text(f"❌ Error: {str(e)}")
        
        else:
            await update.message.reply_text("🔗 Tipo de contenido no soportado")
            
    except Exception as e:
        logging.error(f"Error crítico: {str(e)}", exc_info=True)
        await update.message.reply_text("⚠️ Error procesando tu solicitud")