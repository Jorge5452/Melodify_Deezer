import logging
import asyncio
import random
from typing import List, Union, Optional, Any, Dict, Callable, TypeVar, Awaitable
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaAudio, Message
from telegram.ext import ContextTypes
from telegram.error import TimedOut, RetryAfter, NetworkError

# Define el tipo para funciones asíncronas genéricas
T = TypeVar('T')

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

async def retry_async_operation(func: Callable[..., Awaitable[T]], 
                               max_retries: int = 3, 
                               initial_delay: float = 1.0, 
                               jitter: float = 0.1,
                               backoff_factor: float = 2.0,
                               *args: Any, 
                               **kwargs: Any) -> T:
    """
    Ejecuta una operación asíncrona con reintentos automáticos y backoff exponencial.
    
    Esta función es útil para operaciones de red que pueden fallar temporalmente,
    como envíos de archivos a Telegram o peticiones a APIs externas.
    
    Args:
        func: Función asíncrona a ejecutar
        max_retries: Número máximo de reintentos (default: 3)
        initial_delay: Tiempo de espera inicial en segundos (default: 1.0)
        jitter: Factor de aleatoriedad para evitar tormentas de reintentos (default: 0.1)
        backoff_factor: Factor para incrementar el tiempo de espera (default: 2.0)
        *args, **kwargs: Argumentos para pasar a la función
        
    Returns:
        El resultado de la función ejecutada exitosamente
        
    Raises:
        Exception: Re-lanza la última excepción después de agotar los reintentos
    """
    delay = initial_delay
    last_exception = None
    
    # Intentar la operación hasta max_retries veces
    for attempt in range(max_retries + 1):
        try:
            # Ejecutar la función
            return await func(*args, **kwargs)
            
        except (TimedOut, NetworkError) as e:
            last_exception = e
            # Solo registrar el error y reintentar si no es el último intento
            if attempt < max_retries:
                # Añadir jitter para evitar sincronización de reintentos
                jitter_value = random.uniform(-jitter, jitter) * delay
                current_delay = delay + jitter_value
                
                logging.warning(
                    f"Intento {attempt+1}/{max_retries+1} falló con error: {str(e)}. "
                    f"Reintentando en {current_delay:.2f}s"
                )
                
                # Esperar antes del siguiente intento
                await asyncio.sleep(current_delay)
                
                # Incrementar el tiempo de espera para el próximo reintento
                delay *= backoff_factor
                
        except RetryAfter as e:
            last_exception = e
            # Para RetryAfter, esperar el tiempo específico indicado por Telegram
            retry_after = e.retry_after
            
            if attempt < max_retries:
                logging.warning(
                    f"Rate limit alcanzado. Intento {attempt+1}/{max_retries+1} falló. "
                    f"Esperando {retry_after}s según indicado por Telegram"
                )
                
                await asyncio.sleep(retry_after)
                
        except Exception as e:
            # Para otros errores, no reintentar
            logging.error(f"Error no recuperable en intento {attempt+1}: {str(e)}")
            raise
    
    # Si llegamos aquí, se agotaron los reintentos
    logging.error(f"Operación falló después de {max_retries+1} intentos: {str(last_exception)}")
    raise last_exception
