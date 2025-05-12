"""
Gestor de colas de tareas para Melodify Deluxe.

Este módulo proporciona una implementación centralizada para manejar
colas de tareas asíncronas, priorizando diferentes tipos de operaciones
y controlando la concurrencia para evitar sobrecargas del sistema.
"""

import asyncio
import logging
import time
from typing import Dict, Any, Optional, Callable, Awaitable, List, Union, Tuple, TypeVar, cast

from config import (
    MAX_CONCURRENT_DOWNLOADS_GLOBAL,
    MAX_CONCURRENT_DOWNLOADS_PER_USER
)

T = TypeVar('T')

class TaskQueue:
    """
    Gestiona una cola de tareas asíncronas con control de concurrencia.
    
    Esta clase permite encolar tareas para su ejecución asíncrona, manteniendo
    un límite de concurrencia y proporcionando estadísticas sobre el procesamiento.
    """
    
    def __init__(self, 
                name: str, 
                max_concurrent: int, 
                priority: int = 0) -> None:
        """
        Inicializa una nueva cola de tareas.
        
        Args:
            name: Nombre identificativo de la cola
            max_concurrent: Número máximo de tareas que pueden ejecutarse simultáneamente
            priority: Prioridad de la cola (mayor número = mayor prioridad)
        """
        self.name = name
        self.semaphore = asyncio.Semaphore(max_concurrent)
        self.queue: asyncio.Queue = asyncio.Queue()
        self.priority = priority
        self.active = False
        self._worker_task: Optional[asyncio.Task] = None
        self.tasks_processed = 0
        self.tasks_failed = 0
        self.processing_time = 0.0

    async def enqueue(self, 
                    task_func: Callable[..., Awaitable[T]], 
                    *args: Any, 
                    **kwargs: Any) -> Optional[asyncio.Task]:
        """
        Añade una tarea a la cola para su ejecución.
        
        Args:
            task_func: Función asíncrona a ejecutar
            *args, **kwargs: Argumentos para la función
            
        Returns:
            Task creada o None si no se pudo encolar
        """
        try:
            # Encolar la tarea con sus argumentos
            await self.queue.put((task_func, args, kwargs))
            
            # Iniciar el worker si no está activo
            if not self.active:
                self.active = True
                self._worker_task = asyncio.create_task(self._process_queue())
                logging.info(f"[QUEUE] Cola {self.name} iniciada")
            
            return self._worker_task
        except Exception as e:
            logging.error(f"[QUEUE] Error al encolar tarea en {self.name}: {str(e)}", exc_info=True)
            return None

    async def _process_queue(self) -> None:
        """
        Procesa las tareas encoladas de manera secuencial.
        
        Este método se ejecuta como tarea en segundo plano y gestiona
        la ejecución de las tareas respetando el límite de concurrencia.
        """
        while self.active:
            try:
                # Si la cola está vacía, esperar un poco y verificar de nuevo
                if self.queue.empty():
                    await asyncio.sleep(1)
                    if self.queue.empty():
                        logging.info(f"[QUEUE] Cola {self.name} inactiva, deteniendo worker")
                        self.active = False
                        break
                    continue
                
                # Obtener la siguiente tarea
                task_func, args, kwargs = await self.queue.get()
                
                # Ejecutar la tarea respetando el semáforo
                start_time = time.time()
                try:
                    async with self.semaphore:
                        logging.info(f"[QUEUE] Ejecutando tarea de cola {self.name}")
                        await task_func(*args, **kwargs)
                        self.tasks_processed += 1
                except Exception as e:
                    self.tasks_failed += 1
                    logging.error(f"[QUEUE] Error en tarea de cola {self.name}: {str(e)}", exc_info=True)
                finally:
                    # Calcular tiempo de procesamiento
                    elapsed = time.time() - start_time
                    self.processing_time += elapsed
                    self.queue.task_done()
                    logging.info(f"[QUEUE] Tarea completada en cola {self.name} en {elapsed:.2f}s")
                
            except Exception as e:
                logging.error(f"[QUEUE] Error en worker de cola {self.name}: {str(e)}", exc_info=True)
                # Evitar bucle infinito en caso de error
                await asyncio.sleep(1)

    async def stop(self) -> None:
        """
        Detiene el procesamiento de la cola.
        
        Marca la cola como inactiva y cancela la tarea del worker si existe.
        """
        self.active = False
        if self._worker_task:
            try:
                self._worker_task.cancel()
                await asyncio.gather(self._worker_task, return_exceptions=True)
                logging.info(f"[QUEUE] Cola {self.name} detenida")
            except Exception as e:
                logging.error(f"[QUEUE] Error al detener cola {self.name}: {str(e)}", exc_info=True)

    def get_stats(self) -> Dict[str, Any]:
        """
        Obtiene estadísticas de la cola.
        
        Returns:
            Diccionario con estadísticas de procesamiento
        """
        avg_time = 0.0
        if self.tasks_processed > 0:
            avg_time = self.processing_time / self.tasks_processed
            
        return {
            "name": self.name,
            "active": self.active,
            "pending_tasks": self.queue.qsize(),
            "tasks_processed": self.tasks_processed,
            "tasks_failed": self.tasks_failed,
            "avg_processing_time": round(avg_time, 2),
            "total_processing_time": round(self.processing_time, 2)
        }

