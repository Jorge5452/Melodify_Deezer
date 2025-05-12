"""
Comandos de administración para Melodify Deluxe.

Este módulo proporciona comandos reservados para administradores y funciones
para gestionar roles de usuario, estadísticas avanzadas y mantenimiento.
"""

import logging
import time
import asyncio
from datetime import datetime
from typing import Dict, Any, Optional, List, Tuple

from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes, ConversationHandler

from user_session import UserSession, requires_role
from modules.queue_manager import QueueManager

# Estados para conversaciones
WAITING_FOR_USER_ID = 1
WAITING_FOR_ROLE = 2

async def admin_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Muestra ayuda sobre los comandos administrativos disponibles.
    
    Solo visible para administradores.
    """
    help_text = """
🛠️ *Comandos de Administración* 🛠️

*/setrole* - Establecer o cambiar el rol de un usuario
*/userinfo* - Ver información detallada de un usuario
*/stats_admin* - Estadísticas detalladas del sistema
*/broadcast* - Enviar mensaje a todos los usuarios
*/system* - Ver estado del sistema y recursos
*/maintenance* - Activar/desactivar modo mantenimiento

Recuerda usar estos comandos con responsabilidad.
"""
    await update.message.reply_text(help_text, parse_mode="Markdown")

@requires_role("admin")
async def cmd_set_role(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Inicia el proceso para cambiar el rol de un usuario.
    
    Comando: /setrole
    """
    # Verificar si hay argumentos (ID usuario y rol)
    if context.args and len(context.args) == 2:
        try:
            # Formato: /setrole <user_id> <role>
            user_id = int(context.args[0])
            role = context.args[1].lower()
            
            # Validar rol
            if role not in ["normal", "premium", "admin"]:
                await update.message.reply_text(
                    "❌ Rol no válido. Opciones: normal, premium, admin"
                )
                return ConversationHandler.END
                
            # Actualizar rol
            return await set_user_role(update, context, user_id, role)
        except ValueError:
            await update.message.reply_text(
                "❌ ID de usuario no válido. Debe ser un número."
            )
            return ConversationHandler.END
    
    # Si no hay argumentos completos, iniciar conversación
    await update.message.reply_text(
        "🔄 Por favor, envía el ID del usuario cuyo rol deseas cambiar:"
    )
    return WAITING_FOR_USER_ID

async def set_role_user_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Procesa el ID de usuario enviado para cambiar su rol.
    """
    try:
        user_id = int(update.message.text.strip())
        context.user_data["target_user_id"] = user_id
        
        # Comprobar si el usuario existe
        try:
            import db_manager
            session_data = db_manager.load_user_session(user_id)
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
            # Si no hay DB, buscar en memoria
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
    Confirma y procesa el cambio de rol para el usuario seleccionado.
    """
    role = update.message.text.strip().lower()
    user_id = context.user_data.get("target_user_id")
    
    if not user_id:
        await update.message.reply_text("❌ Error: ID de usuario no encontrado.")
        return ConversationHandler.END
    
    # Procesar el cambio de rol
    return await set_user_role(update, context, user_id, role)

async def set_user_role(update: Update, 
                    context: ContextTypes.DEFAULT_TYPE, 
                    user_id: int, 
                    role: str) -> int:
    """
    Establece el rol de un usuario.
    
    Args:
        update: Objeto Update de Telegram
        context: Contexto de la conversación
        user_id: ID del usuario a modificar
        role: Nuevo rol (normal, premium, admin)
    """
    # Validar el rol
    if role not in ["normal", "premium", "admin"]:
        await update.message.reply_text(
            "❌ Rol no válido. Opciones: normal, premium, admin"
        )
        return ConversationHandler.END
    
    try:
        # Actualizar en base de datos si está disponible
        db_updated = False
        try:
            import db_manager
            if db_manager.set_user_role(user_id, role):
                db_updated = True
        except ImportError:
            pass
            
        # Actualizar en memoria si el usuario tiene sesión activa
        memory_updated = False
        if user_id in UserSession._sessions:
            session = UserSession._sessions[user_id]
            await session.set_role(role)
            memory_updated = True
            
        # Reportar resultado
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
        logging.error(f"Error al establecer rol para usuario {user_id}: {e}", exc_info=True)
        await update.message.reply_text(
            f"❌ Error al actualizar el rol: {str(e)}"
        )
    
    return ConversationHandler.END

