import logging
import asyncio
from typing import List, Union
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaAudio
from telegram.ext import ContextTypes

# Clases para simular objetos de Telegram
class SimulatedUser:
    def __init__(self, user_id):
        self.id = user_id

class SimulatedMessage:
    def __init__(self, chat_id, text):
        self.chat_id = chat_id
        self.text = text
        
    async def reply_text(self, text, **kwargs):
        # Se debe proporcionar context al usar esta función
        return await self._context.bot.send_message(chat_id=self.chat_id, text=text, **kwargs)
        
    async def reply_audio(self, **kwargs):
        # Se debe proporcionar context al usar esta función
        return await self._context.bot.send_audio(chat_id=self.chat_id, **kwargs)
    
class SimulatedUpdate:
    def __init__(self, chat_id, user_id, text, context):
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
async def safe_edit_message(message, text):
    """
    Edita un mensaje de forma segura, capturando el error si el contenido no cambia.
    
    Args:
        message: Objeto Message de Telegram
        text: Nuevo texto para el mensaje
    """
    try:
        await message.edit_text(text)
    except Exception as e:
        # Ignorar error específico de mensaje no modificado
        if "Message is not modified" not in str(e):
            logging.error(f"Error editando mensaje: {str(e)}")
