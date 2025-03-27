"""
Módulo de gestión de sesiones de usuario para Melodify Deezer.

Proporciona clases para administrar el estado de los usuarios, controlar tasas
de solicitudes, encolar descargas y gestionar recursos del sistema para evitar
sobrecargas.
"""

import asyncio
import time
import logging
from typing import Dict, Any, Optional, Callable, Awaitable, List, Union, Tuple
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
    """
    Controla la tasa de solicitudes por usuario para evitar sobrecargas.
    
    Implementa un mecanismo de ventana deslizante para limitar el número
    de solicitudes que un usuario puede hacer en un período de tiempo.
    """
    
    def __init__(self, max_requests: int = RATE_LIMIT_MAX_REQUESTS, 
                time_window: int = RATE_LIMIT_TIME_WINDOW) -> None:
        """
        Inicializa el limitador de tasa.
        
        Args:
            max_requests: Número máximo de solicitudes permitidas en la ventana de tiempo
            time_window: Duración de la ventana de tiempo en segundos
        """
        self.max_requests: int = max_requests
        self.time_window: int = time_window
        self.request_timestamps: List[float] = []
    
    async def acquire(self) -> bool:
        """
        Intenta adquirir un permiso para realizar una solicitud.
        
        Verifica si el usuario ha excedido su cuota de solicitudes en
        la ventana de tiempo actual.
        
        Returns:
            True si se permite la solicitud, False si se debe limitar
        """
        current_time = time.time()
        
        # Limpiar timestamps antiguos fuera de la ventana de tiempo
        self.request_timestamps = [ts for ts in self.request_timestamps 
                                  if current_time - ts < self.time_window]
        
        # Verificar si se excede el límite
        if len(self.request_timestamps) >= self.max_requests:
            return False
        
        # Registrar nueva solicitud
        self.request_timestamps.append(current_time)
        return True
    
    async def wait_for_slot(self) -> None:
        """
        Espera hasta que haya un slot disponible para realizar una solicitud.
        
        Bloqueará la ejecución hasta que el usuario pueda realizar una nueva
        solicitud según las restricciones de tasa configuradas.
        """
        while True:
            if await self.acquire():
                return
            # Esperar antes de verificar nuevamente
            await asyncio.sleep(1)

class DownloadQueue:
    """
    Gestiona una cola de descargas para un usuario.
    
    Implementa un trabajador asíncrono que procesa las descargas de manera
    secuencial respetando el límite de concurrencia configurado.
    """
    
    def __init__(self, max_concurrent: int = MAX_CONCURRENT_DOWNLOADS_PER_USER) -> None:
        """
        Inicializa la cola de descargas.
        
        Args:
            max_concurrent: Número máximo de descargas concurrentes permitidas
        """
        self.semaphore: asyncio.Semaphore = asyncio.Semaphore(max_concurrent)
        self.queue: asyncio.Queue = asyncio.Queue()
        self.active: bool = False
        self._worker_task: Optional[asyncio.Task] = None
    
    async def add_download(self, download_func: Callable[..., Awaitable[Any]], 
                        *args: Any, **kwargs: Any) -> None:
        """
        Añade una tarea de descarga a la cola.
        
        Args:
            download_func: Función asíncrona que realiza la descarga
            *args, **kwargs: Argumentos para la función de descarga
        """
        # Encolar la tarea con sus argumentos
        await self.queue.put((download_func, args, kwargs))
        
        # Iniciar el trabajador si no está activo
        if not self.active:
            self.active = True
            self._worker_task = asyncio.create_task(self._download_worker())
    
    async def _download_worker(self) -> None:
        """
        Procesa las descargas en la cola de manera secuencial.
        
        Este método se ejecuta como una tarea en segundo plano y procesa
        las solicitudes de descarga respetando el límite de concurrencia.
        """
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
                
                # Adquirir un slot del semáforo para controlar concurrencia
                async with self.semaphore:
                    # Ejecutar la descarga con los parámetros proporcionados
                    await download_func(*args, **kwargs)
                
                # Marcar la tarea como completada
                self.queue.task_done()
            except Exception as e:
                logging.error(f"Error en worker de descargas: {str(e)}", exc_info=True)
                # Breve pausa para evitar bucle continuo en caso de errores
                await asyncio.sleep(1)
    
    def is_active(self) -> bool:
        """
        Verifica si hay descargas activas en la cola.
        
        Returns:
            True si hay descargas en proceso, False en caso contrario
        """
        return self.active
    
    async def stop(self) -> None:
        """
        Detiene el procesamiento de la cola de descargas.
        
        Cancela la tarea del trabajador y marca la cola como inactiva.
        """
        self.active = False
        if self._worker_task:
            try:
                # Cancelar la tarea y esperar a que termine
                self._worker_task.cancel()
                await asyncio.gather(self._worker_task, return_exceptions=True)
            except Exception:
                # Ignorar errores al cancelar la tarea
                pass

