import json
import os
import logging

VAULT_JSON = "vault_data.json"

def load_vault():
    if os.path.exists(VAULT_JSON):
        try:
            with open(VAULT_JSON, 'r') as f:
                return json.load(f)
        except Exception as e:
            logging.error(f"Error cargando JSON: {str(e)}")
    return {}

def save_vault(data):
    try:
        with open(VAULT_JSON, 'w') as f:
            json.dump(data, f, indent=4)
    except Exception as e:
        logging.error(f"Error guardando JSON: {str(e)}")

