"""
Decoradores para funciones del bot Melodify Deluxe.

Este módulo proporciona decoradores que encapsulan patrones comunes usados
en los handlers del bot, como la gestión de sesiones de usuario, limitación
de tasa y manejo de errores.
"""

import logging
import time
import functools
import asyncio
from typing import Any, Callable, Awaitable, Optional, TypeVar, cast

from telegram import Update, CallbackQuery
from telegram.ext import ContextTypes

from user_session import UserSession

F = TypeVar('F', bound=Callable[..., Any])

def with_user_session(func: F) -> F:
    """
    Decorador que gestiona automáticamente la obtención y actualización de la sesión de usuario.
    
    Este decorador obtiene el ID del usuario desde el objeto Update, recupera o crea
    una sesión de usuario y actualiza su timestamp de actividad antes de llamar a la
    función decorada.
    
    Args:
        func: Función asíncrona que maneja un comando o mensaje de Telegram
        
    Returns:
        Función envuelta que incluye gestión de sesiones
    """
    @functools.wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args: Any, **kwargs: Any) -> Any:
        # Obtener el ID del usuario
        user_id = None
        
        if update.effective_user:
            user_id = update.effective_user.id
        elif update.callback_query and update.callback_query.from_user:
            user_id = update.callback_query.from_user.id
        
        if user_id:
            # Obtener o crear sesión de usuario
            session = UserSession.get_session(user_id)
            # Actualizar timestamp de actividad
            session.update_activity()
            
            # Guardar la sesión en el contexto para que esté disponible en la función
            if not hasattr(context, 'user_data'):
                context.user_data = {}
            context.user_data['session'] = session
            
        # Llamar a la función original
        return await func(update, context, *args, **kwargs)
    
    return cast(F, wrapper)

def with_rate_limiting(func: F) -> F:
    """
    Decorador que aplica limitación de tasa a la función decorada.
    
    Este decorador obtiene la sesión de usuario y espera hasta que
    se pueda procesar una nueva solicitud según la configuración
    de limitación de tasa.
    
    Args:
        func: Función asíncrona que maneja un comando o mensaje de Telegram
        
    Returns:
        Función envuelta que incluye limitación de tasa
    """
    @functools.wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args: Any, **kwargs: Any) -> Any:
        # Obtener el ID del usuario
        user_id = None
        
        if update.effective_user:
            user_id = update.effective_user.id
        elif update.callback_query and update.callback_query.from_user:
            user_id = update.callback_query.from_user.id
        
        if user_id:
            # Obtener sesión de usuario
            session = UserSession.get_session(user_id)
            
            # Esperar a que se libere el límite de tasa
            logging.info(f"[RATE_LIMIT] Esperando límite de tasa para usuario: {user_id}")
            await session.wait_for_rate_limit()
            logging.info(f"[RATE_LIMIT] Límite de tasa liberado para usuario: {user_id}")
        
        # Llamar a la función original
        return await func(update, context, *args, **kwargs)
    
    return cast(F, wrapper)

def with_error_handling(func: F) -> F:
    """
    Decorador que proporciona manejo de errores estándar para funciones del bot.
    
    Este decorador captura las excepciones que ocurren durante la ejecución
    de la función decorada, las registra en el log y envía un mensaje de error
    al usuario.
    
    Args:
        func: Función asíncrona que maneja un comando o mensaje de Telegram
        
    Returns:
        Función envuelta que incluye manejo de errores
    """
    @functools.wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args: Any, **kwargs: Any) -> Any:
        try:
            # Obtener información para logging
            user_id = "desconocido"
            command = ""
            
            # Manejar tanto actualizaciones regulares como callbacks
            if update.effective_user:
                user_id = update.effective_user.id
            elif update.callback_query and update.callback_query.from_user:
                user_id = update.callback_query.from_user.id
            
            if update.message and update.message.text:
                command = update.message.text
            elif update.callback_query:
                command = f"callback: {update.callback_query.data}"
            
            logging.info(f"[COMANDO] Recibido: {command} de usuario: {user_id} - timestamp: {time.time()}")
            
            # Ejecutar la función original
            result = await func(update, context, *args, **kwargs)
            
            logging.info(f"[COMANDO] Completado: {command} de usuario: {user_id}")
            return result
            
        except Exception as e:
            # Registrar el error
            logging.error(f"Error al procesar {update}: {str(e)}", exc_info=True)
            
            # Notificar al usuario - manejar tanto mensajes regulares como callbacks
            message = None
            if update.effective_message:
                message = update.effective_message
            elif update.callback_query and update.callback_query.message:
                message = update.callback_query.message
                
            if message:
                await message.reply_text(
                    "❌ Algo salió mal. Inténtalo de nuevo por favor."
                )
            
            # Re-lanzar la excepción para manejo adicional si es necesario
            raise
    
    return cast(F, wrapper)

