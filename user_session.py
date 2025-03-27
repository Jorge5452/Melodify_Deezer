import asyncio
import time
import logging
from typing import Dict, Any, Optional
from deemix.settings import load as load_settings
from config import (
    RATE_LIMIT_MAX_REQUESTS,
    RATE_LIMIT_TIME_WINDOW,
    MAX_CONCURRENT_DOWNLOADS_PER_USER,
    MAX_CONCURRENT_DOWNLOADS_GLOBAL,
    SESSION_TIMEOUT,
    SESSION_CLEANUP_INTERVAL
)

class RateLimiter:
    """Controla la tasa de solicitudes por usuario."""
    
    def __init__(self, max_requests: int = RATE_LIMIT_MAX_REQUESTS, time_window: int = RATE_LIMIT_TIME_WINDOW):
        """
        Inicializa el limitador de tasa.
        
        Args:
            max_requests: Número máximo de solicitudes permitidas en la ventana de tiempo
            time_window: Duración de la ventana de tiempo en segundos
        """
        self.max_requests = max_requests
        self.time_window = time_window
        self.request_timestamps = []
    
    async def acquire(self) -> bool:
        """
        Intenta adquirir un permiso para realizar una solicitud.
        
        Returns:
            True si se permite la solicitud, False en caso contrario
        """
        current_time = time.time()
        
        # Limpiar timestamps antiguos
        self.request_timestamps = [ts for ts in self.request_timestamps 
                                  if current_time - ts < self.time_window]
        
        # Verificar si se excede el límite
        if len(self.request_timestamps) >= self.max_requests:
            return False
        
        # Registrar nueva solicitud
        self.request_timestamps.append(current_time)
        return True
    
    async def wait_for_slot(self) -> None:
        """Espera hasta que haya un slot disponible."""
        while True:
            if await self.acquire():
                return
            await asyncio.sleep(1)

class DownloadQueue:
    """Gestiona una cola de descargas para un usuario."""
    
    def __init__(self, max_concurrent: int = MAX_CONCURRENT_DOWNLOADS_PER_USER):
        """
        Inicializa la cola de descargas.
        
        Args:
            max_concurrent: Número máximo de descargas concurrentes
        """
        self.semaphore = asyncio.Semaphore(max_concurrent)
        self.queue = asyncio.Queue()
        self.active = False
        self._worker_task = None
    
    async def add_download(self, download_func, *args, **kwargs):
        """
        Añade una tarea de descarga a la cola.
        
        Args:
            download_func: Función asíncrona que realiza la descarga
            *args, **kwargs: Argumentos para la función de descarga
        """
        await self.queue.put((download_func, args, kwargs))
        
        # Iniciar el trabajador si no está activo
        if not self.active:
            self.active = True
            self._worker_task = asyncio.create_task(self._download_worker())
    
    async def _download_worker(self):
        """Procesa las descargas en la cola."""
        while self.active:
            try:
                # Esperar por una tarea si la cola está vacía
                if self.queue.empty():
                    # Esperar un poco y verificar si hay nuevas tareas
                    await asyncio.sleep(1)
                    if self.queue.empty():
                        self.active = False
                        break
                    continue
                
                # Obtener la siguiente tarea de descarga
                download_func, args, kwargs = await self.queue.get()
                
                # Adquirir un slot del semáforo
                async with self.semaphore:
                    # Ejecutar la descarga
                    await download_func(*args, **kwargs)
                
                # Marcar la tarea como completada
                self.queue.task_done()
            except Exception as e:
                logging.error(f"Error en worker de descargas: {str(e)}", exc_info=True)
                await asyncio.sleep(1)
    
    def is_active(self) -> bool:
        """Verifica si hay descargas activas."""
        return self.active
    
    async def stop(self):
        """Detiene el procesamiento de la cola."""
        self.active = False
        if self._worker_task:
            try:
                self._worker_task.cancel()
                await asyncio.gather(self._worker_task, return_exceptions=True)
            except:
                pass

