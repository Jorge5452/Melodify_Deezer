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
            if 0 < remaining <= 20:
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
            
            # Enviar un mensaje confirmando que se recibió la solicitud
            status_message = await update.message.reply_text(
                f"📥 Recibido! Procesando tu {'canción' if content_type == 'track' else content_type}..."
            )
            
            # Usar enqueue_download para procesamiento asíncrono dependiendo del tipo
            if content_type == "track":
                # Para canciones individuales podemos procesarlas directamente
                await process_track(update, context, url, content_id, dz, settings, vault_chat_id, listener)
            elif content_type in ["album", "playlist"]:
                # Para colecciones (que llevan más tiempo), usar el sistema de colas
                user_id = update.effective_user.id
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
                    listener=listener
                )
                
                if success:
                    await status_message.edit_text(
                        f"✅ Tu {content_type} ha sido añadido a la cola de descargas. "
                        f"Te enviaré las canciones tan pronto como estén listas."
                    )
                else:
                    await status_message.edit_text(
                        "❌ No se pudo añadir a la cola de descargas. Por favor, inténtalo de nuevo."
                    )
            else:
                await update.message.reply_text("🔗 Tipo de contenido no soportado")
        else:
            # Si no es una URL, tratar como búsqueda
            await show_search_menu(update, context)
            
    except Exception as e:
        logging.error(f"Error crítico en handle_message: {str(e)}", exc_info=True)
        await update.message.reply_text("⚠️ Error procesando tu solicitud")
