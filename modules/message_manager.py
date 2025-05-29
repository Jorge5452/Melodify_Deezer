"""
Sistema centralizado de gestión de mensajes para Melodify Deluxe.

Este módulo proporciona clases y funciones para enviar, actualizar y administrar
mensajes del bot de forma consistente y eficiente, reduciendo la cantidad de
mensajes enviados y mejorando la experiencia de usuario.
"""

import asyncio
import logging
import time
from typing import Dict, Any, Optional, Union, Callable, Awaitable, List
from datetime import datetime

from telegram import Message, Update, Chat
from telegram.ext import ContextTypes
from telegram.error import BadRequest, TelegramError

# Plantillas de mensajes
DOWNLOAD_TEMPLATES = {
    "starting": "⏳ Iniciando descarga de {content_type}...",
    "processing": "📥 Recibido! Procesando tu {content_type}...",
    "downloading": "⬇️ Descargando {track_info}...",
    "uploading": "✅ ¡Listo! Enviando a Telegram...",
    "completed": "✅ ¡Disfruta tu música!",
    "waiting": "⌛ Tu {content_type} está en cola de procesamiento.\n{queue_info}",
    "error": "❌ {error_message}"
}

SEARCH_TEMPLATES = {
    "starting": "🔍 Buscando {query_type}...",
    "no_results": "❌ No encontré resultados para '{query}'",
    "results": "🎵 Resultados para '{query}':",
    "error": "❌ Error en la búsqueda: {error_message}"
}

COLLECTION_TEMPLATES = {
    "starting": "🔍 Buscando {content_type}...",
    "processing": "⏳ Preparando {track_count} canciones...",
    "downloading": "⬇️ Descargando: {current}/{total} canciones...",
    "completed": "✅ Completado: {success_count}/{total} canciones",
    "uploading": "📤 Enviando canciones: {current}/{total}...",
    "waiting": "⌛ Tu {content_type} está en cola de procesamiento.\n{queue_info}",
    "error": "❌ {error_message}"
}

STATUS_EMOJI = {
    "starting": "⏳",
    "processing": "📥",
    "downloading": "⬇️",
    "uploading": "📤",
    "completed": "✅",
    "error": "❌",
    "warning": "⚠️",
    "info": "ℹ️",
    "waiting": "⌛"
}

# Configuración de tiempos de vida de mensajes (en segundos)
MESSAGE_TTL = {
    "success": 30,  # Mensajes de éxito
    "error": 60,    # Mensajes de error
    "info": 15,     # Mensajes informativos
    "temp": 10      # Mensajes temporales generales
}

async def safe_edit_message(message: Message, text: str, parse_mode: Optional[str] = None) -> bool:
    """
    Edita un mensaje de forma segura, manejando posibles errores.
    
    Args:
        message: Objeto Message de Telegram a editar
        text: Nuevo texto para el mensaje
        parse_mode: Modo de formato del texto (None, "Markdown", "HTML")
        
    Returns:
        bool: True si la edición fue exitosa, False en caso contrario
    """
    try:
        # Intentar editar el mensaje con el parse_mode especificado
        await message.edit_text(text, parse_mode=parse_mode)
        return True
    except BadRequest as e:
        # Esto ocurre si el mensaje no ha cambiado o ya no existe
        if "message is not modified" in str(e).lower():
            # No es un error real, simplemente no hubo cambios
            return True
        logging.warning(f"No se pudo editar mensaje: {str(e)}")
        return False
    except TelegramError as e:
        logging.warning(f"Error de Telegram al editar mensaje: {str(e)}")
        return False
    except Exception as e:
        logging.warning(f"Error inesperado al editar mensaje: {str(e)}")
        return False

