import re
from config import (
    DEEZER_TRACK_REGEX,
    DEEZER_ALBUM_REGEX,
    DEEZER_PLAYLIST_REGEX
)

def validate_deezer_url(url: str) -> bool:
    """Valida si una URL es una URL válida de Deezer."""
    patterns = [DEEZER_TRACK_REGEX, DEEZER_ALBUM_REGEX, DEEZER_PLAYLIST_REGEX]
    return any(pattern.match(url) for pattern in patterns)

def get_content_type(url: str) -> str:
    """Determina el tipo de contenido de una URL de Deezer."""
    if DEEZER_TRACK_REGEX.match(url):
        return "track"
    elif DEEZER_ALBUM_REGEX.match(url):
        return "album"
    elif DEEZER_PLAYLIST_REGEX.match(url):
        return "playlist"
    return "unknown"

def extract_id_from_url(url: str) -> str:
    """Extrae el ID de una URL de Deezer."""
    for pattern in [DEEZER_TRACK_REGEX, DEEZER_ALBUM_REGEX, DEEZER_PLAYLIST_REGEX]:
        match = pattern.match(url)
        if match:
            return match.group(3)  # El ID está en el grupo de captura 3
    return ""
