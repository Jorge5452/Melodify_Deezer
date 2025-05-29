"""
Módulo de configuración para la aplicación Melodify_Deezer.

Este módulo centraliza todas las configuraciones, constantes y variables
de entorno necesarias para el funcionamiento del bot de Telegram que
permite descargar música desde Deezer.
"""

import os
import re
from dotenv import load_dotenv
from typing import Dict, Pattern, Union, List, Any

# Cargar variables de entorno desde el archivo .env
load_dotenv()

# ----- TOKENS Y CLAVES DE API -----
# Token para la API de Telegram Bot
TELEGRAM_TOKEN: str = os.environ.get("TELEGRAM_TOKEN")
# ARL (Authentication Renewal Login) para la autenticación con Deezer
DEEZER_ARL: str = os.environ.get("DEEZER_AR")
# ID del chat donde se almacenarán los archivos en "vault"
VAULT_CHATID: str = os.environ.get("VAULT_CHATID")

# ----- RUTAS Y DIRECTORIOS -----
# Directorio donde se guardarán las descargas
DOWNLOAD_PATH: str = "./descargas"

# ----- OPCIONES DE DESCARGA -----
class TrackFormats:
    """
    Define los formatos disponibles para la descarga de pistas de música.
    
    Los valores numéricos corresponden a los códigos de calidad en Deezer:
    - FLAC: Audio sin pérdida
    - MP3_320: MP3 de alta calidad (320kbps)
    - MP3_128: MP3 de calidad estándar (128kbps)
    - MP4_RA*: Formatos de audio adaptativo con diferentes calidades
    """
    FLAC: int = 9      # FLAC 1411kbps
    MP3_320: int = 3   # MP3 320kbps
    MP3_128: int = 1   # MP3 128kbps
    MP4_RA3: int = 15  # MP4 alta calidad
    MP4_RA2: int = 14  # MP4 calidad media
    MP4_RA1: int = 13  # MP4 calidad baja
    DEFAULT: int = 8   # Mejor calidad disponible
    LOCAL: int = 0     # Archivo local

# ----- EXPRESIONES REGULARES -----
# Patrones compilados para validar y extraer información de URLs de Deezer
DEEZER_TRACK_REGEX: Pattern = re.compile(r'(https?://)?(www\.)?deezer\.com/(?:\w{2}/)?track/(\d+)')
DEEZER_ALBUM_REGEX: Pattern = re.compile(r'(https?://)?(www\.)?deezer\.com/(?:\w{2}/)?album/(\d+)')
DEEZER_PLAYLIST_REGEX: Pattern = re.compile(r'(https?://)?(www\.)?deezer\.com/(?:\w{2}/)?playlist/(\d+)')

# ----- CONSTANTES DE PROCESAMIENTO -----
# Número de pistas a procesar por lote en colecciones grandes
BATCH_SIZE: int = 5

# ----- LÍMITES Y TASAS -----
# Máximo de solicitudes por usuario en la ventana de tiempo
RATE_LIMIT_MAX_REQUESTS: int = 5
# Ventana de tiempo en segundos para la limitación de tasa
RATE_LIMIT_TIME_WINDOW: int = 60
# Máximo de descargas concurrentes permitidas por usuario
MAX_CONCURRENT_DOWNLOADS_PER_USER: int = 2
# Límite global de descargas concurrentes en todo el sistema
MAX_CONCURRENT_DOWNLOADS_GLOBAL: int = 10

# ----- TIEMPOS Y CADUCIDAD -----
# Tiempo en segundos antes de que una sesión de usuario expire por inactividad (1 hora)
SESSION_TIMEOUT: int = 3600
# Intervalo en segundos para ejecutar la limpieza de sesiones inactivas (10 minutos)
SESSION_CLEANUP_INTERVAL: int = 600

# ----- GESTIÓN DE SESIONES -----
# Máximo número de sesiones mantenidas en memoria
SESSION_CACHE_SIZE: int = 100
# Tiempos de expiración por rol (segundos)
SESSION_TIERS: Dict[str, int] = {
    "admin": 86400,     # 24 horas para administradores
    "premium": 43200,   # 12 horas para usuarios premium
    "normal": 3600      # 1 hora para usuarios normales
}
# Tamaño en bytes para activar compresión de datos
COMPRESSION_THRESHOLD: int = 1024
# Número de operaciones de BD antes de realizar flush
DB_BATCH_SIZE: int = 10
# Tiempo entre flushes de BD (segundos)
DB_FLUSH_INTERVAL: int = 5
# Límite mensual de descargas para usuarios normales
MONTHLY_DOWNLOAD_LIMIT: int = 50
# Lista ordenada de roles por jerarquía (menor a mayor nivel)
ROLES_HIERARCHY: List[str] = ["normal", "premium", "admin"]

# ----- LOGGING -----
# Nivel de detalle para los logs (DEBUG, INFO, WARNING, ERROR, CRITICAL)
LOG_LEVEL: str = "WARNING"
# Formato para los mensajes de log
LOG_FORMAT: str = "%(asctime)s - %(levelname)s - %(message)s"


# ----- CONSTANTES DEL VAULT -----

VAULT_JSON = "vault_data.json"
VAULT_BACKUP = "vault_data.backup.json"
MAX_VAULT_ENTRIES = 1000  # Límite máximo de entradas en el vault

# Configuración de timeouts para HTTP y Telegram
# Valores predeterminados más generosos para operaciones que implican
# archivos grandes como subidas de audio
HTTP_CONNECT_TIMEOUT = float(os.getenv("HTTP_CONNECT_TIMEOUT", "20.0"))  # 20 segundos
HTTP_READ_TIMEOUT = float(os.getenv("HTTP_READ_TIMEOUT", "300.0"))       # 5 minutos
HTTP_WRITE_TIMEOUT = float(os.getenv("HTTP_WRITE_TIMEOUT", "300.0"))     # 5 minutos

# Configuración de reintentos
MAX_RETRIES = int(os.getenv("MAX_RETRIES", "3"))
INITIAL_RETRY_DELAY = float(os.getenv("INITIAL_RETRY_DELAY", "2.0"))
RETRY_BACKOFF_FACTOR = float(os.getenv("RETRY_BACKOFF_FACTOR", "2.0"))
