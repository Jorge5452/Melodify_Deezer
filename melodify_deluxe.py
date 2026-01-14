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
import signal
import argparse
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
from user_session import cleanup_sessions, UserSession, requires_role
from config import (
    TELEGRAM_TOKEN,
    DEEZER_ARL,
    VAULT_CHATID,
    DOWNLOAD_PATH,
    LOG_LEVEL,
    LOG_FORMAT
)

# Funcionalidades del bot - Importadas directamente desde modules
from modules import start, handle_message, configuracion, config_callback, process_search_callback, stats_command
from modules.decorators import with_error_handling
from modules.queue_manager import QueueManager
from downloader import LogListener

# Nuevo módulo para gestión centralizada de logs
from modules.log_manager import initialize_logging, silence_http_logs, silence_telegram_logs

# Nuevos módulos para sistema de roles
from modules.admin_commands import (
    admin_help, cmd_set_role, set_role_user_id, set_role_confirm, 
    cancel_conversation, cmd_user_info, admin_stats, handle_admin_callback, 
    cmd_maintenance, cmd_broadcast, broadcast_confirm, cmd_system,
    cmd_session_stats, WAITING_FOR_USER_ID, WAITING_FOR_ROLE
)
from modules.premium_commands import (
    premium_help, premium_stats, premium_audio_options, 
    handle_premium_callback
)

# Función para configurar logging basada en argumentos
def setup_logging(debug_mode: bool = False):
    """
    Configura el sistema de logging basándose en el modo de ejecución.
    
    Args:
        debug_mode (bool): Si es True, activa el modo debug/desarrollo.
                           Si es False, usa el modo producción.
    """
    preset = "development" if debug_mode else "production"
    
    # Inicializar el sistema de logging usando el nuevo módulo centralizado
    initialize_logging(
        log_level=LOG_LEVEL,
        log_file="melodify.log",
        enable_console=True,
        preset=preset
    )
    
    # Configuración específica según el modo
    if not debug_mode:
        # En producción, silenciar loggers ruidosos
        silence_http_logs()  # Silenciar logs de HTTP y conexiones
        silence_telegram_logs()  # Silenciar logs de Telegram API
        print("✅ Modo PRODUCCIÓN activo: Logs ruidosos silenciados")
    else:
        print("🐞 Modo DEBUG activo: Todos los logs habilitados")
    
    # Configurar niveles específicos adicionales comunes a ambos modos
    logging.getLogger("deemix").setLevel(logging.INFO)
    
    # En debug, message_manager puede ser más verboso
    msg_mgr_level = logging.DEBUG if debug_mode else logging.INFO
    logging.getLogger('modules.message_manager').setLevel(msg_mgr_level)

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

async def handle_message_wrapper(update: Any, context: Any) -> None:
    """
    Wrapper para handle_message que pasa los datos necesarios desde el contexto global.
    """
    # Verificar modo mantenimiento
    maintenance_mode = context.bot_data.get("maintenance_mode", False)
    if maintenance_mode:
        # En modo mantenimiento, solo permitir usuarios premium y admin
        user_id = update.effective_user.id
        session = UserSession.get_session(user_id)
        
        if not session.has_permission("premium"):
            await update.message.reply_text(
                "🛠️ *El bot está en mantenimiento* 🛠️\n\n"
                "En este momento solo los usuarios premium y administradores pueden usar el bot.\n"
                "Por favor, inténtalo más tarde.",
                parse_mode="Markdown"
            )
            return
            
    # Obtener componentes del contexto global
    dz = context.bot_data.get('dz')
    settings = context.bot_data.get('settings')
    listener = context.bot_data.get('listener')
    vault_chat_id = context.bot_data.get('vault_chat_id')
    
    # Llamar a la función principal
    await handle_message(update, context, dz, settings, vault_chat_id, listener)

