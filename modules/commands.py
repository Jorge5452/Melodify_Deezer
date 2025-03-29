import os
import logging
from typing import Dict, Any, Union
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CallbackContext
from deemix.settings import load, save
from config import TrackFormats
from vault import load_vault
from user_session import UserSession

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Maneja el comando /start del bot.
    """
    # Obtener datos del usuario para mantener un seguimiento adecuado
    user_id = update.effective_user.id
    session = UserSession.get_session(user_id)
    session.update_activity()
    
    help_text = (
        "👋 *¡Hola! Soy MelodifyDeluxe*\n\n"
        "Puedo descargar tu música favorita de Deezer. Simplemente:\n"
        "• Envíame un enlace de Deezer\n"
        "• Escribe el nombre de una canción para buscarla\n"
        "• Usa /config para elegir la calidad de audio\n\n"
        "¡Disfruta tu música! 🎧"
    )
    await update.message.reply_text(help_text, parse_mode="Markdown")

async def configuracion(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Maneja el comando /config para modificar la configuración de calidad de audio.
    """
    # Obtener datos del usuario para mantener un seguimiento adecuado
    user_id = update.effective_user.id
    session = UserSession.get_session(user_id)
    session.update_activity()
    
    # Cargar configuración actual
    settings = load()
    # Obtener calidad actual
    bitrate = settings.get("maxBitrate", TrackFormats.MP3_320)
    
    # Crear teclado inline con las opciones de calidad
    keyboard = [
        [InlineKeyboardButton("FLAC ★★★★★ (Sin pérdida)", callback_data=str(TrackFormats.FLAC))],
        [InlineKeyboardButton("MP3 320kbps ★★★★☆ (Alta calidad)", callback_data=str(TrackFormats.MP3_320))],
        [InlineKeyboardButton("MP3 128kbps ★★★☆☆ (Estándar)", callback_data=str(TrackFormats.MP3_128))]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Determinar la calidad actual para mostrar en el mensaje
    quality_text = "Desconocida"
    if bitrate == TrackFormats.FLAC:
        quality_text = "FLAC (Sin pérdida)"
    elif bitrate == TrackFormats.MP3_320:
        quality_text = "MP3 320kbps (Alta calidad)"
    elif bitrate == TrackFormats.MP3_128:
        quality_text = "MP3 128kbps (Estándar)"
    
    await update.message.reply_text(
        f"⚙️ *Configuración de calidad*\n\n"
        f"Calidad actual: *{quality_text}*\n\n"
        f"Selecciona la calidad de audio para descargas:",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )

async def config_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Procesa la selección de calidad de audio desde el teclado inline.
    """
    query = update.callback_query
    await query.answer()
    
    # Obtener datos del usuario para mantener un seguimiento adecuado
    user_id = query.from_user.id
    session = UserSession.get_session(user_id)
    session.update_activity()
    
    # Obtener el valor de calidad seleccionado
    try:
        new_bitrate = int(query.data)
    except ValueError:
        await query.edit_message_text("❌ Valor de calidad inválido")
        return
    
    # Cargar configuración actual
    settings = load()
    
    # Actualizar configuración con la nueva calidad
    settings["maxBitrate"] = new_bitrate
    
    # También actualizar en la sesión del usuario
    session.update_setting("maxBitrate", new_bitrate)
    
    # Guardar configuración
    save(settings)
    
    # Determinar texto descriptivo para la calidad seleccionada
    quality_text = "Desconocida"
    if new_bitrate == TrackFormats.FLAC:
        quality_text = "FLAC (Sin pérdida)"
    elif new_bitrate == TrackFormats.MP3_320:
        quality_text = "MP3 320kbps (Alta calidad)"
    elif new_bitrate == TrackFormats.MP3_128:
        quality_text = "MP3 128kbps (Estándar)"
    
    # Actualizar mensaje con la nueva configuración
    await query.edit_message_text(
        f"✅ Calidad de audio actualizada a: *{quality_text}*\n\n"
        f"Las próximas descargas usarán esta configuración.",
        parse_mode="Markdown"
    )

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Muestra estadísticas del bot: usuarios activos, caché, etc.
    """
    # Obtener datos del usuario para mantener un seguimiento adecuado
    user_id = update.effective_user.id
    session = UserSession.get_session(user_id)
    session.update_activity()
    
    # Estadísticas de usuarios
    active_sessions = UserSession.get_active_sessions_count()
    
    # Estadísticas del usuario actual
    user_downloads = session.total_downloads
    active_downloads = session.active_downloads
    
    # Estadísticas de caché
    vault_data = load_vault()
    cache_size = len(vault_data) if vault_data else 0
    
    # Estadísticas de disco (directorio de descargas)
    download_dir_size = 0
    download_files = 0
    try:
        for dirpath, dirnames, filenames in os.walk(os.path.abspath("./descargas")):
            download_files += len(filenames)
            for f in filenames:
                fp = os.path.join(dirpath, f)
                if os.path.exists(fp):
                    download_dir_size += os.path.getsize(fp)
    except Exception as e:
        logging.error(f"Error obteniendo estadísticas de disco: {e}")
    
    # Convertir bytes a MB
    download_dir_size_mb = round(download_dir_size / (1024 * 1024), 2)
    
    await update.message.reply_text(
        f"📊 *Estadísticas del Bot*\n\n"
        f"👥 Usuarios activos: {active_sessions}\n"
        f"🔄 Tus descargas activas: {active_downloads}\n"
        f"📥 Total de tus descargas: {user_downloads}\n\n"
        f"🗃️ Canciones en caché: {cache_size}\n"
        f"💾 Archivos temporales: {download_files}\n"
        f"📁 Espacio utilizado: {download_dir_size_mb} MB\n",
        parse_mode="Markdown"
    )
