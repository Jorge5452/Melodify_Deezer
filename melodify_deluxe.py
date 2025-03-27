"""
Punto de entrada principal para la aplicación Melodify Deluxe.

Este script inicializa el bot de Telegram, configura la conexión con Deezer,
registra los handlers para procesar comandos y mensajes, y mantiene el bot
en funcionamiento.
"""

import os
import asyncio
import logging
from typing import Dict, Any, Optional, Tuple

# Componentes de Telegram
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)

# Componentes de Deezer
from deezer import Deezer
from deemix.settings import load, save

# Módulos propios
from user_session import cleanup_sessions, UserSession
from config import (
    TELEGRAM_TOKEN,
    DEEZER_ARL,
    VAULT_CHATID,
    DOWNLOAD_PATH,
    LOG_LEVEL,
    LOG_FORMAT
)

# Funcionalidades del bot
from downloader import LogListener
from bot import start, handle_message, configuracion, config_callback, process_search_callback, stats_command

# Configuración del sistema de logging
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format=LOG_FORMAT
)

# Reducir verbosidad de logs de bibliotecas externas
logging.getLogger("telegram").setLevel(logging.WARNING)
logging.getLogger("deemix").setLevel(logging.INFO)

async def error_handler(update: Optional[Any], context: Any) -> None:
    """
    Maneja excepciones que ocurren en los handlers del bot.
    """
    logging.error(f"Error al procesar la actualización {update}: {context.error}", exc_info=True)
    
    # Notificar al usuario si es posible
    if update and update.effective_message:
        await update.effective_message.reply_text(
            "❌ Algo salió mal. Inténtalo de nuevo por favor."
        )


async def handle_message_with_user_session(
                            update: Any,
                            context: Any, 
                            dz: Deezer,
                            settings: Dict[str, Any],
                            vault_chat_id: str,
                            listener: LogListener
                        ) -> None:
    """
    Wrapper para handle_message que gestiona la sesión de usuario y control de tasas.
    
    Args:
        update: Objeto de actualización de Telegram
        context: Contexto del handler
        dz: Instancia autenticada de Deezer
        settings: Configuración de deemix
        vault_chat_id: ID del chat para almacenar archivos en el vault
        listener: Instancia de LogListener para eventos de deemix
    """
    try:
        # Obtener ID del usuario
        user_id = update.effective_user.id
        
        # Obtener o crear sesión de usuario
        session = UserSession.get_session(user_id)
        session.update_activity()
        
        # Aplicar límite de tasa para evitar sobrecarga
        await session.wait_for_rate_limit()
        
        # Llamar a la función principal de manejo de mensajes
        await handle_message(update, context, dz, settings, vault_chat_id, listener)
    except Exception as e:
        logging.error(f"Error en handle_message_with_user_session: {e}", exc_info=True)
        await update.message.reply_text("❌ Error al procesar tu solicitud. Por favor, inténtalo de nuevo.")


async def main() -> None:
    """
    Función principal que inicializa y ejecuta el bot.
    
    Configura la conexión con Deezer, inicializa el bot de Telegram,
    registra los handlers y mantiene el bot en ejecución.
    """
    try:
        logging.info("Iniciando el bot...")
        
        # Verificar configuración de variables de entorno
        if not TELEGRAM_TOKEN:
            raise Exception("La variable de entorno TELEGRAM_TOKEN no está configurada en el archivo .env")
        logging.info("Token de Telegram encontrado")
        
        if not DEEZER_ARL:
            raise Exception("La variable de entorno DEEZER_AR no está configurada en el archivo .env")
        logging.info("ARL de Deezer encontrado")
        
        # Crear directorio de descargas
        logging.info(f"Creando directorio de descargas: {DOWNLOAD_PATH}")
        os.makedirs(DOWNLOAD_PATH, exist_ok=True)
        
        # Configurar deemix
        logging.info("Cargando configuración de deemix...")
        settings = load()
        settings["downloadLocation"] = os.path.abspath(DOWNLOAD_PATH)
        save(settings)
        
        # Inicializar y autenticar con Deezer
        logging.info("Iniciando sesión en Deezer...")
        dz = Deezer()
        if not dz.login_via_arl(DEEZER_ARL):
            raise Exception("Fallo en la autenticación: verifica tu ARL.")
        logging.info("Sesión iniciada exitosamente")
        
        # Crear listener para logs de deemix
        listener = LogListener()
        
        # Inicializar aplicación de Telegram
        logging.info("Creando aplicación de Telegram...")
        app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
        
        # Guardar componentes en el contexto global del bot
        app.bot_data['settings'] = settings
        app.bot_data['dz'] = dz
        app.bot_data['listener'] = listener
        app.bot_data['vault_chat_id'] = VAULT_CHATID
        
        # Registrar handlers para comandos
        app.add_handler(CommandHandler("start", start))
        app.add_handler(CommandHandler("config", configuracion))
        app.add_handler(CommandHandler("stats", stats_command))
        
        # Registrar handlers para callbacks
        app.add_handler(CallbackQueryHandler(config_callback, pattern="^[0-9]+$"))
        app.add_handler(CallbackQueryHandler(process_search_callback, pattern="^(search|artist|artist_menu|download|back)"))
        
        # Registrar handler para mensajes de texto
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
        
        # Inicializar y arrancar el bot
        await app.initialize()
        await app.start()
        await app.updater.start_polling()
        
        # Log de inicio exitoso
        logging.info("Bot iniciado y listo para recibir mensajes")
        logging.info(f"Directorio de descargas: {os.path.abspath(DOWNLOAD_PATH)}")
        
        # Mantener el bot en ejecución indefinidamente
        await asyncio.Event().wait()
        
    except Exception as e:
        logging.critical(f"Error crítico: {str(e)}", exc_info=True)
        
if __name__ == "__main__":
    asyncio.run(main())
