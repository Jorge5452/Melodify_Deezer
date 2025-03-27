import logging
import os
from downloader import download_track
from vault import add_to_vault, get_from_vault
from modules.audio_sender import send_and_save_audio
from modules.utils import safe_edit_message

async def process_track(update, context, url, track_id, dz, settings, vault_chat_id, listener):
    """
    Procesa la descarga de una pista individual.
    """
    bitrate = settings.get("maxBitrate", 3)
    cache_key = f"{track_id}_{bitrate}"
    cached_data = get_from_vault(cache_key)
    
    if cached_data:
        await update.message.reply_text("🎵 Encontrado en caché")
        await update.message.reply_audio(audio=cached_data)
        return
    
    # Notificar inicio de descarga
    status_message = await update.message.reply_text("⏳ Descargando pista...")
    
    try:
        # Descargar track
        file_path = await download_track(url, dz, settings, listener)
        
        # Actualizar estado
        await status_message.edit_text("✅ Descarga completada. Enviando...")
        
        # Enviar y guardar en vault
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
