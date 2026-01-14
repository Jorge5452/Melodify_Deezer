# -*- coding: utf-8 -*-
"""
Basic command handlers for Melodify Deluxe bot.

Provides handlers for /start, /config and /stats commands.
"""

import os
import logging
from typing import Dict, Any

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from deemix.settings import load, save

from src.config import TrackFormats
from src.core.services import UserSession, load_vault
from src.core.services.queue_service import QueueManager
from src.interface.telegram.utils import with_user_session, with_error_handling, combined_decorator


@with_user_session
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handles the /start command of the bot.
    """
    help_text = (
        "👋 *¡Hola! Soy MelodifyDeluxe*\n\n"
        "Puedo descargar tu música favorita de Deezer. Simplemente:\n"
        "• Envíame un enlace de Deezer\n"
        "• Escribe el nombre de una canción para buscarla\n"
        "• Usa /config para elegir la calidad de audio\n\n"
        "¡Disfruta tu música! 🎧"
    )
    await update.message.reply_text(help_text, parse_mode="Markdown")


@with_user_session
async def configuracion(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handles the /config command to modify audio quality settings.
    """
    # Load current configuration
    settings = load()
    # Get current quality
    bitrate = settings.get("maxBitrate", TrackFormats.MP3_320)
    
    # Create inline keyboard with quality options
    keyboard = [
        [InlineKeyboardButton("FLAC ★★★★★ (Sin pérdida)", callback_data=str(TrackFormats.FLAC))],
        [InlineKeyboardButton("MP3 320kbps ★★★★☆ (Alta calidad)", callback_data=str(TrackFormats.MP3_320))],
        [InlineKeyboardButton("MP3 128kbps ★★★☆☆ (Estándar)", callback_data=str(TrackFormats.MP3_128))]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Determine current quality for display
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


@with_user_session
@with_error_handling
async def config_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Processes audio quality selection from inline keyboard.
    """
    query = update.callback_query
    await query.answer()
    
    session = context.user_data.get('session')
    
    # Get selected quality value
    try:
        new_bitrate = int(query.data)
    except ValueError:
        await query.edit_message_text("❌ Valor de calidad inválido")
        return
    
    # Load current configuration
    settings = load()
    
    # Update configuration with new quality
    settings["maxBitrate"] = new_bitrate
    
    # Also update in user session
    if session:
        session.update_setting("maxBitrate", new_bitrate)
    
    # Save configuration
    save(settings)
    
    # Determine descriptive text for selected quality
    quality_text = "Desconocida"
    if new_bitrate == TrackFormats.FLAC:
        quality_text = "FLAC (Sin pérdida)"
    elif new_bitrate == TrackFormats.MP3_320:
        quality_text = "MP3 320kbps (Alta calidad)"
    elif new_bitrate == TrackFormats.MP3_128:
        quality_text = "MP3 128kbps (Estándar)"
    
    # Update message with new configuration
    await query.edit_message_text(
        f"✅ Calidad de audio actualizada a: *{quality_text}*\n\n"
        f"Las próximas descargas usarán esta configuración.",
        parse_mode="Markdown"
    )


@combined_decorator
async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Shows bot statistics: active users, cache, etc.
    """
    session = context.user_data.get('session')
    user_id = update.effective_user.id
    
    # User statistics
    active_sessions = UserSession.get_active_sessions_count()
    
    # Current user statistics
    user_downloads = session.total_downloads if session else 0
    active_downloads = session.active_downloads if session else 0
    
    # Get monthly download info for normal users
    monthly_stats = session.get_monthly_downloads_left() if session else {"limit": 0, "used": 0, "remaining": 0}
    user_role = session.get_role() if session else "normal"
    
    # Get queue statistics
    queue_manager = QueueManager.get_instance()
    queue_stats = queue_manager.get_stats()
    
    # Get user queue statistics
    user_queue = queue_manager.get_user_queue(user_id, "downloads")
    user_queue_stats = user_queue.get_stats()
    
    # Cache statistics
    vault_data = load_vault()
    cache_size = len(vault_data) if vault_data else 0
    
    # Disk statistics (downloads directory)
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
        logging.error(f"Error getting disk statistics: {e}")
    
    # Convert bytes to MB
    download_dir_size_mb = round(download_dir_size / (1024 * 1024), 2)
    
    # Create formatted statistics message
    stats_message = (
        f"📊 *Estadísticas del Bot*\n\n"
        f"*👥 Usuarios:*\n"
        f"  • Activos: {active_sessions}\n"
        f"  • Total en cola: {queue_stats['active_users']}\n\n"
        
        f"*🔄 Tu actividad:*\n"
        f"  • Descargas activas: {active_downloads}\n"
        f"  • Total histórico: {user_downloads}\n"
        f"  • En cola: {user_queue_stats['pending_tasks']}\n"
    )
    
    # Add monthly download info for normal users
    if user_role == "normal":
        stats_message += (
            f"  • Rol: 👤 Normal\n"
            f"  • Descargas mensuales: {monthly_stats['used']}/{monthly_stats['limit']}\n"
            f"  • Restantes este mes: {monthly_stats['remaining']}\n\n"
        )
    elif user_role == "premium":
        stats_message += (
            f"  • Rol: 💎 Premium\n"
            f"  • Descargas mensuales: Ilimitadas ♾️\n\n"
        )
    elif user_role == "admin":
        stats_message += (
            f"  • Rol: 👑 Admin\n"
            f"  • Descargas mensuales: Ilimitadas ♾️\n\n"
        )
    else:
        stats_message += "\n"
    
    stats_message += (
        f"*⚙️ Sistema:*\n"
        f"  • Tareas globales pendientes: {queue_stats['total_pending']}\n"
        f"  • Tareas procesadas: {queue_stats['total_processed']}\n"
        f"  • Tareas fallidas: {queue_stats['total_failed']}\n\n"
        
        f"*🗃️ Almacenamiento:*\n"
        f"  • Canciones en caché: {cache_size}\n"
        f"  • Archivos temporales: {download_files}\n"
        f"  • Espacio utilizado: {download_dir_size_mb} MB\n"
    )
    
    await update.message.reply_text(stats_message, parse_mode="Markdown")