async def delete_message_safe(message: Message, delay: float = 0) -> bool:
    """
    Elimina un mensaje después de un retardo, manejando errores posibles.
    
    Args:
        message: Mensaje a eliminar
        delay: Tiempo de espera antes de eliminar (segundos)
        
    Returns:
        bool: True si el mensaje fue eliminado, False en caso contrario
    """
    if delay > 0:
        await asyncio.sleep(delay)
    
    try:
        await message.delete()
        return True
    except BadRequest as e:
        # Handle specific known errors more gracefully
        error_msg = str(e).lower()
        if "message to delete not found" in error_msg or "message can't be deleted" in error_msg:
            # This is a common case - message already deleted or can't be deleted
            # Log at debug level only to reduce noise
            logging.debug(f"No se pudo eliminar el mensaje (ya borrado o sin permisos): {str(e)}")
        else:
            # Other BadRequest errors might be interesting
            logging.warning(f"Error al eliminar mensaje (BadRequest): {str(e)}")
        return False
    except TelegramError as e:
        # Handle Telegram API errors
        error_msg = str(e).lower()
        if "forbidden" in error_msg:
            logging.debug(f"Sin permisos para eliminar mensaje: {str(e)}")
        else:
            logging.warning(f"Error de Telegram al eliminar mensaje: {str(e)}")
        return False
    except Exception as e:
        logging.warning(f"Error inesperado al eliminar mensaje: {str(e)}")
        return False


class MessageTemplate:
    """Clase para manejar plantillas de mensajes con estados"""
    
    def __init__(self, template_dict: Dict[str, str]):
        self.templates = template_dict
        
    def get_template(self, status: str = "starting") -> str:
        """
        Obtiene el texto de plantilla para un estado específico.
        
        Args:
            status: Estado del mensaje (starting, processing, completed, error, etc.)
            
        Returns:
            Texto de la plantilla sin formatear
        """
        return self.templates.get(status, self.templates.get("info", "{message}"))
        
    def format_message(self, status: str = "starting", **kwargs) -> str:
        """
        Formatea un mensaje usando la plantilla y parámetros proporcionados.
        
        Args:
            status: Estado del mensaje
            **kwargs: Parámetros para formatear la plantilla
            
        Returns:
            Mensaje formateado
        """
        template = self.get_template(status)
        try:
            return template.format(**kwargs)
        except KeyError as e:
            logging.warning(f"Falta clave en plantilla {status}: {e}")
            # Intentar devolver al menos el template sin formatear
            return template
        except Exception as e:
            logging.error(f"Error al formatear mensaje: {e}")
            return f"Error al formatear mensaje: {str(e)}"


class ProgressMessage:
    """
    Mensaje con seguimiento de progreso y estados
    
    Esta clase encapsula un mensaje de Telegram que puede actualizarse
    para mostrar el progreso de una operación.
    """
    
    def __init__(self, message: Message, process_type: str):
        """
        Inicializa un mensaje de progreso.
        
        Args:
            message: Mensaje de Telegram a gestionar
            process_type: Tipo de proceso (download, search, collection)
        """
        self.message = message
        self.process_type = process_type
        self.current_status = "starting"
        self.data = {}  # Datos adicionales para formatear mensajes
        self.start_time = time.time()
        
        # Seleccionar plantilla según tipo de proceso
        if process_type == "download":
            self.template = MessageTemplate(DOWNLOAD_TEMPLATES)
        elif process_type == "search":
            self.template = MessageTemplate(SEARCH_TEMPLATES)
        elif process_type == "collection":
            self.template = MessageTemplate(COLLECTION_TEMPLATES)
        else:
            # Plantilla genérica si no hay específica
            self.template = MessageTemplate({
                "starting": "⏳ Iniciando...",
                "completed": "✅ Completado",
                "error": "❌ {error_message}"
            })
            
    async def update(self, status: str, parse_mode: Optional[str] = None, **kwargs) -> bool:
        """
        Actualiza el mensaje con un nuevo estado.
        
        Args:
            status: Nuevo estado del mensaje
            parse_mode: Modo de formato (Markdown, HTML, None)
            **kwargs: Datos para formatear el mensaje
            
        Returns:
            bool: True si la actualización fue exitosa
        """
        # Actualizar datos y estado
        self.data.update(kwargs)
        self.current_status = status
        
        # Formatear mensaje con datos acumulados
        message_text = self.template.format_message(status, **self.data)
        
        # Actualizar mensaje en Telegram
        return await safe_edit_message(self.message, message_text, parse_mode)
            
    async def complete(self, success: bool = True, auto_delete: bool = True, 
                      parse_mode: Optional[str] = None, **kwargs) -> bool:
        """
        Marca el mensaje de progreso como completado.
        
        Args:
            success: True si el proceso fue exitoso, False en caso contrario
            auto_delete: Si True, programa eliminación automática
            parse_mode: Modo de formato (Markdown, HTML, None)
            **kwargs: Datos adicionales para formatear el mensaje
            
        Returns:
            bool: True si la actualización fue exitosa
        """
        # Actualizar con estado final
        status = "completed" if success else "error"
        self.data.update(kwargs)
        
        # Try to update the message, but handle errors gracefully
        try:
            await self.update(status, parse_mode)
        except Exception as e:
            logging.debug(f"No se pudo actualizar mensaje de progreso a estado '{status}': {str(e)}")
        
        # Calcular tiempo total que tomó el proceso
        elapsed_time = time.time() - self.start_time
        
        if auto_delete:
            # Tiempo antes de eliminar depende del resultado
            ttl = MESSAGE_TTL["success"] if success else MESSAGE_TTL["error"]
            # Programar eliminación
            try:
                # Use a shorter TTL for error messages if they're very common
                if not success and "error_message" in kwargs:
                    error_msg = kwargs["error_message"].lower()
                    if "límite de descargas" in error_msg or "descargas simultáneas" in error_msg:
                        ttl = min(10, ttl)  # Use a shorter TTL for common errors
                
                asyncio.create_task(delete_message_safe(self.message, ttl))
            except Exception as e:
                logging.debug(f"Error al programar eliminación automática de mensaje: {str(e)}")
            
        return True


