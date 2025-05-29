# Melodify Deluxe - Sistema de Roles y Permisos

## Cambios en la nueva actualización

Esta actualización introduce un completo sistema de roles y permisos que permite diferenciar entre usuarios normales, premium y administradores, ofreciendo distintas capacidades según el nivel de acceso.

### Principales novedades:

- **Sistema de roles**: Normal, Premium y Admin
- **Límites personalizados** por tipo de usuario
- **Base de datos SQLite** para persistencia de sesiones
- **Nuevos comandos** administrativos y premium
- **Interfaz mejorada** para configuración avanzada
- **Modo mantenimiento** para controlar el acceso al bot
- **Estadísticas detalladas** por usuario y globales

## Roles y sus beneficios

| Característica | Normal | Premium | Admin |
|---------------|--------|---------|-------|
| Descargas simultáneas | 2 | 5 | Sin límite |
| Formatos de audio | Estándar | Avanzados (FLAC) | Todos |
| Estadísticas | Básicas | Detalladas | Completas |
| Opciones de organización | Estándar | Personalizadas | Todas |
| Acceso durante mantenimiento | ❌ | ✅ | ✅ |
| Comandos administrativos | ❌ | ❌ | ✅ |

## Comandos para usuarios normales

- `/start` - Iniciar el bot y ver instrucciones
- `/config` - Configurar la calidad básica de audio
- `/stats` - Ver estadísticas básicas de uso
- `/premium` - Ver información sobre beneficios premium

## Comandos para usuarios premium

- `/premium` - Ver beneficios premium activos
- `/premium_stats` - Ver estadísticas detalladas de tus descargas
- `/premium_audio` - Configurar opciones avanzadas de audio

Los usuarios premium también pueden usar botones interactivos para:
- Cambiar calidad de audio (incluido FLAC)
- Personalizar formato de carpetas de descarga

## Comandos para administradores

- `/admin` - Ver ayuda de comandos administrativos
- `/setrole <user_id> <role>` - Cambiar el rol de un usuario
- `/userinfo <user_id>` - Ver información detallada de usuario
- `/stats_admin` - Ver estadísticas completas del sistema
- `/broadcast <mensaje>` - Enviar mensaje a todos los usuarios
- `/maintenance [on/off]` - Activar/desactivar modo mantenimiento

## Herramientas de administración

El script `setup_roles.py` permite gestionar usuarios desde línea de comandos:

```bash
# Establecer administradores iniciales
python setup_roles.py --set-admin 123456,789012

# Listar todos los usuarios con sus roles
python setup_roles.py --list

# Ver usuarios con un rol específico
python setup_roles.py --list-role admin
python setup_roles.py --list-role premium
```

## Guía de uso para administradores

### Configuración inicial

1. Configura al menos un administrador usando el script:
   ```
   python setup_roles.py --set-admin <TU_ID_TELEGRAM>
   ```

2. Inicia el bot y usa los comandos administrativos para configurar otros usuarios:
   ```
   /setrole <ID_USUARIO> premium
   ```

### Gestión de usuarios

- Para ver detalles de un usuario usa: `/userinfo <ID_USUARIO>`
- Para cambiar el rol de un usuario usa: `/setrole <ID_USUARIO> <ROLE>`
- Para eliminar sesiones usa los botones en la vista de `/userinfo`

### Comunicación y mantenimiento

- Para entrar en modo mantenimiento: `/maintenance on`
- Para salir del modo mantenimiento: `/maintenance off`
- Para enviar un mensaje a todos: `/broadcast <MENSAJE>`

### Estadísticas y exportación

- Ver estadísticas detalladas: `/stats_admin`
- Para exportar datos, usa el botón "Exportar datos" en las estadísticas

## Guía de uso para usuarios premium

1. Ver tus beneficios premium: `/premium`
2. Configurar calidad de audio avanzada: `/premium_audio`
3. Ver estadísticas detalladas: `/premium_stats`

## Migración desde versiones anteriores

Si ya tenías una base de datos existente, la actualización migrará automáticamente tus usuarios. Por defecto, todos los usuarios existentes mantendrán el rol "normal" hasta que un administrador les asigne un rol diferente.

Para migrar manualmente desde archivo JSON a la base de datos SQLite:
```
python migration_tool.py --json-to-sqlite
```

## Solución de problemas

- **Sin acceso admin**: Usa `setup_roles.py` para establecer un administrador
- **Error de base de datos**: Verifica permisos de escritura en la carpeta `data/`
- **Conflictos de sesión**: Reinicia el bot y vuelve a establecer roles
