"""
Gestor de base de datos para persistencia de sesiones de usuario.

Este módulo implementa una capa de abstracción sobre SQLite
para manejar el almacenamiento persistente de las sesiones.
"""

import sqlite3
import json
import time
import logging
import asyncio
import os
from typing import Dict, Any, Optional, List, Tuple
from contextlib import contextmanager

# Configuración de la base de datos
DB_DIR = "./data"
DB_PATH = f"{DB_DIR}/melodify_sessions.db"

# Roles válidos del sistema
VALID_ROLES = ["normal", "premium", "admin"]
DEFAULT_ROLE = "normal"

# Asegurar que el directorio existe
os.makedirs(DB_DIR, exist_ok=True)

@contextmanager
def get_connection():
    """
    Gestiona la conexión a la base de datos SQLite.
    
    Establece una conexión con optimizaciones y la cierra automáticamente
    al finalizar el contexto.
    """
    conn = None
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row  # Permite acceder a columnas por nombre
        conn.execute("PRAGMA journal_mode=WAL")  # Mejora rendimiento de escritura
        conn.execute("PRAGMA synchronous=NORMAL")  # Equilibrio entre seguridad/rendimiento
        yield conn
    except Exception as e:
        logging.error(f"Error en la conexión a la BD: {str(e)}", exc_info=True)
        raise
    finally:
        if conn:
            conn.close()

def initialize_database():
    """
    Crea las tablas necesarias si no existen.
    
    Esta función debe ser llamada antes de usar cualquier
    otra función de este módulo.
    """
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            
            # Tabla de sesiones de usuario
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                settings TEXT NOT NULL,
                last_activity REAL NOT NULL,
                context_data TEXT,
                total_downloads INTEGER DEFAULT 0,
                active_downloads INTEGER DEFAULT 0,
                role TEXT DEFAULT 'normal',
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL
            )
            ''')
            
            # Índice para búsquedas por actividad
            cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_last_activity ON users(last_activity)
            ''')
            
            # Verificar si la columna 'role' ya existe en la tabla
            cursor.execute("PRAGMA table_info(users)")
            columns = {col[1] for col in cursor.fetchall()}
            
            # Agregar columna 'role' si no existe
            if 'role' not in columns:
                logging.info("Añadiendo columna 'role' a la tabla users")
                cursor.execute("ALTER TABLE users ADD COLUMN role TEXT DEFAULT 'normal'")
                
            conn.commit()
            logging.info("Base de datos inicializada correctamente")
            
            # Verificar si la tabla se creó y tiene la estructura esperada
            cursor.execute("PRAGMA table_info(users)")
            columns = {col[1] for col in cursor.fetchall()}
            expected_columns = {
                "user_id", "settings", "last_activity", "context_data", 
                "total_downloads", "active_downloads", "role", "created_at", "updated_at"
            }
            
            if not expected_columns.issubset(columns):
                missing = expected_columns - columns
                logging.warning(f"Faltan columnas en la tabla users: {missing}")
                
        return True
    except Exception as e:
        logging.error(f"Error inicializando la base de datos: {e}", exc_info=True)
        return False

