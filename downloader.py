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
import requests  # Añadido el import faltante de requests
import time
from typing import Union, List, Dict, Any, Optional, Callable, Awaitable, Tuple
from deezer import Deezer
from deemix import generateDownloadObject
from deemix.downloader import Downloader
from user_session import UserSession
from config import DOWNLOAD_PATH, MAX_CONCURRENT_DOWNLOADS_PER_USER
from modules.queue_manager import QueueManager

# Definir excepción específica para pistas sin preview
class TrackPreviewUnavailableError(Exception):
    """Excepción lanzada cuando una pista no tiene preview disponible en Deezer."""
    pass

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
    # Log inicio de descarga con timestamp
    start_time = time.time()
    logging.info(f"[DOWNLOADER] Iniciando descarga de URL: {url} para usuario: {user_id}, timestamp: {start_time}")
    
    # Si se proporciona user_id, usar el gestor de colas para controlar concurrencia
    if user_id:
        # Obtener gestor de colas
        queue_manager = QueueManager.get_instance()
        
        # Obtener sesión de usuario para estadísticas
        session = UserSession.get_session(user_id)
        session.update_activity()
        
        try:
            # Incrementar contador de descargas activas
            session.active_downloads += 1
            session.total_downloads += 1
            logging.info(f"[DOWNLOADER] Usuario {user_id} ahora tiene {session.active_downloads} descargas activas")
            
            # Ejecutar descarga en segundo plano utilizando colas
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None, 
                lambda: sync_download_track(url, dz, settings, listener, user_id)
            )
            logging.info(f"[DOWNLOADER] Descarga completada para usuario: {user_id}, tiempo: {time.time() - start_time:.2f}s")
            return result
        finally:
            # Decrementar contador al finalizar
            session.active_downloads -= 1
            logging.info(f"[DOWNLOADER] Usuario {user_id} ahora tiene {session.active_downloads} descargas activas")
    else:
        # Comportamiento original para compatibilidad con código legacy
        logging.info("[DOWNLOADER] Usando método legacy sin user_id")
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, sync_download_track, url, dz, settings, listener)
        logging.info(f"[DOWNLOADER] Descarga legacy completada, tiempo: {time.time() - start_time:.2f}s")
        return result

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
        
        # Verificar si el objeto es válido
        if not download_obj:
            raise Exception("No se encontró esta canción en Deezer")
        
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
        downloader = Downloader(dz, download_obj, temp_settings, listener)
        
        # Capturar errores específicos durante la descarga
        try:
            # Registrar información sobre el objeto a descargar para diagnóstico
            track_info = None
            try:
                # Intentar obtener ID de la URL para diagnosis
                track_id = url.split("/")[-1]
                if track_id.isdigit():
                    track_info = dz.api.get_track(track_id)
                    if track_info and track_info.get('title'):
                        logging.info(f"Descargando: {track_info.get('title')} - {track_info.get('artist', {}).get('name', 'Unknown')}")
            except Exception:
                pass  # Ignorar errores en la obtención de info para diagnóstico

            downloader.start()
        except IndexError as e:
            error_str = str(e)
            # Capturar el error específico relacionado con MEDIA
            if 'list index out of range' in error_str:
                track_title = "canción desconocida"
                if track_info and track_info.get('title'):
                    track_title = f"{track_info.get('title')} - {track_info.get('artist', {}).get('name', 'Desconocido')}"
                
                logging.error(f"{track_title} list index out of range")
                raise TrackPreviewUnavailableError(f"La canción '{track_title}' no está disponible en Deezer")
            else:
                raise  # Re-lanzar otros errores de índice
        except Exception as e:
            error_msg = str(e).lower()
            if "403" in error_msg or "forbidden" in error_msg:
                raise Exception("Esta canción no está disponible en tu región")
            elif "404" in error_msg or "not found" in error_msg:
                raise Exception("Esta canción ya no está disponible en Deezer")
            elif "copyright" in error_msg or "rights" in error_msg:
                raise Exception("Esta canción tiene restricciones de derechos de autor")
            elif "timeout" in error_msg or "timed out" in error_msg:
                raise Exception("Problemas de conexión. Inténtalo de nuevo")
            elif "key error" in error_msg or "missing" in error_msg:
                raise Exception("Información incompleta para esta canción")
            else:
                raise  # Re-lanzar la excepción original para otros casos
        
        # Buscar archivo de audio descargado en el directorio temporal
        audio_files = []
        for root, _, files in os.walk(temp_dir):
            for file in files:
                if file.endswith(('.mp3', '.flac', '.m4a')):
                    file_path = os.path.join(root, file)
                    audio_files.append(file_path)
        
        if not audio_files:
            raise Exception("No se pudo descargar la canción")
        
        # Mover el primer archivo a la carpeta principal
        target_path = os.path.join(DOWNLOAD_PATH, os.path.basename(audio_files[0]))
        shutil.move(audio_files[0], target_path)
        return target_path
    
    except TrackPreviewUnavailableError as e:
        logging.error(f"Error de preview no disponible: {str(e)}")
        raise  # Re-lanzar la excepción específica para ser manejada en collection_processor
    except requests.exceptions.ConnectionError:
        logging.error("Error de conexión durante la descarga", exc_info=True)
        raise Exception("Problemas de conexión. Inténtalo más tarde")
    except requests.exceptions.Timeout:
        logging.error("Tiempo de espera agotado durante la descarga", exc_info=True)
        raise Exception("La descarga está tardando demasiado. Inténtalo más tarde")
    except FileNotFoundError:
        logging.error("Archivo no encontrado durante el procesamiento", exc_info=True)
        raise Exception("Esta canción no está disponible actualmente")
    except Exception as e:
        logging.error(f"Error durante la descarga: {str(e)}", exc_info=True)
        raise
    
    finally:
        # Limpiar el directorio temporal independientemente del resultado
        try:
            if os.path.exists(temp_dir):
                logging.info(f"Limpiando directorio temporal: {temp_dir}")
                shutil.rmtree(temp_dir, ignore_errors=True)
        except Exception as cleanup_error:
            logging.error(f"Error al limpiar directorio temporal: {str(cleanup_error)}")

