"""
Módulo para la descarga de contenido desde Deezer.

Proporciona funciones para descargar pistas, álbumes y playlists usando la API
de Deezer y la biblioteca deemix, con gestión de concurrencia y límites de recursos.
"""

import os
import asyncio
import logging
import shutil
import uuid
from typing import Union, List, Dict, Any, Optional, Callable, Awaitable, Tuple
from deezer import Deezer
from deemix import generateDownloadObject
from deemix.downloader import Downloader
from user_session import UserSession
from config import DOWNLOAD_PATH

class LogListener:
    """
    Clase para capturar y registrar los mensajes de log generados por deemix.
    """
    
    def send(self, key: str, value: Any = None) -> None:
        """
        Procesa y registra un mensaje de log de deemix.
        
        Args:
            key: Identificador del mensaje o evento
            value: Valor o información adicional asociada al evento
        """
        logging.debug(f"[DEEMIX] {key}: {value}")

async def download_track(url: str, dz: Deezer, settings: Dict[str, Any], 
                         listener: LogListener, user_id: Optional[int] = None) -> Union[str, List[str]]:
    """
    Descarga una pista, álbum o playlist de Deezer con gestión de concurrencia.
    
    Args:
        url: URL de Deezer para descargar (pista, álbum o playlist)
        dz: Instancia autenticada de la clase Deezer
        settings: Diccionario con la configuración de descarga
        listener: Instancia de LogListener para recibir eventos de progreso
        user_id: ID opcional del usuario para gestión de recursos y límites
        
    Returns:
        Ruta al archivo descargado o lista de rutas para álbumes/playlists
        
    Raises:
        Exception: Si ocurre un error durante la descarga o el procesamiento
    """
    # Si se proporciona user_id, usar el semáforo global para controlar concurrencia
    if user_id:
        # Obtener sesión de usuario
        session = UserSession.get_session(user_id)
        # Actualizar actividad
        session.update_activity()
        # Controlar tasa de solicitudes
        await session.wait_for_rate_limit()
        # Obtener semáforo global
        global_semaphore = await UserSession.get_global_semaphore()
        
        # Usar semáforo global para limitar descargas concurrentes
        async with global_semaphore:
            # Incrementar contador de descargas activas
            session.active_downloads += 1
            session.total_downloads += 1
            try:
                # Ejecutar descarga en segundo plano para no bloquear el bucle de eventos
                loop = asyncio.get_event_loop()
                result = await loop.run_in_executor(
                    None, 
                    lambda: sync_download_track(url, dz, settings, listener, user_id)
                )
                return result
            finally:
                # Decrementar contador al finalizar
                session.active_downloads -= 1
    else:
        # Comportamiento original para compatibilidad con código legacy
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, sync_download_track, url, dz, settings, listener)

def sync_download_track(url: str, dz: Deezer, settings: Dict[str, Any], 
                        listener: LogListener, user_id: Optional[int] = None) -> Union[str, List[str]]:
    """
    Versión sincrónica de la función para descargar contenido de Deezer.
    
    Esta función realiza la descarga de manera sincrónica y es ejecutada
    en un executor por la función asíncrona download_track.
    
    Args:
        url: URL de Deezer para descargar
        dz: Instancia autenticada de la clase Deezer
        settings: Diccionario con la configuración de descarga
        listener: Instancia de LogListener para recibir eventos de progreso
        user_id: ID opcional del usuario para identificación de archivos
        
    Returns:
        Ruta al archivo descargado o lista de rutas para álbumes/playlists
        
    Raises:
        Exception: Si ocurre un error durante la descarga o procesamiento
    """
    # Asegurar que el directorio base de descargas exista
    os.makedirs(DOWNLOAD_PATH, exist_ok=True)
    
    # Crear un directorio temporal único para evitar conflictos
    # Si hay user_id, incluirlo en la ruta para separar por usuario
    folder_name = f"temp_{uuid.uuid4().hex}"
    if user_id:
        folder_name = f"user_{user_id}_{folder_name}"
    
    temp_dir = os.path.join(DOWNLOAD_PATH, folder_name)
    os.makedirs(temp_dir, exist_ok=True)
    
    # Guardar settings temporales para esta descarga
    temp_settings = settings.copy()
    temp_settings["downloadLocation"] = temp_dir
    
    try:
        # Registrar inicio de la descarga
        logging.info(f"Iniciando descarga: {url}" + (f" para usuario {user_id}" if user_id else ""))
        logging.info("Tipo de contenido: track")
        
        # Generar objeto de descarga con la configuración de calidad deseada
        bitrate = settings["maxBitrate"]
        plugins = {}  # Sin plugins adicionales
        download_obj = generateDownloadObject(dz, url, bitrate, plugins, listener)
        
        # Extraer información del objeto a descargar para logging
        obj_info = "Objeto a descargar"
        try:
            if hasattr(download_obj, 'title'):
                obj_info += f": {download_obj.title}"
            if hasattr(download_obj, 'artist') and hasattr(download_obj.artist, 'name'):
                obj_info += f" - {download_obj.artist.name}"
        except Exception:
            # Ignorar errores al extraer información para logging
            pass
        logging.info(obj_info)

        # Iniciar la descarga utilizando el downloader de deemix
        Downloader(dz, download_obj, temp_settings, listener).start()
        
        # Buscar archivo de audio descargado en el directorio temporal
        for root, _, files in os.walk(temp_dir):
            for file in files:
                if file.endswith(('.mp3', '.flac', '.m4a')):
                    file_path = os.path.join(root, file)
                    # Mover a la carpeta principal de descargas
                    target_path = os.path.join(DOWNLOAD_PATH, file)
                    shutil.move(file_path, target_path)
                    return target_path
        
        raise Exception("No se encontró ningún archivo de audio descargado.")
    
    except Exception as e:
        logging.error(f"Error durante la descarga: {str(e)}", exc_info=True)
        raise
    
    finally:
        # Registrar todos los archivos encontrados antes de limpiar
        all_files = []
        for root, _, files in os.walk(temp_dir):
            for file in files:
                all_files.append(os.path.join(root, file))
        logging.info(f"Todos los archivos encontrados: {all_files}")
        
        # Limpiar directorio temporal para no acumular basura
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir, ignore_errors=True)

async def enqueue_download(user_id: int, process_func: Callable[..., Awaitable[Any]], 
                        *args: Any, **kwargs: Any) -> bool:
    """
    Encola una tarea de descarga en la sesión del usuario para procesamiento asíncrono.
    
    Args:
        user_id: ID del usuario de Telegram
        process_func: Función a ejecutar (process_track o process_collection)
        *args, **kwargs: Argumentos para la función de procesamiento
        
    Returns:
        bool: True si se encoló correctamente, False en caso de error
    """
    try:
        session = UserSession.get_session(user_id)
        await session.add_download_task(process_func, *args, **kwargs)
        return True
    except Exception as e:
        logging.error(f"Error añadiendo descarga a la cola para usuario {user_id}: {str(e)}", exc_info=True)
        return False

async def get_user_stats(user_id: int) -> Dict[str, Any]:
    """
    Obtiene estadísticas de descargas para un usuario específico.
    
    Args:
        user_id: ID del usuario de Telegram
        
    Returns:
        Diccionario con estadísticas del usuario incluyendo:
        - active_downloads: Número de descargas actualmente en proceso
        - total_downloads: Número total de descargas realizadas
        - last_activity: Timestamp de la última actividad del usuario
    """
    session = UserSession.get_session(user_id)
    return {
        'active_downloads': session.active_downloads,
        'total_downloads': session.total_downloads,
        'last_activity': session.last_activity
    }
