# -*- coding: utf-8 -*-
"""
User session management module for Melodify Deezer.

Provides classes to manage user state, control request rates,
queue downloads and manage system resources to avoid overloads.
"""

import asyncio
import time
import logging
from collections import OrderedDict
from typing import Dict, Any, Optional, Callable, Awaitable, List, Union
from datetime import datetime

from deemix.settings import load as load_settings
from src.config import (
    RATE_LIMIT_MAX_REQUESTS,
    RATE_LIMIT_TIME_WINDOW,
    MAX_CONCURRENT_DOWNLOADS_PER_USER,
    MAX_CONCURRENT_DOWNLOADS_GLOBAL,
    SESSION_TIMEOUT,
    SESSION_CLEANUP_INTERVAL,
    SESSION_CACHE_SIZE,
    SESSION_TIERS,
    MONTHLY_DOWNLOAD_LIMIT,
    ROLES_HIERARCHY
)

# Check if database service is available
DB_AVAILABLE = False
try:
    from src.infrastructure.database import db_service
    DB_AVAILABLE = True
except ImportError:
    # Persistence functionality will be disabled
    db_service = None

# Download limits per role
ROLE_DOWNLOAD_LIMITS = {
    "normal": 2,
    "premium": 5,
    "admin": 0  # 0 means no limit
}


class SessionMetrics:
    """Metrics for the session management system."""
    
    def __init__(self):
        # Cache metrics
        self.cache_hits = 0
        self.cache_misses = 0
        # Database metrics
        self.db_reads = 0
        self.db_writes = 0 
        self.db_errors = 0
        # Compression metrics
        self.compression_count = 0
        self.uncompressed_size = 0
        self.compressed_size = 0
        # Periodic reset
        self.last_reset = time.time()
    
    def log_cache_hit(self):
        self.cache_hits += 1
    
    def log_cache_miss(self):
        self.cache_misses += 1
        
    def log_db_read(self):
        self.db_reads += 1
        
    def log_db_write(self):
        self.db_writes += 1
    
    def log_compression(self, before_size: int, after_size: int):
        self.compression_count += 1
        self.uncompressed_size += before_size
        self.compressed_size += after_size
        
    def get_compression_ratio(self) -> float:
        if self.compressed_size == 0 or self.uncompressed_size == 0:
            return 1.0
        return self.uncompressed_size / self.compressed_size
        
    def get_cache_hit_ratio(self) -> float:
        total = self.cache_hits + self.cache_misses
        if total == 0:
            return 0
        return self.cache_hits / total


class LRUCache(OrderedDict):
    """Cache with LRU (Least Recently Used) eviction policy."""
    
    def __init__(self, maxsize: int = SESSION_CACHE_SIZE):
        super().__init__()
        self.maxsize = maxsize
        
    def get(self, key):
        """Gets a value and updates its position in the cache."""
        if key not in self:
            return None
        self.move_to_end(key)
        return self[key]
        
    def put(self, key, value):
        """Inserts/updates a value and maintains size limit."""
        if key in self:
            self.move_to_end(key)
        self[key] = value
        if len(self) > self.maxsize:
            oldest = next(iter(self))
            del self[oldest]
            
    def keys_ordered(self):
        """Returns keys ordered by usage (most recent at end)."""
        return list(self.keys())


class RateLimiter:
    """
    Controls request rate per user to avoid overloads.
    
    Implements a sliding window mechanism to limit the number
    of requests a user can make in a time period.
    """
    
    def __init__(
        self, 
        max_requests: int = RATE_LIMIT_MAX_REQUESTS, 
        time_window: int = RATE_LIMIT_TIME_WINDOW
    ) -> None:
        """
        Initializes the rate limiter.
        
        Args:
            max_requests: Maximum allowed requests in the time window
            time_window: Time window duration in seconds
        """
        self.max_requests: int = max_requests
        self.time_window: int = time_window
        self.request_timestamps: List[float] = []
    
    async def acquire(self) -> bool:
        """
        Attempts to acquire a permit to make a request.
        
        Checks if the user has exceeded their request quota in
        the current time window.
        
        Returns:
            True if request is allowed, False if should be limited
        """
        current_time = time.time()
        
        # Clean old timestamps outside the time window
        self.request_timestamps = [
            ts for ts in self.request_timestamps 
            if current_time - ts < self.time_window
        ]
        
        # Check if limit is exceeded
        if len(self.request_timestamps) >= self.max_requests:
            return False
        
        # Register new request
        self.request_timestamps.append(current_time)
        return True
    
    async def wait_for_slot(self) -> None:
        """
        Waits until a slot is available to make a request.
        
        Blocks execution until the user can make a new request
        according to configured rate restrictions.
        """
        while True:
            if await self.acquire():
                return
            # Wait before checking again
            await asyncio.sleep(1)


