"""
Motor de búsqueda centralizado para Melodify Deluxe.

Este módulo proporciona funciones para realizar búsquedas en Deezer y manejar
los resultados, centralizando la lógica de búsqueda para evitar importaciones
circulares entre los módulos del bot.
"""

import logging
from io import BytesIO
from typing import Dict, List, Any, Optional, Union

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery
from telegram.ext import ContextTypes

async def search_content(dz, query: str, search_type: str = 'artist', limit: int = 5) -> List[Dict[str, Any]]:
    """
    Busca contenido en Deezer según el tipo especificado.
    
    Args:
        dz: Cliente Deezer autenticado
        query: Término de búsqueda
        search_type: Tipo de búsqueda ('artist', 'album', 'track')
        limit: Número máximo de resultados a devolver
        
    Returns:
        Lista de resultados obtenidos
    """
    try:
        # Realizar búsqueda según el tipo
        search_method = getattr(dz.api, f"search_{search_type}")
        search_results = search_method(query)
        
        # Verificar si hay resultados
        if not search_results or not search_results.get('data'):
            return []
        
        # Limitar resultados
        results = search_results['data'][:limit]
        return results
    except Exception as e:
        logging.error(f"Error en búsqueda de {search_type}: {str(e)}", exc_info=True)
        return []

async def show_search_menu(update, context):
    """
    Muestra el menú principal de búsqueda.
    
    Args:
        update: Objeto Update de Telegram
        context: Contexto del bot
    """
    # Obtener el texto de la consulta
    query = update.message.text.strip()
    
    # Crear teclado inline con opciones de búsqueda
    keyboard = [
        [InlineKeyboardButton("🎤 Buscar por Artista", callback_data=f"search:artist:{query}")],
        [InlineKeyboardButton("💿 Buscar por Álbum", callback_data=f"search:album:{query}")],
        [InlineKeyboardButton("🎵 Buscar por Canción", callback_data=f"search:track:{query}")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Enviar mensaje con opciones
    await update.message.reply_text(
        f"🔍 *Búsqueda de música*\n\n"
        f"Término de búsqueda: *{query}*\n\n"
        f"Selecciona el tipo de búsqueda:",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )

async def show_artist_results(query: CallbackQuery, results: List[Dict[str, Any]]) -> None:
    """
    Muestra resultados de búsqueda de artistas.
    
    Args:
        query: Objeto CallbackQuery de Telegram
        results: Lista de artistas encontrados
    """
    # Crear teclado con los resultados
    keyboard = []
    for artist in results:
        name = artist.get('name', 'Artista desconocido')
        artist_id = artist.get('id')
        fans = artist.get('nb_fan', 0)
        
        # Añadir botón para cada artista
        keyboard.append([
            InlineKeyboardButton(
                f"{name} ({fans} fans)",
                callback_data=f"artist:{artist_id}"
            )
        ])
    
    # Añadir botón para volver
    keyboard.append([
        InlineKeyboardButton("↩️ Volver", callback_data=f"back:search:{query.data.split(':')[2]}")
    ])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Actualizar mensaje con resultados
    await query.edit_message_text(
        f"🎤 *Artistas encontrados*\n\n"
        f"Selecciona un artista para ver detalles:",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )

async def show_album_results(query: CallbackQuery, results: List[Dict[str, Any]]) -> None:
    """
    Muestra resultados de búsqueda de álbumes.
    
    Args:
        query: Objeto CallbackQuery de Telegram
        results: Lista de álbumes encontrados
    """
    # Crear teclado con los resultados
    keyboard = []
    for album in results:
        title = album.get('title', 'Álbum desconocido')
        album_id = album.get('id')
        artist = album.get('artist', {}).get('name', 'Artista desconocido')
        
        # Añadir botón para cada álbum
        keyboard.append([
            InlineKeyboardButton(
                f"{title} - {artist}",
                callback_data=f"download:album:{album_id}"
            )
        ])
    
    # Añadir botón para volver
    keyboard.append([
        InlineKeyboardButton("↩️ Volver", callback_data=f"back:search:{query.data.split(':')[2]}")
    ])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Actualizar mensaje con resultados
    await query.edit_message_text(
        f"💿 *Álbumes encontrados*\n\n"
        f"Selecciona un álbum para descargarlo:",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )

async def show_track_results(query: CallbackQuery, results: List[Dict[str, Any]]) -> None:
    """
    Muestra resultados de búsqueda de canciones.
    
    Args:
        query: Objeto CallbackQuery de Telegram
        results: Lista de canciones encontradas
    """
    # Crear teclado con los resultados
    keyboard = []
    for track in results:
        title = track.get('title', 'Canción desconocida')
        track_id = track.get('id')
        artist = track.get('artist', {}).get('name', 'Artista desconocido')
        
        # Añadir botón para cada canción
        keyboard.append([
            InlineKeyboardButton(
                f"{title} - {artist}",
                callback_data=f"download:track:{track_id}"
            )
        ])
    
    # Añadir botón para volver
    keyboard.append([
        InlineKeyboardButton("↩️ Volver", callback_data=f"back:search:{query.data.split(':')[2]}")
    ])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Actualizar mensaje con resultados
    await query.edit_message_text(
        f"🎵 *Canciones encontradas*\n\n"
        f"Selecciona una canción para descargarla:",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )

async def show_artist_info(query: CallbackQuery, context: ContextTypes.DEFAULT_TYPE, artist_id: str) -> None:
    """
    Muestra información detallada de un artista.
    
    Args:
        query: Objeto CallbackQuery de Telegram
        context: Contexto del bot
        artist_id: ID del artista en Deezer
    """
    # Obtener cliente Deezer
    dz = context.bot_data.get('dz')
    
    try:
        # Obtener datos del artista
        artist = dz.api.get_artist(artist_id)
        
        if not artist:
            await query.edit_message_text("❌ No se pudo obtener información del artista")
            return
        
        # Extraer información
        name = artist.get('name', 'Artista desconocido')
        fans = artist.get('nb_fan', 0)
        albums_count = artist.get('nb_album', 0)
        
        # Crear teclado con opciones
        keyboard = [
            [InlineKeyboardButton("💿 Ver Álbumes", callback_data=f"artist_menu:{artist_id}:albums")],
            [InlineKeyboardButton("🔝 Canciones Populares", callback_data=f"artist_menu:{artist_id}:top")],
            [InlineKeyboardButton("↩️ Volver", callback_data=f"back:search:{name}")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # Actualizar mensaje con información
        await query.edit_message_text(
            f"🎤 *{name}*\n\n"
            f"👥 Fans: {fans:,}\n"
            f"💿 Álbumes: {albums_count}\n\n"
            f"¿Qué te gustaría ver?",
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )
        
    except Exception as e:
        logging.error(f"Error obteniendo info del artista {artist_id}: {e}", exc_info=True)
        await query.edit_message_text("❌ Error al obtener información del artista")

# Funciones adicionales para obtener detalles de artistas y álbumes...
# Estas funciones se implementarán a medida que se refactorice el código existente 