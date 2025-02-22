# Melodify_Deluxe

Bot para descargar canciones desde Deezer y administrar un vault de audios vía Telegram.

## Características
- Descarga automática de tracks.
- Gestión de un vault para evitar descargas duplicadas.
- Sincronización opcional con el historial del canal.
- Logging detallado para diagnóstico.

## Instalación
1. Clona el repositorio.
2. Instala los requerimientos (p.ej., `pip install -r requirements.txt`).
3. Configura los tokens en `config.py`.

## Uso
Ejecuta el bot:
```
python melodify_deluxe.py
```

## Estructura del Proyecto
- `bot.py` – Manejo de mensajes y comandos.
- `vault.py` – Gestión del vault de audios.
- `downloader.py` – Funciones para descarga asíncrona.
- `config.py` – Configuración y credenciales (revisar para seguridad).

## Notas
- Asegúrate de no compartir el token y credenciales incluidos en `config.py`.
- Se generan archivos temporales (descargas, JSON de vault) que se ignoran en el repositorio.
