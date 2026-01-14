# -*- coding: utf-8 -*-
"""
Main entry point for Melodify Deluxe application.

This module initializes the Telegram bot, sets up Deezer connection,
registers handlers for commands and messages, and keeps the bot running.

This is the new modular entry point that bridges the refactored architecture
with existing modules during the migration period.
"""

import os
import asyncio
import logging
import argparse
from typing import Any, Optional

# Telegram components
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

# Deezer components
from deezer import Deezer
from deemix.settings import load, save

# New modular imports
from src.config import (
    TELEGRAM_TOKEN,
    DEEZER_ARL,
    VAULT_CHATID,
    DOWNLOAD_PATH,
    LOG_LEVEL
)
from src.infrastructure.logging import initialize_logging, silence_http_logs, silence_telegram_logs
from src.infrastructure.database import db_service
from src.infrastructure.deezer import LogListener
from src.core.services import UserSession, cleanup_sessions
from src.core.services.queue_service import QueueManager

# Interface handlers (newly migrated)
from src.interface.telegram.handlers import (
    start,
    configuracion,
    config_callback,
    stats_command,
    # Admin handlers
    admin_help,
    cmd_set_role,
    set_role_user_id,
    set_role_confirm,
    cancel_conversation,
    cmd_user_info,
    admin_stats,
    handle_admin_callback,
    cmd_maintenance,
    cmd_broadcast,
    broadcast_confirm,
    cmd_system,
    cmd_session_stats,
    WAITING_FOR_USER_ID,
    WAITING_FOR_ROLE,
    # Premium handlers
    premium_help,
    premium_stats,
    premium_audio_options,
    handle_premium_callback,
    # Message handler
    handle_message,
)

# Callbacks (newly migrated)
from src.interface.telegram.callbacks import process_search_callback


def setup_logging(debug_mode: bool = False) -> None:
    """
    Configures the logging system based on execution mode.
    
    Args:
        debug_mode: If True, enables debug/development mode.
                   If False, uses production mode.
    """
    preset = "development" if debug_mode else "production"
    
    # Initialize logging using new centralized module
    initialize_logging(
        log_level=LOG_LEVEL,
        log_file="melodify.log",
        enable_console=True,
        preset=preset
    )
    
    # Mode-specific configuration
    if not debug_mode:
        # In production, silence noisy loggers
        silence_http_logs()
        silence_telegram_logs()
        print("✅ PRODUCTION mode active: Noisy logs silenced")
    else:
        print("🐞 DEBUG mode active: All logs enabled")
    
    # Set specific levels common to both modes
    logging.getLogger("deemix").setLevel(logging.INFO)
    
    # In debug, message_manager can be more verbose
    msg_mgr_level = logging.DEBUG if debug_mode else logging.INFO
    logging.getLogger('modules.message_manager').setLevel(msg_mgr_level)


async def error_handler(update: Optional[Any], context: Any) -> None:
    """Handles exceptions in bot handlers."""
    logging.error(f"Error processing update {update}: {context.error}", exc_info=True)
    
    if update and update.effective_message:
        await update.effective_message.reply_text(
            "❌ Something went wrong. Please try again."
        )


async def handle_message_wrapper(update: Any, context: Any) -> None:
    """
    Wrapper for handle_message that passes necessary data from global context.
    """
    # Check maintenance mode
    maintenance_mode = context.bot_data.get("maintenance_mode", False)
    if maintenance_mode:
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
    
    # Get components from global context
    dz = context.bot_data.get('dz')
    settings = context.bot_data.get('settings')
    listener = context.bot_data.get('listener')
    vault_chat_id = context.bot_data.get('vault_chat_id')
    
    await handle_message(update, context, dz, settings, vault_chat_id, listener)


