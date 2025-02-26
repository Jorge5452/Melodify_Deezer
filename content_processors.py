from abc import ABC, abstractmethod
from bot import process_track, process_collection
import logging

class ContentProcessor(ABC):
    @abstractmethod
    async def process(self, update, context, dz, settings, vault_chat_id, listener, url, content_id):
        """
        Método que debe implementar cada estrategia para procesar el contenido.
        """
        pass

class TrackProcessor(ContentProcessor):
    async def process(self, update, context, dz, settings, vault_chat_id, listener, url, content_id):
        logging.info("Usando TrackProcessor")
        # Se reutiliza la lógica existente para procesar tracks
        await process_track(update, context, url, content_id, dz, settings, vault_chat_id, listener)

class AlbumProcessor(ContentProcessor):
    async def process(self, update, context, dz, settings, vault_chat_id, listener, url, content_id):
        logging.info("Usando AlbumProcessor")
        # Se utiliza process_collection con el tipo "album"
        await process_collection(update, context, url, "album", content_id, dz, settings, vault_chat_id, listener)

class PlaylistProcessor(ContentProcessor):
    async def process(self, update, context, dz, settings, vault_chat_id, listener, url, content_id):
        logging.info("Usando PlaylistProcessor")
        # Se utiliza process_collection con el tipo "playlist"
        await process_collection(update, context, url, "playlist", content_id, dz, settings, vault_chat_id, listener)

# Diccionario de estrategias basado en el tipo de contenido
strategy_map = {
    "track": TrackProcessor(),
    "album": AlbumProcessor(),
    "playlist": PlaylistProcessor()
} 