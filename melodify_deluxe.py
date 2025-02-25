import os
import asyncio
import logging
from dotenv import load_dotenv
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)
from deezer import Deezer
from deemix.settings import load, save
# Importar aiohttp para el servidor web simple
from aiohttp import web

# Cargar variables de entorno desde .env
load_dotenv()

# Obtener variables de entorno
BOT_TOKEN = os.environ.get("TELEGRAM_TOKEN")
DEEZER_AR = os.environ.get("DEEZER_AR")
VAULT_CHATID = os.environ.get("VAULT_CHATID")
# Obtener el puerto de Render (o usar 8080 como predeterminado)
PORT = int(os.environ.get("PORT", 8080))

from downloader import LogListener
from bot import start, handle_message, configuracion, config_callback, process_search_callback

# Configuración del logging con formato claro
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

DOWNLOAD_PATH = "./descargas"

logging.getLogger("telegram").setLevel(logging.WARNING)
logging.getLogger("deemix").setLevel(logging.INFO)

# Crear la aplicación web
async def create_web_app():
    app = web.Application()
    app.router.add_get('/', health_check)
    app.router.add_get('/ping', ping_handler)
    return app

# Endpoint simple para health checks
async def health_check(request):
    return web.Response(text="¡Melodify Deluxe está funcionando correctamente!", status=200)

# Endpoint adicional para pings periódicos
async def ping_handler(request):
    return web.Response(text="pong", status=200)

async def error_handler(update, context):
    """Maneja excepciones que ocurren en los handlers."""
    logging.error(f"Error al procesar la actualización {update}: {context.error}", exc_info=True)
    if update and update.effective_message:
        await update.effective_message.reply_text("⚠️ Ocurrió un error al procesar tu solicitud. Inténtalo de nuevo más tarde.")

async def main():
    try:
        # Verificar que las variables de entorno estén configuradas
        if not BOT_TOKEN:
            raise Exception("La variable de entorno TELEGRAM_TOKEN no está configurada en el archivo .env")
        if not DEEZER_AR:
            raise Exception("La variable de entorno DEEZER_AR no está configurada en el archivo .env")
        
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
        
        # Guardar settings y componentes en el contexto del bot
        app.bot_data['settings'] = settings
        app.bot_data['dz'] = dz
        app.bot_data['listener'] = listener
        app.bot_data['vault_chat_id'] = VAULT_CHATID
        
        # Registrar handlers
        app.add_handler(CommandHandler("start", start))
        app.add_handler(CommandHandler("config", configuracion))
        app.add_handler(CallbackQueryHandler(config_callback, pattern="^[0-9]+$"))
        app.add_handler(CallbackQueryHandler(process_search_callback, pattern="^(search|artist|artist_menu|download|back)"))
        app.add_handler(MessageHandler(
            filters.TEXT,
            lambda u, c: handle_message(u, c, dz, settings, VAULT_CHATID, listener)
        ))
        
        # Registrar handler de errores
        app.add_error_handler(error_handler)
        
        # Iniciar el bot de Telegram
        await app.initialize()
        await app.start()
        await app.updater.start_polling()
        
        # Iniciar el servidor web para mantener vivo el servicio en Render
        web_app = await create_web_app()
        runner = web.AppRunner(web_app)
        await runner.setup()
        site = web.TCPSite(runner, '0.0.0.0', PORT)
        await site.start()
        
        logging.info(f"Servidor web iniciado en http://0.0.0.0:{PORT}")
        logging.info(f"Health check disponible en http://0.0.0.0:{PORT}/")
        logging.info(f"Endpoint de ping disponible en http://0.0.0.0:{PORT}/ping")
        
        # Mantener la aplicación en ejecución
        await asyncio.Event().wait()
        
    except Exception as e:
        logging.critical(f"Error crítico: {str(e)}", exc_info=True)
        
if __name__ == "__main__":
    asyncio.run(main())