class AutoDestructMessage:
    """Mensaje que se elimina después de un tiempo determinado"""
    
    def __init__(self, message: Message, duration: int = 10):
        """
        Inicializa un mensaje de autodestrucción.
        
        Args:
            message: Mensaje de Telegram a gestionar
            duration: Tiempo en segundos antes de eliminar el mensaje
        """
        self.message = message
        self.duration = duration
        self._deletion_task = None
        
    async def start_countdown(self) -> None:
        """Inicia la cuenta regresiva para eliminar el mensaje"""
        # Cancelar tarea anterior si existe
        if self._deletion_task:
            self._deletion_task.cancel()
        
        # Crear nueva tarea de eliminación
        self._deletion_task = asyncio.create_task(
            delete_message_safe(self.message, self.duration)
        )
        
    async def extend_duration(self, additional_time: int) -> None:
        """
        Extiende la duración antes de la eliminación.
        
        Args:
            additional_time: Segundos adicionales a añadir
        """
        self.duration += additional_time
        # Reiniciar cuenta atrás
        await self.start_countdown()
        
    async def cancel(self) -> None:
        """Cancela la eliminación programada"""
        if self._deletion_task:
            self._deletion_task.cancel()
            self._deletion_task = None


class MessageManager:
    """
    Gestor centralizado para todos los mensajes del bot.
    
    Proporciona funcionalidades para:
    - Enviar mensajes con formato consistente
    - Actualizar mensajes existentes con estados de progreso
    - Gestionar mensajes autoexpirables
    - Utilizar plantillas de mensajes predefinidas
    """
    
    # Singleton pattern
    _instance = None
    
    @classmethod
    def get_instance(cls):
        """Obtiene la instancia singleton del gestor de mensajes"""
        if cls._instance is None:
            cls._instance = MessageManager()
        return cls._instance
    
    def __init__(self):
        """Inicializa el gestor de mensajes"""
        # Inicializar plantillas
        self._templates = {
            "download": MessageTemplate(DOWNLOAD_TEMPLATES),
            "search": MessageTemplate(SEARCH_TEMPLATES),
            "collection": MessageTemplate(COLLECTION_TEMPLATES)
        }
        # Registros de mensajes
        self._progress_messages: Dict[int, ProgressMessage] = {}
        self._auto_destruct_messages: Dict[int, AutoDestructMessage] = {}
        
    async def send_message(self, 
                         update: Update, 
                         message_type: str, 
                         status: str = "info",
                         auto_destruct: bool = False,
                         ttl: Optional[int] = None,
                         parse_mode: Optional[str] = None,
                         **kwargs) -> Message:
        """
        Envía un mensaje utilizando una plantilla predefinida.
        
        Args:
            update: Objeto Update de Telegram
            message_type: Tipo de mensaje (download, search, collection)
            status: Estado del mensaje
            auto_destruct: Si debe autodestruirse
            ttl: Tiempo de vida del mensaje en segundos
            parse_mode: Modo de formato (Markdown, HTML)
            **kwargs: Datos para formatear la plantilla
            
        Returns:
            Message: Mensaje enviado
        """
        template = self._templates.get(message_type, 
                                      self._templates.get("download"))
        
        # Formatear mensaje
        text = template.format_message(status, **kwargs)
        
        # Enviar mensaje
        message = await update.message.reply_text(text, parse_mode=parse_mode)
        
        # Configurar autodestrucción si es necesario
        if auto_destruct:
            if ttl is None:
                # Usar valor por defecto según tipo de mensaje
                if status == "error":
                    ttl = MESSAGE_TTL["error"]
                elif status == "completed":
                    ttl = MESSAGE_TTL["success"]
                else:
                    ttl = MESSAGE_TTL["info"]
                    
            auto_msg = AutoDestructMessage(message, ttl)
            self._auto_destruct_messages[message.message_id] = auto_msg
            await auto_msg.start_countdown()
            
        return message
        
    async def send_progress(self, 
                          update: Update, 
                          process_type: str = "download",
                          initial_status: str = "starting",
                          parse_mode: Optional[str] = None,
                          query = None,
                          **kwargs) -> ProgressMessage:
        """
        Envía un mensaje de progreso que puede actualizarse.
        
        Args:
            update: Objeto Update de Telegram (puede ser None si se proporciona query)
            process_type: Tipo de proceso (download, search, collection)
            initial_status: Estado inicial
            parse_mode: Modo de formato
            query: Objeto CallbackQuery (opcional, usado cuando update es None)
            **kwargs: Datos para formatear la plantilla
            
        Returns:
            ProgressMessage: Objeto que gestiona el mensaje de progreso
        """
        template = self._templates.get(process_type, 
                                     self._templates.get("download"))
        
        # Formatear mensaje inicial
        text = template.format_message(initial_status, **kwargs)
        
        # Determinar cómo enviar el mensaje según el contexto
        if update is not None:
            # Caso normal: enviar como respuesta a un mensaje
            message = await update.message.reply_text(text, parse_mode=parse_mode)
        elif query is not None:
            # Caso de callback: editar mensaje existente o enviar nuevo
            try:
                await query.edit_message_text(text, parse_mode=parse_mode)
                message = query.message
            except Exception as e:
                # Si falla editar, enviar un nuevo mensaje
                message = await query.message.reply_text(text, parse_mode=parse_mode)
        else:
            # No se proporcionó ni update ni query
            raise ValueError("Se debe proporcionar update o query para enviar mensaje de progreso")
        
        # Crear objeto de progreso
        progress = ProgressMessage(message, process_type)
        progress.data.update(kwargs)  # Guardar datos iniciales
        
        # Registrar el mensaje de progreso
        self._progress_messages[message.message_id] = progress
        
        return progress
    
    async def send_temporary(self, 
                           update: Update, 
                           text: str,
                           ttl: int = 10,
                           parse_mode: Optional[str] = None) -> Message:
        """
        Envía un mensaje temporal que se autodestruye después de ttl segundos.
        
        Args:
            update: Objeto Update de Telegram
            text: Texto del mensaje
            ttl: Tiempo de vida en segundos
            parse_mode: Modo de formato
            
        Returns:
            Message: Mensaje enviado
        """
        # Enviar mensaje
        message = await update.message.reply_text(text, parse_mode=parse_mode)
        
        # Programar eliminación
        asyncio.create_task(delete_message_safe(message, ttl))
        
        return message
    
    def get_progress(self, message_id: int) -> Optional[ProgressMessage]:
        """
        Obtiene un mensaje de progreso por su ID.
        
        Args:
            message_id: ID del mensaje
            
        Returns:
            ProgressMessage o None si no existe
        """
        return self._progress_messages.get(message_id)
    
    def register_progress(self, progress: ProgressMessage) -> None:
        """
        Registra un mensaje de progreso existente.
        
        Args:
            progress: ProgressMessage a registrar
        """
        self._progress_messages[progress.message.message_id] = progress
    
    def unregister_message(self, message_id: int) -> None:
        """
        Elimina un mensaje de los registros.
        
        Args:
            message_id: ID del mensaje a eliminar
        """
        self._progress_messages.pop(message_id, None)
        self._auto_destruct_messages.pop(message_id, None)

# Crear singleton para uso global
message_manager = MessageManager.get_instance() 