class DownloadQueue:
    """
    Manages a download queue for a user.
    
    Implements an asynchronous worker that processes downloads
    sequentially respecting the configured concurrency limit.
    """
    
    def __init__(self, max_concurrent: int = MAX_CONCURRENT_DOWNLOADS_PER_USER) -> None:
        """
        Initializes the download queue.
        
        Args:
            max_concurrent: Maximum concurrent downloads allowed
        """
        self.semaphore: asyncio.Semaphore = asyncio.Semaphore(max_concurrent)
        self.queue: asyncio.Queue = asyncio.Queue()
        self.active: bool = False
        self._worker_task: Optional[asyncio.Task] = None
    
    async def add_download(
        self, 
        download_func: Callable[..., Awaitable[Any]], 
        *args: Any, 
        **kwargs: Any
    ) -> None:
        """
        Adds a download task to the queue.
        
        Args:
            download_func: Async function that performs the download
            *args, **kwargs: Arguments for the download function
        """
        # Queue the task with its arguments
        await self.queue.put((download_func, args, kwargs))
        
        # Start worker if not active
        if not self.active:
            self.active = True
            self._worker_task = asyncio.create_task(self._download_worker())
    
    async def _download_worker(self) -> None:
        """
        Processes downloads in the queue sequentially.
        
        This method runs as a background task and processes
        download requests respecting the concurrency limit.
        """
        while self.active:
            try:
                # Wait for a task if queue is empty
                if self.queue.empty():
                    # Wait a bit and check for new tasks
                    await asyncio.sleep(1)
                    if self.queue.empty():
                        self.active = False
                        break
                    continue
                
                # Get the next download task
                download_func, args, kwargs = await self.queue.get()
                
                # Acquire a semaphore slot to control concurrency
                async with self.semaphore:
                    # Execute download with provided parameters
                    await download_func(*args, **kwargs)
                
                # Mark task as done
                self.queue.task_done()
            except Exception as e:
                logging.error(f"Error in download worker: {str(e)}", exc_info=True)
                # Brief pause to avoid continuous loop on errors
                await asyncio.sleep(1)
    
    def is_active(self) -> bool:
        """
        Checks if there are active downloads in the queue.
        
        Returns:
            True if downloads are in progress, False otherwise
        """
        return self.active
    
    async def stop(self) -> None:
        """
        Stops download queue processing.
        
        Cancels the worker task and marks the queue as inactive.
        """
        self.active = False
        if self._worker_task:
            try:
                # Cancel task and wait for it to finish
                self._worker_task.cancel()
                await asyncio.gather(self._worker_task, return_exceptions=True)
            except Exception:
                # Ignore errors when cancelling task
                pass
    
    def update_concurrency_limit(self, new_limit: int) -> None:
        """
        Updates the concurrency limit for this user.
        
        Args:
            new_limit: New concurrent downloads limit
        """
        # If 0 (admin), use a high value to simulate "no limit"
        if new_limit == 0:
            new_limit = 100
            
        self.semaphore = asyncio.Semaphore(new_limit)
        logging.debug(f"Concurrency limit updated to {new_limit}")


