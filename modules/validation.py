import re
from typing import Optional, Pattern
from config import (
    DEEZER_TRACK_REGEX,
    DEEZER_ALBUM_REGEX,
    DEEZER_PLAYLIST_REGEX
)

def validate_deezer_url(url: str) -> bool:
    """
    Valida si una URL es una URL válida de Deezer.
    
    Comprueba si la URL proporcionada coincide con alguno de los patrones
    de URLs válidas de Deezer (pista, álbum o playlist).
    
    Args:
        url: La URL a validar
        
    Returns:
        bool: True si la URL es válida, False en caso contrario
        
    Example:
        >>> validate_deezer_url("https://www.deezer.com/track/3135556")
        True
    """
    patterns = [DEEZER_TRACK_REGEX, DEEZER_ALBUM_REGEX, DEEZER_PLAYLIST_REGEX]
    return any(pattern.match(url) for pattern in patterns)

def get_content_type(url: str) -> str:
    """
    Determina el tipo de contenido de una URL de Deezer.
    
    Analiza la URL para identificar si corresponde a una pista, 
    álbum o playlist de Deezer.
    
    Args:
        url: La URL de Deezer a analizar
        
    Returns:
        str: El tipo de contenido ("track", "album", "playlist" o "unknown")
        
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
    Extrae el ID de una URL de Deezer.
    
    Analiza la URL para extraer el identificador numérico único
    de la pista, álbum o playlist.
    
    Args:
        url: La URL de Deezer
        
    Returns:
        str: El ID extraído como string, o una cadena vacía si no se encontró
        
    Example:
        >>> extract_id_from_url("https://www.deezer.com/track/3135556")
        "3135556"
    """
    for pattern in [DEEZER_TRACK_REGEX, DEEZER_ALBUM_REGEX, DEEZER_PLAYLIST_REGEX]:
        match = pattern.match(url)
        if match:
            return match.group(3)  # El ID está en el grupo de captura 3
    return ""
