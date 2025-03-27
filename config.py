import os
import re
from dotenv import load_dotenv

# Cargar variables de entorno desde .env
load_dotenv()

# Variables de API y tokens
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
DEEZER_ARL = os.environ.get("DEEZER_AR")
VAULT_CHATID = os.environ.get("VAULT_CHATID")

# Rutas y directorios
DOWNLOAD_PATH = "./descargas"

# Opciones de descarga
class TrackFormats:
    FLAC = 9
    MP3_320 = 3
    MP3_128 = 1
    MP4_RA3 = 15
    MP4_RA2 = 14
    MP4_RA1 = 13
    DEFAULT = 8
    LOCAL = 0

# Expresiones regulares compiladas para validar URLs
DEEZER_TRACK_REGEX = re.compile(r'(https?://)?(www\.)?deezer\.com/(?:\w{2}/)?track/(\d+)')
DEEZER_ALBUM_REGEX = re.compile(r'(https?://)?(www\.)?deezer\.com/(?:\w{2}/)?album/(\d+)')
DEEZER_PLAYLIST_REGEX = re.compile(r'(https?://)?(www\.)?deezer\.com/(?:\w{2}/)?playlist/(\d+)')

# Constantes para procesamiento y limitación de recursos
BATCH_SIZE = 5  # Número de pistas por lote

# Configuración de límites de tasa y recursos
RATE_LIMIT_MAX_REQUESTS = 5  # Máximo de solicitudes por usuario
RATE_LIMIT_TIME_WINDOW = 60  # Ventana de tiempo en segundos
MAX_CONCURRENT_DOWNLOADS_PER_USER = 2  # Descargas concurrentes por usuario
MAX_CONCURRENT_DOWNLOADS_GLOBAL = 10  # Límite global de descargas concurrentes

# Tiempos
SESSION_TIMEOUT = 3600  # Tiempo de expiración de sesiones en segundos (1 hora)
SESSION_CLEANUP_INTERVAL = 600  # Intervalo para limpiar sesiones inactivas (10 minutos)

# Configuración de logging
LOG_LEVEL = "INFO"
LOG_FORMAT = "%(asctime)s - %(levelname)s - %(message)s"
