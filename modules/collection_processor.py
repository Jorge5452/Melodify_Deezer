import logging
import os
import asyncio
import requests
from io import BytesIO
from telegram import InputMediaAudio
from downloader import download_track, TrackPreviewUnavailableError
from vault import add_to_vault, get_from_vault
from config import BATCH_SIZE
from modules.audio_sender import send_and_save_audio
from modules.utils import safe_edit_message, retry_async_operation
from telegram.error import TimedOut, NetworkError

# Definir clases de excepciones personalizadas
class CollectionProcessingError(Exception):
    """Excepción base para errores en el procesamiento de colecciones."""
    pass

class EmptyCollectionError(CollectionProcessingError):
    """Excepción lanzada cuando una colección no contiene pistas."""
    pass

class TrackDownloadError(CollectionProcessingError):
    """Excepción lanzada cuando falla la descarga de una pista individual."""
    pass

class TrackNotAvailableError(TrackDownloadError):
    """Excepción lanzada cuando una pista no está disponible (región, derechos, etc.)."""
    pass

async def process_collection(update, context, url, content_type, content_id, dz, settings, vault_chat_id, listener):
    """
    Procesa la descarga de un álbum o playlist.
    """
    cache_key = f"{content_type}_{content_id}"
    # Verificar si existe el álbum/playlist completo en caché, pero solo usarlo 
    # completamente para tipos de contenido que no sean ni playlist ni álbum
    cached_data = get_from_vault(cache_key)
    
    # Si no es ni playlist ni álbum y existe en caché, enviar directamente
    if content_type != "playlist" and content_type != "album" and cached_data and isinstance(cached_data, list):
        for file_id in cached_data:
            await update.message.reply_audio(audio=file_id)
        return
    
    # Notificar inicio de descarga
    status_message = await update.message.reply_text(f"⏳ Buscando {content_type}...")
    
    try:
        # Obtener información del álbum/playlist
        collection_info = await get_collection_info(dz, content_type, content_id)
        
        # Verificar si se obtuvo la información correctamente
        if not collection_info:
            await status_message.edit_text(f"❌ No encuentro este {content_type}. ¿El enlace es correcto?")
            return
        
        # Extraer metadatos y URLs de pistas
        track_urls, track_ids, track_titles = await extract_tracks_info(collection_info, dz)
        
        if not track_urls:
            # Mensaje más descriptivo cuando no hay pistas
            if content_type == "album":
                message = f"❌ Este álbum no tiene canciones disponibles"
            else:  # playlist
                message = f"❌ Esta playlist está vacía o sus canciones no están disponibles"
            
            await status_message.edit_text(message)
            return
        
        total_tracks = len(track_urls)
        logging.info(f"Pistas encontradas en {content_type}: {total_tracks}")
        
        # Enviar vista previa de la colección
        await send_collection_preview(update, context, collection_info, content_type, total_tracks)
        
        # Actualizar mensaje de estado
        await status_message.edit_text(f"⏳ Preparando {total_tracks} canciones...")
        
        # Determinar si procesar por lotes o individualmente
        if total_tracks > BATCH_SIZE:
            # Procesar en lotes para playlists grandes
            await process_playlist_in_batches(update, context, track_urls, track_ids, track_titles, 
                                             dz, settings, listener, vault_chat_id, 
                                             status_message, cache_key, content_type)
        else:
            # Para pocas pistas, procesar individualmente
            await process_small_collection(update, context, track_urls, track_ids, track_titles,
                                          total_tracks, dz, settings, listener, vault_chat_id,
                                          status_message, cache_key, content_type)
    
    except EmptyCollectionError:
        await status_message.edit_text(f"❌ No hay canciones disponibles")
    except requests.exceptions.RequestException as e:
        await status_message.edit_text(f"❌ Problemas de conexión. Inténtalo más tarde")
        logging.error(f"Error de conexión en {content_type}: {str(e)}", exc_info=True)
    except Exception as e:
        logging.error(f"Error al procesar {content_type}: {str(e)}", exc_info=True)
        await status_message.edit_text(f"❌ No pude procesar este {content_type}")

