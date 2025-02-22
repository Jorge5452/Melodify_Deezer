import re
import logging
import os
from telegram import Update
from telegram.ext import ContextTypes
from vault import load_vault, save_vault
from downloader import download_track

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
        if "deezer.com" in url and "/track/" in url:
            vault_data = load_vault()
            
            track_id = re.search(r'/track/(\d+)', url).group(1)
            bitrate = settings["maxBitrate"]
            key = f"{track_id}_{bitrate}"
            
            if key in vault_data:
                await update.message.reply_audio(audio=vault_data[key])
                return
                
            file_path = await download_track(url, dz, settings, listener)
            
            with open(file_path, "rb") as f:
                sent_message = await context.bot.send_audio(
                    chat_id=vault_chat_id,
                    audio=f,
                    caption=key
                )
                # Actualizar y guardar JSON
                vault_data[key] = sent_message.audio.file_id
                save_vault(vault_data)
                logging.info(f"🎵 Nueva canción almacenada: {key}")
            
            await update.message.reply_audio(audio=vault_data[key])
            os.remove(file_path)
            
        else:
            await update.message.reply_text("🔗 Envía un enlace válido de Deezer")
            
    except Exception as e:
        logging.error(f"Error crítico: {str(e)}", exc_info=True)
        await update.message.reply_text("⚠️ Error procesando tu solicitud")