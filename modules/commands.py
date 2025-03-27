import os
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CallbackContext
from deemix.settings import load, save
from config import TrackFormats
from vault import load_vault

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

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Muestra estadísticas de uso del bot."""
    try:
        # Obtener datos para las estadísticas
        vault = load_vault()
        total_tracks = len(vault.keys())
        
        # Obtener información sobre directorios de descargas
        download_dir = os.path.abspath("./descargas")
        stats_text = (
            "📊 *Estadísticas de MelodifyDeluxe*\n\n"
            f"🎵 Total de pistas en caché: {total_tracks}\n"
            f"💾 Directorio de descargas: `{download_dir}`\n"
        )
        
        # Añadir más estadísticas si están disponibles
        if os.path.exists(download_dir):
            files_count = len([f for f in os.listdir(download_dir) if os.path.isfile(os.path.join(download_dir, f))])
            total_size = sum(os.path.getsize(os.path.join(download_dir, f)) for f in os.listdir(download_dir) if os.path.isfile(os.path.join(download_dir, f)))
            size_mb = total_size / (1024 * 1024)
            
            stats_text += (
                f"📁 Archivos temporales: {files_count}\n"
                f"📦 Tamaño en disco: {size_mb:.2f} MB\n"
            )
        
        # Configuración actual
        settings = context.bot_data.get('settings', load())
        bitrate = settings.get("maxBitrate", 3)
        
        # Mapear valores de bitrate a nombres legibles
        bitrate_names = {
            1: "MP3 128kbps",
            3: "MP3 320kbps",
            9: "FLAC (Calidad máxima)"
        }
        
        stats_text += (
            f"\n⚙️ *Configuración actual:*\n"
            f"🎚️ Calidad: {bitrate_names.get(bitrate, 'Desconocida')}\n"
        )
        
        await update.message.reply_text(
            stats_text,
            parse_mode="Markdown"
        )
        
    except Exception as e:
        logging.error(f"Error al mostrar estadísticas: {str(e)}", exc_info=True)
        await update.message.reply_text("❌ Error al generar estadísticas.")