async def shutdown(app: Application) -> None:
    """
    Realizar tareas de limpieza al detener el bot.
    
    Esta función se ejecuta cuando se recibe una señal de terminación
    y garantiza un cierre limpio de todas las conexiones y tareas.
    
    Args:
        app: Instancia de la aplicación de Telegram
    """
    logging.info("Iniciando apagado controlado del bot...")
    
    # Guardar sesiones en la base de datos si está disponible
    try:
        from user_session import UserSession
        if UserSession._use_database:
            # Importar aquí para evitar errores si no está disponible
            import db_manager
            
            # Migrar todas las sesiones actuales a la BD
            session_count = len(UserSession._sessions)
            if session_count > 0:
                logging.info(f"Guardando {session_count} sesiones en la base de datos...")
                migrated = db_manager.migrate_memory_sessions_to_db(UserSession._sessions)
                logging.info(f"Guardadas {migrated} de {session_count} sesiones")
    except Exception as e:
        logging.error(f"Error guardando sesiones: {str(e)}", exc_info=True)
    
    # Detener primero el updater para dejar de recibir mensajes
    logging.info("Deteniendo updater...")
    if app.updater:
        await app.updater.stop()
    
    # Detener todas las colas de tareas
    logging.info("Deteniendo colas de tareas...")
    queue_manager = QueueManager.get_instance()
    await queue_manager.stop_all_queues()
    
    # Detener job_queue
    logging.info("Deteniendo JobQueue...")
    if "job_queue" in app.bot_data and app.bot_data["job_queue"]:
        await app.bot_data["job_queue"].stop()
    
    # Detener la aplicación
    logging.info("Deteniendo aplicación...")
    await app.stop()
    
    logging.info("Apagado completo. ¡Hasta pronto!")

