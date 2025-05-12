#!/usr/bin/env python3
"""
Script de utilidad para configurar los administradores iniciales del sistema.

Este script permite establecer los usuarios administradores directamente
a través de la línea de comandos sin tener que usar el bot.
"""

import os
import sys
import asyncio
import logging
import argparse
from typing import List, Dict, Any

def setup_logging():
    """Configura el sistema de logging."""
    log_format = "%(asctime)s - %(levelname)s - %(message)s"
    logging.basicConfig(
        level=logging.INFO,
        format=log_format,
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler("roles_setup.log")
        ]
    )

async def set_admin_users(admin_ids: List[int]) -> bool:
    """
    Establece los usuarios administradores en la base de datos.
    
    Args:
        admin_ids: Lista de IDs de usuario a establecer como administradores
        
    Returns:
        True si la operación fue exitosa, False en caso contrario
    """
    try:
        # Importar módulos necesarios
        try:
            import db_manager
        except ImportError as e:
            logging.error(f"Error: No se puede importar db_manager: {e}")
            print("Asegúrate de que el módulo db_manager.py está en el mismo directorio o en el PYTHONPATH.")
            return False
            
        # Inicializar base de datos
        if not db_manager.initialize_database():
            logging.error("Error: No se pudo inicializar la base de datos.")
            return False
            
        # Procesar cada ID de administrador
        successful = 0
        failed = 0
        
        for user_id in admin_ids:
            if db_manager.set_user_role(user_id, "admin"):
                logging.info(f"[OK] Usuario {user_id} establecido como administrador")
                successful += 1
            else:
                logging.warning(f"[AVISO] No se pudo establecer al usuario {user_id} como administrador")
                failed += 1
                
        # Crear sesiones para estos usuarios si no existen
        for user_id in admin_ids:
            session = db_manager.load_user_session(user_id)
            if not session:
                # Crear datos mínimos para este usuario
                current_time = db_manager.time.time()
                session_data = {
                    "settings": {},
                    "last_activity": current_time,
                    "context_data": {},
                    "total_downloads": 0,
                    "active_downloads": 0,
                    "role": "admin",
                    "created_at": current_time,
                    "updated_at": current_time
                }
                if db_manager.save_user_session(user_id, session_data):
                    logging.info(f"[OK] Creada sesión inicial para el administrador {user_id}")
                else:
                    logging.warning(f"[AVISO] No se pudo crear sesión para el administrador {user_id}")
        
        # Mostrar resumen
        print(f"\nResumen de la operación:")
        print(f"- {successful} administradores establecidos correctamente")
        print(f"- {failed} operaciones fallidas")
        
        return successful > 0
        
    except Exception as e:
        logging.error(f"Error estableciendo administradores: {e}", exc_info=True)
        return False

async def list_users(role: str = None) -> None:
    """
    Lista los usuarios del sistema, opcionalmente filtrados por rol.
    
    Args:
        role: Rol para filtrar (None para mostrar todos)
    """
    try:
        import db_manager
        
        # Inicializar base de datos
        if not db_manager.initialize_database():
            logging.error("Error: No se pudo inicializar la base de datos.")
            return
            
        # Si se especifica un rol, obtener usuarios con ese rol
        if role:
            if role not in db_manager.VALID_ROLES:
                print(f"Rol no válido: {role}")
                print(f"Roles válidos: {', '.join(db_manager.VALID_ROLES)}")
                return
                
            users = db_manager.get_users_by_role(role)
            print(f"\nUsuarios con rol {role.upper()}: {len(users)}")
            for user_id in users:
                print(f"- ID: {user_id}")
        
        # Si no se especifica rol, mostrar todos los usuarios con su rol
        else:
            sessions = db_manager.load_all_sessions()
            roles = {r: [] for r in db_manager.VALID_ROLES}
            
            for user_id, session in sessions.items():
                user_role = session.get("role", "normal")
                if user_role in roles:
                    roles[user_role].append(user_id)
            
            # Mostrar información
            print("\nUsuarios por rol:")
            for role, users in roles.items():
                print(f"\n{role.upper()} ({len(users)} usuarios):")
                for user_id in users:
                    session = sessions[user_id]
                    last_active = db_manager.time.strftime(
                        '%Y-%m-%d %H:%M:%S', 
                        db_manager.time.localtime(session.get("last_activity", 0))
                    )
                    print(f"- ID: {user_id}, Última actividad: {last_active}")
        
    except ImportError:
        logging.error("Error: No se puede importar db_manager")
        print("Asegúrate de que el módulo db_manager.py está en el mismo directorio o en el PYTHONPATH.")
    except Exception as e:
        logging.error(f"Error listando usuarios: {e}", exc_info=True)

def parse_admin_ids(admin_ids_str: str) -> List[int]:
    """
    Parsea una cadena con IDs de administrador separadas por comas.
    
    Args:
        admin_ids_str: String con IDs (ej: "123456,789012,456789")
        
    Returns:
        Lista de IDs como enteros
    """
    try:
        return [int(x.strip()) for x in admin_ids_str.split(",") if x.strip()]
    except ValueError:
        logging.error("Error: Los IDs de usuario deben ser números enteros.")
        return []

async def main():
    """Función principal del script."""
    # Configurar parser de argumentos
    parser = argparse.ArgumentParser(
        description="Configurar administradores del sistema Melodify Deluxe"
    )
    
    # Acciones principales
    parser.add_argument("--set-admin", type=str, metavar="IDS",
                       help="IDs de usuarios a establecer como administradores (separados por comas)")
    parser.add_argument("--list", action="store_true",
                       help="Listar todos los usuarios con sus roles")
    parser.add_argument("--list-role", type=str, metavar="ROLE",
                       help=f"Listar usuarios con un rol específico (normal, premium, admin)")
    
    # Parsear argumentos
    args = parser.parse_args()
    
    # Configurar logging
    setup_logging()
    
    # Verificar que al menos hay una acción especificada
    if not (args.set_admin or args.list or args.list_role):
        parser.print_help()
        return
    
    # Ejecutar acción solicitada
    if args.set_admin:
        admin_ids = parse_admin_ids(args.set_admin)
        if not admin_ids:
            print("Error: No se proporcionaron IDs de administrador válidos.")
            return
            
        success = await set_admin_users(admin_ids)
        if success:
            print("\n[OK] Administradores configurados correctamente")
        else:
            print("\n[ERROR] Error configurando administradores")
    
    elif args.list:
        await list_users()
        
    elif args.list_role:
        await list_users(args.list_role)

if __name__ == "__main__":
    asyncio.run(main()) 