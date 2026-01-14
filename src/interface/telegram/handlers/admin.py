# -*- coding: utf-8 -*-
"""
Administration commands for Melodify Deluxe.

This module provides commands reserved for administrators and functions
for managing user roles, advanced statistics and maintenance.
"""

import logging
import time
import asyncio
from datetime import datetime

from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes, ConversationHandler

from src.core.services import UserSession, requires_role
from src.core.services.queue_service import QueueManager

# Conversation states
WAITING_FOR_USER_ID = 1
WAITING_FOR_ROLE = 2


@requires_role("admin")
async def admin_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Shows help about available administrative commands.
    
    Only visible to administrators.
    """
    help_text = """
🛠️ *Comandos de Administración* 🛠️

*/setrole* - Establecer o cambiar el rol de un usuario
*/userinfo* - Ver información detallada de un usuario
*/stats_admin* - Estadísticas detalladas del sistema
*/broadcast* - Enviar mensaje a todos los usuarios
*/system* - Ver estado del sistema y recursos
*/maintenance* - Activar/desactivar modo mantenimiento
*/session_stats* - Ver estadísticas detalladas del sistema de gestión de sesiones

Recuerda usar estos comandos con responsabilidad.
"""
    await update.message.reply_text(help_text, parse_mode="Markdown")


@requires_role("admin")
async def cmd_set_role(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Starts the process to change a user's role.
    
    Command: /setrole
    """
    # Check for arguments (user ID and role)
    if context.args and len(context.args) == 2:
        try:
            # Format: /setrole <user_id> <role>
            user_id = int(context.args[0])
            role = context.args[1].lower()
            
            # Validate role
            if role not in ["normal", "premium", "admin"]:
                await update.message.reply_text(
                    "❌ Rol no válido. Opciones: normal, premium, admin"
                )
                return ConversationHandler.END
                
            # Update role
            return await set_user_role(update, context, user_id, role)
        except ValueError:
            await update.message.reply_text(
                "❌ ID de usuario no válido. Debe ser un número."
            )
            return ConversationHandler.END
    
    # If no complete arguments, start conversation
    await update.message.reply_text(
        "🔄 Por favor, envía el ID del usuario cuyo rol deseas cambiar:"
    )
    return WAITING_FOR_USER_ID


async def set_role_user_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Processes the user ID sent to change their role.
    """
    try:
        user_id = int(update.message.text.strip())
        context.user_data["target_user_id"] = user_id
        
        # Check if user exists
        try:
            from src.infrastructure.database import db_service
            session_data = db_service.load_user_session(user_id)
            if session_data:
                current_role = session_data.get("role", "normal")
                await update.message.reply_text(
                    f"👤 Usuario ID: {user_id}\n"
                    f"📊 Rol actual: {current_role.upper()}\n\n"
                    f"✏️ Envía el nuevo rol (normal, premium, admin):"
                )
                return WAITING_FOR_ROLE
            else:
                await update.message.reply_text(
                    "❌ El usuario no existe en la base de datos.\n"
                    "Puedes intentar con otro ID."
                )
                return WAITING_FOR_USER_ID
        except ImportError:
            # If no DB, search in memory
            if user_id in UserSession._sessions:
                current_role = UserSession._sessions[user_id].get_role()
                await update.message.reply_text(
                    f"👤 Usuario ID: {user_id}\n"
                    f"📊 Rol actual: {current_role.upper()}\n\n"
                    f"✏️ Envía el nuevo rol (normal, premium, admin):"
                )
                return WAITING_FOR_ROLE
            else:
                await update.message.reply_text(
                    "❌ No se encontró información del usuario.\n"
                    "Puedes intentar con otro ID o cancelar con /cancel."
                )
                return WAITING_FOR_USER_ID
    except ValueError:
        await update.message.reply_text(
            "❌ ID no válido. Debe ser un número.\n"
            "Inténtalo de nuevo o cancela con /cancel."
        )
        return WAITING_FOR_USER_ID


async def set_role_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Confirms and processes role change for selected user.
    """
    role = update.message.text.strip().lower()
    user_id = context.user_data.get("target_user_id")
    
    if not user_id:
        await update.message.reply_text("❌ Error: ID de usuario no encontrado.")
        return ConversationHandler.END
    
    # Process role change
    return await set_user_role(update, context, user_id, role)