def with_callback_error_handling(func: F) -> F:
    """
    Decorador especializado para manejar errores en funciones que procesan CallbackQuery.
    
    Este decorador es similar a with_error_handling pero está diseñado para funciones
    que reciben directamente un objeto CallbackQuery en lugar de un Update completo.
    
    Args:
        func: Función asíncrona que maneja un callback query de Telegram
        
    Returns:
        Función envuelta que incluye manejo de errores
    """
    @functools.wraps(func)
    async def wrapper(query: CallbackQuery, context: ContextTypes.DEFAULT_TYPE, *args: Any, **kwargs: Any) -> Any:
        try:
            # Obtener información para logging
            user_id = query.from_user.id if query.from_user else "desconocido"
            command = f"callback: {query.data}" if query.data else "callback desconocido"
            
            logging.info(f"[COMANDO] Recibido: {command} de usuario: {user_id} - timestamp: {time.time()}")
            
            # Ejecutar la función original
            result = await func(query, context, *args, **kwargs)
            
            logging.info(f"[COMANDO] Completado: {command} de usuario: {user_id}")
            return result
            
        except Exception as e:
            # Registrar el error
            logging.error(f"Error al procesar callback query {query}: {str(e)}", exc_info=True)
            
            # Notificar al usuario si es posible
            if query.message:
                await query.message.reply_text(
                    "❌ Algo salió mal. Inténtalo de nuevo por favor."
                )
            
            # Re-lanzar la excepción para manejo adicional si es necesario
            raise
    
    return cast(F, wrapper)

def with_callback_user_session(func: F) -> F:
    """
    Decorador especializado para gestionar sesiones de usuario en funciones que procesan CallbackQuery.
    
    Args:
        func: Función asíncrona que maneja un callback query de Telegram
        
    Returns:
        Función envuelta que incluye gestión de sesiones
    """
    @functools.wraps(func)
    async def wrapper(query: CallbackQuery, context: ContextTypes.DEFAULT_TYPE, *args: Any, **kwargs: Any) -> Any:
        # Obtener el ID del usuario
        user_id = query.from_user.id if query.from_user else None
        
        if user_id:
            # Obtener o crear sesión de usuario
            session = UserSession.get_session(user_id)
            # Actualizar timestamp de actividad
            session.update_activity()
            
            # Guardar la sesión en el contexto para que esté disponible en la función
            if not hasattr(context, 'user_data'):
                context.user_data = {}
            context.user_data['session'] = session
            
        # Llamar a la función original
        return await func(query, context, *args, **kwargs)
    
    return cast(F, wrapper)

def combined_decorator(func: F) -> F:
    """
    Decorador combinado que aplica gestión de sesiones, limitación de tasa y manejo de errores.
    
    Este decorador es una conveniencia que combina los tres decoradores principales
    en uno solo para simplificar la decoración de funciones.
    
    Args:
        func: Función asíncrona que maneja un comando o mensaje de Telegram
        
    Returns:
        Función envuelta con todas las funcionalidades
    """
    @with_error_handling
    @with_rate_limiting
    @with_user_session
    @functools.wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args: Any, **kwargs: Any) -> Any:
        return await func(update, context, *args, **kwargs)
    
    return cast(F, wrapper)

def combined_callback_decorator(func: F) -> F:
    """
    Decorador combinado para funciones que manejan CallbackQuery directamente.
    
    Este decorador aplica manejo de errores y gestión de sesiones adaptados para
    funciones que reciben directamente un objeto CallbackQuery.
    
    Args:
        func: Función asíncrona que maneja un callback query de Telegram
        
    Returns:
        Función envuelta con todas las funcionalidades
    """
    @with_callback_error_handling
    @with_callback_user_session
    @functools.wraps(func)
    async def wrapper(query: CallbackQuery, context: ContextTypes.DEFAULT_TYPE, *args: Any, **kwargs: Any) -> Any:
        return await func(query, context, *args, **kwargs) 