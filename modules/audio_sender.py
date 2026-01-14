import logging
import os
import requests
from io import BytesIO
from vault import add_to_vault
from config import (
    HTTP_CONNECT_TIMEOUT, 
    HTTP_READ_TIMEOUT, 
    HTTP_WRITE_TIMEOUT,
    MAX_RETRIES,
    INITIAL_RETRY_DELAY,
    RETRY_BACKOFF_FACTOR
)
from modules.utils import retry_async_operation
from telegram.request import HTTPXRequest
from telegram.error import TimedOut, NetworkError

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
        
        # Enviar al canal de vault con metadatos y sistema de reintentos
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
                
            # Añadir miniatura si está disponible
            if thumbnail:
                send_kwargs["thumbnail"] = thumbnail
                
            # Función interna para enviar con reintentos y reset de archivo
            async def send_with_file_reset(func, **kwargs):
                import random
                import asyncio
                
                delay = INITIAL_RETRY_DELAY
                last_exception = None
                
                for attempt in range(MAX_RETRIES + 1):
                    try:
                        # CRÍTICO: Resetear el puntero del archivo al inicio antes de cada intento
                        f.seek(0)
                        
                        return await func(**kwargs)
                    except (TimedOut, NetworkError) as e:
                        last_exception = e
                        if attempt < MAX_RETRIES:
                            jitter_value = random.uniform(-0.1, 0.1) * delay
                            current_delay = delay + jitter_value
                            
                            logging.warning(
                                f"Intento {attempt+1}/{MAX_RETRIES+1} falló al enviar audio: {str(e)}. "
                                f"Reintentando en {current_delay:.2f}s"
                            )
                            await asyncio.sleep(current_delay)
                            delay *= RETRY_BACKOFF_FACTOR
                    except RetryAfter as e:
                        last_exception = e
                        if attempt < MAX_RETRIES:
                            logging.warning(f"Rate limit. Esperando {e.retry_after}s.")
                            await asyncio.sleep(e.retry_after)
                    except Exception as e:
                        logging.error(f"Error no recuperable en intento {attempt+1}: {str(e)}")
                        raise

                raise last_exception

            # Usar la nueva lógica robusta
            try:
                sent_message = await send_with_file_reset(
                    context.bot.send_audio,
                    **send_kwargs
                )
            except (TimedOut, NetworkError) as e:
                logging.error(f"Error después de {MAX_RETRIES+1} intentos al enviar audio: {str(e)}")
                # Intentar una última vez con un archivo más simple (sin metadatos ni miniatura)
                logging.info("Intentando envío simplificado sin metadatos...")
                simple_kwargs = {
                    "chat_id": vault_chat_id,
                    "audio": f,
                    "caption": caption
                }
                # También usar reset para el intento simplificado (solo 1 reintento para fallback)
                # Hack: Usamos la misma función pero limitamos el loop si quisiéramos, 
                # o simplemente hacemos un intento directo con seek.
                f.seek(0) 
                # Reutilizamos la función auxiliar con menos reintentos para el fallback
                MAX_RETRIES_FALLBACK = 1
                
                # Redefinimos temporalmente para el fallback o usamos lógica similar
                sent_message = await send_with_file_reset(
                   context.bot.send_audio,
                   **simple_kwargs
                )
        
        file_id = sent_message.audio.file_id
        
        # Enviar al usuario solo si se solicita explícitamente
        if send_to_user and chat_id != vault_chat_id:
            await retry_async_operation(
                context.bot.send_audio,
                max_retries=MAX_RETRIES,
                initial_delay=INITIAL_RETRY_DELAY,
                backoff_factor=RETRY_BACKOFF_FACTOR,
                chat_id=chat_id,
                audio=file_id
            )
        
        return file_id
    except Exception as e:
        logging.error(f"Error al enviar audio: {str(e)}", exc_info=True)
        raise
