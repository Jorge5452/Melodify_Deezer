# -*- coding: utf-8 -*-
"""
URL validation utilities for Deezer content.

Provides functions to validate Deezer URLs and extract content information.
"""

import re
from typing import Optional

from src.config import (
    DEEZER_TRACK_REGEX,
    DEEZER_ALBUM_REGEX,
    DEEZER_PLAYLIST_REGEX
)


def validate_deezer_url(url: str) -> bool:
    """
    Validates if a URL is a valid Deezer URL.
    
    Checks if the provided URL matches any of the valid
    Deezer URL patterns (track, album or playlist).
    
    Args:
        url: The URL to validate
        
    Returns:
        bool: True if URL is valid, False otherwise
        
    Example:
        >>> validate_deezer_url("https://www.deezer.com/track/3135556")
        True
    """
    patterns = [DEEZER_TRACK_REGEX, DEEZER_ALBUM_REGEX, DEEZER_PLAYLIST_REGEX]
    return any(pattern.match(url) for pattern in patterns)


def get_content_type(url: str) -> str:
    """
    Determines the content type of a Deezer URL.
    
    Analyzes the URL to identify if it corresponds to a track,
    album or playlist from Deezer.
    
    Args:
        url: The Deezer URL to analyze
        
    Returns:
        str: Content type ("track", "album", "playlist" or "unknown")
        
    Example:
        >>> get_content_type("https://www.deezer.com/album/1234")
        "album"
    """
    if DEEZER_TRACK_REGEX.match(url):
        return "track"
    elif DEEZER_ALBUM_REGEX.match(url):
        return "album"
    elif DEEZER_PLAYLIST_REGEX.match(url):
        return "playlist"
    return "unknown"


def extract_id_from_url(url: str) -> str:
    """
    Extracts the ID from a Deezer URL.
    
    Analyzes the URL to extract the unique numeric identifier
    of the track, album or playlist.
    
    Args:
        url: The Deezer URL
        
    Returns:
        str: Extracted ID as string, or empty string if not found
        
    Example:
        >>> extract_id_from_url("https://www.deezer.com/track/3135556")
        "3135556"
    """
    for pattern in [DEEZER_TRACK_REGEX, DEEZER_ALBUM_REGEX, DEEZER_PLAYLIST_REGEX]:
        match = pattern.match(url)
        if match:
            return match.group(3)  # ID is in capture group 3
    return ""
