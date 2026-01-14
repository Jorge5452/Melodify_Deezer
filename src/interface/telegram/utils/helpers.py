# -*- coding: utf-8 -*-
"""
Utility functions and classes for the Melodify Deluxe Telegram bot.

Provides simulated Telegram objects for testing and internal processing,
as well as helper functions for safe message editing and retry logic.
"""

import logging
import asyncio
import random
from typing import Callable, TypeVar, Awaitable, Any

from telegram import Message
from telegram.ext import ContextTypes
from telegram.error import TimedOut, RetryAfter, NetworkError


# Define type for generic async functions
T = TypeVar('T')



class SimulatedUser:
    """
    Simulates a Telegram User object for tests and internal processing.
    
    This class provides a Telegram user-like object with
    basic properties needed to simulate interactions.
    
    Attributes:
        id (int): The unique user ID
    """
    def __init__(self, user_id: int) -> None:
        """
        Initializes a simulated user with a specific ID.
        
        Args:
            user_id: The user ID to assign
        """
        self.id = user_id


class SimulatedMessage:
    """
    Simulates a Telegram Message object for tests and internal processing.
    
    This class allows creating simulated messages that can be used in
    functions expecting Telegram Message objects, facilitating tests
    and request processing without a real message.
    
    Attributes:
        chat_id (int): The chat ID where the message would be sent
        text (str): The message text
        _context (ContextTypes.DEFAULT_TYPE): Bot context needed for sending messages
    """
    def __init__(self, chat_id: int, text: str) -> None:
        """
        Initializes a simulated message.
        
        Args:
            chat_id: Chat ID where the message is simulated
            text: Simulated message text
        """
        self.chat_id = chat_id
        self.text = text
        self._context = None
        
    async def reply_text(self, text: str, **kwargs) -> Message:
        """
        Simulates replying to a message with text.
        
        Sends a message through the bot context to the same chat_id.
        
        Args:
            text: Text to send as reply
            **kwargs: Additional arguments for send_message
            
        Returns:
            Message: The Message object returned by telegram
            
        Note:
            _context must be provided before using this method
        """
        return await self._context.bot.send_message(chat_id=self.chat_id, text=text, **kwargs)
        
    async def reply_audio(self, **kwargs) -> Message:
        """
        Simulates sending an audio file as reply.
        
        Args:
            **kwargs: Arguments for send_audio
            
        Returns:
            Message: The Message object returned by telegram
            
        Note:
            _context must be provided before using this method
        """
        return await self._context.bot.send_audio(chat_id=self.chat_id, **kwargs)


class SimulatedUpdate:
    """
    Simulates a Telegram Update object to facilitate testing and code reuse.
    
    This class allows creating an object that mimics Telegram Update behavior,
    especially useful for reusing functions that process messages or updates.
    
    Attributes:
        message (SimulatedMessage): The simulated message
        effective_user (SimulatedUser): The simulated user
        progress_message: Pre-existing progress message (optional)
    """
    def __init__(self, chat_id: int, user_id: int, text: str, context: ContextTypes.DEFAULT_TYPE) -> None:
        """
        Initializes a simulated update.
        
        Args:
            chat_id: Chat ID where the update is simulated
            user_id: User ID who simulates sending the message
            text: Simulated message text
            context: Bot context needed for sending messages
        """
        self.message = SimulatedMessage(chat_id, text)
        self.effective_user = SimulatedUser(user_id)
        # Provide context to SimulatedMessage
        self.message._context = context
        # Progress message (if reusing an existing message)
        self.progress_message = None
        # Flag to indicate if this update comes from a search callback
        self.from_search_callback = False


def create_simulated_update(query, context, url, progress_message=None, from_search=True):
    """
    Creates a simulated Update object from a callback query.
    
    Args:
        query: Telegram CallbackQuery object
        context: Bot context
        url: URL to include as message text
        progress_message: Existing progress message (optional)
        from_search: Indicates if update comes from a search callback
    
    Returns:
        SimulatedUpdate object for use in message handling functions
    """
    chat_id = query.message.chat_id
    user_id = query.from_user.id
    update = SimulatedUpdate(chat_id, user_id, url, context)
    
    # If a progress message is provided, associate it with the update
    if progress_message:
        update.progress_message = progress_message
    
    # Mark this update as coming from a search
    update.from_search_callback = from_search
    
    return update


async def retry_async_operation(
    func: Callable[..., Awaitable[T]], 
    max_retries: int = 3, 
    initial_delay: float = 1.0, 
    jitter: float = 0.1,
    backoff_factor: float = 2.0,
    *args: Any, 
    **kwargs: Any
) -> T:
    """
    Executes an async operation with automatic retries and exponential backoff.
    
    This function is useful for network operations that can fail temporarily,
    like sending files to Telegram or external API requests.
    
    Args:
        func: Async function to execute
        max_retries: Maximum number of retries (default: 3)
        initial_delay: Initial wait time in seconds (default: 1.0)
        jitter: Randomness factor to avoid retry storms (default: 0.1)
        backoff_factor: Factor to increase wait time (default: 2.0)
        *args, **kwargs: Arguments to pass to the function
        
    Returns:
        The result of the successfully executed function
        
    Raises:
        Exception: Re-raises the last exception after exhausting retries
    """
    delay = initial_delay
    last_exception = None
    
    # Try the operation up to max_retries times
    for attempt in range(max_retries + 1):
        try:
            # Execute the function
            return await func(*args, **kwargs)
            
        except (TimedOut, NetworkError) as e:
            last_exception = e
            # Only log and retry if not the last attempt
            if attempt < max_retries:
                # Add jitter to avoid retry synchronization
                jitter_value = random.uniform(-jitter, jitter) * delay
                current_delay = delay + jitter_value
                
                logging.warning(
                    f"Attempt {attempt+1}/{max_retries+1} failed with error: {str(e)}. "
                    f"Retrying in {current_delay:.2f}s"
                )
                
                # Wait before next attempt
                await asyncio.sleep(current_delay)
                
                # Increase wait time for next retry
                delay *= backoff_factor
                
        except RetryAfter as e:
            last_exception = e
            # For RetryAfter, wait the specific time indicated by Telegram
            retry_after = e.retry_after
            
            if attempt < max_retries:
                logging.warning(
                    f"Rate limit reached. Attempt {attempt+1}/{max_retries+1} failed. "
                    f"Waiting {retry_after}s as indicated by Telegram"
                )
                
                await asyncio.sleep(retry_after)
                
        except Exception as e:
            # For other errors, don't retry
            logging.error(f"Non-recoverable error in attempt {attempt+1}: {str(e)}")
            raise
    
    # If we get here, retries were exhausted
    logging.error(f"Operation failed after {max_retries+1} attempts: {str(last_exception)}")
    raise last_exception