async def process_playlist_in_batches(update, context, track_urls, track_ids, track_titles, 
                                     dz, settings, listener, vault_chat_id, 
                                     status_message, cache_key, content_type):
    """
    Procesa una playlist grande en lotes y actualiza el progreso en tiempo real.
    """
    total_tracks = len(track_urls)
    total_batches = (total_tracks + BATCH_SIZE - 1) // BATCH_SIZE  # Redondeo hacia arriba
    
    file_ids_all = []
    successful_tracks = 0
    failed_tracks = 0
    last_status_text = ""  # Para evitar actualizar con el mismo texto
    skipped_tracks = []  # Lista para almacenar información de pistas omitidas
    
    # Mensaje inicial de progreso
    await safe_edit_message(status_message, 
        f"⏳ Descargando: 0/{total_tracks}\n"
        f"Procesando lote 1/{total_batches}"
    )
    
    for batch_num in range(total_batches):
        start_idx = batch_num * BATCH_SIZE
        end_idx = min(start_idx + BATCH_SIZE, total_tracks)
        
        # Obtener listas para este lote
        batch_urls = track_urls[start_idx:end_idx]
        batch_ids = track_ids[start_idx:end_idx]
        batch_titles = track_titles[start_idx:end_idx]
        
        # Actualizar mensaje de estado para este lote
        new_text = (
            f"⏳ Descargando canciones: {successful_tracks}/{total_tracks}\n"
            f"Lote: {batch_num+1}/{total_batches}\n"
            f"Preparando lote..."
        )
        if new_text != last_status_text:
            await safe_edit_message(status_message, new_text)
            last_status_text = new_text
        
        # Descargar y preparar pistas de este lote
        file_ids_batch = []
        
        for i, (track_url, track_id, track_title) in enumerate(zip(batch_urls, batch_ids, batch_titles)):
            try:
                # Calcular el índice global de la pista
                global_idx = start_idx + i
                
                # Actualizar mensaje de progreso con la canción actual
                new_text = (
                    f"⏳ Descargando: {successful_tracks}/{total_tracks}\n"
                    f"Procesando: {track_title}"
                )
                if new_text != last_status_text:
                    await safe_edit_message(status_message, new_text)
                    last_status_text = new_text
                
                # Verificar si esta pista específica está en caché
                bitrate = settings.get("maxBitrate", 3)
                individual_cache_key = f"{track_id}_{bitrate}"
                cached_file_id = get_from_vault(individual_cache_key)
                
                if cached_file_id:
                    # Si está en caché, usar directamente
                    file_ids_batch.append(cached_file_id)
                    file_ids_all.append(cached_file_id)
                    successful_tracks += 1
                    
                    # Actualizar progreso después de cada canción exitosa
                    new_text = (
                        f"⏳ Progreso: {successful_tracks}/{total_tracks}\n"
                        f"✅ Encontrada en caché: {track_title}"
                    )
                    if new_text != last_status_text:
                        await safe_edit_message(status_message, new_text)
                        last_status_text = new_text
                    continue
                
                # Descargar pista individual
                try:
                    file_path = await download_track(track_url, dz, settings, listener)
                except TrackPreviewUnavailableError as e:
                    # Extraer el nombre de la canción del error o usar el título conocido
                    error_msg = str(e)
                    error_track = track_title
                    
                    # Mensaje para logs
                    logging.warning(f"Canción sin preview disponible: {track_id} - {track_title}")
                    
                    # Añadir a lista de canciones saltadas con su nombre
                    skipped_tracks.append(f"• {track_title} - No disponible en Deezer")
                    
                    # Mensaje amigable al usuario sobre esta canción específica
                    skip_text = (
                        f"⚠️ No pude conseguir: {track_title}\n"
                        f"Esta canción ya no está disponible en Deezer o ha sido retirada"
                    )
                    await update.message.reply_text(skip_text)
                    
                    failed_tracks += 1
                    continue
                except Exception as track_error:
                    # Asegurar que guardamos qué canción falló
                    error_msg = str(track_error)
                    logging.error(f"Error descargando pista {track_id} ({track_title}): {error_msg}")
                    
                    # Garantizar que siempre se incluye el nombre de la canción
                    skipped_tracks.append(f"• {track_title} - Error: {error_msg[:30]}..." if len(error_msg) > 30 else error_msg)
                    
                    # También informar al usuario en tiempo real
                    skip_text = f"⚠️ No pude descargar: {track_title}"
                    await update.message.reply_text(skip_text)
                    
                    failed_tracks += 1
                    continue
                
                # Guardar en vault pero no enviar individualmente
                file_id = await send_and_save_audio(
                    context, 
                    vault_chat_id,  # Solo enviar al vault, no al usuario todavía
                    file_path, 
                    f"{content_type.title()} pista {global_idx+1}/{total_tracks}: {track_title}", 
                    vault_chat_id, 
                    individual_cache_key,
                    dz=dz,
                    track_id=track_id
                )
                
                # Guardar ID en las listas
                file_ids_batch.append(file_id)
                file_ids_all.append(file_id)
                add_to_vault(individual_cache_key, file_id)
                successful_tracks += 1
                
                # Actualizar progreso después de cada canción exitosa
                new_text = (
                    f"⏳ Progreso: {successful_tracks}/{total_tracks}\n"
                    f"✅ Descargada: {track_title}"
                )
                if new_text != last_status_text:
                    await safe_edit_message(status_message, new_text)
                    last_status_text = new_text
                
                # Eliminar archivo temporal
                if os.path.exists(file_path):
                    os.remove(file_path)
                
            except requests.exceptions.RequestException as e:
                logging.error(f"Error de conexión descargando pista {start_idx+i+1}: {str(e)}")
                skipped_tracks.append(f"• {track_title} - Error de conexión")
                failed_tracks += 1
                continue
            except FileNotFoundError:
                logging.error(f"Pista no encontrada: {track_id}")
                skipped_tracks.append(f"• {track_title} - No disponible en esta región")
                failed_tracks += 1
                continue
            except TrackNotAvailableError:
                logging.error(f"Pista no disponible: {track_id}")
                skipped_tracks.append(f"• {track_title} - Restricciones de derechos")
                failed_tracks += 1
                continue
            except Exception as e:
                logging.error(f"Error descargando pista {start_idx+i+1}: {str(e)}", exc_info=True)
                skipped_tracks.append(f"• {track_title} - {str(e)[:50]}...")
                failed_tracks += 1
                continue
        
        # Enviar audios del lote en un solo mensaje agrupado
        if file_ids_batch:
            try:
                # Actualizar mensaje mientras se envían los archivos
                new_text = (
                    f"⏳ Canciones: {successful_tracks}/{total_tracks}\n"
                    f"📤 Enviando lote {batch_num+1}..."
                )
                if new_text != last_status_text:
                    await safe_edit_message(status_message, new_text)
                    last_status_text = new_text
                
                # Usar retry_async_operation para enviar el grupo de medios
                try:
                    await retry_async_operation(
                        context.bot.send_media_group,
                        max_retries=3,
                        initial_delay=2.0,
                        chat_id=update.message.chat_id,
                        media=[InputMediaAudio(media=file_id) for file_id in file_ids_batch]
                    )
                except (TimedOut, NetworkError) as e:
                    logging.error(f"Error al enviar grupo de audios después de reintentos: {str(e)}")
                    # Si falla después de los reintentos, intentar envío individual
                    logging.info("Cambiando a envío individual de archivos...")
                    for file_id in file_ids_batch:
                        try:
                            await retry_async_operation(
                                context.bot.send_audio,
                                max_retries=2,
                                chat_id=update.message.chat_id,
                                audio=file_id,
                                # Sin metadatos para simplificar
                            )
                            # Pequeña pausa entre envíos para evitar límites de tasa
                            await asyncio.sleep(0.5)
                        except Exception as individual_error:
                            logging.error(f"No se pudo enviar archivo individual: {str(individual_error)}")
            except Exception as e:
                logging.error(f"Error enviando grupo de audios: {str(e)}", exc_info=True)
                # Intentar enviar uno por uno como fallback
                for file_id in file_ids_batch:
                    try:
                        await retry_async_operation(
                            context.bot.send_audio,
                            max_retries=2,
                            chat_id=update.message.chat_id,
                            audio=file_id
                        )
                        # Pequeña pausa entre envíos
                        await asyncio.sleep(0.5)
                    except Exception as fallback_error:
                        logging.error(f"Error en fallback de envío individual: {str(fallback_error)}")
        
        # Pausa entre lotes
        if batch_num < total_batches - 1:
            await asyncio.sleep(3)
    
    # Guardar todos los IDs en el vault como playlist/album completo
    if file_ids_all:
        add_to_vault(cache_key, file_ids_all)
        
        # Construir mensaje final con información detallada
        if failed_tracks > 0:
            # Formato más claro para las pistas con error, destacando los nombres
            formatted_skipped = []
            for error_entry in skipped_tracks[:5]:
                if " - " in error_entry and error_entry.startswith("•"):
                    # Separar el título de la canción y el mensaje de error
                    parts = error_entry.split(" - ", 1)
                    song_title = parts[0][2:].strip()  # Quitar el "• " del inicio
                    error_reason = parts[1] if len(parts) > 1 else "No disponible"
                    
                    # Dar formato más legible con el título en negrita
                    formatted_skipped.append(f"• *{song_title}*: {error_reason}")
                else:
                    formatted_skipped.append(error_entry)
            
            skipped_info = "\n".join(formatted_skipped)
            if len(skipped_tracks) > 5:
                skipped_info += f"\n... y {len(skipped_tracks) - 5} más"
            
            new_text = (
                f"✅ ¡Listo! Conseguí {successful_tracks} de {total_tracks} canciones\n\n"
                f"⚠️ Canciones no descargadas:\n{skipped_info}"
            )
        else:
            new_text = f"✅ ¡Todo listo! Disfruta tus {successful_tracks} canciones"
        
        await safe_edit_message(status_message, new_text, parse_mode="Markdown")
    else:
        await safe_edit_message(status_message, f"❌ No pude descargar ninguna canción")
    
    return file_ids_all