@requires_role("admin")
async def cancel_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Cancela cualquier conversación en curso.
    """
    await update.message.reply_text("❌ Operación cancelada.")
    return ConversationHandler.END

@requires_role("admin")
async def cmd_user_info(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Muestra información detallada sobre un usuario.
    
    Comando: /userinfo <user_id>
    """
    if not context.args:
        await update.message.reply_text(
            "❓ Uso: /userinfo <user_id>"
        )
        return
        
    try:
        user_id = int(context.args[0])
        
        # Buscar información del usuario
        user_data = None
        
        # Intentar primero desde la base de datos
        try:
            import db_manager
            user_data = db_manager.load_user_session(user_id)
        except ImportError:
            pass
            
        # Si no está en BD, buscar en memoria
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
            
        # Formatear y mostrar información
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
        
        # Añadir botones de acción
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
        logging.error(f"Error al obtener información de usuario: {e}", exc_info=True)
        await update.message.reply_text(
            f"❌ Error al obtener información: {str(e)}"
        )

@requires_role("admin")
async def admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Muestra estadísticas detalladas del sistema.
    
    Comando: /stats_admin
    """
    try:
        # Estadísticas básicas
        total_sessions = len(UserSession._sessions)
        
        # Estadísticas de descargas
        total_downloads = sum(session.total_downloads for session in UserSession._sessions.values())
        active_downloads = sum(session.active_downloads for session in UserSession._sessions.values())
        
        # Estadísticas de usuarios por rol
        roles = {"normal": 0, "premium": 0, "admin": 0}
        for session in UserSession._sessions.values():
            role = session.get_role()
            if role in roles:
                roles[role] += 1
        
        # Estadísticas de la base de datos
        db_stats = {}
        try:
            import db_manager
            db_stats = db_manager.get_session_stats()
        except ImportError:
            pass
            
        # Formatear mensaje
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

        # Añadir estadísticas de BD si están disponibles
        if db_stats:
            # Calcular sesiones creadas hoy
            today = int(time.time() - 86400)  # Últimas 24h
            sessions_today = db_stats.get("active_last_day", 0)
            
            stats_text += f"""
📀 *Base de datos*:
   - 👥 Total usuarios: {db_stats.get('total_sessions', 0)}
   - 🆕 Nuevos (24h): {sessions_today}
   - ⬇️ Total descargas: {db_stats.get('total_downloads', 0)}
"""

        # Añadir botones de acción
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
        logging.error(f"Error al obtener estadísticas: {e}", exc_info=True)
        await update.message.reply_text(
            f"❌ Error al obtener estadísticas: {str(e)}"
        )

@requires_role("admin")
async def handle_admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Maneja callbacks de los botones en comandos administrativos.
    """
    query = update.callback_query
    await query.answer()
    
    data = query.data
    
    if data == "admin_refresh_stats":
        # Actualizar estadísticas
        await admin_stats(update, context)
    elif data.startswith("admin_setrole_"):
        # Cambiar rol de usuario
        user_id = int(data.split("_")[2])
        context.user_data["target_user_id"] = user_id
        
        # Mostrar opciones de rol
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
        # Procesar cambio de rol
        parts = data.split("_")
        role = parts[2]
        user_id = int(parts[3])
        
        # Actualizar rol directamente
        db_updated = False
        try:
            import db_manager
            if db_manager.set_user_role(user_id, role):
                db_updated = True
        except ImportError:
            pass
            
        # Actualizar en memoria si el usuario tiene sesión activa
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
            # Cancelar eliminación
            await query.edit_message_text("❌ Eliminación cancelada.")
        elif data.startswith("admin_delete_confirm_"):
            # Procesar eliminación de sesión
            user_id = int(data.split("_")[3])
            
            # Eliminar de memoria
            deleted_memory = False
            if user_id in UserSession._sessions:
                del UserSession._sessions[user_id]
                deleted_memory = True
                
            # Eliminar de BD
            deleted_db = False
            try:
                import db_manager
                deleted_db = db_manager.delete_session(user_id)
            except ImportError:
                pass
                
            await query.edit_message_text(
                f"🗑️ Sesión del usuario {user_id} eliminada\n\n"
                f"📀 Eliminada de BD: {'✓' if deleted_db else '✗'}\n"
                f"💾 Eliminada de memoria: {'✓' if deleted_memory else '✗'}"
            )
        else:
            # Confirmar eliminación
            user_id = int(data.split("_")[2])
            
            # Confirmar eliminación
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
        # Exportar datos a JSON
        try:
            # Intentar exportar datos
            success = False
            filename = ""
            try:
                import db_manager
                from migration_tool import migrate_sqlite_to_json
                
                # Generar nombre de archivo con timestamp
                timestamp = int(time.time())
                filename = f"melodify_export_{timestamp}.json"
                
                # Ejecutar exportación de forma asíncrona
                loop = asyncio.get_event_loop()
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
            logging.error(f"Error al exportar datos: {e}", exc_info=True)
            await query.edit_message_text(
                f"❌ Error al exportar datos: {str(e)}"
            )

