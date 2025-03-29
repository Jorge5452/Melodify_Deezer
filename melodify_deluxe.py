"""
Punto de entrada principal para la aplicación Melodify Deluxe.

Este script inicializa el bot de Telegram, configura la conexión con Deezer,
registra los handlers para procesar comandos y mensajes, y mantiene el bot
en funcionamiento.
"""

import os
import asyncio
import logging
import time
from typing import Dict, Any, Optional, Tuple

# Componentes de Telegram
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    JobQueue,
    ConversationHandler, 
    Application
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

# Wrapper personalizado para comandos que añade logging
async def command_wrapper(command_func, update, context):
    """
    Wrapper para comandos que añade logs detallados.
    """
    user_id = update.effective_user.id if update.effective_user else "desconocido"
    command = update.message.text if update.message else "callback"
    
    logging.info(f"[COMANDO] Recibido: {command} de usuario: {user_id} - timestamp: {time.time()}")
    
    try:
        result = await command_func(update, context)
        logging.info(f"[COMANDO] Completado: {command} de usuario: {user_id}")
        return result
    except Exception as e:
        logging.error(f"[COMANDO] Error en {command} de usuario {user_id}: {str(e)}", exc_info=True)
        raise

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
        message_text = update.message.text[:30] + "..." if len(update.message.text) > 30 else update.message.text
        
        logging.info(f"[MENSAJE] Recibido: '{message_text}' de usuario: {user_id} - timestamp: {time.time()}")
        
        # Obtener o crear sesión de usuario
        session = UserSession.get_session(user_id)
        session.update_activity()
        
        # Aplicar límite de tasa para evitar sobrecarga
        logging.info(f"[MENSAJE] Esperando límite de tasa para usuario: {user_id}")
        await session.wait_for_rate_limit()
        logging.info(f"[MENSAJE] Límite de tasa liberado para usuario: {user_id}")
        
        # Usar JobQueue para tareas pesadas
        # Primero enviar una respuesta inmediata
        logging.info(f"[MENSAJE] Procesando mensaje de usuario: {user_id} en JobQueue")
        
        # Para evitar bloquear, usamos el job_queue para procesar mensajes pesados
        if "job_queue" in context.application.bot_data and context.application.bot_data["job_queue"]:
            logging.info(f"[MENSAJE] Añadiendo a job_queue para usuario: {user_id}")
            
            # Crear un trabajo que se ejecute inmediatamente
            context.application.bot_data["job_queue"].run_once(
                lambda job_context: asyncio.create_task(
                    handle_message(update, context, dz, settings, vault_chat_id, listener)
                ),
                0  # Ejecutar inmediatamente
            )
            logging.info(f"[MENSAJE] Añadido con éxito a job_queue para usuario: {user_id}")
        else:
            # Llamar a la función principal de manejo de mensajes directamente
            logging.info(f"[MENSAJE] Sin job_queue disponible, procesando directamente para usuario: {user_id}")
            await handle_message(update, context, dz, settings, vault_chat_id, listener)
            
        logging.info(f"[MENSAJE] Handler completado para usuario: {user_id}")
        
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
        
        # Inicializar aplicación de Telegram con JobQueue
        logging.info("Creando aplicación de Telegram con JobQueue...")
        app = ApplicationBuilder().token(TELEGRAM_TOKEN).concurrent_updates(True).build()
        
        # Activar JobQueue para tareas pesadas
        job_queue = JobQueue()
        job_queue.set_application(app)
        app.bot_data["job_queue"] = job_queue
        await job_queue.start()
        logging.info("JobQueue iniciada correctamente")
        
        # Guardar componentes en el contexto global del bot
        app.bot_data['settings'] = settings
        app.bot_data['dz'] = dz
        app.bot_data['listener'] = listener
        app.bot_data['vault_chat_id'] = VAULT_CHATID
        
        # Registrar handlers para comandos con wrappers de logging
        logging.info("Registrando handlers de comandos...")
        app.add_handler(CommandHandler("start", lambda update, context: command_wrapper(start, update, context)))
        app.add_handler(CommandHandler("config", lambda update, context: command_wrapper(configuracion, update, context)))
        app.add_handler(CommandHandler("stats", lambda update, context: command_wrapper(stats_command, update, context)))
        
        # Registrar handlers para callbacks
        app.add_handler(CallbackQueryHandler(config_callback, pattern="^[0-9]+$"))
        app.add_handler(CallbackQueryHandler(process_search_callback, pattern="^(search|artist|artist_menu|download|back)"))
        
        # Registrar handler para mensajes de texto
        logging.info("Registrando handler de mensajes...")
        async def message_handler(update, context):
            # Pasar los datos necesarios desde el contexto global
            await handle_message_with_user_session(
                update, context, dz, settings, VAULT_CHATID, listener
            )
            
        app.add_handler(MessageHandler(filters.TEXT, message_handler))
        
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
