"""
Módulo para gestión centralizada de logs en Melodify Deluxe.

Proporciona funcionalidades para:
- Configurar niveles de log por componente
- Silenciar grupos de loggers relacionados
- Activar logs contextuales temporalmente
- Filtrar mensajes repetitivos
"""

import logging
import functools
import time
import threading
import contextlib
from typing import Dict, List, Set, Any, Optional, Union, Callable, ContextManager

# Grupos predefinidos de loggers para silenciar/activar juntos
LOGGER_GROUPS = {
    "http": [
        "httpx", "httpcore", "httpcore.http11", "httpcore.connection", 
        "httpcore.http", "telegram.request"
    ],
    "telegram": [
        "telegram", "telegram.Bot", "telegram.ext", "telegram.ext.Application"
    ],
    "database": [
        "db_manager", "sqlite3"
    ],
    "download": [
        "downloader", "deezer", "deemix"
    ],
    "messages": [
        "modules.message_manager"
    ]
}

# Niveles predefinidos para diferentes entornos
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
    """Gestor centralizado de logs para toda la aplicación."""
    
    _instance = None  # Singleton
    
    @classmethod
    def get_instance(cls):
        """Obtiene la instancia única del gestor de logs."""
        if cls._instance is None:
            cls._instance = LogManager()
        return cls._instance
    
    def __init__(self):
        """Inicializa el gestor de logs con valores predeterminados."""
        self.initialized = False
        self.active_contexts = set()
        self.original_levels = {}  # Guardar niveles originales
        self.log_formatter = logging.Formatter(
            "%(asctime)s - %(levelname)s - %(name)s - %(message)s"
        )
        self.verbose_formatter = logging.Formatter(
            "%(asctime)s - %(levelname)s - %(name)s:%(lineno)d - %(funcName)s - %(message)s"
        )
    
    def initialize(self, log_level: str = "WARNING", 
                   log_file: Optional[str] = None,
                   enable_console: bool = True,
                   preset: str = "production") -> None:
        """
        Inicializa la configuración global de logging.
        
        Args:
            log_level: Nivel de log principal
            log_file: Ruta al archivo de log
            enable_console: Si True, envía logs a la consola
            preset: Preset de configuración ("production", "development", "debug")
        """
        if self.initialized:
            return
            
        # Configurar logger raíz
        root_logger = logging.getLogger()
        root_logger.setLevel(getattr(logging, log_level))
        
        # Limpiar handlers existentes
        for handler in list(root_logger.handlers):
            root_logger.removeHandler(handler)
        
        # Configurar handler de consola
        if enable_console:
            console_handler = logging.StreamHandler()
            console_handler.setFormatter(self.log_formatter)
            root_logger.addHandler(console_handler)
        
        # Configurar handler de archivo
        if log_file:
            try:
                file_handler = logging.FileHandler(log_file)
                file_handler.setFormatter(self.log_formatter)
                root_logger.addHandler(file_handler)
            except Exception as e:
                logging.error(f"No se pudo configurar archivo de log {log_file}: {e}")
        
        # Aplicar preset
        self.apply_preset(preset)
        
        self.initialized = True
    
    def apply_preset(self, preset_name: str) -> None:
        """
        Aplica un preset predefinido de niveles de log.
        
        Args:
            preset_name: Nombre del preset ("production", "development", "debug")
        """
        if preset_name not in LOG_PRESETS:
            logging.warning(f"Preset de log desconocido: {preset_name}")
            return
            
        preset = LOG_PRESETS[preset_name]
        
        # Configurar nivel raíz
        if "root" in preset:
            logging.getLogger().setLevel(preset["root"])
        
        # Configurar grupos
        for group_name, level in preset.items():
            if group_name == "root":
                continue
                
            if group_name in LOGGER_GROUPS:
                self.set_group_level(group_name, level)
    
    def set_group_level(self, group_name: str, level: Union[str, int]) -> None:
        """
        Establece el nivel de log para un grupo predefinido de loggers.
        
        Args:
            group_name: Nombre del grupo de loggers
            level: Nivel de log a establecer
        """
        if group_name not in LOGGER_GROUPS:
            logging.warning(f"Grupo de log desconocido: {group_name}")
            return
            
        # Convertir nivel si es string
        if isinstance(level, str):
            level = getattr(logging, level.upper())
            
        # Aplicar a todos los loggers del grupo
        for logger_name in LOGGER_GROUPS[group_name]:
            logger = logging.getLogger(logger_name)
            logger.setLevel(level)
            
    def silence_group(self, group_name: str) -> None:
        """
        Silencia completamente un grupo de loggers.
        
        Args:
            group_name: Nombre del grupo a silenciar
        """
        self.set_group_level(group_name, logging.ERROR)
    
    def unsilence_group(self, group_name: str, level: Union[str, int] = logging.INFO) -> None:
        """
        Restaura el nivel normal de un grupo previamente silenciado.
        
        Args:
            group_name: Nombre del grupo a restaurar
            level: Nivel al que restaurar (por defecto INFO)
        """
        self.set_group_level(group_name, level)
    
    def silence_all_except(self, except_groups: List[str]) -> None:
        """
        Silencia todos los grupos excepto los especificados.
        
        Args:
            except_groups: Lista de nombres de grupos a mantener activos
        """
        for group_name in LOGGER_GROUPS:
            if group_name not in except_groups:
                self.silence_group(group_name)
    
    @contextlib.contextmanager
    def verbose_context(self, component: Optional[str] = None, 
                       level: int = logging.DEBUG) -> ContextManager[None]:
        """
        Contexto temporal con logs más detallados para un componente.
        
        Args:
            component: Componente a aumentar verbosidad (None para todos)
            level: Nivel de log a usar temporalmente
            
        Yields:
            Contexto donde los logs son más detallados
        """
        # Guardar niveles actuales
        saved_levels = {}
        
        if component and component in LOGGER_GROUPS:
            # Guardar niveles anteriores y aumentar verbosidad
            for logger_name in LOGGER_GROUPS[component]:
                logger = logging.getLogger(logger_name)
                saved_levels[logger_name] = logger.level
                logger.setLevel(level)
                
                # Cambiar formato para incluir más info
                for handler in logger.handlers:
                    saved_levels[f"fmt_{id(handler)}"] = handler.formatter
                    handler.setFormatter(self.verbose_formatter)
        elif not component:
            # Aplicar a todos los loggers
            for group_name, loggers in LOGGER_GROUPS.items():
                for logger_name in loggers:
                    logger = logging.getLogger(logger_name)
                    saved_levels[logger_name] = logger.level
                    logger.setLevel(level)
                    
                    # Cambiar formato para incluir más info
                    for handler in logger.handlers:
                        saved_levels[f"fmt_{id(handler)}"] = handler.formatter
                        handler.setFormatter(self.verbose_formatter)
        
        try:
            yield
        finally:
            # Restaurar niveles anteriores
            for name, level in saved_levels.items():
                if name.startswith("fmt_"):
                    # Restaurar formato
                    id_int = int(name[4:])
                    for group_loggers in LOGGER_GROUPS.values():
                        for logger_name in group_loggers:
                            logger = logging.getLogger(logger_name)
                            for handler in logger.handlers:
                                if id(handler) == id_int:
                                    handler.setFormatter(level)
                else:
                    # Restaurar nivel
                    logger = logging.getLogger(name)
                    logger.setLevel(level)

# Crear instancia global
log_manager = LogManager.get_instance()

# Funciones de conveniencia para usar en el código
def initialize_logging(log_level: str = "WARNING", 
                     log_file: Optional[str] = None,
                     enable_console: bool = True,
                     preset: str = "production") -> None:
    """Inicializa el sistema de logging."""
    log_manager.initialize(log_level, log_file, enable_console, preset)

def silence_http_logs() -> None:
    """Silencia los logs relacionados con HTTP."""
    log_manager.silence_group("http")

def silence_telegram_logs() -> None:
    """Silencia los logs relacionados con Telegram."""
    log_manager.silence_group("telegram")

def unsilence_logs(group_name: str) -> None:
    """Restaura los logs de un grupo específico."""
    log_manager.unsilence_group(group_name)

@contextlib.contextmanager
def verbose_logging(component: Optional[str] = None) -> ContextManager[None]:
    """Contexto para logs verbosos temporales."""
    with log_manager.verbose_context(component):
        yield 