@requires_role("admin")
async def cmd_maintenance(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Activa o desactiva el modo mantenimiento.
    
    Comando: /maintenance [on/off]
    """
    # Esta función implementa un modo mantenimiento básico
    # Para una implementación completa, se necesitaría un sistema más robusto
    
    maintenance_mode = context.bot_data.get("maintenance_mode", False)
    
    if not context.args:
        # Mostrar estado actual
        status = "ACTIVADO ✅" if maintenance_mode else "DESACTIVADO ❌"
        await update.message.reply_text(
            f"🛠️ Modo mantenimiento: {status}\n\n"
            f"Usa:\n"
            f"/maintenance on - Para activar\n"
            f"/maintenance off - Para desactivar"
        )
        return
        
    # Cambiar estado
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
    Envía un mensaje a todos los usuarios activos.
    
    Comando: /broadcast <mensaje>
    """
    if not context.args:
        await update.message.reply_text(
            "❓ Uso: /broadcast <mensaje>"
        )
        return
        
    # Obtener mensaje
    message = " ".join(context.args)
    
    # Confirmar acción
    await update.message.reply_text(
        f"📣 ¿Seguro que quieres enviar este mensaje a todos los usuarios?\n\n"
        f"{message}\n\n"
        f"Responde con 'confirmar' para enviar o cualquier otra cosa para cancelar."
    )
    
    # Guardar mensaje en contexto para posterior confirmación
    context.user_data["broadcast_message"] = message

@requires_role("admin")
async def cmd_system(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Muestra información sobre el estado del sistema y recursos.
    
    Comando: /system
    """
    try:
        import psutil
        import platform
        from datetime import datetime, timedelta
        
        # Información del sistema
        system_info = {
            "system": platform.system(),
            "release": platform.release(),
            "version": platform.version(),
            "machine": platform.machine(),
            "processor": platform.processor()
        }
        
        # Información de recursos
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        
        # Tiempo de actividad del sistema
        boot_time = datetime.fromtimestamp(psutil.boot_time())
        uptime = datetime.now() - boot_time
        
        # Formatear mensaje
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
        
        # Información del bot
        queue_manager = QueueManager.get_instance()
        queue_stats = queue_manager.get_stats()
        active_sessions = len(UserSession._sessions)
        
        system_message += (
            f"*Bot Melodify Deluxe*:\n"
            f"  • Sesiones activas: {active_sessions}\n"
            f"  • Tareas en cola: {queue_stats['total_pending']}\n"
            f"  • Tareas procesadas: {queue_stats['total_processed']}\n"
        )
        
        # Enviar mensaje
        await update.message.reply_text(system_message, parse_mode="Markdown")
        
    except ImportError:
        # Si falta psutil, enviar un mensaje más básico
        await update.message.reply_text(
            "⚠️ No se pudo obtener información completa del sistema.\n"
            "Para habilitar todas las funciones, instala el módulo psutil:\n"
            "`pip install psutil`\n\n"
            f"Sesiones activas: {len(UserSession._sessions)}\n",
            parse_mode="Markdown"
        )
    except Exception as e:
        logging.error(f"Error obteniendo información del sistema: {e}", exc_info=True)
        await update.message.reply_text(
            f"❌ Error obteniendo información del sistema: {str(e)}"
        )

async def broadcast_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Confirma y procesa el envío de un mensaje a todos los usuarios.
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
        
    # Enviar mensaje a todos los usuarios
    message = context.user_data["broadcast_message"]
    sent = 0
    failed = 0
    
    await update.message.reply_text(
        "🔄 Enviando mensaje a todos los usuarios..."
    )
    
    # Obtener todas las sesiones
    sessions = []
    
    # Desde memoria
    sessions.extend(UserSession._sessions.keys())
    
    # Desde BD si está disponible
    try:
        import db_manager
        db_sessions = db_manager.load_all_sessions()
        for user_id in db_sessions:
            if user_id not in sessions:
                sessions.append(user_id)
    except ImportError:
        pass
        
    total = len(sessions)
    
    # Enviar mensajes
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
            
        # Pequeña pausa para evitar límites de Telegram
        if sent % 20 == 0:
            await asyncio.sleep(1)
    
    # Informar resultado
    await update.message.reply_text(
        f"✅ Mensaje enviado a {sent}/{total} usuarios.\n"
        f"❌ Fallos: {failed}"
    )
    
    # Limpiar contexto
    context.user_data.pop("broadcast_message", None) 