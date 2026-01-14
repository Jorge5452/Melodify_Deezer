import logging
import os
import time
from typing import Any, Dict, Union, Optional
from telegram import Update
from telegram.ext import ContextTypes
from downloader import download_track, TrackPreviewUnavailableError
from vault import add_to_vault, get_from_vault
from modules.audio_sender import send_and_save_audio
from modules.message_manager import message_manager
from user_session import UserSession

async def process_track(
    update: Update, 
    context: ContextTypes.DEFAULT_TYPE, 
    url: str, 
    track_id: str, 
    dz: Any, 
    settings: Dict[str, Any], 
    vault_chat_id: int, 
    listener: Optional[Any] = None,
    progress_msg: Optional[Any] = None
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
        progress_msg: Objeto ProgressMessage opcional existente
        
    Raises:
        Exception: Si ocurre algún error durante la descarga o procesamiento
    """
    user_id = update.effective_user.id
    start_time = time.time()
    logging.info(f"[TRACK] Inicio procesamiento track_id: {track_id}, usuario: {user_id}")
    
    # Get user session to manage active downloads
    session = UserSession.get_session(user_id)
    
    # Increment active_downloads counter for individual tracks
    # Note: For collections, this is handled in enqueue_download
    if not progress_msg or not hasattr(progress_msg, 'from_collection'):
        session.active_downloads += 1
        session.mark_as_changed()
    
    # Determinar la calidad de audio a utilizar
    bitrate = settings.get("maxBitrate", 3)
    cache_key = f"{track_id}_{bitrate}"
    
    # Verificar si ya existe en caché
    cached_data = get_from_vault(cache_key)
    
    if cached_data:
        # Si está en caché, enviar directamente
        logging.info(f"[TRACK] Canción {track_id} encontrada en caché, usuario: {user_id}")
        # Enviar mensaje temporal que se autodestruye
        await message_manager.send_temporary(
            update,
            "🎵 ¡Ya tengo esta canción! Enviando...",
            ttl=5  # Desaparece después de 5 segundos
        )
        await update.message.reply_audio(audio=cached_data)
        
        # Si tenemos un mensaje de progreso existente, completarlo y autoborrar
        if progress_msg:
            await progress_msg.complete(success=True, auto_delete=True)
            
        logging.info(f"[TRACK] Canción {track_id} enviada desde caché, usuario: {user_id}, tiempo: {time.time() - start_time:.2f}s")
        return
    
    # Si no se proporcionó un mensaje de progreso existente, crear uno nuevo
    if not progress_msg:
        # Notificar inicio de descarga con un mensaje de progreso
        logging.info(f"[TRACK] Canción {track_id} no encontrada en caché, descargando para usuario: {user_id}") 
        
        # Crear mensaje de progreso para la descarga
        progress_msg = await message_manager.send_progress(
                update,
                process_type="download",
                initial_status="starting",
                content_type="canción"
            )
    
    try:
        # Verificar si la pista existe antes de intentar descargarla
        try:
            logging.info(f"[TRACK] Verificando existencia de pista {track_id}, usuario: {user_id}")
            track_info = dz.api.get_track(track_id)
            if not track_info:
                await progress_msg.complete(
                    success=False,
                    error_message="No encuentro esta canción en Deezer. ¿El enlace es correcto?"
                )
                logging.warning(f"[TRACK] Pista {track_id} no encontrada en Deezer, usuario: {user_id}")
                return
                
            # Actualizar mensaje con información de la pista
            track_name = track_info.get('title', 'Canción sin título')
            artist_name = track_info.get('artist', {}).get('name', 'Artista desconocido')
            track_info_text = f"{track_name} - {artist_name}"
            
            # Solo actualizar si no está ya en estado "downloading" (para evitar revertir desde búsqueda)
            if progress_msg.current_status != "downloading":
                await progress_msg.update(
                    "processing",
                    content_type="canción", 
                    track_info=track_info_text
                )
            
            logging.info(f"[TRACK] Pista {track_id} verificada y existe, usuario: {user_id}")
        except Exception as check_error:
            logging.warning(f"[TRACK] Error verificando pista {track_id}: {str(check_error)}, usuario: {user_id}")
            # Continuamos con la descarga aunque falle la verificación previa
        
        # Fase 1: Descargar track
        try:
            logging.info(f"[TRACK] Iniciando descarga efectiva de pista {track_id}, usuario: {user_id}")
            before_download = time.time()
            
            # Actualizar mensaje a estado de descarga si no está ya en ese estado
            if progress_msg.current_status != "downloading":
                await progress_msg.update(
                    "downloading", 
                    content_type="canción",
                    track_info=track_info_text if 'track_info_text' in locals() else "canción"
                )
            
            file_path = await download_track(url, dz, settings, listener, user_id)
            logging.info(f"[TRACK] Descarga completada para pista {track_id}, usuario: {user_id}, tiempo: {time.time() - before_download:.2f}s")
        except TrackPreviewUnavailableError:
            logging.error(f"[TRACK] Pista {track_id} sin preview disponible, usuario: {user_id}")
            await progress_msg.complete(
                success=False,
                error_message="Esta canción ya no está disponible en Deezer\nEs posible que haya sido retirada del catálogo o tenga restricciones"
            )
            return
        except Exception as download_error:
            error_msg = str(download_error).lower()
            logging.error(f"[TRACK] Error en descarga de pista {track_id}: {error_msg}, usuario: {user_id}")
            
            # Proporcionar mensajes de error específicos según el tipo de problema
            if "403" in error_msg or "forbidden" in error_msg:
                error_text = "Esta canción no está disponible en tu región"
            elif "404" in error_msg or "not found" in error_msg:
                error_text = "Esta canción ya no está disponible en Deezer"
            elif "copyright" in error_msg or "rights" in error_msg:
                error_text = "Esta canción tiene restricciones que impiden su descarga"
            elif "timeout" in error_msg or "timed out" in error_msg or "connection" in error_msg:
                error_text = "Problemas de conexión. Inténtalo de nuevo"
            else:
                error_text = "No pude descargar la canción"
            
            await progress_msg.complete(
                success=False,
                error_message=error_text
            )
            
            logging.error(f"[TRACK] Error al descargar pista {track_id}: {str(download_error)}, usuario: {user_id}")
            return
        
        # Fase 2: Notificar avance
        logging.info(f"[TRACK] Descarga exitosa, enviando a Telegram pista {track_id}, usuario: {user_id}")
        await progress_msg.update("uploading", content_type="canción")
        
        # Fase 3: Enviar y guardar en vault
        before_send = time.time()
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
        logging.info(f"[TRACK] Audio enviado para pista {track_id}, usuario: {user_id}, tiempo envío: {time.time() - before_send:.2f}s")
        
        # Fase 4: Guardar en vault para futuras solicitudes
        logging.info(f"[TRACK] Guardando en vault pista {track_id}, usuario: {user_id}")
        add_to_vault(cache_key, file_id)
        
        # Fase 5: Eliminar archivo temporal
        if os.path.exists(file_path):
            os.remove(file_path)
            logging.info(f"[TRACK] Archivo temporal eliminado para pista {track_id}, usuario: {user_id}")
        
        # Fase 6: Actualizar mensaje de estado final y programar eliminación
        await progress_msg.complete(success=True, auto_delete=True)
        logging.info(f"[TRACK] Procesamiento completo para pista {track_id}, usuario: {user_id}, tiempo total: {time.time() - start_time:.2f}s")
        
    except Exception as e:
        # Manejo de errores generales
        logging.error(f"[TRACK] Error general al procesar pista {track_id}: {str(e)}, usuario: {user_id}", exc_info=True)
        await progress_msg.complete(
            success=False, 
            error_message="Algo salió mal. Inténtalo de nuevo"
        )
        
    finally:
        # Decrement active_downloads counter for individual tracks only
        # For collections, this is handled in process_collection
        if not progress_msg or not hasattr(progress_msg, 'from_collection'):
            session.active_downloads = max(0, session.active_downloads - 1)
            session.mark_as_changed()
            
        logging.info(f"[TRACK] Procesamiento completo para pista {track_id}, usuario: {user_id}, tiempo total: {time.time() - start_time:.2f}s")