class QueueManager:
    """
    Gestiona múltiples colas de tareas del sistema.
    
    Esta clase proporciona una interfaz centralizada para gestionar diferentes
    colas de tareas, asignar recursos del sistema y monitorear su uso.
    """
    
    # Instancia singleton
    _instance: Optional["QueueManager"] = None
    
    @classmethod
    def get_instance(cls) -> "QueueManager":
        """
        Obtiene la instancia singleton del gestor de colas.
        
        Returns:
            Instancia del gestor de colas
        """
        if cls._instance is None:
            cls._instance = QueueManager()
        return cls._instance
    
    def __init__(self) -> None:
        """Inicializa el gestor de colas."""
        if QueueManager._instance is not None:
            return
            
        # Colas globales (compartidas por todos los usuarios)
        self.global_queues: Dict[str, TaskQueue] = {
            "downloads": TaskQueue(
                name="downloads",
                max_concurrent=MAX_CONCURRENT_DOWNLOADS_GLOBAL,
                priority=10
            ),
            "api_requests": TaskQueue(
                name="api_requests", 
                max_concurrent=5, 
                priority=20
            ),
            "notifications": TaskQueue(
                name="notifications", 
                max_concurrent=3, 
                priority=5
            )
        }
        
        # Colas específicas por usuario
        self.user_queues: Dict[int, Dict[str, TaskQueue]] = {}
        
        logging.info("[QUEUE_MANAGER] Inicializado con éxito")
    
    def get_user_queue(self, user_id: int, queue_type: str = "downloads") -> TaskQueue:
        """
        Obtiene una cola específica para un usuario, creándola si no existe.
        
        Args:
            user_id: ID del usuario
            queue_type: Tipo de cola ('downloads', 'api_requests', etc.)
            
        Returns:
            Instancia de TaskQueue para ese usuario y tipo
        """
        # Crear diccionario para el usuario si no existe
        if user_id not in self.user_queues:
            self.user_queues[user_id] = {}
        
        # Crear cola si no existe para este usuario
        if queue_type not in self.user_queues[user_id]:
            self.user_queues[user_id][queue_type] = TaskQueue(
                name=f"{queue_type}_{user_id}",
                max_concurrent=MAX_CONCURRENT_DOWNLOADS_PER_USER if queue_type == "downloads" else 2,
                priority=5
            )
        
        return self.user_queues[user_id][queue_type]
    
    def get_global_queue(self, queue_type: str = "downloads") -> TaskQueue:
        """
        Obtiene una cola global del sistema.
        
        Args:
            queue_type: Tipo de cola ('downloads', 'api_requests', etc.)
            
        Returns:
            Instancia de TaskQueue global
            
        Raises:
            KeyError: Si el tipo de cola no existe
        """
        if queue_type not in self.global_queues:
            raise KeyError(f"No existe una cola global de tipo '{queue_type}'")
        
        return self.global_queues[queue_type]
    
    async def enqueue_user_task(self, 
                             user_id: int, 
                             task_func: Callable[..., Awaitable[T]], 
                             queue_type: str = "downloads",
                             *args: Any, 
                             **kwargs: Any) -> Optional[asyncio.Task]:
        """
        Encola una tarea en la cola específica de un usuario.
        
        Args:
            user_id: ID del usuario
            task_func: Función asíncrona a ejecutar
            queue_type: Tipo de cola ('downloads', 'api_requests', etc.)
            *args, **kwargs: Argumentos para la función
            
        Returns:
            Task creada o None si no se pudo encolar
        """
        queue = self.get_user_queue(user_id, queue_type)
        return await queue.enqueue(task_func, *args, **kwargs)
    
    async def enqueue_global_task(self, 
                               task_func: Callable[..., Awaitable[T]], 
                               queue_type: str = "downloads",
                               *args: Any, 
                               **kwargs: Any) -> Optional[asyncio.Task]:
        """
        Encola una tarea en una cola global del sistema.
        
        Args:
            task_func: Función asíncrona a ejecutar
            queue_type: Tipo de cola ('downloads', 'api_requests', etc.)
            *args, **kwargs: Argumentos para la función
            
        Returns:
            Task creada o None si no se pudo encolar
        """
        queue = self.get_global_queue(queue_type)
        return await queue.enqueue(task_func, *args, **kwargs)
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Obtiene estadísticas de todas las colas.
        
        Returns:
            Diccionario con estadísticas de todas las colas
        """
        stats = {
            "global_queues": {name: queue.get_stats() for name, queue in self.global_queues.items()},
            "user_queues": {user_id: {name: queue.get_stats() for name, queue in queues.items()} 
                          for user_id, queues in self.user_queues.items()},
            "active_users": len(self.user_queues)
        }
        
        # Calcular totales
        total_pending = 0
        total_processed = 0
        total_failed = 0
        
        # Sumar estadísticas de colas globales
        for queue in self.global_queues.values():
            stats_data = queue.get_stats()
            total_pending += stats_data["pending_tasks"]
            total_processed += stats_data["tasks_processed"]
            total_failed += stats_data["tasks_failed"]
        
        # Sumar estadísticas de colas de usuarios
        for user_queues in self.user_queues.values():
            for queue in user_queues.values():
                stats_data = queue.get_stats()
                total_pending += stats_data["pending_tasks"]
                total_processed += stats_data["tasks_processed"]
                total_failed += stats_data["tasks_failed"]
        
        # Añadir totales
        stats["total_pending"] = total_pending
        stats["total_processed"] = total_processed
        stats["total_failed"] = total_failed
        
        return stats
        
    async def stop_all_queues(self) -> None:
        """
        Detiene todas las colas de tareas.
        
        Útil para apagado limpio del sistema.
        """
        # Detener colas globales
        for queue in self.global_queues.values():
            await queue.stop()
        
        # Detener colas de usuarios
        for user_queues in self.user_queues.values():
            for queue in user_queues.values():
                await queue.stop()
                
        logging.info("[QUEUE_MANAGER] Todas las colas detenidas") 