"""
Módulo de gestión del vault para Melodify Deezer.

El vault es un sistema de almacenamiento persistente que guarda file_ids de
archivos de Telegram para evitar volver a subir los mismos archivos repetidamente.
Implementa funciones para guardar, cargar y gestionar los datos con seguridad.
"""

import json
import os
import logging
import time
from typing import Dict, Any, Optional, List, Union, Tuple, Callable
from config import VAULT_JSON, VAULT_BACKUP, MAX_VAULT_ENTRIES

def validate_vault_data(data: Dict[str, Any]) -> bool:
    """
    Valida que los datos del vault tengan el formato correcto.
    
    Verifica que la estructura de datos sea un diccionario válido con
    claves de tipo string y valores que sean strings o listas de strings.
    
    Args:
        data: Diccionario con los datos del vault a validar
        
    Returns:
        True si los datos cumplen con la estructura esperada, False en caso contrario
    """
    # Verificar que sea un diccionario
    if not isinstance(data, dict):
        return False
    
    # Verificar estructura interna
    for key, value in data.items():
        # Las claves deben ser strings
        if not isinstance(key, str):
            return False
        # Los valores deben ser strings o listas de strings
        if not isinstance(value, (str, list)):
            return False
        # Si es lista, cada elemento debe ser string
        if isinstance(value, list):
            for item in value:
                if not isinstance(item, str):
                    return False
    
    # Todos los checks pasaron
    return True

def create_backup(data: Dict[str, Any]) -> None:
    """
    Crea una copia de seguridad del vault.
    
    Args:
        data: Diccionario con los datos del vault a respaldar
    """
    try:
        with open(VAULT_BACKUP, 'w') as f:
            json.dump(data, f, indent=4)
    except Exception as e:
        logging.error(f"Error creando backup del vault: {str(e)}")

def load_vault() -> Dict[str, Any]:
    """
    Carga los datos del vault desde el archivo JSON.
    
    Intenta cargar los datos del archivo principal y, si falla,
    intenta recuperarlos desde el archivo de backup.
    
    Returns:
        Diccionario con los datos del vault, o un diccionario vacío si hay errores
    """
    data: Dict[str, Any] = {}
    
    # Intentar cargar el archivo principal
    if os.path.exists(VAULT_JSON):
        try:
            with open(VAULT_JSON, 'r') as f:
                data = json.load(f)
            
            # Validar estructura de datos cargados
            if not validate_vault_data(data):
                logging.warning("Estructura de datos del vault.json inválida, intentando recuperar desde backup")
                # Forzamos la recuperación desde backup
                raise ValueError("Vault JSON inválido")
            
            return data
        except Exception as e:
            logging.error(f"Error al cargar vault.json: {str(e)}")
    
    # Si el archivo principal no existe o falla, intentar usar el backup
    if os.path.exists(VAULT_BACKUP):
        try:
            with open(VAULT_BACKUP, 'r') as f:
                data = json.load(f)
            if validate_vault_data(data):
                logging.info("Vault recuperado desde archivo de backup")
                return data
            else:
                logging.error("Estructura de datos del backup también es inválida")
        except Exception as e:
            logging.error(f"No se pudo recuperar desde backup: {str(e)}")
    
    # Si ambos intentos fallan, devolver diccionario vacío
    return data

def save_vault(data: Dict[str, Any]) -> bool:
    """
    Guarda los datos del vault en el archivo JSON.
    
    Realiza validación previa, crea una copia de seguridad y
    mantiene el tamaño del vault bajo control eliminando entradas
    antiguas si es necesario.
    
    Args:
        data: Diccionario con los datos a guardar
        
    Returns:
        True si se guardó correctamente, False en caso de error
    """
    # Validar datos antes de guardar
    if not validate_vault_data(data):
        logging.error("Intentando guardar datos inválidos en el vault")
        return False
    
    # Limitar el tamaño del vault para evitar archivos demasiado grandes
    if len(data) > MAX_VAULT_ENTRIES:
        # Obtener lista de claves para eliminar las más antiguas
        items_to_remove = len(data) - MAX_VAULT_ENTRIES
        keys_to_remove = list(data.keys())[:items_to_remove]
        
        # Eliminar entradas antiguas
        for key in keys_to_remove:
            del data[key]
        
        logging.info(f"Vault limpiado: se eliminaron {items_to_remove} entradas antiguas")
    
    try:
        # Crear backup antes de modificar el archivo principal
        if os.path.exists(VAULT_JSON):
            create_backup(data)
        
        # Guardar datos actualizados
        with open(VAULT_JSON, 'w') as f:
            json.dump(data, f, indent=4)
        return True
    except Exception as e:
        logging.error(f"Error guardando vault: {str(e)}")
        return False

def add_to_vault(key: str, value: Union[str, List[str]]) -> bool:
    """
    Añade una entrada al vault con verificación de integridad.
    
    Args:
        key: Clave única para el elemento (normalmente URL o ID del contenido)
        value: File ID de Telegram o lista de File IDs
        
    Returns:
        True si se añadió correctamente, False en caso de error
    """
    # Cargar datos actuales
    data = load_vault()
    
    # Añadir o actualizar entrada
    data[key] = value
    
    # Guardar cambios
    return save_vault(data)

def get_from_vault(key: str) -> Optional[Union[str, List[str]]]:
    """
    Obtiene una entrada del vault por su clave.
    
    Args:
        key: Clave a buscar (URL o ID del contenido)
        
    Returns:
        Valor asociado a la clave o None si no existe
    """
    data = load_vault()
    return data.get(key)

