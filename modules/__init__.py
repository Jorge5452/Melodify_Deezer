"""
Módulo principal para el bot MelodifyDeluxe.

Este paquete contiene todos los módulos necesarios para el funcionamiento 
del bot, organizados por funcionalidad:

- validation: Validación de URLs y extracción de IDs
- utils: Utilidades generales y clases de simulación
- commands: Manejadores de comandos del bot
- callbacks: Procesamiento de callbacks de botones
- track_processor: Lógica de descarga de pistas
- audio_sender: Envío de archivos de audio
- search_engine: Motor centralizado de búsquedas
- decorators: Decoradores para patrones comunes

Uso:
    from modules import validation, utils, commands, etc.
"""

# Importación de comandos
from modules.commands import start, configuracion, config_callback, stats_command

# Importación de manejadores de mensajes
from modules.message_handler import handle_message

# Importación de manejadores de callbacks
from modules.callbacks import process_search_callback

# Importación de funciones de búsqueda
from modules.search_engine import (
    search_content, 
    show_search_menu, 
    show_artist_results,
    show_album_results, 
    show_track_results, 
    show_artist_info
)

# Exportar todas las funciones relevantes para ser usadas directamente desde modules
__all__ = [
    # Comandos
    'start', 
    'configuracion', 
    'config_callback', 
    'stats_command',
    
    # Manejadores
    'handle_message',
    'process_search_callback',
    
    # Búsqueda
    'search_content',
    'show_search_menu',
    'show_artist_results',
    'show_album_results',
    'show_track_results',
    'show_artist_info'
]