class UserSession:
    """
    Mantiene el estado y las preferencias de un usuario en el sistema.
    
    Gestiona la configuración personalizada, estadísticas, colas de descarga
    y control de tasas para cada usuario del bot.
    """
    
    # Almacenamiento estático compartido para todas las sesiones
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
            Instancia de UserSession para el usuario específico
        """
        if user_id not in cls._sessions:
            cls._sessions[user_id] = UserSession(user_id)
        return cls._sessions[user_id]
    
    @classmethod
    def get_active_sessions_count(cls) -> int:
        """
        Obtiene el número de sesiones activas en el sistema.
        
        Returns:
            Número total de sesiones de usuario activas
        """
        return len(cls._sessions)
    
    @classmethod
    async def get_global_semaphore(cls) -> asyncio.Semaphore:
        """
        Obtiene el semáforo global para limitar las descargas concurrentes.
        
        Returns:
            Semáforo global compartido entre todas las sesiones
        """
        return cls._global_semaphore
    
    def __init__(self, user_id: int) -> None:
        """
        Inicializa una nueva sesión de usuario.
        
        Args:
            user_id: ID del usuario de Telegram
        """
        self.user_id: int = user_id
        # Cargar configuración inicial desde los ajustes globales
        self.settings: Dict[str, Any] = load_settings().copy()
        # Timestamp de la última actividad para expiración
        self.last_activity: float = time.time()
        # Cola para gestionar descargas
        self.download_queue: DownloadQueue = DownloadQueue()
        # Limitador de tasa para este usuario
        self.rate_limiter: RateLimiter = RateLimiter()
        # Almacenamiento para datos contextuales de la sesión
        self.context_data: Dict[str, Any] = {}
        # Contadores para estadísticas
        self.active_downloads: int = 0
        self.total_downloads: int = 0
    
    def update_activity(self) -> None:
        """
        Actualiza el timestamp de la última actividad del usuario.
        
        Esto retrasa la expiración de la sesión mientras el usuario esté activo.
        """
        self.last_activity = time.time()
    
    def is_expired(self, timeout: int = SESSION_TIMEOUT) -> bool:
        """
        Verifica si la sesión ha expirado por inactividad.
        
        Args:
            timeout: Tiempo de inactividad en segundos antes de expirar
            
        Returns:
            True si la sesión ha expirado, False si sigue activa
        """
        return time.time() - self.last_activity > timeout
    
    def get_setting(self, key: str, default: Any = None) -> Any:
        """
        Obtiene un valor de configuración específico para este usuario.
        
        Args:
            key: Clave de configuración
            default: Valor predeterminado si la clave no existe
            
        Returns:
            Valor de configuración para el usuario
        """
        return self.settings.get(key, default)
    
    def update_setting(self, key: str, value: Any) -> None:
        """
        Actualiza un valor de configuración para este usuario.
        
        Args:
            key: Clave de configuración
            value: Nuevo valor a establecer
        """
        self.settings[key] = value
    
    async def add_download_task(self, download_func: Callable[..., Awaitable[Any]], 
                             *args: Any, **kwargs: Any) -> None:
        """
        Añade una tarea de descarga a la cola del usuario.
        
        Args:
            download_func: Función asíncrona que realiza la descarga
            *args, **kwargs: Argumentos para la función de descarga
        """
        # Actualizar timestamp de actividad
        self.update_activity()
        # Añadir a la cola de descargas
        await self.download_queue.add_download(download_func, *args, **kwargs)
    
    async def wait_for_rate_limit(self) -> None:
        """
        Espera hasta que se pueda realizar una nueva solicitud según el límite de tasa.
        
        Bloquea la ejecución hasta que el limitador de tasa permita una nueva solicitud.
        """
        await self.rate_limiter.wait_for_slot()
        self.update_activity()

# Función para limpieza periódica de sesiones inactivas
async def cleanup_sessions() -> None:
    """
    Elimina sesiones inactivas periódicamente para liberar recursos.
    
    Esta función se ejecuta como una tarea en segundo plano y verifica
    periódicamente las sesiones que han excedido el tiempo de inactividad.
    """
    while True:
        try:
            # Identificar sesiones expiradas
            expired_user_ids = []
            for user_id, session in UserSession._sessions.items():
                if session.is_expired():
                    expired_user_ids.append(user_id)
            
            # Eliminar sesiones expiradas
            for user_id in expired_user_ids:
                session = UserSession._sessions.pop(user_id, None)
                if session:
                    # Detener cualquier descarga pendiente
                    await session.download_queue.stop()
                    logging.info(f"Sesión del usuario {user_id} eliminada por inactividad")
            
            # Registrar estadísticas de sesiones activas
            active_sessions = UserSession.get_active_sessions_count()
            if active_sessions > 0:
                logging.info(f"Sesiones activas: {active_sessions}")
                
        except Exception as e:
            logging.error(f"Error en limpieza de sesiones: {str(e)}", exc_info=True)
        
        # Esperar antes de la próxima limpieza
        await asyncio.sleep(SESSION_CLEANUP_INTERVAL)
