import logging
import os
import requests
from io import BytesIO
from vault import add_to_vault

async def send_and_save_audio(context, chat_id, file_path, caption, vault_chat_id, key, dz=None, track_id=None, send_to_user=False):
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
        send_to_user: Si es True, también se envía al usuario (por defecto False)
    
    Returns:
        El file_id del audio enviado
    """
    try:
        # Extraer metadatos si es posible
        title = None
        performer = None
        duration = None
        thumbnail = None  # Cambiado de thumb a thumbnail (nombre correcto)
        
        # Intentar obtener metadatos de Deezer si se proporcionan dz y track_id
        if dz and track_id and str(track_id).isdigit():
            try:
                track_info = dz.api.get_track(track_id)
                if track_info:
                    title = track_info.get('title')
                    performer = track_info.get('artist', {}).get('name')
                    duration = track_info.get('duration')
                    
                    # Obtener URL de la miniatura
                    album_info = track_info.get('album', {})
                    cover_url = album_info.get('cover_medium') or album_info.get('cover_small')
                    
                    if cover_url:
                        # Descargar imagen de carátula
                        response = requests.get(cover_url)
                        if response.status_code == 200:
                            thumbnail = BytesIO(response.content)
                            thumbnail.name = "cover.jpg"
            except Exception as e:
                logging.warning(f"No se pudieron obtener metadatos de Deezer: {str(e)}")
        
        # Si no se pudieron obtener metadatos, extraer del nombre del archivo
        if not title or not performer:
            # Extraer información del nombre del archivo
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
        
        # Enviar al canal de vault con metadatos
        with open(file_path, "rb") as f:
            # Preparar argumentos para send_audio
            send_kwargs = {
                "chat_id": vault_chat_id,
                "audio": f,
                "caption": caption,
                "title": title,
                "performer": performer
            }
            
            # Añadir duración si está disponible
            if duration:
                send_kwargs["duration"] = duration
                
            # Añadir miniatura si está disponible (usando el nombre correcto del parámetro)
            if thumbnail:
                send_kwargs["thumbnail"] = thumbnail
                
            sent_message = await context.bot.send_audio(**send_kwargs)
            
        file_id = sent_message.audio.file_id
        
        # Enviar al usuario solo si se solicita explícitamente
        if send_to_user and chat_id != vault_chat_id:
            await context.bot.send_audio(
                chat_id=chat_id,
                audio=file_id
            )
        
        return file_id
    except Exception as e:
        logging.error(f"Error al enviar audio: {str(e)}", exc_info=True)
        raise
