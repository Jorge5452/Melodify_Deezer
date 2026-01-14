# -*- coding: utf-8 -*-
"""
Audio file sender and vault integration.

Handles sending audio files to users and saving them to vault for caching.
"""

import logging
import os
import asyncio
import random
import requests
from io import BytesIO

from telegram.error import TimedOut, NetworkError, RetryAfter

from src.config import (
    HTTP_CONNECT_TIMEOUT, 
    HTTP_READ_TIMEOUT, 
    HTTP_WRITE_TIMEOUT,
    MAX_RETRIES,
    INITIAL_RETRY_DELAY,
    RETRY_BACKOFF_FACTOR
)
from src.core.services.vault_service import add_to_vault
from src.interface.telegram.utils.helpers import retry_async_operation


async def send_and_save_audio(context, chat_id, file_path, caption, vault_chat_id, key, 
                              dz=None, track_id=None, send_to_user=False):
    """
    Sends an audio file and saves it to vault.
    
    Args:
        context: Bot context
        chat_id: Chat ID to send audio
        file_path: Path to local file
        caption: Description
        vault_chat_id: Chat ID for storing audio
        key: Vault key
        dz: Deezer object (optional)
        track_id: Deezer track ID (optional)
        send_to_user: If True, also sends to user (default False)
    
    Returns:
        The file_id of the sent audio
    """
    try:
        # Extract metadata if possible
        title = None
        performer = None
        duration = None
        thumbnail = None
        
        # Try to get metadata from Deezer
        if dz and track_id and str(track_id).isdigit():
            try:
                track_info = dz.api.get_track(track_id)
                if track_info:
                    title = track_info.get('title')
                    performer = track_info.get('artist', {}).get('name')
                    duration = track_info.get('duration')
                    
                    album_info = track_info.get('album', {})
                    cover_url = album_info.get('cover_medium') or album_info.get('cover_small')
                    
                    if cover_url:
                        response = requests.get(cover_url)
                        if response.status_code == 200:
                            thumbnail = BytesIO(response.content)
                            thumbnail.name = "cover.jpg"
            except Exception as e:
                logging.warning(f"Could not get Deezer metadata: {str(e)}")
        
        # Extract info from filename if no metadata
        if not title or not performer:
            filename = os.path.basename(file_path)
            filename_no_ext = os.path.splitext(filename)[0]
            
            if " - " in filename_no_ext:
                parts = filename_no_ext.split(" - ", 1)
                if not performer:
                    performer = parts[0].strip()
                if not title:
                    title = parts[1].strip()
            else:
                if not title:
                    title = filename_no_ext
        
        # Send to vault with retries
        with open(file_path, "rb") as f:
            send_kwargs = {
                "chat_id": vault_chat_id,
                "audio": f,
                "caption": caption,
                "title": title,
                "performer": performer
            }
            
            if duration:
                send_kwargs["duration"] = duration
                
            if thumbnail:
                send_kwargs["thumbnail"] = thumbnail
                
            async def send_with_file_reset(func, **kwargs):
                delay = INITIAL_RETRY_DELAY
                last_exception = None
                
                for attempt in range(MAX_RETRIES + 1):
                    try:
                        f.seek(0)
                        return await func(**kwargs)
                    except (TimedOut, NetworkError) as e:
                        last_exception = e
                        if attempt < MAX_RETRIES:
                            jitter_value = random.uniform(-0.1, 0.1) * delay
                            current_delay = delay + jitter_value
                            
                            logging.warning(
                                f"Attempt {attempt+1}/{MAX_RETRIES+1} failed sending audio: {str(e)}. "
                                f"Retrying in {current_delay:.2f}s"
                            )
                            await asyncio.sleep(current_delay)
                            delay *= RETRY_BACKOFF_FACTOR
                    except RetryAfter as e:
                        last_exception = e
                        if attempt < MAX_RETRIES:
                            logging.warning(f"Rate limit. Waiting {e.retry_after}s.")
                            await asyncio.sleep(e.retry_after)
                    except Exception as e:
                        logging.error(f"Unrecoverable error in attempt {attempt+1}: {str(e)}")
                        raise

                raise last_exception

            try:
                sent_message = await send_with_file_reset(
                    context.bot.send_audio,
                    **send_kwargs
                )
            except (TimedOut, NetworkError) as e:
                logging.error(f"Error after {MAX_RETRIES+1} attempts sending audio: {str(e)}")
                logging.info("Trying simplified send without metadata...")
                simple_kwargs = {
                    "chat_id": vault_chat_id,
                    "audio": f,
                    "caption": caption
                }
                f.seek(0)
                sent_message = await send_with_file_reset(
                   context.bot.send_audio,
                   **simple_kwargs
                )
        
        file_id = sent_message.audio.file_id
        
        # Send to user only if explicitly requested
        if send_to_user and chat_id != vault_chat_id:
            await retry_async_operation(
                context.bot.send_audio,
                max_retries=MAX_RETRIES,
                initial_delay=INITIAL_RETRY_DELAY,
                backoff_factor=RETRY_BACKOFF_FACTOR,
                chat_id=chat_id,
                audio=file_id
            )
        
        return file_id
    except Exception as e:
        logging.error(f"Error sending audio: {str(e)}", exc_info=True)
        raise
