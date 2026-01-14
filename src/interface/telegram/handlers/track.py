# -*- coding: utf-8 -*-
"""
Track processor for individual Deezer tracks.

Handles downloading and processing individual tracks.
"""

import logging
import os
import time
from typing import Any, Dict, Optional

from telegram import Update
from telegram.ext import ContextTypes

from src.infrastructure.deezer import download_track, TrackPreviewUnavailableError
from src.core.services.vault_service import add_to_vault, get_from_vault
from src.core.services import UserSession
from src.interface.telegram.handlers.audio import send_and_save_audio
from src.interface.telegram.handlers.messages import message_manager


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
    Processes downloading an individual Deezer track.
    
    This function handles the entire download process including:
    - Cache check to avoid duplicate downloads
    - Track download with configured quality
    - Audio file sending to user
    - Cache storage for future uses
    - Temporary file cleanup
    """
    user_id = update.effective_user.id
    start_time = time.time()
    logging.info(f"[TRACK] Start processing track_id: {track_id}, user: {user_id}")
    
    session = UserSession.get_session(user_id)
    
    # Increment active_downloads counter for individual tracks
    if not progress_msg or not hasattr(progress_msg, 'from_collection') or not progress_msg.from_collection:
        session.active_downloads += 1
        session.mark_as_changed()
    
    # Determine audio quality
    bitrate = settings.get("maxBitrate", 3)
    cache_key = f"{track_id}_{bitrate}"
    
    # Check cache
    cached_data = get_from_vault(cache_key)
    
    if cached_data:
        logging.info(f"[TRACK] Song {track_id} found in cache, user: {user_id}")
        await message_manager.send_temporary(
            update,
            "🎵 ¡Ya tengo esta canción! Enviando...",
            ttl=5
        )
        await update.message.reply_audio(audio=cached_data)
        
        if progress_msg:
            await progress_msg.complete(success=True, auto_delete=True)
            
        logging.info(f"[TRACK] Song {track_id} sent from cache, user: {user_id}, time: {time.time() - start_time:.2f}s")
        return
    
    # Create progress message if not provided
    if not progress_msg:
        logging.info(f"[TRACK] Song {track_id} not found in cache, downloading for user: {user_id}") 
        
        progress_msg = await message_manager.send_progress(
                update,
                process_type="download",
                initial_status="starting",
                content_type="canción"
            )
    
    try:
        # Verify track exists
        try:
            logging.info(f"[TRACK] Verifying track {track_id} existence, user: {user_id}")
            track_info = dz.api.get_track(track_id)
            if not track_info:
                await progress_msg.complete(
                    success=False,
                    error_message="No encuentro esta canción en Deezer. ¿El enlace es correcto?"
                )
                logging.warning(f"[TRACK] Track {track_id} not found on Deezer, user: {user_id}")
                return
                
            track_name = track_info.get('title', 'Canción sin título')
            artist_name = track_info.get('artist', {}).get('name', 'Artista desconocido')
            track_info_text = f"{track_name} - {artist_name}"
            
            if progress_msg.current_status != "downloading":
                await progress_msg.update(
                    "processing",
                    content_type="canción", 
                    track_info=track_info_text
                )
            
            logging.info(f"[TRACK] Track {track_id} verified and exists, user: {user_id}")
        except Exception as check_error:
            logging.warning(f"[TRACK] Error verifying track {track_id}: {str(check_error)}, user: {user_id}")
        
        # Download track
        try:
            logging.info(f"[TRACK] Starting actual download of track {track_id}, user: {user_id}")
            before_download = time.time()
            
            if progress_msg.current_status != "downloading":
                await progress_msg.update(
                    "downloading", 
                    content_type="canción",
                    track_info=track_info_text if 'track_info_text' in locals() else "canción"
                )
            
            file_path = await download_track(url, dz, settings, listener, user_id)
            logging.info(f"[TRACK] Download completed for track {track_id}, user: {user_id}, time: {time.time() - before_download:.2f}s")
        except TrackPreviewUnavailableError:
            logging.error(f"[TRACK] Track {track_id} has no preview available, user: {user_id}")
            await progress_msg.complete(
                success=False,
                error_message="Esta canción ya no está disponible en Deezer\nEs posible que haya sido retirada del catálogo o tenga restricciones"
            )
            return
        except Exception as download_error:
            error_msg = str(download_error).lower()
            logging.error(f"[TRACK] Error downloading track {track_id}: {error_msg}, user: {user_id}")
            
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
            
            logging.error(f"[TRACK] Error downloading track {track_id}: {str(download_error)}, user: {user_id}")
            return
        
        # Send to Telegram
        logging.info(f"[TRACK] Download successful, sending to Telegram track {track_id}, user: {user_id}")
        await progress_msg.update("uploading", content_type="canción")
        
        # Send and save to vault
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
        logging.info(f"[TRACK] Audio sent for track {track_id}, user: {user_id}, send time: {time.time() - before_send:.2f}s")
        
        # Save to vault
        logging.info(f"[TRACK] Saving to vault track {track_id}, user: {user_id}")
        add_to_vault(cache_key, file_id)
        
        # Delete temporary file
        if os.path.exists(file_path):
            os.remove(file_path)
            logging.info(f"[TRACK] Temporary file deleted for track {track_id}, user: {user_id}")
        
        # Complete progress message
        await progress_msg.complete(success=True, auto_delete=True)
        logging.info(f"[TRACK] Processing complete for track {track_id}, user: {user_id}, total time: {time.time() - start_time:.2f}s")
        
    except Exception as e:
        logging.error(f"[TRACK] General error processing track {track_id}: {str(e)}, user: {user_id}", exc_info=True)
        await progress_msg.complete(
            success=False, 
            error_message="Algo salió mal. Inténtalo de nuevo"
        )
        
    finally:
        # Decrement active_downloads counter for individual tracks only
        if not progress_msg or not hasattr(progress_msg, 'from_collection') or not progress_msg.from_collection:
            session.active_downloads = max(0, session.active_downloads - 1)
            session.mark_as_changed()
            
        logging.info(f"[TRACK] Processing complete for track {track_id}, user: {user_id}, total time: {time.time() - start_time:.2f}s")