class UserSession:
    """Mantiene el estado y las preferencias de un usuario."""
    
    # Diccionario compartido para almacenar todas las sesiones activas
    _sessions: Dict[int, "UserSession"] = {}
    # Semáforo global para limitar las descargas concurrentes en todo el sistema
    _global_semaphore = asyncio.Semaphore(MAX_CONCURRENT_DOWNLOADS_GLOBAL)
    
    @classmethod
    def get_session(cls, user_id: int) -> "UserSession":
        """
        Obtiene la sesión de un usuario, creándola si no existe.
        
        Args:
            user_id: ID del usuario de Telegram
            
        Returns:
            Instancia de UserSession para el usuario
        """
        if user_id not in cls._sessions:
            cls._sessions[user_id] = UserSession(user_id)
        return cls._sessions[user_id]
    
    @classmethod
    def get_active_sessions_count(cls) -> int:
        """
        Obtiene el número de sesiones activas.
        
        Returns:
            Número de sesiones activas
        """
        return len(cls._sessions)
    
    @classmethod
    async def get_global_semaphore(cls):
        """
        Obtiene el semáforo global para limitar las descargas concurrentes.
        
        Returns:
            Semáforo global
        """
        return cls._global_semaphore
    
    def __init__(self, user_id: int):
        """
        Inicializa una nueva sesión de usuario.
        
        Args:
            user_id: ID del usuario de Telegram
        """
        self.user_id = user_id
        self.settings = load_settings().copy()
        self.last_activity = time.time()
        self.download_queue = DownloadQueue()
        self.rate_limiter = RateLimiter()
        self.context_data: Dict[str, Any] = {}
        self.active_downloads = 0
        self.total_downloads = 0
    
    def update_activity(self):
        """Actualiza el timestamp de la última actividad."""
        self.last_activity = time.time()
    
    def is_expired(self, timeout: int = SESSION_TIMEOUT) -> bool:
        """
        Verifica si la sesión ha expirado por inactividad.
        
        Args:
            timeout: Tiempo de inactividad en segundos antes de expirar
            
        Returns:
            True si la sesión ha expirado, False en caso contrario
        """
        return time.time() - self.last_activity > timeout
    
    def get_setting(self, key: str, default=None) -> Any:
        """
        Obtiene un valor de configuración.
        
        Args:
            key: Clave de configuración
            default: Valor predeterminado si la clave no existe
            
        Returns:
            Valor de configuración
        """
        return self.settings.get(key, default)
    
    def update_setting(self, key: str, value: Any) -> None:
        """
        Actualiza un valor de configuración.
        
        Args:
            key: Clave de configuración
            value: Nuevo valor
        """
        self.settings[key] = value
    
    async def add_download_task(self, download_func, *args, **kwargs) -> None:
        """
        Añade una tarea de descarga a la cola del usuario.
        
        Args:
            download_func: Función asíncrona que realiza la descarga
            *args, **kwargs: Argumentos para la función de descarga
        """
        self.update_activity()
        await self.download_queue.add_download(download_func, *args, **kwargs)
    
    async def wait_for_rate_limit(self) -> None:
        """Espera hasta que se pueda realizar una nueva solicitud según el límite de tasa."""
        await self.rate_limiter.wait_for_slot()
        self.update_activity()

# Iniciar una tarea de limpieza periódica para sesiones inactivas
async def cleanup_sessions():
    """Elimina sesiones inactivas periódicamente."""
    while True:
        try:
            expired_user_ids = []
            for user_id, session in UserSession._sessions.items():
                if session.is_expired():
                    expired_user_ids.append(user_id)
            
            # Eliminar sesiones expiradas
            for user_id in expired_user_ids:
                session = UserSession._sessions.pop(user_id, None)
                if session:
                    await session.download_queue.stop()
                    logging.info(f"Sesión del usuario {user_id} eliminada por inactividad")
            
            # Registrar estadísticas
            active_sessions = UserSession.get_active_sessions_count()
            if active_sessions > 0:
                logging.info(f"Sesiones activas: {active_sessions}")
                
        except Exception as e:
            logging.error(f"Error en limpieza de sesiones: {str(e)}", exc_info=True)
        
        # Esperar antes de la próxima limpieza
        await asyncio.sleep(SESSION_CLEANUP_INTERVAL)  # 10 minutos
