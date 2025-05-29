# Melodify Deluxe

Bot de Telegram para descargar música desde Deezer con alta calidad y organización.

## Características

- 🎵 Descarga canciones directamente desde enlaces de Deezer
- 💿 Soporte para álbumes y playlists completos
- 🔍 Búsqueda integrada de artistas, álbumes y canciones
- 🎧 Múltiples formatos de audio (FLAC, MP3 320kbps, MP3 128kbps)
- 📱 Envío directo a Telegram o guardado en un canal vault
- 🚀 Procesamiento en segundo plano para múltiples solicitudes
- ⏱️ Sistema de colas para optimizar recursos
- 📊 Estadísticas detalladas de uso
- 👑 Sistema de roles y permisos (normal, premium, admin)
- 💾 Persistencia de sesiones en base de datos SQLite

## Arquitectura

El proyecto sigue una arquitectura modular, con separación clara de responsabilidades:

- **Módulos Core**:
  - `melodify_deluxe.py`: Punto de entrada principal
  - `config.py`: Configuración centralizada
  - `user_session.py`: Gestión de sesiones de usuario
  - `downloader.py`: Lógica de descarga usando deemix
  - `vault.py`: Almacenamiento y recuperación de archivos
  - `db_manager.py`: Gestión de persistencia en base de datos
  - `migration_tool.py`: Herramienta para migración de datos

- **Módulos Funcionales**:
  - `modules/commands.py`: Manejadores de comandos
  - `modules/message_handler.py`: Procesamiento de mensajes
  - `modules/track_processor.py`: Procesador de pistas individuales
  - `modules/collection_processor.py`: Procesador de álbumes/playlists
  - `modules/search_engine.py`: Motor de búsqueda centralizado
  - `modules/audio_sender.py`: Envío de archivos de audio
  - `modules/callbacks.py`: Manejadores de callbacks
  - `modules/validation.py`: Validación de URLs
  - `modules/decorators.py`: Decoradores para funciones comunes
  - `modules/queue_manager.py`: Gestor de colas de tareas
  - `modules/admin_commands.py`: Comandos administrativos
  - `modules/premium_commands.py`: Funcionalidades para usuarios premium

## Sistema de Roles y Permisos

El bot implementa tres niveles de acceso para los usuarios:

- **Normal**: Usuarios estándar con funcionalidades básicas
  - Límite: 2 descargas simultáneas

- **Premium**: Usuarios con beneficios adicionales
  - Límite: 5 descargas simultáneas
  - Prioridad en cola de descargas
  - Opciones de audio avanzadas
  - Estadísticas detalladas de uso
  - Acceso durante modo mantenimiento

- **Admin**: Administradores del sistema
  - Sin límite de descargas simultáneas
  - Comandos de administración exclusivos
  - Gestión de usuarios (ver/modificar roles)
  - Estadísticas globales del sistema
  - Modo mantenimiento y broadcast

### Comandos de Administración

- `/setrole` - Establecer rol de usuario
- `/userinfo` - Ver información detallada de usuarios
- `/stats_admin` - Estadísticas detalladas del sistema
- `/broadcast` - Enviar mensaje a todos los usuarios
- `/maintenance` - Activar/desactivar modo mantenimiento
- `/admin` - Ayuda para comandos de administración

### Comandos Premium

- `/premium` - Ver beneficios premium
- `/premium_stats` - Estadísticas detalladas de uso
- `/premium_audio` - Configurar opciones avanzadas de audio

### Herramientas de Gestión

Para la configuración inicial de administradores:

```
python setup_roles.py --set-admin <ID_TELEGRAM>
```

Para ver usuarios por rol:

```
python setup_roles.py --list
```

## Patrones de Diseño

El proyecto implementa varios patrones de diseño:

- **Singleton**: Para el gestor de colas y sesiones
- **Decorator**: Para la gestión de sesiones, limitación de tasa, permisos y manejo de errores
- **Factory**: Para la creación de objetos de descarga
- **Repository**: Para el almacenamiento y recuperación de datos

## Sistema de Colas Avanzado

Las tareas pesadas (como descargas) se procesan a través de un sistema de colas para evitar bloqueos:

- **Cola Global**: Limita el número total de descargas concurrentes 
- **Colas por Usuario**: Cada usuario tiene su propia cola de descargas
- **Prioridades**: Las tareas tienen diferentes prioridades según su tipo
- **Límites por Rol**: Diferentes límites de concurrencia según el rol del usuario
- **Estadísticas**: Seguimiento detallado de tareas procesadas, fallidas y en cola

## Base de Datos y Persistencia

El sistema utiliza SQLite para almacenar:

- Sesiones de usuario
- Configuraciones personalizadas
- Estadísticas de uso
- Roles y permisos

Beneficios:
- Mantiene estado entre reinicios del bot
- Migración suave desde/hacia otros formatos
- Optimización automática de almacenamiento
- Respaldo sencillo con la herramienta incluida

## Mejoras de Rendimiento

- **Concurrencia Controlada**: Límites de tasa y concurrencia por usuario
- **Procesamiento Asíncrono**: Descargas en segundo plano sin bloquear el bot
- **Ejecución Optimizada**: Uso de generadores y patrones asíncronos
- **Gestión de Memoria**: Limpieza automática de recursos temporales

## Requisitos

- Python 3.8+
- Bibliotecas en `requirements.txt`
- Token de Telegram Bot API
- Cookie ARL de Deezer

## Instalación

1. Clonar el repositorio
2. Instalar dependencias: `pip install -r requirements.txt`
3. Crear archivo `.env` con los tokens necesarios (ver `.env.example`)
4. Configurar administradores iniciales: `python setup_roles.py --set-admin <ID_TELEGRAM>`
5. Ejecutar: `python melodify_deluxe.py`

## Configuración

El archivo `.env` debe contener:

```
TELEGRAM_TOKEN=tu_token_de_telegram
DEEZER_AR=tu_cookie_arl_de_deezer
VAULT_CHATID=id_del_chat_para_vault (opcional)
```

## Comandos Disponibles

- `/start` - Iniciar el bot y ver instrucciones
- `/config` - Configurar la calidad de audio
- `/stats` - Ver estadísticas de uso
- `/premium` - Ver beneficios premium (si tienes acceso)

## Créditos

Desarrollado utilizando:
- [python-telegram-bot](https://github.com/python-telegram-bot/python-telegram-bot)
- [deemix](https://gitlab.com/RemixDev/deemix)
- [deezer-python](https://github.com/browniebroke/deezer-python)