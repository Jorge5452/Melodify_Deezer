# -*- coding: utf-8 -*-
"""
Collection processor for albums and playlists.

Handles downloading and processing album and playlist collections.
"""

import logging
import os
import asyncio
import requests
from io import BytesIO
from typing import List, Tuple, Any, Optional

from telegram import InputMediaAudio
from telegram.error import TimedOut, NetworkError

from src.config import BATCH_SIZE
from src.infrastructure.deezer import download_track, TrackPreviewUnavailableError
from src.core.services.vault_service import add_to_vault, get_from_vault
from src.core.services import UserSession
from src.interface.telegram.handlers.audio import send_and_save_audio
from src.interface.telegram.handlers.messages import safe_edit_message
from src.interface.telegram.utils.helpers import retry_async_operation


class CollectionProcessingError(Exception):
    """Base exception for collection processing errors."""
    pass


class EmptyCollectionError(CollectionProcessingError):
    """Exception raised when a collection contains no tracks."""
    pass


class TrackNotAvailableError(CollectionProcessingError):
    """Exception raised when a track is not available."""
    pass


async def process_collection(update, context, url, content_type, content_id, dz, settings, 
                            vault_chat_id, listener, progress_message=None):
    """Processes downloading an album or playlist."""
    user_id = update.effective_user.id
    session = UserSession.get_session(user_id)
    
    cache_key = f"{content_type}_{content_id}"
    cached_data = get_from_vault(cache_key)
    
    if content_type != "playlist" and content_type != "album" and cached_data and isinstance(cached_data, list):
        for file_id in cached_data:
            await update.message.reply_audio(audio=file_id)
        session.active_downloads = max(0, session.active_downloads - 1)
        session.mark_as_changed()
        return
    
    status_message = None
    if progress_message:
        status_message = progress_message.message
    else:
        status_message = await update.message.reply_text(f"⏳ Buscando {content_type}...")
    
    try:
        collection_info = await get_collection_info(dz, content_type, content_id)
        
        if not collection_info:
            await status_message.edit_text(f"❌ No encuentro este {content_type}. ¿El enlace es correcto?")
            return
        
        track_urls, track_ids, track_titles = await extract_tracks_info(collection_info, dz)
        
        if not track_urls:
            if content_type == "album":
                message = f"❌ Este álbum no tiene canciones disponibles"
            else:
                message = f"❌ Esta playlist está vacía o sus canciones no están disponibles"
            
            await status_message.edit_text(message)
            return
        
        total_tracks = len(track_urls)
        logging.info(f"Tracks found in {content_type}: {total_tracks}")
        
        await send_collection_preview(update, context, collection_info, content_type, total_tracks)
        await status_message.edit_text(f"⏳ Preparando {total_tracks} canciones...")
        
        if total_tracks > BATCH_SIZE:
            await process_playlist_in_batches(update, context, track_urls, track_ids, track_titles, 
                                             dz, settings, listener, vault_chat_id, 
                                             status_message, cache_key, content_type)
        else:
            await process_small_collection(update, context, track_urls, track_ids, track_titles,
                                          total_tracks, dz, settings, listener, vault_chat_id,
                                          status_message, cache_key, content_type)
    
    except EmptyCollectionError:
        await status_message.edit_text(f"❌ No hay canciones disponibles")
    except requests.exceptions.RequestException as e:
        await status_message.edit_text(f"❌ Problemas de conexión. Inténtalo más tarde")
        logging.error(f"Connection error in {content_type}: {str(e)}", exc_info=True)
    except Exception as e:
        logging.error(f"Error processing {content_type}: {str(e)}", exc_info=True)
        await status_message.edit_text(f"❌ No pude procesar este {content_type}")
    finally:
        session.active_downloads = max(0, session.active_downloads - 1)
        session.mark_as_changed()


async def get_collection_info(dz, content_type: str, content_id: str) -> Optional[dict]:
    """Gets information about an album or playlist."""
    try:
        if content_type == "album":
            result = dz.api.get_album(content_id)
        else:
            result = dz.api.get_playlist(content_id)
        
        if not result:
            raise EmptyCollectionError(f"Could not find {content_type}")
        
        return result
    except Exception as e:
        logging.error(f"Error getting {content_type} info: {str(e)}", exc_info=True)
        raise


