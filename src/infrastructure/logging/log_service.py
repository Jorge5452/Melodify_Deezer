# -*- coding: utf-8 -*-
"""
Centralized logging management for Melodify Deluxe.

Provides functionality for:
- Configuring log levels per component
- Silencing groups of related loggers
- Temporarily activating contextual logs
- Filtering repetitive messages
"""

import logging
import functools
import time
import threading
import contextlib
from typing import Dict, List, Set, Any, Optional, Union, Callable, ContextManager

# Predefined groups of loggers to silence/activate together
LOGGER_GROUPS = {
    "http": [
        "httpx", "httpcore", "httpcore.http11", "httpcore.connection", 
        "httpcore.http", "telegram.request"
    ],
    "telegram": [
        "telegram", "telegram.Bot", "telegram.ext", "telegram.ext.Application"
    ],
    "database": [
        "db_manager", "sqlite3", "src.infrastructure.database"
    ],
    "download": [
        "downloader", "deezer", "deemix", "src.infrastructure.deezer"
    ],
    "messages": [
        "modules.message_manager", "src.interface.telegram"
    ]
}

# Predefined levels for different environments
LOG_PRESETS = {
    "production": {
        "http": logging.ERROR,
        "telegram": logging.WARNING,
        "database": logging.WARNING,
        "download": logging.INFO,
        "messages": logging.WARNING,
        "root": logging.WARNING
    },
    "development": {
        "http": logging.WARNING,
        "telegram": logging.INFO,
        "database": logging.INFO,
        "download": logging.DEBUG,
        "messages": logging.DEBUG,
        "root": logging.INFO
    },
    "debug": {
        "http": logging.INFO,
        "telegram": logging.DEBUG,
        "database": logging.DEBUG,
        "download": logging.DEBUG,
        "messages": logging.DEBUG,
        "root": logging.DEBUG
    }
}