async def main() -> Application:
    """
    Función principal que inicializa y ejecuta el bot.
    
    Configura la conexión con Deezer, inicializa el bot de Telegram,
    registra los handlers y mantiene el bot en ejecución.
    
    Returns:
        Application: La instancia de la aplicación de Telegram
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
        
        # Inicializar la base de datos si está disponible
        db_initialized = False
        try:
            import db_manager
            db_manager.initialize_database()
            db_initialized = True
            logging.info("Base de datos inicializada correctamente")
        except ImportError:
            logging.warning("Módulo db_manager no disponible: funcionando sin persistencia")
        
        # Si la BD está disponible, activar persistencia y cargar sesiones
        if db_initialized:
            from user_session import UserSession
            UserSession.enable_persistence(True)
            # Ya no cargamos todas las sesiones al inicio - Carga diferida
            logging.info("Persistencia de sesiones activada con carga diferida")
            
            # Configurar tamaño de caché según recursos disponibles
            try:
                import psutil
                available_memory = psutil.virtual_memory().available / (1024 * 1024)  # En MB
                if available_memory > 1024:  # Más de 1GB
                    # En sistemas con más memoria, permitir más sesiones en memoria
                    UserSession._sessions.maxsize = 200
                    logging.info(f"Tamaño de caché ajustado a 200 sesiones (RAM disponible: {available_memory:.0f}MB)")
                elif available_memory < 512:  # Menos de 512MB
                    # En sistemas con poca memoria, reducir la cantidad de sesiones
                    UserSession._sessions.maxsize = 50
                    logging.info(f"Tamaño de caché reducido a 50 sesiones (RAM disponible: {available_memory:.0f}MB)")
                else:
                    # En sistemas intermedios, mantener el valor predeterminado
                    logging.info(f"Tamaño de caché mantenido en {UserSession._sessions.maxsize} sesiones")
            except ImportError:
                logging.info("No se pudo importar psutil. Usando tamaño de caché predeterminado")
        
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
        
        # Inicializar el gestor de colas
        logging.info("Inicializando gestor de colas...")
        queue_manager = QueueManager.get_instance()
        
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
        app.bot_data['queue_manager'] = queue_manager
        app.bot_data['maintenance_mode'] = False  # Inicialmente desactivado
        
        # Registrar handlers para comandos básicos (ya decorados en sus módulos)
        logging.info("Registrando handlers de comandos...")
        app.add_handler(CommandHandler("start", start))
        app.add_handler(CommandHandler("config", configuracion))
        app.add_handler(CommandHandler("stats", stats_command))
        
        # Registrar handlers para callbacks de configuración
        app.add_handler(CallbackQueryHandler(config_callback, pattern="^[0-9]+$"))
        app.add_handler(CallbackQueryHandler(process_search_callback, pattern="^(search|artist|artist_menu|download|back)"))
        
        # Registrar handlers para comandos premium
        app.add_handler(CommandHandler("premium", premium_help))
        app.add_handler(CommandHandler("premium_stats", premium_stats))
        app.add_handler(CommandHandler("premium_audio", premium_audio_options))
        app.add_handler(CallbackQueryHandler(handle_premium_callback, pattern="^premium_"))
        
        # Registrar handlers para comandos de administración
        app.add_handler(CommandHandler("admin", requires_role("admin")(admin_help)))
        app.add_handler(CommandHandler("stats_admin", admin_stats))
        app.add_handler(CommandHandler("maintenance", cmd_maintenance))
        app.add_handler(CommandHandler("userinfo", cmd_user_info))
        app.add_handler(CommandHandler("system", requires_role("admin")(cmd_system)))
        app.add_handler(CommandHandler("session_stats", requires_role("admin")(cmd_session_stats)))
        app.add_handler(CallbackQueryHandler(handle_admin_callback, pattern="^admin_"))
        
        # Handler para el comando broadcast (en dos pasos)
        app.add_handler(CommandHandler("broadcast", cmd_broadcast))
        app.add_handler(MessageHandler(
            filters.TEXT & filters.Regex(r'^confirmar$') & ~filters.COMMAND,
            broadcast_confirm
        ))
        
        # Conversación para establecer rol
        setrole_conv_handler = ConversationHandler(
            entry_points=[CommandHandler("setrole", cmd_set_role)],
            states={
                WAITING_FOR_USER_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_role_user_id)],
                WAITING_FOR_ROLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_role_confirm)],
            },
            fallbacks=[CommandHandler("cancel", cancel_conversation)]
        )
        app.add_handler(setrole_conv_handler)
        
        # Registrar handler para mensajes de texto
        logging.info("Registrando handler de mensajes...")
        app.add_handler(MessageHandler(filters.TEXT, handle_message_wrapper))
        
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
        
        # Devolver la instancia de la aplicación para poder acceder a ella desde el manejador de señales
        return app
        
    except Exception as e:
        logging.critical(f"Error crítico: {str(e)}", exc_info=True)
        
        # Intentar guardar sesiones en caso de error
        try:
            if 'db_initialized' in locals() and db_initialized:
                from user_session import UserSession
                if UserSession._use_database:
                    import db_manager
                    session_count = len(UserSession._sessions)
                    if session_count > 0:
                        logging.info(f"Guardando {session_count} sesiones antes de terminar...")
                        migrated = db_manager.migrate_memory_sessions_to_db(UserSession._sessions)
                        logging.info(f"Guardadas {migrated} de {session_count} sesiones")
        except Exception as save_error:
            logging.error(f"Error guardando sesiones: {save_error}")


def parse_arguments():
    """Parsea los argumentos de línea de comandos."""
    parser = argparse.ArgumentParser(description="Melodify Deluxe Bot")
    parser.add_argument(
        "--debug", 
        action="store_true", 
        help="Activa el modo debug con logs detallados"
    )
    return parser.parse_args()

if __name__ == "__main__":
    # Parsear argumentos antes de iniciar
    args = parse_arguments()
    
    # Configurar logging según los argumentos
    setup_logging(args.debug)

    # Configurar manejo de señales para cierre controlado
    try:
        import platform
        loop = asyncio.get_event_loop()
        app = None  # Variable para almacenar la aplicación
        
        # Definir handler que se ejecutará cuando se reciba una señal de terminación
        async def signal_handler():
            if app:
                logging.info("Señal de terminación recibida, iniciando apagado controlado...")
                await shutdown(app)
                loop.stop()
        
        # Registrar manejadores de señales de forma compatible con cada plataforma
        if platform.system() == "Windows":
            # En Windows, usar eventos de control de consola
            try:
                import win32api
                
                def win_handler(ctrl_type):
                    if ctrl_type in (0, 2):  # CTRL_C_EVENT o CTRL_BREAK_EVENT
                        logging.info("Evento de control detectado en Windows")
                        asyncio.create_task(signal_handler())
                        return True  # No propagar el evento
                    return False
                    
                win32api.SetConsoleCtrlHandler(win_handler, True)
                logging.info("Manejador de eventos de control de Windows registrado")
            except ImportError:
                logging.warning("No se pudo importar win32api. El cierre controlado podría no funcionar en Windows.")
                # Fallar silenciosamente y continuar
        else:
            # En Linux/Unix, usar señales estándar
            for sig in (signal.SIGINT, signal.SIGTERM):
                loop.add_signal_handler(sig, lambda: asyncio.create_task(signal_handler()))
            logging.info("Manejadores de señales POSIX registrados")
            
        # Ejecutar el bot y guardar la referencia a la aplicación para manejo de señales
        async def run_bot():
            global app
            app = await main()
            # Mantener la aplicación en ejecución hasta que se reciba una señal
            await asyncio.Event().wait()
            
        asyncio.run(run_bot())
    except KeyboardInterrupt:
        logging.info("Interrupción de teclado detectada, cerrando...")
    except Exception as e:
        logging.critical(f"Error fatal: {str(e)}", exc_info=True)
        # Intentar un cierre limpio si es posible
        if 'app' in locals() and app:
            try:
                loop = asyncio.get_event_loop()
                loop.run_until_complete(shutdown(app))
            except Exception as shutdown_error:
                logging.error(f"Error durante el cierre: {str(shutdown_error)}")
else:
    # Comportamiento para importación como módulo
    pass
