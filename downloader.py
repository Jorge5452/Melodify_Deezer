import os
import asyncio
import logging
import shutil
from typing import Union, List
from deezer import Deezer
from deemix import generateDownloadObject
from deemix.downloader import Downloader
from deemix.settings import load, save

DOWNLOAD_PATH = "./descargas"

class LogListener:
    def send(self, key, value=None):
        logging.debug(f"[DEEMIX] {key}: {value}")

async def download_track(url: str, dz, settings, listener) -> Union[str, List[str]]:
    """
    Descarga una pista, álbum o playlist de Deezer.
    
    Args:
        url: URL de Deezer para descargar
        dz: Instancia de Deezer autenticada
        settings: Configuración de descarga
        listener: Listener para logs
        
    Returns:
        Ruta al archivo descargado o lista de rutas para álbumes/playlists
    """
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, sync_download_track, url, dz, settings, listener)

def sync_download_track(url: str, dz, settings, listener) -> Union[str, List[str]]:
    """
    Versión sincrónica de la función para descargar contenido de Deezer.
    """
    os.makedirs(DOWNLOAD_PATH, exist_ok=True)
    
    # Determinar tipo de contenido
    is_track = "/track/" in url
    is_album = "/album/" in url
    is_playlist = "/playlist/" in url
    
    # Crear un directorio temporal único para evitar conflictos
    import uuid
    temp_dir = os.path.join(DOWNLOAD_PATH, f"temp_{uuid.uuid4().hex}")
    os.makedirs(temp_dir, exist_ok=True)
    
    # Guardar settings temporales para esta descarga
    temp_settings = settings.copy()
    temp_settings["downloadLocation"] = temp_dir
    
    try:
        # Al principio de sync_download_track
        logging.info(f"Iniciando descarga: {url}")
        logging.info(f"Tipo de contenido: {'track' if is_track else 'album' if is_album else 'playlist' if is_playlist else 'desconocido'}")
        
        # Generar objeto de descarga
        bitrate = settings["maxBitrate"]
        plugins = {}  # Sin plugins adicionales
        download_obj = generateDownloadObject(dz, url, bitrate, plugins, listener)
        
        # Después de generar download_obj - CORREGIDO el acceso a atributos
        try:
            if isinstance(download_obj, list):
                logging.info(f"Objetos a descargar: {len(download_obj)}")
                # No intentamos acceder a atributos específicos de los objetos en la lista
            else:
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
        except Exception as e:
            logging.warning(f"No se pudo obtener info del objeto de descarga: {str(e)}")
        
        # Procesar descarga según el tipo
        if isinstance(download_obj, list):
            # Múltiples pistas (álbum o playlist)
            for obj in download_obj:
                Downloader(dz, obj, temp_settings, listener).start()
            
            # Obtener lista de archivos descargados
            downloaded_files = []
            for root, _, files in os.walk(temp_dir):
                for file in files:
                    if file.endswith(('.mp3', '.flac', '.m4a')):
                        file_path = os.path.join(root, file)
                        
                        # Generar nombre único para evitar sobrescribir archivos
                        base_name, ext = os.path.splitext(file)
                        target_file = file
                        counter = 1
                        while os.path.exists(os.path.join(DOWNLOAD_PATH, target_file)):
                            target_file = f"{base_name}_{counter}{ext}"
                            counter += 1
                            
                        # Mover a la carpeta principal de descargas
                        target_path = os.path.join(DOWNLOAD_PATH, target_file)
                        shutil.move(file_path, target_path)
                        downloaded_files.append(target_path)
                        logging.info(f"Archivo añadido a lista: {target_path}")
            
            if not downloaded_files:
                raise Exception("No se encontraron archivos de audio descargados.")
            
            # Ordenar archivos por nombre para mantener el orden de las pistas
            downloaded_files.sort()
            
            # Para playlists o álbumes, devolvemos la lista de archivos
            if is_album or is_playlist:
                return downloaded_files
            # Para un solo track seleccionado de una lista, devolvemos el primero
            return downloaded_files[0]
            
        else:
            # Una sola pista
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
