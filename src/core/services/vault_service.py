# -*- coding: utf-8 -*-
"""
Vault service for Melodify Deezer.

The vault is a persistent storage system that saves Telegram file_ids
to avoid re-uploading the same files repeatedly.
Implements functions for saving, loading and managing data securely.
"""

import json
import os
import logging
from typing import Dict, Any, Optional, List, Union

from src.config import VAULT_JSON, VAULT_BACKUP, MAX_VAULT_ENTRIES


def validate_vault_data(data: Dict[str, Any]) -> bool:
    """
    Validates that vault data has the correct format.
    
    Verifies that the data structure is a valid dictionary with
    string keys and values that are either strings or lists of strings.
    
    Args:
        data: Dictionary with vault data to validate
        
    Returns:
        True if data meets expected structure, False otherwise
    """
    # Verify it's a dictionary
    if not isinstance(data, dict):
        return False
    
    # Verify internal structure
    for key, value in data.items():
        # Keys must be strings
        if not isinstance(key, str):
            return False
        # Values must be strings or lists of strings
        if not isinstance(value, (str, list)):
            return False
        # If it's a list, each element must be string
        if isinstance(value, list):
            for item in value:
                if not isinstance(item, str):
                    return False
    
    # All checks passed
    return True


def create_backup(data: Dict[str, Any]) -> None:
    """
    Creates a backup of the vault.
    
    Args:
        data: Dictionary with vault data to backup
    """
    try:
        with open(VAULT_BACKUP, 'w') as f:
            json.dump(data, f, indent=4)
    except Exception as e:
        logging.error(f"Error creating vault backup: {str(e)}")


def load_vault() -> Dict[str, Any]:
    """
    Loads vault data from the JSON file.
    
    Attempts to load data from the main file and, if it fails,
    tries to recover from the backup file.
    
    Returns:
        Dictionary with vault data, or empty dictionary on errors
    """
    data: Dict[str, Any] = {}
    
    # Try to load main file
    if os.path.exists(VAULT_JSON):
        try:
            with open(VAULT_JSON, 'r') as f:
                data = json.load(f)
            
            # Validate loaded data structure
            if not validate_vault_data(data):
                logging.warning("Invalid vault.json data structure, trying to recover from backup")
                # Force recovery from backup
                raise ValueError("Invalid Vault JSON")
            
            return data
        except Exception as e:
            logging.error(f"Error loading vault.json: {str(e)}")
    
    # If main file doesn't exist or fails, try backup
    if os.path.exists(VAULT_BACKUP):
        try:
            with open(VAULT_BACKUP, 'r') as f:
                data = json.load(f)
            if validate_vault_data(data):
                logging.info("Vault recovered from backup file")
                return data
            else:
                logging.error("Backup data structure is also invalid")
        except Exception as e:
            logging.error(f"Could not recover from backup: {str(e)}")
    
    # If both attempts fail, return empty dictionary
    return data


def save_vault(data: Dict[str, Any]) -> bool:
    """
    Saves vault data to the JSON file.
    
    Performs prior validation, creates a backup and
    keeps vault size under control by removing old entries if necessary.
    
    Args:
        data: Dictionary with data to save
        
    Returns:
        True if saved successfully, False on error
    """
    # Validate data before saving
    if not validate_vault_data(data):
        logging.error("Attempting to save invalid data to vault")
        return False
    
    # Limit vault size to avoid overly large files
    if len(data) > MAX_VAULT_ENTRIES:
        # Get list of keys to remove oldest ones
        items_to_remove = len(data) - MAX_VAULT_ENTRIES
        keys_to_remove = list(data.keys())[:items_to_remove]
        
        # Remove old entries
        for key in keys_to_remove:
            del data[key]
        
        logging.info(f"Vault cleaned: removed {items_to_remove} old entries")
    
    try:
        # Create backup before modifying main file
        if os.path.exists(VAULT_JSON):
            create_backup(data)
        
        # Save updated data
        with open(VAULT_JSON, 'w') as f:
            json.dump(data, f, indent=4)
        return True
    except Exception as e:
        logging.error(f"Error saving vault: {str(e)}")
        return False


def add_to_vault(key: str, value: Union[str, List[str]]) -> bool:
    """
    Adds an entry to the vault with integrity verification.
    
    Args:
        key: Unique key for the element (normally URL or content ID)
        value: Telegram file ID or list of file IDs
        
    Returns:
        True if added successfully, False on error
    """
    # Load current data
    data = load_vault()
    
    # Add or update entry
    data[key] = value
    
    # Save changes
    return save_vault(data)


def get_from_vault(key: str) -> Optional[Union[str, List[str]]]:
    """
    Gets an entry from the vault by its key.
    
    Args:
        key: Key to search (URL or content ID)
        
    Returns:
        Value associated with key or None if not found
    """
    data = load_vault()
    return data.get(key)


def delete_from_vault(key: str) -> bool:
    """
    Deletes an entry from the vault.
    
    Args:
        key: Key to delete
        
    Returns:
        True if deleted successfully, False otherwise
    """
    data = load_vault()
    if key in data:
        del data[key]
        return save_vault(data)
    return False


def get_vault_stats() -> Dict[str, Any]:
    """
    Gets statistics about the vault.
    
    Returns:
        Dictionary with vault statistics
    """
    data = load_vault()
    return {
        "total_entries": len(data),
        "max_entries": MAX_VAULT_ENTRIES,
        "usage_percent": (len(data) / MAX_VAULT_ENTRIES) * 100 if MAX_VAULT_ENTRIES > 0 else 0
    }