async def process_small_collection(update, context, track_urls, track_ids, track_titles,
                                  total_tracks, dz, settings, listener, vault_chat_id,
                                  status_message, cache_key, content_type):
    """Procesa una colección pequeña de pistas con mensajes de progreso detallados."""
    file_ids_all = []
    file_ids_batch = []
    successful_tracks = 0
    failed_tracks = 0
    last_status_text = ""  # Para evitar actualizar con el mismo texto
    skipped_tracks = []  # Lista para almacenar información de pistas omitidas
    
    # Mensaje inicial de progreso
    await safe_edit_message(status_message,
        f"⏳ Descargando: 0/{total_tracks}"
    )
    
    for i, (track_url, track_id, track_title) in enumerate(zip(track_urls, track_ids, track_titles)):
        try:
            # Actualizar mensaje con la canción actual
            new_text = (
                f"⏳ Progreso: {successful_tracks}/{total_tracks}\n"
                f"Procesando: {track_title}"
            )
            if new_text != last_status_text:
                await safe_edit_message(status_message, new_text)
                last_status_text = new_text
            
            # Definir clave de caché para esta pista
            bitrate = settings.get("maxBitrate", 3)
            individual_cache_key = f"{track_id}_{bitrate}"
            
            # Verificar si esta pista específica está en caché
            cached_track = get_from_vault(individual_cache_key)
            if cached_track:
                file_ids_batch.append(cached_track)
                file_ids_all.append(cached_track)
                successful_tracks += 1
                
                # Actualizar progreso después de cada canción exitosa
                new_text = (
                    f"⏳ Progreso: {successful_tracks}/{total_tracks}\n"
                    f"✅ Encontrada en caché: {track_title}"
                )
                if new_text != last_status_text:
                    await safe_edit_message(status_message, new_text)
                    last_status_text = new_text
                continue
            
            # Descargar pista individual
            try:
                file_path = await download_track(track_url, dz, settings, listener)
            except TrackPreviewUnavailableError as e:
                # Mensaje para logs
                logging.warning(f"Canción sin preview disponible: {track_id} - {track_title}")
                
                # Añadir a lista de canciones saltadas con su nombre
                skipped_tracks.append(f"• {track_title} - No disponible en Deezer")
                
                # Mensaje amigable al usuario sobre esta canción específica
                skip_text = (
                    f"⚠️ No pude conseguir: {track_title}\n"
                    f"Esta canción ya no está disponible en Deezer o ha sido retirada"
                )
                await update.message.reply_text(skip_text)
                
                failed_tracks += 1
                continue
            except Exception as track_error:
                # Asegurar que guardamos qué canción falló
                error_msg = str(track_error)
                logging.error(f"Error descargando pista {track_id} ({track_title}): {error_msg}")
                
                # Garantizar que siempre se incluye el nombre de la canción
                skipped_tracks.append(f"• {track_title} - Error: {error_msg[:30]}..." if len(error_msg) > 30 else error_msg)
                
                # También informar al usuario en tiempo real
                skip_text = f"⚠️ No pude descargar: {track_title}"
                await update.message.reply_text(skip_text)
                
                failed_tracks += 1
                continue
            
            # Enviar y guardar en vault
            file_id = await send_and_save_audio(
                context, 
                vault_chat_id,  # Solo enviar al vault primero
                file_path, 
                f"{content_type.title()} pista {i+1}/{total_tracks}: {track_title}", 
                vault_chat_id, 
                individual_cache_key,
                dz=dz,
                track_id=track_id
            )
            
            # Guardar ID en las listas
            file_ids_batch.append(file_id)
            file_ids_all.append(file_id)
            add_to_vault(individual_cache_key, file_id)
            successful_tracks += 1
            
            # Actualizar progreso después de cada canción exitosa
            new_text = (
                f"⏳ Progreso: {successful_tracks}/{total_tracks}\n"
                f"✅ Descargada: {track_title}"
            )
            if new_text != last_status_text:
                await safe_edit_message(status_message, new_text)
                last_status_text = new_text
            
            # Eliminar archivo temporal
            if os.path.exists(file_path):
                os.remove(file_path)
            
        except requests.exceptions.RequestException as e:
            logging.error(f"Error de conexión descargando pista {i+1}: {str(e)}")
            skipped_tracks.append(f"• {track_title} - Error de conexión")
            failed_tracks += 1
            continue
        except FileNotFoundError:
            logging.error(f"Pista no encontrada: {track_id}")
            skipped_tracks.append(f"• {track_title} - No disponible en esta región")
            failed_tracks += 1
            continue
        except TrackNotAvailableError:
            logging.error(f"Pista no disponible: {track_id}")
            skipped_tracks.append(f"• {track_title} - Restricciones de derechos")
            failed_tracks += 1
            continue
        except Exception as e:
            logging.error(f"Error descargando pista {i+1}: {str(e)}", exc_info=True)
            skipped_tracks.append(f"• {track_title} - {str(e)[:50]}...")
            failed_tracks += 1
            continue
    
    # Enviar todos los audios en un solo grupo
    if file_ids_batch:
        try:
            # Actualizar mensaje mientras se envían los archivos
            new_text = (
                f"⏳ Canciones: {successful_tracks}/{total_tracks}\n"
                f"📤 Enviando música..."
            )
            if new_text != last_status_text:
                await safe_edit_message(status_message, new_text)
                last_status_text = new_text
            
            # Usar retry_async_operation para enviar el grupo de medios
            try:
                await retry_async_operation(
                    context.bot.send_media_group,
                    max_retries=3,
                    initial_delay=2.0,
                    chat_id=update.message.chat_id,
                    media=[InputMediaAudio(media=file_id) for file_id in file_ids_batch]
                )
            except (TimedOut, NetworkError) as e:
                logging.error(f"Error al enviar grupo de audios después de reintentos: {str(e)}")
                # Si falla después de los reintentos, intentar envío individual
                logging.info("Cambiando a envío individual de archivos...")
                for file_id in file_ids_batch:
                    try:
                        await retry_async_operation(
                            context.bot.send_audio,
                            max_retries=2,
                            chat_id=update.message.chat_id,
                            audio=file_id,
                            # Sin metadatos para simplificar
                        )
                        # Pequeña pausa entre envíos para evitar límites de tasa
                        await asyncio.sleep(0.5)
                    except Exception as individual_error:
                        logging.error(f"No se pudo enviar archivo individual: {str(individual_error)}")
        except Exception as e:
            logging.error(f"Error enviando grupo de audios: {str(e)}", exc_info=True)
            # Intentar enviar uno por uno como fallback
            for file_id in file_ids_batch:
                try:
                    await retry_async_operation(
                        context.bot.send_audio,
                        max_retries=2,
                        chat_id=update.message.chat_id,
                        audio=file_id
                    )
                    # Pequeña pausa entre envíos
                    await asyncio.sleep(0.5)
                except Exception as fallback_error:
                    logging.error(f"Error en fallback de envío individual: {str(fallback_error)}")
    
    # Guardar todos los IDs en el vault como playlist/album completo
    if file_ids_all:
        add_to_vault(cache_key, file_ids_all)
        
        # Construir mensaje final con información detallada
        if failed_tracks > 0:
            # Formato más claro para las pistas con error, destacando los nombres
            formatted_skipped = []
            for error_entry in skipped_tracks[:5]:
                if " - " in error_entry and error_entry.startswith("•"):
                    # Separar el título de la canción y el mensaje de error
                    parts = error_entry.split(" - ", 1)
                    song_title = parts[0][2:].strip()  # Quitar el "• " del inicio
                    error_reason = parts[1] if len(parts) > 1 else "No disponible"
                    
                    # Dar formato más legible con el título en negrita
                    formatted_skipped.append(f"• *{song_title}*: {error_reason}")
                else:
                    formatted_skipped.append(error_entry)
            
            skipped_info = "\n".join(formatted_skipped)
            if len(skipped_tracks) > 5:
                skipped_info += f"\n... y {len(skipped_tracks) - 5} más"
            
            new_text = (
                f"✅ ¡Listo! Conseguí {successful_tracks} de {total_tracks} canciones\n\n"
                f"⚠️ Canciones no descargadas:\n{skipped_info}"
            )
        else:
            new_text = f"✅ ¡Todo listo! Disfruta tus {successful_tracks} canciones"
        
        await safe_edit_message(status_message, new_text, parse_mode="Markdown")
    else:
        await safe_edit_message(status_message, f"❌ No pude descargar ninguna canción")
    
    return file_ids_all

