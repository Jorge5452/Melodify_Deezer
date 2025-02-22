import os
import asyncio
import logging
from deezer import Deezer
from deemix import generateDownloadObject
from deemix.downloader import Downloader
from deemix.settings import load, save

DOWNLOAD_PATH = "./descargas"

class LogListener:
    def send(self, key, value=None):
        logging.debug(f"[DEEMIX] {key}: {value}")

async def download_track(url: str, dz, settings, listener) -> str:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, sync_download_track, url, dz, settings, listener)

def sync_download_track(url: str, dz, settings, listener) -> str:
    os.makedirs(DOWNLOAD_PATH, exist_ok=True)
    before_files = set(os.listdir(DOWNLOAD_PATH))
    bitrate = settings["maxBitrate"]
    plugins = {}  # Sin plugins adicionales
    download_obj = generateDownloadObject(dz, url, bitrate, plugins, listener)
    if isinstance(download_obj, list):
        download_obj = download_obj[0]
    Downloader(dz, download_obj, settings, listener).start()
    after_files = set(os.listdir(DOWNLOAD_PATH))
    new_files = after_files - before_files
    if not new_files:
        raise Exception("No se encontró ningún archivo descargado.")
    file_name = new_files.pop()
    return os.path.join(DOWNLOAD_PATH, file_name)
