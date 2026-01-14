# -*- coding: utf-8 -*-
"""
Message management system for Melodify Deluxe.

Provides classes and functions to send, update and manage bot messages
consistently and efficiently.
"""

import asyncio
import logging
import time
from typing import Dict, Any, Optional

from telegram import Message, Update
from telegram.error import BadRequest, TelegramError


# Message templates
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

MESSAGE_TTL = {
    "success": 30,
    "error": 60,
    "info": 15,
    "temp": 10
}


async def safe_edit_message(message: Message, text: str, parse_mode: Optional[str] = None) -> bool:
    """Edits a message safely, handling possible errors."""
    try:
        await message.edit_text(text, parse_mode=parse_mode)
        return True
    except BadRequest as e:
        if "message is not modified" in str(e).lower():
            return True
        logging.warning(f"Could not edit message: {str(e)}")
        return False
    except TelegramError as e:
        logging.warning(f"Telegram error editing message: {str(e)}")
        return False
    except Exception as e:
        logging.warning(f"Unexpected error editing message: {str(e)}")
        return False


async def delete_message_safe(message: Message, delay: float = 0) -> bool:
    """Deletes a message after delay, handling errors."""
    if delay > 0:
        await asyncio.sleep(delay)
    
    try:
        await message.delete()
        return True
    except BadRequest as e:
        error_msg = str(e).lower()
        if "message to delete not found" in error_msg or "message can't be deleted" in error_msg:
            logging.debug(f"Could not delete message (already deleted or no permissions): {str(e)}")
        else:
            logging.warning(f"Error deleting message (BadRequest): {str(e)}")
        return False
    except TelegramError as e:
        error_msg = str(e).lower()
        if "forbidden" in error_msg:
            logging.debug(f"No permissions to delete message: {str(e)}")
        else:
            logging.warning(f"Telegram error deleting message: {str(e)}")
        return False
    except Exception as e:
        logging.warning(f"Unexpected error deleting message: {str(e)}")
        return False


class MessageTemplate:
    """Class to handle message templates with states."""
    
    def __init__(self, template_dict: Dict[str, str]):
        self.templates = template_dict
        
    def get_template(self, status: str = "starting") -> str:
        return self.templates.get(status, self.templates.get("info", "{message}"))
        
    def format_message(self, status: str = "starting", **kwargs) -> str:
        template = self.get_template(status)
        try:
            return template.format(**kwargs)
        except KeyError as e:
            logging.warning(f"Missing key in template {status}: {e}")
            return template
        except Exception as e:
            logging.error(f"Error formatting message: {e}")
            return f"Error formatting message: {str(e)}"


class ProgressMessage:
    """Message with progress tracking and states."""
    
    def __init__(self, message: Message, process_type: str):
        self.message = message
        self.process_type = process_type
        self.current_status = "starting"
        self.data = {}
        self.start_time = time.time()
        self.from_collection = False
        
        if process_type == "download":
            self.template = MessageTemplate(DOWNLOAD_TEMPLATES)
        elif process_type == "search":
            self.template = MessageTemplate(SEARCH_TEMPLATES)
        elif process_type == "collection":
            self.template = MessageTemplate(COLLECTION_TEMPLATES)
        else:
            self.template = MessageTemplate({
                "starting": "⏳ Iniciando...",
                "completed": "✅ Completado",
                "error": "❌ {error_message}"
            })
            
    async def update(self, status: str, parse_mode: Optional[str] = None, **kwargs) -> bool:
        self.data.update(kwargs)
        self.current_status = status
        message_text = self.template.format_message(status, **self.data)
        return await safe_edit_message(self.message, message_text, parse_mode)
            
    async def complete(self, success: bool = True, auto_delete: bool = True, 
                      parse_mode: Optional[str] = None, **kwargs) -> bool:
        status = "completed" if success else "error"
        self.data.update(kwargs)
        
        try:
            await self.update(status, parse_mode)
        except Exception as e:
            logging.debug(f"Could not update progress message to state '{status}': {str(e)}")
        
        if auto_delete:
            ttl = MESSAGE_TTL["success"] if success else MESSAGE_TTL["error"]
            try:
                if not success and "error_message" in kwargs:
                    error_msg = kwargs["error_message"].lower()
                    if "límite de descargas" in error_msg or "descargas simultáneas" in error_msg:
                        ttl = min(10, ttl)
                asyncio.create_task(delete_message_safe(self.message, ttl))
            except Exception as e:
                logging.debug(f"Error scheduling auto-delete: {str(e)}")
            
        return True


class MessageManager:
    """Centralized manager for all bot messages."""
    
    _instance = None
    
    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = MessageManager()
        return cls._instance
    
    def __init__(self):
        self._templates = {
            "download": MessageTemplate(DOWNLOAD_TEMPLATES),
            "search": MessageTemplate(SEARCH_TEMPLATES),
            "collection": MessageTemplate(COLLECTION_TEMPLATES)
        }
        self._progress_messages: Dict[int, ProgressMessage] = {}
        
    async def send_progress(self, 
                          update: Update, 
                          process_type: str = "download",
                          initial_status: str = "starting",
                          parse_mode: Optional[str] = None,
                          query = None,
                          **kwargs) -> ProgressMessage:
        template = self._templates.get(process_type, self._templates.get("download"))
        text = template.format_message(initial_status, **kwargs)
        
        if update is not None:
            message = await update.message.reply_text(text, parse_mode=parse_mode)
        elif query is not None:
            try:
                await query.edit_message_text(text, parse_mode=parse_mode)
                message = query.message
            except Exception:
                message = await query.message.reply_text(text, parse_mode=parse_mode)
        else:
            raise ValueError("Must provide update or query to send progress message")
        
        progress = ProgressMessage(message, process_type)
        progress.data.update(kwargs)
        self._progress_messages[message.message_id] = progress
        
        return progress
    
    async def send_temporary(self, 
                           update: Update, 
                           text: str,
                           ttl: int = 10,
                           parse_mode: Optional[str] = None) -> Message:
        message = await update.message.reply_text(text, parse_mode=parse_mode)
        asyncio.create_task(delete_message_safe(message, ttl))
        return message


# Create singleton for global use
message_manager = MessageManager.get_instance()