async def get_collection_info(dz, content_type, content_id):
    """Obtiene información sobre un álbum o playlist."""
    try:
        if content_type == "album":
            result = dz.api.get_album(content_id)
        else:  # playlist
            result = dz.api.get_playlist(content_id)
        
        if not result:
            raise EmptyCollectionError(f"No se pudo encontrar el {content_type}")
        
        return result
    except Exception as e:
        logging.error(f"Error al obtener información de {content_type}: {str(e)}", exc_info=True)
        raise

async def extract_tracks_info(collection_info, dz):
    """Extrae información de pistas de un álbum o playlist."""
    track_urls = []
    track_ids = []
    track_titles = []
    
    try:
        # Extraer la página inicial de pistas.
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
        
        # Obtener la cantidad total de pistas en el álbum (si está disponible)
        total_album_tracks = collection_info.get('nb_tracks')
        album_id = collection_info.get('id')

        # Determinar la URL de la siguiente página. Si la API no la entrega pero faltan pistas, la construimos manualmente.
        next_url = tracks_data.get('next')
        if total_album_tracks and total_album_tracks > len(track_urls) and not next_url:
            next_url = f"https://api.deezer.com/album/{album_id}/tracks?index={len(track_urls)}"

        # Mientras exista una URL "next" y aún no se hayan obtenido todas las pistas, seguir extrayéndolas.
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
                # Si la API no proporciona "next" pero aún faltan pistas, generar la URL manualmente.
                if not next_url and total_album_tracks and len(track_urls) < total_album_tracks:
                    next_url = f"https://api.deezer.com/album/{album_id}/tracks?index={len(track_urls)}"
            else:
                break
    except Exception as e:
        logging.warning(f"No se pudo obtener lista de tracks: {str(e)}")
        
    return track_urls, track_ids, track_titles