async def extract_tracks_info(collection_info: dict, dz) -> Tuple[List[str], List[str], List[str]]:
    """Extracts track information from an album or playlist."""
    track_urls = []
    track_ids = []
    track_titles = []
    
    try:
        tracks_data = collection_info.get('tracks', {})
        tracks = tracks_data.get('data', [])
        for track in tracks:
            track_id = track.get('id')
            if track_id:
                track_urls.append(f"https://www.deezer.com/track/{track_id}")
                track_ids.append(str(track_id))
                artist_name = track.get('artist', {}).get('name', 'Desconocido')
                track_title = track.get('title', 'Sin título')
                track_titles.append(f"{artist_name} - {track_title}")
        
        total_album_tracks = collection_info.get('nb_tracks')
        album_id = collection_info.get('id')

        next_url = tracks_data.get('next')
        if total_album_tracks and total_album_tracks > len(track_urls) and not next_url:
            next_url = f"https://api.deezer.com/album/{album_id}/tracks?index={len(track_urls)}"

        while next_url and (not total_album_tracks or len(track_urls) < total_album_tracks):
            response = requests.get(next_url)
            if response.status_code == 200:
                tracks_data = response.json()
                tracks = tracks_data.get('data', [])
                for track in tracks:
                    track_id = track.get('id')
                    if track_id:
                        track_urls.append(f"https://www.deezer.com/track/{track_id}")
                        track_ids.append(str(track_id))
                        artist_name = track.get('artist', {}).get('name', 'Desconocido')
                        track_title = track.get('title', 'Sin título')
                        track_titles.append(f"{artist_name} - {track_title}")
                next_url = tracks_data.get('next')
                if not next_url and total_album_tracks and len(track_urls) < total_album_tracks:
                    next_url = f"https://api.deezer.com/album/{album_id}/tracks?index={len(track_urls)}"
            else:
                break
    except Exception as e:
        logging.warning(f"Could not get track list: {str(e)}")
        
    return track_urls, track_ids, track_titles


async def send_collection_preview(update, context, collection_info: dict, content_type: str, total_tracks: int):
    """Sends a preview of the playlist or album with cover and info."""
    try:
        image_url = None
        title = collection_info.get('title', 'Sin título')
        
        if content_type == 'album':
            image_url = collection_info.get('cover_big') or collection_info.get('cover_medium')
            artist_name = collection_info.get('artist', {}).get('name', 'Artista desconocido')
            caption = f"🎵 Álbum: {title}\n👤 Artista: {artist_name}\n🔢 Pistas: {total_tracks}"
        else:
            image_url = collection_info.get('picture_big') or collection_info.get('picture_medium')
            creator = collection_info.get('creator', {}).get('name', 'Creador desconocido')
            caption = f"🎵 Playlist: {title}\n👤 Creador: {creator}\n🔢 Pistas: {total_tracks}"
        
        if not image_url:
            await update.message.reply_text(caption)
            return
        
        response = requests.get(image_url)
        if response.status_code != 200:
            await update.message.reply_text(caption)
            return
        
        image_data = BytesIO(response.content)
        image_data.name = f"{content_type}_cover.jpg"
        
        await context.bot.send_photo(
            chat_id=update.message.chat_id,
            photo=image_data,
            caption=caption
        )
        
    except Exception as e:
        logging.error(f"Error sending preview: {str(e)}", exc_info=True)
        try:
            await update.message.reply_text(f"🎵 {content_type.title()}: {collection_info.get('title', 'Sin título')}\n🔢 Pistas: {total_tracks}")
        except:
            pass