async def shutdown(app: Application) -> None:
    """
    Performs cleanup tasks when stopping the bot.
    """
    logging.info("Starting controlled shutdown...")
    
    # Save sessions to database if available
    try:
        if UserSession._use_database:
            session_count = len(UserSession._sessions)
            if session_count > 0:
                logging.info(f"Saving {session_count} sessions to database...")
                migrated = db_service.migrate_memory_sessions_to_db(UserSession._sessions)
                logging.info(f"Saved {migrated} of {session_count} sessions")
    except Exception as e:
        logging.error(f"Error saving sessions: {str(e)}", exc_info=True)
    
    # Stop updater first
    logging.info("Stopping updater...")
    if app.updater:
        await app.updater.stop()
    
    # Stop all task queues
    logging.info("Stopping task queues...")
    queue_manager = QueueManager.get_instance()
    await queue_manager.stop_all_queues()
    
    # Stop job_queue
    logging.info("Stopping JobQueue...")
    if "job_queue" in app.bot_data and app.bot_data["job_queue"]:
        await app.bot_data["job_queue"].stop()
    
    # Stop application
    logging.info("Stopping application...")
    await app.stop()
    
    logging.info("Shutdown complete. Goodbye!")


async def main() -> Application:
    """
    Main function that initializes and runs the bot.
    
    Returns:
        Application: Telegram application instance
    """
    try:
        logging.info("Starting bot...")
        
        # Verify environment variables
        if not TELEGRAM_TOKEN:
            raise Exception("TELEGRAM_TOKEN environment variable not configured in .env")
        logging.info("Telegram token found")
        
        if not DEEZER_ARL:
            raise Exception("DEEZER_ARL environment variable not configured in .env")
        logging.info("Deezer ARL found")
        
        # Initialize database if available
        db_initialized = False
        try:
            db_service.initialize_database()
            db_initialized = True
        except Exception as e:
            logging.warning(f"Database initialization failed: {e}. Running without persistence")
        
        # Enable persistence and lazy loading
        if db_initialized:
            UserSession.enable_persistence(True)
            logging.info("Session persistence enabled with lazy loading")
            
            # Adjust cache size based on available resources
            try:
                import psutil
                available_memory = psutil.virtual_memory().available / (1024 * 1024)
                if available_memory > 1024:
                    UserSession._sessions.maxsize = 200
                    logging.info(f"Cache size adjusted to 200 sessions (RAM: {available_memory:.0f}MB)")
                elif available_memory < 512:
                    UserSession._sessions.maxsize = 50
                    logging.info(f"Cache size reduced to 50 sessions (RAM: {available_memory:.0f}MB)")
            except ImportError:
                logging.info("psutil not available. Using default cache size")
        
        # Create downloads directory
        logging.info(f"Creating downloads directory: {DOWNLOAD_PATH}")
        os.makedirs(DOWNLOAD_PATH, exist_ok=True)
        
        # Configure deemix
        logging.info("Loading deemix configuration...")
        settings = load()
        settings["downloadLocation"] = os.path.abspath(DOWNLOAD_PATH)
        save(settings)
        
        # Initialize and authenticate with Deezer
        logging.info("Logging into Deezer...")
        dz = Deezer()
        if not dz.login_via_arl(DEEZER_ARL):
            raise Exception("Authentication failed: verify your ARL.")
        logging.info("Login successful")
        
        # Create deemix log listener
        listener = LogListener()
        
        # Initialize queue manager
        logging.info("Initializing queue manager...")
        queue_manager = QueueManager.get_instance()
        
        # Initialize Telegram application with JobQueue
        logging.info("Creating Telegram application with JobQueue...")
        app = ApplicationBuilder().token(TELEGRAM_TOKEN).concurrent_updates(True).build()
        
        # Enable JobQueue for heavy tasks
        job_queue = JobQueue()
        job_queue.set_application(app)
        app.bot_data["job_queue"] = job_queue
        await job_queue.start()
        logging.info("JobQueue started successfully")
        
        # Store components in global bot context
        app.bot_data['settings'] = settings
        app.bot_data['dz'] = dz
        app.bot_data['listener'] = listener
        app.bot_data['vault_chat_id'] = VAULT_CHATID
        app.bot_data['queue_manager'] = queue_manager
        app.bot_data['maintenance_mode'] = False
        
        # Register basic command handlers
        logging.info("Registering command handlers...")
        app.add_handler(CommandHandler("start", start))
        app.add_handler(CommandHandler("config", configuracion))
        app.add_handler(CommandHandler("stats", stats_command))
        
        # Register config callbacks
        app.add_handler(CallbackQueryHandler(config_callback, pattern="^[0-9]+$"))
        app.add_handler(CallbackQueryHandler(process_search_callback, pattern="^(search|artist|artist_menu|download|back)"))
        
        # Register premium command handlers
        app.add_handler(CommandHandler("premium", premium_help))
        app.add_handler(CommandHandler("premium_stats", premium_stats))
        app.add_handler(CommandHandler("premium_audio", premium_audio_options))
        app.add_handler(CallbackQueryHandler(handle_premium_callback, pattern="^premium_"))
        
        # Register admin command handlers
        app.add_handler(CommandHandler("admin", admin_help))
        app.add_handler(CommandHandler("stats_admin", admin_stats))
        app.add_handler(CommandHandler("maintenance", cmd_maintenance))
        app.add_handler(CommandHandler("userinfo", cmd_user_info))
        app.add_handler(CommandHandler("system", cmd_system))
        app.add_handler(CommandHandler("session_stats", cmd_session_stats))
        app.add_handler(CallbackQueryHandler(handle_admin_callback, pattern="^admin_"))
        
        # Broadcast command handler
        app.add_handler(CommandHandler("broadcast", cmd_broadcast))
        app.add_handler(MessageHandler(
            filters.TEXT & filters.Regex(r'^confirmar$') & ~filters.COMMAND,
            broadcast_confirm
        ))
        
        # Set role conversation handler
        setrole_conv_handler = ConversationHandler(
            entry_points=[CommandHandler("setrole", cmd_set_role)],
            states={
                WAITING_FOR_USER_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_role_user_id)],
                WAITING_FOR_ROLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_role_confirm)],
            },
            fallbacks=[CommandHandler("cancel", cancel_conversation)]
        )
        app.add_handler(setrole_conv_handler)
        
        # Register text message handler
        logging.info("Registering message handler...")
        app.add_handler(MessageHandler(filters.TEXT, handle_message_wrapper))
        
        # Register error handler
        app.add_error_handler(error_handler)
        
        # Start inactive session cleanup task
        asyncio.create_task(cleanup_sessions())
        logging.info("Inactive session cleanup task started")
        
        # Initialize and start bot
        await app.initialize()
        await app.start()
        await app.updater.start_polling()
        
        logging.info("Bot started and ready to receive messages")
        logging.info(f"Downloads directory: {os.path.abspath(DOWNLOAD_PATH)}")
        
        return app
        
    except Exception as e:
        logging.critical(f"Critical error: {str(e)}", exc_info=True)
        raise


def parse_arguments():
    """Parses command line arguments."""
    parser = argparse.ArgumentParser(description="Melodify Deluxe Bot")
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enables debug mode with detailed logs"
    )
    return parser.parse_args()


def run():
    """Entry point function to run the bot."""
    args = parse_arguments()
    setup_logging(args.debug)
    
    try:
        import platform
        loop = asyncio.get_event_loop()
        app = None
        
        async def signal_handler():
            if app:
                logging.info("Termination signal received, starting controlled shutdown...")
                await shutdown(app)
                loop.stop()
        
        # Platform-specific signal handlers
        if platform.system() != "Windows":
            import signal
            for sig in (signal.SIGINT, signal.SIGTERM):
                loop.add_signal_handler(sig, lambda: asyncio.create_task(signal_handler()))
            logging.info("POSIX signal handlers registered")
        
        async def run_bot():
            nonlocal app
            app = await main()
            await asyncio.Event().wait()
        
        asyncio.run(run_bot())
    except KeyboardInterrupt:
        logging.info("Keyboard interrupt detected, closing...")
    except Exception as e:
        logging.critical(f"Fatal error: {str(e)}", exc_info=True)


if __name__ == "__main__":
    run()
