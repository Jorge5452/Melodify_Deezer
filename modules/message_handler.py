import logging
from telegram import Update
from telegram.ext import ContextTypes
from user_session import UserSession
from modules.validation import validate_deezer_url, get_content_type, extract_id_from_url
from modules.track_processor import process_track
from modules.collection_processor import process_collection

async def handle_message(
    update: Update, 
    context: ContextTypes.DEFAULT_TYPE, 
    dz, 
    settings, 
    vault_chat_id, 
    listener
):
    """Maneja los mensajes entrantes, procesando URLs de Deezer o búsquedas."""
    print(" - - - Dentro de handle message - - -")
    try:
        url = update.message.text.strip()
        user_id = update.effective_user.id
        
        # Obtener sesión de usuario
        session = UserSession.get_session(user_id)
        
        # Validar URL
        if validate_deezer_url(url):
            # Obtener tipo de contenido y su ID
            content_type = get_content_type(url)
            content_id = extract_id_from_url(url)
            
            if content_type == "track":
                print(f" - - - Usando {content_type} - - -")
                await process_track(update, context, url, content_id, dz, settings, vault_chat_id, listener)
            elif content_type in ["album", "playlist"]:
                print(f" - - - Usando {content_type} - - -")
                await process_collection(update, context, url, content_type, content_id, dz, settings, vault_chat_id, listener)
            else:
                await update.message.reply_text("🔗 Tipo de contenido no soportado")
        else:
            # Si no es una URL, tratar como búsqueda
            # Importamos aquí para evitar la importación circular
            from modules.search_handler import show_search_menu
            await show_search_menu(update, context)
            
    except Exception as e:
        logging.error(f"Error crítico: {str(e)}", exc_info=True)
        await update.message.reply_text("⚠️ Error procesando tu solicitud")