async def process_playlist_in_batches(update, context, track_urls, track_ids, track_titles, 
                                     dz, settings, listener, vault_chat_id, 
                                     status_message, cache_key, content_type):
    """Processes a large playlist in batches."""
    total_tracks = len(track_urls)
    total_batches = (total_tracks + BATCH_SIZE - 1) // BATCH_SIZE
    
    file_ids_all = []
    successful_tracks = 0
    failed_tracks = 0
    last_status_text = ""
    skipped_tracks = []
    
    await safe_edit_message(status_message, 
        f"⏳ Descargando: 0/{total_tracks}\n"
        f"Procesando lote 1/{total_batches}"
    )
    
    for batch_num in range(total_batches):
        start_idx = batch_num * BATCH_SIZE
        end_idx = min(start_idx + BATCH_SIZE, total_tracks)
        
        batch_urls = track_urls[start_idx:end_idx]
        batch_ids = track_ids[start_idx:end_idx]
        batch_titles = track_titles[start_idx:end_idx]
        
        file_ids_batch = []
        
        for i, (track_url, track_id, track_title) in enumerate(zip(batch_urls, batch_ids, batch_titles)):
            try:
                global_idx = start_idx + i
                
                new_text = f"⏳ Descargando: {successful_tracks}/{total_tracks}\nProcesando: {track_title}"
                if new_text != last_status_text:
                    await safe_edit_message(status_message, new_text)
                    last_status_text = new_text
                
                bitrate = settings.get("maxBitrate", 3)
                individual_cache_key = f"{track_id}_{bitrate}"
                cached_file_id = get_from_vault(individual_cache_key)
                
                if cached_file_id:
                    file_ids_batch.append(cached_file_id)
                    file_ids_all.append(cached_file_id)
                    successful_tracks += 1
                    continue
                
                try:
                    file_path = await download_track(track_url, dz, settings, listener)
                except TrackPreviewUnavailableError:
                    logging.warning(f"Song without preview available: {track_id} - {track_title}")
                    skipped_tracks.append(f"• {track_title} - No disponible en Deezer")
                    await update.message.reply_text(f"⚠️ No pude conseguir: {track_title}")
                    failed_tracks += 1
                    continue
                except Exception as track_error:
                    error_msg = str(track_error)
                    logging.error(f"Error downloading track {track_id} ({track_title}): {error_msg}")
                    skipped_tracks.append(f"• {track_title} - Error")
                    await update.message.reply_text(f"⚠️ No pude descargar: {track_title}")
                    failed_tracks += 1
                    continue
                
                file_id = await send_and_save_audio(
                    context, 
                    vault_chat_id,
                    file_path, 
                    f"{content_type.title()} track {global_idx+1}/{total_tracks}: {track_title}", 
                    vault_chat_id, 
                    individual_cache_key,
                    dz=dz,
                    track_id=track_id
                )
                
                file_ids_batch.append(file_id)
                file_ids_all.append(file_id)
                add_to_vault(individual_cache_key, file_id)
                
                # Update user statistics
                try:
                    session.increment_downloads()
                except Exception as stats_error:
                    logging.error(f"[COLLECTION] Error updating stats for track {i+1}: {stats_error}")
                    
                successful_tracks += 1
                
                if os.path.exists(file_path):
                    os.remove(file_path)
                
            except Exception as e:
                logging.error(f"Error downloading track {start_idx+i+1}: {str(e)}", exc_info=True)
                failed_tracks += 1
                continue
        
        if file_ids_batch:
            try:
                await retry_async_operation(
                    context.bot.send_media_group,
                    max_retries=3,
                    initial_delay=2.0,
                    chat_id=update.message.chat_id,
                    media=[InputMediaAudio(media=file_id) for file_id in file_ids_batch]
                )
            except (TimedOut, NetworkError):
                for file_id in file_ids_batch:
                    try:
                        await context.bot.send_audio(chat_id=update.message.chat_id, audio=file_id)
                        await asyncio.sleep(0.5)
                    except:
                        pass
        
        if batch_num < total_batches - 1:
            await asyncio.sleep(3)
    
    if file_ids_all:
        add_to_vault(cache_key, file_ids_all)
        
        if failed_tracks > 0:
            skipped_info = "\n".join(skipped_tracks[:5])
            if len(skipped_tracks) > 5:
                skipped_info += f"\n... y {len(skipped_tracks) - 5} más"
            new_text = f"✅ ¡Listo! Conseguí {successful_tracks} de {total_tracks} canciones\n\n⚠️ No descargadas:\n{skipped_info}"
        else:
            new_text = f"✅ ¡Todo listo! Disfruta tus {successful_tracks} canciones"
        
        await safe_edit_message(status_message, new_text, parse_mode="Markdown")
    else:
        await safe_edit_message(status_message, f"❌ No pude descargar ninguna canción")
    
    return file_ids_all