def save_user_session(user_id: int, session_data: Dict[str, Any]) -> bool:
    """
    Guarda una sesión de usuario en la base de datos.
    
    Args:
        user_id: ID del usuario
        session_data: Diccionario con los datos de la sesión
        
    Returns:
        True si la operación fue exitosa, False en caso contrario
    """
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            now = time.time()
            
            # Convertir diccionarios a JSON para almacenamiento
            settings_json = json.dumps(session_data.get("settings", {}))
            context_data_json = json.dumps(session_data.get("context_data", {}))
            
            # Asegurar que el role sea válido
            role = session_data.get("role", DEFAULT_ROLE)
            if role not in VALID_ROLES:
                role = DEFAULT_ROLE
            
            # Insertar o actualizar registro (UPSERT)
            cursor.execute('''
            INSERT OR REPLACE INTO users 
            (user_id, settings, last_activity, context_data, total_downloads, 
             active_downloads, role, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                user_id,
                settings_json,
                session_data.get("last_activity", now),
                context_data_json,
                session_data.get("total_downloads", 0),
                session_data.get("active_downloads", 0),
                role,
                session_data.get("created_at", now),
                now  # updated_at siempre es el tiempo actual
            ))
            conn.commit()
            return True
    except sqlite3.OperationalError as e:
        if "database is locked" in str(e):
            logging.warning(f"Base de datos bloqueada al guardar sesión {user_id}, reintentando...")
            time.sleep(0.5)  # Breve pausa antes de reintentar
            return save_user_session(user_id, session_data)  # Reintentar una vez
        logging.error(f"Error operacional al guardar sesión para usuario {user_id}: {e}", exc_info=True)
        return False
    except Exception as e:
        logging.error(f"Error guardando sesión para usuario {user_id}: {e}", exc_info=True)
        return False

def load_user_session(user_id: int) -> Optional[Dict[str, Any]]:
    """
    Carga una sesión de usuario desde la base de datos.
    
    Args:
        user_id: ID del usuario
        
    Returns:
        Diccionario con datos de la sesión o None si no existe
    """
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute('''
            SELECT * FROM users WHERE user_id = ?
            ''', (user_id,))
            
            row = cursor.fetchone()
            if not row:
                return None
                
            # Convertir de nuevo a diccionario con deserialización JSON
            return {
                "user_id": row["user_id"],
                "settings": json.loads(row["settings"]),
                "last_activity": row["last_activity"],
                "context_data": json.loads(row["context_data"]) if row["context_data"] else {},
                "total_downloads": row["total_downloads"],
                "active_downloads": row["active_downloads"],
                "role": row["role"] if "role" in row.keys() else DEFAULT_ROLE,
                "created_at": row["created_at"],
                "updated_at": row["updated_at"]
            }
    except Exception as e:
        logging.error(f"Error cargando sesión para usuario {user_id}: {e}", exc_info=True)
        return None

def load_all_sessions() -> Dict[int, Dict[str, Any]]:
    """
    Carga todas las sesiones de usuario desde la base de datos.
    
    Para bases de datos grandes, considera usar paginación.
    
    Returns:
        Diccionario con todas las sesiones (user_id: datos_sesión)
    """
    sessions = {}
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            
            # Limitar a 1000 resultados para evitar problemas de memoria
            cursor.execute('''
            SELECT * FROM users 
            ORDER BY last_activity DESC 
            LIMIT 1000
            ''')
            
            for row in cursor.fetchall():
                user_id = row["user_id"]
                try:
                    sessions[user_id] = {
                        "user_id": user_id,
                        "settings": json.loads(row["settings"]),
                        "last_activity": row["last_activity"],
                        "context_data": json.loads(row["context_data"]) if row["context_data"] else {},
                        "total_downloads": row["total_downloads"],
                        "active_downloads": row["active_downloads"],
                        "role": row["role"] if "role" in row.keys() else DEFAULT_ROLE,
                        "created_at": row["created_at"],
                        "updated_at": row["updated_at"]
                    }
                except json.JSONDecodeError:
                    logging.error(f"Error decodificando JSON para usuario {user_id}")
                    # Saltar esta sesión y continuar con las demás
                    continue
                
        logging.info(f"Cargadas {len(sessions)} sesiones desde la base de datos")
        return sessions
    except Exception as e:
        logging.error(f"Error cargando todas las sesiones: {e}", exc_info=True)
        return {}

def delete_session(user_id: int) -> bool:
    """
    Elimina una sesión de usuario de la base de datos.
    
    Args:
        user_id: ID del usuario
        
    Returns:
        True si se eliminó correctamente, False en caso contrario
    """
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM users WHERE user_id = ?", (user_id,))
            conn.commit()
            return cursor.rowcount > 0
    except Exception as e:
        logging.error(f"Error eliminando sesión para usuario {user_id}: {e}", exc_info=True)
        return False

def delete_expired_sessions(timeout_seconds: int) -> int:
    """
    Elimina sesiones expiradas de la base de datos.
    
    Args:
        timeout_seconds: Tiempo máximo de inactividad en segundos
        
    Returns:
        Número de sesiones eliminadas
    """
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cutoff = time.time() - timeout_seconds
            cursor.execute("DELETE FROM users WHERE last_activity < ?", (cutoff,))
            deleted_count = cursor.rowcount
            conn.commit()
            if deleted_count > 0:
                logging.info(f"Eliminadas {deleted_count} sesiones expiradas de la base de datos")
            return deleted_count
    except Exception as e:
        logging.error(f"Error eliminando sesiones expiradas: {e}", exc_info=True)
        return 0

def get_session_stats() -> Dict[str, Any]:
    """
    Obtiene estadísticas de las sesiones almacenadas.
    
    Returns:
        Diccionario con estadísticas generales
    """
    stats = {
        'total_sessions': 0,
        'active_last_hour': 0,
        'active_last_day': 0,
        'total_downloads': 0,
        'oldest_session': None,
        'newest_session': None
    }
    
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            
            # Total de sesiones
            cursor.execute('SELECT COUNT(*) FROM users')
            stats['total_sessions'] = cursor.fetchone()[0]
            
            # Activas en la última hora
            hour_ago = time.time() - 3600
            cursor.execute('SELECT COUNT(*) FROM users WHERE last_activity > ?', (hour_ago,))
            stats['active_last_hour'] = cursor.fetchone()[0]
            
            # Activas en el último día
            day_ago = time.time() - 86400
            cursor.execute('SELECT COUNT(*) FROM users WHERE last_activity > ?', (day_ago,))
            stats['active_last_day'] = cursor.fetchone()[0]
            
            # Total de descargas
            cursor.execute('SELECT SUM(total_downloads) FROM users')
            result = cursor.fetchone()[0]
            stats['total_downloads'] = result if result is not None else 0
            
            # Sesión más antigua
            cursor.execute('SELECT MIN(created_at) FROM users')
            stats['oldest_session'] = cursor.fetchone()[0]
            
            # Sesión más reciente
            cursor.execute('SELECT MAX(created_at) FROM users')
            stats['newest_session'] = cursor.fetchone()[0]
            
        return stats
    except Exception as e:
        logging.error(f"Error al obtener estadísticas de sesiones: {e}", exc_info=True)
        return stats

def optimize_database() -> bool:
    """
    Optimiza la base de datos eliminando espacio no utilizado.
    
    Esta operación puede tomar tiempo en bases de datos grandes.
    
    Returns:
        True si la operación fue exitosa, False en caso contrario
    """
    try:
        with get_connection() as conn:
            conn.execute("VACUUM")
            conn.execute("ANALYZE")
            logging.info("Base de datos optimizada correctamente")
            return True
    except Exception as e:
        logging.error(f"Error optimizando la base de datos: {e}", exc_info=True)
        return False

def backup_database(backup_path: Optional[str] = None) -> bool:
    """
    Crea una copia de seguridad de la base de datos.
    
    Args:
        backup_path: Ruta del archivo de respaldo. Si es None,
                    se genera una ruta con timestamp.
        
    Returns:
        True si la operación fue exitosa, False en caso contrario
    """
    if not backup_path:
        backup_path = f"{DB_PATH}.backup-{int(time.time())}"
        
    try:
        # Verificar que el directorio de destino existe
        backup_dir = os.path.dirname(backup_path)
        if backup_dir:
            os.makedirs(backup_dir, exist_ok=True)
            
        with get_connection() as conn:
            backup = sqlite3.connect(backup_path)
            conn.backup(backup)
            backup.close()
            
        logging.info(f"Backup de la base de datos creado en {backup_path}")
        return True
    except Exception as e:
        logging.error(f"Error creando backup de la base de datos: {e}", exc_info=True)
        return False

def migrate_memory_sessions_to_db(sessions_dict: Dict[int, Any]) -> int:
    """
    Migra las sesiones en memoria a la base de datos.
    
    Args:
        sessions_dict: Diccionario con las sesiones (user_id: UserSession)
        
    Returns:
        Número de sesiones migradas con éxito
    """
    migrated = 0
    current_time = time.time()
    
    for user_id, session in sessions_dict.items():
        try:
            # Crear diccionario con datos relevantes de la sesión
            session_data = {
                "settings": session.settings,
                "last_activity": session.last_activity,
                "context_data": session.context_data,
                "total_downloads": session.total_downloads,
                "active_downloads": getattr(session, "active_downloads", 0),
                "created_at": getattr(session, "created_at", current_time),
                "updated_at": current_time
            }
            
            if save_user_session(user_id, session_data):
                migrated += 1
        except Exception as e:
            logging.error(f"Error migrando sesión {user_id}: {e}", exc_info=True)
    
    if migrated > 0:        
        logging.info(f"Migradas {migrated} de {len(sessions_dict)} sesiones a la base de datos")
    return migrated 

def set_user_role(user_id: int, role: str) -> bool:
    """
    Actualiza el rol de un usuario en la base de datos.
    
    Args:
        user_id: ID del usuario
        role: Nuevo rol (debe ser uno de los VALID_ROLES)
        
    Returns:
        True si se actualizó correctamente, False en caso contrario
    """
    if role not in VALID_ROLES:
        logging.error(f"Rol inválido: {role}. Debe ser uno de: {VALID_ROLES}")
        return False
        
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            # Verificar si el usuario existe
            cursor.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
            if not cursor.fetchone():
                logging.warning(f"Usuario {user_id} no existe en la base de datos")
                return False
                
            # Actualizar el rol
            cursor.execute(
                "UPDATE users SET role = ?, updated_at = ? WHERE user_id = ?",
                (role, time.time(), user_id)
            )
            conn.commit()
            logging.info(f"Rol del usuario {user_id} actualizado a {role}")
            return True
    except Exception as e:
        logging.error(f"Error actualizando rol para usuario {user_id}: {e}", exc_info=True)
        return False
        
def get_user_role(user_id: int) -> Optional[str]:
    """
    Obtiene el rol de un usuario desde la base de datos.
    
    Args:
        user_id: ID del usuario
        
    Returns:
        Rol del usuario o None si no existe
    """
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT role FROM users WHERE user_id = ?", 
                (user_id,)
            )
            row = cursor.fetchone()
            if row and "role" in row.keys():
                return row["role"]
            return DEFAULT_ROLE
    except Exception as e:
        logging.error(f"Error obteniendo rol para usuario {user_id}: {e}", exc_info=True)
        return DEFAULT_ROLE

def get_users_by_role(role: str) -> List[int]:
    """
    Obtiene una lista de usuarios con un rol específico.
    
    Args:
        role: Rol a buscar
        
    Returns:
        Lista de IDs de usuario con ese rol
    """
    users = []
    if role not in VALID_ROLES:
        logging.error(f"Rol inválido: {role}. Debe ser uno de: {VALID_ROLES}")
        return users
        
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT user_id FROM users WHERE role = ?", (role,))
            for row in cursor.fetchall():
                users.append(row["user_id"])
            return users
    except Exception as e:
        logging.error(f"Error obteniendo usuarios con rol {role}: {e}", exc_info=True)
        return users 