async def set_user_role(update: Update, 
                    context: ContextTypes.DEFAULT_TYPE, 
                    user_id: int, 
                    role: str) -> int:
    """
    Sets a user's role.
    
    Args:
        update: Telegram Update object
        context: Conversation context
        user_id: User ID to modify
        role: New role (normal, premium, admin)
    """
    # Validate role
    if role not in ["normal", "premium", "admin"]:
        await update.message.reply_text(
            "❌ Rol no válido. Opciones: normal, premium, admin"
        )
        return ConversationHandler.END
    
    try:
        # Update in database if available
        db_updated = False
        try:
            from src.infrastructure.database import db_service
            if db_service.set_user_role(user_id, role):
                db_updated = True
        except ImportError:
            pass
            
        # Update in memory if user has active session
        memory_updated = False
        if user_id in UserSession._sessions:
            session = UserSession._sessions[user_id]
            await session.set_role(role)
            memory_updated = True
            
        # Report result
        if db_updated or memory_updated:
            await update.message.reply_text(
                f"✅ Rol actualizado correctamente\n\n"
                f"👤 Usuario: {user_id}\n"
                f"🔄 Nuevo rol: {role.upper()}\n\n"
                f"📀 Actualizado en BD: {'✓' if db_updated else '✗'}\n"
                f"💾 Actualizado en memoria: {'✓' if memory_updated else '✗'}"
            )
        else:
            await update.message.reply_text(
                f"⚠️ No se pudo actualizar el rol. El usuario {user_id} no existe."
            )
    except Exception as e:
        logging.error(f"Error setting role for user {user_id}: {e}", exc_info=True)
        await update.message.reply_text(
            f"❌ Error al actualizar el rol: {str(e)}"
        )
    
    return ConversationHandler.END


