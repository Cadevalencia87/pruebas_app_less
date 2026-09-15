# Unidad Chocoflán — portal personal CMS

Un sitio independiente para Less/Leslie: un directorio público de páginas personalizadas y un panel privado para administrarlas. Combina el lenguaje de un sistema ridículamente formal con espacio para detalles sencillos, cálidos y sin presión.

No comparte código, base de datos ni servicio con la encuesta de satisfacción anterior.

## Qué incluye

- Directorio público en `/`: lista automáticamente las páginas activas.
- Páginas en `/p/<slug>` de cuatro tipos: informativa, confirmación, encuesta y propuesta/especial.
- Panel privado en `/admin` con inicio de sesión, creación, edición, publicación, borrado, estadísticas y archivo de respuestas.
- Encuestas configurables desde el panel: opción múltiple, escala numérica o texto libre.
- Confirmaciones de dos botones y propuestas especiales con registro de interacción y mensaje posterior.
- Contraseñas con hash, sesión firmada, token CSRF en formularios, validación de entradas y consultas SQLite parametrizadas.
- Imágenes mediante URL externa; no hay subida de archivos.

## Estructura

```
app.py                 Aplicación Flask, rutas, base de datos y seguridad
templates/             Vistas públicas y panel privado
static/css/style.css   Identidad visual propia
static/js/editor.js    Editor visual de configuraciones del CMS
requirements.txt       Dependencias
Procfile               Inicio compatible con plataformas PaaS
render.yaml            Plano opcional para Render
```

## Ejecutarlo en tu PC

Requisito: Python 3.10 o posterior.

1. Abre una terminal dentro de esta carpeta y crea el entorno virtual:

   ```powershell
   py -m venv .venv
   .\.venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   ```

2. Copia `.env.example` como `.env` y cambia sus valores. En PowerShell, para esta sesión puedes definirlos así:

   ```powershell
   $env:SECRET_KEY = "un-secreto-largo-aleatorio-distinto-para-este-proyecto"
   $env:ADMIN_USERNAME = "tu_usuario"
   $env:ADMIN_PASSWORD = "una-contrasena-larga-de-12-caracteres-o-mas"
   ```

   Flask no carga archivos `.env` por sí solo; usa las variables anteriores o configura un cargador de entorno de tu preferencia. `DATABASE_PATH` es opcional y por defecto usa `instance/less_portal.sqlite3`.

3. Inicializa y crea el administrador (solo una vez):

   ```powershell
   flask --app app init-db
   flask --app app create-admin
   ```

   Los dos comandos toman `ADMIN_USERNAME` y `ADMIN_PASSWORD` de las variables de entorno. Si ya existe ese usuario, `create-admin` se detiene sin modificarlo.

4. Arranca el sitio:

   ```powershell
   flask --app app run --debug
   ```

   Visita `http://127.0.0.1:5000` y entra a `http://127.0.0.1:5000/admin/login`.

## Crear la primera página de prueba

1. Desde el panel, abre **Páginas** y presiona **Nueva página**.
2. Prueba con título `Solicitud oficial: ramen`, slug `plan-ramen`, tipo **Confirmación** y estado publicado.
3. Escribe los textos de los dos botones, por ejemplo “Sí, se antoja” y “Reprogramar trámite”, además del mensaje posterior.
4. Guarda. La página aparece de inmediato en el directorio y queda disponible en `/p/plan-ramen`.
5. Usa el enlace de esa tabla para probarla. Cada clic de confirmación se archiva en **Respuestas**.

Para una encuesta, elige **Encuesta**. El editor permite añadir preguntas y elegir sus tipos. Para una página íntima o significativa, usa **Propuesta / especial**: cambia la presentación pública a un estilo más suave y solo muestra un botón principal.

## Despliegue separado en GitHub y Render

1. Crea un repositorio nuevo en GitHub, por ejemplo `unidad-chocoflan`. No lo agregues al repositorio de la encuesta anterior.
2. Sube **esta carpeta completa** al repositorio. No subas `.env`, `instance/` ni ningún archivo `.sqlite3`.
3. En [Render](https://render.com), elige **New + → Web Service**, conecta el repositorio nuevo y autoriza el acceso.
4. Selecciona la rama deseada. Render detecta `render.yaml`; si lo configuras manualmente, usa:
   - Runtime: `Python 3`
   - Build command: `pip install -r requirements.txt`
   - Start command: `gunicorn app:app`
5. En **Environment**, define estas variables (Render puede generar `SECRET_KEY` automáticamente al usar el blueprint, pero revisa que exista):
   - `SECRET_KEY`: una cadena aleatoria larga, única y secreta.
   - `ADMIN_USERNAME`: el usuario inicial del panel.
   - `ADMIN_PASSWORD`: contraseña de 12 caracteres o más.
   - `DATABASE_PATH` (opcional): deja el valor por defecto para SQLite local del servicio.
6. Crea el servicio. En el primer arranque, si todavía no hay administradores, la app crea el usuario indicado por `ADMIN_USERNAME` y `ADMIN_PASSWORD`. Después ya no vuelve a crear usuarios automáticamente.
7. Abre la URL de Render y entra por `/admin/login`. Crea la primera página siguiendo la guía anterior.

## Importante: SQLite y Render gratuito

SQLite funciona para probar y para una demo pequeña, pero el disco local de un servicio gratuito de Render es efímero. Un reinicio, redeploy o cambio de instancia puede borrar la base de datos: eso incluye administrador, páginas y respuestas. No hay persistencia garantizada con esa configuración.

Por eso las imágenes siempre son URLs externas, pero también debes conservar una copia de tu contenido importante fuera del servicio. Cuando el proyecto necesite conservar respuestas, la ruta natural es migrar a Render PostgreSQL u otro Postgres persistente y sustituir la capa SQLite; esta versión no promete ni simula esa persistencia.

## Operación y notas de seguridad

- No reutilices el `SECRET_KEY` de otro proyecto; al cambiarlo se invalidan sesiones existentes.
- Usa una contraseña de administrador única y larga. No la escribas en el repositorio.
- El panel y las respuestas requieren sesión de administrador. Las URLs públicas solo exponen páginas marcadas como activas.
- Al borrar una página se borran también sus respuestas asociadas. Es una acción irreversible.
- Para cambiar el administrador actual, crea una nueva base local y ejecuta el comando de alta, o gestiona el registro directamente durante mantenimiento. No existe una pantalla pública de registro por diseño.
