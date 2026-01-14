# -*- coding: utf-8 -*-
"""
Constants module: Static values and compiled patterns.

This module contains constants that do not depend on environment variables.
"""

import re
from typing import Pattern


class TrackFormats:
    """
    Defines available formats for music track downloads.
    
    Numeric values correspond to Deezer quality codes:
    - FLAC: Lossless audio
    - MP3_320: High quality MP3 (320kbps)
    - MP3_128: Standard quality MP3 (128kbps)
    - MP4_RA*: Adaptive audio formats with various qualities
    """
    FLAC: int = 9      # FLAC 1411kbps
    MP3_320: int = 3   # MP3 320kbps
    MP3_128: int = 1   # MP3 128kbps
    MP4_RA3: int = 15  # MP4 high quality
    MP4_RA2: int = 14  # MP4 medium quality
    MP4_RA1: int = 13  # MP4 low quality
    DEFAULT: int = 8   # Best available quality
    LOCAL: int = 0     # Local file


# ----- REGULAR EXPRESSIONS -----
# Compiled patterns for validating and extracting info from Deezer URLs
DEEZER_TRACK_REGEX: Pattern = re.compile(
    r'(https?://)?(www\.)?deezer\.com/(?:\w{2}/)?track/(\d+)'
)
DEEZER_ALBUM_REGEX: Pattern = re.compile(
    r'(https?://)?(www\.)?deezer\.com/(?:\w{2}/)?album/(\d+)'
)
DEEZER_PLAYLIST_REGEX: Pattern = re.compile(
    r'(https?://)?(www\.)?deezer\.com/(?:\w{2}/)?playlist/(\d+)'
)

# ----- PROCESSING CONSTANTS -----
# Number of tracks to process per batch in large collections
BATCH_SIZE: int = 5

# ----- VAULT CONSTANTS -----
VAULT_JSON = "vault_data.json"
VAULT_BACKUP = "vault_data.backup.json"
MAX_VAULT_ENTRIES = 1000  # Maximum entries in the vault
