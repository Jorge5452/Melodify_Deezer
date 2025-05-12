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

# Verificar si db_manager está disponible
DB_AVAILABLE = False
try:
    import db_manager
    DB_AVAILABLE = True
except ImportError:
    # La funcionalidad de persistencia será desactivada
    pass

# Configuración de límites según roles
ROLE_DOWNLOAD_LIMITS = {
    "normal": 2,
    "premium": 5,
    "admin": 0  # 0 significa sin límite
}

# Límite de descargas mensuales para usuarios normales
MONTHLY_DOWNLOAD_LIMIT = 450

# Roles en orden ascendente de privilegios
ROLES_HIERARCHY = ["normal", "premium", "admin"]

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
    
    def update_concurrency_limit(self, new_limit: int) -> None:
        """
        Actualiza el límite de concurrencia para este usuario.
        
        Args:
            new_limit: Nuevo límite de descargas concurrentes
        """
        # Si es 0 (admin), usar un valor alto para simulador "sin límite"
        if new_limit == 0:
            new_limit = 100
            
        self.semaphore = asyncio.Semaphore(new_limit)
        logging.debug(f"Límite de concurrencia actualizado a {new_limit}")

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
    # Control de persistencia en BD
    _use_database: bool = False
    
    @classmethod
    def enable_persistence(cls, enable: bool = True) -> None:
        """
        Activa o desactiva la persistencia en base de datos.
        
        Args:
            enable: True para activar, False para desactivar
        """
        if enable and not DB_AVAILABLE:
            logging.warning("No se puede activar la persistencia: módulo db_manager no disponible")
            return
            
        cls._use_database = enable and DB_AVAILABLE
        logging.info(f"Persistencia en base de datos: {'activada' if cls._use_database else 'desactivada'}")
    
    @classmethod
    def get_session(cls, user_id: int) -> "UserSession":
        """
        Obtiene la sesión de un usuario, creándola si no existe.
        Si la persistencia está activada, intenta cargarla de la BD.
        
        Args:
            user_id: ID del usuario de Telegram
            
        Returns:
            Instancia de UserSession para el usuario específico
        """
        # Verificar si ya existe en memoria
        if user_id not in cls._sessions:
            # Si persistencia activada, intentar cargar desde BD
            if cls._use_database:
                try:
                    session_data = db_manager.load_user_session(user_id)
                    
                    if session_data:
                        # Crear sesión con datos de BD
                        session = cls(user_id)
                        session.settings = session_data["settings"]
                        session.last_activity = session_data["last_activity"]
                        session.context_data = session_data["context_data"]
                        session.total_downloads = session_data["total_downloads"]
                        session.active_downloads = session_data["active_downloads"]
                        session.role = session_data.get("role", "normal")
                        # Campos adicionales para tracking
                        session.created_at = session_data["created_at"]
                        session.updated_at = session_data["updated_at"]
                        
                        # Actualizar límites basados en rol
                        limit = ROLE_DOWNLOAD_LIMITS.get(session.role, ROLE_DOWNLOAD_LIMITS["normal"])
                        session.download_queue.update_concurrency_limit(limit)
                        
                        cls._sessions[user_id] = session
                        return session
                except Exception as e:
                    logging.error(f"Error cargando sesión {user_id} desde BD: {e}", 
                                 exc_info=True)
            
            # Si no está en BD o falló la carga, crear nueva
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
    
    @classmethod
    def load_all_sessions_from_db(cls) -> None:
        """
        Carga todas las sesiones desde la base de datos.
        Solo si la persistencia está activada.
        """
        if not cls._use_database:
            logging.info("Persistencia desactivada: no se cargan sesiones desde BD")
            return
            
        try:
            sessions_data = db_manager.load_all_sessions()
            loaded = 0
            
            for user_id, data in sessions_data.items():
                if user_id not in cls._sessions:
                    # Crear sesión con datos de BD
                    session = cls(user_id)
                    session.settings = data["settings"]
                    session.last_activity = data["last_activity"]
                    session.context_data = data["context_data"]
                    session.total_downloads = data["total_downloads"]
                    session.active_downloads = data["active_downloads"]
                    session.role = data.get("role", "normal")
                    session.created_at = data["created_at"]
                    session.updated_at = data["updated_at"]
                    
                    # Actualizar límites basados en rol
                    limit = ROLE_DOWNLOAD_LIMITS.get(session.role, ROLE_DOWNLOAD_LIMITS["normal"])
                    session.download_queue.update_concurrency_limit(limit)
                    
                    cls._sessions[user_id] = session
                    loaded += 1
            
            logging.info(f"Cargadas {loaded} sesiones desde la base de datos")
        except Exception as e:
            logging.error(f"Error cargando sesiones desde BD: {e}", exc_info=True)
    
    @classmethod
    def _create_session_from_data(cls, user_id: int, data: Dict[str, Any]) -> "UserSession":
        """
        Crea una instancia de UserSession a partir de datos de BD.
        
        Args:
            user_id: ID del usuario
            data: Datos de la sesión cargados desde BD
            
        Returns:
            Nueva instancia de UserSession
        """
        session = cls(user_id)
        session.settings = data.get("settings", session.settings)
        session.last_activity = data.get("last_activity", session.last_activity)
        session.context_data = data.get("context_data", {})
        session.total_downloads = data.get("total_downloads", 0)
        session.active_downloads = data.get("active_downloads", 0)
        session.role = data.get("role", "normal")
        
        # Campos de tracking mensuales
        session.monthly_downloads = data.get("monthly_downloads", 0)
        session.current_month = data.get("current_month", session._get_current_month())
        
        # Campos de tracking
        session.created_at = data.get("created_at", time.time())
        session.updated_at = data.get("updated_at", time.time())
        
        # Actualizar límites basados en rol
        limit = ROLE_DOWNLOAD_LIMITS.get(session.role, ROLE_DOWNLOAD_LIMITS["normal"])
        session.download_queue.update_concurrency_limit(limit)
        
        return session
    
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
        # Control de límites mensuales (para usuarios normales)
        self.monthly_downloads: int = 0
        self.current_month: int = self._get_current_month()
        # Rol del usuario (por defecto: normal)
        self.role: str = "normal"
        # Campos adicionales para tracking
        self.created_at: float = time.time()
        self.updated_at: float = time.time()
        # Indicador de cambios pendientes
        self._pending_changes: bool = False
        
        # Configurar límites iniciales según rol
        limit = ROLE_DOWNLOAD_LIMITS.get(self.role, ROLE_DOWNLOAD_LIMITS["normal"])
        self.download_queue.update_concurrency_limit(limit)
    
    def _get_current_month(self) -> int:
        """
        Obtiene el mes actual como entero.
        
        Returns:
            Número de mes (1-12)
        """
        from datetime import datetime
        return datetime.now().month
        
    def _check_monthly_limit_reset(self) -> None:
        """
        Verifica si debe reiniciarse el contador mensual por cambio de mes.
        """
        current_month = self._get_current_month()
        if current_month != self.current_month:
            # Reiniciar contador si cambió el mes
            self.monthly_downloads = 0
            self.current_month = current_month
            self._pending_changes = True
    
    def update_activity(self) -> None:
        """
        Actualiza el timestamp de la última actividad del usuario.
        
        Esto retrasa la expiración de la sesión mientras el usuario esté activo.
        Si la persistencia está habilitada, guarda en BD.
        """
        self.last_activity = time.time()
        self.updated_at = time.time()
        
        # Si persistencia activada, guardar asíncronamente
        if self.__class__._use_database:
            asyncio.create_task(self._save_to_db())
    
    def is_expired(self, timeout: int = SESSION_TIMEOUT) -> bool:
        """
        Verifica si la sesión ha expirado por inactividad.
        
        Args:
            timeout: Tiempo en segundos después del cual una sesión se considera inactiva
            
        Returns:
            True si la sesión ha expirado, False en caso contrario
        """
        return time.time() - self.last_activity > timeout
    
    def get_setting(self, key: str, default: Any = None) -> Any:
        """
        Obtiene una configuración específica del usuario.
        
        Args:
            key: Nombre de la configuración
            default: Valor por defecto si la configuración no existe
            
        Returns:
            Valor de la configuración o el valor por defecto
        """
        return self.settings.get(key, default)
    
    def update_setting(self, key: str, value: Any) -> None:
        """
        Actualiza una configuración específica del usuario.
        
        Args:
            key: Nombre de la configuración
            value: Nuevo valor para la configuración
        """
        self.settings[key] = value
        self.updated_at = time.time()
        self._pending_changes = True
        
        # Si persistencia activada, guardar asíncronamente
        if self.__class__._use_database:
            asyncio.create_task(self._save_to_db())
    
    async def add_download_task(self, download_func: Callable[..., Awaitable[Any]], 
                             *args: Any, **kwargs: Any) -> None:
        """
        Añade una tarea a la cola de descargas del usuario.
        
        Args:
            download_func: Función asíncrona que realiza la descarga
            *args, **kwargs: Argumentos para la función de descarga
        """
        # Verificar límite mensual para usuarios normales
        if self.role == "normal":
            # Verificar si cambió el mes y reiniciar contador si es necesario
            self._check_monthly_limit_reset()
            
            # Verificar si alcanzó límite mensual
            if self.monthly_downloads >= MONTHLY_DOWNLOAD_LIMIT:
                # Rechazar la descarga y lanzar error
                raise Exception(f"Has alcanzado el límite de {MONTHLY_DOWNLOAD_LIMIT} descargas mensuales. Actualiza a premium para descargas ilimitadas.")
        
        # Incrementar contador de descargas activas
        self.active_downloads += 1
        
        # Añadir tarea a la cola
        await self.download_queue.add_download(
            self._wrap_download_task, download_func, *args, **kwargs
        )
    
    async def _wrap_download_task(self, download_func: Callable[..., Awaitable[Any]],
                              *args: Any, **kwargs: Any) -> None:
        """
        Wrapper para las tareas de descarga que actualiza contadores.
        
        Args:
            download_func: Función asíncrona original
            *args, **kwargs: Argumentos para la función original
        """
        try:
            # Ejecutar la función de descarga
            await download_func(*args, **kwargs)
            
            # Actualizar contadores al finalizar
            self.total_downloads += 1
            
            # Incrementar contador mensual si es usuario normal
            if self.role == "normal":
                self.monthly_downloads += 1
                
            self.active_downloads = max(0, self.active_downloads - 1)
            self._pending_changes = True
            
            # Si persistencia activada, guardar resultados
            if self.__class__._use_database:
                asyncio.create_task(self._save_to_db())
                
        except Exception as e:
            # En caso de error, también decrementar contador de descargas activas
            self.active_downloads = max(0, self.active_downloads - 1)
            raise
    
    async def wait_for_rate_limit(self) -> None:
        """
        Espera hasta que el usuario pueda realizar una nueva solicitud.
        
        Este método bloquea hasta que se cumpla el límite de tasa.
        """
        await self.rate_limiter.wait_for_slot()
    
    def get_role(self) -> str:
        """
        Obtiene el rol actual del usuario.
        
        Returns:
            Rol del usuario (normal, premium, admin)
        """
        return self.role
    
    async def set_role(self, new_role: str) -> bool:
        """
        Actualiza el rol del usuario y sus límites asociados.
        
        Args:
            new_role: Nuevo rol a establecer
            
        Returns:
            True si se actualizó correctamente, False en caso contrario
        """
        if new_role not in ["normal", "premium", "admin"]:
            logging.error(f"Rol inválido: {new_role}")
            return False
        
        # Actualizar rol en memoria
        self.role = new_role
        self._pending_changes = True
        
        # Actualizar límites según el nuevo rol
        limit = ROLE_DOWNLOAD_LIMITS.get(new_role, ROLE_DOWNLOAD_LIMITS["normal"])
        self.download_queue.update_concurrency_limit(limit)
        
        # Guardar en BD si está habilitado
        if self.__class__._use_database:
            success = await self._save_to_db()
            
            # Intentar actualizar directamente el rol en la BD
            try:
                result = await asyncio.to_thread(
                    db_manager.set_user_role,
                    self.user_id,
                    new_role
                )
                return result
            except Exception as e:
                logging.error(f"Error actualizando rol en BD: {e}", exc_info=True)
                return success
                
        return True
    
    async def _save_to_db(self) -> bool:
        """
        Guarda la sesión en la base de datos sin bloquear.
        Solo si la persistencia está habilitada.
        
        Returns:
            True si se guardó correctamente, False en caso contrario
        """
        if not self.__class__._use_database:
            return False
            
        try:
            # Preparar datos para guardar
            session_data = {
                "settings": self.settings,
                "last_activity": self.last_activity,
                "context_data": self.context_data,
                "total_downloads": self.total_downloads,
                "active_downloads": self.active_downloads,
                "role": self.role,
                "created_at": self.created_at,
                "updated_at": self.updated_at,
                "monthly_downloads": self.monthly_downloads,
                "current_month": self.current_month
            }
            
            # Ejecutar en otro thread para no bloquear
            result = await asyncio.to_thread(
                db_manager.save_user_session, 
                self.user_id, 
                session_data
            )
            
            # Resetear indicador de cambios pendientes
            if result:
                self._pending_changes = False
                
            return result
            
        except Exception as e:
            logging.error(f"Error guardando sesión {self.user_id} en BD: {e}", 
                         exc_info=True)
            return False
    
    def increment_downloads(self) -> None:
        """
        Incrementa el contador de descargas y guarda en BD.
        """
        # Verificar límite mensual para usuarios normales
        if self.role == "normal":
            # Verificar si cambió el mes y reiniciar contador si es necesario
            self._check_monthly_limit_reset()
            
            # Verificar si alcanzó límite mensual
            if self.monthly_downloads >= MONTHLY_DOWNLOAD_LIMIT:
                # Rechazar la descarga
                raise Exception(f"Has alcanzado el límite de {MONTHLY_DOWNLOAD_LIMIT} descargas mensuales. Actualiza a premium para descargas ilimitadas.")
                
            # Incrementar contador mensual
            self.monthly_downloads += 1
        
        self.total_downloads += 1
        self.updated_at = time.time()
        self._pending_changes = True
        
        # Guardar en BD si está habilitado
        if self.__class__._use_database:
            asyncio.create_task(self._save_to_db())
    
    def mark_as_changed(self) -> None:
        """
        Marca la sesión como modificada, requiriendo guardado en BD.
        """
        self._pending_changes = True
        self.updated_at = time.time()
        
        if self.__class__._use_database:
            asyncio.create_task(self._save_to_db())
    
    def update_minor_stat(self, increment: int = 1) -> None:
        """
        Actualiza estadística menor sin guardar inmediatamente en BD.
        """
        self.stat_counter = getattr(self, 'stat_counter', 0) + increment
        self.updated_at = time.time()
        self._pending_changes = True
        
        # Solo guardar en BD cada cierto número de cambios
        if self.stat_counter % 10 == 0 and self.__class__._use_database:
            asyncio.create_task(self._save_to_db())
    
    def has_permission(self, required_role: str) -> bool:
        """
        Verifica si el usuario tiene un rol con permisos suficientes.
        
        Args:
            required_role: Rol requerido para una operación
            
        Returns:
            True si el usuario tiene permisos suficientes, False en caso contrario
        """
        if required_role not in ROLES_HIERARCHY:
            return False
            
        # Obtener índices en la jerarquía
        required_idx = ROLES_HIERARCHY.index(required_role)
        user_idx = ROLES_HIERARCHY.index(self.role)
        
        # Usuario tiene permisos si su rol es igual o superior al requerido
        return user_idx >= required_idx

    def get_monthly_downloads_left(self) -> Dict[str, int]:
        """
        Retorna información sobre las descargas mensuales restantes para usuarios normales.
        
        Returns:
            Diccionario con información de descargas usadas y restantes
        """
        # Solo aplicable a usuarios normales
        if self.role != "normal":
            return {"limit": "∞", "used": self.monthly_downloads, "remaining": "∞"}
            
        # Verificar si cambió el mes y reiniciar contador si es necesario
        self._check_monthly_limit_reset()
        
        # Calcular descargas restantes
        remaining = max(0, MONTHLY_DOWNLOAD_LIMIT - self.monthly_downloads)
        
        return {
            "limit": MONTHLY_DOWNLOAD_LIMIT,
            "used": self.monthly_downloads,
            "remaining": remaining
        }

