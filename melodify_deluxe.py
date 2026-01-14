# -*- coding: utf-8 -*-
"""
Punto de entrada principal para Melodify Deluxe.
Redirige al nuevo sistema modular en src.
"""

import sys
import logging
from src.main import run

if __name__ == "__main__":
    try:
        run()
    except KeyboardInterrupt:
        pass
    except Exception as e:
        print(f"Error fatal irrecoverable: {e}")
        logging.critical("Error fatal irrecoverable", exc_info=True)
        sys.exit(1)
