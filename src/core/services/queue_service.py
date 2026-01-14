# -*- coding: utf-8 -*-
"""
Task queue manager for Melodify Deluxe.

This module provides a centralized implementation for handling
async task queues, prioritizing different types of operations
and controlling concurrency to avoid system overloads.
"""

import asyncio
import logging
import time
from typing import Dict, Any, Optional, Callable, Awaitable, TypeVar

from src.config import (
    MAX_CONCURRENT_DOWNLOADS_GLOBAL,
    MAX_CONCURRENT_DOWNLOADS_PER_USER
)

T = TypeVar('T')


class TaskQueue:
    """
    Manages an async task queue with concurrency control.
    
    This class allows queuing tasks for async execution, maintaining
    a concurrency limit and providing processing statistics.
    """
    
    def __init__(
        self, 
        name: str, 
        max_concurrent: int, 
        priority: int = 0
    ) -> None:
        """
        Initializes a new task queue.
        
        Args:
            name: Queue identifier name
            max_concurrent: Maximum tasks that can run simultaneously
            priority: Queue priority (higher number = higher priority)
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

    async def enqueue(
        self, 
        task_func: Callable[..., Awaitable[T]], 
        *args: Any, 
        **kwargs: Any
    ) -> Optional[asyncio.Task]:
        """
        Adds a task to the queue for execution.
        
        Args:
            task_func: Async function to execute
            *args, **kwargs: Arguments for the function
            
        Returns:
            Created Task or None if couldn't queue
        """
        try:
            # Queue the task with its arguments
            await self.queue.put((task_func, args, kwargs))
            
            # Start worker if not active
            if not self.active:
                self.active = True
                self._worker_task = asyncio.create_task(self._process_queue())
                logging.info(f"[QUEUE] Queue {self.name} started")
            
            return self._worker_task
        except Exception as e:
            logging.error(f"[QUEUE] Error queuing task in {self.name}: {str(e)}", exc_info=True)
            return None

    async def _process_queue(self) -> None:
        """
        Processes queued tasks sequentially.
        
        This method runs as a background task and manages
        task execution respecting the concurrency limit.
        """
        while self.active:
            try:
                # If queue is empty, wait a bit and check again
                if self.queue.empty():
                    await asyncio.sleep(1)
                    if self.queue.empty():
                        logging.info(f"[QUEUE] Queue {self.name} inactive, stopping worker")
                        self.active = False
                        break
                    continue
                
                # Get next task
                task_func, args, kwargs = await self.queue.get()
                
                # Execute task respecting semaphore
                start_time = time.time()
                try:
                    async with self.semaphore:
                        logging.info(f"[QUEUE] Executing task from queue {self.name}")
                        await task_func(*args, **kwargs)
                        self.tasks_processed += 1
                except Exception as e:
                    self.tasks_failed += 1
                    logging.error(f"[QUEUE] Error in queue {self.name} task: {str(e)}", exc_info=True)
                finally:
                    # Calculate processing time
                    elapsed = time.time() - start_time
                    self.processing_time += elapsed
                    self.queue.task_done()
                    logging.info(f"[QUEUE] Task completed in queue {self.name} in {elapsed:.2f}s")
                
            except Exception as e:
                logging.error(f"[QUEUE] Error in queue {self.name} worker: {str(e)}", exc_info=True)
                # Avoid infinite loop on error
                await asyncio.sleep(1)

    async def stop(self) -> None:
        """
        Stops queue processing.
        
        Marks queue as inactive and cancels worker task if exists.
        """
        self.active = False
        if self._worker_task:
            try:
                self._worker_task.cancel()
                await asyncio.gather(self._worker_task, return_exceptions=True)
                logging.info(f"[QUEUE] Queue {self.name} stopped")
            except Exception as e:
                logging.error(f"[QUEUE] Error stopping queue {self.name}: {str(e)}", exc_info=True)

    def get_stats(self) -> Dict[str, Any]:
        """
        Gets queue statistics.
        
        Returns:
            Dictionary with processing statistics
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
    Manages multiple system task queues.
    
    This class provides a centralized interface for managing different
    task queues, allocating system resources and monitoring usage.
    """
    
    # Singleton instance
    _instance: Optional["QueueManager"] = None
    
    @classmethod
    def get_instance(cls) -> "QueueManager":
        """
        Gets the singleton queue manager instance.
        
        Returns:
            Queue manager instance
        """
        if cls._instance is None:
            cls._instance = QueueManager()
        return cls._instance
    
    def __init__(self) -> None:
        """Initializes the queue manager."""
        if QueueManager._instance is not None:
            return
            
        # Global queues (shared by all users)
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
        
        # User-specific queues
        self.user_queues: Dict[int, Dict[str, TaskQueue]] = {}
        
        logging.info("[QUEUE_MANAGER] Initialized successfully")
    
    def get_user_queue(self, user_id: int, queue_type: str = "downloads") -> TaskQueue:
        """
        Gets a user-specific queue, creating it if it doesn't exist.
        
        Args:
            user_id: User ID
            queue_type: Queue type ('downloads', 'api_requests', etc.)
            
        Returns:
            TaskQueue instance for that user and type
        """
        # Create user dictionary if doesn't exist
        if user_id not in self.user_queues:
            self.user_queues[user_id] = {}
        
        # Create queue if doesn't exist for this user
        if queue_type not in self.user_queues[user_id]:
            self.user_queues[user_id][queue_type] = TaskQueue(
                name=f"{queue_type}_{user_id}",
                max_concurrent=MAX_CONCURRENT_DOWNLOADS_PER_USER if queue_type == "downloads" else 2,
                priority=5
            )
        
        return self.user_queues[user_id][queue_type]
    
    def get_global_queue(self, queue_type: str = "downloads") -> TaskQueue:
        """
        Gets a global system queue.
        
        Args:
            queue_type: Queue type ('downloads', 'api_requests', etc.)
            
        Returns:
            Global TaskQueue instance
            
        Raises:
            KeyError: If queue type doesn't exist
        """
        if queue_type not in self.global_queues:
            raise KeyError(f"No global queue of type '{queue_type}' exists")
        
        return self.global_queues[queue_type]
    
    async def enqueue_user_task(
        self, 
        user_id: int, 
        task_func: Callable[..., Awaitable[T]], 
        queue_type: str = "downloads",
        *args: Any, 
        **kwargs: Any
    ) -> Optional[asyncio.Task]:
        """
        Queues a task in a user's specific queue.
        
        Args:
            user_id: User ID
            task_func: Async function to execute
            queue_type: Queue type ('downloads', 'api_requests', etc.)
            *args, **kwargs: Arguments for the function
            
        Returns:
            Created Task or None if couldn't queue
        """
        queue = self.get_user_queue(user_id, queue_type)
        return await queue.enqueue(task_func, *args, **kwargs)
    
    async def enqueue_global_task(
        self, 
        task_func: Callable[..., Awaitable[T]], 
        queue_type: str = "downloads",
        *args: Any, 
        **kwargs: Any
    ) -> Optional[asyncio.Task]:
        """
        Queues a task in a global system queue.
        
        Args:
            task_func: Async function to execute
            queue_type: Queue type ('downloads', 'api_requests', etc.)
            *args, **kwargs: Arguments for the function
            
        Returns:
            Created Task or None if couldn't queue
        """
        queue = self.get_global_queue(queue_type)
        return await queue.enqueue(task_func, *args, **kwargs)
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Gets statistics for all queues.
        
        Returns:
            Dictionary with all queue statistics
        """
        stats = {
            "global_queues": {name: queue.get_stats() for name, queue in self.global_queues.items()},
            "user_queues": {user_id: {name: queue.get_stats() for name, queue in queues.items()} 
                          for user_id, queues in self.user_queues.items()},
            "active_users": len(self.user_queues)
        }
        
        # Calculate totals
        total_pending = 0
        total_processed = 0
        total_failed = 0
        
        # Sum global queue statistics
        for queue in self.global_queues.values():
            stats_data = queue.get_stats()
            total_pending += stats_data["pending_tasks"]
            total_processed += stats_data["tasks_processed"]
            total_failed += stats_data["tasks_failed"]
        
        # Sum user queue statistics
        for user_queues in self.user_queues.values():
            for queue in user_queues.values():
                stats_data = queue.get_stats()
                total_pending += stats_data["pending_tasks"]
                total_processed += stats_data["tasks_processed"]
                total_failed += stats_data["tasks_failed"]
        
        # Add totals
        stats["total_pending"] = total_pending
        stats["total_processed"] = total_processed
        stats["total_failed"] = total_failed
        
        return stats
        
    async def stop_all_queues(self) -> None:
        """
        Stops all task queues.
        
        Useful for clean system shutdown.
        """
        # Stop global queues
        for queue in self.global_queues.values():
            await queue.stop()
        
        # Stop user queues
        for user_queues in self.user_queues.values():
            for queue in user_queues.values():
                await queue.stop()
                
        logging.info("[QUEUE_MANAGER] All queues stopped")
