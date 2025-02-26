import json
import os
import logging
import time
from typing import Dict, Any, Optional, List, Union

VAULT_JSON = "vault_data.json"
VAULT_BACKUP = "vault_data.backup.json"
MAX_VAULT_ENTRIES = 1000  # Limitar el vault a 1000 entradas

def validate_vault_data(data: Dict[str, Any]) -> bool:
    """
    Valida que los datos del vault tengan el formato correcto.
    
    Args:
        data: Diccionario con los datos del vault
        
    Returns:
        True si los datos son válidos, False en caso contrario
    """
    if not isinstance(data, dict):
        return False
    
    # Verificar estructura básica
    for key, value in data.items():
        if not isinstance(key, str):
            return False
        if not isinstance(value, (str, list)):
            return False
        if isinstance(value, list):
            for item in value:
                if not isinstance(item, str):
                    return False
    
    return True

def create_backup(data: Dict[str, Any]) -> None:
    """Crea una copia de seguridad del vault."""
    try:
        with open(VAULT_BACKUP, 'w') as f:
            json.dump(data, f, indent=4)
    except Exception as e:
        logging.error(f"Error creando backup del vault: {str(e)}")

def load_vault() -> Dict[str, Any]:
    """
    Carga los datos del vault desde el archivo JSON.
    
    Returns:
        Diccionario con los datos del vault, o un diccionario vacío si hay errores.
    """
    data = {}
    
    # Intentar cargar vault_data.json
    if os.path.exists(VAULT_JSON):
        try:
            with open(VAULT_JSON, 'r') as f:
                data = json.load(f)
            
            # Validar datos del vault.json
            if not validate_vault_data(data):
                logging.warning("Estructura de datos del vault.json inválida, intentando recuperar desde backup")
                # Forzamos la recuperación desde backup
                raise ValueError("Vault JSON inválido")
            
            return data
        except Exception as e:
            logging.error(f"Error al cargar vault.json: {str(e)}")
    
    # Si vault_data.json no existe o falla, intentar usar el backup
    if os.path.exists(VAULT_BACKUP):
        try:
            with open(VAULT_BACKUP, 'r') as f:
                data = json.load(f)
            if validate_vault_data(data):
                logging.info("Vault recuperado desde backup")
                return data
            else:
                logging.error("Estructura de datos del backup inválida")
        except Exception as e:
            logging.error(f"No se pudo recuperar desde backup: {str(e)}")
    
    return data

def save_vault(data: Dict[str, Any]) -> bool:
    """
    Guarda los datos del vault en el archivo JSON.
    
    Args:
        data: Diccionario con los datos a guardar
        
    Returns:
        True si se guardó correctamente, False en caso contrario
    """
    # Validar datos antes de guardar
    if not validate_vault_data(data):
        logging.error("Intentando guardar datos inválidos en el vault")
        return False
    
    # Limitar el tamaño del vault
    if len(data) > MAX_VAULT_ENTRIES:
        # Ordenar por timestamp si existe, de lo contrario usar orden arbitrario
        items_to_remove = len(data) - MAX_VAULT_ENTRIES
        keys_to_remove = list(data.keys())[:items_to_remove]
        for key in keys_to_remove:
            del data[key]
        logging.info(f"Vault limpiado: se eliminaron {items_to_remove} entradas antiguas")
    
    try:
        # Crear backup primero
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
    Añade una entrada al vault con verificación de tamaño.
    
    Args:
        key: Clave única para el elemento
        value: File ID de Telegram o lista de File IDs
        
    Returns:
        True si se añadió correctamente, False en caso contrario
    """
    data = load_vault()
    data[key] = value
    return save_vault(data)

def get_from_vault(key: str) -> Optional[Union[str, List[str]]]:
    """
    Obtiene una entrada del vault.
    
    Args:
        key: Clave a buscar
        
    Returns:
        Valor asociado a la clave o None si no existe
    """
    data = load_vault()
    return data.get(key)