class UserSession:
    """
    Maintains a user's state and preferences in the system.
    
    Manages custom configuration, statistics, download queues
    and rate control for each bot user.
    """
    
    # Replace static dictionary with LRU cache
    _sessions = LRUCache(maxsize=SESSION_CACHE_SIZE)
    # Global semaphore to limit concurrent downloads system-wide
    _global_semaphore = asyncio.Semaphore(MAX_CONCURRENT_DOWNLOADS_GLOBAL)
    # Database persistence control
    _use_database: bool = False
    # Session management system metrics
    _metrics = SessionMetrics()
    
    @classmethod
    def enable_persistence(cls, enable: bool = True) -> None:
        """
        Enables or disables database persistence.
        
        Args:
            enable: True to enable, False to disable
        """
        if enable and not DB_AVAILABLE:
            logging.warning("Cannot enable persistence: db_service module not available")
            return
            
        cls._use_database = enable and DB_AVAILABLE
        logging.info(f"Database persistence: {'enabled' if cls._use_database else 'disabled'}")
    
    @classmethod
    def get_session(cls, user_id: int) -> "UserSession":
        """
        Gets a user's session, creating it if it doesn't exist.
        Implements lazy loading from DB when necessary.
        
        Args:
            user_id: Telegram user ID
            
        Returns:
            UserSession instance for the specific user
        """
        # Search cache first
        session = cls._sessions.get(user_id)
        if session:
            # Register cache hit and return session
            cls._metrics.log_cache_hit()
            return session

        # If not in cache, register miss
        cls._metrics.log_cache_miss()
        
        # If persistence enabled, try loading from DB
        if cls._use_database and db_service:
            try:
                # Register DB read
                cls._metrics.log_db_read()
                
                # Load from DB
                session_data = db_service.load_user_session(user_id)
                
                if session_data:
                    # Create session with DB data using creation method
                    session = cls._create_session_from_data(user_id, session_data)
                    cls._sessions.put(user_id, session)
                    return session
            except Exception as e:
                cls._metrics.db_errors += 1
                logging.error(f"Error loading session {user_id} from DB: {e}", 
                             exc_info=True)
        
        # If not in DB or load failed, create new
        session = UserSession(user_id)
        cls._sessions.put(user_id, session)
        return session
    
    @classmethod
    def get_active_sessions_count(cls) -> int:
        """
        Gets the number of active sessions in memory.
        
        Returns:
            Total number of user sessions in cache
        """
        return len(cls._sessions)
    
    @classmethod
    async def get_global_semaphore(cls) -> asyncio.Semaphore:
        """
        Gets the global semaphore for limiting concurrent downloads.
        
        Returns:
            Global semaphore shared between all sessions
        """
        return cls._global_semaphore
    
    @classmethod
    def load_all_sessions_from_db(cls) -> None:
        """
        Loads all sessions from the database.
        Only if persistence is enabled.
        """
        if not cls._use_database or not db_service:
            logging.info("Persistence disabled: not loading sessions from DB")
            return
            
        try:
            sessions_data = db_service.load_all_sessions()
            loaded = 0
            
            for user_id, data in sessions_data.items():
                if user_id not in cls._sessions:
                    # Create session with DB data
                    session = cls(user_id)
                    session.settings = data["settings"]
                    session.last_activity = data["last_activity"]
                    session.context_data = data["context_data"]
                    session.total_downloads = data["total_downloads"]
                    session.active_downloads = data["active_downloads"]
                    session.role = data.get("role", "normal")
                    session.created_at = data["created_at"]
                    session.updated_at = data["updated_at"]
                    
                    # Update limits based on role
                    limit = ROLE_DOWNLOAD_LIMITS.get(session.role, ROLE_DOWNLOAD_LIMITS["normal"])
                    session.download_queue.update_concurrency_limit(limit)
                    
                    cls._sessions.put(user_id, session)
                    loaded += 1
            
            logging.info(f"Loaded {loaded} sessions from database")
        except Exception as e:
            logging.error(f"Error loading sessions from DB: {e}", exc_info=True)
    
    @classmethod
    def _create_session_from_data(cls, user_id: int, data: Dict[str, Any]) -> "UserSession":
        """
        Creates a UserSession instance from DB data.
        
        Args:
            user_id: User ID
            data: Session data loaded from DB
            
        Returns:
            New UserSession instance
        """
        session = cls(user_id)
        session.settings = data.get("settings", session.settings)
        session.last_activity = data.get("last_activity", session.last_activity)
        session.context_data = data.get("context_data", {})
        session.total_downloads = data.get("total_downloads", 0)
        session.active_downloads = data.get("active_downloads", 0)
        session.role = data.get("role", "normal")
        
        # Monthly tracking fields
        session.monthly_downloads = data.get("monthly_downloads", 0)
        session.current_month = data.get("current_month", session._get_current_month())
        
        # Tracking fields
        session.created_at = data.get("created_at", time.time())
        session.updated_at = data.get("updated_at", time.time())
        
        # Update limits based on role
        limit = ROLE_DOWNLOAD_LIMITS.get(session.role, ROLE_DOWNLOAD_LIMITS["normal"])
        session.download_queue.update_concurrency_limit(limit)
        
        return session
    
    def __init__(self, user_id: int) -> None:
        """
        Initializes a new user session.
        
        Args:
            user_id: Telegram user ID
        """
        self.user_id: int = user_id
        # Load initial configuration from global settings
        self.settings: Dict[str, Any] = load_settings().copy()
        # Last activity timestamp for expiration
        self.last_activity: float = time.time()
        # Queue for managing downloads
        self.download_queue: DownloadQueue = DownloadQueue()
        # Rate limiter for this user
        self.rate_limiter: RateLimiter = RateLimiter()
        # Storage for contextual session data
        self.context_data: Dict[str, Any] = {}
        # Counters for statistics
        self.active_downloads: int = 0
        self.total_downloads: int = 0
        # Monthly limit control (for normal users)
        self.monthly_downloads: int = 0
        self.current_month: int = self._get_current_month()
        # User role (default: normal)
        self.role: str = "normal"
        # Additional tracking fields
        self.created_at: float = time.time()
        self.updated_at: float = time.time()
        # Pending changes indicator
        self._pending_changes: bool = False
        
        # Configure initial limits according to role
        limit = ROLE_DOWNLOAD_LIMITS.get(self.role, ROLE_DOWNLOAD_LIMITS["normal"])
        self.download_queue.update_concurrency_limit(limit)
    
    def _get_current_month(self) -> int:
        """
        Gets the current month as integer.
        
        Returns:
            Month number (1-12)
        """
        return datetime.now().month
        
    def _check_monthly_limit_reset(self) -> None:
        """
        Checks if monthly counter should be reset due to month change.
        """
        current_month = self._get_current_month()
        if current_month != self.current_month:
            # Reset counter if month changed
            self.monthly_downloads = 0
            self.current_month = current_month
            self._pending_changes = True
    
    def update_activity(self) -> None:
        """
        Updates the user's last activity timestamp.
        
        This delays session expiration while user is active.
        If persistence is enabled, saves to DB.
        """
        self.last_activity = time.time()
        self.updated_at = time.time()
        
        # If persistence enabled, save asynchronously
        if self.__class__._use_database:
            asyncio.create_task(self._save_to_db())
    
    def is_expired(self, timeout: Optional[int] = None) -> bool:
        """
        Checks if session has expired due to inactivity.
        Uses different times according to user role.
        
        Args:
            timeout: Time in seconds after which session is considered inactive.
                    If None, uses role-specific time.
            
        Returns:
            True if session has expired, False otherwise
        """
        if timeout is None:
            # Use role-specific time
            timeout = SESSION_TIERS.get(self.role, SESSION_TIMEOUT)
        return time.time() - self.last_activity > timeout
    
    def get_setting(self, key: str, default: Any = None) -> Any:
        """
        Gets a specific user setting.
        
        Args:
            key: Setting name
            default: Default value if setting doesn't exist
            
        Returns:
            Setting value or default value
        """
        return self.settings.get(key, default)
    
    def update_setting(self, key: str, value: Any) -> None:
        """
        Updates a specific user setting.
        
        Args:
            key: Setting name
            value: New value for the setting
        """
        self.settings[key] = value
        self.updated_at = time.time()
        self._pending_changes = True
        
        # If persistence enabled, save asynchronously
        if self.__class__._use_database:
            asyncio.create_task(self._save_to_db())
    
    async def add_download_task(
        self, 
        download_func: Callable[..., Awaitable[Any]], 
        *args: Any, 
        **kwargs: Any
    ) -> None:
        """
        Adds a task to the user's download queue.
        
        Args:
            download_func: Async function that performs the download
            *args, **kwargs: Arguments for the download function
        """
        # Check monthly limit for normal users
        if self.role == "normal":
            # Check if month changed and reset counter if necessary
            self._check_monthly_limit_reset()
            
            # Check if monthly limit reached
            if self.monthly_downloads >= MONTHLY_DOWNLOAD_LIMIT:
                # Reject download and raise error
                raise Exception(
                    f"You have reached the limit of {MONTHLY_DOWNLOAD_LIMIT} monthly downloads. "
                    "Upgrade to premium for unlimited downloads."
                )
        
        # Increment active downloads counter
        self.active_downloads += 1
        
        # Add task to queue
        await self.download_queue.add_download(
            self._wrap_download_task, download_func, *args, **kwargs
        )
    
    async def _wrap_download_task(
        self, 
        download_func: Callable[..., Awaitable[Any]],
        *args: Any, 
        **kwargs: Any
    ) -> None:
        """
        Wrapper for download tasks that updates counters.
        
        Args:
            download_func: Original async function
            *args, **kwargs: Arguments for the original function
        """
        try:
            # Execute download function
            await download_func(*args, **kwargs)
            
            # Update counters on completion
            self.total_downloads += 1
            
            # Increment monthly counter if normal user
            if self.role == "normal":
                self.monthly_downloads += 1
                
            self.active_downloads = max(0, self.active_downloads - 1)
            self._pending_changes = True
            
            # If persistence enabled, save results
            if self.__class__._use_database:
                asyncio.create_task(self._save_to_db())
                
        except Exception as e:
            # On error, also decrement active downloads counter
            self.active_downloads = max(0, self.active_downloads - 1)
            raise
    
    async def wait_for_rate_limit(self) -> None:
        """
        Waits until user can make a new request.
        
        This method blocks until rate limit is satisfied.
        """
        await self.rate_limiter.wait_for_slot()
    
    def get_role(self) -> str:
        """
        Gets the user's current role.
        
        Returns:
            User role (normal, premium, admin)
        """
        return self.role
    
    async def set_role(self, new_role: str) -> bool:
        """
        Updates the user's role and associated limits.
        
        Args:
            new_role: New role to set
            
        Returns:
            True if updated successfully, False otherwise
        """
        if new_role not in ["normal", "premium", "admin"]:
            logging.error(f"Invalid role: {new_role}")
            return False
        
        # Update role in memory
        self.role = new_role
        self._pending_changes = True
        
        # Update limits according to new role
        limit = ROLE_DOWNLOAD_LIMITS.get(new_role, ROLE_DOWNLOAD_LIMITS["normal"])
        self.download_queue.update_concurrency_limit(limit)

        # Save to DB if enabled
        if self.__class__._use_database and db_service:
            success = await self._save_to_db()
            
            # Try to update role directly in DB
            try:
                result = await asyncio.to_thread(
                    db_service.set_user_role,
                    self.user_id,
                    new_role
                )
                return result
            except Exception as e:
                logging.error(f"Error updating role in DB: {e}", exc_info=True)
                return success
                
        return True
    
    async def _save_to_db(self) -> bool:
        """
        Saves session to database without blocking.
        Registers write metrics to DB.
        
        Returns:
            True if saved successfully, False otherwise
        """
        if not self.__class__._use_database or not db_service:
            return False
            
        try:
            # Prepare data to save
            session_data = {
                "settings": self.settings,
                "last_activity": self.last_activity,
                "context_data": self.context_data,
                "total_downloads": self.total_downloads,
                "active_downloads": self.active_downloads,
                "role": self.role,
                "created_at": self.created_at,
                "updated_at": self.updated_at,
                "monthly_downloads": getattr(self, "monthly_downloads", 0),
                "current_month": getattr(self, "current_month", self._get_current_month())
            }
            
            # Execute in another thread to not block
            result = await asyncio.to_thread(
                db_service.save_user_session, 
                self.user_id, 
                session_data
            )
            
            # Register write in metrics
            if result:
                self._pending_changes = False
                self.__class__._metrics.log_db_write()
            else:
                self.__class__._metrics.db_errors += 1
                
            return result
            
        except Exception as e:
            logging.error(f"Error saving session {self.user_id} to DB: {e}", 
                         exc_info=True)
            self.__class__._metrics.db_errors += 1
            return False
    
    def increment_downloads(self) -> None:
        """
        Increments download counter and saves to DB.
        """
        # Check monthly limit for normal users
        if self.role == "normal":
            # Check if month changed and reset counter if necessary
            self._check_monthly_limit_reset()
            
            # Check if monthly limit reached
            if self.monthly_downloads >= MONTHLY_DOWNLOAD_LIMIT:
                # Reject download
                raise Exception(
                    f"You have reached the limit of {MONTHLY_DOWNLOAD_LIMIT} monthly downloads. "
                    "Upgrade to premium for unlimited downloads."
                )
                
            # Increment monthly counter
            self.monthly_downloads += 1
        
        self.total_downloads += 1
        self.updated_at = time.time()
        self._pending_changes = True
        
        # Save to DB if enabled
        if self.__class__._use_database:
            asyncio.create_task(self._save_to_db())
    
    def mark_as_changed(self) -> None:
        """
        Marks session as modified, requiring DB save.
        """
        self._pending_changes = True
        self.updated_at = time.time()
        
        if self.__class__._use_database:
            asyncio.create_task(self._save_to_db())
    
    def update_minor_stat(self, increment: int = 1) -> None:
        """
        Updates minor statistic without saving immediately to DB.
        """
        self.stat_counter = getattr(self, 'stat_counter', 0) + increment
        self.updated_at = time.time()
        self._pending_changes = True
        
        # Only save to DB every certain number of changes
        if self.stat_counter % 10 == 0 and self.__class__._use_database:
            asyncio.create_task(self._save_to_db())
    
    def has_permission(self, required_role: str) -> bool:
        """
        Checks if user has a role with sufficient permissions.
        
        Args:
            required_role: Required role for an operation
            
        Returns:
            True if user has sufficient permissions, False otherwise
        """
        if required_role not in ROLES_HIERARCHY:
            return False
            
        # Get indices in hierarchy
        required_idx = ROLES_HIERARCHY.index(required_role)
        user_idx = ROLES_HIERARCHY.index(self.role)
        
        # User has permissions if their role is equal or higher than required
        return user_idx >= required_idx

    def get_monthly_downloads_left(self) -> Dict[str, Union[int, str]]:
        """
        Returns information about remaining monthly downloads for normal users.
        
        Returns:
            Dictionary with used and remaining download info
        """
        # Only applicable to normal users
        if self.role != "normal":
            return {"limit": "∞", "used": self.monthly_downloads, "remaining": "∞"}
            
        # Check if month changed and reset counter if necessary
        self._check_monthly_limit_reset()
        
        # Calculate remaining downloads
        remaining = max(0, MONTHLY_DOWNLOAD_LIMIT - self.monthly_downloads)
        
        return {
            "limit": MONTHLY_DOWNLOAD_LIMIT,
            "used": self.monthly_downloads,
            "remaining": remaining
        }


