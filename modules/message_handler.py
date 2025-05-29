import logging
from telegram import Update
from telegram.ext import ContextTypes
from user_session import UserSession
from modules.validation import validate_deezer_url, get_content_type, extract_id_from_url
from modules.track_processor import process_track
from modules.collection_processor import process_collection
from modules.search_engine import show_search_menu
from modules.decorators import combined_decorator
from downloader import enqueue_download
from modules.message_manager import message_manager

@combined_decorator
async def handle_message(
    update: Update, 
    context: ContextTypes.DEFAULT_TYPE, 
    dz, 
    settings, 
    vault_chat_id, 
    listener
):
    """Maneja los mensajes entrantes, procesando URLs de Deezer o búsquedas."""
    try:
        url = update.message.text.strip()
        session = context.user_data.get('session')
        
        # Verificar límite mensual para usuarios normales
        if session and session.get_role() == "normal":
            # Verificar si el usuario está cerca de su límite mensual
            monthly_stats = session.get_monthly_downloads_left()
            remaining = monthly_stats['remaining']
            
            # Mostrar una advertencia si quedan pocas descargas
            if 0 < remaining <= 50:
                await update.message.reply_text(
                    f"⚠️ *Aviso: Te quedan solo {remaining} descargas* este mes.\n"
                    f"Has usado {monthly_stats['used']} de {monthly_stats['limit']} descargas mensuales.\n"
                    f"Considera donar para mantener el servicio y obtener beneficios adicionales.",
                    parse_mode="Markdown"
                )
        
        # Validar URL
        if validate_deezer_url(url):
            # Obtener tipo de contenido y su ID
            content_type = get_content_type(url)
            content_id = extract_id_from_url(url)
            
            # Verificar si ya hay un mensaje de progreso (desde un callback de búsqueda)
            progress_message = None
            
            # Si el update viene de un SimulatedUpdate con un mensaje de progreso existente
            if hasattr(update, 'progress_message') and update.progress_message:
                # Reutilizar el mensaje de progreso existente
                progress_message = update.progress_message
                
                # Actualizar solo si no viene de una búsqueda (para evitar doble mensaje)
                if not hasattr(update, 'from_search_callback') or not update.from_search_callback:
                    # Actualizar a estado "processing"
                    await progress_message.update(
                        "processing", 
                        content_type="canción" if content_type == "track" else content_type
                    )
                # Si viene de una búsqueda, reutilizar sin actualizar texto (ya está en "starting")
            else:
                # Si no hay mensaje existente, crear uno nuevo
                progress_message = await message_manager.send_progress(
                    update,
                    process_type="download" if content_type == "track" else "collection",
                    initial_status="processing", # Usar "processing" directamente ya que "starting" ya se mostró en search_handler
                    content_type="canción" if content_type == "track" else content_type
            )
            
            # Usar enqueue_download para procesamiento asíncrono dependiendo del tipo
            if content_type == "track":
                # Para canciones individuales podemos procesarlas directamente
                # No necesitamos usar enqueue_download, pero debemos marcar que progreso es individual
                progress_message.from_collection = False
                await process_track(update, context, url, content_id, dz, settings, vault_chat_id, listener, progress_message)
            elif content_type in ["album", "playlist"]:
                # Para colecciones (que llevan más tiempo), usar el sistema de colas
                user_id = update.effective_user.id
                # Mark the progress message as coming from a collection
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
                    progress_message=progress_message  # Pasar el mensaje de progreso
                )
                
                if not success:
                    # Si falla la cola, actualizar el mensaje de progreso
                    await progress_message.complete(
                        success=False,
                        error_message="No se pudo añadir a la cola de descargas. Por favor, inténtalo de nuevo."
                    )
            else:
                await update.message.reply_text("🔗 Tipo de contenido no soportado")
        else:
            # Si no es una URL, tratar como búsqueda
            await show_search_menu(update, context)
            
    except Exception as e:
        logging.error(f"Error crítico en handle_message: {str(e)}", exc_info=True)
        await update.message.reply_text("⚠️ Error procesando tu solicitud")