async def cleanup_sessions() -> None:
    """
    Función periódica que limpia las sesiones inactivas y las sincroniza con la BD.
    
    Se ejecuta en segundo plano para eliminar las sesiones que han expirado
    por inactividad, liberando recursos del sistema.
    """
    while True:
        try:
            # Esperar el intervalo configurado
            await asyncio.sleep(SESSION_CLEANUP_INTERVAL)
            
            # Contar sesiones antes de limpiar
            active_before = len(UserSession._sessions)
            
            # Identificar sesiones expiradas
            expired_ids = []
            for user_id, session in list(UserSession._sessions.items()):
                if session.is_expired():
                    expired_ids.append(user_id)
            
            # Eliminar sesiones expiradas de memoria
            for user_id in expired_ids:
                # Si persistencia activada y hay cambios pendientes, guardar última vez
                if UserSession._use_database and UserSession._sessions[user_id]._pending_changes:
                    session = UserSession._sessions[user_id]
                    await session._save_to_db()
                
                del UserSession._sessions[user_id]
            
            # Eliminar sesiones expiradas de la BD
            deleted_db = 0
            if UserSession._use_database:
                deleted_db = await asyncio.to_thread(
                    db_manager.delete_expired_sessions, 
                    SESSION_TIMEOUT
                )
            
            # Log de información
            if expired_ids or deleted_db > 0:
                logging.info(
                    f"Limpieza de sesiones: {len(expired_ids)} eliminadas de memoria"
                    f"{f', {deleted_db} de la BD' if UserSession._use_database else ''}. "
                    f"Quedan {len(UserSession._sessions)} sesiones activas."
                )
                
        except Exception as e:
            logging.error(f"Error en la limpieza de sesiones: {str(e)}", exc_info=True)

def requires_role(minimum_role: str):
    """
    Decorador para restringir comandos según el rol del usuario.
    
    Verifica que el usuario tenga al menos el rol especificado
    antes de permitir la ejecución del comando.
    
    Args:
        minimum_role: Rol mínimo requerido ("normal", "premium" o "admin")
    """
    def decorator(func):
        async def wrapper(update, context, *args, **kwargs):
            user_id = update.effective_user.id
            session = UserSession.get_session(user_id)
            
            # Verificar permisos
            if not session.has_permission(minimum_role):
                # Silencio - no enviar mensaje de error
                return
                
            # Si tiene permisos, ejecutar la función original
            return await func(update, context, *args, **kwargs)
        return wrapper
    return decorator