async def process_small_collection(update, context, track_urls, track_ids, track_titles,
                                  total_tracks, dz, settings, listener, vault_chat_id,
                                  status_message, cache_key, content_type):
    """Processes a small collection of tracks."""
    file_ids_all = []
    file_ids_batch = []
    successful_tracks = 0
    failed_tracks = 0
    last_status_text = ""
    skipped_tracks = []
    
    await safe_edit_message(status_message, f"⏳ Descargando: 0/{total_tracks}")
    
    for i, (track_url, track_id, track_title) in enumerate(zip(track_urls, track_ids, track_titles)):
        try:
            new_text = f"⏳ Progreso: {successful_tracks}/{total_tracks}\nProcesando: {track_title}"
            if new_text != last_status_text:
                await safe_edit_message(status_message, new_text)
                last_status_text = new_text
            
            bitrate = settings.get("maxBitrate", 3)
            individual_cache_key = f"{track_id}_{bitrate}"
            
            cached_track = get_from_vault(individual_cache_key)
            if cached_track:
                file_ids_batch.append(cached_track)
                file_ids_all.append(cached_track)
                successful_tracks += 1
                continue
            
            try:
                file_path = await download_track(track_url, dz, settings, listener)
            except TrackPreviewUnavailableError:
                logging.warning(f"Song without preview available: {track_id} - {track_title}")
                skipped_tracks.append(f"• {track_title} - No disponible en Deezer")
                await update.message.reply_text(f"⚠️ No pude conseguir: {track_title}")
                failed_tracks += 1
                continue
            except Exception as track_error:
                error_msg = str(track_error)
                logging.error(f"Error downloading track {track_id} ({track_title}): {error_msg}")
                skipped_tracks.append(f"• {track_title} - Error")
                await update.message.reply_text(f"⚠️ No pude descargar: {track_title}")
                failed_tracks += 1
                continue
            
            file_id = await send_and_save_audio(
                context, 
                vault_chat_id,
                file_path, 
                f"{content_type.title()} track {i+1}/{total_tracks}: {track_title}", 
                vault_chat_id, 
                individual_cache_key,
                dz=dz,
                track_id=track_id
            )
            
            file_ids_batch.append(file_id)
            file_ids_all.append(file_id)
            add_to_vault(individual_cache_key, file_id)
            
            # Update user statistics
            try:
                session.increment_downloads()
            except Exception as stats_error:
                logging.error(f"[COLLECTION] Error updating stats for track {i+1}: {stats_error}")
                
            successful_tracks += 1
            
            if os.path.exists(file_path):
                os.remove(file_path)
            
        except Exception as e:
            logging.error(f"Error downloading track {i+1}: {str(e)}", exc_info=True)
            failed_tracks += 1
            continue
    
    if file_ids_batch:
        try:
            await retry_async_operation(
                context.bot.send_media_group,
                max_retries=3,
                initial_delay=2.0,
                chat_id=update.message.chat_id,
                media=[InputMediaAudio(media=file_id) for file_id in file_ids_batch]
            )
        except (TimedOut, NetworkError):
            for file_id in file_ids_batch:
                try:
                    await context.bot.send_audio(chat_id=update.message.chat_id, audio=file_id)
                    await asyncio.sleep(0.5)
                except:
                    pass
    
    if file_ids_all:
        add_to_vault(cache_key, file_ids_all)
        
        if failed_tracks > 0:
            skipped_info = "\n".join(skipped_tracks[:5])
            if len(skipped_tracks) > 5:
                skipped_info += f"\n... y {len(skipped_tracks) - 5} más"
            new_text = f"✅ ¡Listo! Conseguí {successful_tracks} de {total_tracks} canciones\n\n⚠️ No descargadas:\n{skipped_info}"
        else:
            new_text = f"✅ ¡Todo listo! Disfruta tus {successful_tracks} canciones"
        
        await safe_edit_message(status_message, new_text, parse_mode="Markdown")
    else:
        await safe_edit_message(status_message, f"❌ No pude descargar ninguna canción")
    
    return file_ids_all
