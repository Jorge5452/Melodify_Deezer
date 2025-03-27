import logging
import asyncio
from typing import List, Union, Optional, Any, Dict
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaAudio, Message
from telegram.ext import ContextTypes

class SimulatedUser:
    """
    Simula un objeto User de Telegram para pruebas y procesamiento interno.
    
    Esta clase proporciona un objeto similar al usuario de Telegram con
    propiedades básicas necesarias para simular interacciones.
    
    Attributes:
        id (int): El ID único del usuario
    """
    def __init__(self, user_id: int) -> None:
        """
        Inicializa un usuario simulado con un ID específico.
        
        Args:
            user_id: El ID de usuario a asignar
        """
        self.id = user_id

class SimulatedMessage:
    """
    Simula un objeto Message de Telegram para pruebas y procesamiento interno.
    
    Esta clase permite crear mensajes simulados que pueden utilizarse en
    funciones que esperan objetos Message de Telegram, facilitando pruebas
    y procesamiento de solicitudes sin un mensaje real.
    
    Attributes:
        chat_id (int): El ID del chat donde se enviaría el mensaje
        text (str): El texto del mensaje
        _context (ContextTypes.DEFAULT_TYPE): Contexto del bot necesario para enviar mensajes
    """
    def __init__(self, chat_id: int, text: str) -> None:
        """
        Inicializa un mensaje simulado.
        
        Args:
            chat_id: ID del chat donde se simula el mensaje
            text: Texto del mensaje simulado
        """
        self.chat_id = chat_id
        self.text = text
        
    async def reply_text(self, text: str, **kwargs) -> Message:
        """
        Simula la respuesta a un mensaje con texto.
        
        Envía un mensaje a través del contexto del bot al mismo chat_id.
        
        Args:
            text: Texto a enviar como respuesta
            **kwargs: Argumentos adicionales para send_message
            
        Returns:
            Message: El objeto Message devuelto por telegram
            
        Note:
            Se debe proporcionar _context antes de usar este método
        """
        return await self._context.bot.send_message(chat_id=self.chat_id, text=text, **kwargs)
        
    async def reply_audio(self, **kwargs) -> Message:
        """
        Simula el envío de un archivo de audio como respuesta.
        
        Args:
            **kwargs: Argumentos para send_audio
            
        Returns:
            Message: El objeto Message devuelto por telegram
            
        Note:
            Se debe proporcionar _context antes de usar este método
        """
        return await self._context.bot.send_audio(chat_id=self.chat_id, **kwargs)
    
class SimulatedUpdate:
    """
    Simula un objeto Update de Telegram para facilitar las pruebas y reutilización de código.
    
    Esta clase permite crear un objeto que imita el comportamiento de un Update de Telegram,
    especialmente útil para reutilizar funciones que procesan mensajes o actualizaciones.
    
    Attributes:
        message (SimulatedMessage): El mensaje simulado
        effective_user (SimulatedUser): El usuario simulado
    """
    def __init__(self, chat_id: int, user_id: int, text: str, context: ContextTypes.DEFAULT_TYPE) -> None:
        """
        Inicializa una actualización simulada.
        
        Args:
            chat_id: ID del chat donde se simula la actualización
            user_id: ID del usuario que simuladamente envía el mensaje
            text: Texto del mensaje simulado
            context: Contexto del bot necesario para enviar mensajes
        """
        self.message = SimulatedMessage(chat_id, text)
        self.effective_user = SimulatedUser(user_id)
        # Proporcionar context a SimulatedMessage
        self.message._context = context

# Función auxiliar para crear objetos simulados
def create_simulated_update(query, context, url):
    """
    Crea un objeto Update simulado a partir de un callback query.
    
    Args:
        query: Objeto CallbackQuery de Telegram
        context: Contexto del bot
        url: URL a incluir como texto del mensaje
    
    Returns:
        Objeto SimulatedUpdate para usar en funciones de manejo de mensajes
    """
    chat_id = query.message.chat_id
    user_id = query.from_user.id
    return SimulatedUpdate(chat_id, user_id, url, context)

# Funciones auxiliares generales
async def safe_edit_message(message, text, parse_mode=None):
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
    except Exception as e:
        logging.warning(f"No se pudo editar mensaje: {str(e)}")
        return False
