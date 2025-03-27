import os
import asyncio
import logging
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)
from deezer import Deezer
from deemix.settings import load, save
from user_session import cleanup_sessions, UserSession
from config import (
    TELEGRAM_TOKEN,
    DEEZER_ARL,
    VAULT_CHATID,
    DOWNLOAD_PATH,
    LOG_LEVEL,
    LOG_FORMAT
)

from downloader import LogListener
from bot import start, handle_message, configuracion, config_callback, process_search_callback, stats_command

# Configuración del logging con formato claro
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format=LOG_FORMAT
)

logging.getLogger("telegram").setLevel(logging.WARNING)
logging.getLogger("deemix").setLevel(logging.INFO)

async def error_handler(update, context):
    """Maneja excepciones que ocurren en los handlers."""
    logging.error(f"Error al procesar la actualización {update}: {context.error}", exc_info=True)
    if update and update.effective_message:
        await update.effective_message.reply_text("⚠️ Ocurrió un error al procesar tu solicitud. Inténtalo de nuevo más tarde.")


async def handle_message_with_user_session(update, context, dz, settings, vault_chat_id, listener):
    """Wrapper para handle_message que gestiona la sesión de usuario"""
    try:
        user_id = update.effective_user.id
        session = UserSession.get_session(user_id)
        session.update_activity()
        
        # Usando una restricción de tasa para no sobrecargar
        await session.wait_for_rate_limit()
        
        # Llamar a la función original de manejo de mensajes
        await handle_message(update, context, dz, settings, vault_chat_id, listener)
    except Exception as e:
        logging.error(f"Error en handle_message_with_user_session: {e}", exc_info=True)
        await update.message.reply_text("❌ Error al procesar tu solicitud. Por favor, inténtalo de nuevo.")


async def main():
    try:
        logging.info("Iniciando el bot...")
        
        # Verificar que las variables de entorno estén configuradas
        if not TELEGRAM_TOKEN:
            raise Exception("La variable de entorno TELEGRAM_TOKEN no está configurada en el archivo .env")
        logging.info("Token de Telegram encontrado")
        
        if not DEEZER_ARL:
            raise Exception("La variable de entorno DEEZER_AR no está configurada en el archivo .env")
        logging.info("ARL de Deezer encontrado")
        
        logging.info(f"Creando directorio de descargas: {DOWNLOAD_PATH}")
        os.makedirs(DOWNLOAD_PATH, exist_ok=True)
        
        # Configurar settings
        logging.info("Cargando configuración de deemix...")
        settings = load()
        settings["downloadLocation"] = os.path.abspath(DOWNLOAD_PATH)
        save(settings)
        
        # Inicializar Deezer
        logging.info("Iniciando sesión en Deezer...")
        dz = Deezer()
        if not dz.login_via_arl(DEEZER_ARL):
            raise Exception("Fallo en la autenticación: verifica tu ARL.")
        logging.info("Sesión iniciada exitosamente")
        
        listener = LogListener()
        
        logging.info("Creando aplicación de Telegram...")
        app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
        
        # Guardar settings y componentes en el contexto del bot
        app.bot_data['settings'] = settings
        app.bot_data['dz'] = dz
        app.bot_data['listener'] = listener
        app.bot_data['vault_chat_id'] = VAULT_CHATID
        
        # Registrar handlers
        app.add_handler(CommandHandler("start", start))
        app.add_handler(CommandHandler("config", configuracion))
        app.add_handler(CommandHandler("stats", stats_command))
        app.add_handler(CallbackQueryHandler(config_callback, pattern="^[0-9]+$"))
        app.add_handler(CallbackQueryHandler(process_search_callback, pattern="^(search|artist|artist_menu|download|back)"))
        app.add_handler(MessageHandler(
            filters.TEXT,
            lambda update, context: asyncio.create_task(
                handle_message_with_user_session(update, context, dz, settings, VAULT_CHATID, listener)
            )
        ))
        
        # Registrar handler de errores
        app.add_error_handler(error_handler)
        
        # Iniciar tarea de limpieza de sesiones inactivas
        asyncio.create_task(cleanup_sessions())
        logging.info("Tarea de limpieza de sesiones inactivas iniciada")
        
        await app.initialize()
        await app.start()
        await app.updater.start_polling()
        
        # Log inicial
        logging.info("Bot iniciado y listo para recibir mensajes")
        logging.info(f"Directorio de descargas: {os.path.abspath(DOWNLOAD_PATH)}")
        
        await asyncio.Event().wait()
        
    except Exception as e:
        logging.critical(f"Error crítico: {str(e)}", exc_info=True)
        
if __name__ == "__main__":
    asyncio.run(main())
