import logging
import os
from typing import Any, Dict, Union, Optional
from telegram import Update
from telegram.ext import ContextTypes
from downloader import download_track, TrackPreviewUnavailableError
from vault import add_to_vault, get_from_vault
from modules.audio_sender import send_and_save_audio
from modules.utils import safe_edit_message

async def process_track(
    update: Update, 
    context: ContextTypes.DEFAULT_TYPE, 
    url: str, 
    track_id: str, 
    dz: Any, 
    settings: Dict[str, Any], 
    vault_chat_id: int, 
    listener: Optional[Any] = None
) -> None:
    """
    Procesa la descarga de una pista individual de Deezer.
    
    Esta función maneja todo el proceso de descarga, incluyendo:
    - Verificación de caché para evitar descargas duplicadas
    - Descarga de la pista con la calidad configurada
    - Envío del archivo de audio al usuario
    - Almacenamiento en caché para usos futuros
    - Limpieza de archivos temporales
    
    Args:
        update: Objeto Update de Telegram con información del mensaje
        context: Contexto del bot de Telegram
        url: URL de la pista de Deezer
        track_id: ID único de la pista
        dz: Objeto cliente de Deezer autenticado
        settings: Configuraciones del usuario (calidad, formato, etc.)
        vault_chat_id: ID del chat donde se almacenan archivos en caché
        listener: Objeto opcional para recibir eventos de progreso
        
    Raises:
        Exception: Si ocurre algún error durante la descarga o procesamiento
    """
    # Determinar la calidad de audio a utilizar
    bitrate = settings.get("maxBitrate", 3)
    cache_key = f"{track_id}_{bitrate}"
    
    # Verificar si ya existe en caché
    cached_data = get_from_vault(cache_key)
    
    if cached_data:
        # Si está en caché, enviar directamente sin descargar de nuevo
        await update.message.reply_text("🎵 ¡Ya tengo esta canción! Enviando...")
        await update.message.reply_audio(audio=cached_data)
        return
    
    # Notificar inicio de descarga
    status_message = await update.message.reply_text("⏳ Descargando tu canción...")
    
    try:
        # Verificar si la pista existe antes de intentar descargarla
        try:
            track_info = dz.api.get_track(track_id)
            if not track_info:
                await status_message.edit_text("❌ No encuentro esta canción en Deezer. ¿El enlace es correcto?")
                return
        except Exception as check_error:
            logging.warning(f"Error verificando pista {track_id}: {str(check_error)}")
            # Continuamos con la descarga aunque falle la verificación previa
        
        # Fase 1: Descargar track
        try:
            file_path = await download_track(url, dz, settings, listener)
        except TrackPreviewUnavailableError:
            await status_message.edit_text(
                "❌ Esta canción ya no está disponible en Deezer\n"
                "Es posible que haya sido retirada del catálogo o tenga restricciones"
            )
            return
        except Exception as download_error:
            error_msg = str(download_error).lower()
            
            # Proporcionar mensajes de error específicos según el tipo de problema
            if "403" in error_msg or "forbidden" in error_msg:
                await status_message.edit_text("❌ Esta canción no está disponible en tu región")
            elif "404" in error_msg or "not found" in error_msg:
                await status_message.edit_text("❌ Esta canción ya no está disponible en Deezer")
            elif "copyright" in error_msg or "rights" in error_msg:
                await status_message.edit_text("❌ Esta canción tiene restricciones que impiden su descarga")
            elif "timeout" in error_msg or "timed out" in error_msg or "connection" in error_msg:
                await status_message.edit_text("❌ Problemas de conexión. Inténtalo de nuevo")
            else:
                await status_message.edit_text(f"❌ No pude descargar la canción")
            
            logging.error(f"Error al descargar pista {track_id}: {str(download_error)}", exc_info=True)
            return
        
        # Fase 2: Notificar avance
        await safe_edit_message(status_message, "✅ ¡Listo! Enviando a Telegram...")
        
        # Fase 3: Enviar y guardar en vault
        file_id = await send_and_save_audio(
            context, 
            update.message.chat_id, 
            file_path, 
            f"Track: {track_id}", 
            vault_chat_id, 
            cache_key,
            dz=dz,
            track_id=track_id,
            send_to_user=True
        )
        
        # Fase 4: Guardar en vault para futuras solicitudes
        add_to_vault(cache_key, file_id)
        
        # Fase 5: Eliminar archivo temporal
        if os.path.exists(file_path):
            os.remove(file_path)
        
        # Fase 6: Actualizar mensaje de estado
        await safe_edit_message(status_message, "✅ ¡Disfruta tu música!")
        
    except Exception as e:
        # Manejo de errores generales
        logging.error(f"Error al descargar: {str(e)}", exc_info=True)
        await safe_edit_message(status_message, "❌ Algo salió mal. Inténtalo de nuevo")
