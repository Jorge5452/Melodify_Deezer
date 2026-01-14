# -*- coding: utf-8 -*-
"""
Telegram utilities package.

Exports decorators, helpers, and validation functions.
"""

from src.interface.telegram.utils.decorators import (
    with_user_session,
    with_rate_limiting,
    with_error_handling,
    with_callback_error_handling,
    with_callback_user_session,
    combined_decorator,
    combined_callback_decorator,
)

from src.interface.telegram.utils.helpers import (
    SimulatedUser,
    SimulatedMessage,
    SimulatedUpdate,
    create_simulated_update,
    retry_async_operation,
)

from src.interface.telegram.utils.validation import (
    validate_deezer_url,
    get_content_type,
    extract_id_from_url,
)
