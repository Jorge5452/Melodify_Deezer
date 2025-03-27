import os
import asyncio
import logging
import shutil
import uuid
from typing import Union, List
from deezer import Deezer
from deemix import generateDownloadObject
from deemix.downloader import Downloader
from user_session import UserSession
from config import DOWNLOAD_PATH

class LogListener:
    def send(self, key, value=None):
        logging.debug(f"[DEEMIX] {key}: {value}")

async def download_track(url: str, dz, settings, listener, user_id=None) -> Union[str, List[str]]:
    """
    Descarga una pista, álbum o playlist de Deezer.
    
    Args:
        url: URL de Deezer para descargar
        dz: Instancia de Deezer autenticada
        settings: Configuración de descarga
        listener: Listener para logs
        user_id: ID opcional del usuario para gestión de recursos
        
    Returns:
        Ruta al archivo descargado o lista de rutas para álbumes/playlists
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
                # Ejecutar descarga
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
        # Comportamiento original para compatibilidad
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, sync_download_track, url, dz, settings, listener)

def sync_download_track(url: str, dz, settings, listener, user_id=None) -> Union[str, List[str]]:
    """
    Versión sincrónica de la función para descargar contenido de Deezer.
    """
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
        # Al principio de sync_download_track
        logging.info(f"Iniciando descarga: {url}" + (f" para usuario {user_id}" if user_id else ""))
        logging.info("Tipo de contenido: track")
        
        # Generar objeto de descarga
        bitrate = settings["maxBitrate"]
        plugins = {}  # Sin plugins adicionales
        download_obj = generateDownloadObject(dz, url, bitrate, plugins, listener)
        
        # Intentamos extraer información de manera segura
        obj_info = "Objeto a descargar"
        try:
            if hasattr(download_obj, 'title'):
                obj_info += f": {download_obj.title}"
            if hasattr(download_obj, 'artist') and hasattr(download_obj.artist, 'name'):
                obj_info += f" - {download_obj.artist.name}"
        except:
            pass
        logging.info(obj_info)

        # Siempre tratamos la descarga como de pista única
        Downloader(dz, download_obj, temp_settings, listener).start()
        
        # Buscar archivo de audio descargado
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
        # Después de las descargas y antes de procesar los archivos
        all_files = []
        for root, _, files in os.walk(temp_dir):
            for file in files:
                all_files.append(os.path.join(root, file))
        logging.info(f"Todos los archivos encontrados: {all_files}")
        
        # Limpiar directorio temporal
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir, ignore_errors=True)

# Nueva función para encolar descargas en la sesión de usuario
async def enqueue_download(user_id, process_func, *args, **kwargs):
    """
    Encola una descarga en la sesión del usuario.
    
    Args:
        user_id: ID del usuario de Telegram
        process_func: Función a ejecutar (process_track o process_collection)
        *args, **kwargs: Argumentos para la función
        
    Returns:
        True si se encoló correctamente, False en caso de error
    """
    try:
        session = UserSession.get_session(user_id)
        await session.add_download_task(process_func, *args, **kwargs)
        return True
    except Exception as e:
        logging.error(f"Error añadiendo descarga a la cola para usuario {user_id}: {str(e)}", exc_info=True)
        return False

# Nueva función para obtener estadísticas de un usuario
async def get_user_stats(user_id):
    """
    Obtiene estadísticas de descargas para un usuario.
    
    Args:
        user_id: ID del usuario de Telegram
        
    Returns:
        Diccionario con estadísticas del usuario
    """
    session = UserSession.get_session(user_id)
    return {
        'active_downloads': session.active_downloads,
        'total_downloads': session.total_downloads,
        'last_activity': session.last_activity
    }
