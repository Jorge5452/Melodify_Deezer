# Melodify_Deluxe

Bot para descargar canciones desde Deezer y administrar un vault de audios vía Telegram.

## Características
- Descarga automática de tracks.
- Gestión de un vault para evitar descargas duplicadas.
- Sincronización opcional con el historial del canal.
- Logging detallado para diagnóstico.
- **Soporte para múltiples usuarios concurrentes.**
- Sistema de colas de descargas por usuario.
- Limitación de tasa para evitar sobrecarga.
- Estadísticas de uso por usuario.

## Instalación
1. Clona el repositorio.
2. Crea un entorno virtual:

   **Windows:**
   ```
   python -m venv deluxe
   ```
   
   **Linux:**
   ```
   python3 -m venv deluxe
   ```

3. Activa el entorno virtual:


   **Windows:**
   ```
   deluxe\Scripts\activate
   ```
   
   **Linux:**
   ```
   source deluxe/bin/activate
   ```

4. Instala los requerimientos:
   ```
   pip install -r requirements.txt
   ```

5. Configura el archivo `.env` con tus credenciales siguiendo el formato de `.env.example`.

## Uso
Ejecuta el bot (con el entorno virtual activado):
**Windows:**
```
python melodify_deluxe.py

```
**Linux:**
```
python3 melodify_deluxe.py

```

### Comandos disponibles
- `/start` - Inicia el bot y muestra información de ayuda.
- `/config` - Configura la calidad de audio para las descargas.
- `/stats` - Muestra estadísticas de uso del usuario y del sistema.

## Estructura del Proyecto
- `bot.py` – Manejo de mensajes y comandos.
- `vault.py` – Gestión del vault de audios.
- `downloader.py` – Funciones para descarga asíncrona.
- `user_session.py` - Gestión de sesiones de usuarios y colas de descargas.
- `content_processors.py` - Procesadores para distintos tipos de contenido.
- `.env` – Configuración y credenciales (no incluido en el repositorio).
- `.env.example` – Plantilla para configurar tus propias credenciales.

## Características Avanzadas

### Sistema de Usuarios Concurrentes
El bot implementa un sistema avanzado para manejar múltiples usuarios y solicitudes concurrentes:

- **Sesiones de usuario**: Cada usuario tiene su propia sesión que mantiene su estado y preferencias.
- **Colas de descarga**: Las solicitudes se encolan para cada usuario, permitiendo múltiples descargas simultáneas.
- **Limitación de tasa**: Se controla el número de solicitudes por intervalo de tiempo para evitar sobrecarga.
- **Semáforos globales**: Se limita la cantidad total de descargas concurrentes en todo el sistema.
- **Limpieza automática**: Las sesiones inactivas se eliminan después de un período de inactividad.

## Notas
- **No incluyas tu archivo `.env` en el repositorio** ya que contiene información sensible.
- Se generan archivos temporales (descargas, JSON de vault) que se ignoran en el repositorio.