async def cleanup_sessions() -> None:
    """
    Periodic function that cleans inactive sessions.
    Implements tiered expiration according to user role.
    """
    while True:
        try:
            # Wait configured interval
            await asyncio.sleep(SESSION_CLEANUP_INTERVAL)
            
            # Count sessions before cleaning
            active_before = len(UserSession._sessions)
            
            # Identify expired sessions using tiered times
            expired_ids = []
            for user_id, session in list(UserSession._sessions.items()):
                # Use is_expired which now implements tiered times
                if session.is_expired():
                    # If persistence enabled and pending changes, save last time
                    if UserSession._use_database and getattr(session, "_pending_changes", False):
                        await session._save_to_db()
                    expired_ids.append(user_id)
            
            # Remove expired sessions from memory
            for user_id in expired_ids:
                del UserSession._sessions[user_id]
            
            # Remove expired sessions from DB
            deleted_db = 0
            if UserSession._use_database and db_service:
                try:
                    # Use new function to respect tiered times
                    deleted_db = await asyncio.to_thread(
                        db_service.delete_tiered_sessions, 
                        SESSION_TIERS
                    )
                except Exception as e:
                    UserSession._metrics.db_errors += 1
                    logging.error(f"Error deleting sessions from DB: {e}", exc_info=True)
            
            # Log info only if there were changes
            if expired_ids or deleted_db > 0:
                logging.info(
                    f"Session cleanup: {len(expired_ids)} removed from memory"
                    f"{f', {deleted_db} from DB' if UserSession._use_database else ''}. "
                    f"{len(UserSession._sessions)} active sessions remaining."
                )
                
        except Exception as e:
            logging.error(f"Error in session cleanup: {e}", exc_info=True)


def requires_role(minimum_role: str):
    """
    Decorator to restrict commands by user role.
    
    Verifies user has at least the specified role
    before allowing command execution.
    
    Args:
        minimum_role: Minimum required role ("normal", "premium" or "admin")
    """
    def decorator(func):
        async def wrapper(update, context, *args, **kwargs):
            user_id = update.effective_user.id
            session = UserSession.get_session(user_id)
            
            # Check permissions
            if not session.has_permission(minimum_role):
                # Silent - don't send error message
                return
                
            # If has permissions, execute original function
            return await func(update, context, *args, **kwargs)
        return wrapper
    return decorator
