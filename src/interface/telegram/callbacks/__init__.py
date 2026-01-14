# -*- coding: utf-8 -*-
"""
Telegram callbacks package.

Exports callback handlers for inline keyboard interactions.
"""

from src.interface.telegram.callbacks.search import process_search_callback

__all__ = [
    "process_search_callback",
]