async def send_collection_preview(update, context, collection_info, content_type, total_tracks):
    """
    Envía una vista previa de la playlist o álbum con su carátula e información.
    
    Args:
        update: Objeto Update de Telegram
        context: Contexto del bot
        collection_info: Información de la colección (playlist/álbum)
        content_type: Tipo de contenido ('playlist' o 'album')
        total_tracks: Número total de pistas
    """
    try:
        # Determinar URL de la imagen según el tipo de contenido
        image_url = None
        title = collection_info.get('title', 'Sin título')
        
        if (content_type == 'album'):
            image_url = collection_info.get('cover_big') or collection_info.get('cover_medium')
            artist_name = collection_info.get('artist', {}).get('name', 'Artista desconocido')
            caption = f"🎵 Álbum: {title}\n👤 Artista: {artist_name}\n🔢 Pistas: {total_tracks}"
        else:  # playlist
            image_url = collection_info.get('picture_big') or collection_info.get('picture_medium')
            creator = collection_info.get('creator', {}).get('name', 'Creador desconocido')
            caption = f"🎵 Playlist: {title}\n👤 Creador: {creator}\n🔢 Pistas: {total_tracks}"
        
        # Si no hay URL de imagen, enviar solo mensaje de texto
        if not image_url:
            await update.message.reply_text(caption)
            return
        
        # Descargar imagen
        response = requests.get(image_url)
        if response.status_code != 200:
            # Si falla la descarga de imagen, enviar solo texto
            await update.message.reply_text(caption)
            return
        
        # Crear objeto de bytes para la imagen
        image_data = BytesIO(response.content)
        image_data.name = f"{content_type}_cover.jpg"
        
        # Enviar imagen con caption
        await context.bot.send_photo(
            chat_id=update.message.chat_id,
            photo=image_data,
            caption=caption
        )
        
    except Exception as e:
        logging.error(f"Error enviando vista previa: {str(e)}", exc_info=True)
        # Si falla, intentar enviar al menos el texto
        try:
            await update.message.reply_text(f"🎵 {content_type.title()}: {collection_info.get('title', 'Sin título')}\n🔢 Pistas: {total_tracks}")
        except:
            pass
