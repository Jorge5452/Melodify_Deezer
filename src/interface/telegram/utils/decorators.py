# -*- coding: utf-8 -*-
"""
Decorators for Melodify Deluxe bot functions.

This module provides decorators that encapsulate common patterns used
in bot handlers, such as user session management, rate limiting
and error handling.
"""

import logging
import time
import functools
from typing import Any, Callable, TypeVar, cast

from telegram import Update, CallbackQuery
from telegram.ext import ContextTypes

from src.core.services import UserSession

F = TypeVar('F', bound=Callable[..., Any])


def with_user_session(func: F) -> F:
    """
    Decorator that automatically manages user session retrieval and update.
    
    This decorator gets the user ID from the Update object, retrieves or creates
    a user session and updates its activity timestamp before calling the
    decorated function.
    
    Args:
        func: Async function that handles a Telegram command or message
        
    Returns:
        Wrapped function with session management included
    """
    @functools.wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args: Any, **kwargs: Any) -> Any:
        # Get user ID
        user_id = None
        
        if update.effective_user:
            user_id = update.effective_user.id
        elif update.callback_query and update.callback_query.from_user:
            user_id = update.callback_query.from_user.id
        
        if user_id:
            # Get or create user session
            session = UserSession.get_session(user_id)
            # Update activity timestamp
            session.update_activity()
            
            # Store session in context for availability in the function
            if not hasattr(context, 'user_data'):
                context.user_data = {}
            context.user_data['session'] = session
            
        # Call original function
        return await func(update, context, *args, **kwargs)
    
    return cast(F, wrapper)


def with_rate_limiting(func: F) -> F:
    """
    Decorator that applies rate limiting to the decorated function.
    
    This decorator gets the user session and waits until
    a new request can be processed according to the rate limiting
    configuration.
    
    Args:
        func: Async function that handles a Telegram command or message
        
    Returns:
        Wrapped function with rate limiting included
    """
    @functools.wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args: Any, **kwargs: Any) -> Any:
        # Get user ID
        user_id = None
        
        if update.effective_user:
            user_id = update.effective_user.id
        elif update.callback_query and update.callback_query.from_user:
            user_id = update.callback_query.from_user.id
        
        if user_id:
            # Get user session
            session = UserSession.get_session(user_id)
            
            # Wait for rate limit to be released
            logging.info(f"[RATE_LIMIT] Waiting for rate limit for user: {user_id}")
            await session.wait_for_rate_limit()
            logging.info(f"[RATE_LIMIT] Rate limit released for user: {user_id}")
        
        # Call original function
        return await func(update, context, *args, **kwargs)
    
    return cast(F, wrapper)


def with_error_handling(func: F) -> F:
    """
    Decorator that provides standard error handling for bot functions.
    
    This decorator captures exceptions that occur during execution
    of the decorated function, logs them and sends an error message
    to the user.
    
    Args:
        func: Async function that handles a Telegram command or message
        
    Returns:
        Wrapped function with error handling included
    """
    @functools.wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args: Any, **kwargs: Any) -> Any:
        try:
            # Get info for logging
            user_id = "unknown"
            command = ""
            
            # Handle both regular updates and callbacks
            if update.effective_user:
                user_id = update.effective_user.id
            elif update.callback_query and update.callback_query.from_user:
                user_id = update.callback_query.from_user.id
            
            if update.message and update.message.text:
                command = update.message.text
            elif update.callback_query:
                command = f"callback: {update.callback_query.data}"
            
            logging.info(f"[COMMAND] Received: {command} from user: {user_id} - timestamp: {time.time()}")
            
            # Execute original function
            result = await func(update, context, *args, **kwargs)
            
            logging.info(f"[COMMAND] Completed: {command} from user: {user_id}")
            return result
            
        except Exception as e:
            # Log the error
            logging.error(f"Error processing {update}: {str(e)}", exc_info=True)
            
            # Notify user - handle both regular messages and callbacks
            message = None
            if update.effective_message:
                message = update.effective_message
            elif update.callback_query and update.callback_query.message:
                message = update.callback_query.message
                
            if message:
                await message.reply_text(
                    "❌ Something went wrong. Please try again."
                )
            
            # Re-raise exception for additional handling if needed
            raise
    
    return cast(F, wrapper)


def with_callback_error_handling(func: F) -> F:
    """
    Specialized decorator for error handling in functions that process CallbackQuery.
    
    This decorator is similar to with_error_handling but is designed for functions
    that receive a CallbackQuery object directly instead of a full Update.
    
    Args:
        func: Async function that handles a Telegram callback query
        
    Returns:
        Wrapped function with error handling included
    """
    @functools.wraps(func)
    async def wrapper(query: CallbackQuery, context: ContextTypes.DEFAULT_TYPE, *args: Any, **kwargs: Any) -> Any:
        try:
            # Get info for logging
            user_id = query.from_user.id if query.from_user else "unknown"
            command = f"callback: {query.data}" if query.data else "unknown callback"
            
            logging.info(f"[COMMAND] Received: {command} from user: {user_id} - timestamp: {time.time()}")
            
            # Execute original function
            result = await func(query, context, *args, **kwargs)
            
            logging.info(f"[COMMAND] Completed: {command} from user: {user_id}")
            return result
            
        except Exception as e:
            # Log the error
            logging.error(f"Error processing callback query {query}: {str(e)}", exc_info=True)
            
            # Notify user if possible
            if query.message:
                await query.message.reply_text(
                    "❌ Something went wrong. Please try again."
                )
            
            # Re-raise exception for additional handling if needed
            raise
    
    return cast(F, wrapper)


def with_callback_user_session(func: F) -> F:
    """
    Specialized decorator for managing user sessions in CallbackQuery functions.
    
    Args:
        func: Async function that handles a Telegram callback query
        
    Returns:
        Wrapped function with session management included
    """
    @functools.wraps(func)
    async def wrapper(query: CallbackQuery, context: ContextTypes.DEFAULT_TYPE, *args: Any, **kwargs: Any) -> Any:
        # Get user ID
        user_id = query.from_user.id if query.from_user else None
        
        if user_id:
            # Get or create user session
            session = UserSession.get_session(user_id)
            # Update activity timestamp
            session.update_activity()
            
            # Store session in context for availability in the function
            if not hasattr(context, 'user_data'):
                context.user_data = {}
            context.user_data['session'] = session
            
        # Call original function
        return await func(query, context, *args, **kwargs)
    
    return cast(F, wrapper)


def combined_decorator(func: F) -> F:
    """
    Combined decorator that applies session management, rate limiting and error handling.
    
    This decorator is a convenience that combines the three main decorators
    into one to simplify function decoration.
    
    Args:
        func: Async function that handles a Telegram command or message
        
    Returns:
        Wrapped function with all functionalities
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
    Combined decorator for functions that handle CallbackQuery directly.
    
    This decorator applies error handling and session management adapted for
    functions that receive a CallbackQuery object directly.
    
    Args:
        func: Async function that handles a Telegram callback query
        
    Returns:
        Wrapped function with all functionalities
    """
    @with_callback_error_handling
    @with_callback_user_session
    @functools.wraps(func)
    async def wrapper(query: CallbackQuery, context: ContextTypes.DEFAULT_TYPE, *args: Any, **kwargs: Any) -> Any:
        return await func(query, context, *args, **kwargs)
    
    return cast(F, wrapper)
