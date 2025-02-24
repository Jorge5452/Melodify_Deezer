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
from config import TELEGRAM_TOKEN, DEEZER_AR, VAULT_CHATID


from downloader import LogListener
from bot import start, handle_message, configuracion, config_callback

# Configuración del logging con formato claro
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

BOT_TOKEN = TELEGRAM_TOKEN
DOWNLOAD_PATH = "./descargas"

logging.getLogger("telegram").setLevel(logging.WARNING)
logging.getLogger("deemix").setLevel(logging.INFO)

async def error_handler(update, context):
    """Maneja excepciones que ocurren en los handlers."""
    logging.error(f"Error al procesar la actualización {update}: {context.error}", exc_info=True)
    if update and update.effective_message:
        await update.effective_message.reply_text("⚠️ Ocurrió un error al procesar tu solicitud. Inténtalo de nuevo más tarde.")

async def main():
    try:
        os.makedirs(DOWNLOAD_PATH, exist_ok=True)
        
        # Configurar settings
        settings = load()
        settings["downloadLocation"] = os.path.abspath(DOWNLOAD_PATH)
        save(settings)
        
        # Inicializar Deezer
        dz = Deezer()
        if not dz.login_via_arl(DEEZER_AR):
            raise Exception("Fallo en la autenticación: verifica tu ARL.")
        
        listener = LogListener()
        
        app = ApplicationBuilder().token(BOT_TOKEN).build()
        
        # Guardar settings en el contexto del bot
        app.bot_data['settings'] = settings
        
        # Registrar handlers
        app.add_handler(CommandHandler("start", start))
        app.add_handler(CommandHandler("config", configuracion))
        app.add_handler(CallbackQueryHandler(config_callback))
        app.add_handler(MessageHandler(
            filters.TEXT,
            lambda u, c: handle_message(u, c, dz, settings, VAULT_CHATID, listener)
        ))
        
        # Registrar handler de errores
        app.add_error_handler(error_handler)
        
        await app.initialize()
        await app.start()
        await app.updater.start_polling()
        await asyncio.Event().wait()
        
    except Exception as e:
        logging.critical(f"Error crítico: {str(e)}", exc_info=True)
        
if __name__ == "__main__":
    asyncio.run(main())