class LogManager:
    """Centralized log manager for the entire application."""
    
    _instance = None  # Singleton
    
    @classmethod
    def get_instance(cls) -> "LogManager":
        """Gets the unique instance of the log manager."""
        if cls._instance is None:
            cls._instance = LogManager()
        return cls._instance
    
    def __init__(self):
        """Initializes the log manager with default values."""
        self.initialized = False
        self.active_contexts: Set[str] = set()
        self.original_levels: Dict[str, int] = {}  # Save original levels
        self.log_formatter = logging.Formatter(
            "%(asctime)s - %(levelname)s - %(name)s - %(message)s"
        )
        self.verbose_formatter = logging.Formatter(
            "%(asctime)s - %(levelname)s - %(name)s:%(lineno)d - %(funcName)s - %(message)s"
        )
    
    def initialize(
        self,
        log_level: str = "WARNING", 
        log_file: Optional[str] = None,
        enable_console: bool = True,
        preset: str = "production"
    ) -> None:
        """
        Initializes the global logging configuration.
        
        Args:
            log_level: Main log level
            log_file: Path to log file
            enable_console: If True, sends logs to console
            preset: Configuration preset ("production", "development", "debug")
        """
        if self.initialized:
            return
            
        # Configure root logger
        root_logger = logging.getLogger()
        root_logger.setLevel(getattr(logging, log_level))
        
        # Clear existing handlers
        for handler in list(root_logger.handlers):
            root_logger.removeHandler(handler)
        
        # Configure console handler
        if enable_console:
            console_handler = logging.StreamHandler()
            console_handler.setFormatter(self.log_formatter)
            root_logger.addHandler(console_handler)
        
        # Configure file handler
        if log_file:
            try:
                file_handler = logging.FileHandler(log_file)
                file_handler.setFormatter(self.log_formatter)
                root_logger.addHandler(file_handler)
            except Exception as e:
                logging.error(f"Could not configure log file {log_file}: {e}")
        
        # Apply preset
        self.apply_preset(preset)
        
        self.initialized = True
    
    def apply_preset(self, preset_name: str) -> None:
        """
        Applies a predefined log level preset.
        
        Args:
            preset_name: Name of the preset ("production", "development", "debug")
        """
        if preset_name not in LOG_PRESETS:
            logging.warning(f"Unknown log preset: {preset_name}")
            return
            
        preset = LOG_PRESETS[preset_name]
        
        # Configure root level
        if "root" in preset:
            logging.getLogger().setLevel(preset["root"])
        
        # Configure groups
        for group_name, level in preset.items():
            if group_name == "root":
                continue
                
            if group_name in LOGGER_GROUPS:
                self.set_group_level(group_name, level)
    
    def set_group_level(self, group_name: str, level: Union[str, int]) -> None:
        """
        Sets the log level for a predefined group of loggers.
        
        Args:
            group_name: Name of the logger group
            level: Log level to set
        """
        if group_name not in LOGGER_GROUPS:
            logging.warning(f"Unknown log group: {group_name}")
            return
            
        # Convert level if string
        if isinstance(level, str):
            level = getattr(logging, level.upper())
            
        # Apply to all loggers in the group
        for logger_name in LOGGER_GROUPS[group_name]:
            logger = logging.getLogger(logger_name)
            logger.setLevel(level)
            
    def silence_group(self, group_name: str) -> None:
        """
        Completely silences a group of loggers.
        
        Args:
            group_name: Name of the group to silence
        """
        self.set_group_level(group_name, logging.ERROR)
    
    def unsilence_group(self, group_name: str, level: Union[str, int] = logging.INFO) -> None:
        """
        Restores the normal level of a previously silenced group.
        
        Args:
            group_name: Name of the group to restore
            level: Level to restore to (default INFO)
        """
        self.set_group_level(group_name, level)
    
    def silence_all_except(self, except_groups: List[str]) -> None:
        """
        Silences all groups except those specified.
        
        Args:
            except_groups: List of group names to keep active
        """
        for group_name in LOGGER_GROUPS:
            if group_name not in except_groups:
                self.silence_group(group_name)
    
    @contextlib.contextmanager
    def verbose_context(
        self, 
        component: Optional[str] = None, 
        level: int = logging.DEBUG
    ) -> ContextManager[None]:
        """
        Temporary context with more detailed logs for a component.
        
        Args:
            component: Component to increase verbosity (None for all)
            level: Log level to use temporarily
            
        Yields:
            Context where logs are more detailed
        """
        # Save current levels
        saved_levels: Dict[str, Any] = {}
        
        if component and component in LOGGER_GROUPS:
            # Save previous levels and increase verbosity
            for logger_name in LOGGER_GROUPS[component]:
                logger = logging.getLogger(logger_name)
                saved_levels[logger_name] = logger.level
                logger.setLevel(level)
                
                # Change format to include more info
                for handler in logger.handlers:
                    saved_levels[f"fmt_{id(handler)}"] = handler.formatter
                    handler.setFormatter(self.verbose_formatter)
        elif not component:
            # Apply to all loggers
            for group_name, loggers in LOGGER_GROUPS.items():
                for logger_name in loggers:
                    logger = logging.getLogger(logger_name)
                    saved_levels[logger_name] = logger.level
                    logger.setLevel(level)
                    
                    # Change format to include more info
                    for handler in logger.handlers:
                        saved_levels[f"fmt_{id(handler)}"] = handler.formatter
                        handler.setFormatter(self.verbose_formatter)
        
        try:
            yield
        finally:
            # Restore previous levels
            for name, saved_level in saved_levels.items():
                if name.startswith("fmt_"):
                    # Restore format
                    id_int = int(name[4:])
                    for group_loggers in LOGGER_GROUPS.values():
                        for logger_name in group_loggers:
                            logger = logging.getLogger(logger_name)
                            for handler in logger.handlers:
                                if id(handler) == id_int:
                                    handler.setFormatter(saved_level)
                else:
                    # Restore level
                    logger = logging.getLogger(name)
                    logger.setLevel(saved_level)


# Create global instance
log_manager = LogManager.get_instance()


# Convenience functions for use in code
def initialize_logging(
    log_level: str = "WARNING", 
    log_file: Optional[str] = None,
    enable_console: bool = True,
    preset: str = "production"
) -> None:
    """Initializes the logging system."""
    log_manager.initialize(log_level, log_file, enable_console, preset)


def silence_http_logs() -> None:
    """Silences HTTP related logs."""
    log_manager.silence_group("http")


def silence_telegram_logs() -> None:
    """Silences Telegram related logs."""
    log_manager.silence_group("telegram")


def unsilence_logs(group_name: str) -> None:
    """Restores logs for a specific group."""
    log_manager.unsilence_group(group_name)


@contextlib.contextmanager
def verbose_logging(component: Optional[str] = None) -> ContextManager[None]:
    """Context for temporary verbose logs."""
    with log_manager.verbose_context(component):
        yield