@requires_role("admin")
async def cancel_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Cancels any ongoing conversation.
    """
    await update.message.reply_text("❌ Operación cancelada.")
    return ConversationHandler.END


@requires_role("admin")
async def cmd_user_info(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Shows detailed information about a user.
    
    Command: /userinfo <user_id>
    """
    if not context.args:
        await update.message.reply_text(
            "❓ Uso: /userinfo <user_id>"
        )
        return
        
    try:
        user_id = int(context.args[0])
        
        # Search for user information
        user_data = None
        
        # Try from database first
        try:
            from src.infrastructure.database import db_service
            user_data = db_service.load_user_session(user_id)
        except ImportError:
            pass
            
        # If not in DB, search in memory
        if not user_data and user_id in UserSession._sessions:
            session = UserSession._sessions[user_id]
            user_data = {
                "user_id": user_id,
                "role": session.get_role(),
                "last_activity": session.last_activity,
                "total_downloads": session.total_downloads,
                "active_downloads": session.active_downloads,
                "created_at": session.created_at
            }
            
        if not user_data:
            await update.message.reply_text(
                f"❌ No se encontró información para el usuario {user_id}."
            )
            return
            
        # Format and show information
        last_activity = datetime.fromtimestamp(user_data["last_activity"])
        created_at = datetime.fromtimestamp(user_data.get("created_at", 0))
        
        info_text = f"""
📋 *Información del Usuario* 📋

👤 *ID*: `{user_id}`
🏅 *Rol*: {user_data.get("role", "normal").upper()}
📅 *Registrado*: {created_at.strftime('%Y-%m-%d %H:%M')}
🕒 *Última actividad*: {last_activity.strftime('%Y-%m-%d %H:%M')}
💾 *Descargas totales*: {user_data.get("total_downloads", 0)}
⏳ *Descargas activas*: {user_data.get("active_downloads", 0)}
"""
        
        # Add action buttons
        keyboard = [
            [
                InlineKeyboardButton("🔄 Cambiar rol", callback_data=f"admin_setrole_{user_id}"),
                InlineKeyboardButton("🗑️ Borrar sesión", callback_data=f"admin_delete_{user_id}")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            info_text,
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )
            
    except ValueError:
        await update.message.reply_text(
            "❌ ID de usuario no válido. Debe ser un número."
        )
    except Exception as e:
        logging.error(f"Error getting user info: {e}", exc_info=True)
        await update.message.reply_text(
            f"❌ Error al obtener información: {str(e)}"
        )


@requires_role("admin")
async def admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Shows detailed system statistics.
    
    Command: /stats_admin
    """
    try:
        # Basic statistics
        total_sessions = len(UserSession._sessions)
        
        # Download statistics
        total_downloads = sum(session.total_downloads for session in UserSession._sessions.values())
        active_downloads = sum(session.active_downloads for session in UserSession._sessions.values())
        
        # User statistics by role
        roles = {"normal": 0, "premium": 0, "admin": 0}
        for session in UserSession._sessions.values():
            role = session.get_role()
            if role in roles:
                roles[role] += 1
        
        # Database statistics
        db_stats = {}
        try:
            from src.infrastructure.database import db_service
            db_stats = db_service.get_session_stats()
        except ImportError:
            pass
            
        # Format message
        stats_text = f"""
📊 *Estadísticas del Sistema* 📊

👥 *Usuarios activos*: {total_sessions}
⬇️ *Descargas totales*: {total_downloads}
⏳ *Descargas en curso*: {active_downloads}

📱 *Por rol (activos)*:
   - 👑 Admin: {roles["admin"]}
   - 💎 Premium: {roles["premium"]}
   - 👤 Normal: {roles["normal"]}
"""

        # Add DB statistics if available
        if db_stats:
            sessions_today = db_stats.get("active_last_day", 0)
            
            stats_text += f"""
📀 *Base de datos*:
   - 👥 Total usuarios: {db_stats.get('total_sessions', 0)}
   - 🆕 Nuevos (24h): {sessions_today}
   - ⬇️ Total descargas: {db_stats.get('total_downloads', 0)}
"""

        # Add action buttons
        keyboard = [
            [
                InlineKeyboardButton("🔄 Actualizar", callback_data="admin_refresh_stats")
            ],
            [
                InlineKeyboardButton("📊 Exportar datos", callback_data="admin_export_data")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            stats_text,
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )
    
    except Exception as e:
        logging.error(f"Error getting statistics: {e}", exc_info=True)
        await update.message.reply_text(
            f"❌ Error al obtener estadísticas: {str(e)}"
        )


@requires_role("admin")
async def handle_admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handles callbacks from buttons in administrative commands.
    """
    query = update.callback_query
    await query.answer()
    
    data = query.data
    
    if data == "admin_refresh_stats":
        # Refresh statistics
        await admin_stats(update, context)
    elif data.startswith("admin_setrole_"):
        # Change user role
        user_id = int(data.split("_")[2])
        context.user_data["target_user_id"] = user_id
        
        # Show role options
        keyboard = [
            [
                InlineKeyboardButton("👤 Normal", callback_data=f"admin_set_normal_{user_id}"),
                InlineKeyboardButton("💎 Premium", callback_data=f"admin_set_premium_{user_id}"),
                InlineKeyboardButton("👑 Admin", callback_data=f"admin_set_admin_{user_id}")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            f"Selecciona el nuevo rol para el usuario {user_id}:",
            reply_markup=reply_markup
        )
    elif data.startswith("admin_set_"):
        # Process role change
        parts = data.split("_")
        role = parts[2]
        user_id = int(parts[3])
        
        # Update role directly
        db_updated = False
        try:
            from src.infrastructure.database import db_service
            if db_service.set_user_role(user_id, role):
                db_updated = True
        except ImportError:
            pass
            
        # Update in memory if user has active session
        memory_updated = False
        if user_id in UserSession._sessions:
            session = UserSession._sessions[user_id]
            await session.set_role(role)
            memory_updated = True
            
        await query.edit_message_text(
            f"✅ Rol actualizado correctamente\n\n"
            f"👤 Usuario: {user_id}\n"
            f"🔄 Nuevo rol: {role.upper()}\n\n"
            f"📀 Actualizado en BD: {'✓' if db_updated else '✗'}\n"
            f"💾 Actualizado en memoria: {'✓' if memory_updated else '✗'}"
        )
    elif data.startswith("admin_delete_"):
        if data == "admin_delete_cancel":
            await query.edit_message_text("❌ Eliminación cancelada.")
        elif data.startswith("admin_delete_confirm_"):
            user_id = int(data.split("_")[3])
            
            # Delete from memory
            deleted_memory = False
            if user_id in UserSession._sessions:
                del UserSession._sessions[user_id]
                deleted_memory = True
                
            # Delete from DB
            deleted_db = False
            try:
                from src.infrastructure.database import db_service
                deleted_db = db_service.delete_session(user_id)
            except ImportError:
                pass
                
            await query.edit_message_text(
                f"🗑️ Sesión del usuario {user_id} eliminada\n\n"
                f"📀 Eliminada de BD: {'✓' if deleted_db else '✗'}\n"
                f"💾 Eliminada de memoria: {'✓' if deleted_memory else '✗'}"
            )
        else:
            user_id = int(data.split("_")[2])
            
            keyboard = [
                [
                    InlineKeyboardButton("✅ Confirmar", callback_data=f"admin_delete_confirm_{user_id}"),
                    InlineKeyboardButton("❌ Cancelar", callback_data="admin_delete_cancel")
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                f"¿Estás seguro de que deseas eliminar la sesión del usuario {user_id}?",
                reply_markup=reply_markup
            )
    elif data == "admin_export_data":
        try:
            success = False
            filename = ""
            try:
                from src.infrastructure.database import db_service
                from migration_tool import migrate_sqlite_to_json
                
                timestamp = int(time.time())
                filename = f"melodify_export_{timestamp}.json"
                success = await migrate_sqlite_to_json(filename)
            except ImportError:
                await query.edit_message_text(
                    "❌ No se pueden exportar datos: módulos necesarios no disponibles."
                )
                return
                
            if success:
                await query.edit_message_text(
                    f"✅ Datos exportados correctamente a: {filename}"
                )
            else:
                await query.edit_message_text(
                    "❌ Error al exportar datos. Revisa los logs para más información."
                )
        except Exception as e:
            logging.error(f"Error exporting data: {e}", exc_info=True)
            await query.edit_message_text(
                f"❌ Error al exportar datos: {str(e)}"
            )


@requires_role("admin")
async def cmd_maintenance(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Enables or disables maintenance mode.
    
    Command: /maintenance [on/off]
    """
    maintenance_mode = context.bot_data.get("maintenance_mode", False)
    
    if not context.args:
        status = "ACTIVADO ✅" if maintenance_mode else "DESACTIVADO ❌"
        await update.message.reply_text(
            f"🛠️ Modo mantenimiento: {status}\n\n"
            f"Usa:\n"
            f"/maintenance on - Para activar\n"
            f"/maintenance off - Para desactivar"
        )
        return
        
    command = context.args[0].lower()
    if command == "on":
        context.bot_data["maintenance_mode"] = True
        await update.message.reply_text(
            "🛠️ Modo mantenimiento ACTIVADO ✅\n\n"
            "Los usuarios normales no podrán usar el bot hasta que se desactive."
        )
    elif command == "off":
        context.bot_data["maintenance_mode"] = False
        await update.message.reply_text(
            "🛠️ Modo mantenimiento DESACTIVADO ❌\n\n"
            "El bot ahora está disponible para todos los usuarios."
        )
    else:
        await update.message.reply_text(
            "❌ Opción no válida. Use 'on' u 'off'."
        )


@requires_role("admin")
async def cmd_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Sends a message to all active users.
    
    Command: /broadcast <message>
    """
    if not context.args:
        await update.message.reply_text(
            "❓ Uso: /broadcast <mensaje>"
        )
        return
        
    message = " ".join(context.args)
    
    await update.message.reply_text(
        f"📣 ¿Seguro que quieres enviar este mensaje a todos los usuarios?\n\n"
        f"{message}\n\n"
        f"Responde con 'confirmar' para enviar o cualquier otra cosa para cancelar."
    )
    
    context.user_data["broadcast_message"] = message


@requires_role("admin")
async def cmd_system(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Shows system state and resource information.
    
    Command: /system
    """
    try:
        import psutil
        import platform
        from datetime import datetime
        
        system_info = {
            "system": platform.system(),
            "release": platform.release(),
            "version": platform.version(),
            "machine": platform.machine(),
            "processor": platform.processor()
        }
        
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        
        boot_time = datetime.fromtimestamp(psutil.boot_time())
        uptime = datetime.now() - boot_time
        
        system_message = (
            f"🖥️ *Información del Sistema* 🖥️\n\n"
            
            f"*Sistema Operativo*:\n"
            f"  • {system_info['system']} {system_info['release']}\n"
            f"  • {system_info['version']}\n"
            f"  • Arquitectura: {system_info['machine']}\n\n"
            
            f"*Recursos*:\n"
            f"  • CPU: {psutil.cpu_percent()}% en uso\n"
            f"  • RAM: {memory.percent}% ({round(memory.used/1024/1024/1024, 2)} GB de {round(memory.total/1024/1024/1024, 2)} GB)\n"
            f"  • Disco: {disk.percent}% ({round(disk.used/1024/1024/1024, 2)} GB de {round(disk.total/1024/1024/1024, 2)} GB)\n\n"
            
            f"*Tiempo de actividad*:\n"
            f"  • Sistema: {str(uptime).split('.')[0]}\n"
        )
        
        queue_manager = QueueManager.get_instance()
        queue_stats = queue_manager.get_stats()
        active_sessions = len(UserSession._sessions)
        
        system_message += (
            f"*Bot Melodify Deluxe*:\n"
            f"  • Sesiones activas: {active_sessions}\n"
            f"  • Tareas en cola: {queue_stats['total_pending']}\n"
            f"  • Tareas procesadas: {queue_stats['total_processed']}\n"
        )
        
        await update.message.reply_text(system_message, parse_mode="Markdown")
        
    except ImportError:
        await update.message.reply_text(
            "⚠️ No se pudo obtener información completa del sistema.\n"
            "Para habilitar todas las funciones, instala el módulo psutil:\n"
            "`pip install psutil`\n\n"
            f"Sesiones activas: {len(UserSession._sessions)}\n",
            parse_mode="Markdown"
        )
    except Exception as e:
        logging.error(f"Error getting system info: {e}", exc_info=True)
        await update.message.reply_text(
            f"❌ Error obteniendo información del sistema: {str(e)}"
        )


async def broadcast_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Confirms and processes sending a message to all users.
    """
    if "broadcast_message" not in context.user_data:
        await update.message.reply_text(
            "❌ No hay mensaje pendiente para enviar."
        )
        return
        
    if update.message.text.strip().lower() != "confirmar":
        await update.message.reply_text(
            "❌ Envío cancelado."
        )
        context.user_data.pop("broadcast_message", None)
        return
        
    message = context.user_data["broadcast_message"]
    sent = 0
    failed = 0
    
    await update.message.reply_text(
        "🔄 Enviando mensaje a todos los usuarios..."
    )
    
    sessions = []
    sessions.extend(UserSession._sessions.keys())
    
    try:
        from src.infrastructure.database import db_service
        db_sessions = db_service.load_all_sessions()
        for user_id in db_sessions:
            if user_id not in sessions:
                sessions.append(user_id)
    except ImportError:
        pass
        
    total = len(sessions)
    
    for user_id in sessions:
        try:
            await context.bot.send_message(
                chat_id=user_id,
                text=f"📣 *ANUNCIO*\n\n{message}",
                parse_mode="Markdown"
            )
            sent += 1
        except Exception:
            failed += 1
            
        if sent % 20 == 0:
            await asyncio.sleep(1)
    
    await update.message.reply_text(
        f"✅ Mensaje enviado a {sent}/{total} usuarios.\n"
        f"❌ Fallos: {failed}"
    )
    
    context.user_data.pop("broadcast_message", None)


@requires_role("admin")
async def cmd_session_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Shows detailed session management system statistics.
    
    Command: /session_stats
    """
    # Get metrics
    metrics = UserSession._metrics
    
    # Calculate ratios
    cache_hit_ratio = metrics.get_cache_hit_ratio()
    compression_ratio = metrics.get_compression_ratio()
    
    stats_text = f"""
📊 *Estadísticas del Sistema de Sesiones* 📊

💾 *Caché*:
• Sesiones en memoria: {len(UserSession._sessions)}/{UserSession._sessions.maxsize}
• Hits: {metrics.cache_hits}
• Misses: {metrics.cache_misses}
• Ratio de aciertos: {cache_hit_ratio:.2%}

🗄️ *Base de Datos*:
• Lecturas: {metrics.db_reads}
• Escrituras: {metrics.db_writes}
• Errores: {metrics.db_errors}
"""

    if metrics.compression_count > 0:
        stats_text += f"""
🔄 *Compresión*:
• Datos comprimidos: {metrics.compression_count}
• Ratio promedio: {compression_ratio:.2f}x
• Ahorro: {(1 - 1/compression_ratio)*100:.1f}%
"""
    
    if UserSession._use_database:
        try:
            from src.infrastructure.database import db_service
            db_stats = db_service.get_session_stats()
            
            stats_text += f"""
📁 *Almacenamiento*:
• Total sesiones: {db_stats.get('total_sessions', 0)}
• Por rol:
  - Admin: {db_stats.get('admin_sessions', 0)}
  - Premium: {db_stats.get('premium_sessions', 0)}
  - Normal: {db_stats.get('normal_sessions', 0)}
• Activas hoy: {db_stats.get('active_last_day', 0)}
"""
        except ImportError:
            pass
            
    from src.config import SESSION_TIERS
    stats_text += f"""
⏱️ *Expiración por Niveles*:
• Admin: {SESSION_TIERS['admin'] // 3600} horas
• Premium: {SESSION_TIERS['premium'] // 3600} horas
• Normal: {SESSION_TIERS['normal'] // 60} minutos
"""
    
    await update.message.reply_text(stats_text, parse_mode="Markdown")
