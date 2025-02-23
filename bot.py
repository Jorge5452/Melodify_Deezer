import re
import logging
import os
from telegram import Update
from telegram.ext import ContextTypes
from vault import load_vault, save_vault
from downloader import download_track
from deemix.settings import load, save

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Envía un enlace de Deezer para descargar una canción.")

async def handle_message(
    update: Update, 
    context: ContextTypes.DEFAULT_TYPE, 
    dz, 
    settings, 
    vault_chat_id, 
    listener
):
    try:
        url = update.message.text.strip()
        if "deezer.com" in url and ("/track/" in url or "/album/" in url or "/playlist/" in url):
            vault_data = load_vault()
            if "/track/" in url:
                track_id = re.search(r'/track/(\d+)', url).group(1)
                bitrate = settings["maxBitrate"]
                key = f"{track_id}_{bitrate}"
            else:
                # Para album y playlist usamos la URL como llave
                key = url

            if key in vault_data:
                if "/track/" in url:
                    await update.message.reply_audio(audio=vault_data[key])
                else:
                    await update.message.reply_text("Este album/playlist ya fue descargado anteriormente.")
                return

            file_path = await download_track(url, dz, settings, listener)

            if "/track/" in url:
                with open(file_path, "rb") as f:
                    sent_message = await context.bot.send_audio(
                        chat_id=vault_chat_id,
                        audio=f,
                        caption=key
                    )
                    # Guardar y actualizar vault JSON
                    vault_data[key] = sent_message.audio.file_id
                    save_vault(vault_data)
                    await update.message.reply_audio(audio=vault_data[key])
            else:
                # En album/playlist se notifica la descarga sin enviar audio individualmente
                await update.message.reply_text("Album/Playlist descargado correctamente.")
            os.remove(file_path)
        else:
            await update.message.reply_text("🔗 Envía un enlace válido de Deezer")
    except Exception as e:
        logging.error(f"Error crítico: {str(e)}", exc_info=True)
        await update.message.reply_text("⚠️ Error procesando tu solicitud")