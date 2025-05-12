#!/usr/bin/env python3
"""
Herramienta de migración para sesiones de usuario de Melodify Deluxe.

Este script proporciona funciones para migrar datos de sesiones
entre diferentes formatos de almacenamiento.
"""

import os
import json
import time
import logging
import asyncio
import argparse
from typing import Dict, Any, Optional, List

# Configurar logging
def setup_logging():
    """Configura el logging para la herramienta de migración."""
    log_format = "%(asctime)s - %(levelname)s - %(message)s"
    logging.basicConfig(
        level=logging.INFO,
        format=log_format,
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler("migration.log")
        ]
    )

# Función para cargar sesiones desde un archivo JSON
def load_from_json(json_file: str) -> Dict[str, Any]:
    """
    Carga datos de sesiones desde un archivo JSON.
    
    Args:
        json_file: Ruta al archivo JSON
        
    Returns:
        Diccionario con los datos cargados o diccionario vacío si hay error
    """
    try:
        if not os.path.exists(json_file):
            logging.error(f"Archivo JSON no encontrado: {json_file}")
            return {}
            
        with open(json_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
            
        if "sessions" not in data:
            logging.warning(f"El archivo {json_file} no contiene datos de sesiones.")
            return {}
            
        sessions = data.get("sessions", {})
        logging.info(f"Cargadas {len(sessions)} sesiones desde {json_file}")
        return sessions
    except json.JSONDecodeError as e:
        logging.error(f"Error decodificando JSON de {json_file}: {e}")
        return {}
    except Exception as e:
        logging.error(f"Error leyendo archivo {json_file}: {e}", exc_info=True)
        return {}

async def migrate_json_to_sqlite(json_file: str = "user_sessions.json") -> bool:
    """
    Migra datos de sesiones desde un archivo JSON a la base de datos SQLite.
    
    Args:
        json_file: Ruta al archivo JSON con los datos de sesiones
        
    Returns:
        True si la migración fue exitosa, False en caso contrario
    """
    try:
        # Importar módulo de base de datos
        try:
            import db_manager
        except ImportError as e:
            logging.error(f"No se puede importar db_manager: {e}")
            return False
            
        # Inicializar la base de datos
        db_manager.initialize_database()
        
        # Cargar datos del JSON
        sessions_data = load_from_json(json_file)
        if not sessions_data:
            logging.warning("No hay datos para migrar desde JSON.")
            return False
            
        total = len(sessions_data)
        migrated = 0
        current_time = time.time()
        
        # Migrar cada sesión al formato adecuado para SQLite
        for user_id_str, session_data in sessions_data.items():
            try:
                user_id = int(user_id_str)
                
                # Extraer datos relevantes de la sesión
                clean_data = {
                    "settings": session_data.get("settings", {}),
                    "last_activity": session_data.get("last_activity", current_time),
                    "context_data": session_data.get("context_data", {}),
                    "total_downloads": session_data.get("total_downloads", 0),
                    "active_downloads": 0,  # Reiniciar contadores activos
                    "role": session_data.get("role", "normal"),  # Usar rol existente o defecto
                    "created_at": current_time,  # Usar tiempo actual como fecha de creación
                    "updated_at": current_time   # Usar tiempo actual como fecha de actualización
                }
                
                # Guardar en la base de datos
                if db_manager.save_user_session(user_id, clean_data):
                    migrated += 1
                    if migrated % 10 == 0:  # Log cada 10 sesiones
                        logging.info(f"Migradas {migrated}/{total} sesiones...")
            except ValueError:
                logging.error(f"ID de usuario inválido: {user_id_str}")
            except Exception as e:
                logging.error(f"Error migrando sesión {user_id_str}: {e}")
        
        # Verificar el resultado
        if migrated > 0:
            logging.info(f"Migración completada: {migrated} de {total} sesiones migradas con éxito")
            
            # Optimizar la base de datos después de la migración
            db_manager.optimize_database()
            
            # Crear un respaldo de la base de datos
            db_manager.backup_database(f"data/melodify_sessions_migrated_{int(current_time)}.db")
            return True
        else:
            logging.error("No se migró ninguna sesión correctamente.")
            return False
    
    except Exception as e:
        logging.error(f"Error durante la migración: {e}", exc_info=True)
        return False

async def migrate_sqlite_to_json(output_file: str = "exported_sessions.json") -> bool:
    """
    Migra datos de sesiones desde SQLite a un archivo JSON.
    
    Args:
        output_file: Ruta donde guardar el archivo JSON
        
    Returns:
        True si la migración fue exitosa, False en caso contrario
    """
    try:
        # Importar módulo de base de datos
        try:
            import db_manager
        except ImportError as e:
            logging.error(f"No se puede importar db_manager: {e}")
            return False
            
        # Cargar todas las sesiones de la BD
        sessions_data = db_manager.load_all_sessions()
        if not sessions_data:
            logging.warning("No hay sesiones para exportar desde SQLite.")
            return False
            
        # Preparar estructura para el JSON
        export_data = {
            "timestamp": time.time(),
            "version": "1.0",
            "sessions": {}
        }
        
        # Convertir cada sesión al formato JSON
        for user_id, session in sessions_data.items():
            export_data["sessions"][str(user_id)] = session
            
        # Guardar en archivo JSON
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(export_data, f, indent=2)
            
        logging.info(f"Exportación completada: {len(sessions_data)} sesiones guardadas en {output_file}")
        return True
        
    except Exception as e:
        logging.error(f"Error durante la exportación a JSON: {e}", exc_info=True)
        return False

async def update_user_roles(role_mappings: Dict[int, str] = None) -> Dict[str, Any]:
    """
    Actualiza los roles de usuarios en la base de datos.
    
    Args:
        role_mappings: Diccionario con mapeos {user_id: role}
                      Ej: {123456: "admin", 789012: "premium"}
    
    Returns:
        Diccionario con estadísticas de la operación
    """
    if not role_mappings:
        logging.warning("No se proporcionaron mapeos de roles para actualizar")
        return {"success": False, "updated": 0, "failed": 0}
        
    try:
        import db_manager
        
        # Verificar roles válidos
        valid_roles = set(db_manager.VALID_ROLES)
        invalid_mappings = {uid: role for uid, role in role_mappings.items() 
                          if role not in valid_roles}
        
        if invalid_mappings:
            logging.error(f"Roles inválidos detectados: {invalid_mappings}")
            return {"success": False, "error": "Roles inválidos", "invalid": invalid_mappings}
            
        # Actualizar roles
        updated = 0
        failed = 0
        
        for user_id, role in role_mappings.items():
            if db_manager.set_user_role(user_id, role):
                updated += 1
                logging.info(f"Rol de usuario {user_id} actualizado a {role}")
            else:
                failed += 1
                logging.warning(f"No se pudo actualizar rol para usuario {user_id}")
                
        return {
            "success": updated > 0,
            "updated": updated,
            "failed": failed
        }
        
    except ImportError:
        return {"success": False, "error": "Módulo db_manager no disponible"}
    except Exception as e:
        logging.error(f"Error actualizando roles: {e}", exc_info=True)
        return {"success": False, "error": str(e)}

async def set_admins(admin_ids: List[int]) -> Dict[str, Any]:
    """
    Establece usuarios administradores en el sistema.
    
    Args:
        admin_ids: Lista de IDs de usuario a establecer como administradores
        
    Returns:
        Resultado de la operación
    """
    mappings = {user_id: "admin" for user_id in admin_ids}
    return await update_user_roles(mappings)

async def verify_migration() -> Dict[str, Any]:
    """
    Verifica la integridad de la migración comparando datos entre JSON y SQLite.
    
    Returns:
        Diccionario con estadísticas de verificación
    """
    try:
        # Importar módulos necesarios
        try:
            import db_manager
        except ImportError as e:
            logging.error(f"No se puede importar db_manager: {e}")
            return {"success": False, "error": str(e)}
            
        # Obtener estadísticas de la base de datos
        stats = db_manager.get_session_stats()
        
        # Verificar algunas sesiones aleatorias
        sessions = db_manager.load_all_sessions()
        sample_size = min(5, len(sessions))
        verified = 0
        
        if sessions:
            # Tomar algunos IDs de usuario para verificar
            import random
            sample_ids = random.sample(list(sessions.keys()), sample_size)
            
            for user_id in sample_ids:
                session = sessions[user_id]
                role = session.get("role", "normal")
                logging.info(f"Verificando sesión {user_id}: rol {role}, "
                           f"{len(session['settings'])} configuraciones, "
                           f"{session['total_downloads']} descargas")
                verified += 1
                
        # Contar roles
        roles_count = {"normal": 0, "premium": 0, "admin": 0}
        for user_id, session in sessions.items():
            role = session.get("role", "normal")
            if role in roles_count:
                roles_count[role] += 1
                
        return {
            "success": True,
            "total_sessions": stats['total_sessions'],
            "total_downloads": stats['total_downloads'],
            "verified_samples": verified,
            "roles_count": roles_count,
            "oldest_session": stats['oldest_session'],
            "newest_session": stats['newest_session']
        }
            
    except Exception as e:
        logging.error(f"Error durante la verificación: {e}", exc_info=True)
        return {"success": False, "error": str(e)}

def display_stats():
    """Muestra estadísticas de la base de datos SQLite."""
    try:
        import db_manager
        stats = db_manager.get_session_stats()
        
        print("\n=== ESTADÍSTICAS DE LA BASE DE DATOS ===")
        print(f"Total de sesiones: {stats['total_sessions']}")
        print(f"Sesiones activas (última hora): {stats['active_last_hour']}")
        print(f"Sesiones activas (último día): {stats['active_last_day']}")
        print(f"Total de descargas: {stats['total_downloads']}")
        
        # Mostrar distribución de roles
        try:
            admins = db_manager.get_users_by_role("admin")
            premium = db_manager.get_users_by_role("premium")
            print(f"Usuarios admin: {len(admins)}")
            print(f"Usuarios premium: {len(premium)}")
            print(f"Usuarios normales: {stats['total_sessions'] - len(admins) - len(premium)}")
        except Exception as e:
            print(f"Error al obtener distribución de roles: {e}")
            
        if stats['oldest_session']:
            import datetime
            oldest = datetime.datetime.fromtimestamp(stats['oldest_session'])
            newest = datetime.datetime.fromtimestamp(stats['newest_session'])
            print(f"Sesión más antigua: {oldest.strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"Sesión más reciente: {newest.strftime('%Y-%m-%d %H:%M:%S')}")
            
    except ImportError:
        print("No se puede importar db_manager. ¿Está instalado?")
    except Exception as e:
        print(f"Error al mostrar estadísticas: {e}")

async def main():
    """Función principal con interfaz de línea de comandos."""
    # Configurar parser de argumentos
    parser = argparse.ArgumentParser(description="Herramienta de migración de sesiones Melodify")
    
    # Comandos principales
    parser.add_argument("--json-to-sqlite", action="store_true", 
                       help="Migrar desde JSON a SQLite")
    parser.add_argument("--sqlite-to-json", action="store_true",
                       help="Exportar desde SQLite a JSON")
    parser.add_argument("--verify", action="store_true",
                       help="Verificar la integridad de los datos en SQLite")
    parser.add_argument("--stats", action="store_true",
                       help="Mostrar estadísticas de la base de datos")
    parser.add_argument("--set-admin", type=str, 
                       help="Establecer administrador por ID (separar múltiples IDs con comas)")
    parser.add_argument("--set-premium", type=str,
                       help="Establecer usuarios premium por ID (separar múltiples IDs con comas)")
    
    # Opciones adicionales
    parser.add_argument("--input", type=str, default="user_sessions.json",
                       help="Archivo JSON de entrada (para --json-to-sqlite)")
    parser.add_argument("--output", type=str, default="exported_sessions.json",
                       help="Archivo JSON de salida (para --sqlite-to-json)")
    
    # Parsear argumentos
    args = parser.parse_args()
    
    # Configurar logging
    setup_logging()
    
    # Ejecutar el comando seleccionado
    if args.set_admin:
        try:
            admin_ids = [int(id.strip()) for id in args.set_admin.split(",")]
            result = await set_admins(admin_ids)
            if result["success"]:
                logging.info(f"Establecidos {result['updated']} administradores")
            else:
                logging.error(f"Error estableciendo administradores: {result.get('error', 'Error desconocido')}")
        except Exception as e:
            logging.error(f"Error procesando IDs de administrador: {e}")
    
    elif args.set_premium:
        try:
            premium_ids = [int(id.strip()) for id in args.set_premium.split(",")]
            mappings = {user_id: "premium" for user_id in premium_ids}
            result = await update_user_roles(mappings)
            if result["success"]:
                logging.info(f"Establecidos {result['updated']} usuarios premium")
            else:
                logging.error(f"Error estableciendo usuarios premium: {result.get('error', 'Error desconocido')}")
        except Exception as e:
            logging.error(f"Error procesando IDs premium: {e}")
            
    elif args.json_to_sqlite:
        success = await migrate_json_to_sqlite(args.input)
        if success:
            logging.info("Migración JSON → SQLite completada con éxito")
            if args.verify:
                await verify_migration()
        else:
            logging.error("La migración JSON → SQLite falló")
            
    elif args.sqlite_to_json:
        success = await migrate_sqlite_to_json(args.output)
        if success:
            logging.info(f"Exportación SQLite → JSON completada con éxito: {args.output}")
        else:
            logging.error("La exportación SQLite → JSON falló")
            
    elif args.verify:
        results = await verify_migration()
        if results["success"]:
            logging.info(f"Verificación completada. {results['total_sessions']} sesiones encontradas.")
            if 'roles_count' in results:
                logging.info(f"Distribución de roles: {results['roles_count']}")
        else:
            logging.error(f"Verificación fallida: {results.get('error', 'Error desconocido')}")
            
    elif args.stats:
        display_stats()
        
    else:
        parser.print_help()

if __name__ == "__main__":
    asyncio.run(main()) 