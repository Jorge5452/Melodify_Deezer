import os
import asyncio
import logging
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    filters,
)
from deezer import Deezer
from deemix.settings import load, save
import config
from config import TELEGRAM_TOKEN, DEEZER_AR, VAULT_CHATID


from downloader import LogListener
from bot import start, handle_message

# Configuración del logging con formato claro
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

BOT_TOKEN = TELEGRAM_TOKEN
DOWNLOAD_PATH = "./descargas"

logging.getLogger("telegram").setLevel(logging.WARNING)
logging.getLogger("deemix").setLevel(logging.INFO)

settings = load()
settings["downloadLocation"] = os.path.abspath(DOWNLOAD_PATH)
save(settings)

dz = Deezer()
if not dz.login_via_arl(DEEZER_AR):
    raise Exception("Fallo en la autenticación: verifica tu ARL.")

listener = LogListener()

async def main():
    os.makedirs(DOWNLOAD_PATH, exist_ok=True)
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    
    # Sincronizar vault al iniciar
    ###vault_data = await sync_vault_from_channel(app.bot, VAULT_CHATID)
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(
        filters.TEXT,
        lambda u, c: handle_message(u, c, dz, settings, VAULT_CHATID, listener)
    ))
    
    await app.initialize()
    await app.start()
    await app.updater.start_polling()
    await asyncio.Event().wait()
    
if __name__ == "__main__":
    asyncio.run(main())
