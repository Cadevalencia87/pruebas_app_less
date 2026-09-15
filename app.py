import json
import os
import re
import secrets
import sqlite3
from datetime import datetime, timezone
from functools import wraps

import click
from flask import Flask, abort, flash, g, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash


BASE_DIR = os.path.abspath(os.path.dirname(__file__))
PAGE_TYPES = {"informativa", "confirmacion", "encuesta", "especial"}


def utcnow():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def create_app(test_config=None):
    app = Flask(__name__)
    app.config.from_mapping(
        SECRET_KEY=os.environ.get("SECRET_KEY", ""),
        DATABASE=os.environ.get("DATABASE_PATH", os.path.join(BASE_DIR, "instance", "less_portal.sqlite3")),
    )
    if test_config:
        app.config.update(test_config)
    if not app.config["SECRET_KEY"]:
        raise RuntimeError("Define SECRET_KEY antes de iniciar la aplicación.")
    database_dir = os.path.dirname(app.config["DATABASE"])
    if database_dir:
        os.makedirs(database_dir, exist_ok=True)

    def get_db():
        if "db" not in g:
            g.db = sqlite3.connect(app.config["DATABASE"])
            g.db.row_factory = sqlite3.Row
            g.db.execute("PRAGMA foreign_keys = ON")
        return g.db

    @app.teardown_appcontext
    def close_db(_error=None):
        db = g.pop("db", None)
        if db is not None:
            db.close()

    def init_db():
        db = get_db()
        db.executescript("""
            CREATE TABLE IF NOT EXISTS admins (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE COLLATE NOCASE,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS paginas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                slug TEXT NOT NULL UNIQUE,
                titulo TEXT NOT NULL,
                subtitulo TEXT NOT NULL DEFAULT '',
                contenido TEXT NOT NULL DEFAULT '',
                imagen_url TEXT NOT NULL DEFAULT '',
                tipo TEXT NOT NULL CHECK(tipo IN ('informativa','confirmacion','encuesta','especial')),
                configuracion TEXT NOT NULL DEFAULT '{}',
                activa INTEGER NOT NULL DEFAULT 1 CHECK(activa IN (0,1)),
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS respuestas_confirmacion (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pagina_id INTEGER NOT NULL,
                respuesta TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(pagina_id) REFERENCES paginas(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS respuestas_encuesta (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pagina_id INTEGER NOT NULL,
                respuestas TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(pagina_id) REFERENCES paginas(id) ON DELETE CASCADE
            );
        """)
        db.commit()

    @app.cli.command("init-db")
    def init_db_command():
        """Crea las tablas de la aplicación."""
        init_db()
        click.echo("Base de datos inicializada.")

    @app.cli.command("create-admin")
    @click.option("--username", envvar="ADMIN_USERNAME", required=True)
    @click.option("--password", envvar="ADMIN_PASSWORD", required=True)
    def create_admin(username, password):
        """Crea el primer administrador desde variables de entorno o argumentos."""
        init_db()
        username = username.strip()
        if not re.fullmatch(r"[A-Za-z0-9_.-]{3,40}", username):
            raise click.UsageError("El usuario debe tener 3-40 caracteres: letras, números, _, . o -.")
        if len(password) < 12:
            raise click.UsageError("La contraseña debe tener al menos 12 caracteres.")
        try:
            get_db().execute("INSERT INTO admins (username, password_hash, created_at) VALUES (?, ?, ?)",
                (username, generate_password_hash(password), utcnow()))
            get_db().commit()
        except sqlite3.IntegrityError:
            raise click.UsageError("Ese usuario ya existe.")
        click.echo(f"Administrador '{username}' creado.")

    def csrf_token():
        if "csrf_token" not in session:
            session["csrf_token"] = secrets.token_urlsafe(32)
        return session["csrf_token"]

    app.jinja_env.globals["csrf_token"] = csrf_token
    app.jinja_env.filters["fromjson"] = lambda value: json.loads(value)

    @app.before_request
    def csrf_protect():
        if request.method == "POST" and request.endpoint not in {"static"}:
            submitted = request.form.get("csrf_token", "")
            if not submitted or not secrets.compare_digest(submitted, session.get("csrf_token", "")):
                abort(400, "Solicitud no válida. Recarga la página e inténtalo de nuevo.")

    def login_required(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if "admin_id" not in session:
                flash("Inicia sesión para entrar al panel.", "warning")
                return redirect(url_for("login"))
            return view(*args, **kwargs)
        return wrapped

    def get_page_or_404(slug, include_inactive=False):
        query = "SELECT * FROM paginas WHERE slug = ?"
        params = [slug]
        if not include_inactive:
            query += " AND activa = 1"
        page = get_db().execute(query, params).fetchone()
        if page is None:
            abort(404)
        return page

    def parse_config(raw, page_type):
        try:
            config = json.loads(raw or "{}")
        except json.JSONDecodeError:
            raise ValueError("La configuración no contiene JSON válido.")
        if not isinstance(config, dict):
            raise ValueError("La configuración debe ser un objeto JSON.")
        if page_type == "encuesta":
            questions = config.get("preguntas", [])
            if not isinstance(questions, list) or not questions:
                raise ValueError("La encuesta necesita al menos una pregunta.")
            for question in questions:
                if not isinstance(question, dict) or not str(question.get("texto", "")).strip():
                    raise ValueError("Cada pregunta necesita texto.")
                if question.get("tipo") not in {"opcion", "escala", "texto"}:
                    raise ValueError("Tipo de pregunta no válido.")
                if question["tipo"] == "opcion":
                    options = question.get("opciones", [])
                    if not isinstance(options, list) or len(options) < 2:
                        raise ValueError("Las preguntas de opción necesitan al menos dos opciones.")
        return config

    def page_payload(form):
        title = form.get("titulo", "").strip()
        slug = form.get("slug", "").strip().lower()
        subtitle = form.get("subtitulo", "").strip()
        content = form.get("contenido", "").strip()
        image_url = form.get("imagen_url", "").strip()
        page_type = form.get("tipo", "")
        if not title or len(title) > 120:
            raise ValueError("El título es obligatorio y admite hasta 120 caracteres.")
        if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", slug):
            raise ValueError("El slug usa minúsculas, números y guiones (ejemplo: plan-ramen).")
        if page_type not in PAGE_TYPES:
            raise ValueError("Tipo de página no válido.")
        if image_url and not re.match(r"^https?://", image_url, re.I):
            raise ValueError("La imagen debe usar una URL externa http:// o https://.")
        config = parse_config(form.get("configuracion", "{}"), page_type)
        return (slug, title, subtitle, content, image_url, page_type, json.dumps(config, ensure_ascii=False), 1 if form.get("activa") else 0)

    @app.route("/")
    def index():
        pages = get_db().execute("SELECT * FROM paginas WHERE activa = 1 ORDER BY created_at DESC").fetchall()
        return render_template("index.html", pages=pages)

    @app.route("/p/<slug>", methods=["GET", "POST"])
    def public_page(slug):
        page = get_page_or_404(slug)
        config = json.loads(page["configuracion"])
        if request.method == "POST":
            if page["tipo"] == "confirmacion":
                answer = request.form.get("respuesta", "")
                valid = {str(config.get("boton_1", "Sí")), str(config.get("boton_2", "No"))}
                if answer not in valid:
                    abort(400)
                get_db().execute("INSERT INTO respuestas_confirmacion (pagina_id, respuesta, created_at) VALUES (?, ?, ?)",
                    (page["id"], answer, utcnow()))
                get_db().commit()
                return render_template("response_received.html", page=page, config=config,
                    message=config.get("mensaje_posterior", "Respuesta registrada correctamente."))
            if page["tipo"] == "encuesta":
                answers = {}
                for index, question in enumerate(config.get("preguntas", [])):
                    value = request.form.get(f"q_{index}", "").strip()
                    if question.get("requerida", True) and not value:
                        flash("Completa las preguntas obligatorias.", "error")
                        return render_template("page.html", page=page, config=config)
                    if question["tipo"] == "opcion" and value and value not in question.get("opciones", []):
                        abort(400)
                    if question["tipo"] == "escala" and value:
                        try:
                            numeric = int(value)
                        except ValueError:
                            abort(400)
                        if numeric not in range(int(question.get("min", 1)), int(question.get("max", 5)) + 1):
                            abort(400)
                    answers[str(index)] = {"pregunta": question["texto"], "respuesta": value}
                get_db().execute("INSERT INTO respuestas_encuesta (pagina_id, respuestas, created_at) VALUES (?, ?, ?)",
                    (page["id"], json.dumps(answers, ensure_ascii=False), utcnow()))
                get_db().commit()
                return render_template("response_received.html", page=page, config=config,
                    message=config.get("mensaje_posterior", "Gracias por completar el formulario."))
            if page["tipo"] == "especial":
                get_db().execute("INSERT INTO respuestas_confirmacion (pagina_id, respuesta, created_at) VALUES (?, ?, ?)",
                    (page["id"], str(config.get("boton_principal", "Continuar")), utcnow()))
                get_db().commit()
                return render_template("response_received.html", page=page, config=config,
                    message=config.get("mensaje_posterior", "Recibido con calma y una pequeña dosis de magia."))
            abort(405)
        return render_template("page.html", page=page, config=config)

    @app.route("/admin/login", methods=["GET", "POST"])
    def login():
        if request.method == "POST":
            admin = get_db().execute("SELECT * FROM admins WHERE username = ?", (request.form.get("username", "").strip(),)).fetchone()
            if admin and check_password_hash(admin["password_hash"], request.form.get("password", "")):
                session.clear()
                session["admin_id"] = admin["id"]
                csrf_token()
                return redirect(url_for("admin_dashboard"))
            flash("Usuario o contraseña incorrectos.", "error")
        return render_template("login.html")

    @app.post("/admin/logout")
    @login_required
    def logout():
        session.clear()
        return redirect(url_for("index"))

    @app.route("/admin")
    @login_required
    def admin_dashboard():
        db = get_db()
        stats = {
            "pages": db.execute("SELECT COUNT(*) FROM paginas").fetchone()[0],
            "confirmations": db.execute("SELECT COUNT(*) FROM respuestas_confirmacion").fetchone()[0],
            "surveys": db.execute("SELECT COUNT(*) FROM respuestas_encuesta").fetchone()[0],
        }
        activity = db.execute("""
            SELECT p.titulo, r.created_at, r.respuesta AS detalle, 'Confirmación / especial' AS tipo
            FROM respuestas_confirmacion r JOIN paginas p ON p.id=r.pagina_id
            UNION ALL
            SELECT p.titulo, r.created_at, 'Formulario recibido' AS detalle, 'Encuesta' AS tipo
            FROM respuestas_encuesta r JOIN paginas p ON p.id=r.pagina_id
            ORDER BY created_at DESC LIMIT 12
        """).fetchall()
        return render_template("admin/dashboard.html", stats=stats, activity=activity)

    @app.route("/admin/pages")
    @login_required
    def admin_pages():
        pages = get_db().execute("SELECT * FROM paginas ORDER BY updated_at DESC").fetchall()
        return render_template("admin/pages.html", pages=pages)

    @app.route("/admin/pages/new", methods=["GET", "POST"])
    @login_required
    def admin_page_new():
        if request.method == "POST":
            try:
                payload = page_payload(request.form)
                now = utcnow()
                get_db().execute("""INSERT INTO paginas (slug,titulo,subtitulo,contenido,imagen_url,tipo,configuracion,activa,created_at,updated_at)
                    VALUES (?,?,?,?,?,?,?,?,?,?)""", (*payload, now, now))
                get_db().commit()
                flash("Página creada y agregada al directorio.", "success")
                return redirect(url_for("admin_pages"))
            except (ValueError, sqlite3.IntegrityError) as error:
                flash("El slug ya existe." if isinstance(error, sqlite3.IntegrityError) else str(error), "error")
        return render_template("admin/page_form.html", page=None)

    @app.route("/admin/pages/<int:page_id>/edit", methods=["GET", "POST"])
    @login_required
    def admin_page_edit(page_id):
        page = get_db().execute("SELECT * FROM paginas WHERE id=?", (page_id,)).fetchone()
        if page is None: abort(404)
        if request.method == "POST":
            try:
                payload = page_payload(request.form)
                get_db().execute("""UPDATE paginas SET slug=?,titulo=?,subtitulo=?,contenido=?,imagen_url=?,tipo=?,configuracion=?,activa=?,updated_at=? WHERE id=?""",
                    (*payload, utcnow(), page_id))
                get_db().commit()
                flash("Cambios guardados.", "success")
                return redirect(url_for("admin_pages"))
            except (ValueError, sqlite3.IntegrityError) as error:
                flash("El slug ya existe." if isinstance(error, sqlite3.IntegrityError) else str(error), "error")
        return render_template("admin/page_form.html", page=page)

    @app.post("/admin/pages/<int:page_id>/delete")
    @login_required
    def admin_page_delete(page_id):
        get_db().execute("DELETE FROM paginas WHERE id=?", (page_id,))
        get_db().commit()
        flash("Página y sus respuestas eliminadas.", "success")
        return redirect(url_for("admin_pages"))

    @app.route("/admin/responses")
    @login_required
    def admin_responses():
        db = get_db()
        confirmations = db.execute("SELECT r.*, p.titulo FROM respuestas_confirmacion r JOIN paginas p ON p.id=r.pagina_id ORDER BY r.created_at DESC").fetchall()
        surveys = db.execute("SELECT r.*, p.titulo FROM respuestas_encuesta r JOIN paginas p ON p.id=r.pagina_id ORDER BY r.created_at DESC").fetchall()
        return render_template("admin/responses.html", confirmations=confirmations, surveys=surveys)

    with app.app_context():
        init_db()
        # Permite el primer arranque en Render sin exponer una ruta de registro.
        bootstrap_user = os.environ.get("ADMIN_USERNAME", "").strip()
        bootstrap_password = os.environ.get("ADMIN_PASSWORD", "")
        if bootstrap_user and len(bootstrap_password) >= 12 and get_db().execute("SELECT COUNT(*) FROM admins").fetchone()[0] == 0:
            get_db().execute("INSERT INTO admins (username, password_hash, created_at) VALUES (?, ?, ?)",
                (bootstrap_user, generate_password_hash(bootstrap_password), utcnow()))
            get_db().commit()
    return app


app = create_app()

if __name__ == "__main__":
    app.run(debug=os.environ.get("FLASK_DEBUG") == "1")