async def enqueue_download(user_id: int, process_func: Callable[..., Awaitable[Any]], 
                        *args: Any, **kwargs: Any) -> bool:
    """
    Encola una tarea de descarga en la cola del usuario para procesamiento asíncrono.
    
    Este método es crucial para permitir que el bot responda a otros usuarios mientras
    procesa descargas largas. Evita bloquear el bucle principal de eventos.
    
    Args:
        user_id: ID del usuario de Telegram
        process_func: Función a ejecutar (process_track o process_collection)
        *args, **kwargs: Argumentos para la función de procesamiento
        
    Returns:
        bool: True si se encoló correctamente, False en caso de error
    """
    try:
        # Obtener la sesión del usuario para estadísticas
        session = UserSession.get_session(user_id)
        session.update_activity()
        
        # Verificar si el usuario tiene demasiadas descargas activas
        if session.active_downloads >= MAX_CONCURRENT_DOWNLOADS_PER_USER:
            logging.warning(f"Usuario {user_id} ha alcanzado el límite de descargas concurrentes")
            return False
            
        # Verificar límite mensual para usuarios normales
        if session.role == "normal":
            # Verificar si cambió el mes y reiniciar contador si es necesario
            session._check_monthly_limit_reset()
            
            # Obtener información mensual
            monthly_stats = session.get_monthly_downloads_left()
            remaining = monthly_stats['remaining']
            
            # Rechazar la descarga si se alcanzó el límite mensual
            if remaining <= 0:
                logging.warning(f"Usuario {user_id} ha alcanzado el límite mensual de descargas ({monthly_stats['limit']})")
                # Hacer que el update.message pueda manejar este error específico
                if 'update' in kwargs and hasattr(kwargs['update'], 'message'):
                    await kwargs['update'].message.reply_text(
                        f"⛔ Has alcanzado el límite de {monthly_stats['limit']} descargas mensuales.\n"
                        f"Considera donar para mantener el servicio y obtener beneficios adicionales."
                    )
                return False
        
        # Obtener el gestor de colas
        queue_manager = QueueManager.get_instance()
        
        # Añadir la tarea a la cola del usuario a través del gestor de colas
        task = await queue_manager.enqueue_user_task(
            user_id=user_id,
            task_func=process_func,
            queue_type="downloads",
            **kwargs
        )
        
        if task:
            logging.info(f"Tarea encolada para usuario {user_id}, descargas activas: {session.active_downloads}")
            return True
        else:
            logging.error(f"No se pudo encolar la tarea para usuario {user_id}")
            return False
        
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
        - queue_stats: Estadísticas de la cola de descargas del usuario
    """
    # Obtener estadísticas básicas de la sesión
    session = UserSession.get_session(user_id)
    stats = {
        'active_downloads': session.active_downloads,
        'total_downloads': session.total_downloads,
        'last_activity': session.last_activity
    }
    
    # Añadir estadísticas de la cola si está disponible
    try:
        queue_manager = QueueManager.get_instance()
        user_queue = queue_manager.get_user_queue(user_id, "downloads")
        stats['queue_stats'] = user_queue.get_stats()
    except Exception as e:
        logging.error(f"Error obteniendo estadísticas de cola para usuario {user_id}: {str(e)}")
        stats['queue_stats'] = {"error": "No se pudieron obtener estadísticas de cola"}
    
    return stats
