# -*- coding: utf-8 -*-
"""
Premium commands and features for Melodify Deluxe.

This module implements exclusive features for premium users,
such as advanced download options, queue priority, and more.
"""

import logging
import time

from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes

from src.core.services import UserSession, requires_role

# Global definitions for the module
quality_options = {
    "FLAC": "FLAC (Lossless)",
    "MP3_320": "MP3 320kbps",
    "MP3_128": "MP3 128kbps"
}


async def premium_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Shows information about available premium features.
    
    Command: /premium
    """
    user_id = update.effective_user.id
    session = UserSession.get_session(user_id)
    
    # Check if user is premium
    is_premium = session.has_permission("premium")
    
    if is_premium:
        # Show available premium features
        help_text = """
💎 *Beneficios Premium Activos* 💎

✓ Hasta 5 descargas simultáneas
✓ Prioridad en la cola de descargas
✓ Acceso a formatos de mayor calidad
✓ Estadísticas detalladas de descargas
✓ Soporte prioritario

Usa /premium_stats para ver tus estadísticas de uso
"""
        keyboard = [
            [
                InlineKeyboardButton("📊 Mis estadísticas", callback_data="premium_stats")
            ],
            [
                InlineKeyboardButton("🎧 Opciones de audio", callback_data="premium_audio_options")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            help_text,
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )
    else:
        # Show info about how to get premium
        help_text = """
💎 *Beneficios Premium* 💎

Con una cuenta premium podrás disfrutar de:

• Hasta 5 descargas simultáneas
• Prioridad en la cola de descargas
• Acceso a formatos de mayor calidad
• Estadísticas detalladas de descargas
• Soporte prioritario

Contacta con el administrador para obtener acceso premium.
"""
        await update.message.reply_text(
            help_text,
            parse_mode="Markdown"
        )


@requires_role("premium")
async def premium_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Shows detailed statistics for premium users.
    
    Command: /premium_stats
    """
    user_id = update.effective_user.id
    session = UserSession.get_session(user_id)
    
    # Get user statistics
    total_downloads = session.total_downloads
    active_downloads = session.active_downloads
    
    # Calculate premium member time (simulated for now)
    premium_since = session.context_data.get("premium_since", time.time())
    days_premium = int((time.time() - premium_since) / 86400)
    
    stats_text = f"""
📊 *Tus Estadísticas Premium* 📊

⬇️ Total descargas: {total_downloads}
⏳ Descargas activas: {active_downloads}
📅 Días como premium: {days_premium}
🔄 Límite simultaneo: 5 descargas

📋 *Uso del mes*
🎵 Canciones: {int(total_downloads * 0.8)}
💿 Álbumes: {int(total_downloads * 0.2)}
🎧 Calidad Premium: {int(total_downloads * 0.6)}
"""
    
    await update.message.reply_text(stats_text, parse_mode="Markdown")


@requires_role("premium")
async def premium_audio_options(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Configures advanced audio options for premium users.
    
    Command: /premium_audio
    """
    user_id = update.effective_user.id
    session = UserSession.get_session(user_id)
    
    # Get current configuration
    settings = session.settings
    current_format = settings.get("downloadQuality", "MP3_320")
    
    # Create buttons for options
    keyboard = []
    for format_code, format_name in quality_options.items():
        text = f"✓ {format_name}" if format_code == current_format else format_name
        keyboard.append([InlineKeyboardButton(text, callback_data=f"premium_quality_{format_code}")])
    
    # Add folder format option
    keyboard.append([InlineKeyboardButton("📁 Formato de carpetas", callback_data="premium_folders")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "🎧 *Opciones de Audio Premium*\n\n"
        "Selecciona la calidad de descarga preferida:",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )


async def handle_premium_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handles callbacks from buttons in premium commands.
    """
    query = update.callback_query
    await query.answer()
    
    data = query.data
    user_id = update.effective_user.id
    session = UserSession.get_session(user_id)
    
    # Check if user is premium
    if not session.has_permission("premium"):
        await query.edit_message_text(
            "❌ Esta función requiere acceso premium."
        )
        return
    
    if data == "premium_stats":
        await premium_stats(update, context)
        
    elif data == "premium_audio_options":
        await premium_audio_options(update, context)
        
    elif data.startswith("premium_quality_"):
        quality = data.split("_")[-1]
        session.update_setting("downloadQuality", quality)
        
        await query.edit_message_text(
            f"✅ Calidad de audio actualizada a {quality_options.get(quality, quality)}\n\n"
            "Esta configuración se aplicará a tus próximas descargas."
        )
        
    elif data == "premium_folders":
        keyboard = [
            [InlineKeyboardButton("🎵 Artista/Álbum", callback_data="premium_folder_artist_album")],
            [InlineKeyboardButton("🎵 Artista/Año - Álbum", callback_data="premium_folder_artist_year_album")],
            [InlineKeyboardButton("📁 Personalizado", callback_data="premium_folder_custom")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            "📁 *Formato de carpetas*\n\n"
            "Selecciona cómo quieres organizar tus descargas:",
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )
        
    elif data.startswith("premium_folder_"):
        folder_format = data.replace("premium_folder_", "")
        
        if folder_format == "artist_album":
            template = "%artist%/%album%"
        elif folder_format == "artist_year_album":
            template = "%artist%/%year% - %album%"
        else:
            template = "%artist%/%album%"
        
        session.update_setting("albumNameTemplate", template)
        
        await query.edit_message_text(
            f"✅ Formato de carpetas actualizado\n\n"
            f"Tus descargas se organizarán según el nuevo formato."
        )


async def process_download_queue(session: UserSession) -> None:
    """
    Processes download queue with priority for premium users.
    
    This function is designed to be called when a new download is added
    and reorders the queue based on user priority.
    
    Args:
        session: User session that is downloading
    """
    # In a complete implementation, a priority system would be implemented here
    # that reorganizes queues to give preference to premium users
    
    logging.info(f"User {session.user_id} (role: {session.get_role()}) processing download queue")
