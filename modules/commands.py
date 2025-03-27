import os
import logging
from typing import Dict, Any, Union
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CallbackContext
from deemix.settings import load, save
from config import TrackFormats
from vault import load_vault

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Maneja el comando /start del bot.
    
    Envía un mensaje de bienvenida al usuario con información básica sobre
    las capacidades del bot y comandos disponibles.
    
    Args:
        update: Objeto Update con la información del mensaje
        context: Contexto del manejador de mensajes
    """
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

async def configuracion(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Maneja el comando /config para configurar la calidad de audio.
    
    Muestra un menú interactivo con botones que permite al usuario
    seleccionar la calidad deseada para las descargas de audio.
    
    Args:
        update: Objeto Update con la información del mensaje
        context: Contexto del manejador de mensajes
    """
    # Obtener la configuración actual o cargar la predeterminada
    settings = context.bot_data.get('settings', load())
    current_bitrate = settings.get("maxBitrate", 3)
    
    # Crear teclado con opciones de calidad
    keyboard = [
        [InlineKeyboardButton(f"FLAC (Calidad máxima) {'✅' if current_bitrate == TrackFormats.FLAC else ''}", 
                            callback_data=str(TrackFormats.FLAC))],
        [InlineKeyboardButton(f"MP3 320kbps {'✅' if current_bitrate == TrackFormats.MP3_320 else ''}", 
                            callback_data=str(TrackFormats.MP3_320))],
        [InlineKeyboardButton(f"MP3 128kbps {'✅' if current_bitrate == TrackFormats.MP3_128 else ''}", 
                            callback_data=str(TrackFormats.MP3_128))]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Enviar mensaje con opciones
    await update.message.reply_text(
        "⚙️ *Configuración de Calidad*\nSelecciona el formato de descarga:",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )

async def config_callback(update: Update, context: CallbackContext) -> None:
    """
    Maneja las respuestas a los botones de configuración.
    
    Procesa la selección del usuario en el menú de configuración,
    guarda los cambios y actualiza el mensaje para confirmar la acción.
    
    Args:
        update: Objeto Update con la información del callback query
        context: Contexto del manejador de mensajes
    """
    query = update.callback_query
    await query.answer()
    
    # Obtener el nuevo valor de bitrate seleccionado
    new_bitrate = int(query.data)
    
    # Actualizar la configuración
    settings = context.bot_data.get('settings', load())
    settings["maxBitrate"] = new_bitrate
    context.bot_data['settings'] = settings
    save(settings)  # Guardar configuración en disco
    
    # Preparar mensaje de confirmación
    format_name = {
        TrackFormats.FLAC: "FLAC (Calidad máxima)",
        TrackFormats.MP3_320: "MP3 320kbps",
        TrackFormats.MP3_128: "MP3 128kbps"
    }.get(new_bitrate, "Desconocido")
    
    # Actualizar mensaje con confirmación
    await query.edit_message_text(f"✅ Calidad actualizada a: {format_name}")

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Muestra estadísticas de uso del bot.
    
    Obtiene y muestra información sobre el número de pistas en caché,
    el directorio de descargas y la configuración actual del bot.
    
    Args:
        update: Objeto Update con la información del mensaje
        context: Contexto del manejador de mensajes
    """
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
