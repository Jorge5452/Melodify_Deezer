# -*- coding: utf-8 -*-
"""
Main message handler for incoming Telegram messages.

Routes incoming text messages to appropriate handlers based on content.
"""

import logging
from telegram import Update
from telegram.ext import ContextTypes

from src.core.services import UserSession
from src.interface.telegram.utils.validation import validate_deezer_url, get_content_type, extract_id_from_url
from src.interface.telegram.handlers.track import process_track
from src.interface.telegram.handlers.collection import process_collection
from src.interface.telegram.handlers.search import show_search_menu
from src.interface.telegram.handlers.messages import message_manager
from src.interface.telegram.utils.decorators import combined_decorator
from src.infrastructure.deezer import enqueue_download


@combined_decorator
async def handle_message(
    update: Update, 
    context: ContextTypes.DEFAULT_TYPE, 
    dz, 
    settings, 
    vault_chat_id, 
    listener
):
    """Handles incoming messages, processing Deezer URLs or searches."""
    try:
        url = update.message.text.strip()
        session = context.user_data.get('session')
        
        # Check monthly limit for normal users
        if session and session.get_role() == "normal":
            monthly_stats = session.get_monthly_downloads_left()
            remaining = monthly_stats['remaining']
            
            if 0 < remaining <= 50:
                await update.message.reply_text(
                    f"⚠️ *Aviso: Te quedan solo {remaining} descargas* este mes.\n"
                    f"Has usado {monthly_stats['used']} de {monthly_stats['limit']} descargas mensuales.\n"
                    f"Considera donar para mantener el servicio y obtener beneficios adicionales.",
                    parse_mode="Markdown"
                )
        
        # Validate URL
        if validate_deezer_url(url):
            content_type = get_content_type(url)
            content_id = extract_id_from_url(url)
            
            progress_message = None
            
            # Check for existing progress message from search callback
            if hasattr(update, 'progress_message') and update.progress_message:
                progress_message = update.progress_message
                
                if not hasattr(update, 'from_search_callback') or not update.from_search_callback:
                    await progress_message.update(
                        "processing", 
                        content_type="canción" if content_type == "track" else content_type
                    )
            else:
                progress_message = await message_manager.send_progress(
                    update,
                    process_type="download" if content_type == "track" else "collection",
                    initial_status="processing",
                    content_type="canción" if content_type == "track" else content_type
            )
            
            if content_type == "track":
                progress_message.from_collection = False
                await process_track(update, context, url, content_id, dz, settings, vault_chat_id, listener, progress_message)
            elif content_type in ["album", "playlist"]:
                user_id = update.effective_user.id
                progress_message.from_collection = True
                success = await enqueue_download(
                    user_id, 
                    process_collection, 
                    update=update, 
                    context=context, 
                    url=url, 
                    content_type=content_type, 
                    content_id=content_id, 
                    dz=dz, 
                    settings=settings, 
                    vault_chat_id=vault_chat_id, 
                    listener=listener,
                    progress_message=progress_message
                )
                
                if not success:
                    await progress_message.complete(
                        success=False,
                        error_message="No se pudo añadir a la cola de descargas. Por favor, inténtalo de nuevo."
                    )
            else:
                await update.message.reply_text("🔗 Tipo de contenido no soportado")
        else:
            # Not a URL, treat as search
            await show_search_menu(update, context)
            
    except Exception as e:
        logging.error(f"Critical error in handle_message: {str(e)}", exc_info=True)
        await update.message.reply_text("⚠️ Error procesando tu solicitud")
